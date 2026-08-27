"""E2 clinic-scoped, bounded and explainable Glance preference learning.

Only metadata from successful status compare-and-set writes is recorded. The
service is called on write paths; Glance GET never imports or queries it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .ids import new_id
from .models import Artifact, Event, Highlight, ImportanceFeedback
from .tasks import resolve_exact_span

FEEDBACK_KEYS = frozenset(
    {"symptom", "medication", "task", "risk", "allergy", "follow_up", "other"}
)
APPLIED_FEEDBACK_KEYS = FEEDBACK_KEYS - {"other"}
SIGNAL_VALUES = {
    "clinician": {"accepted": 1, "pinned": 2, "rejected": -1},
    "staff": {"accepted": 1, "pinned": 1, "rejected": -1},
}
MIN_ADJUSTMENT = -2
MAX_ADJUSTMENT = 3
MIN_DECAY_ADJUSTMENT = -2
MAX_DECAY_ADJUSTMENT = 0
AI_SUMMARY_TYPES = {
    "ai_doctor_consult_summary",
    "ai_nurse_consult_summary",
    "ai_patient_session_summary",
}


@dataclass(frozen=True)
class LearningResult:
    base_importance_score: int
    adaptive_adjustment: int
    decay_adjustment: int
    importance_score: int
    learning_metadata: dict


def feedback_key_for_entity_type(entity_type: str | None) -> str:
    return entity_type if entity_type in FEEDBACK_KEYS else "other"


def _expected_signal(actor_role: str, status: str) -> int | None:
    return SIGNAL_VALUES.get(actor_role, {}).get(status)


def record_feedback(
    db: Session,
    *,
    highlight: Highlight,
    event: Event,
    actor_id: str,
    actor_role: str,
    status: str,
    created_at: datetime | None = None,
    feedback_id: str | None = None,
) -> ImportanceFeedback | None:
    """Append one eligible feedback event after a successful status CAS.

    Eligibility is intentionally narrow: a system-authored AI summary plus an
    exact resolvable raw-source span. Task-only or malformed rows do not train.
    """
    signal = _expected_signal(actor_role, status)
    if signal is None or event.clinic_id is None:
        return None
    if highlight.patient_id != event.patient_id:
        return None

    summary = db.get(Artifact, highlight.artifact_id)
    source = db.get(Artifact, highlight.source_artifact_id)
    pointer = summary.provenance_pointer if summary is not None else None
    if (
        summary is None
        or summary.event_id != event.event_id
        or summary.author_role != "system"
        or summary.artifact_type not in AI_SUMMARY_TYPES
        or source is None
        or source.artifact_id == summary.artifact_id
        or source.event_id != event.event_id
        or source.artifact_type not in {"raw_conversation", "transcript"}
        or not isinstance(pointer, dict)
        or pointer.get("event_id") != event.event_id
        or pointer.get("artifact_id") != source.artifact_id
        or highlight.source_span is None
        or resolve_exact_span(source.content, highlight.source_span) is None
    ):
        return None

    row = ImportanceFeedback(
        feedback_id=feedback_id or new_id("ifb"),
        highlight_id=highlight.highlight_id,
        clinic_id=event.clinic_id,
        actor_id=actor_id,
        actor_role=actor_role,
        feedback_key=feedback_key_for_entity_type(highlight.entity_type),
        status=status,
        signal_value=signal,
        created_at=created_at or datetime.now(),
    )
    db.add(row)
    return row


def adjustment(db: Session, clinic_id: str, entity_type: str | None) -> tuple[int, dict]:
    """Aggregate latest valid feedback per actor/highlight within one clinic."""
    feedback_key = feedback_key_for_entity_type(entity_type)
    rows = db.scalars(
        select(ImportanceFeedback)
        .where(
            ImportanceFeedback.clinic_id == clinic_id,
            ImportanceFeedback.feedback_key == feedback_key,
        )
        .order_by(ImportanceFeedback.created_at, ImportanceFeedback.feedback_id)
    ).all()

    latest: dict[tuple[str, str], ImportanceFeedback] = {}
    for row in rows:
        expected = _expected_signal(row.actor_role, row.status)
        if expected is None or expected != row.signal_value:
            continue
        latest[(row.actor_id, row.highlight_id)] = row

    effective = list(latest.values())
    raw_adjustment = sum(row.signal_value for row in effective)
    if feedback_key not in APPLIED_FEEDBACK_KEYS:
        applied = 0
        reason = "unsupported_key_no_generalization"
    else:
        applied = max(MIN_ADJUSTMENT, min(MAX_ADJUSTMENT, raw_adjustment))
        reason = "clinic_latest_reviews"

    metadata = {
        "feedback_key": feedback_key,
        "review_count": len(effective),
        "positive_count": sum(row.signal_value > 0 for row in effective),
        "negative_count": sum(row.signal_value < 0 for row in effective),
        "raw_adjustment": raw_adjustment,
        "cap_min": MIN_ADJUSTMENT,
        "cap_max": MAX_ADJUSTMENT,
        "reason": reason,
        "protection_applied": False,
    }
    return applied, metadata


def is_protected(
    feature_flags: dict,
    *,
    status: str,
    review_status: str | None,
) -> bool:
    return bool(
        feature_flags.get("explicit_risk")
        or feature_flags.get("unresolved_task")
        or feature_flags.get("clinician_confirmed")
        or status == "pinned"
        or review_status == "needs_review"
    )


def requested_adaptive_adjustment(
    adaptive_adjustment: int, learning_metadata: dict | None
) -> int:
    """Recover the bounded learned value before any per-row protection floor."""
    raw = (learning_metadata or {}).get("raw_adjustment")
    if isinstance(raw, int) and not isinstance(raw, bool):
        return max(MIN_ADJUSTMENT, min(MAX_ADJUSTMENT, raw))
    return max(MIN_ADJUSTMENT, min(MAX_ADJUSTMENT, adaptive_adjustment))


def compose_score(
    *,
    base_importance_score: int,
    adaptive_adjustment: int,
    decay_adjustment: int,
    feature_flags: dict,
    status: str,
    review_status: str | None,
    learning_metadata: dict | None = None,
) -> LearningResult:
    """Apply E2's negative-learning floor without weakening hard protections."""
    metadata = dict(learning_metadata or {})
    applied_adaptive = max(
        MIN_ADJUSTMENT, min(MAX_ADJUSTMENT, adaptive_adjustment)
    )
    protected = is_protected(
        feature_flags, status=status, review_status=review_status
    )
    if applied_adaptive < 0 and protected:
        applied_adaptive = 0
        metadata["protection_applied"] = True
        metadata["reason"] = "protected_negative_adjustment_blocked"
    applied_decay = max(
        MIN_DECAY_ADJUSTMENT, min(MAX_DECAY_ADJUSTMENT, decay_adjustment)
    )
    if applied_decay < 0 and protected:
        applied_decay = 0
        metadata["protection_applied"] = True
        metadata["reason"] = "protected_negative_adjustment_blocked"
    final = base_importance_score + applied_adaptive + applied_decay
    return LearningResult(
        base_importance_score=base_importance_score,
        adaptive_adjustment=applied_adaptive,
        decay_adjustment=applied_decay,
        importance_score=final,
        learning_metadata=metadata,
    )


def score_new_candidate(
    db: Session,
    *,
    clinic_id: str,
    entity_type: str | None,
    base_importance_score: int,
    feature_flags: dict,
    status: str = "suggested",
    review_status: str | None = None,
) -> LearningResult:
    adaptive, metadata = adjustment(db, clinic_id, entity_type)
    return compose_score(
        base_importance_score=base_importance_score,
        adaptive_adjustment=adaptive,
        decay_adjustment=0,
        feature_flags=feature_flags,
        status=status,
        review_status=review_status,
        learning_metadata=metadata,
    )
