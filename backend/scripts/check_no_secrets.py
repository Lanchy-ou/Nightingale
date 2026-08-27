"""Fail on high-confidence credential/private-key material in tracked files."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path


PATTERNS = {
    "private_key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "openai_style_secret": re.compile(rb"\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}\b"),
    "aws_access_key": re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
}


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    listed = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={root.as_posix()}",
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
        ],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout
    findings: list[str] = []
    for raw_name in listed.split(b"\x00"):
        if not raw_name:
            continue
        relative = Path(raw_name.decode("utf-8"))
        path = root / relative
        try:
            data = path.read_bytes()
        except OSError:
            continue
        for label, pattern in PATTERNS.items():
            if pattern.search(data):
                findings.append(f"{relative.as_posix()}: {label}")
    if findings:
        raise SystemExit("SECRET_SCAN_FAILED\n" + "\n".join(findings))
    print("SECRET_SCAN_PASS")


if __name__ == "__main__":
    main()
