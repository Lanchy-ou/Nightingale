"""Deployment-local management of shared AI credentials and device defaults."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import update
from sqlalchemy.orm import Session

from .audit import add_audit
from .credential_store import delete_secret, store_secret
from .llm_client import DeepSeekAdapter
from .models import SystemSettings
from .system_settings import SETTINGS_ID, device_deepseek_available, ensure_settings


def store_device_deepseek_key(db: Session, key: str) -> SystemSettings:
    value = key.strip()
    if len(value) < 8:
        raise ValueError("Device AI key is too short")
    DeepSeekAdapter(api_key=value).verify_connection()
    row = ensure_settings(db)
    new_ref = str(uuid.uuid4())
    store_secret(row.deployment_id, new_ref, value)
    old_ref = row.deepseek_secret_ref
    now = datetime.now()
    try:
        db.execute(
            update(SystemSettings)
            .where(SystemSettings.settings_id == SETTINGS_ID)
            .values(
                deepseek_secret_ref=new_ref,
                deepseek_key_suffix=value[-4:],
                deepseek_key_source="credential_manager",
                deepseek_verified_at=now,
                version=row.version + 1,
                updated_by=None,
                updated_at=now,
            )
        )
        add_audit(
            db,
            actor_id=None,
            actor_role="system",
            action="system_key_rotated",
            target_type="system_settings",
            target_id=SETTINGS_ID,
            clinic_id=None,
            patient_id=None,
            details={"source": "credential_manager"},
        )
        db.commit()
    except Exception:
        db.rollback()
        try:
            delete_secret(row.deployment_id, new_ref)
        except Exception:
            pass
        raise
    if old_ref:
        try:
            delete_secret(row.deployment_id, old_ref)
        except Exception:
            pass
    return db.get(SystemSettings, SETTINGS_ID)


def remove_device_deepseek_key(db: Session) -> SystemSettings:
    row = ensure_settings(db)
    old_ref = row.deepseek_secret_ref
    now = datetime.now()
    db.execute(
        update(SystemSettings)
        .where(SystemSettings.settings_id == SETTINGS_ID)
        .values(
            ai_mode="local",
            deepseek_secret_ref=None,
            deepseek_key_suffix=None,
            deepseek_key_source=None,
            deepseek_verified_at=None,
            version=row.version + 1,
            updated_by=None,
            updated_at=now,
        )
    )
    add_audit(
        db,
        actor_id=None,
        actor_role="system",
        action="system_key_removed",
        target_type="system_settings",
        target_id=SETTINGS_ID,
        clinic_id=None,
        patient_id=None,
        details={"ai_mode": "local"},
    )
    db.commit()
    if old_ref:
        try:
            delete_secret(row.deployment_id, old_ref)
        except Exception:
            pass
    return db.get(SystemSettings, SETTINGS_ID)


def update_device_defaults(
    db: Session, *, ai_mode: str | None = None, voice_enabled: bool | None = None
) -> SystemSettings:
    row = ensure_settings(db)
    if ai_mode not in {None, "local", "deepseek"}:
        raise ValueError("Invalid device AI mode")
    if ai_mode == "deepseek" and not device_deepseek_available(db):
        raise ValueError("The device AI provider is not configured")
    if voice_enabled is True:
        from .voice.model_manager import model_status

        if model_status()["status"] != "ready":
            raise ValueError("The local Voice model is not ready")
    values: dict = {}
    actions: list[tuple[str, dict]] = []
    if ai_mode is not None and ai_mode != row.ai_mode:
        values["ai_mode"] = ai_mode
        actions.append(("system_ai_mode_changed", {"from": row.ai_mode, "to": ai_mode}))
    if voice_enabled is not None and voice_enabled != row.voice_enabled:
        values["voice_enabled"] = voice_enabled
        actions.append(
            ("system_voice_changed", {"from": row.voice_enabled, "to": voice_enabled})
        )
    if not actions:
        return row
    values.update(version=row.version + 1, updated_by=None, updated_at=datetime.now())
    db.execute(
        update(SystemSettings)
        .where(SystemSettings.settings_id == SETTINGS_ID)
        .values(**values)
    )
    for action, details in actions:
        add_audit(
            db,
            actor_id=None,
            actor_role="system",
            action=action,
            target_type="system_settings",
            target_id=SETTINGS_ID,
            clinic_id=None,
            patient_id=None,
            details=details,
        )
    db.commit()
    return db.get(SystemSettings, SETTINGS_ID)
