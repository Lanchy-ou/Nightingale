"""Restore a SQLCipher backup to a new, separately keyed database file."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.storage_security import assert_sqlcipher_file, restore_encrypted_backup


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    backup_key = os.environ.get("NANTINGALE_BACKUP_KEY", "")
    restored_key = os.environ.get("NANTINGALE_RESTORED_DB_KEY", "")
    database_key = os.environ.get("NANTINGALE_DB_KEY", "")
    restore_encrypted_backup(
        args.input,
        backup_key,
        args.output,
        restored_key,
        database_key,
    )
    probe = assert_sqlcipher_file(args.output, restored_key)
    print(json.dumps({"status": "ENCRYPTED_RESTORE_VERIFIED", **probe}, sort_keys=True))


if __name__ == "__main__":
    main()
