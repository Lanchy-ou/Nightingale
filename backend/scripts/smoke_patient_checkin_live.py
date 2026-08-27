"""Current synthetic DeepSeek smoke for the bounded Patient Check-in path."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

handle = tempfile.NamedTemporaryFile(prefix="nantingale-checkin-live-", suffix=".db", delete=False)
handle.close()
temp_path = Path(handle.name).resolve()
if temp_path.parent != Path(tempfile.gettempdir()).resolve():
    raise RuntimeError("temporary DB path escaped the system temp directory")

os.environ["NANTINGALE_DB_URL"] = f"sqlite:///{temp_path}"
os.environ["NANTINGALE_DEMO_AUTH"] = "true"
os.environ["NANTINGALE_LLM_PROVIDER"] = "deepseek"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal, engine  # noqa: E402
from app.highlights import extract_text  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Artifact, Highlight, PatientCheckInMessage  # noqa: E402
from seed import fixture  # noqa: E402
from seed.seed import create_schema, seed  # noqa: E402


def main() -> None:
    create_schema(engine)
    with SessionLocal() as db:
        seed(db)

    headers = {"X-User-Id": fixture.USER_PATIENT_ID}
    with TestClient(app, headers=headers) as client:
        session_id = "checkin-live-synthetic-001"
        started = client.post(
            f"/api/patients/{fixture.PATIENT_ID}/check-ins",
            json={"session_id": session_id},
        )
        started.raise_for_status()
        turn = client.post(
            f"/api/check-ins/{session_id}/messages",
            json={
                "message_id": "patient-live-synthetic-001",
                "intent": "answer",
                "text": "My synthetic headache is better today, about 3 out of 10, but nausea is still present.",
            },
        )
        turn.raise_for_status()
        ai = next(
            message for message in turn.json()["messages"]
            if message["response_to_message_id"] == "patient-live-synthetic-001"
        )
        if ai["generation_method"] != "deepseek" or ai["degraded"]:
            with SessionLocal() as db:
                metadata = db.get(
                    PatientCheckInMessage,
                    next(
                        message["message_id"] for message in turn.json()["messages"]
                        if message["response_to_message_id"] == "patient-live-synthetic-001"
                    ),
                ).generation_metadata
            raise RuntimeError(
                "live Check-in turn did not complete through DeepSeek: "
                f"method={metadata.get('method')} degraded={metadata.get('degraded')} "
                f"fallback_reason={metadata.get('fallback_reason')}"
            )
        ended = client.post(
            f"/api/check-ins/{session_id}/messages",
            json={
                "message_id": "patient-live-synthetic-end-001",
                "intent": "no_more",
                "text": "",
            },
        )
        ended.raise_for_status()
        submitted = client.post(
            f"/api/check-ins/{session_id}/submit",
            json={"expected_status": "awaiting_confirmation"},
        )
        submitted.raise_for_status()
        event_id = submitted.json()["event_id"]

    with SessionLocal() as db:
        raw = db.scalar(select(Artifact).where(
            Artifact.event_id == event_id, Artifact.artifact_type == "raw_conversation"
        ))
        summary = db.scalar(select(Artifact).where(
            Artifact.event_id == event_id,
            Artifact.artifact_type == "ai_patient_session_summary",
        ))
        if summary is None or summary.generation_metadata.get("method") != "deepseek":
            metadata = summary.generation_metadata if summary is not None else {}
            raise RuntimeError(
                "live Check-in summary did not complete through DeepSeek: "
                f"method={metadata.get('method')} degraded={metadata.get('degraded')} "
                f"fallback_reason={metadata.get('fallback_reason')}"
            )
        highlights = db.scalars(select(Highlight).where(Highlight.event_id == event_id)).all()
        if any(
            not isinstance(highlight.source_span.get("index"), str)
            or not extract_text(raw.content, highlight.source_span)
            for highlight in highlights
        ):
            raise RuntimeError("live Check-in Highlight provenance did not resolve")
        print("CHECKIN_LIVE_DEEPSEEK_PASS")
        print(f"turn_method={ai['generation_method']}")
        print(f"summary_method={summary.generation_metadata.get('method')}")
        print(f"exact_patient_message_highlights={len(highlights)}")

if __name__ == "__main__":
    try:
        main()
    finally:
        engine.dispose()
        temp_path.unlink(missing_ok=True)
