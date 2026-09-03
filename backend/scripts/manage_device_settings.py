"""Deployment-local device settings; secrets are prompted, never command arguments."""
from __future__ import annotations

import argparse
from getpass import getpass
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import SessionLocal  # noqa: E402
from app.device_settings import (  # noqa: E402
    remove_device_deepseek_key,
    store_device_deepseek_key,
    update_device_defaults,
)
from app.system_settings import device_deepseek_available, ensure_settings  # noqa: E402
from app.voice.model_manager import model_status, prepare_model_blocking  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("show")
    subcommands.add_parser("set-key")
    subcommands.add_parser("remove-key")
    ai = subcommands.add_parser("set-ai-default")
    ai.add_argument("mode", choices=("local", "deepseek"))
    voice = subcommands.add_parser("set-voice-default")
    voice.add_argument("mode", choices=("enabled", "disabled"))
    subcommands.add_parser("prepare-voice-model")
    args = parser.parse_args()

    if args.command == "prepare-voice-model":
        prepare_model_blocking()
        print(json.dumps(model_status(), sort_keys=True))
        return

    with SessionLocal() as db:
        if args.command == "set-key":
            key = getpass("DeepSeek API key: ")
            store_device_deepseek_key(db, key)
        elif args.command == "remove-key":
            remove_device_deepseek_key(db)
        elif args.command == "set-ai-default":
            update_device_defaults(db, ai_mode=args.mode)
        elif args.command == "set-voice-default":
            update_device_defaults(db, voice_enabled=args.mode == "enabled")
        row = ensure_settings(db)
        print(
            json.dumps(
                {
                    "ai_mode": row.ai_mode,
                    "deepseek_available": device_deepseek_available(db),
                    "voice_enabled": row.voice_enabled,
                    "voice_model_status": model_status()["status"],
                    "version": row.version,
                },
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
