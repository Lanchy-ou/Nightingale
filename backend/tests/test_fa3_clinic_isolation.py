from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event as sqlalchemy_event, select, text
from sqlalchemy.exc import IntegrityError

from app import authz
from app.clinic_scope import (
    load_artifact_with_event,
    load_event,
    load_highlight_with_event,
    load_patient,
    load_ranking_decision_with_run,
    load_task,
)
from app.db import Base, engine, install_clinic_isolation_schema
from app.glance_projection import rebuild_glance_projections
from app.main import app
from app.models import (
    Artifact,
    Event,
    Highlight,
    LearningSignal,
    RankingDecision,
    RankingRun,
    Task,
)
from app.role_context import RoleContext
from scripts.check_clinic_scope_bypass import (
    PRIVILEGED_SCOPE_ALLOWLIST,
    find_route_bypasses,
)
from seed import fixture
from tests.voice_api_helpers import create_payload


@pytest.mark.parametrize(
    "cross_path,missing_path",
    [
        (f"/api/patients/{fixture.PATIENT_ID}", "/api/patients/pat_missing"),
        (
            f"/api/events/{fixture.EVT_DOC_0821}/artifacts",
            "/api/events/evt_missing/artifacts",
        ),
        (
            "/api/highlights/hl_headache_worsening/provenance",
            "/api/highlights/hl_missing/provenance",
        ),
        (
            f"/api/tasks/{fixture.TASK_BLOOD_TEST}/provenance",
            "/api/tasks/tsk_missing/provenance",
        ),
        (
            f"/api/artifacts/{fixture.ART_DOC_NOTE}/versions",
            "/api/artifacts/art_missing/versions",
        ),
        (
            f"/api/events/{fixture.EVT_DOC_0821}/comments",
            "/api/events/evt_missing/comments",
        ),
        (
            f"/api/events/{fixture.EVT_DOC_0821}/audit",
            "/api/events/evt_missing/audit",
        ),
        (
            f"/api/patients/{fixture.PATIENT_ID}/tasks",
            "/api/patients/pat_missing/tasks",
        ),
        (
            f"/api/patients/{fixture.PATIENT_ID}/glance",
            "/api/patients/pat_missing/glance",
        ),
        (
            f"/api/patients/{fixture.PATIENT_ID}/coverage-review?viewer_role=clinician",
            "/api/patients/pat_missing/coverage-review?viewer_role=clinician",
        ),
    ],
)
def test_scope_fault_injection_keeps_cross_clinic_reads_indistinguishable(
    client, monkeypatch, cross_path: str, missing_path: str
):
    monkeypatch.setattr(authz, "authorize_scope", lambda *_args, **_kwargs: None)
    headers = {"X-User-Id": fixture.USER_CLINICIAN_B_ID}

    cross = client.get(cross_path, headers=headers)
    missing = client.get(missing_path, headers=headers)

    assert cross.status_code == missing.status_code == 404
    assert cross.json() == missing.json()


def test_event_patient_clinic_mismatch_is_rejected(db_session):
    db_session.add(
        Event(
            event_id="evt_fa3_bad_scope",
            patient_id=fixture.PATIENT_ID,
            clinic_id=fixture.CLINIC_B_ID,
            event_type="clinician_review",
            started_at=datetime(2026, 9, 2, 9, 0),
            ended_at=None,
            created_at=datetime(2026, 9, 2, 9, 0),
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_task_event_patient_clinic_mismatch_is_rejected(db_session):
    db_session.add(
        Task(
            task_id="tsk_fa3_bad_scope",
            patient_id=fixture.PATIENT_ID,
            clinic_id=fixture.CLINIC_B_ID,
            event_id=fixture.EVT_DOC_0821,
            source_artifact_id=None,
            source_span=None,
            title="Invalid tenant relation",
            description="Synthetic ownership probe",
            assigned_role="clinician",
            assigned_user_id=fixture.USER_CLINICIAN_B_ID,
            patient_visible=False,
            status="open",
            due_at=None,
            created_by=fixture.USER_CLINICIAN_B_ID,
            created_at=datetime(2026, 9, 2, 9, 0),
            updated_at=datetime(2026, 9, 2, 9, 0),
            reported_done_at=None,
            completed_by=None,
            completed_at=None,
            cancelled_by=None,
            cancelled_at=None,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_ranking_run_patient_clinic_mismatch_is_rejected(db_session):
    db_session.add(
        RankingRun(
            run_id="rrn_fa3_bad_scope",
            clinic_id=fixture.CLINIC_B_ID,
            patient_id=fixture.PATIENT_ID,
            viewer_role="clinician",
            rule_version="attention-v1",
            policy_version="legacy-e2-v1",
            top_k=5,
            state_fingerprint="f" * 64,
            evaluated_at=datetime(2026, 9, 2, 9, 0),
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_patient_bound_route_ids_cannot_use_global_db_get():
    assert find_route_bypasses() == []


def test_privileged_scope_allowlist_is_small_and_explicit():
    assert PRIVILEGED_SCOPE_ALLOWLIST == {
        "app.db": {
            "migrate_phase_e_schema",
            "migrate_fa1_schema",
            "install_clinic_isolation_schema",
        },
        "app.patient_review": {"materialize_due_escalations"},
        "seed.seed": {"create_schema", "seed"},
        "seed.highlights": {"generate_highlights"},
    }


def test_fault_injected_cross_clinic_writes_are_404_and_do_not_mutate(
    client, db_session, monkeypatch
):
    decision = db_session.scalar(
        select(RankingDecision)
        .join(RankingRun, RankingRun.run_id == RankingDecision.run_id)
        .where(RankingRun.clinic_id == fixture.CLINIC_ID)
    )
    highlight = db_session.get(Highlight, "hl_bp_elevated")
    task = db_session.get(Task, fixture.TASK_BLOOD_TEST)
    old_highlight_status = highlight.status
    old_task_status = task.status
    old_signal_count = db_session.query(LearningSignal).count()
    monkeypatch.setattr(authz, "authorize_scope", lambda *_args, **_kwargs: None)
    headers = {"X-User-Id": fixture.USER_CLINICIAN_B_ID}

    responses = [
        client.post(
            "/api/highlights/hl_bp_elevated/status",
            headers=headers,
            json={"status": "accepted"},
        ),
        client.post(
            f"/api/tasks/{fixture.TASK_BLOOD_TEST}/transition",
            headers=headers,
            json={"expected_status": old_task_status, "status": "in_progress"},
        ),
        client.patch(
            f"/api/artifacts/{fixture.ART_DOC_NOTE}",
            headers=headers,
            json={"expected_version": 1, "content": {"plan": "cross-clinic"}},
        ),
        client.post(
            f"/api/ranking-decisions/{decision.decision_id}/signals",
            headers=headers,
            json={
                "signal_type": "explicit_demotion",
                "reason_code": "duplicate_or_redundant",
                "confirmed": True,
            },
        ),
    ]

    assert [response.status_code for response in responses] == [404, 404, 404, 404]
    db_session.expire_all()
    assert db_session.get(Highlight, "hl_bp_elevated").status == old_highlight_status
    assert db_session.get(Task, fixture.TASK_BLOOD_TEST).status == old_task_status
    assert db_session.query(LearningSignal).count() == old_signal_count


def test_fault_injected_checkin_and_voice_direct_ids_stay_scoped(
    patient_client, clinician_client, client, monkeypatch
):
    checkin_id = "fa3-scope-checkin"
    assert patient_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/check-ins",
        json={"session_id": checkin_id},
    ).status_code == 200
    voice = clinician_client.post(
        "/api/voice/captures",
        json=create_payload(idempotency_key="fa3-scope-voice"),
    )
    assert voice.status_code == 201, voice.text
    monkeypatch.setattr(authz, "authorize_scope", lambda *_args, **_kwargs: None)
    headers = {"X-User-Id": fixture.USER_CLINICIAN_B_ID}

    cross_checkin = client.get(f"/api/check-ins/{checkin_id}", headers=headers)
    missing_checkin = client.get("/api/check-ins/checkin_missing", headers=headers)
    cross_voice = client.get(
        f"/api/voice/captures/{voice.json()['capture_id']}", headers=headers
    )
    missing_voice = client.get("/api/voice/captures/vc_missing", headers=headers)

    assert cross_checkin.status_code == missing_checkin.status_code == 404
    assert cross_checkin.json() == missing_checkin.json()
    assert cross_voice.status_code == missing_voice.status_code == 404
    assert cross_voice.json() == missing_voice.json()


def test_cross_entity_highlight_decision_and_signal_links_are_rejected(db_session):
    other_event = db_session.scalar(
        select(Event).where(Event.clinic_id == fixture.CLINIC_B_ID)
    )
    highlight = db_session.get(Highlight, "hl_headache_worsening")
    highlight.event_id = other_event.event_id
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()

    clinic_a_decision = db_session.scalar(
        select(RankingDecision)
        .join(RankingRun, RankingRun.run_id == RankingDecision.run_id)
        .where(RankingRun.clinic_id == fixture.CLINIC_ID)
    )
    clinic_b_highlight = db_session.scalar(
        select(Highlight)
        .join(Event, Event.event_id == Highlight.event_id)
        .where(Event.clinic_id == fixture.CLINIC_B_ID)
    )
    clinic_a_decision.highlight_id = clinic_b_highlight.highlight_id
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()

    clinic_a_decision = db_session.scalar(
        select(RankingDecision)
        .join(RankingRun, RankingRun.run_id == RankingDecision.run_id)
        .where(RankingRun.clinic_id == fixture.CLINIC_ID)
    )
    db_session.add(
        LearningSignal(
            signal_id="lsg_fa3_bad_scope",
            decision_id=clinic_a_decision.decision_id,
            clinic_id=fixture.CLINIC_ID,
            actor_id=fixture.USER_CLINICIAN_B_ID,
            actor_role="clinician",
            signal_type="quality_issue",
            reason_code="source_mismatch",
            feedback_key="other",
            signal_value=0,
            eligible_for_shadow=False,
            ineligibility_reason="quality_signal_not_ranking_feedback",
            independence_key="fa3",
            policy_version="legacy-e2-v1",
            supersedes_signal_id=None,
            created_at=datetime(2026, 9, 2, 9, 0),
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_scoped_loaders_resolve_each_direct_object_in_one_query(db_session):
    ctx = RoleContext(
        fixture.USER_CLINICIAN_ID,
        "clinician",
        fixture.CLINIC_ID,
        None,
        True,
    )
    decision = db_session.scalar(
        select(RankingDecision)
        .join(RankingRun, RankingRun.run_id == RankingDecision.run_id)
        .where(RankingRun.clinic_id == fixture.CLINIC_ID)
    )
    statements: list[str] = []

    def capture(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    sqlalchemy_event.listen(engine, "before_cursor_execute", capture)
    try:
        assert load_patient(db_session, ctx, fixture.PATIENT_ID) is not None
        assert load_event(db_session, ctx, fixture.EVT_DOC_0821) is not None
        assert load_artifact_with_event(db_session, ctx, fixture.ART_DOC_NOTE) is not None
        assert load_highlight_with_event(db_session, ctx, "hl_headache_worsening") is not None
        assert load_task(db_session, ctx, fixture.TASK_BLOOD_TEST) is not None
        assert load_ranking_decision_with_run(db_session, ctx, decision.decision_id) is not None
    finally:
        sqlalchemy_event.remove(engine, "before_cursor_execute", capture)

    assert len(statements) == 6


def test_foreign_keys_and_scope_indexes_are_active(db_session):
    assert db_session.execute(text("PRAGMA foreign_keys")).scalar() == 1
    plan = db_session.execute(
        text(
            "EXPLAIN QUERY PLAN SELECT projection_id FROM glance_projections "
            "WHERE clinic_id=:clinic AND patient_id=:patient "
            "AND viewer_role='clinician' AND eligible=1 "
            "ORDER BY priority_band, final_score DESC LIMIT 5"
        ),
        {"clinic": fixture.CLINIC_ID, "patient": fixture.PATIENT_ID},
    ).all()
    assert "ix_glance_scope_read" in " ".join(str(row) for row in plan)


def test_a1_ranking_snapshot_batch_does_not_commit_inside_service(
    db_session, monkeypatch
):
    def unexpected_commit():
        raise AssertionError("A1 batch service committed outside its caller transaction")

    monkeypatch.setattr(db_session, "commit", unexpected_commit)
    rebuild_glance_projections(
        db_session,
        fixture.PATIENT_ID,
        as_of=datetime(2026, 9, 2, 12, 0),
    )
    db_session.rollback()


def test_dual_database_sessions_remain_isolated_when_scope_function_is_noop(
    monkeypatch,
):
    monkeypatch.delenv("NANTINGALE_DEMO_AUTH", raising=False)
    monkeypatch.setattr(authz, "authorize_scope", lambda *_args, **_kwargs: None)
    with TestClient(app) as clinic_a, TestClient(app) as clinic_b:
        login_a = clinic_a.post(
            "/api/auth/login",
            json={
                "email": fixture.DEMO_EMAILS[fixture.USER_CLINICIAN_ID],
                "password": fixture.DEMO_PASSWORD,
            },
        )
        login_b = clinic_b.post(
            "/api/auth/login",
            json={
                "email": fixture.DEMO_EMAILS[fixture.USER_CLINICIAN_B_ID],
                "password": fixture.DEMO_PASSWORD,
            },
        )
        assert login_a.status_code == login_b.status_code == 200
        assert clinic_a.get("/api/auth/session").json()["user_id"] == fixture.USER_CLINICIAN_ID
        assert clinic_b.get("/api/auth/session").json()["user_id"] == fixture.USER_CLINICIAN_B_ID

        assert clinic_a.get(f"/api/patients/{fixture.PATIENT_ID}").status_code == 200
        assert clinic_b.get(f"/api/patients/{fixture.PATIENT_OTHER_ID}").status_code == 200

        a_cross = clinic_a.get(f"/api/patients/{fixture.PATIENT_OTHER_ID}")
        a_missing = clinic_a.get("/api/patients/pat_missing")
        b_cross = clinic_b.get(f"/api/patients/{fixture.PATIENT_ID}")
        b_missing = clinic_b.get("/api/patients/pat_missing")
        assert a_cross.status_code == a_missing.status_code == 404
        assert b_cross.status_code == b_missing.status_code == 404
        assert a_cross.json() == a_missing.json()
        assert b_cross.json() == b_missing.json()


def test_migration_preflight_refuses_legacy_ownership_mismatch():
    legacy = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(legacy)
    with legacy.begin() as connection:
        connection.execute(
            text("INSERT INTO clinics (clinic_id, name) VALUES ('a', 'A'), ('b', 'B')")
        )
        connection.execute(
            text("INSERT INTO patients (patient_id, clinic_id, name) VALUES ('p', 'a', 'P')")
        )
        connection.execute(
            text(
                "INSERT INTO events "
                "(event_id, patient_id, clinic_id, event_type, started_at, created_at) "
                "VALUES ('e', 'p', 'b', 'clinician_review', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
    with pytest.raises(RuntimeError, match="event_scope=1"):
        install_clinic_isolation_schema(legacy)
    legacy.dispose()
