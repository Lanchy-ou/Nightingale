"""Create one deployment-owned clinic onboarding link without seeding data."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import Base, SessionLocal, engine, install_clinic_isolation_schema, migrate_fb5_schema  # noqa: E402
from app.onboarding import issue_onboarding_token  # noqa: E402
from app.voice.models import VoiceCaptureRecord  # noqa: E402,F401 - register full schema


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    args = parser.parse_args()

    Base.metadata.create_all(engine)
    migrate_fb5_schema(engine)
    install_clinic_isolation_schema(engine)
    with SessionLocal() as db:
        issued = issue_onboarding_token(db, base_url=args.base_url)
    print(issued.setup_link)
    print(f"Expires at: {issued.expires_at.isoformat()}")


if __name__ == "__main__":
    main()
