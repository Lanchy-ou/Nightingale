from __future__ import annotations

from sqlalchemy import event as sqlalchemy_event, select

from app.models import (
    ImportanceFeedback,
    Artifact,
    Highlight,
    LearningSignal,
    RankingDecision,
    RankingRun,
)
from app.db import engine, migrate_fa1_schema
from app.shadow_learning import active_policy, shadow_adjustment
from seed import fixture


def test_hide_is_presentation_only_and_serving_stays_base_only(
    clinician_client, db_session
):
    before = db_session.query(ImportanceFeedback).count()
    response = clinician_client.post(
        "/api/highlights/hl_headache_worsening/status",
        json={"status": "rejected"},
    )
    assert response.status_code == 200, response.text
    db_session.expire_all()
    assert db_session.query(ImportanceFeedback).count() == before
    row = response.json()
    assert row["adaptive_adjustment"] == 0
    assert row["importance_score"] == row["base_importance_score"] + row["decay_adjustment"]


def test_projection_rebuild_records_top_five_and_unsurfaced_candidates(
    clinician_client, db_session
):
    hidden = clinician_client.post(
        "/api/highlights/hl_bp_elevated/status", json={"status": "rejected"}
    )
    assert hidden.status_code == 200, hidden.text
    db_session.expire_all()
    runs = db_session.scalars(
        select(RankingRun).where(
            RankingRun.patient_id == fixture.PATIENT_ID,
            RankingRun.viewer_role == "clinician",
        )
    ).all()
    assert runs
    latest = sorted(runs, key=lambda row: (row.evaluated_at, row.run_id))[-1]
    decisions = db_session.scalars(
        select(RankingDecision).where(RankingDecision.run_id == latest.run_id)
    ).all()
    assert sum(row.surfaced_base for row in decisions) == 5
    assert any(row.eligible and not row.surfaced_base for row in decisions)
    assert any(not row.eligible and row.exclusion_reason for row in decisions)
    assert all("text" not in (row.factor_snapshot or {}) for row in decisions)


def test_identical_projection_state_reuses_ranking_run(db_session):
    from datetime import datetime
    from app.glance_projection import rebuild_glance_projections

    as_of = datetime(2026, 9, 2, 12, 0)
    rebuild_glance_projections(db_session, fixture.PATIENT_ID, as_of=as_of)
    db_session.commit()
    first = db_session.query(RankingRun).count()
    rebuild_glance_projections(db_session, fixture.PATIENT_ID, as_of=as_of)
    db_session.commit()
    assert db_session.query(RankingRun).count() == first


def test_coverage_review_and_signal_roles(
    clinician_client, staff_client, admin_client, db_session
):
    coverage = clinician_client.get(
        f"/api/patients/{fixture.PATIENT_ID}/coverage-review?viewer_role=clinician"
    )
    assert coverage.status_code == 200, coverage.text
    body = coverage.json()
    assert body["serving_mode"] == "base_only"
    assert body["shadow_only"] is True
    assert body["eligible_unsurfaced"]
    decision_id = body["eligible_unsurfaced"][0]["decision_id"]

    staff_denied = staff_client.post(
        f"/api/ranking-decisions/{decision_id}/signals",
        json={
            "signal_type": "explicit_demotion",
            "reason_code": "duplicate_or_redundant",
            "confirmed": True,
        },
    )
    assert staff_denied.status_code == 403
    created = clinician_client.post(
        f"/api/ranking-decisions/{decision_id}/signals",
        json={
            "signal_type": "explicit_demotion",
            "reason_code": "duplicate_or_redundant",
            "confirmed": True,
        },
    )
    assert created.status_code == 200, created.text
    assert created.json()["signal_value"] == -1
    assert db_session.query(LearningSignal).count() == 1

    assert admin_client.get("/api/admin/learning/status").status_code == 200


def test_quality_feedback_never_becomes_shadow_demotion(
    staff_client, db_session
):
    coverage = staff_client.get(
        f"/api/patients/{fixture.PATIENT_ID}/coverage-review?viewer_role=staff"
    ).json()
    decision_id = coverage["eligible_unsurfaced"][0]["decision_id"]
    response = staff_client.post(
        f"/api/ranking-decisions/{decision_id}/signals",
        json={
            "signal_type": "quality_issue",
            "reason_code": "wrong_role_route",
            "confirmed": True,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["signal_value"] == 0
    assert response.json()["eligible_for_shadow"] is False


def test_changed_source_fails_closed_for_explicit_demotion(
    clinician_client, db_session
):
    coverage = clinician_client.get(
        f"/api/patients/{fixture.PATIENT_ID}/coverage-review?viewer_role=clinician"
    ).json()
    candidate = next(
        item for item in coverage["eligible_unsurfaced"]
        if item["source_binding_status"] == "current"
    )
    decision = db_session.get(RankingDecision, candidate["decision_id"])
    highlight = db_session.get(Highlight, decision.highlight_id)
    source = db_session.get(Artifact, highlight.source_artifact_id)
    source.version += 1
    db_session.commit()
    response = clinician_client.post(
        f"/api/ranking-decisions/{candidate['decision_id']}/signals",
        json={
            "signal_type": "explicit_demotion",
            "reason_code": "duplicate_or_redundant",
            "confirmed": True,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["eligible_for_shadow"] is False
    assert response.json()["ineligibility_reason"] == "source_binding_invalid"


def test_admin_replay_is_reproducible_and_enabled_serving_is_rejected(admin_client):
    first = admin_client.post("/api/admin/learning/replays", json={"run_ids": []})
    second = admin_client.post("/api/admin/learning/replays", json={"run_ids": []})
    assert first.status_code == second.status_code == 200
    assert first.json()["metrics"] == second.json()["metrics"]
    enabled = admin_client.post(
        "/api/admin/learning/policies/enabled/activate", json={}
    )
    assert enabled.status_code == 422


def test_protected_candidate_records_ineligible_shadow_signal(
    clinician_client, db_session
):
    coverage = clinician_client.get(
        f"/api/patients/{fixture.PATIENT_ID}/coverage-review?viewer_role=clinician"
    ).json()
    protected = next(
        item for item in coverage["base_top_five"]
        if item["highlight_id"] == "hl_bp_elevated"
    )
    response = clinician_client.post(
        f"/api/ranking-decisions/{protected['decision_id']}/signals",
        json={
            "signal_type": "explicit_demotion",
            "reason_code": "lower_than_other_active_work",
            "confirmed": True,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["eligible_for_shadow"] is False
    assert response.json()["ineligibility_reason"] == "negative_generalization_protected"


def test_freeze_ignores_later_signal_and_policy_rollback_is_shadow_only(
    clinician_client, admin_client, db_session
):
    frozen = admin_client.post(
        "/api/admin/learning/freeze",
        json={"expected_frozen": False, "frozen": True},
    )
    assert frozen.status_code == 200, frozen.text
    assert frozen.json()["frozen"] is True
    cutoff = frozen.json()["signal_cutoff_at"]

    coverage = clinician_client.get(
        f"/api/patients/{fixture.PATIENT_ID}/coverage-review?viewer_role=clinician"
    ).json()
    decision = coverage["eligible_unsurfaced"][0]
    signal = clinician_client.post(
        f"/api/ranking-decisions/{decision['decision_id']}/signals",
        json={
            "signal_type": "explicit_demotion",
            "reason_code": "duplicate_or_redundant",
            "confirmed": True,
        },
    )
    assert signal.status_code == 200, signal.text
    db_session.expire_all()
    policy = active_policy(db_session, fixture.CLINIC_ID)
    assert policy.signal_cutoff_at.isoformat() == cutoff
    assert shadow_adjustment(
        db_session,
        clinic_id=fixture.CLINIC_ID,
        feedback_key=decision["entity_type"] or "other",
        policy=policy,
    ) == 0

    rolled_back = admin_client.post(
        "/api/admin/learning/policies/no-adjustment-v1/activate", json={}
    )
    assert rolled_back.status_code == 200, rolled_back.text
    assert rolled_back.json()["active_policy"] == "no-adjustment-v1"
    assert rolled_back.json()["serving_mode"] == "base_only"
    replay = admin_client.post("/api/admin/learning/replays", json={"run_ids": []})
    assert replay.status_code == 200, replay.text
    assert replay.json()["metrics"]["rank_shift_count"] == 0


def test_glance_read_does_not_query_shadow_or_legacy_tables(clinician_client):
    statements: list[str] = []

    def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement.lower())

    sqlalchemy_event.listen(engine, "before_cursor_execute", capture)
    try:
        response = clinician_client.get(f"/api/patients/{fixture.PATIENT_ID}/glance")
    finally:
        sqlalchemy_event.remove(engine, "before_cursor_execute", capture)
    assert response.status_code == 200
    forbidden = (
        "ranking_runs",
        "ranking_decisions",
        "learning_signals",
        "learning_policy_versions",
        "learning_evaluations",
        "importance_feedback",
    )
    assert not any(any(table in statement for table in forbidden) for statement in statements)


def test_fa1_migration_is_idempotent_and_preserves_legacy_feedback(db_session):
    legacy_count = db_session.query(ImportanceFeedback).count()
    highlight = db_session.get(Highlight, "hl_headache_worsening")
    highlight.adaptive_adjustment = 2
    highlight.importance_score = highlight.base_importance_score + 2
    db_session.commit()
    migrate_fa1_schema(engine)
    migrate_fa1_schema(engine)
    db_session.expire_all()
    assert db_session.query(ImportanceFeedback).count() == legacy_count
    migrated = db_session.get(Highlight, "hl_headache_worsening")
    assert migrated.adaptive_adjustment == 0
    assert migrated.importance_score == migrated.base_importance_score + migrated.decay_adjustment


def test_coverage_review_rbac_and_scope_are_server_enforced(
    client, patient_client, admin_client, clinician_client
):
    url = f"/api/patients/{fixture.PATIENT_ID}/coverage-review?viewer_role=clinician"
    assert patient_client.get(url).status_code == 403
    assert admin_client.get(url).status_code == 403
    mismatch = clinician_client.get(
        f"/api/patients/{fixture.PATIENT_ID}/coverage-review?viewer_role=staff"
    )
    assert mismatch.status_code == 403
    cross = client.get(
        url,
        headers={"X-User-Id": fixture.USER_CLINICIAN_B_ID},
    )
    missing = client.get(
        "/api/patients/pat_missing/coverage-review?viewer_role=clinician",
        headers={"X-User-Id": fixture.USER_CLINICIAN_B_ID},
    )
    assert cross.status_code == missing.status_code == 404
    assert cross.json() == missing.json()
