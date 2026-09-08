"""D3 preview API must be strict, non-persistent, and LLM-free."""
from __future__ import annotations

from app import ingestion_service

from sqlalchemy import func, select

from app.models import Artifact, AuditLog, Event
from seed import fixture


RAW = "Doctor: Any nausea?\nPatient: No nausea today."


def _counts(db_session) -> tuple[int, int, int]:
    return (
        db_session.scalar(select(func.count()).select_from(Event)),
        db_session.scalar(select(func.count()).select_from(Artifact)),
        db_session.scalar(select(func.count()).select_from(AuditLog)),
    )


def test_normalize_preview_exact_shape_no_persistence_and_no_provider(
    clinician_client, db_session, monkeypatch
):
    import app.api.sources as sources

    def forbidden(*args, **kwargs):  # pragma: no cover - failure path
        raise AssertionError("normalization must not call provider or pipeline")

    monkeypatch.setattr(ingestion_service, "build_client", forbidden)
    monkeypatch.setattr(ingestion_service, "run_pipeline", forbidden)
    before = _counts(db_session)

    response = clinician_client.post("/api/transcripts/normalize", json={"raw_text": RAW})
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {
        "outcome",
        "normalize_reason",
        "raw_byte_length",
        "segments",
        "issues",
    }
    assert body["outcome"] == "ACCEPT"
    assert body["normalize_reason"] is None
    assert body["raw_byte_length"] == len(RAW.encode("utf-8"))
    assert body["issues"] == []
    assert [segment["index"] for segment in body["segments"]] == [0, 1]
    assert all(
        set(segment)
        == {
            "index",
            "speaker_candidate",
            "text",
            "source_start",
            "source_end",
            "confidence_marker",
            "issues",
        }
        for segment in body["segments"]
    )
    assert _counts(db_session) == before


def test_preview_ranges_resolve_to_exact_raw_substrings(clinician_client):
    response = clinician_client.post("/api/transcripts/normalize", json={"raw_text": RAW})
    assert response.status_code == 200
    for segment in response.json()["segments"]:
        assert RAW[segment["source_start"] : segment["source_end"]] == segment["text"]


def test_unknown_speaker_is_visible_and_never_defaulted(clinician_client):
    raw = "CONSULTANT: Describe the symptom.\nPATIENT: Headache."
    response = clinician_client.post("/api/transcripts/normalize", json={"raw_text": raw})
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "NEEDS_REVIEW"
    assert body["normalize_reason"] == "UNKNOWN_SPEAKER_LABEL"
    assert body["segments"][0]["speaker_candidate"] is None
    assert body["segments"][0]["confidence_marker"] == "unknown"
    assert "unknown_speaker_label:CONSULTANT" in body["segments"][0]["issues"]


def test_normalize_endpoint_is_clinician_only(client):
    expected = {
        fixture.USER_CLINICIAN_ID: 200,
        fixture.USER_STAFF_ID: 403,
        fixture.USER_PATIENT_ID: 403,
        fixture.USER_ADMIN_ID: 403,
    }
    for user_id, status in expected.items():
        response = client.post(
            "/api/transcripts/normalize",
            headers={"X-User-Id": user_id},
            json={"raw_text": RAW},
        )
        assert response.status_code == status
    assert client.post("/api/transcripts/normalize", json={"raw_text": RAW}).status_code == 401


def test_normalize_request_is_strict(clinician_client):
    extra = clinician_client.post(
        "/api/transcripts/normalize", json={"raw_text": RAW, "patient_id": fixture.PATIENT_ID}
    )
    empty = clinician_client.post("/api/transcripts/normalize", json={"raw_text": ""})
    assert extra.status_code == 422
    assert empty.status_code == 422


def test_canonical_confirm_rejects_preview_metadata_and_source_ranges(clinician_client):
    """Preview source_start/source_end/confidence_marker/issues are informational
    only. The confirm boundary must reject them so a drifted or pseudo-precise
    range can never enter the immutable canonical Transcript."""
    response = clinician_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/doctor-consults",
        json={
            "consult_id": "d3-range-reject",
            "ingestion_key": "d3-range-reject-key",
            "started_at": "2026-08-27T09:00:00",
            **fixture.DOCTOR_CONSULT_REVIEW_ATTESTATION,
            "content": {
                "segments": [
                    {
                        "index": 0,
                        "speaker": "doctor",
                        "text": "Any nausea?",
                        "source_start": 0,
                        "source_end": 11,
                    }
                ]
            },
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_confirmed_transcript_segments_have_only_canonical_fields(clinician_client, db_session):
    created = clinician_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/doctor-consults",
        json={
            "consult_id": "d3-canonical-fields",
            "ingestion_key": "d3-canonical-fields-key",
            "started_at": "2026-08-27T09:05:00",
            **fixture.DOCTOR_CONSULT_REVIEW_ATTESTATION,
            "content": {
                "segments": [
                    {"index": 0, "speaker": "doctor", "text": "Any nausea?"},
                    {"index": 1, "speaker": "patient", "text": "No nausea today."},
                ]
            },
        },
    )
    assert created.status_code == 200, created.text
    source_artifact_id = created.json()["source_artifact_id"]
    artifact = db_session.get(Artifact, source_artifact_id)
    assert artifact is not None
    for segment in artifact.content["segments"]:
        assert set(segment) == {"index", "speaker", "text"}
        assert segment["speaker"] in {"doctor", "patient"}
