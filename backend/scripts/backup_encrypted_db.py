"""Create a separately keyed encrypted SQLCipher backup without overwriting."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.storage_security import assert_sqlcipher_file, create_encrypted_backup


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    database_path = os.environ.get("NANTINGALE_DB_PATH", "").strip()
    database_key = os.environ.get("NANTINGALE_DB_KEY", "")
    backup_key = os.environ.get("NANTINGALE_BACKUP_KEY", "")
    if not database_path:
        raise SystemExit("NANTINGALE_DB_PATH is required")

    create_encrypted_backup(
        Path(database_path), database_key, args.output, backup_key
    )
    probe = assert_sqlcipher_file(args.output, backup_key)
    print(json.dumps({"status": "ENCRYPTED_BACKUP_CREATED", **probe}, sort_keys=True))


if __name__ == "__main__":
    main()
