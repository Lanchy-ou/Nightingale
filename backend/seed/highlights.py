"""Deterministic highlight generator (seed path).

M5 contract (does NOT adjust frozen weights):
- explicit `as_of` computes `recency` (never hand-filled);
- `unresolved_task` comes from a real, non-terminal Task with matching
  Event/source provenance;
- `repeated_mentions` is computed from the SAME exact `entity_key` appearing in
  >=2 distinct Events (both sides recomputed);
- quotes anchor via deterministic string matching; a failed match drops the
  candidate (never fabricate a span, never count it toward repeated_mentions).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from sqlalchemy.orm import Session

from app.highlights import compute_score, is_recent, locate_span
from app.importance_learning import score_new_candidate
from app.models import Artifact, Event, Highlight
from app.provenance_binding import create_source_binding
from app.tasks import unresolved_task_exists

from . import fixture

SEED_AS_OF = datetime(2026, 8, 26, 12, 0)
_GENERATED_AT = datetime(2026, 8, 26, 12, 0)


def group_repeated_entity_keys(anchored: list[tuple[str, str]]) -> set[str]:
    """Return entity_keys present in >=2 distinct events (anchored candidates only)."""
    events_per_key: dict[str, set[str]] = defaultdict(set)
    for entity_key, event_id in anchored:
        if entity_key:
            events_per_key[entity_key].add(event_id)
    return {key for key, events in events_per_key.items() if len(events) >= 2}


from app.repeated_mentions import group_repeated_patient_entity_keys
from app.semantic_rules import interpret, repetition_key


def generate_highlights(db: Session) -> list[str]:
    # 1. anchor every candidate (drop failures).
    anchored: list[tuple[dict, dict, Event]] = []
    for cand in fixture.HIGHLIGHT_CANDIDATES:
        source = db.get(Artifact, cand["source_artifact_id"])
        if source is None:
            continue
        span = locate_span(source.content, cand["quote"])
        if span is None:
            continue
        event = db.get(Event, cand["event_id"])
        patient_id = cand.get("patient_id", fixture.PATIENT_ID)
        if event is None or event.patient_id != patient_id:
            continue
        anchored.append((cand, span, event))

    # 2. repeated_mentions across distinct events (anchored only).
    repeated_keys = group_repeated_patient_entity_keys(
        [
            (c.get("patient_id", fixture.PATIENT_ID), repetition_key(interpret(c["quote"], c.get("entity_type"), c["text"])), e.event_id)
            for c, _s, e in anchored
        ]
    )

    # 3. build highlights with computed structural flags + score.
    created: list[str] = []
    for cand, span, event in anchored:
        source = db.get(Artifact, cand["source_artifact_id"])
        source_version, quote_hash = create_source_binding(source, span)
        entity_key = cand.get("entity_key")
        patient_id = cand.get("patient_id", fixture.PATIENT_ID)
        semantics = interpret(cand["quote"], cand.get("entity_type"), cand["text"])
        key = repetition_key(semantics)
        repeated = bool(key and (patient_id, key) in repeated_keys)
        recency = is_recent(event.started_at, SEED_AS_OF)
        flags = {
            "recency": recency,
            "explicit_risk": bool(cand["feature_flags"].get("explicit_risk")),
            "unresolved_task": unresolved_task_exists(
                db,
                patient_id=patient_id,
                task_id=cand.get("task_id"),
            ),
            "clinician_confirmed": False,
            "symptom_change": bool(cand["feature_flags"].get("symptom_change")),
            "repeated_mentions": repeated,
        }
        learned = score_new_candidate(
            db,
            clinic_id=event.clinic_id,
            entity_type=cand.get("entity_type"),
            base_importance_score=compute_score(flags),
            feature_flags=flags,
        )
        db.add(
            Highlight(
                highlight_id=cand["highlight_id"],
                patient_id=patient_id,
                event_id=cand["event_id"],
                artifact_id=cand["artifact_id"],
                source_artifact_id=cand["source_artifact_id"],
                source_span=span,
                source_artifact_version=source_version,
                source_quote_sha256=quote_hash,
                task_id=cand.get("task_id"),
                text=cand["text"],
                risk_reason=cand["risk_reason"],
                feature_flags=flags,
                base_importance_score=learned.base_importance_score,
                adaptive_adjustment=learned.adaptive_adjustment,
                decay_adjustment=learned.decay_adjustment,
                importance_score=learned.importance_score,
                learning_metadata=learned.learning_metadata,
                status="suggested",
                status_history=[],
                created_at=_GENERATED_AT,
                updated_at=_GENERATED_AT,
                entity_type=cand.get("entity_type"),
                entity_key=entity_key,
                semantic_context=semantics,
                assertion_value=cand.get("assertion_value"),
                conflict_with_artifact_id=None,
                review_status=None,
            )
        )
        created.append(cand["highlight_id"])
    db.commit()
    return created
