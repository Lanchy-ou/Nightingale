"""E3 deterministic storage tiering and reversible shadow-archive proof.

This module is maintenance/write-path code.  Clinical read endpoints never
call it and never decompress the shadow payload.  ``Artifact.content`` remains
the sole authoritative content throughout E3.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import zlib

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from .importance_learning import compose_score, requested_adaptive_adjustment
from .models import Artifact, ArtifactStorageState, Event, Highlight, Task, User
from .provenance_binding import current_source_matches_binding
from .tasks import UNRESOLVED_TASK_STATUSES, resolve_exact_span

POLICY_VERSION = "decay-v1"
HOT_MAX_AGE_DAYS = 30
WARM_MAX_AGE_DAYS = 365
DECAY_BY_TIER = {"hot": 0, "warm": -1, "cold": -2}
CODEC = "zlib-json-v1"

PROTECTION_REASON_ORDER = (
    "explicit_risk",
    "unresolved_task",
    "clinician_confirmed",
    "pinned",
    "needs_review",
    "current_patient_instruction",
    "provenance_unverified",
    "archive_integrity_failed",
    "canonicalization_failed",
)


class ArchiveIntegrityError(ValueError):
    """The compressed shadow copy cannot be proven equivalent to its source."""


@dataclass(frozen=True)
class ShadowArchive:
    source_sha256: str
    compressed_payload: bytes
    original_bytes: int
    compressed_bytes: int


@dataclass(frozen=True)
class ArtifactPolicyResult:
    artifact_id: str
    tier: str
    reason_codes: tuple[str, ...]
    decay_adjustment: int
    protected: bool
    archive_eligible: bool
    source_sha256: str | None
    codec: str | None
    original_bytes: int | None
    compressed_bytes: int | None
    roundtrip_verified: bool


@dataclass(frozen=True)
class StoragePolicyReport:
    policy_version: str
    as_of: datetime
    artifacts: tuple[ArtifactPolicyResult, ...]
    updated_count: int
    highlight_updated_count: int

    @property
    def tier_counts(self) -> dict[str, int]:
        return {
            tier: sum(row.tier == tier for row in self.artifacts)
            for tier in ("hot", "warm", "cold")
        }

    @property
    def protected_count(self) -> int:
        return sum(row.protected for row in self.artifacts)

    @property
    def archive_candidate_count(self) -> int:
        return sum(row.archive_eligible for row in self.artifacts)

    @property
    def original_bytes(self) -> int:
        return sum(row.original_bytes or 0 for row in self.artifacts if row.archive_eligible)

    @property
    def compressed_bytes(self) -> int:
        return sum(row.compressed_bytes or 0 for row in self.artifacts if row.archive_eligible)

    def to_safe_dict(self) -> dict:
        ratio = (
            round(self.compressed_bytes / self.original_bytes, 4)
            if self.original_bytes
            else None
        )
        return {
            "policy_version": self.policy_version,
            "as_of": self.as_of.isoformat(),
            "tier_counts": self.tier_counts,
            "protected_count": self.protected_count,
            "archive_candidate_count": self.archive_candidate_count,
            "original_bytes": self.original_bytes,
            "compressed_bytes": self.compressed_bytes,
            "compressed_to_original_ratio": ratio,
            "roundtrip_verified_count": sum(
                row.roundtrip_verified for row in self.artifacts
            ),
            "updated_count": self.updated_count,
            "highlight_updated_count": self.highlight_updated_count,
            "artifacts": [
                {
                    "artifact_id": row.artifact_id,
                    "tier": row.tier,
                    "reason_codes": list(row.reason_codes),
                    "protected": row.protected,
                    "archive_eligible": row.archive_eligible,
                    "original_bytes": row.original_bytes,
                    "compressed_bytes": row.compressed_bytes,
                    "roundtrip_verified": row.roundtrip_verified,
                }
                for row in self.artifacts
            ],
            "limitation": (
                "Shadow archive only: authoritative Artifact.content remains in the "
                "database, so these compression figures are not total database savings."
            ),
        }


def canonical_json_bytes(content: dict) -> bytes:
    if not isinstance(content, dict):
        raise TypeError("Artifact content must be a JSON object")
    return json.dumps(
        content,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def build_shadow_archive(content: dict) -> ShadowArchive:
    canonical = canonical_json_bytes(content)
    payload = zlib.compress(canonical, level=9)
    digest = hashlib.sha256(canonical).hexdigest()
    # Verify before any caller can persist the payload.
    if zlib.decompress(payload) != canonical:
        raise ArchiveIntegrityError("Shadow archive round-trip mismatch")
    return ShadowArchive(
        source_sha256=digest,
        compressed_payload=payload,
        original_bytes=len(canonical),
        compressed_bytes=len(payload),
    )


def restore_shadow_archive(state: ArtifactStorageState) -> dict:
    if state.codec != CODEC or not isinstance(state.compressed_payload, bytes):
        raise ArchiveIntegrityError("Unsupported or missing shadow archive payload")
    try:
        canonical = zlib.decompress(state.compressed_payload)
    except zlib.error as exc:
        raise ArchiveIntegrityError("Shadow archive decompression failed") from exc
    digest = hashlib.sha256(canonical).hexdigest()
    if not state.source_sha256 or digest != state.source_sha256:
        raise ArchiveIntegrityError("Shadow archive hash mismatch")
    try:
        restored = json.loads(canonical.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArchiveIntegrityError("Shadow archive JSON is invalid") from exc
    if canonical_json_bytes(restored) != canonical:
        raise ArchiveIntegrityError("Shadow archive is not canonical JSON")
    return restored


def _age_decision(event_time: datetime, as_of: datetime) -> tuple[str, tuple[str, ...]]:
    if event_time > as_of:
        return "hot", ("future_event_time",)
    age_seconds = (as_of - event_time).total_seconds()
    if age_seconds <= HOT_MAX_AGE_DAYS * 86400:
        return "hot", ("current_window",)
    if age_seconds <= WARM_MAX_AGE_DAYS * 86400:
        return "warm", ("warm_age",)
    return "cold", ("cold_age",)


def _ordered_reasons(reasons: set[str]) -> tuple[str, ...]:
    return tuple(reason for reason in PROTECTION_REASON_ORDER if reason in reasons)


def _provenance_verified(
    artifact: Artifact,
    event: Event,
    *,
    artifacts_by_id: dict[str, Artifact],
    related_highlights: list[Highlight],
    sourced_tasks: list[Task],
    voice_captures_by_id: dict[str, object],
) -> bool:
    for highlight in related_highlights:
        if highlight.source_artifact_id == artifact.artifact_id:
            if not current_source_matches_binding(highlight, artifact):
                return False
        if (
            highlight.artifact_id == artifact.artifact_id
            and highlight.source_artifact_id != artifact.artifact_id
        ):
            pointer = artifact.provenance_pointer
            source = artifacts_by_id.get(highlight.source_artifact_id or "")
            if (
                not isinstance(pointer, dict)
                or pointer.get("event_id") != event.event_id
                or pointer.get("artifact_id") != highlight.source_artifact_id
                or source is None
                or source.event_id != event.event_id
                or not current_source_matches_binding(highlight, source)
            ):
                return False

    for task in sourced_tasks:
        if resolve_exact_span(artifact.content, task.source_span) is None:
            return False

    pointer = artifact.provenance_pointer
    if pointer is not None:
        if not isinstance(pointer, dict):
            return False
        recording_capture_id = pointer.get("recording_capture_id")
        if recording_capture_id is not None:
            capture = voice_captures_by_id.get(recording_capture_id)
            audio_ranges = pointer.get("audio_ranges")
            if (
                capture is None
                or getattr(capture, "transcript_artifact_id", None) != artifact.artifact_id
                or getattr(capture, "event_id", None) != event.event_id
                or getattr(capture, "patient_id", None) != event.patient_id
                or getattr(capture, "clinic_id", None) != event.clinic_id
                or not isinstance(audio_ranges, list)
            ):
                return False
            for item in audio_ranges:
                if not isinstance(item, dict):
                    return False
                values = (
                    item.get("segment_index"),
                    item.get("source_start_ms"),
                    item.get("source_end_ms"),
                )
                if any(not isinstance(value, int) or isinstance(value, bool) for value in values):
                    return False
                if values[0] < 0 or values[1] < 0 or values[2] < values[1]:
                    return False
            return True
        source = artifacts_by_id.get(pointer.get("artifact_id", ""))
        if (
            pointer.get("event_id") != event.event_id
            or source is None
            or source.event_id != event.event_id
        ):
            return False
    return True


def _existing_archive_corrupt(state: ArtifactStorageState | None) -> bool:
    if state is None or state.compressed_payload is None:
        return False
    try:
        restore_shadow_archive(state)
    except ArchiveIntegrityError:
        return True
    return False


def _same_state(state: ArtifactStorageState, desired: dict) -> bool:
    return all(getattr(state, key) == value for key, value in desired.items())


def run_storage_policy(
    db: Session,
    *,
    as_of: datetime,
    apply: bool,
    evaluated_at: datetime | None = None,
) -> StoragePolicyReport:
    """Evaluate all Artifacts and optionally atomically persist state/scores."""
    if not isinstance(as_of, datetime):
        raise TypeError("as_of must be an injected datetime")
    evaluated_at = evaluated_at or datetime.now()

    rows = db.execute(
        select(Artifact, Event).join(Event, Artifact.event_id == Event.event_id)
    ).all()
    artifacts = [artifact for artifact, _event in rows]
    event_by_id = {event.event_id: event for _artifact, event in rows}
    artifacts_by_id = {artifact.artifact_id: artifact for artifact in artifacts}
    highlights = db.scalars(select(Highlight)).all()
    tasks = db.scalars(select(Task)).all()

    highlights_by_artifact: dict[str, list[Highlight]] = {}
    for highlight in highlights:
        for artifact_id in {highlight.artifact_id, highlight.source_artifact_id} - {None}:
            highlights_by_artifact.setdefault(artifact_id, []).append(highlight)
    tasks_by_event: dict[str, list[Task]] = {}
    tasks_by_artifact: dict[str, list[Task]] = {}
    for task in tasks:
        tasks_by_event.setdefault(task.event_id, []).append(task)
        if task.source_artifact_id:
            tasks_by_artifact.setdefault(task.source_artifact_id, []).append(task)

    users_by_id = {user.user_id: user for user in db.scalars(select(User)).all()}
    current_instruction_ids: set[str] = set()
    instructions_by_patient: dict[str, list[tuple[Artifact, Event]]] = {}
    for artifact, event in rows:
        author = users_by_id.get(artifact.author_id or "")
        instruction = artifact.content.get("instruction")
        if (
            artifact.artifact_type == "patient_instruction"
            and artifact.author_role == "clinician"
            and author is not None
            and author.role == "clinician"
            and author.clinic_id == event.clinic_id
            and isinstance(instruction, str)
            and instruction.strip()
        ):
            instructions_by_patient.setdefault(event.patient_id, []).append((artifact, event))
    for candidates in instructions_by_patient.values():
        current = max(
            candidates,
            key=lambda row: (row[1].started_at, row[0].created_at, row[0].artifact_id),
        )
        current_instruction_ids.add(current[0].artifact_id)

    bind = db.get_bind()
    has_state_table = inspect(bind).has_table("artifact_storage_state")
    existing_states = (
        {row.artifact_id: row for row in db.scalars(select(ArtifactStorageState)).all()}
        if has_state_table
        else {}
    )
    voice_captures_by_id: dict[str, object] = {}
    if inspect(bind).has_table("voice_captures"):
        from .voice.models import VoiceCaptureRecord

        voice_captures_by_id = {
            capture.capture_id: capture
            for capture in db.scalars(select(VoiceCaptureRecord)).all()
        }

    decisions: dict[str, ArtifactPolicyResult] = {}
    desired_states: dict[str, dict] = {}
    for artifact in sorted(artifacts, key=lambda row: row.artifact_id):
        event = event_by_id[artifact.event_id]
        related = [
            highlight
            for highlight in highlights_by_artifact.get(artifact.artifact_id, [])
            if highlight.event_id == event.event_id
            and highlight.patient_id == event.patient_id
        ]
        event_tasks = [
            task
            for task in tasks_by_event.get(event.event_id, [])
            if task.patient_id == event.patient_id and task.clinic_id == event.clinic_id
        ]
        sourced_tasks = [
            task
            for task in tasks_by_artifact.get(artifact.artifact_id, [])
            if task.event_id == event.event_id
            and task.patient_id == event.patient_id
            and task.clinic_id == event.clinic_id
        ]
        protections: set[str] = set()
        if any(bool(h.feature_flags.get("explicit_risk")) for h in related):
            protections.add("explicit_risk")
        if any(task.status in UNRESOLVED_TASK_STATUSES for task in event_tasks):
            protections.add("unresolved_task")
        if any(bool(h.feature_flags.get("clinician_confirmed")) for h in related):
            protections.add("clinician_confirmed")
        if any(h.status == "pinned" for h in related):
            protections.add("pinned")
        if any(h.review_status == "needs_review" for h in related):
            protections.add("needs_review")
        if artifact.artifact_id in current_instruction_ids:
            protections.add("current_patient_instruction")
        if not _provenance_verified(
            artifact,
            event,
            artifacts_by_id=artifacts_by_id,
            related_highlights=related,
            sourced_tasks=sourced_tasks,
            voice_captures_by_id=voice_captures_by_id,
        ):
            protections.add("provenance_unverified")

        existing = existing_states.get(artifact.artifact_id)
        if _existing_archive_corrupt(existing):
            protections.add("archive_integrity_failed")

        archive: ShadowArchive | None = None
        try:
            canonical = canonical_json_bytes(artifact.content)
            source_sha256 = hashlib.sha256(canonical).hexdigest()
            original_bytes = len(canonical)
        except (TypeError, ValueError):
            canonical = None
            source_sha256 = None
            original_bytes = None
            protections.add("canonicalization_failed")

        if protections:
            tier = "hot"
            reasons = _ordered_reasons(protections)
        else:
            tier, reasons = _age_decision(event.started_at, as_of)

        if tier == "cold":
            try:
                archive = build_shadow_archive(artifact.content)
            except (TypeError, ValueError, zlib.error):
                tier = "hot"
                reasons = ("archive_integrity_failed",)

        decay = DECAY_BY_TIER[tier]
        roundtrip_verified = archive is not None
        result = ArtifactPolicyResult(
            artifact_id=artifact.artifact_id,
            tier=tier,
            reason_codes=reasons,
            decay_adjustment=decay,
            protected=any(reason in PROTECTION_REASON_ORDER for reason in reasons),
            archive_eligible=tier == "cold" and archive is not None,
            source_sha256=source_sha256,
            codec=CODEC if archive else None,
            original_bytes=original_bytes,
            compressed_bytes=archive.compressed_bytes if archive else None,
            roundtrip_verified=roundtrip_verified,
        )
        decisions[artifact.artifact_id] = result
        verified_at = None
        if archive is not None:
            if (
                existing is not None
                and existing.codec == CODEC
                and existing.source_sha256 == archive.source_sha256
                and existing.compressed_payload == archive.compressed_payload
                and existing.roundtrip_verified_at is not None
            ):
                verified_at = existing.roundtrip_verified_at
            else:
                verified_at = evaluated_at
        desired_states[artifact.artifact_id] = {
            "tier": tier,
            "reason_codes": list(reasons),
            "policy_version": POLICY_VERSION,
            "evaluated_as_of": as_of,
            "source_sha256": source_sha256,
            "codec": CODEC if archive else None,
            "compressed_payload": archive.compressed_payload if archive else None,
            "original_bytes": original_bytes,
            "compressed_bytes": archive.compressed_bytes if archive else None,
            "roundtrip_verified_at": verified_at,
        }

    updated_count = 0
    highlight_updated_count = 0
    if apply:
        if not has_state_table:
            raise RuntimeError("E3 schema is missing; run migrate_e3_schema first")
        try:
            for artifact_id, desired in desired_states.items():
                state = existing_states.get(artifact_id)
                if state is None:
                    state = ArtifactStorageState(
                        artifact_id=artifact_id,
                        evaluated_at=evaluated_at,
                        **desired,
                    )
                    db.add(state)
                    updated_count += 1
                elif not _same_state(state, desired):
                    for key, value in desired.items():
                        setattr(state, key, value)
                    state.evaluated_at = evaluated_at
                    db.add(state)
                    updated_count += 1

            tasks_by_id = {task.task_id: task for task in tasks}
            for highlight in highlights:
                highlight_event = event_by_id.get(highlight.event_id)
                candidate_artifact_id = (
                    highlight.source_artifact_id or highlight.artifact_id
                )
                candidate_artifact = artifacts_by_id.get(candidate_artifact_id or "")
                valid_scope = bool(
                    highlight_event is not None
                    and highlight_event.patient_id == highlight.patient_id
                )
                valid_artifact = bool(
                    valid_scope
                    and candidate_artifact is not None
                    and candidate_artifact.event_id == highlight.event_id
                )
                decision = (
                    decisions.get(candidate_artifact_id or "")
                    if valid_artifact
                    else None
                )
                if decision is not None:
                    desired_decay = decision.decay_adjustment
                elif valid_scope and candidate_artifact_id is None:
                    tier, _reasons = _age_decision(
                        highlight_event.started_at, as_of
                    )
                    desired_decay = DECAY_BY_TIER[tier]
                else:
                    desired_decay = 0

                linked_task = tasks_by_id.get(highlight.task_id or "")
                real_unresolved = bool(
                    linked_task is not None
                    and highlight_event is not None
                    and linked_task.status in UNRESOLVED_TASK_STATUSES
                    and linked_task.event_id == highlight.event_id
                    and linked_task.patient_id == highlight.patient_id
                    and linked_task.clinic_id == highlight_event.clinic_id
                )
                score_flags = {
                    **highlight.feature_flags,
                    "unresolved_task": real_unresolved,
                }
                rescored = compose_score(
                    base_importance_score=highlight.base_importance_score,
                    adaptive_adjustment=requested_adaptive_adjustment(
                        highlight.adaptive_adjustment, highlight.learning_metadata
                    ),
                    decay_adjustment=desired_decay,
                    feature_flags=score_flags,
                    status=highlight.status,
                    review_status=highlight.review_status,
                    learning_metadata=highlight.learning_metadata,
                )
                values = (
                    rescored.base_importance_score,
                    rescored.adaptive_adjustment,
                    rescored.decay_adjustment,
                    rescored.importance_score,
                    rescored.learning_metadata,
                )
                current = (
                    highlight.base_importance_score,
                    highlight.adaptive_adjustment,
                    highlight.decay_adjustment,
                    highlight.importance_score,
                    highlight.learning_metadata,
                )
                if values != current:
                    (
                        highlight.base_importance_score,
                        highlight.adaptive_adjustment,
                        highlight.decay_adjustment,
                        highlight.importance_score,
                        highlight.learning_metadata,
                    ) = values
                    highlight.updated_at = evaluated_at
                    db.add(highlight)
                    highlight_updated_count += 1
            if highlight_updated_count:
                from .glance_projection import rebuild_glance_projections

                for patient_id in sorted({row.patient_id for row in highlights}):
                    rebuild_glance_projections(db, patient_id, as_of=evaluated_at)
            db.commit()
        except Exception:
            db.rollback()
            raise

    return StoragePolicyReport(
        policy_version=POLICY_VERSION,
        as_of=as_of,
        artifacts=tuple(decisions[key] for key in sorted(decisions)),
        updated_count=updated_count,
        highlight_updated_count=highlight_updated_count,
    )
