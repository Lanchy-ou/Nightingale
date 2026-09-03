"""Device-level runtime settings with environment bootstrap compatibility."""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from .credential_store import CredentialStoreError, read_secret
from .models import ClinicSettings, SystemSettings

SETTINGS_ID = "device"


@dataclass(frozen=True)
class EffectiveAIConfig:
    provider: str
    api_key: str | None
    source: str | None


def _env_key() -> str | None:
    return os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("Natingale_API_KEY")


def _bootstrap_values() -> dict:
    provider = os.environ.get("NANTINGALE_LLM_PROVIDER", "mock").strip().lower()
    key = _env_key() if provider == "deepseek" else None
    return {
        "settings_id": SETTINGS_ID,
        "deployment_id": str(uuid.uuid4()),
        "ai_mode": "deepseek" if provider == "deepseek" else "local",
        "voice_enabled": os.environ.get("NANTINGALE_VOICE_ENABLED", "false").strip().lower() == "true",
        "deepseek_secret_ref": None,
        "deepseek_key_suffix": key[-4:] if key else None,
        "deepseek_key_source": "environment" if key else None,
        "deepseek_verified_at": None,
        "version": 1,
        "updated_by": None,
        "updated_at": datetime.now(),
    }


def get_settings(db: Session) -> SystemSettings | None:
    return db.get(SystemSettings, SETTINGS_ID)


def ensure_settings(db: Session) -> SystemSettings:
    row = get_settings(db)
    if row is not None:
        return row
    # A first read may arrive concurrently from two tabs or two React mounts.
    # Let the database choose the single winner instead of racing two ORM
    # INSERTs for the fixed device primary key.
    db.execute(
        sqlite_insert(SystemSettings)
        .values(**_bootstrap_values())
        .on_conflict_do_nothing(index_elements=[SystemSettings.settings_id])
    )
    db.commit()
    row = db.get(SystemSettings, SETTINGS_ID)
    if row is None:
        raise RuntimeError("System settings initialization failed")
    return row


def get_clinic_settings(db: Session, clinic_id: str) -> ClinicSettings | None:
    return db.get(ClinicSettings, clinic_id)


def ensure_clinic_settings(db: Session, clinic_id: str) -> ClinicSettings:
    row = get_clinic_settings(db, clinic_id)
    if row is not None:
        return row
    db.execute(
        sqlite_insert(ClinicSettings)
        .values(
            clinic_id=clinic_id,
            ai_mode_override=None,
            voice_enabled_override=None,
            version=1,
            updated_by=None,
            updated_at=datetime.now(),
        )
        .on_conflict_do_nothing(index_elements=[ClinicSettings.clinic_id])
    )
    db.commit()
    row = db.get(ClinicSettings, clinic_id)
    if row is None:
        raise RuntimeError("Clinic settings initialization failed")
    return row


def _device_deepseek_config(row: SystemSettings | None) -> EffectiveAIConfig:
    if row is None:
        key = _env_key()
        return EffectiveAIConfig(
            provider="deepseek",
            api_key=None,
            source="environment" if key else None,
        )
    if row.deepseek_secret_ref:
        try:
            key = read_secret(row.deployment_id, row.deepseek_secret_ref)
        except CredentialStoreError:
            key = None
        return EffectiveAIConfig(
            provider="deepseek", api_key=key, source="credential_manager"
        )
    if row.deepseek_key_source == "environment":
        return EffectiveAIConfig(
            provider="deepseek", api_key=None, source="environment" if _env_key() else None
        )
    return EffectiveAIConfig(provider="deepseek", api_key=None, source=None)


def device_deepseek_available(db: Session) -> bool:
    config = _device_deepseek_config(get_settings(db))
    if config.source == "environment":
        return bool(_env_key())
    return bool(config.api_key)


def effective_ai_config(db: Session, clinic_id: str | None = None) -> EffectiveAIConfig:
    row = get_settings(db)
    if row is None:
        provider = os.environ.get("NANTINGALE_LLM_PROVIDER", "deepseek").strip().lower()
        selected_mode = "deepseek" if provider == "deepseek" else "mock"
    else:
        selected_mode = row.ai_mode
    if clinic_id is not None:
        clinic = get_clinic_settings(db, clinic_id)
        if clinic is not None and clinic.ai_mode_override is not None:
            selected_mode = clinic.ai_mode_override
    if selected_mode != "deepseek":
        return EffectiveAIConfig(provider=selected_mode, api_key=None, source=None)
    return _device_deepseek_config(row)


def effective_voice_enabled(db: Session, clinic_id: str | None = None) -> bool:
    row = get_settings(db)
    if row is not None:
        enabled = bool(row.voice_enabled)
    else:
        enabled = os.environ.get("NANTINGALE_VOICE_ENABLED", "false").strip().lower() == "true"
    if clinic_id is not None:
        clinic = get_clinic_settings(db, clinic_id)
        if clinic is not None and clinic.voice_enabled_override is not None:
            enabled = bool(clinic.voice_enabled_override)
    return enabled
