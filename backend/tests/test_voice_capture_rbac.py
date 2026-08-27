"""Server identity, not page/body claims, decides voice capture authority."""

import pytest

from seed import fixture
from tests.voice_api_helpers import create_payload


@pytest.mark.parametrize(
    ("user_id", "mode", "expected"),
    [
        (fixture.USER_CLINICIAN_ID, "doctor_consult", 201),
        (fixture.USER_STAFF_ID, "nurse_consult", 201),
        (fixture.USER_PATIENT_ID, "patient_session", 201),
        (fixture.USER_CLINICIAN_ID, "nurse_consult", 403),
        (fixture.USER_STAFF_ID, "doctor_consult", 403),
        (fixture.USER_PATIENT_ID, "doctor_consult", 403),
        (fixture.USER_ADMIN_ID, "doctor_consult", 403),
    ],
)
def test_role_to_capture_mode_matrix(client, user_id, mode, expected):
    response = client.post(
        "/api/voice/captures",
        headers={"X-User-Id": user_id},
        json=create_payload(capture_mode=mode, idempotency_key=f"voice-{user_id}-{mode}"),
    )
    assert response.status_code == expected


def test_patient_can_capture_only_own_record(client):
    response = client.post(
        "/api/voice/captures",
        headers={"X-User-Id": fixture.USER_PATIENT_ID},
        json=create_payload(
            capture_mode="patient_session",
            patient_id=fixture.PATIENT_B_ID,
        ),
    )
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Resource not found"


def test_cross_clinic_and_missing_patient_are_indistinguishable(client):
    cross = client.post(
        "/api/voice/captures",
        headers={"X-User-Id": fixture.USER_CLINICIAN_B_ID},
        json=create_payload(),
    )
    missing = client.post(
        "/api/voice/captures",
        headers={"X-User-Id": fixture.USER_CLINICIAN_B_ID},
        json=create_payload(patient_id="missing-patient", idempotency_key="missing"),
    )
    assert cross.status_code == missing.status_code == 404
    assert cross.json() == missing.json()


def test_body_cannot_choose_actor_role_author_or_clinic(clinician_client):
    payload = create_payload()
    payload.update(
        {
            "actor_role": "admin",
            "author_id": fixture.USER_ADMIN_ID,
            "clinic_id": fixture.CLINIC_B_ID,
        }
    )
    response = clinician_client.post("/api/voice/captures", json=payload)
    assert response.status_code == 422


def test_anonymous_capture_is_401(client):
    assert client.post("/api/voice/captures", json=create_payload()).status_code == 401


def test_same_clinic_other_role_cannot_read_or_download_capture(
    clinician_client, client
):
    capture_id = clinician_client.post(
        "/api/voice/captures", json=create_payload(idempotency_key="owner-only")
    ).json()["capture_id"]

    for suffix in ("", "/audio"):
        staff = client.get(
            f"/api/voice/captures/{capture_id}{suffix}",
            headers={"X-User-Id": fixture.USER_STAFF_ID},
        )
        patient = client.get(
            f"/api/voice/captures/{capture_id}{suffix}",
            headers={"X-User-Id": fixture.USER_PATIENT_ID},
        )
        assert staff.status_code == patient.status_code == 404
