"""F Final: clinician review attestation and mixed-language transport evidence."""
from __future__ import annotations

from app import ingestion_service

from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.ai_pipeline import run_pipeline
from app.extraction import Candidate
from app.highlights import extract_text
from app.llm_client import MockLLMClient
from app.models import Artifact, AuditLog, Event, Highlight
from app.voice.models import VoiceCaptureRecord
from seed import fixture
from tests.voice_api_helpers import create_payload, mock_asr_for, synthetic_wav, upload


ATTESTATION = fixture.DOCTOR_CONSULT_REVIEW_ATTESTATION


def _doctor_payload(identity: str, *, attested: bool = True) -> dict:
    payload = {
        "consult_id": f"feedback-{identity}",
        "ingestion_key": f"feedback-submit-{identity}",
        "started_at": "2026-09-03T09:00:00",
        "ended_at": "2026-09-03T09:20:00",
        "content": deepcopy(fixture.F_FINAL_MIXED_LANGUAGE_DOCTOR_TRANSCRIPT),
    }
    if attested:
        payload.update(ATTESTATION)
    return payload


def _force_fallback(monkeypatch) -> None:
    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "deepseek")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("Natingale_API_KEY", raising=False)


def test_manual_attestation_missing_or_false_blocks_before_raw_and_retry_is_safe(
    clinician_client, db_session, monkeypatch
):
    _force_fallback(monkeypatch)
    before_events = db_session.scalar(select(func.count()).select_from(Event))
    before_artifacts = db_session.scalar(select(func.count()).select_from(Artifact))
    missing = _doctor_payload("manual-gate", attested=False)

    response = clinician_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/doctor-consults", json=missing
    )
    assert response.status_code == 422

    false_attestation = {**missing, **ATTESTATION, "mixed_language_content_reviewed": False}
    response = clinician_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/doctor-consults",
        json=false_attestation,
    )
    assert response.status_code == 422
    assert db_session.scalar(select(func.count()).select_from(Event)) == before_events
    assert db_session.scalar(select(func.count()).select_from(Artifact)) == before_artifacts

    accepted = clinician_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/doctor-consults",
        json={**missing, **ATTESTATION},
    )
    replay = clinician_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/doctor-consults",
        json={**missing, **ATTESTATION},
    )
    assert accepted.status_code == replay.status_code == 200
    assert replay.json()["idempotent_replay"] is True
    event_id = accepted.json()["event"]["event_id"]
    source_id = accepted.json()["source_artifact_id"]
    assert db_session.scalar(
        select(func.count()).select_from(Event).where(Event.event_id == event_id)
    ) == 1
    assert db_session.scalar(
        select(func.count()).select_from(Artifact).where(
            Artifact.artifact_id == source_id,
            Artifact.artifact_type == "transcript",
        )
    ) == 1


def test_manual_attestation_audit_is_metadata_only(
    clinician_client, db_session, monkeypatch
):
    _force_fallback(monkeypatch)
    payload = _doctor_payload("audit")
    payload["content"]["segments"][4]["text"] = (
        "Alice Tan, IC 880523-01-1234, phone 012-3456789: "
        "continue propranolol 20 mg daily."
    )
    response = clinician_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/doctor-consults", json=payload
    )
    assert response.status_code == 200, response.text
    audit = db_session.scalar(
        select(AuditLog).where(
            AuditLog.event_id == response.json()["event"]["event_id"],
            AuditLog.action == "doctor_consult_create",
        )
    )
    assert audit is not None
    assert audit.actor_id == fixture.USER_CLINICIAN_ID
    assert audit.actor_role == "clinician"
    assert audit.created_at is not None
    assert audit.details == ATTESTATION
    serialized = json.dumps(audit.details).lower()
    for forbidden in (
        "alice tan",
        "880523-01-1234",
        "012-3456789",
        "propranolol",
        "20 mg",
    ):
        assert forbidden not in serialized


@pytest.mark.parametrize("user_id", [fixture.USER_PATIENT_ID, fixture.USER_STAFF_ID])
def test_patient_and_staff_cannot_attest_doctor_consult(client, user_id):
    response = client.post(
        f"/api/patients/{fixture.PATIENT_ID}/doctor-consults",
        headers={"X-User-Id": user_id},
        json=_doctor_payload(f"rbac-{user_id}"),
    )
    assert response.status_code == 403


def test_mixed_language_round_trip_and_mock_exact_provenance(
    clinician_client, db_session, monkeypatch
):
    from app.api import sources

    quote = fixture.F_FINAL_MIXED_LANGUAGE_DOCTOR_TRANSCRIPT["segments"][1]["text"]
    mock = MockLLMClient(
        candidates=[
            Candidate(
                text="Patient-reported symptom change",
                quote=quote,
                risk_reason="Exact patient statement requires human review",
                entity_type="symptom",
                symptom_change=True,
            )
        ]
    )
    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "mock")
    monkeypatch.setattr(ingestion_service, "build_client", lambda _provider: mock)

    response = clinician_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/doctor-consults",
        json=_doctor_payload("round-trip"),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    raw = db_session.get(Artifact, body["source_artifact_id"])
    assert raw.content == fixture.F_FINAL_MIXED_LANGUAGE_DOCTOR_TRANSCRIPT
    assert raw.content["segments"][1]["text"].encode("utf-8").decode("utf-8") == quote
    assert [item["index"] for item in raw.content["segments"]] == list(
        range(len(raw.content["segments"]))
    )
    assert [item["speaker"] for item in raw.content["segments"]] == [
        "doctor",
        "patient",
        "doctor",
        "patient",
        "doctor",
    ]
    assert len(body["highlight_ids"]) == 1
    highlight = db_session.get(Highlight, body["highlight_ids"][0])
    assert extract_text(raw.content, highlight.source_span) == quote

    provenance = clinician_client.get(
        f"/api/highlights/{highlight.highlight_id}/provenance"
    )
    assert provenance.status_code == 200
    assert provenance.json()["quote"] == quote
    assert provenance.json()["source_artifact"]["artifact_id"] == raw.artifact_id
    assert provenance.json()["span"]["kind"] == "segment"


def test_nonexistent_multilingual_claim_is_dropped_and_fallback_does_not_invent(
    db_session,
):
    statement = fixture.F_FINAL_MIXED_LANGUAGE_DOCTOR_TRANSCRIPT["segments"][1]["text"]
    event = Event(
        event_id="evt_feedback_multilingual_fail_closed",
        patient_id=fixture.PATIENT_ID,
        clinic_id=fixture.CLINIC_ID,
        event_type="doctor_consult",
        started_at=datetime(2026, 9, 3, 10, 0),
        ended_at=None,
        created_at=datetime(2026, 9, 3, 10, 1),
    )
    raw = Artifact(
        artifact_id="art_feedback_multilingual_fail_closed",
        event_id=event.event_id,
        artifact_type="transcript",
        author_role="system",
        author_id=None,
        content={"segments": [{"index": 0, "speaker": "patient", "text": statement}]},
        created_at=datetime(2026, 9, 3, 10, 1),
        version=1,
        provenance_pointer=None,
    )
    db_session.add_all([event, raw])
    db_session.commit()
    client = MockLLMClient(
        candidates=[
            Candidate(
                text="Invented medication translation",
                quote="Take invented medicine 999 mg now.",
                risk_reason="Invented multilingual interpretation",
                entity_type="medication",
            )
        ]
    )

    output = run_pipeline(
        db_session,
        event,
        raw,
        "ai_doctor_consult_summary",
        datetime(2026, 9, 3, 11, 0),
        client,
        "mock",
    )
    assert output.method == "deterministic_fallback"
    assert output.fallback_reason == "anchor_drop_rate"
    assert output.summary_content["summary"] == statement
    assert all("invented" not in candidate.text.lower() for candidate in output.candidates)
    assert all(extract_text(raw.content, candidate.span) and extract_text(raw.content, candidate.span) in statement for candidate in output.candidates)
    serialized = json.dumps(output.summary_content).lower()
    assert "invented" not in serialized
    assert "999 mg" not in serialized


def test_unknown_speaker_stays_blocked_until_reviewed_and_attested(
    clinician_client, monkeypatch
):
    _force_fallback(monkeypatch)
    raw_text = "AH MA: Sakit kepala is better, but nausea masih ada, bo pian."
    preview = clinician_client.post(
        "/api/transcripts/normalize", json={"raw_text": raw_text}
    )
    assert preview.status_code == 200
    assert preview.json()["outcome"] == "NEEDS_REVIEW"
    assert preview.json()["segments"][0]["speaker_candidate"] is None

    unresolved = _doctor_payload("unknown-speaker")
    unresolved["content"] = {
        "segments": [{"index": 0, "speaker": "ah_ma", "text": raw_text.split(": ", 1)[1]}]
    }
    assert clinician_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/doctor-consults", json=unresolved
    ).status_code == 422

    reviewed = deepcopy(unresolved)
    reviewed["content"]["segments"][0]["speaker"] = "patient"
    accepted = clinician_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/doctor-consults", json=reviewed
    )
    assert accepted.status_code == 200, accepted.text


def test_doctor_voice_confirmation_requires_attestation_and_audits_only_metadata(
    clinician_client, db_session, monkeypatch
):
    from app.api import voice as voice_api

    audio = synthetic_wav()
    monkeypatch.setattr(voice_api, "build_asr_client", lambda _provider: mock_asr_for(audio))
    capture_id = clinician_client.post(
        "/api/voice/captures",
        json=create_payload(idempotency_key="feedback-voice-capture"),
    ).json()["capture_id"]
    assert upload(clinician_client, capture_id, audio).status_code == 200
    assert clinician_client.post(
        f"/api/voice/captures/{capture_id}/transcribe",
        json={"expected_revision": 2, "idempotency_key": "feedback-voice-transcribe"},
    ).status_code == 200

    missing = clinician_client.post(
        f"/api/voice/captures/{capture_id}/confirm",
        json={"expected_revision": 4, "idempotency_key": "feedback-voice-confirm"},
    )
    false = clinician_client.post(
        f"/api/voice/captures/{capture_id}/confirm",
        json={
            "expected_revision": 4,
            "idempotency_key": "feedback-voice-confirm",
            **ATTESTATION,
            "medication_dosage_mentions_reviewed": False,
        },
    )
    assert missing.status_code == false.status_code == 422
    capture = db_session.get(VoiceCaptureRecord, capture_id)
    assert capture.status == "needs_review"
    assert capture.event_id is None
    assert capture.transcript_artifact_id is None

    complete = clinician_client.post(
        f"/api/voice/captures/{capture_id}/confirm",
        json={
            "expected_revision": 4,
            "idempotency_key": "feedback-voice-confirm",
            **ATTESTATION,
        },
    )
    assert complete.status_code == 200, complete.text
    capture = db_session.get(VoiceCaptureRecord, capture_id)
    audit = db_session.scalar(
        select(AuditLog).where(
            AuditLog.target_id == capture_id,
            AuditLog.action == "voice_confirm",
        )
    )
    assert audit is not None
    assert audit.actor_id == fixture.USER_CLINICIAN_ID
    assert audit.actor_role == "clinician"
    assert audit.details == ATTESTATION


def test_clinician_confirmation_ui_exposes_all_three_required_checks():
    root = Path(__file__).resolve().parents[2]
    manual = (root / "frontend/src/components/NewDoctorConsult.tsx").read_text(
        encoding="utf-8"
    )
    voice = (root / "frontend/src/components/VoiceCapture.tsx").read_text(
        encoding="utf-8"
    )
    api = (root / "frontend/src/api.ts").read_text(encoding="utf-8")
    types = (root / "frontend/src/types.ts").read_text(encoding="utf-8")
    for field in ATTESTATION:
        assert field in manual
        assert field in voice
        assert field in types
    assert "...reviewAttestation" in api
    assert "Object.values(reviewAttestation).every(Boolean)" in manual
    assert "captureMode === 'doctor_consult'" in voice
    assert "translation or medical-reference validation" in manual
    assert "translation or medical-reference validation" in voice
