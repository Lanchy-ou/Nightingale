"""Deterministic highlight generator (M2 stub).

For each candidate in fixture.HIGHLIGHT_CANDIDATES:
  1. load the source artifact;
  2. locate the verbatim quote via deterministic string matching;
  3. if matched, compute importance_score from feature_flags and store the
     Highlight (status="suggested"). A failed match drops the candidate.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.highlights import compute_score, locate_span
from app.models import Artifact, Highlight

from . import fixture

_GENERATED_AT = datetime(2026, 8, 24, 12, 0)


def generate_highlights(db: Session) -> list[Highlight]:
    created: list[Highlight] = []
    for cand in fixture.HIGHLIGHT_CANDIDATES:
        source = db.get(Artifact, cand["source_artifact_id"])
        if source is None:
            continue  # dangling source => drop candidate
        span = locate_span(source.content, cand["quote"])
        if span is None:
            continue  # quote not found => never fabricate a span
        db.add(
            Highlight(
                highlight_id=cand["highlight_id"],
                patient_id=fixture.PATIENT_ID,
                event_id=cand["event_id"],
                artifact_id=cand["artifact_id"],
                source_artifact_id=cand["source_artifact_id"],
                source_span=span,
                text=cand["text"],
                risk_reason=cand["risk_reason"],
                feature_flags=cand["feature_flags"],
                importance_score=compute_score(cand["feature_flags"]),
                status="suggested",
                status_history=[],
                created_at=_GENERATED_AT,
                updated_at=_GENERATED_AT,
                entity_type=cand.get("entity_type"),
                entity_key=cand.get("entity_key"),
                assertion_value=cand.get("assertion_value"),
                conflict_with_artifact_id=None,
                review_status=None,
            )
        )
        created.append(cand["highlight_id"])
    db.commit()
    return db.query(Highlight).filter(Highlight.highlight_id.in_(created)).all() if created else []
