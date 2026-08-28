"""E4 authorized Recording -> reviewed Transcript lifecycle API."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..audit import add_audit
from ..authz import authorize, authorize_scope, require_auth, resource_not_found
from ..db import get_db
from ..ids import stable_id
from ..models import Patient
from ..role_context import RoleContext
from ..system_settings import effective_voice_enabled, get_settings
from ..voice.api_schemas import (
    VoiceAudioMetadataOut,
    VoiceCapabilitiesOut,
    VoiceCaptureCreate,
    VoiceCaptureOut,
    VoiceCommand,
    VoiceProcessingOut,
    VoiceReviewPatch,
)
from ..voice.asr import asr_runtime_ready, build_asr_client, configured_asr_provider
from ..voice.audio import AudioPolicy, AudioValidationError, inspect_audio
from ..voice.contracts import (
    ASRResult,
    AudioMetadata,
    AuthorizedRecording,
    CaptureMode,
    ReviewedSegment,
)
from ..voice.models import VoiceCaptureRecord
from ..voice.state_machine import (
    CaptureState,
    CaptureStatus,
    InvalidCaptureTransition,
    StaleCaptureState,
    fail_capture,
    retry_capture,
    transition_capture,
)
from ..voice.transcript import TranscriptConfirmationError, confirm_transcript
from .sources import ingest_confirmed_voice_transcript

router = APIRouter(prefix="/api/voice", tags=["voice"])

MAX_AUDIO_BYTES = 8 * 1024 * 1024
MAX_AUDIO_DURATION_MS = 120_000
AUDIO_POLICY = AudioPolicy(
    max_bytes=MAX_AUDIO_BYTES,
    max_duration_ms=MAX_AUDIO_DURATION_MS,
)

_MODE_ROLE = {
    "doctor_consult": "clinician",
    "nurse_consult": "staff",
    "patient_session": "patient",
}

_MODE_SPEAKERS = {
    "doctor_consult": {"doctor", "patient"},
    "nurse_consult": {"nurse", "patient"},
    "patient_session": {"patient", "ai", "system"},
}

ACCEPTED_AUDIO_MIME_TYPES = ["audio/webm", "audio/ogg", "audio/wav"]


def _voice_enabled(db: Session) -> bool:
    return effective_voice_enabled(db)


def _require_voice_enabled(db: Session) -> None:
    if not _voice_enabled(db):
        raise resource_not_found()
    provider = _asr_provider(db)
    if provider not in {"mock", "faster_whisper"}:
        raise HTTPException(status_code=503, detail="Voice transcription is unavailable")
    if provider == "faster_whisper" and not asr_runtime_ready("faster_whisper"):
        raise HTTPException(status_code=503, detail="Local voice transcription is unavailable")


def _asr_provider(db: Session) -> str:
    return "faster_whisper" if get_settings(db) is not None else configured_asr_provider()


@router.get("/capabilities", response_model=VoiceCapabilitiesOut)
def voice_capabilities(
    db: Session = Depends(get_db), ctx: RoleContext = Depends(require_auth)
):
    provider = _asr_provider(db)
    enabled = _voice_enabled(db)
    eligible_modes = [
        mode for mode, role in _MODE_ROLE.items() if role == ctx.role
    ]
    allowed_modes = eligible_modes if enabled else []
    # The mock remains an automated-test adapter and never exposes product UI.
    asr_ready = provider == "faster_whisper" and asr_runtime_ready(provider)
    return VoiceCapabilitiesOut(
        enabled=enabled,
        provider=provider,
        asr_ready=asr_ready,
        allowed_modes=allowed_modes,
        eligible_modes=eligible_modes,
        disabled_reason=(
            None if enabled and asr_ready
            else "disabled_by_admin" if not enabled
            else "model_not_ready"
        ),
        accepted_mime_types=ACCEPTED_AUDIO_MIME_TYPES,
        max_bytes=MAX_AUDIO_BYTES,
        max_duration_ms=MAX_AUDIO_DURATION_MS,
    )


def _state(capture: VoiceCaptureRecord) -> CaptureState:
    return CaptureState(
        capture_id=capture.capture_id,
        status=CaptureStatus(capture.status),
        revision=capture.revision,
        failure_reason=capture.failure_reason,
        retry_status=CaptureStatus(capture.retry_status) if capture.retry_status else None,
    )


def _state_values(state: CaptureState) -> dict:
    return {
        "status": state.status.value,
        "revision": state.revision,
        "failure_reason": state.failure_reason,
        "retry_status": state.retry_status.value if state.retry_status else None,
        "updated_at": datetime.now(),
    }


def _cas_capture(
    db: Session,
    capture: VoiceCaptureRecord,
    *,
    expected_status: str,
    expected_revision: int,
    values: dict,
) -> None:
    result = db.execute(
        update(VoiceCaptureRecord)
        .where(
            VoiceCaptureRecord.capture_id == capture.capture_id,
            VoiceCaptureRecord.status == expected_status,
            VoiceCaptureRecord.revision == expected_revision,
        )
        .values(**values)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Stale capture revision")


def _transition_error(exc: Exception) -> HTTPException:
    if isinstance(exc, StaleCaptureState):
        return HTTPException(status_code=409, detail="Stale capture revision")
    if isinstance(exc, InvalidCaptureTransition):
        return HTTPException(status_code=409, detail="Invalid capture state transition")
    return HTTPException(status_code=409, detail="Capture conflict")


def _get_capture(db: Session, capture_id: str) -> VoiceCaptureRecord:
    capture = db.get(VoiceCaptureRecord, capture_id)
    if capture is None:
        raise resource_not_found()
    return capture


def _authorize_capture(
    capture: VoiceCaptureRecord,
    ctx: RoleContext,
    action: str,
) -> None:
    # Scope is checked before action/owner/status/audio branching so an
    # out-of-scope capture never reveals its existence or lifecycle.
    authorize_scope(ctx, capture.clinic_id, capture.patient_id)
    authorize(ctx, action, capture.clinic_id, capture.patient_id)
    if capture.created_by != ctx.user_id:
        raise resource_not_found()


def _capture_out(capture: VoiceCaptureRecord) -> VoiceCaptureOut:
    audio = None
    if capture.audio_bytes is not None:
        audio = VoiceAudioMetadataOut(
            mime_type=capture.mime_type,
            byte_length=capture.byte_length,
            sha256=capture.audio_sha256,
            duration_ms=capture.duration_ms,
            sample_rate_hz=capture.sample_rate_hz,
            channels=capture.channels,
        )
    processing = None
    if capture.processing_metadata is not None:
        processing = VoiceProcessingOut(**capture.processing_metadata)
    return VoiceCaptureOut(
        capture_id=capture.capture_id,
        patient_id=capture.patient_id,
        capture_mode=capture.capture_mode,
        event_type=capture.event_type,
        encounter_id=capture.encounter_id,
        status=capture.status,
        revision=capture.revision,
        failure_reason=capture.failure_reason,
        started_at=capture.started_at,
        ended_at=capture.ended_at,
        created_at=capture.created_at,
        updated_at=capture.updated_at,
        audio=audio,
        machine_transcript=capture.machine_transcript,
        reviewed_segments=capture.reviewed_segments,
        event_id=capture.event_id,
        processing=processing,
    )


def _event_type(body: VoiceCaptureCreate) -> str:
    if body.capture_mode == "doctor_consult":
        return "doctor_consult"
    if body.capture_mode == "nurse_consult":
        return "nurse_consult"
    return body.patient_event_type


def _storage_time(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _operation_key(value: str, label: str) -> str:
    value = value.strip()
    if not value or len(value) > 64:
        raise HTTPException(status_code=422, detail=f"Invalid {label} idempotency key")
    return value


@router.post("/captures", response_model=VoiceCaptureOut, status_code=201)
def create_capture(
    body: VoiceCaptureCreate,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    _require_voice_enabled(db)
    patient = db.get(Patient, body.patient_id)
    if patient is None:
        raise resource_not_found()
    authorize(ctx, "create_voice_capture", patient.clinic_id, patient.patient_id)
    if _MODE_ROLE[body.capture_mode] != ctx.role:
        raise HTTPException(status_code=403, detail="Forbidden")

    event_type = _event_type(body)
    scoped_key = ":".join(
        (
            patient.clinic_id,
            ctx.user_id,
            patient.patient_id,
            "voice_capture",
            body.idempotency_key,
        )
    )
    existing = db.scalar(
        select(VoiceCaptureRecord).where(VoiceCaptureRecord.idempotency_key == scoped_key)
    )
    if existing is not None:
        identity = (
            existing.capture_mode,
            existing.event_type,
            existing.started_at,
            existing.ended_at,
            existing.encounter_id,
        )
        requested = (
            body.capture_mode,
            event_type,
            _storage_time(body.started_at),
            _storage_time(body.ended_at),
            body.encounter_id,
        )
        if identity != requested:
            raise HTTPException(status_code=409, detail="Idempotency identity conflict")
        return _capture_out(existing)

    now = datetime.now()
    capture = VoiceCaptureRecord(
        capture_id=f"vc_{stable_id(scoped_key)}",
        clinic_id=patient.clinic_id,
        patient_id=patient.patient_id,
        created_by=ctx.user_id,
        capture_mode=body.capture_mode,
        event_type=event_type,
        encounter_id=body.encounter_id,
        idempotency_key=scoped_key,
        status=CaptureStatus.CREATED.value,
        revision=0,
        retry_status=None,
        failure_reason=None,
        started_at=_storage_time(body.started_at),
        ended_at=_storage_time(body.ended_at),
        created_at=now,
        updated_at=now,
    )
    db.add(capture)
    add_audit(
        db,
        actor_id=ctx.user_id,
        actor_role=ctx.role,
        action="voice_capture_create",
        target_type="voice_capture",
        target_id=capture.capture_id,
        clinic_id=capture.clinic_id,
        patient_id=capture.patient_id,
        details={"capture_mode": capture.capture_mode, "status": capture.status},
    )
    db.commit()
    return _capture_out(capture)


@router.get("/captures/{capture_id}", response_model=VoiceCaptureOut)
def get_capture(
    capture_id: str,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    capture = _get_capture(db, capture_id)
    _authorize_capture(capture, ctx, "read_voice_capture")
    return _capture_out(capture)


@router.get("/captures/{capture_id}/audio")
def get_capture_audio(
    capture_id: str,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    capture = _get_capture(db, capture_id)
    _authorize_capture(capture, ctx, "read_voice_audio")
    if capture.audio_bytes is None:
        raise resource_not_found()
    return Response(
        content=capture.audio_bytes,
        media_type=capture.mime_type,
        headers={"Cache-Control": "private, no-store"},
    )


@router.put("/captures/{capture_id}/audio", response_model=VoiceCaptureOut)
async def upload_capture_audio(
    capture_id: str,
    request: Request,
    expected_revision: int = Header(alias="X-Expected-Revision", ge=0),
    idempotency_key: str = Header(alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    _require_voice_enabled(db)
    capture = _get_capture(db, capture_id)
    _authorize_capture(capture, ctx, "upload_voice_audio")
    upload_key = _operation_key(idempotency_key, "upload")
    declared_mime = request.headers.get("content-type", "").split(";", 1)[0].lower()
    if declared_mime not in {*ACCEPTED_AUDIO_MIME_TYPES, "audio/x-wav"}:
        raise HTTPException(status_code=415, detail="Unsupported audio media type")

    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_AUDIO_BYTES:
            raise HTTPException(status_code=413, detail="Audio exceeds size limit")
    audio_bytes = bytes(data)
    try:
        metadata = inspect_audio(
            audio_bytes,
            declared_mime_type=declared_mime,
            policy=AUDIO_POLICY,
        )
    except AudioValidationError as exc:
        if str(exc) == "audio_too_large":
            raise HTTPException(status_code=413, detail="Audio exceeds size limit") from exc
        raise HTTPException(status_code=422, detail="Invalid audio") from exc

    if capture.audio_upload_key == upload_key:
        if capture.audio_sha256 != metadata.sha256:
            raise HTTPException(status_code=409, detail="Upload idempotency conflict")
        return _capture_out(capture)
    if capture.audio_bytes is not None:
        raise HTTPException(status_code=409, detail="Recording is immutable")

    try:
        uploading = transition_capture(
            _state(capture), CaptureStatus.UPLOADING, expected_revision=expected_revision
        )
        uploaded = transition_capture(
            uploading, CaptureStatus.UPLOADED, expected_revision=uploading.revision
        )
    except (StaleCaptureState, InvalidCaptureTransition) as exc:
        raise _transition_error(exc)

    _cas_capture(
        db,
        capture,
        expected_status=CaptureStatus.CREATED.value,
        expected_revision=expected_revision,
        values={
            **_state_values(uploaded),
            "mime_type": metadata.mime_type,
            "byte_length": metadata.byte_length,
            "audio_sha256": metadata.sha256,
            "duration_ms": metadata.duration_ms,
            "sample_rate_hz": metadata.sample_rate_hz,
            "channels": metadata.channels,
            "audio_bytes": audio_bytes,
            "audio_upload_key": upload_key,
        },
    )
    add_audit(
        db,
        actor_id=ctx.user_id,
        actor_role=ctx.role,
        action="voice_audio_upload",
        target_type="voice_capture",
        target_id=capture.capture_id,
        clinic_id=capture.clinic_id,
        patient_id=capture.patient_id,
        details={
            "mime_type": metadata.mime_type,
            "byte_length": metadata.byte_length,
            "duration_ms": metadata.duration_ms,
            "sha256": metadata.sha256,
        },
    )
    db.commit()
    db.expire_all()
    capture = _get_capture(db, capture_id)
    return _capture_out(capture)


def _initial_review(capture: VoiceCaptureRecord, result: ASRResult) -> list[ReviewedSegment]:
    allowed = _MODE_SPEAKERS[capture.capture_mode]
    reviewed: list[ReviewedSegment] = []
    for index, segment in enumerate(result.segments):
        issues = list(segment.issues)
        speaker = segment.speaker_candidate
        if speaker not in allowed:
            speaker = None
            if "unknown_speaker" not in issues:
                issues.append("unknown_speaker")
        exact_range = segment.source_start_ms is not None and segment.source_end_ms is not None
        reviewed.append(
            ReviewedSegment(
                index=index,
                source_machine_segment_ids=[segment.machine_segment_id],
                speaker=speaker,
                text=segment.text,
                source_start_ms=segment.source_start_ms,
                source_end_ms=segment.source_end_ms,
                confidence=segment.confidence,
                issues=issues,
                audio_range_exact=exact_range,
                speaker_source_verified=False,
            )
        )
    return reviewed


@router.post("/captures/{capture_id}/transcribe", response_model=VoiceCaptureOut)
def transcribe_capture(
    capture_id: str,
    body: VoiceCommand,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    _require_voice_enabled(db)
    capture = _get_capture(db, capture_id)
    _authorize_capture(capture, ctx, "transcribe_voice_capture")
    if capture.transcribe_key == body.idempotency_key:
        return _capture_out(capture)

    try:
        current = _state(capture)
        if current.status is CaptureStatus.FAILED:
            transcribing = retry_capture(current, expected_revision=body.expected_revision)
        else:
            transcribing = transition_capture(
                current,
                CaptureStatus.TRANSCRIBING,
                expected_revision=body.expected_revision,
            )
    except (StaleCaptureState, InvalidCaptureTransition) as exc:
        raise _transition_error(exc)

    if capture.audio_bytes is None:
        raise HTTPException(status_code=409, detail="Recording is not uploaded")
    _cas_capture(
        db,
        capture,
        expected_status=capture.status,
        expected_revision=body.expected_revision,
        values={**_state_values(transcribing), "transcribe_key": body.idempotency_key},
    )
    db.commit()
    db.expire_all()
    capture = _get_capture(db, capture_id)

    metadata = AudioMetadata(
        mime_type=capture.mime_type,
        byte_length=capture.byte_length,
        sha256=capture.audio_sha256,
        duration_ms=capture.duration_ms,
        sample_rate_hz=capture.sample_rate_hz,
        channels=capture.channels,
    )
    recording = AuthorizedRecording(
        capture_id=capture.capture_id,
        clinic_id=capture.clinic_id,
        patient_id=capture.patient_id,
        capture_mode=CaptureMode(capture.capture_mode),
        audio_bytes=capture.audio_bytes,
        metadata=metadata,
    )
    try:
        result = build_asr_client(_asr_provider(db)).transcribe(recording)
    except Exception:
        result = ASRResult(
            provider="unavailable",
            method="adapter_error",
            model=None,
            version=None,
            language=None,
            segments=[],
            degraded=True,
            failure_reason="asr_provider_error",
        )

    if result.failure_reason is not None:
        failed = fail_capture(
            _state(capture),
            result.failure_reason,
            expected_revision=capture.revision,
        )
        _cas_capture(
            db,
            capture,
            expected_status=CaptureStatus.TRANSCRIBING.value,
            expected_revision=capture.revision,
            values=_state_values(failed),
        )
        add_audit(
            db,
            actor_id=ctx.user_id,
            actor_role=ctx.role,
            action="voice_failed",
            target_type="voice_capture",
            target_id=capture.capture_id,
            clinic_id=capture.clinic_id,
            patient_id=capture.patient_id,
            details={"stage": "transcribing", "reason": result.failure_reason},
        )
        db.commit()
        db.expire_all()
        capture = _get_capture(db, capture_id)
        return _capture_out(capture)

    reviewed = _initial_review(capture, result)
    needs_review = transition_capture(
        _state(capture),
        CaptureStatus.NEEDS_REVIEW,
        expected_revision=capture.revision,
    )
    _cas_capture(
        db,
        capture,
        expected_status=CaptureStatus.TRANSCRIBING.value,
        expected_revision=capture.revision,
        values={
            **_state_values(needs_review),
            "machine_transcript": result.model_dump(mode="json"),
            "reviewed_segments": [segment.model_dump(mode="json") for segment in reviewed],
        },
    )
    add_audit(
        db,
        actor_id=ctx.user_id,
        actor_role=ctx.role,
        action="voice_transcribe",
        target_type="voice_capture",
        target_id=capture.capture_id,
        clinic_id=capture.clinic_id,
        patient_id=capture.patient_id,
        details={
            "provider": result.provider,
            "method": result.method,
            "degraded": result.degraded,
            "segment_count": len(result.segments),
        },
    )
    db.commit()
    db.expire_all()
    capture = _get_capture(db, capture_id)
    return _capture_out(capture)


def _reviewed_from_patch(
    capture: VoiceCaptureRecord,
    body: VoiceReviewPatch,
) -> list[ReviewedSegment]:
    machine = ASRResult.model_validate(capture.machine_transcript)
    by_id = {segment.machine_segment_id: segment for segment in machine.segments}
    supplied = {
        source_id
        for edit in body.segments
        for source_id in edit.source_machine_segment_ids
    }
    if supplied != set(by_id):
        raise HTTPException(status_code=422, detail="Every machine segment must remain represented")

    allowed = _MODE_SPEAKERS[capture.capture_mode]
    reviewed: list[ReviewedSegment] = []
    for index, edit in enumerate(body.segments):
        if len(set(edit.source_machine_segment_ids)) != len(edit.source_machine_segment_ids):
            raise HTTPException(status_code=422, detail="Duplicate machine segment reference")
        try:
            sources = [by_id[source_id] for source_id in edit.source_machine_segment_ids]
        except KeyError as exc:
            raise HTTPException(status_code=422, detail="Unknown machine segment") from exc
        source_issues = set().union(*(set(source.issues) for source in sources))
        for source in sources:
            if source.speaker_candidate not in allowed:
                source_issues.add("unknown_speaker")
        resolved = set(edit.resolved_issues)
        if not resolved.issubset(source_issues):
            raise HTTPException(status_code=422, detail="Cannot resolve an unobserved issue")
        issues = sorted(source_issues - resolved)
        if edit.speaker not in allowed:
            if "unknown_speaker" not in issues:
                issues.append("unknown_speaker")
        if capture.capture_mode == "patient_session" and edit.speaker in {"ai", "system"}:
            observed = any(source.speaker_candidate == edit.speaker for source in sources)
            if not edit.speaker_source_verified or not observed:
                raise HTTPException(
                    status_code=422,
                    detail="ai/system speaker is not supported by the source",
                )
        exact = (
            len(sources) == 1
            and edit.text == sources[0].text
            and sources[0].source_start_ms is not None
            and sources[0].source_end_ms is not None
        )
        reviewed.append(
            ReviewedSegment(
                index=index,
                source_machine_segment_ids=edit.source_machine_segment_ids,
                speaker=edit.speaker,
                text=edit.text,
                source_start_ms=sources[0].source_start_ms if exact else None,
                source_end_ms=sources[0].source_end_ms if exact else None,
                confidence=sources[0].confidence if len(sources) == 1 else None,
                issues=issues,
                audio_range_exact=exact,
                speaker_source_verified=edit.speaker_source_verified,
            )
        )
    return reviewed


@router.patch("/captures/{capture_id}/segments", response_model=VoiceCaptureOut)
def review_capture_segments(
    capture_id: str,
    body: VoiceReviewPatch,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    _require_voice_enabled(db)
    capture = _get_capture(db, capture_id)
    _authorize_capture(capture, ctx, "review_voice_transcript")
    if capture.revision != body.expected_revision:
        raise HTTPException(status_code=409, detail="Stale capture revision")
    if capture.status != CaptureStatus.NEEDS_REVIEW.value or capture.machine_transcript is None:
        raise HTTPException(status_code=409, detail="Capture is not ready for review")

    reviewed = _reviewed_from_patch(capture, body)
    _cas_capture(
        db,
        capture,
        expected_status=CaptureStatus.NEEDS_REVIEW.value,
        expected_revision=body.expected_revision,
        values={
            "reviewed_segments": [segment.model_dump(mode="json") for segment in reviewed],
            "revision": body.expected_revision + 1,
            "updated_at": datetime.now(),
        },
    )
    add_audit(
        db,
        actor_id=ctx.user_id,
        actor_role=ctx.role,
        action="voice_review",
        target_type="voice_capture",
        target_id=capture.capture_id,
        clinic_id=capture.clinic_id,
        patient_id=capture.patient_id,
        details={"segment_count": len(reviewed)},
    )
    db.commit()
    db.expire_all()
    capture = _get_capture(db, capture_id)
    return _capture_out(capture)


@router.post("/captures/{capture_id}/confirm", response_model=VoiceCaptureOut)
def confirm_capture(
    capture_id: str,
    body: VoiceCommand,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    _require_voice_enabled(db)
    capture = _get_capture(db, capture_id)
    _authorize_capture(capture, ctx, "confirm_voice_transcript")
    if capture.confirm_key == body.idempotency_key and capture.status == CaptureStatus.PROCESSED.value:
        return _capture_out(capture)

    if capture.status == CaptureStatus.CONFIRMED.value:
        if capture.confirm_key != body.idempotency_key or capture.revision != body.expected_revision:
            raise HTTPException(status_code=409, detail="Confirm operation conflict")
    else:
        if capture.revision != body.expected_revision:
            raise HTTPException(status_code=409, detail="Stale capture revision")
        if capture.status != CaptureStatus.NEEDS_REVIEW.value:
            raise HTTPException(status_code=409, detail="Capture is not ready to confirm")
        try:
            reviewed = [
                ReviewedSegment.model_validate(segment)
                for segment in capture.reviewed_segments or []
            ]
            confirmed = confirm_transcript(CaptureMode(capture.capture_mode), reviewed)
        except (TranscriptConfirmationError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="Transcript review is incomplete") from exc

        try:
            confirmed_state = transition_capture(
                _state(capture),
                CaptureStatus.CONFIRMED,
                expected_revision=body.expected_revision,
            )
        except (StaleCaptureState, InvalidCaptureTransition) as exc:
            raise _transition_error(exc)
        _cas_capture(
            db,
            capture,
            expected_status=CaptureStatus.NEEDS_REVIEW.value,
            expected_revision=body.expected_revision,
            values={
                **_state_values(confirmed_state),
                "confirmed_transcript": confirmed.content.model_dump(mode="json"),
                "audio_ranges": [
                    item.model_dump(mode="json") for item in confirmed.audio_ranges
                ],
                "confirm_key": body.idempotency_key,
            },
        )
        add_audit(
            db,
            actor_id=ctx.user_id,
            actor_role=ctx.role,
            action="voice_confirm",
            target_type="voice_capture",
            target_id=capture.capture_id,
            clinic_id=capture.clinic_id,
            patient_id=capture.patient_id,
            details={"segment_count": len(confirmed.content.segments)},
        )
        db.commit()
        db.expire_all()
        capture = _get_capture(db, capture_id)

    result = ingest_confirmed_voice_transcript(
        db=db,
        ctx=ctx,
        capture_id=capture.capture_id,
        patient_id=capture.patient_id,
        event_type=capture.event_type,
        started_at=capture.started_at,
        ended_at=capture.ended_at,
        encounter_id=capture.encounter_id,
        content=capture.confirmed_transcript,
        audio_ranges=capture.audio_ranges or [],
    )
    capture = db.get(VoiceCaptureRecord, capture.capture_id)
    processing_metadata = {
        "method": result["generation_method"],
        "degraded": result["degraded"],
        "fallback_reason": result["fallback_reason"],
    }
    processed = transition_capture(
        _state(capture),
        CaptureStatus.PROCESSED,
        expected_revision=capture.revision,
    )
    _cas_capture(
        db,
        capture,
        expected_status=CaptureStatus.CONFIRMED.value,
        expected_revision=capture.revision,
        values={
            **_state_values(processed),
            "event_id": result["event_id"],
            "transcript_artifact_id": result["source_artifact_id"],
            "encounter_id": result["encounter_id"],
            "processing_metadata": processing_metadata,
        },
    )
    add_audit(
        db,
        actor_id=ctx.user_id,
        actor_role=ctx.role,
        action="voice_processed",
        target_type="voice_capture",
        target_id=capture.capture_id,
        clinic_id=capture.clinic_id,
        patient_id=capture.patient_id,
        event_id=result["event_id"],
        details={
            "method": processing_metadata["method"],
            "degraded": processing_metadata["degraded"],
        },
    )
    db.commit()
    db.expire_all()
    capture = _get_capture(db, capture_id)
    return _capture_out(capture)
