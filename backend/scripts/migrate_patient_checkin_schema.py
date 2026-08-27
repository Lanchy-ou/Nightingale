"""Idempotently add the Patient Check-in lifecycle tables to a Demo DB."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import engine, migrate_patient_checkin_schema  # noqa: E402


if __name__ == "__main__":
    migrate_patient_checkin_schema(engine)
    print("Patient Check-in schema is ready.")
