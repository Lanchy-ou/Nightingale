"""Voice review correction never overwrites machine observations."""

from app.api import voice as voice_api
from app.voice.models import VoiceCaptureRecord
from tests.voice_api_helpers import create_payload, mock_asr_for, synthetic_wav, upload


def _prepare_unknown(clinician_client, monkeypatch):
    audio = synthetic_wav()
    monkeypatch.setattr(
        voice_api,
        "build_asr_client",
        lambda _provider: mock_asr_for(
            audio,
            speaker=None,
            confidence=0.4,
            issues=["unknown_speaker", "low_confidence"],
        ),
    )
    capture_id = clinician_client.post("/api/voice/captures", json=create_payload()).json()["capture_id"]
    assert upload(clinician_client, capture_id, audio).status_code == 200
    response = clinician_client.post(
        f"/api/voice/captures/{capture_id}/transcribe",
        json={"expected_revision": 2, "idempotency_key": "transcribe-unknown"},
    )
    assert response.status_code == 200
    return capture_id, response.json()


def test_unknown_and_low_confidence_block_then_explicit_review_resolves(
    clinician_client, monkeypatch, db_session
):
    capture_id, transcript = _prepare_unknown(clinician_client, monkeypatch)
    blocked = clinician_client.post(
        f"/api/voice/captures/{capture_id}/confirm",
        json={"expected_revision": 4, "idempotency_key": "confirm-blocked"},
    )
    assert blocked.status_code == 422

    reviewed = clinician_client.patch(
        f"/api/voice/captures/{capture_id}/segments",
        json={
            "expected_revision": 4,
            "segments": [
                {
                    "source_machine_segment_ids": ["seg_0"],
                    "speaker": "doctor",
                    "text": "My headache is worse and happening almost every day.",
                    "resolved_issues": ["unknown_speaker", "low_confidence"],
                }
            ],
        },
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["revision"] == 5
    assert reviewed.json()["reviewed_segments"][0]["issues"] == []

    confirmed = clinician_client.post(
        f"/api/voice/captures/{capture_id}/confirm",
        json={"expected_revision": 5, "idempotency_key": "confirm-reviewed"},
    )
    assert confirmed.status_code == 200

    capture = db_session.get(VoiceCaptureRecord, capture_id)
    assert capture.machine_transcript == transcript["machine_transcript"]
    assert capture.confirmed_transcript["segments"][0]["speaker"] == "doctor"


def test_split_reindexes_and_clears_unprovable_audio_ranges(
    clinician_client, monkeypatch, db_session
):
    capture_id, _ = _prepare_unknown(clinician_client, monkeypatch)
    response = clinician_client.patch(
        f"/api/voice/captures/{capture_id}/segments",
        json={
            "expected_revision": 4,
            "segments": [
                {
                    "source_machine_segment_ids": ["seg_0"],
                    "speaker": "doctor",
                    "text": "My headache is worse",
                    "resolved_issues": ["unknown_speaker", "low_confidence"],
                },
                {
                    "source_machine_segment_ids": ["seg_0"],
                    "speaker": "patient",
                    "text": "and happening almost every day.",
                    "resolved_issues": ["unknown_speaker", "low_confidence"],
                },
            ],
        },
    )
    assert response.status_code == 200
    segments = response.json()["reviewed_segments"]
    assert [segment["index"] for segment in segments] == [0, 1]
    assert all(segment["source_start_ms"] is None for segment in segments)
    assert all(segment["source_end_ms"] is None for segment in segments)
    assert all(segment["audio_range_exact"] is False for segment in segments)


def test_stale_review_revision_returns_conflict(clinician_client, monkeypatch):
    capture_id, _ = _prepare_unknown(clinician_client, monkeypatch)
    payload = {
        "expected_revision": 3,
        "segments": [
            {
                "source_machine_segment_ids": ["seg_0"],
                "speaker": "doctor",
                "text": "My headache is worse and happening almost every day.",
                "resolved_issues": ["unknown_speaker", "low_confidence"],
            }
        ],
    }
    assert clinician_client.patch(
        f"/api/voice/captures/{capture_id}/segments", json=payload
    ).status_code == 409


def test_review_cannot_drop_machine_segments(clinician_client, monkeypatch):
    capture_id, _ = _prepare_unknown(clinician_client, monkeypatch)
    response = clinician_client.patch(
        f"/api/voice/captures/{capture_id}/segments",
        json={"expected_revision": 4, "segments": []},
    )
    assert response.status_code == 422


def test_patient_cannot_invent_system_speaker_presence(patient_client, monkeypatch):
    audio = synthetic_wav()
    monkeypatch.setattr(
        voice_api,
        "build_asr_client",
        lambda _provider: mock_asr_for(audio, speaker="patient", text="I feel better."),
    )
    capture_id = patient_client.post(
        "/api/voice/captures",
        json=create_payload(capture_mode="patient_session", idempotency_key="patient-system"),
    ).json()["capture_id"]
    assert upload(patient_client, capture_id, audio).status_code == 200
    assert patient_client.post(
        f"/api/voice/captures/{capture_id}/transcribe",
        json={"expected_revision": 2, "idempotency_key": "patient-system-transcribe"},
    ).status_code == 200
    response = patient_client.patch(
        f"/api/voice/captures/{capture_id}/segments",
        json={
            "expected_revision": 4,
            "segments": [
                {
                    "source_machine_segment_ids": ["seg_0"],
                    "speaker": "system",
                    "text": "I feel better.",
                    "resolved_issues": [],
                    "speaker_source_verified": True,
                }
            ],
        },
    )
    assert response.status_code == 422
