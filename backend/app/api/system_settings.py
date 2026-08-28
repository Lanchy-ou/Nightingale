"""Admin-only device settings; responses are secret- and path-free."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session

from ..audit import add_audit
from ..authz import authorize, require_auth
from ..credential_store import (
    CredentialStoreError,
    delete_secret,
    read_secret,
    store_secret,
)
from ..db import DATABASE_MODE, SessionLocal, get_db
from ..llm_client import DeepSeekAdapter
from ..models import SystemSettings
from ..role_context import RoleContext
from ..schemas import (
    AdminAISettingsOut,
    AdminDeepSeekKeyRequest,
    AdminSettingsVersionRequest,
    AdminSystemSettingsOut,
    AdminSystemSettingsUpdate,
    AdminVoiceSettingsOut,
    VoiceModelStatusOut,
)
from ..system_settings import SETTINGS_ID, ensure_settings
from ..voice.model_manager import model_status, start_model_download

router = APIRouter(prefix="/api/admin/system-settings", tags=["admin-settings"])


def _authorize(ctx: RoleContext, action: str) -> None:
    authorize(ctx, action, ctx.clinic_id, None)


def _key_configured(row: SystemSettings) -> tuple[bool, str | None]:
    if row.deepseek_secret_ref:
        try:
            return bool(read_secret(row.deployment_id, row.deepseek_secret_ref)), "credential_manager"
        except CredentialStoreError:
            return False, "credential_manager"
    config = effective_ai_config_from_row(row)
    return bool(config), "environment" if row.deepseek_key_source == "environment" else None


def effective_ai_config_from_row(row: SystemSettings) -> str | None:
    if row.deepseek_key_source != "environment":
        return None
    import os

    return os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("Natingale_API_KEY")


def _out(db: Session, row: SystemSettings) -> AdminSystemSettingsOut:
    configured, source = _key_configured(row)
    state = model_status()
    warning = None
    if DATABASE_MODE != "sqlcipher":
        warning = "Development SQLite: synthetic audio only. Production Voice requires SQLCipher."
    return AdminSystemSettingsOut(
        version=row.version,
        ai=AdminAISettingsOut(
            mode=row.ai_mode,
            provider="deepseek" if row.ai_mode == "deepseek" else "local",
            key_configured=configured,
            key_suffix=row.deepseek_key_suffix if configured else None,
            key_source=source,
            verified_at=row.deepseek_verified_at,
            online_text_egress=row.ai_mode == "deepseek",
        ),
        voice=AdminVoiceSettingsOut(
            enabled=row.voice_enabled,
            provider="faster_whisper",
            model_status=state["status"],
            model=state["model"],
            revision=state["revision"],
            download_bytes_approx=state["download_bytes_approx"],
            storage_mode=DATABASE_MODE,
            warning=warning,
            error_code=state["error_code"],
        ),
        updated_at=row.updated_at,
    )


def _version_conflict() -> HTTPException:
    return HTTPException(status_code=409, detail="System settings version conflict")


@router.get("", response_model=AdminSystemSettingsOut)
def read_system_settings(
    db: Session = Depends(get_db), ctx: RoleContext = Depends(require_auth)
):
    _authorize(ctx, "admin_read_system_settings")
    return _out(db, ensure_settings(db))


@router.patch("", response_model=AdminSystemSettingsOut)
def update_system_settings(
    body: AdminSystemSettingsUpdate,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    _authorize(ctx, "admin_update_system_settings")
    row = ensure_settings(db)
    if row.version != body.expected_version:
        raise _version_conflict()
    if body.ai_mode == "deepseek" and not _key_configured(row)[0]:
        raise HTTPException(status_code=409, detail="A verified DeepSeek key is required")
    if body.voice_enabled is True:
        state = model_status()
        if state["status"] != "ready":
            raise HTTPException(status_code=409, detail="The local Voice model is not ready")
        if DATABASE_MODE == "sqlite" and __import__("os").environ.get("NANTINGALE_ENV", "development") == "production":
            raise HTTPException(status_code=409, detail="Production Voice requires SQLCipher")

    values = {"version": row.version + 1, "updated_by": ctx.user_id, "updated_at": datetime.now()}
    actions: list[tuple[str, dict]] = []
    if body.ai_mode is not None and body.ai_mode != row.ai_mode:
        values["ai_mode"] = body.ai_mode
        actions.append(("system_ai_mode_changed", {"from": row.ai_mode, "to": body.ai_mode}))
    if body.voice_enabled is not None and body.voice_enabled != row.voice_enabled:
        values["voice_enabled"] = body.voice_enabled
        actions.append(("system_voice_changed", {"from": row.voice_enabled, "to": body.voice_enabled}))
    if not actions:
        return _out(db, row)
    result = db.execute(
        update(SystemSettings)
        .where(SystemSettings.settings_id == SETTINGS_ID, SystemSettings.version == body.expected_version)
        .values(**values)
    )
    if result.rowcount != 1:
        db.rollback()
        raise _version_conflict()
    for action, details in actions:
        add_audit(
            db, actor_id=ctx.user_id, actor_role=ctx.role, action=action,
            target_type="system_settings", target_id=SETTINGS_ID,
            clinic_id=ctx.clinic_id, patient_id=None, details=details,
        )
    db.commit()
    return _out(db, db.get(SystemSettings, SETTINGS_ID))


@router.post("/deepseek-key", response_model=AdminSystemSettingsOut)
def verify_and_store_deepseek_key(
    body: AdminDeepSeekKeyRequest,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    _authorize(ctx, "admin_update_system_settings")
    row = ensure_settings(db)
    if row.version != body.expected_version:
        raise _version_conflict()
    key = body.api_key.get_secret_value().strip()
    try:
        DeepSeekAdapter(api_key=key).verify_connection()
    except Exception:
        raise HTTPException(status_code=503, detail="DeepSeek connection verification failed")
    row = db.get(SystemSettings, SETTINGS_ID)
    if row.version != body.expected_version:
        raise _version_conflict()
    new_ref = str(uuid.uuid4())
    try:
        store_secret(row.deployment_id, new_ref, key)
    except CredentialStoreError:
        raise HTTPException(status_code=503, detail="Windows Credential Manager is unavailable")
    old_ref = row.deepseek_secret_ref
    now = datetime.now()
    try:
        result = db.execute(
            update(SystemSettings)
            .where(SystemSettings.settings_id == SETTINGS_ID, SystemSettings.version == body.expected_version)
            .values(
                deepseek_secret_ref=new_ref,
                deepseek_key_suffix=key[-4:],
                deepseek_key_source="credential_manager",
                deepseek_verified_at=now,
                version=row.version + 1,
                updated_by=ctx.user_id,
                updated_at=now,
            )
        )
        if result.rowcount != 1:
            raise _version_conflict()
        add_audit(
            db, actor_id=ctx.user_id, actor_role=ctx.role,
            action="system_key_rotated", target_type="system_settings",
            target_id=SETTINGS_ID, clinic_id=ctx.clinic_id, patient_id=None,
            details={"source": "credential_manager"},
        )
        db.commit()
    except Exception:
        db.rollback()
        try:
            delete_secret(row.deployment_id, new_ref)
        except CredentialStoreError:
            pass
        raise
    if old_ref:
        try:
            delete_secret(row.deployment_id, old_ref)
        except CredentialStoreError:
            pass
    return _out(db, db.get(SystemSettings, SETTINGS_ID))


@router.delete("/deepseek-key", response_model=AdminSystemSettingsOut)
def remove_deepseek_key(
    body: AdminSettingsVersionRequest,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    _authorize(ctx, "admin_update_system_settings")
    row = ensure_settings(db)
    if row.version != body.expected_version:
        raise _version_conflict()
    old_ref = row.deepseek_secret_ref
    result = db.execute(
        update(SystemSettings)
        .where(SystemSettings.settings_id == SETTINGS_ID, SystemSettings.version == body.expected_version)
        .values(
            ai_mode="local", deepseek_secret_ref=None, deepseek_key_suffix=None,
            deepseek_key_source=None, deepseek_verified_at=None,
            version=row.version + 1, updated_by=ctx.user_id, updated_at=datetime.now(),
        )
    )
    if result.rowcount != 1:
        db.rollback()
        raise _version_conflict()
    add_audit(
        db, actor_id=ctx.user_id, actor_role=ctx.role, action="system_key_removed",
        target_type="system_settings", target_id=SETTINGS_ID,
        clinic_id=ctx.clinic_id, patient_id=None, details={"ai_mode": "local"},
    )
    db.commit()
    if old_ref:
        try:
            delete_secret(row.deployment_id, old_ref)
        except CredentialStoreError:
            pass
    return _out(db, db.get(SystemSettings, SETTINGS_ID))


def _record_model_result(actor_id: str, actor_role: str, clinic_id: str, final: str) -> None:
    with SessionLocal() as db:
        add_audit(
            db, actor_id=actor_id, actor_role=actor_role,
            action="voice_model_completed" if final == "ready" else "voice_model_failed",
            target_type="system_settings", target_id=SETTINGS_ID,
            clinic_id=clinic_id, patient_id=None, details={"status": final},
        )
        db.commit()


@router.post("/voice-model", response_model=VoiceModelStatusOut, status_code=202)
def prepare_voice_model(
    db: Session = Depends(get_db), ctx: RoleContext = Depends(require_auth)
):
    _authorize(ctx, "admin_update_system_settings")
    ensure_settings(db)
    before = model_status()
    state = start_model_download(
        lambda final: _record_model_result(ctx.user_id, ctx.role, ctx.clinic_id, final)
    )
    if before["status"] not in {"ready", "downloading"} and state["status"] == "downloading":
        add_audit(
            db, actor_id=ctx.user_id, actor_role=ctx.role, action="voice_model_started",
            target_type="system_settings", target_id=SETTINGS_ID,
            clinic_id=ctx.clinic_id, patient_id=None, details={"status": "downloading"},
        )
        db.commit()
    return VoiceModelStatusOut(**state)


@router.get("/voice-model/status", response_model=VoiceModelStatusOut)
def read_voice_model_status(
    ctx: RoleContext = Depends(require_auth),
):
    _authorize(ctx, "admin_read_system_settings")
    return VoiceModelStatusOut(**model_status())
