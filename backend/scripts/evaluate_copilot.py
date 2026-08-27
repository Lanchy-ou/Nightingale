"""Frozen local D4 Copilot evaluation (mock provider, no network)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from time import perf_counter

tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
tmp.close()
os.environ["NANTINGALE_DB_URL"] = f"sqlite:///{tmp.name}"
os.environ["NANTINGALE_DEMO_AUTH"] = "true"
os.environ["NANTINGALE_LLM_PROVIDER"] = "mock"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.highlights import extract_text, locate_span  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Artifact  # noqa: E402
from seed import fixture  # noqa: E402
from seed.seed import create_schema, seed  # noqa: E402

AI_TYPES = {"ai_doctor_consult_summary", "ai_nurse_consult_summary", "ai_patient_session_summary"}


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, int(len(ordered) * fraction + 0.999999) - 1))]


def _assert_exact(db, body: dict, item: dict, case_id: str) -> None:
    card = next((card for card in body["evidence"] if card["event_id"] == item["event_id"] and card["artifact_id"] == item["artifact_id"] and card["quote"] == item["quote"]), None)
    if card is None:
        raise SystemExit(f"FAIL {case_id}: expected Event/Artifact/quote absent")
    artifact = db.get(Artifact, card["artifact_id"])
    expected_span = locate_span(artifact.content, item["quote"]) if artifact is not None else None
    if expected_span is None or card["span"] != expected_span or extract_text(artifact.content, card["span"]) != item["quote"]:
        raise SystemExit(f"FAIL {case_id}: exact span mismatch actual={card['span']} expected={expected_span}")


def main() -> int:
    create_schema(engine)
    with SessionLocal() as db:
        seed(db)
    questions = json.loads((Path(__file__).resolve().parents[1] / "evals" / "copilot" / "questions.json").read_text(encoding="utf-8"))
    results: list[dict] = []
    latencies: list[float] = []
    draft_result: dict | None = None
    with TestClient(app, headers={"X-User-Id": fixture.USER_CLINICIAN_ID}) as client, SessionLocal() as db:
        for item in questions:
            payload = {"category": item["category"], "question": item["question"]}
            if item.get("draft_type"):
                payload["draft_type"] = item["draft_type"]
            started = perf_counter()
            response = client.post(f"/api/patients/{fixture.PATIENT_ID}/copilot/query", json=payload)
            elapsed_ms = (perf_counter() - started) * 1000
            latencies.append(elapsed_ms)
            if response.status_code != 200:
                raise SystemExit(f"FAIL {item['id']}: HTTP {response.status_code}")
            body = response.json()
            if len(body["evidence"]) > 12:
                raise SystemExit(f"FAIL {item['id']}: provider evidence bound exceeded")
            cards = {card["evidence_id"]: card for card in body["evidence"]}
            for expected in item["expected"]:
                _assert_exact(db, body, expected, item["id"])
            for excluded in item.get("exclude_text", []):
                if any(excluded.lower() in card["quote"].lower() for card in body["evidence"]):
                    raise SystemExit(f"FAIL {item['id']}: unrelated span returned")
            for claim in body["claims"]:
                if claim["status"] != "supported":
                    continue
                if len(claim["evidence_ids"]) != 1:
                    raise SystemExit(f"FAIL {item['id']}: factual claim must have one exact source")
                card = cards[claim["evidence_ids"][0]]
                artifact = db.get(Artifact, card["artifact_id"])
                if artifact is None or artifact.artifact_type in AI_TYPES or extract_text(artifact.content, card["span"]) != claim["text"]:
                    raise SystemExit(f"FAIL {item['id']}: unsupported or AI-self-cited fact")
            if item.get("supported_claims") is not None:
                if sum(claim["status"] == "supported" for claim in body["claims"]) != item["supported_claims"]:
                    raise SystemExit(f"FAIL {item['id']}: supported claim count")
            if item.get("inference_claims") is not None:
                if sum(claim["status"] == "inference" for claim in body["claims"]) != item["inference_claims"]:
                    raise SystemExit(f"FAIL {item['id']}: inference claim count")
            if item.get("expected_draft_type"):
                if body["draft"] is None or body["draft"]["artifact_type"] != item["expected_draft_type"]:
                    raise SystemExit(f"FAIL {item['id']}: clinician draft type authority")
                draft_result = body
            results.append({
                "id": item["id"], "status": body["status"], "claims": len(body["claims"]),
                "evidence": len(cards), "draft": body["draft"] is not None,
                "read_path_latency_ms": round(elapsed_ms, 3),
            })

        # Frozen AI self-citation rejection probe.
        db.add(Artifact(
            artifact_id="eval_ai_self_citation", event_id=fixture.EVT_REVIEW_0826,
            artifact_type="ai_doctor_consult_summary", author_role="system", author_id=None,
            content={"summary": "EVAL_AI_SELF_CITATION_SENTINEL diagnosis"},
            created_at=datetime(2026, 8, 26, 16, 0), version=1,
            provenance_pointer={"event_id": fixture.EVT_REVIEW_0826, "artifact_id": fixture.ART_FU_RAW},
        ))
        db.commit()
        rejected = client.post(f"/api/patients/{fixture.PATIENT_ID}/copilot/query", json={
            "category": "find_evidence", "question": "EVAL_AI_SELF_CITATION_SENTINEL",
        })
        if rejected.status_code != 200 or "EVAL_AI_SELF_CITATION_SENTINEL" in rejected.text:
            raise SystemExit("FAIL ai_self_citation: ungrounded AI summary surfaced")

        # Frozen confirmation-token forgery probe; must not create a Task.
        if draft_result is None:
            raise SystemExit("FAIL draft: missing frozen draft")
        draft = draft_result["draft"]
        source = next(card for card in draft_result["evidence"] if card["evidence_id"] == draft["evidence_ids"][0])
        forged = draft["confirmation_token"][:-1] + ("A" if draft["confirmation_token"][-1] != "A" else "B")
        denied = client.post(f"/api/events/{draft['event_id']}/tasks", json={
            "title": "Frozen token probe", "description": "must not persist",
            "assigned_role": "clinician", "assigned_user_id": None, "patient_visible": False,
            "due_at": None, "source_artifact_id": source["artifact_id"], "source_span": source["span"],
            "confirmation_token": forged,
        })
        if denied.status_code != 422:
            raise SystemExit("FAIL confirmation_token: forgery accepted")

    latency_report = {
        "metric": "COPILOT_READ_PATH",
        "samples": len(latencies),
        "p50_ms": round(_percentile(latencies, 0.50), 3),
        "p95_ms": round(_percentile(latencies, 0.95), 3),
        "max_ms": round(max(latencies), 3),
        "glance_latency_included": False,
    }
    print("D4_COPILOT_EVAL_PASS")
    print(json.dumps({
        "provider": "mock",
        "questions": results,
        "ai_self_citation_rejected": True,
        "forged_confirmation_rejected": True,
        "latency": latency_report,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
