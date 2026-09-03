"""Idempotently add F_B5 operational onboarding tables."""
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import engine, install_clinic_isolation_schema, migrate_fb5_schema  # noqa: E402


def main() -> None:
    migrate_fb5_schema(engine)
    install_clinic_isolation_schema(engine)
    print("F_B5 schema migration complete")


if __name__ == "__main__":
    main()
