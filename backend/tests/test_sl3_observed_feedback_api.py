from __future__ import annotations


def test_admin_status_exposes_read_only_observed_feedback_bridge(admin_client):
    response = admin_client.get("/api/admin/learning/status")
    assert response.status_code == 200
    bridge = response.json()["observed_feedback"]
    assert bridge["automatic_feature_extraction"] is True
    assert bridge["automatic_training"] is False
    assert bridge["serving_mode"] == "base_only"
    assert bridge["real_clinician_validation"] == "NOT_RUN"
    assert set(bridge["roles"]) == {"staff", "clinician"}


def test_non_admin_cannot_inspect_observed_feedback_bridge(clinician_client):
    response = clinician_client.get("/api/admin/learning/status")
    assert response.status_code == 403
