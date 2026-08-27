"""Short-lived signed confirmation tokens for D4 draft writes.

The token is the only way a normal Note/Task write can acquire
``draft_origin=copilot``. It binds the authenticated actor and server-owned
patient/Event/type/evidence decisions; clinical content remains editable.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .highlights import extract_text
from .models import Artifact, Event
from .role_context import RoleContext

TOKEN_TTL_SECONDS = 300
_PROCESS_SECRET = secrets.token_bytes(32)


@dataclass(frozen=True)
class ConfirmationClaims:
    confirmation_id: str
    evidence: list[dict]
    template_digest: str


def _secret() -> bytes:
    configured = os.environ.get("NANTINGALE_COPILOT_CONFIRMATION_SECRET")
    return configured.encode("utf-8") if configured else _PROCESS_SECRET


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def content_digest(content: dict) -> str:
    canonical = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def issue_confirmation_token(
    *, actor_id: str, clinic_id: str, patient_id: str, event_id: str,
    draft_type: str, evidence: list[dict], template_content: dict,
    now: int | None = None,
) -> str:
    issued_at = int(time.time() if now is None else now)
    payload = {
        "v": 1,
        "jti": secrets.token_urlsafe(12),
        "iat": issued_at,
        "exp": issued_at + TOKEN_TTL_SECONDS,
        "actor_id": actor_id,
        "clinic_id": clinic_id,
        "patient_id": patient_id,
        "event_id": event_id,
        "draft_type": draft_type,
        "evidence": evidence,
        "template_digest": content_digest(template_content),
    }
    encoded = _b64(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    signature = _b64(hmac.new(_secret(), encoded.encode("ascii"), hashlib.sha256).digest())
    return f"{encoded}.{signature}"


def validate_confirmation_token(
    token: str | None,
    *, db: Session, ctx: RoleContext, event: Event, expected_type: str, content: dict,
    now: int | None = None,
) -> ConfirmationClaims | None:
    if token is None:
        return None
    try:
        encoded, supplied_signature = token.split(".", 1)
        expected_signature = _b64(hmac.new(_secret(), encoded.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise ValueError("signature")
        payload = json.loads(_unb64(encoded))
        current = int(time.time() if now is None else now)
        if payload.get("v") != 1 or not isinstance(payload.get("exp"), int) or payload["exp"] < current:
            raise ValueError("expired")
        expected = {
            "actor_id": ctx.user_id,
            "clinic_id": event.clinic_id,
            "patient_id": event.patient_id,
            "event_id": event.event_id,
            "draft_type": expected_type,
        }
        if any(payload.get(key) != value for key, value in expected.items()):
            raise ValueError("binding")
        evidence = payload.get("evidence")
        if not isinstance(evidence, list) or not evidence or not all(isinstance(item, dict) for item in evidence):
            raise ValueError("evidence")
        for item in evidence:
            artifact_id = item.get("artifact_id")
            span = item.get("span")
            if item.get("event_id") != event.event_id or not isinstance(artifact_id, str) or not isinstance(span, dict):
                raise ValueError("evidence binding")
            artifact = db.get(Artifact, artifact_id)
            quote = extract_text(artifact.content, span) if artifact is not None and artifact.event_id == event.event_id else None
            if quote is None or hashlib.sha256(quote.encode("utf-8")).hexdigest() != item.get("quote_sha256"):
                raise ValueError("evidence changed")
        template_digest = payload.get("template_digest")
        if not isinstance(template_digest, str):
            raise ValueError("template")
        if expected_type == "patient_instruction" and content_digest(content) == template_digest:
            raise HTTPException(status_code=422, detail="Patient instruction draft must be edited before confirmation")
        return ConfirmationClaims(
            confirmation_id=str(payload["jti"]), evidence=evidence, template_digest=template_digest
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Invalid or expired Copilot confirmation") from exc


def audit_details(claims: ConfirmationClaims | None, base: dict | None = None) -> dict | None:
    details = dict(base or {})
    if claims is not None:
        details.update(
            draft_origin="copilot",
            confirmation_id=claims.confirmation_id,
            evidence_count=len(claims.evidence),
        )
    return details or None
