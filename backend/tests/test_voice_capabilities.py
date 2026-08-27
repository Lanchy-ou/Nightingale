from pathlib import Path


def test_capabilities_are_authenticated_role_derived_and_path_free(
    clinician_client, staff_client, patient_client, admin_client, monkeypatch, tmp_path
):
    for filename in ("config.json", "model.bin", "tokenizer.json"):
        (tmp_path / filename).write_bytes(b"synthetic-model-probe")
    monkeypatch.setenv("NANTINGALE_VOICE_ENABLED", "true")
    monkeypatch.setenv("NANTINGALE_ASR_PROVIDER", "faster_whisper")
    monkeypatch.setenv("NANTINGALE_ASR_MODEL_PATH", str(tmp_path))

    expected = [
        (clinician_client, ["doctor_consult"]),
        (staff_client, ["nurse_consult"]),
        (patient_client, ["patient_session"]),
        (admin_client, []),
    ]
    for client, modes in expected:
        response = client.get("/api/voice/capabilities")
        assert response.status_code == 200
        body = response.json()
        assert body["enabled"] is True
        assert body["asr_ready"] is True
        assert body["allowed_modes"] == modes
        assert set(body["accepted_mime_types"]) == {
            "audio/webm",
            "audio/ogg",
            "audio/wav",
        }
        assert str(Path(tmp_path)) not in response.text


def test_disabled_voice_hides_mutations_and_product_capability(clinician_client, monkeypatch):
    monkeypatch.setenv("NANTINGALE_VOICE_ENABLED", "false")

    capability = clinician_client.get("/api/voice/capabilities")
    assert capability.status_code == 200
    assert capability.json()["enabled"] is False
    assert capability.json()["allowed_modes"] == []

    mutation = clinician_client.post(
        "/api/voice/captures",
        json={
            "idempotency_key": "disabled-probe",
            "patient_id": "pat_001",
            "capture_mode": "doctor_consult",
            "started_at": "2026-08-28T10:00:00",
        },
    )
    assert mutation.status_code == 404


def test_capabilities_require_authentication(client):
    assert client.get("/api/voice/capabilities").status_code == 401
