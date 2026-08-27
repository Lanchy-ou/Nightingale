"""Centralized server-side authorization (M3).

This is THE single place RBAC rules live. Reviewers should only need to read
this function + PERMISSIONS. Endpoints must NOT hand-write their own role
checks.

Semantics:
- unauthenticated (no valid X-User-Id) => 401 (via require_auth)
- authenticated but cross-clinic / not-own-patient => 404 (hide existence)
- authenticated, same clinic, but action not allowed => 403
"""
from __future__ import annotations

from fastapi import Depends, HTTPException

from .role_context import RoleContext, get_role_context

# action -> roles allowed. Any action not listed for a role is denied.
PERMISSIONS: dict[str, dict[str, bool]] = {
    "patient": {
        "read_patient": True,
        "read_events": True,
        "read_artifacts": True,
        "read_patient_view": True,
        "create_patient_session": True,
        "read_tasks": True,
        "transition_task": True,
    },
    "staff": {
        "read_patient": True,
        "read_events": True,
        "read_artifacts": True,
        "read_glance": True,
        "read_provenance": True,
        "read_comments": True,
        "read_versions": True,
        "read_audit": True,
        "write_staff_note": True,
        "edit_staff_note": True,
        "ingest_nurse_transcript": True,
        "list_clinic_patients": True,
        "comment": True,
        "highlight_status": True,
        "read_tasks": True,
        "read_task_provenance": True,
        "create_task": True,
        "transition_task": True,
    },
    "clinician": {
        "read_patient": True,
        "read_events": True,
        "read_artifacts": True,
        "read_glance": True,
        "read_provenance": True,
        "read_comments": True,
        "read_versions": True,
        "read_audit": True,
        "write_clinician_note": True,
        "edit_clinician_note": True,
        "ingest_doctor_transcript": True,
        "create_doctor_consult": True,
        "normalize_doctor_transcript": True,
        "list_clinic_patients": True,
        "comment": True,
        "highlight_status": True,
        "read_tasks": True,
        "read_task_provenance": True,
        "create_task": True,
        "transition_task": True,
    },
    "admin": {
        # Read-only oversight, clinic-scoped. No note/comment/highlight writes.
        "read_patient": True,
        "read_events": True,
        "read_artifacts": True,
        "read_glance": True,
        "read_provenance": True,
        "read_comments": True,
        "read_versions": True,
        "read_audit": True,
        "list_clinic_patients": True,
        # D1: clinic-scoped invite administration (no cross-clinic invites).
        "create_invite": True,
        "list_invites": True,
        "read_tasks": True,
        "read_task_provenance": True,
    },
}

# Artifact types visible to a patient-role user (M3 allowlist).
PATIENT_VISIBLE_ARTIFACT_TYPES = {"patient_instruction"}

# Artifact types that can be edited in M3 (role-owned sections).
EDITABLE_ARTIFACT_TYPES = {"staff_note", "clinician_note"}


def resource_not_found() -> HTTPException:
    """Return one indistinguishable response for absent and out-of-scope resources."""
    return HTTPException(status_code=404, detail="Resource not found")


def require_auth(ctx: RoleContext = Depends(get_role_context)) -> RoleContext:
    if not ctx.authenticated:
        raise HTTPException(status_code=401, detail="Authentication required")
    return ctx


def authorize_scope(ctx: RoleContext, clinic_id: str | None, patient_id: str | None) -> None:
    # Cross-clinic and not-own-patient both look like "not found" (no existence leak).
    if clinic_id is not None and ctx.clinic_id != clinic_id:
        raise resource_not_found()
    if (
        ctx.role == "patient"
        and patient_id is not None
        and ctx.patient_id != patient_id
    ):
        raise resource_not_found()


def authorize(
    ctx: RoleContext,
    action: str,
    clinic_id: str | None,
    patient_id: str | None,
) -> None:
    authorize_scope(ctx, clinic_id, patient_id)
    if not PERMISSIONS.get(ctx.role, {}).get(action, False):
        raise HTTPException(status_code=403, detail="Forbidden")


def note_edit_action(artifact_type: str) -> str | None:
    if artifact_type == "staff_note":
        return "edit_staff_note"
    if artifact_type == "clinician_note":
        return "edit_clinician_note"
    return None
