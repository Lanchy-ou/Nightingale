"""F_A4 real-process journeys: seed stdout and real uvicorn stderr.

These exercise the actual process sinks (not caplog): the seed script's stdout
must not reveal the database path, and a real `uvicorn --no-access-log` process
must keep synthetic sentinels out of stderr for an unhandled 500 and a 422.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

BACKEND = Path(__file__).resolve().parents[2]

PROBE_APP_SOURCE = """\
from app.main import app

def _raise_sensitive(patient_id: str):
    raise RuntimeError("FA4_PROCESS_SENTINEL_EXCEPTION_MSG")

app.add_api_route(
    "/api/patients/{patient_id}/__fa4_process_probe",
    _raise_sensitive,
    methods=["GET"],
    include_in_schema=False,
)
"""

SENTINEL_PATIENT_ID = "pat_fa4_process_sentinel_3c9d"
SENTINEL_422 = "FA4_PROCESS_SENTINEL_422_PASSWORD"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_seed_stdout_omits_database_path(tmp_path):
    db = tmp_path / "seed_stdout_probe.db"
    env = {**os.environ, "NANTINGALE_DB_URL": f"sqlite:///{db}"}
    proc = subprocess.run(
        [sys.executable, "-m", "seed.seed"],
        cwd=str(BACKEND),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 0, proc.stderr
    assert str(db) not in proc.stdout
    assert str(db) not in proc.stderr
    assert "configured database" in proc.stdout


def test_uvicorn_stderr_is_sentinel_free(tmp_path):
    probe = tmp_path / "fa4_probe_app.py"
    probe.write_text(PROBE_APP_SOURCE, encoding="utf-8")
    db = tmp_path / "uvicorn_stderr_probe.db"
    port = _free_port()
    stderr_path = tmp_path / "uvicorn.stderr.log"

    env = {**os.environ, "NANTINGALE_DB_URL": f"sqlite:///{db}", "PYTHONPATH": str(BACKEND)}
    env.pop("NANTINGALE_DEMO_AUTH", None)
    env.pop("NANTINGALE_SECURITY_MODE", None)

    stderr_handle = open(stderr_path, "wb")
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "fa4_probe_app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-access-log",
        ],
        cwd=str(tmp_path),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=stderr_handle,
    )
    try:
        base = f"http://127.0.0.1:{port}"
        # Readiness: the probe route always 500s once uvicorn is serving.
        deadline = time.monotonic() + 20
        ready = False
        with httpx.Client(base_url=base, timeout=2.0) as probe_client:
            while time.monotonic() < deadline:
                try:
                    if probe_client.get(
                        f"/api/patients/{SENTINEL_PATIENT_ID}/__fa4_process_probe"
                    ).status_code == 500:
                        ready = True
                        break
                except httpx.HTTPError:
                    time.sleep(0.1)
        assert ready, "uvicorn did not become ready in time"

        with httpx.Client(base_url=base, timeout=5.0) as client:
            r500 = client.get(f"/api/patients/{SENTINEL_PATIENT_ID}/__fa4_process_probe")
            assert r500.status_code == 500
            assert r500.json() == {
                "error": {"code": "internal_error", "message": "Internal server error"}
            }
            assert SENTINEL_PATIENT_ID not in r500.text

            r422 = client.post(
                "/api/auth/login",
                json={"email": "a@b.co", "password": [SENTINEL_422]},
            )
            assert r422.status_code == 422
            assert SENTINEL_422 not in r422.text
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
        stderr_handle.close()

    stderr = stderr_path.read_text(encoding="utf-8", errors="replace")

    # The three sentinels (path id, exception text, rejected 422 value) never
    # reach stderr, and neither does the server's duplicate raw traceback.
    assert SENTINEL_PATIENT_ID not in stderr
    assert "FA4_PROCESS_SENTINEL_EXCEPTION_MSG" not in stderr
    assert SENTINEL_422 not in stderr
    assert "Exception in ASGI application" not in stderr
    # The unhandled error record used the route TEMPLATE, not the raw path.
    assert "{patient_id}" in stderr
    assert "route_template" in stderr
    # `--no-access-log` suppresses the uvicorn access line (method + raw path).
    assert "GET /api/patients/" not in stderr
