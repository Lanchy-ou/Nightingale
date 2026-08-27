from pathlib import Path


def test_caddy_allows_same_origin_microphone_and_blob_audio_only():
    caddy = (Path(__file__).resolve().parents[3] / "deploy" / "Caddyfile").read_text(
        encoding="utf-8"
    )

    assert 'Permissions-Policy "camera=(), microphone=(self), geolocation=()"' in caddy
    assert "media-src 'self' blob:" in caddy
