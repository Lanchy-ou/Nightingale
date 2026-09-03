"""F_A5: explicit Provider total timeout.

Covers: a never-returning Provider hits the total wall-clock deadline AND the
underlying async call is cancelled; Consult/Check-in fall back with
``provider_timeout``; Copilot is unavailable (no substitute answer); key
deployment key verification times out and never saves the key; raw source persists exactly
once and retry produces no duplicate.
"""
from __future__ import annotations

import asyncio
import socket
import threading
import time
from datetime import datetime

import pytest
from sqlalchemy import select

from app import llm_client
from app.ai_pipeline import run_pipeline
from app.copilot import answer_query
from app.copilot_models import CopilotQuery
from app.llm_client import DeepSeekAdapter, ProviderTimeoutError
from app.models import Artifact, Event, Patient, PatientCheckInMessage
from app.redaction import RedactedContent
from seed import fixture


class _TimeoutClient:
    """A Provider that never returns (every entry raises the timeout error)."""

    def summarize(self, redacted, flow_type):
        raise ProviderTimeoutError("simulated total deadline")

    def copilot(self, redacted, category):
        raise ProviderTimeoutError("simulated total deadline")

    def checkin_turn(self, redacted, clarification_count):
        raise ProviderTimeoutError("simulated total deadline")

    def checkin_summary(self, redacted):
        raise ProviderTimeoutError("simulated total deadline")


def _never_completing(observer: dict):
    async def _run(self, *, system, messages, max_tokens):
        try:
            await asyncio.Event().wait()  # never completes
        except asyncio.CancelledError:
            observer["cancelled"] = True
            raise
        return None

    return _run


class _NeverRespondingHTTPServer:
    """Accept one real SDK request, then wait for client cancellation."""

    def __init__(self):
        self.accepted = threading.Event()
        self.disconnected = threading.Event()
        self._stop = threading.Event()
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen(1)
        self._listener.settimeout(0.05)
        self.base_url = f"http://127.0.0.1:{self._listener.getsockname()[1]}"
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self):
        connection = None
        try:
            while not self._stop.is_set():
                try:
                    connection, _ = self._listener.accept()
                    break
                except TimeoutError:
                    continue
                except OSError:
                    return
            if connection is None:
                return
            self.accepted.set()
            connection.settimeout(0.05)
            while not self._stop.is_set():
                try:
                    if connection.recv(4096) == b"":
                        self.disconnected.set()
                        return
                except TimeoutError:
                    continue
                except OSError:
                    self.disconnected.set()
                    return
        finally:
            if connection is not None:
                connection.close()

    def close(self):
        self._stop.set()
        self._listener.close()
        self._thread.join(timeout=2)


def test_total_deadline_raises_provider_timeout_and_cancels(monkeypatch):
    observer = {}
    monkeypatch.setattr(DeepSeekAdapter, "_messages_create_async", _never_completing(observer))
    monkeypatch.setattr(llm_client, "PROVIDER_TOTAL_DEADLINE_SECONDS", 0.2)

    adapter = DeepSeekAdapter(api_key="dummy-key")
    started = time.perf_counter()
    with pytest.raises(ProviderTimeoutError):
        adapter.summarize(
            RedactedContent(content={"segments": []}, redaction_counts={}),
            "ai_doctor_consult_summary",
        )
    elapsed = time.perf_counter() - started

    # The injected 0.2s bound fired, far below the real 30s policy.
    assert elapsed < 5.0
    # The underlying async coroutine was actually cancelled.
    assert observer.get("cancelled") is True


def test_real_async_anthropic_request_uses_phase_timeouts_and_is_cancelled(monkeypatch):
    server = _NeverRespondingHTTPServer()
    try:
        monkeypatch.setattr(llm_client, "DEEPSEEK_BASE_URL", server.base_url)
        # Allow the lazy SDK import/client construction to finish before the
        # local server exercises cancellation of an in-flight network request.
        monkeypatch.setattr(llm_client, "PROVIDER_TOTAL_DEADLINE_SECONDS", 3.0)
        adapter = DeepSeekAdapter(api_key="dummy-key")

        started = time.perf_counter()
        with pytest.raises(ProviderTimeoutError):
            adapter.verify_connection()
        elapsed = time.perf_counter() - started

        assert elapsed < 5.0
        assert server.accepted.wait(timeout=1)
        assert server.disconnected.wait(timeout=1)
    finally:
        server.close()


def _mk_consult_source(db, patient_id="pat_001", event_id="evt_fa5_t", artifact_id="art_fa5_t"):
    raw_content = {
        "segments": [{"index": 1, "speaker": "doctor", "text": "Your headache is worse."}]
    }
    evt = Event(
        event_id=event_id,
        patient_id=patient_id,
        clinic_id="clinic_001",
        event_type="doctor_consult",
        started_at=datetime(2026, 8, 26, 10, 0),
        ended_at=datetime(2026, 8, 26, 10, 30),
        created_at=datetime(2026, 8, 26, 10, 31),
    )
    art = Artifact(
        artifact_id=artifact_id,
        event_id=event_id,
        artifact_type="transcript",
        author_role="system",
        author_id=None,
        content=raw_content,
        created_at=datetime(2026, 8, 26, 10, 32),
        version=1,
        provenance_pointer=None,
    )
    db.add(evt)
    db.add(art)
    db.commit()
    return db.get(Event, event_id), db.get(Artifact, artifact_id)


def test_consult_timeout_falls_back_provider_timeout_and_preserves_raw(db_session):
    evt, art = _mk_consult_source(db_session)
    raw_content = art.content
    out = run_pipeline(
        db_session, evt, art, "ai_doctor_consult_summary", datetime(2026, 8, 26, 12, 0),
        _TimeoutClient(), "deepseek",
    )
    assert out.fallback_reason == "provider_timeout"
    assert out.degraded is True
    assert out.method == "deterministic_fallback"
    # Raw source content is untouched.
    assert db_session.get(Artifact, art.artifact_id).content == raw_content


def test_checkin_turn_and_summary_timeout_use_provider_timeout_fallback(
    patient_client, db_session, monkeypatch
):
    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "mock")
    monkeypatch.setattr("app.checkins.build_client", lambda *_a, **_k: _TimeoutClient())

    session_id = "checkin-timeout-001"
    patient_client.post(f"/api/patients/{fixture.PATIENT_ID}/check-ins", json={"session_id": session_id})
    sent = patient_client.post(
        f"/api/check-ins/{session_id}/messages",
        json={"message_id": "patient-timeout-msg-001", "intent": "answer", "text": "Headache is worse."},
    )
    assert sent.status_code == 200, sent.text

    sent_ai = next(
        message
        for message in sent.json()["messages"]
        if message["role"] == "ai"
        and message["response_to_message_id"] == "patient-timeout-msg-001"
    )
    assert sent_ai["fallback_reason"] == "provider_timeout"

    ai_message = db_session.scalar(
        select(PatientCheckInMessage).where(
            PatientCheckInMessage.session_id == session_id,
            PatientCheckInMessage.role == "ai",
            PatientCheckInMessage.response_to_message_id == "patient-timeout-msg-001",
        )
    )
    assert ai_message.generation_metadata["fallback_reason"] == "provider_timeout"
    assert ai_message.generation_metadata["method"] == "deterministic_fallback"
    assert ai_message.generation_metadata["degraded"] is True

    patient_client.post(
        f"/api/check-ins/{session_id}/messages",
        json={"message_id": "patient-timeout-end-001", "intent": "no_more", "text": ""},
    )
    submitted = patient_client.post(
        f"/api/check-ins/{session_id}/submit",
        json={"expected_status": "awaiting_confirmation"},
    )
    assert submitted.status_code == 200, submitted.text

    summary = db_session.scalar(
        select(Artifact).where(
            Artifact.event_id == submitted.json()["event_id"],
            Artifact.artifact_type == "ai_patient_session_summary",
        )
    )
    assert summary.generation_metadata["fallback_reason"] == "provider_timeout"
    assert summary.generation_metadata["method"] == "deterministic_fallback"
    assert summary.generation_metadata["degraded"] is True


def test_copilot_timeout_unavailable_without_answer(db_session):
    patient = db_session.get(Patient, fixture.PATIENT_ID)
    query = CopilotQuery(category="find_evidence", question="What changed?")
    resp = answer_query(db_session, patient, query, _TimeoutClient(), "deepseek", "usr_clinician_01")

    assert resp.status == "unavailable"
    assert resp.claims == []
    assert resp.draft is None
    assert resp.degraded is True


def test_device_key_verify_timeout_does_not_save(db_session, monkeypatch):
    import app.device_settings as ds

    def _timeout_verify(self):
        raise ProviderTimeoutError("simulated total deadline")

    monkeypatch.setattr(ds.DeepSeekAdapter, "verify_connection", _timeout_verify)
    vault = {}
    monkeypatch.setattr(ds, "store_secret", lambda deployment, ref, value: vault.__setitem__("key", value))

    with pytest.raises(ProviderTimeoutError):
        ds.store_device_deepseek_key(db_session, "synthetic-key-timeout-1234")
    assert "key" not in vault


def test_doctor_consult_timeout_retry_does_not_duplicate_raw(
    clinician_client, db_session, monkeypatch
):
    import app.api.sources as sources

    monkeypatch.setattr(sources, "build_client", lambda *_a, **_k: _TimeoutClient())
    body = {
        "consult_id": "consult-fa5-timeout-001",
        "ingestion_key": "ingest-fa5-timeout-001",
        "started_at": "2026-08-26T10:00:00",
        "ended_at": "2026-08-26T10:30:00",
        "content": {
            "segments": [
                {"index": 0, "speaker": "doctor", "text": "How has the headache changed?"},
                {"index": 1, "speaker": "patient", "text": "It is worse and near daily."},
            ]
        },
    }

    first = clinician_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/doctor-consults", json=body
    )
    assert first.status_code == 200, first.text
    assert first.json()["fallback_reason"] == "provider_timeout"
    assert first.json()["degraded"] is True
    assert first.json()["generation_method"] == "deterministic_fallback"
    assert first.json()["idempotent_replay"] is False

    event_id = first.json()["event"]["event_id"]
    assert db_session.get(Event, event_id) is not None

    second = clinician_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/doctor-consults", json=body
    )
    assert second.status_code == 200, second.text
    assert second.json()["idempotent_replay"] is True
    # Same stable rows: no duplicate Event, raw Transcript, or derived summary.
    assert second.json()["event"]["event_id"] == event_id
    assert second.json()["source_artifact_id"] == first.json()["source_artifact_id"]
    assert second.json()["ai_summary_artifact_id"] == first.json()["ai_summary_artifact_id"]
    assert len(db_session.scalars(select(Event).where(Event.event_id == event_id)).all()) == 1
    assert len(db_session.scalars(select(Artifact).where(Artifact.event_id == event_id)).all()) == 2
