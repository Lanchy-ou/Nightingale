"""F_A4 operational-log allowlist contract tests.

Operational logs are the process-stderr structured records. These tests lock:
- unhandled errors log the matched route TEMPLATE, never the raw path/id;
- the request id is server-generated, never a client header value;
- unknown fields/events are dropped;
- **invalid field VALUES are dropped** (a short patient message must not pass);
- the scrubber removes PHI-shaped substrings that survive value validation;
- emit_log never raises, even for unhashable/poisoned inputs;
- all four existing log events are allowlisted and structured.
"""
from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import operational_logging
from app.operational_logging import EVENT_ALLOWLIST, _scrub, emit_log

SENTINEL_MSG = "FA4_SENTINEL_EXCEPTION_MESSAGE"
SENTINEL_PATIENT_ID = "pat_fa4_sentinel_9f3a"
SENTINEL_TOKEN = "FA4_SENTINEL_TOKEN_MUST_NEVER_APPEAR_IN_LOGS_0123456789"
PROBE_PATH = "/api/patients/{patient_id}/__fa4_probe"


def _raise_sensitive_error(patient_id: str):
    raise RuntimeError(SENTINEL_MSG)


if not any(getattr(route, "path", None) == PROBE_PATH for route in app.routes):
    app.add_api_route(PROBE_PATH, _raise_sensitive_error, methods=["GET"], include_in_schema=False)


def _emitted_records(caplog) -> list[dict]:
    records = []
    for record in caplog.records:
        message = record.getMessage()
        try:
            records.append(json.loads(message))
        except (json.JSONDecodeError, TypeError):
            continue
    return records


def test_unhandled_error_logs_route_template_not_raw_path(caplog):
    caplog.set_level(logging.ERROR)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(f"/api/patients/{SENTINEL_PATIENT_ID}/__fa4_probe")

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "internal_error", "message": "Internal server error"}
    }
    # Exception text, the raw path value and the raw path segment are all absent.
    assert SENTINEL_MSG not in caplog.text
    assert SENTINEL_PATIENT_ID not in caplog.text
    assert f"/api/patients/{SENTINEL_PATIENT_ID}/" not in caplog.text

    records = _emitted_records(caplog)
    unhandled = [r for r in records if r.get("event") == "unhandled_error"]
    assert len(unhandled) == 1
    assert unhandled[0]["route_template"] == PROBE_PATH
    assert unhandled[0]["error_type"] == "RuntimeError"
    assert unhandled[0]["error_code"] == "internal_error"
    assert unhandled[0]["status_code"] == 500
    assert "{patient_id}" in unhandled[0]["route_template"]


def test_request_id_is_server_generated_not_client_header(caplog):
    caplog.set_level(logging.ERROR)
    client_chosen = "X-REQ-CLIENT-CHOSEN-ID"
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            f"/api/patients/{SENTINEL_PATIENT_ID}/__fa4_probe",
            headers={"X-Request-ID": client_chosen},
        )

    assert response.status_code == 500
    assert client_chosen not in caplog.text
    unhandled = [r for r in _emitted_records(caplog) if r.get("event") == "unhandled_error"]
    assert len(unhandled) == 1
    request_id = unhandled[0]["request_id"]
    assert request_id.startswith("req_")
    assert len(request_id) == len("req_") + 16
    assert request_id != client_chosen


def test_emit_log_drops_unknown_fields_and_events(caplog):
    caplog.set_level(logging.INFO)
    emit_log(
        "unhandled_error",
        unknown_secret_field=SENTINEL_TOKEN,
        error_type="RuntimeError",
        level="info",
    )
    records = _emitted_records(caplog)
    assert records[-1]["event"] == "unhandled_error"
    assert "unknown_secret_field" not in records[-1]
    assert SENTINEL_TOKEN not in caplog.text

    emit_log("not_a_real_event", level="info")
    assert _emitted_records(caplog)[-1]["event"] == "invalid_event"


def test_emit_log_drops_invalid_field_values(caplog):
    """A short patient-message sentinel must not pass as any allowed field."""
    caplog.set_level(logging.INFO)
    emit_log(
        "unhandled_error",
        error_type="SENTINEL_SHORT_PATIENT_MESSAGE",
        model="SENTINEL_SHORT_PATIENT_MESSAGE",
        route_template="SENTINEL_SHORT_PATIENT_MESSAGE",
        error_code="SENTINEL_SHORT_PATIENT_MESSAGE",
        method="SENTINEL_SHORT_PATIENT_MESSAGE",
        request_id="SENTINEL_SHORT_PATIENT_MESSAGE",
        status_code="SENTINEL_SHORT_PATIENT_MESSAGE",
        input_tokens="SENTINEL_SHORT_PATIENT_MESSAGE",
        level="info",
    )
    record = _emitted_records(caplog)[-1]
    assert record["event"] == "unhandled_error"
    # Every invalid value was dropped, leaving no free-text in the record.
    for key in (
        "error_type",
        "model",
        "route_template",
        "error_code",
        "method",
        "request_id",
        "status_code",
        "input_tokens",
    ):
        assert key not in record
    assert "SENTINEL_SHORT_PATIENT_MESSAGE" not in caplog.text


def test_emit_log_rejects_raw_path_shaped_as_route_template(caplog):
    caplog.set_level(logging.INFO)
    raw_path = "/api/patients/pat_secret_123/events/evt_secret_456"

    emit_log("unhandled_error", route_template=raw_path, level="info")

    record = _emitted_records(caplog)[-1]
    assert "route_template" not in record
    assert raw_path not in caplog.text


def test_scrubber_redacts_phi_patterns():
    assert "660101" not in _scrub("ic 660101-01-6001 end")
    assert "6012-345-6789" not in _scrub("tel +6012-345-6789")
    assert "[NAME_1]" not in _scrub("name [NAME_1]")
    assert SENTINEL_TOKEN not in _scrub(SENTINEL_TOKEN)
    assert _scrub(5) == 5
    assert _scrub(True) is True


def test_emit_log_never_raises_on_poisoned_inputs(caplog):
    caplog.set_level(logging.INFO)
    # Unhashable event, non-serializable field value, and a bad level: none may
    # escape (emit_log sits on the unhandled-exception path).
    emit_log(["unhashable", "event"], level="info")
    emit_log("provider_error", error_type=object(), level="info")
    emit_log("provider_error", error_type="RuntimeError", level="not_a_level")
    records = _emitted_records(caplog)
    assert records[-3]["event"] == "invalid_event"
    assert records[-1]["event"] == "provider_error"


def test_uvicorn_filter_suppresses_only_marked_handled_exception():
    operational_logging.suppress_server_duplicate_tracebacks()
    uvicorn_logger = logging.getLogger("uvicorn.error")
    filters = [
        item
        for item in uvicorn_logger.filters
        if item.__class__.__name__ == "_SuppressHandledUvicornTraceback"
    ]
    assert len(filters) == 1

    unmarked = RuntimeError("UNHANDLED_OUTSIDE_APP_SENTINEL")
    unmarked_record = logging.LogRecord(
        "uvicorn.error",
        logging.ERROR,
        __file__,
        1,
        "Exception in ASGI application\n",
        (),
        (RuntimeError, unmarked, None),
    )
    assert all(item.filter(unmarked_record) for item in filters)

    handled = RuntimeError("HANDLED_SENTINEL")
    operational_logging.mark_exception_sanitized(handled)
    handled_record = logging.LogRecord(
        "uvicorn.error",
        logging.ERROR,
        __file__,
        1,
        "Exception in ASGI application\n",
        (),
        (RuntimeError, handled, None),
    )
    assert not all(item.filter(handled_record) for item in filters)


def test_all_four_existing_events_are_allowlisted():
    for event in ("unhandled_error", "sweep_error", "provider_error", "provider_usage"):
        assert event in EVENT_ALLOWLIST


def test_provider_failure_never_logs_payload_or_source(caplog, db_session):
    from datetime import datetime

    from app.ai_pipeline import run_pipeline
    from app.models import Artifact, Event

    sentinel_payload = "SENTINEL_PROVIDER_PAYLOAD_SECRET_7D2C"
    sentinel_patient = "SENTINEL_PATIENT_MESSAGE_I_FEEL_WORSE_TODAY"
    evt = Event(
        event_id="evt_fa4_pp",
        patient_id="pat_001",
        clinic_id="clinic_001",
        event_type="doctor_consult",
        started_at=datetime(2026, 8, 26, 10, 0),
        ended_at=datetime(2026, 8, 26, 10, 30),
        created_at=datetime(2026, 8, 26, 10, 31),
    )
    art = Artifact(
        artifact_id="art_fa4_pp",
        event_id="evt_fa4_pp",
        artifact_type="transcript",
        author_role="system",
        author_id=None,
        content={
            "segments": [
                {"index": 1, "speaker": "doctor", "text": sentinel_patient}
            ]
        },
        created_at=datetime(2026, 8, 26, 10, 32),
        version=1,
        provenance_pointer=None,
    )
    db_session.add(evt)
    db_session.add(art)
    db_session.commit()

    class _UnexpectedFailingClient:
        def summarize(self, redacted, flow_type):
            raise TimeoutError(sentinel_payload)

    caplog.set_level(logging.WARNING)
    out = run_pipeline(
        db_session,
        evt,
        art,
        "ai_doctor_consult_summary",
        datetime(2026, 8, 26, 12, 0),
        _UnexpectedFailingClient(),
        "deepseek",
    )
    assert out.fallback_reason == "provider_error"
    # Neither the exception text (payload) nor the source text reached the log.
    assert sentinel_payload not in caplog.text
    assert sentinel_patient not in caplog.text


@pytest.mark.parametrize(
    "event,fields",
    [
        ("sweep_error", {"error_type": "ValueError"}),
        ("provider_error", {"error_type": "TimeoutError"}),
        ("provider_usage", {"model": "deepseek-v4-flash", "input_tokens": 12, "output_tokens": 3}),
    ],
)
def test_structured_events_are_valid_json(caplog, event, fields):
    caplog.set_level(logging.INFO)
    emit_log(event, level="info", **fields)
    record = _emitted_records(caplog)[-1]
    assert record["event"] == event
    for key, value in fields.items():
        assert record[key] == value
