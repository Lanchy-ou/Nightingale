"""Device-level runtime settings with environment bootstrap compatibility."""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from .credential_store import CredentialStoreError, read_secret
from .models import SystemSettings

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
    row = SystemSettings(**_bootstrap_values())
    db.add(row)
    db.commit()
    return db.get(SystemSettings, SETTINGS_ID)


def effective_ai_config(db: Session) -> EffectiveAIConfig:
    row = get_settings(db)
    if row is None:
        provider = os.environ.get("NANTINGALE_LLM_PROVIDER", "deepseek").strip().lower()
        return EffectiveAIConfig(
            provider="deepseek" if provider == "deepseek" else "mock",
            # Preserve the legacy adapter boundary for environment bootstrap:
            # DeepSeekAdapter reads the environment itself. Explicit key
            # injection is reserved for Credential Manager-backed settings.
            api_key=None,
            source="environment" if provider == "deepseek" and _env_key() else None,
        )
    if row.ai_mode != "deepseek":
        return EffectiveAIConfig(provider="local", api_key=None, source=None)
    if row.deepseek_secret_ref:
        try:
            key = read_secret(row.deployment_id, row.deepseek_secret_ref)
        except CredentialStoreError:
            key = None
        return EffectiveAIConfig(provider="deepseek", api_key=key, source="credential_manager")
    if row.deepseek_key_source == "environment":
        return EffectiveAIConfig(provider="deepseek", api_key=None, source="environment")
    return EffectiveAIConfig(provider="deepseek", api_key=None, source=None)


def effective_voice_enabled(db: Session) -> bool:
    row = get_settings(db)
    if row is not None:
        return bool(row.voice_enabled)
    return os.environ.get("NANTINGALE_VOICE_ENABLED", "false").strip().lower() == "true"
