"""E1 hard gate: clinic-scoped Admin identity/access oversight."""
from __future__ import annotations

from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select

from app.models import AuditLog, AuthSession, UserCredential
from seed import fixture


def _add_active_session(db, user_id: str, suffix: str) -> str:
    now = datetime.now()
    session_id = f"ses_admin_test_{suffix}"
    db.add(
        AuthSession(
            session_id=session_id,
            user_id=user_id,
            token_hash=f"{'a' * 48}{suffix:0>16}"[-64:],
            created_at=now,
            expires_at=now + timedelta(hours=2),
            revoked_at=None,
            last_seen_at=now,
        )
    )
    db.commit()
    return session_id


def test_admin_lists_only_clinic_users_with_sanitized_account_metadata(
    admin_client, db_session
):
    _add_active_session(db_session, fixture.USER_STAFF_ID, "staff")
    response = admin_client.get("/api/admin/users")
    assert response.status_code == 200, response.text
    rows = response.json()
    assert {row["user_id"] for row in rows} == {
        fixture.USER_PATIENT_ID,
        fixture.USER_STAFF_ID,
        fixture.USER_CLINICIAN_ID,
        fixture.USER_ADMIN_ID,
        fixture.USER_PATIENT_B_ID,
    }
    assert fixture.USER_CLINICIAN_B_ID not in {row["user_id"] for row in rows}
    assert all(
        set(row)
        == {
            "user_id",
            "display_name",
            "email",
            "role",
            "professional_title",
            "patient_id",
            "account_status",
            "disabled_at",
            "active_session_count",
            "last_seen_at",
        }
        for row in rows
    )
    staff = next(row for row in rows if row["user_id"] == fixture.USER_STAFF_ID)
    assert staff["professional_title"] == "Registered Nurse"
    assert staff["active_session_count"] == 1

    serialized = str(rows).lower()
    assert "password_hash" not in serialized
    assert "token_hash" not in serialized
    assert "raw_conversation" not in serialized
    assert "clinical" not in serialized


@pytest.mark.parametrize(
    "user_id",
    [fixture.USER_STAFF_ID, fixture.USER_CLINICIAN_ID, fixture.USER_PATIENT_ID],
)
def test_non_admin_cannot_use_oversight_api(client, user_id):
    response = client.get(
        "/api/admin/users", headers={"X-User-Id": user_id}
    )
    assert response.status_code == 403


def test_cross_clinic_user_is_indistinguishable_from_missing(admin_client):
    cross = admin_client.patch(
        f"/api/admin/users/{fixture.USER_CLINICIAN_B_ID}/status",
        json={"expected_status": "active", "status": "disabled"},
    )
    missing = admin_client.patch(
        "/api/admin/users/usr_missing/status",
        json={"expected_status": "active", "status": "disabled"},
    )
    assert cross.status_code == missing.status_code == 404
    assert cross.json() == missing.json()


def test_disable_account_revokes_sessions_and_is_audited_with_cas(
    admin_client, db_session
):
    session_id = _add_active_session(db_session, fixture.USER_CLINICIAN_ID, "doctor")
    response = admin_client.patch(
        f"/api/admin/users/{fixture.USER_CLINICIAN_ID}/status",
        json={"expected_status": "active", "status": "disabled"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["account_status"] == "disabled"
    assert response.json()["active_session_count"] == 0
    db_session.expire_all()
    assert db_session.get(UserCredential, fixture.USER_CLINICIAN_ID).disabled_at is not None
    assert db_session.get(AuthSession, session_id).revoked_at is not None

    actions = db_session.scalars(
        select(AuditLog.action).where(
            AuditLog.target_id.in_((fixture.USER_CLINICIAN_ID, session_id))
        )
    ).all()
    assert "account_disabled" in actions
    assert "session_revoked" in actions

    stale = admin_client.patch(
        f"/api/admin/users/{fixture.USER_CLINICIAN_ID}/status",
        json={"expected_status": "active", "status": "disabled"},
    )
    assert stale.status_code == 409

    reactivated = admin_client.patch(
        f"/api/admin/users/{fixture.USER_CLINICIAN_ID}/status",
        json={"expected_status": "disabled", "status": "active"},
    )
    assert reactivated.status_code == 200
    assert reactivated.json()["account_status"] == "active"


def test_concurrent_account_status_updates_have_one_winner(client):
    def disable():
        return client.patch(
            f"/api/admin/users/{fixture.USER_CLINICIAN_ID}/status",
            headers={"X-User-Id": fixture.USER_ADMIN_ID},
            json={"expected_status": "active", "status": "disabled"},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(disable)
        second = pool.submit(disable)
        statuses = sorted((first.result().status_code, second.result().status_code))
    assert statuses == [200, 409]


def test_admin_cannot_disable_self_or_last_active_admin(admin_client):
    response = admin_client.patch(
        f"/api/admin/users/{fixture.USER_ADMIN_ID}/status",
        json={"expected_status": "active", "status": "disabled"},
    )
    assert response.status_code == 403


def test_revoke_sessions_uses_expected_active_count(admin_client, db_session):
    first = _add_active_session(db_session, fixture.USER_STAFF_ID, "staff-a")
    second = _add_active_session(db_session, fixture.USER_STAFF_ID, "staff-b")
    stale = admin_client.post(
        f"/api/admin/users/{fixture.USER_STAFF_ID}/revoke-sessions",
        json={"expected_active_session_count": 1},
    )
    assert stale.status_code == 409

    response = admin_client.post(
        f"/api/admin/users/{fixture.USER_STAFF_ID}/revoke-sessions",
        json={"expected_active_session_count": 2},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"user_id": fixture.USER_STAFF_ID, "revoked_count": 2}
    db_session.expire_all()
    assert db_session.get(AuthSession, first).revoked_at is not None
    assert db_session.get(AuthSession, second).revoked_at is not None


def test_access_audit_is_clinic_scoped_and_security_only(admin_client, db_session):
    db_session.add(
        AuditLog(
            audit_id="aud_other_clinic_security",
            actor_id=fixture.USER_CLINICIAN_B_ID,
            actor_role="clinician",
            action="login_success",
            target_type="session",
            target_id="ses_other",
            from_version=None,
            to_version=None,
            clinic_id=fixture.CLINIC_B_ID,
            patient_id=None,
            event_id=None,
            details=None,
            created_at=datetime.now(),
        )
    )
    db_session.commit()
    response = admin_client.get("/api/admin/access-audit")
    assert response.status_code == 200
    rows = response.json()
    assert all(
        set(row)
        == {
            "audit_id",
            "actor_id",
            "actor_role",
            "action",
            "target_type",
            "target_id",
            "details",
            "created_at",
        }
        for row in rows
    )
    assert all(row["action"] in {
        "invite_created",
        "register",
        "login_success",
        "login_failure",
        "logout",
        "session_revoked",
        "account_disabled",
        "account_reactivated",
    } for row in rows)
    assert "aud_other_clinic_security" not in {row["audit_id"] for row in rows}
    serialized = str(rows).lower()
    assert "content" not in serialized
    assert "password" not in serialized
    assert "token_hash" not in serialized
