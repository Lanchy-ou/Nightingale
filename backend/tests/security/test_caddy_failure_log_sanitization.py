from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

import httpx
import pytest


FAKE_TOKEN = "D5_CADDY_OFFLINE_FAKE_TOKEN_MUST_NEVER_APPEAR"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _caddy_binary(repo_root: Path) -> str | None:
    configured = os.environ.get("NANTINGALE_CADDY_BINARY", "").strip()
    if configured:
        return configured
    local = repo_root / ".tools" / "caddy-2.11.4" / "caddy.exe"
    if local.is_file():
        return str(local)
    return shutil.which("caddy")


def _wait_until_listening(process: subprocess.Popen, port: int) -> None:
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Caddy exited before the failure probe")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError("Caddy did not start within the probe timeout")


def test_offline_upstream_never_logs_or_echoes_preview_token(tmp_path):
    repo_root = Path(__file__).resolve().parents[3]
    caddy = _caddy_binary(repo_root)
    if caddy is None:
        pytest.skip("Caddy binary not available; run with NANTINGALE_CADDY_BINARY")

    caddy_port = _free_port()
    offline_backend_port = _free_port()
    config = tmp_path / "Caddyfile"
    config.write_text(
        "{\n"
        "\tadmin off\n"
        "\tauto_https off\n"
        "}\n\n"
        f"http://127.0.0.1:{caddy_port} {{\n"
        "\tbind 127.0.0.1\n"
        "\tlog {\n"
        "\t\toutput stderr\n"
        "\t\tformat json\n"
        "\t}\n"
        f"\treverse_proxy 127.0.0.1:{offline_backend_port}\n"
        "}\n",
        encoding="utf-8",
    )
    # The application is deliberately offline. This file represents its log
    # sink and must remain unchanged while Caddy handles the failed upstream.
    application_log = tmp_path / "application.log"
    application_log.write_text("", encoding="utf-8")

    environment = os.environ.copy()
    environment["XDG_DATA_HOME"] = str(tmp_path / "caddy-data")
    environment["XDG_CONFIG_HOME"] = str(tmp_path / "caddy-config")
    process = subprocess.Popen(
        [caddy, "run", "--config", str(config), "--adapter", "caddyfile"],
        cwd=repo_root,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    response_text = ""
    response_status = None
    try:
        _wait_until_listening(process, caddy_port)
        with httpx.Client(trust_env=False, timeout=5) as client:
            response = client.post(
                f"http://127.0.0.1:{caddy_port}/api/auth/invites/preview",
                json={"token": FAKE_TOKEN},
            )
        response_status = response.status_code
        response_text = response.text
        time.sleep(0.2)
    finally:
        process.terminate()
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate(timeout=5)

    assert response_status == 502
    assert "/api/auth/invites/preview" in stderr
    assert '"status":502' in stderr
    assert FAKE_TOKEN not in response_text
    assert FAKE_TOKEN not in stdout
    assert FAKE_TOKEN not in stderr
    assert FAKE_TOKEN not in application_log.read_text(encoding="utf-8")
    assert application_log.read_text(encoding="utf-8") == ""
