"""Revision helpers: stable JSON serialization + unified diff for full snapshots.

Diffs are computed on read (never stored). To make difflib output stable and
readable, content is serialized with sorted keys + fixed indent before diffing.
"""
from __future__ import annotations

import difflib
import json


def stable_text(content: dict) -> str:
    return json.dumps(content, sort_keys=True, indent=2, ensure_ascii=False)


def diff_text(a: dict, b: dict) -> str:
    lines_a = stable_text(a).splitlines(keepends=True)
    lines_b = stable_text(b).splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(lines_a, lines_b, fromfile="version-a", tofile="version-b")
    )
