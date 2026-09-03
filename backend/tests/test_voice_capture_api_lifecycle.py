"""E4 persisted capture lifecycle through confirmed raw-first ingestion."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event as ThreadEvent

import pytest
from sqlalchemy import select
from fastapi.testclient import TestClient

from app.api import voice as voice_api
from app.api import sources as sources_api
from app.highlights import extract_text
from app.main import app
from app.models import Artifact, Event, Highlight
from app.voice.models import VoiceCaptureRecord
from seed import fixture
from tests.voice_api_helpers import create_payload, mock_asr_for, synthetic_wav, upload


def test_clinician_voice_capture_reaches_existing_ai_and_exact_provenance(
    clinician_client, db_session, monkeypatch
):
    audio = synthetic_wav()
    monkeypatch.setattr(
        voice_api,
        "build_asr_client",
        lambda _provider: mock_asr_for(audio),
    )

    created = clinician_client.post("/api/voice/captures", json=create_payload())
    assert created.status_code == 201
    capture_id = created.json()["capture_id"]
    assert created.json()["status"] == "created"
    assert created.json()["revision"] == 0
    assert "audio_bytes" not in created.json()

    uploaded = upload(clinician_client, capture_id, audio)
    assert uploaded.status_code == 200
    assert uploaded.json()["status"] == "uploaded"
    assert uploaded.json()["revision"] == 2

    transcribed = clinician_client.post(
        f"/api/voice/captures/{capture_id}/transcribe",
        json={"expected_revision": 2, "idempotency_key": "transcribe-voice-1"},
    )
    assert transcribed.status_code == 200
    assert transcribed.json()["status"] == "needs_review"
    assert transcribed.json()["revision"] == 4
    assert transcribed.json()["machine_transcript"]["segments"][0]["text"].startswith("My headache")

    confirmed = clinician_client.post(
        f"/api/voice/captures/{capture_id}/confirm",
        json={
            "expected_revision": 4,
            "idempotency_key": "confirm-voice-1",
            **fixture.DOCTOR_CONSULT_REVIEW_ATTESTATION,
        },
    )
    assert confirmed.status_code == 200
    body = confirmed.json()
    assert body["status"] == "processed"
    assert body["revision"] == 6
    assert body["event_id"]
    assert body["processing"]["degraded"] in {True, False}
    assert "transcript_artifact_id" not in body
    assert "ai_summary_artifact_id" not in body
    assert "highlight_ids" not in body

    capture = db_session.get(VoiceCaptureRecord, capture_id)
    assert capture.audio_bytes == audio
    assert capture.machine_transcript["segments"][0]["text"].startswith("My headache")
    assert capture.confirmed_transcript == {
        "segments": [
            {
                "index": 0,
                "speaker": "doctor",
                "text": "My headache is worse and happening almost every day.",
            }
        ]
    }

    event = db_session.get(Event, capture.event_id)
    transcript = db_session.get(Artifact, capture.transcript_artifact_id)
    assert event.event_type == "doctor_consult"
    assert transcript.artifact_type == "transcript"
    assert transcript.author_role == "system"
    assert transcript.content == capture.confirmed_transcript
    assert transcript.provenance_pointer["recording_capture_id"] == capture_id
    assert transcript.provenance_pointer["audio_ranges"] == [
        {"segment_index": 0, "source_start_ms": 0, "source_end_ms": 250}
    ]

    summary = db_session.scalar(
        select(Artifact).where(
            Artifact.event_id == event.event_id,
            Artifact.artifact_type == "ai_doctor_consult_summary",
        )
    )
    assert summary is not None
    highlights = db_session.scalars(
        select(Highlight).where(Highlight.source_artifact_id == transcript.artifact_id)
    ).all()
    assert highlights
    for highlight in highlights:
        assert extract_text(transcript.content, highlight.source_span) is not None


def test_upload_and_confirm_replays_are_idempotent(
    clinician_client, monkeypatch, db_session
):
    audio = synthetic_wav()
    monkeypatch.setattr(voice_api, "build_asr_client", lambda _provider: mock_asr_for(audio))
    capture_id = clinician_client.post("/api/voice/captures", json=create_payload()).json()["capture_id"]

    first_upload = upload(clinician_client, capture_id, audio)
    replay_upload = upload(clinician_client, capture_id, audio)
    assert replay_upload.status_code == 200
    assert replay_upload.json() == first_upload.json()

    first_transcribe = clinician_client.post(
        f"/api/voice/captures/{capture_id}/transcribe",
        json={"expected_revision": 2, "idempotency_key": "transcribe-voice-1"},
    )
    replay_transcribe = clinician_client.post(
        f"/api/voice/captures/{capture_id}/transcribe",
        json={"expected_revision": 2, "idempotency_key": "transcribe-voice-1"},
    )
    assert replay_transcribe.status_code == 200
    assert replay_transcribe.json() == first_transcribe.json()

    first_confirm = clinician_client.post(
        f"/api/voice/captures/{capture_id}/confirm",
        json={
            "expected_revision": 4,
            "idempotency_key": "confirm-voice-1",
            **fixture.DOCTOR_CONSULT_REVIEW_ATTESTATION,
        },
    )
    replay_confirm = clinician_client.post(
        f"/api/voice/captures/{capture_id}/confirm",
        json={
            "expected_revision": 4,
            "idempotency_key": "confirm-voice-1",
            **fixture.DOCTOR_CONSULT_REVIEW_ATTESTATION,
        },
    )
    assert replay_confirm.status_code == 200
    assert replay_confirm.json() == first_confirm.json()

    capture = db_session.get(VoiceCaptureRecord, capture_id)
    assert db_session.scalar(
        select(Event).where(Event.event_id == capture.event_id)
    ) is not None
    assert len(
        db_session.scalars(select(Event).where(Event.event_id == capture.event_id)).all()
    ) == 1


def test_asr_failure_is_explicit_and_creates_no_event_or_summary(
    clinician_client, monkeypatch, db_session
):
    from app.voice.asr import DeterministicMockASRClient

    audio = synthetic_wav()
    monkeypatch.setattr(
        voice_api,
        "build_asr_client",
        lambda _provider: DeterministicMockASRClient({}),
    )
    capture_id = clinician_client.post("/api/voice/captures", json=create_payload()).json()["capture_id"]
    assert upload(clinician_client, capture_id, audio).status_code == 200

    response = clinician_client.post(
        f"/api/voice/captures/{capture_id}/transcribe",
        json={"expected_revision": 2, "idempotency_key": "transcribe-fail-1"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["failure_reason"] == "mock_fixture_not_found"

    capture = db_session.get(VoiceCaptureRecord, capture_id)
    assert capture.event_id is None
    assert capture.transcript_artifact_id is None
    assert db_session.get(Event, f"evt_voice_{capture_id}") is None


def test_asr_failure_audit_and_db_use_fixed_error_code(
    clinician_client, monkeypatch, db_session
):
    from app.models import AuditLog
    from app.voice.asr import DeterministicMockASRClient
    from app.voice.contracts import ASR_FAILURE_CODES

    audio = synthetic_wav()
    monkeypatch.setattr(
        voice_api,
        "build_asr_client",
        lambda _provider: DeterministicMockASRClient({}),
    )
    capture_id = clinician_client.post("/api/voice/captures", json=create_payload()).json()["capture_id"]
    assert upload(clinician_client, capture_id, audio).status_code == 200

    response = clinician_client.post(
        f"/api/voice/captures/{capture_id}/transcribe",
        json={"expected_revision": 2, "idempotency_key": "transcribe-fail-audit"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["failure_reason"] == "mock_fixture_not_found"

    capture = db_session.get(VoiceCaptureRecord, capture_id)
    assert capture.failure_reason in ASR_FAILURE_CODES

    audits = db_session.scalars(
        select(AuditLog).where(
            AuditLog.target_id == capture_id, AuditLog.action == "voice_failed"
        )
    ).all()
    assert len(audits) == 1
    details = audits[0].details
    assert details["error_code"] == "mock_fixture_not_found"
    assert details["error_code"] in ASR_FAILURE_CODES
    assert "reason" not in details


def test_raw_audio_download_is_creator_only_and_never_in_json(
    clinician_client, client, db_session
):
    audio = synthetic_wav()
    capture_id = clinician_client.post("/api/voice/captures", json=create_payload()).json()["capture_id"]
    assert upload(clinician_client, capture_id, audio).status_code == 200

    own = clinician_client.get(f"/api/voice/captures/{capture_id}/audio")
    assert own.status_code == 200
    assert own.content == audio
    assert own.headers["content-type"].startswith("audio/wav")

    other = client.get(
        f"/api/voice/captures/{capture_id}/audio",
        headers={"X-User-Id": fixture.USER_CLINICIAN_B_ID},
    )
    assert other.status_code == 404

    capture_json = clinician_client.get(f"/api/voice/captures/{capture_id}").json()
    assert "audio_bytes" not in capture_json
    assert audio.hex() not in str(capture_json)


def test_staff_voice_creates_separate_nurse_event_and_summary(
    staff_client, monkeypatch, db_session
):
    audio = synthetic_wav()
    monkeypatch.setattr(
        voice_api,
        "build_asr_client",
        lambda _provider: mock_asr_for(
            audio,
            speaker="nurse",
            text="Your blood pressure is elevated at 158 over 96.",
        ),
    )
    capture_id = staff_client.post(
        "/api/voice/captures",
        json=create_payload(capture_mode="nurse_consult", idempotency_key="nurse-voice"),
    ).json()["capture_id"]
    assert upload(staff_client, capture_id, audio).status_code == 200
    assert staff_client.post(
        f"/api/voice/captures/{capture_id}/transcribe",
        json={"expected_revision": 2, "idempotency_key": "nurse-transcribe"},
    ).status_code == 200
    response = staff_client.post(
        f"/api/voice/captures/{capture_id}/confirm",
        json={"expected_revision": 4, "idempotency_key": "nurse-confirm"},
    )
    assert response.status_code == 200
    capture = db_session.get(VoiceCaptureRecord, capture_id)
    event = db_session.get(Event, capture.event_id)
    assert event.event_type == "nurse_consult"
    assert db_session.scalar(
        select(Artifact).where(
            Artifact.event_id == event.event_id,
            Artifact.artifact_type == "ai_nurse_consult_summary",
        )
    ) is not None


def test_patient_voice_creates_patient_event_without_internal_ids_in_response(
    patient_client, monkeypatch, db_session
):
    audio = synthetic_wav()
    monkeypatch.setattr(
        voice_api,
        "build_asr_client",
        lambda _provider: mock_asr_for(
            audio,
            speaker="patient",
            text="My headache is better but nausea persists.",
        ),
    )
    capture_id = patient_client.post(
        "/api/voice/captures",
        json=create_payload(capture_mode="patient_session", idempotency_key="patient-voice"),
    ).json()["capture_id"]
    assert upload(patient_client, capture_id, audio).status_code == 200
    assert patient_client.post(
        f"/api/voice/captures/{capture_id}/transcribe",
        json={"expected_revision": 2, "idempotency_key": "patient-transcribe"},
    ).status_code == 200
    response = patient_client.post(
        f"/api/voice/captures/{capture_id}/confirm",
        json={"expected_revision": 4, "idempotency_key": "patient-confirm"},
    )
    assert response.status_code == 200
    assert "transcript_artifact_id" not in response.json()
    assert "ai_summary_artifact_id" not in response.json()
    capture = db_session.get(VoiceCaptureRecord, capture_id)
    event = db_session.get(Event, capture.event_id)
    transcript = db_session.get(Artifact, capture.transcript_artifact_id)
    assert event.event_type == "patient_followup"
    assert transcript.author_role == "system"
    assert db_session.scalar(
        select(Artifact).where(
            Artifact.event_id == event.event_id,
            Artifact.artifact_type == "ai_patient_session_summary",
        )
    ) is not None


def test_competing_transcribe_revision_has_one_winner(
    clinician_client, monkeypatch
):
    audio = synthetic_wav()
    delegate = mock_asr_for(audio)
    started = ThreadEvent()
    release = ThreadEvent()

    class SlowASR:
        def transcribe(self, recording):
            started.set()
            assert release.wait(timeout=5)
            return delegate.transcribe(recording)

    monkeypatch.setattr(voice_api, "build_asr_client", lambda _provider: SlowASR())
    capture_id = clinician_client.post("/api/voice/captures", json=create_payload()).json()["capture_id"]
    assert upload(clinician_client, capture_id, audio).status_code == 200

    with TestClient(app, headers={"X-User-Id": fixture.USER_CLINICIAN_ID}) as first_client:
        with TestClient(app, headers={"X-User-Id": fixture.USER_CLINICIAN_ID}) as second_client:
            with ThreadPoolExecutor(max_workers=1) as executor:
                first = executor.submit(
                    first_client.post,
                    f"/api/voice/captures/{capture_id}/transcribe",
                    json={"expected_revision": 2, "idempotency_key": "transcribe-race-a"},
                )
                assert started.wait(timeout=5)
                second = second_client.post(
                    f"/api/voice/captures/{capture_id}/transcribe",
                    json={"expected_revision": 2, "idempotency_key": "transcribe-race-b"},
                )
                release.set()
                first_response = first.result(timeout=5)

    assert sorted([first_response.status_code, second.status_code]) == [200, 409]


def test_confirmed_transcript_and_event_survive_derived_pipeline_failure(
    clinician_client, monkeypatch, db_session
):
    audio = synthetic_wav()
    monkeypatch.setattr(voice_api, "build_asr_client", lambda _provider: mock_asr_for(audio))
    capture_id = clinician_client.post("/api/voice/captures", json=create_payload()).json()["capture_id"]
    assert upload(clinician_client, capture_id, audio).status_code == 200
    assert clinician_client.post(
        f"/api/voice/captures/{capture_id}/transcribe",
        json={"expected_revision": 2, "idempotency_key": "raw-first-transcribe"},
    ).status_code == 200

    def fail_after_raw(*_args, **_kwargs):
        raise RuntimeError("synthetic derived failure")

    monkeypatch.setattr(sources_api, "_ingest_common", fail_after_raw)
    with pytest.raises(RuntimeError, match="synthetic derived failure"):
        clinician_client.post(
            f"/api/voice/captures/{capture_id}/confirm",
            json={
                "expected_revision": 4,
                "idempotency_key": "raw-first-confirm",
                **fixture.DOCTOR_CONSULT_REVIEW_ATTESTATION,
            },
        )

    db_session.expire_all()
    capture = db_session.get(VoiceCaptureRecord, capture_id)
    assert capture.status == "confirmed"
    event_id = f"evt_{voice_api.stable_id('voice_capture', capture.clinic_id, capture.patient_id, capture_id)}"
    transcript_id = f"art_{voice_api.stable_id('voice_transcript', capture.clinic_id, capture.patient_id, capture_id)}"
    event = db_session.get(Event, event_id)
    transcript = db_session.get(Artifact, transcript_id)
    assert event is not None
    assert transcript is not None
    assert transcript.content == capture.confirmed_transcript
    assert db_session.scalar(
        select(Artifact).where(
            Artifact.event_id == event_id,
            Artifact.artifact_type == "ai_doctor_consult_summary",
        )
    ) is None


def test_timezone_aware_create_replay_uses_stable_utc_identity(clinician_client):
    payload = create_payload(idempotency_key="timezone-replay")
    payload["started_at"] = "2026-08-27T10:00:00+08:00"
    payload["ended_at"] = "2026-08-27T10:02:00+08:00"
    first = clinician_client.post("/api/voice/captures", json=payload)
    replay = clinician_client.post("/api/voice/captures", json=payload)
    assert first.status_code == replay.status_code == 201
    assert first.json() == replay.json()
