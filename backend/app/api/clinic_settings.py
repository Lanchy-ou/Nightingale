"""Clinic-owned AI/Voice choices over read-only device capabilities."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session

from ..audit import add_audit
from ..authz import authorize, require_auth
from ..db import DATABASE_MODE, get_db
from ..models import ClinicSettings
from ..role_context import RoleContext
from ..schemas import (
    ClinicAISettingsOut,
    ClinicSettingsOut,
    ClinicSettingsUpdate,
    ClinicVoiceSettingsOut,
)
from ..system_settings import (
    device_deepseek_available,
    effective_ai_config,
    effective_voice_enabled,
    ensure_clinic_settings,
)
from ..voice.model_manager import model_status

router = APIRouter(prefix="/api/admin/clinic-settings", tags=["clinic-settings"])


def _selected_voice(value: bool | None) -> str:
    if value is None:
        return "inherit"
    return "enabled" if value else "disabled"


def _out(db: Session, row: ClinicSettings) -> ClinicSettingsOut:
    config = effective_ai_config(db, row.clinic_id)
    effective_mode = "deepseek" if config.provider == "deepseek" else "local"
    state = model_status()
    warning = None
    if DATABASE_MODE != "sqlcipher":
        warning = "Development SQLite: synthetic audio only. Production Voice requires SQLCipher."
    ai_selected = row.ai_mode_override or "inherit"
    voice_selected = _selected_voice(row.voice_enabled_override)
    return ClinicSettingsOut(
        clinic_id=row.clinic_id,
        version=row.version,
        ai=ClinicAISettingsOut(
            selected_mode=ai_selected,
            effective_mode=effective_mode,
            inherited=row.ai_mode_override is None,
            provider_available=device_deepseek_available(db),
            online_text_egress=effective_mode == "deepseek",
        ),
        voice=ClinicVoiceSettingsOut(
            selected_mode=voice_selected,
            effective_enabled=effective_voice_enabled(db, row.clinic_id),
            inherited=row.voice_enabled_override is None,
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


@router.get("", response_model=ClinicSettingsOut)
def read_clinic_settings(
    db: Session = Depends(get_db), ctx: RoleContext = Depends(require_auth)
):
    authorize(ctx, "admin_read_clinic_settings", ctx.clinic_id, None)
    return _out(db, ensure_clinic_settings(db, ctx.clinic_id))


@router.patch("", response_model=ClinicSettingsOut)
def update_clinic_settings(
    body: ClinicSettingsUpdate,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    authorize(ctx, "admin_update_clinic_settings", ctx.clinic_id, None)
    row = ensure_clinic_settings(db, ctx.clinic_id)
    if row.version != body.expected_version:
        raise HTTPException(status_code=409, detail="Clinic settings version conflict")
    if body.ai_mode == "deepseek" and not device_deepseek_available(db):
        raise HTTPException(status_code=409, detail="The device AI provider is not configured")
    if body.voice_mode == "enabled":
        state = model_status()
        if state["status"] != "ready":
            raise HTTPException(status_code=409, detail="The local Voice model is not ready")
        if DATABASE_MODE == "sqlite" and __import__("os").environ.get(
            "NANTINGALE_ENV", "development"
        ) == "production":
            raise HTTPException(status_code=409, detail="Production Voice requires SQLCipher")

    ai_value = None if body.ai_mode == "inherit" else body.ai_mode
    voice_value = (
        None
        if body.voice_mode == "inherit"
        else body.voice_mode == "enabled"
        if body.voice_mode is not None
        else row.voice_enabled_override
    )
    values: dict = {}
    actions: list[tuple[str, dict]] = []
    if body.ai_mode is not None and ai_value != row.ai_mode_override:
        values["ai_mode_override"] = ai_value
        actions.append(
            (
                "clinic_ai_mode_changed",
                {"from": row.ai_mode_override or "inherit", "to": body.ai_mode},
            )
        )
    if body.voice_mode is not None and voice_value != row.voice_enabled_override:
        values["voice_enabled_override"] = voice_value
        actions.append(
            (
                "clinic_voice_changed",
                {"from": _selected_voice(row.voice_enabled_override), "to": body.voice_mode},
            )
        )
    if not actions:
        return _out(db, row)
    values.update(
        version=row.version + 1, updated_by=ctx.user_id, updated_at=datetime.now()
    )
    result = db.execute(
        update(ClinicSettings)
        .where(
            ClinicSettings.clinic_id == ctx.clinic_id,
            ClinicSettings.version == body.expected_version,
        )
        .values(**values)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Clinic settings version conflict")
    for action, details in actions:
        add_audit(
            db,
            actor_id=ctx.user_id,
            actor_role=ctx.role,
            action=action,
            target_type="clinic_settings",
            target_id=ctx.clinic_id,
            clinic_id=ctx.clinic_id,
            patient_id=None,
            details=details,
        )
    db.commit()
    return _out(db, db.get(ClinicSettings, ctx.clinic_id))
