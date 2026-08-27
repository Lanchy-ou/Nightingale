"""Create only the E4 voice table in the configured existing database.

This is a non-destructive prototype migration: it never drops or rewrites an
existing table. The configured SQLCipher mode/key are reused through app.db.
"""

from app import models as _core_models  # noqa: F401 - register FK target tables
from app.db import engine
from app.voice.models import VoiceCaptureRecord


def main() -> None:
    VoiceCaptureRecord.__table__.create(bind=engine, checkfirst=True)
    print("VOICE_SCHEMA_READY")


if __name__ == "__main__":
    main()
