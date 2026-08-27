"""D3 transcript limits reject explicitly and never truncate."""
from __future__ import annotations

from sqlalchemy import func, select

from app.models import Artifact, Event


def _record_counts(db_session) -> tuple[int, int]:
    return (
        db_session.scalar(select(func.count()).select_from(Event)),
        db_session.scalar(select(func.count()).select_from(Artifact)),
    )


def test_overlong_utf8_input_returns_413_without_persistence(clinician_client, db_session):
    raw = "DOCTOR: " + ("A" * 4100) + "\nPATIENT: End."
    before = _record_counts(db_session)
    response = clinician_client.post("/api/transcripts/normalize", json={"raw_text": raw})
    assert response.status_code == 413
    assert _record_counts(db_session) == before


def test_segment_text_limit_returns_422_without_truncation(clinician_client):
    raw = "DOCTOR: " + ("A" * 4001)
    response = clinician_client.post("/api/transcripts/normalize", json={"raw_text": raw})
    assert response.status_code == 422
    assert response.json()["error"]["message"] == "SEGMENT_TEXT_TOO_LONG"


def test_segment_count_limit_returns_422_without_partial_preview(clinician_client):
    raw = "\n".join("Dr:x" for _ in range(501))
    assert len(raw.encode("utf-8")) < 4096
    response = clinician_client.post("/api/transcripts/normalize", json={"raw_text": raw})
    assert response.status_code == 422
    assert response.json()["error"]["message"] == "TOO_MANY_SEGMENTS"


def test_whitespace_only_input_returns_explicit_422(clinician_client):
    response = clinician_client.post("/api/transcripts/normalize", json={"raw_text": "  \n\n  "})
    assert response.status_code == 422
    assert response.json()["error"]["message"] == "EMPTY_INPUT"
