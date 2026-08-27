"""Apply the explicit, idempotent E1-E4 synthetic Demo migration."""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.db import engine, migrate_phase_e_schema  # noqa: E402


if __name__ == "__main__":
    migrate_phase_e_schema(engine)
    print("PHASE_E_SCHEMA_READY")
