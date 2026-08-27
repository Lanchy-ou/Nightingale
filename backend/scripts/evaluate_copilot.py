"""Frozen, local D4 Copilot smoke evaluation (mock provider only).

This reports the read-path result separately from Glance performance and makes
no network call. It checks four frozen query categories and the invariant that
every supported claim equals an exact server-resolved evidence quote.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
tmp.close()
os.environ["NANTINGALE_DB_URL"] = f"sqlite:///{tmp.name}"
os.environ["NANTINGALE_DEMO_AUTH"] = "true"
os.environ["NANTINGALE_LLM_PROVIDER"] = "mock"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from app.highlights import extract_text  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Artifact  # noqa: E402
from seed import fixture  # noqa: E402
from seed.seed import create_schema, seed  # noqa: E402


def main() -> int:
    create_schema(engine)
    with SessionLocal() as db:
        seed(db)
    questions = json.loads((Path(__file__).resolve().parents[1] / "evals" / "copilot" / "questions.json").read_text(encoding="utf-8"))
    results = []
    with TestClient(app, headers={"X-User-Id": fixture.USER_CLINICIAN_ID}) as client, SessionLocal() as db:
        for item in questions:
            response = client.post(f"/api/patients/{fixture.PATIENT_ID}/copilot/query", json={"category": item["category"], "question": item["question"]})
            if response.status_code != 200:
                raise SystemExit(f"FAIL {item['id']}: HTTP {response.status_code}")
            body = response.json()
            cards = {card["evidence_id"]: card for card in body["evidence"]}
            for claim in body["claims"]:
                if claim["status"] != "supported":
                    continue
                if len(claim["evidence_ids"]) != 1:
                    raise SystemExit(f"FAIL {item['id']}: multi/empty factual evidence")
                card = cards[claim["evidence_ids"][0]]
                artifact = db.get(Artifact, card["artifact_id"])
                if artifact is None or extract_text(artifact.content, card["span"]) != claim["text"]:
                    raise SystemExit(f"FAIL {item['id']}: unresolved factual evidence")
            results.append({"id": item["id"], "status": body["status"], "claims": len(body["claims"]), "evidence": len(cards), "draft": body["draft"] is not None})
    print("D4_COPILOT_EVAL_PASS")
    print(json.dumps({"provider": "mock", "questions": results, "glance_latency_included": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
