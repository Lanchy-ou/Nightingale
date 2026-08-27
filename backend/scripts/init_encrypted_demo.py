"""Initialize the synthetic D5 demo in a new SQLCipher database.

Required environment: NANTINGALE_DATABASE_MODE=sqlcipher,
NANTINGALE_DB_PATH and NANTINGALE_DB_KEY.  Existing files are never replaced.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def main() -> None:
    if os.environ.get("NANTINGALE_DATABASE_MODE", "").strip().lower() != "sqlcipher":
        raise SystemExit("NANTINGALE_DATABASE_MODE must be sqlcipher")
    raw_path = os.environ.get("NANTINGALE_DB_PATH", "").strip()
    if not raw_path:
        raise SystemExit("NANTINGALE_DB_PATH is required")
    target = Path(raw_path).resolve()
    if target.exists():
        raise SystemExit(f"Refusing to replace existing database: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)

    from sqlalchemy import func, select

    from app.db import Base, DATABASE_KEY, DATABASE_MODE, SessionLocal, engine
    from app.models import Artifact, Patient
    from app.storage_security import assert_sqlcipher_file
    from seed.seed import seed

    if DATABASE_MODE != "sqlcipher" or engine.url.drivername != "sqlite+pysqlcipher":
        raise SystemExit("The configured SQLAlchemy engine is not SQLCipher")
    try:
        Base.metadata.create_all(engine)
        with SessionLocal() as database:
            seed(database)
            patient_count = database.scalar(select(func.count()).select_from(Patient))
            artifact_count = database.scalar(select(func.count()).select_from(Artifact))
        engine.dispose()
        probe = assert_sqlcipher_file(target, DATABASE_KEY)
    except Exception:
        engine.dispose()
        if target.exists():
            target.unlink()
        raise

    print(
        json.dumps(
            {
                "status": "ENCRYPTED_DEMO_INITIALIZED",
                "patient_count": patient_count,
                "artifact_count": artifact_count,
                **probe,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
