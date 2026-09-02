from __future__ import annotations

from sqlalchemy import event as sqlalchemy_event

from app.db import engine
from seed import fixture


def test_formal_glance_never_queries_or_loads_sl2_training_state(clinician_client):
    statements: list[str] = []

    def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement.lower())

    sqlalchemy_event.listen(engine, "before_cursor_execute", capture)
    try:
        response = clinician_client.get(f"/api/patients/{fixture.PATIENT_ID}/glance")
    finally:
        sqlalchemy_event.remove(engine, "before_cursor_execute", capture)
    assert response.status_code == 200
    assert all(row["adaptive_adjustment"] == 0 for row in response.json()["highlights"])
    assert not any("learning_evaluations" in statement for statement in statements)


def test_sl2_policy_activation_remains_shadow_only(admin_client, clinician_client):
    before = clinician_client.get(f"/api/patients/{fixture.PATIENT_ID}/glance").json()
    activated = admin_client.post(
        "/api/admin/learning/policies/sl2-pairwise-linear-v1/activate", json={}
    )
    assert activated.status_code == 200, activated.text
    assert activated.json()["serving_mode"] == "base_only"
    evidence = activated.json()["sl2_evidence"]
    assert evidence["evaluation"]["all_thresholds_pass"] is True
    assert evidence["artifacts"]["staff"]["valid"] is True
    assert evidence["artifacts"]["clinician"]["valid"] is True
    after = clinician_client.get(f"/api/patients/{fixture.PATIENT_ID}/glance").json()
    assert [row["highlight_id"] for row in before["highlights"]] == [
        row["highlight_id"] for row in after["highlights"]
    ]

    coverage = clinician_client.get(
        f"/api/patients/{fixture.PATIENT_ID}/coverage-review?viewer_role=clinician"
    )
    assert coverage.status_code == 200, coverage.text
    payload = coverage.json()
    assert payload["serving_mode"] == "base_only"
    assert payload["shadow_simulation_only"] is True
    assert payload["run_policy_version"] == "sl2-pairwise-linear-v1"
    eligible = payload["base_top_five"] + payload["eligible_unsurfaced"]
    assert any(row["sl2_model_score"] is not None for row in eligible)
    assert all(row["sl2_model_score"] is None for row in payload["excluded"])
    assert all(row["shadow_rank"] is None for row in payload["excluded"])

    replay = admin_client.post("/api/admin/learning/replays", json={"run_ids": []})
    assert replay.status_code == 200, replay.text
    assert replay.json()["metrics"]["sl2_evidence"]["evaluation"][
        "all_thresholds_pass"
    ] is True

    rolled_back = admin_client.post(
        "/api/admin/learning/policies/no-adjustment-v1/activate", json={}
    )
    assert rolled_back.status_code == 200, rolled_back.text
    assert rolled_back.json()["active_policy"] == "no-adjustment-v1"
    assert rolled_back.json()["serving_mode"] == "base_only"
