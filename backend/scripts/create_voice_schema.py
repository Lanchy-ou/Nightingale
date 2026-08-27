"""Compatibility entry point for the unified E1-E4 schema migration.

The migration never drops an existing table. The configured SQLCipher mode/key
are reused through app.db.
"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.db import engine, migrate_phase_e_schema  # noqa: E402


def main() -> None:
    migrate_phase_e_schema(engine)
    print("VOICE_SCHEMA_READY")


if __name__ == "__main__":
    main()
