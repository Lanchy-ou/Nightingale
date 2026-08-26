"""Short unique + stable id generators for runtime-created rows."""
from __future__ import annotations

import hashlib
import uuid


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def stable_id(*parts: str) -> str:
    """Deterministic id from parts (used for idempotent derivation)."""
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
