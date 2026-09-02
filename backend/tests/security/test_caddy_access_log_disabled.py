"""F_A4: the committed edge config keeps access logging OFF.

Static and adapted-config contract: the committed ``deploy/Caddyfile`` disables
the admin API and does not configure per-server access loggers.

Executable error-log probe: run Caddy with the same global ``admin off`` +
``log { output discard }`` directives against an offline backend, hit a
sentinel-identifier path, and prove the identifier never reaches Caddy's
runtime error output.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

import httpx
import pytest

SENTINEL_ID = "pat_fa4_caddy_access_sentinel_1d7f"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _caddy_binary(repo_root: Path) -> str | None:
    configured = os.environ.get("NANTINGALE_CADDY_BINARY", "").strip()
    if configured:
        return configured
    local = repo_root / ".tools" / "caddy-2.11.4" / "caddy.exe"
    if local.is_file():
        return str(local)
    return shutil.which("caddy")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_committed_caddyfile_disables_admin_and_access_log():
    caddyfile = (_repo_root() / "deploy" / "Caddyfile").read_text(encoding="utf-8")

    assert "admin off" in caddyfile
    # Access logging is NOT ENABLED: exactly one `log {` block (the global
    # default/error logger) and no per-site `log { output discard }` blocks.
    assert caddyfile.count("log {") == 1
    assert caddyfile.count("output discard") == 1


def test_committed_caddyfile_adapts_without_server_access_loggers():
    repo_root = _repo_root()
    caddy = _caddy_binary(repo_root)
    if caddy is None:
        pytest.skip("Caddy binary not available; run with NANTINGALE_CADDY_BINARY")

    result = subprocess.run(
        [
            caddy,
            "adapt",
            "--config",
            str(repo_root / "deploy" / "Caddyfile"),
            "--adapter",
            "caddyfile",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    adapted = json.loads(result.stdout)
    assert adapted["admin"]["disabled"] is True
    assert (
        adapted["logging"]["logs"]["default"]["writer"]["output"]
        == "discard"
    )
    servers = adapted["apps"]["http"]["servers"]
    assert servers
    assert all("logs" not in server for server in servers.values())


def test_uvicorn_no_access_log_is_documented():
    readme = (_repo_root() / "README.md").read_text(encoding="utf-8")
    assert "--no-access-log" in readme


def test_global_error_log_discard_keeps_sentinel_path_out_of_caddy_output(tmp_path):
    repo_root = _repo_root()
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
        "\tlog {\n"
        "\t\toutput discard\n"
        "\t}\n"
        "}\n\n"
        f"http://127.0.0.1:{caddy_port} {{\n"
        "\tbind 127.0.0.1\n"
        f"\treverse_proxy 127.0.0.1:{offline_backend_port}\n"
        "}\n",
        encoding="utf-8",
    )

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
    try:
        deadline = time.monotonic() + 8
        ready = False
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            try:
                with socket.create_connection(("127.0.0.1", caddy_port), timeout=0.2):
                    ready = True
                    break
            except OSError:
                time.sleep(0.05)
        assert ready, "Caddy did not start within the probe timeout"

        with httpx.Client(trust_env=False, timeout=5) as client:
            response = client.get(
                f"http://127.0.0.1:{caddy_port}/api/patients/{SENTINEL_ID}/events"
            )
        # Offline backend: the request was definitely received by Caddy.
        assert response.status_code == 502
        time.sleep(0.2)
    finally:
        process.terminate()
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate(timeout=5)

    assert SENTINEL_ID not in stdout
    assert SENTINEL_ID not in stderr
