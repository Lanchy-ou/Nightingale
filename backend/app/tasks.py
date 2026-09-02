"""D2 care-task state, provenance and Glance integration.

Task↔Glance mapping contract (review-hardened 2026-08-27):
- the mapping is ALWAYS explicit: `Highlight.task_id` points at exactly one
  Task and each Task is represented by at most one Highlight;
- an Event-only Task never flags unrelated Highlights in the same Event;
- a new unresolved Task without an existing task Highlight creates its own
  dedicated Highlight row, so it can always surface in Glance;
- terminal statuses (completed/cancelled) deterministically clear the
  unresolved weight on the Task's own Highlight only.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .highlights import compute_score
from .ids import stable_id
from .models import Artifact, Highlight, Task
from .provenance_binding import create_source_binding

UNRESOLVED_TASK_STATUSES = {"open", "in_progress", "reported_done"}

TASK_HIGHLIGHT_FLAGS = {
    "recency": True,
    "explicit_risk": False,
    "unresolved_task": True,
    "clinician_confirmed": False,
    "symptom_change": False,
    "repeated_mentions": False,
}


def task_transitions() -> dict[str, set[str]]:
    return {
        "open": {"in_progress", "reported_done", "cancelled"},
        "in_progress": {"reported_done", "cancelled"},
        "reported_done": {"completed", "cancelled"},
        "completed": set(),
        "cancelled": set(),
    }


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _span_offset(offset: object) -> tuple[int, int] | None:
    if not isinstance(offset, list) or len(offset) != 2:
        return None
    start, end = offset
    if not _is_int(start) or not _is_int(end):
        return None
    if start < 0 or end <= start:
        return None
    return start, end


def resolve_exact_span(content: object, span: object) -> str | None:
    """Resolve only a structurally valid, in-bounds, non-empty exact span.

    Hardened contract: ANY abnormal structure (content not a dict, segments/
    messages not lists, members not dicts, wrong member types, malformed span
    keys/offsets) fails closed and returns None — it never raises, so callers
    can translate it into a deterministic 422/404 instead of a 500.
    """
    if not isinstance(content, dict) or not isinstance(span, dict):
        return None
    if set(span) != {"kind", "index", "offset"}:
        return None
    offset = _span_offset(span.get("offset"))
    if offset is None:
        return None
    start, end = offset

    kind = span.get("kind")
    index = span.get("index")
    text: str | None = None

    if kind == "segment":
        if not _is_int(index):
            return None
        segments = content.get("segments")
        if segments is None:
            return None
        if not isinstance(segments, list):
            return None
        for member in segments:
            if not isinstance(member, dict):
                continue
            member_index = member.get("index")
            member_text = member.get("text")
            if _is_int(member_index) and member_index == index and isinstance(member_text, str):
                text = member_text
                break
    elif kind == "message":
        messages = content.get("messages")
        if not isinstance(messages, list):
            return None
        member = None
        if _is_int(index):
            if not (1 <= index <= len(messages)):
                return None
            member = messages[index - 1]
        elif isinstance(index, str):
            member = next(
                (
                    candidate
                    for candidate in messages
                    if isinstance(candidate, dict) and candidate.get("id") == index
                ),
                None,
            )
        else:
            return None
        if not isinstance(member, dict):
            return None
        member_text = member.get("text")
        if not isinstance(member_text, str):
            return None
        text = member_text
    elif kind == "section":
        if not isinstance(index, str):
            return None
        value = content.get(index)
        if not isinstance(value, str):
            return None
        text = value
    else:
        return None

    if text is None or end > len(text):
        return None
    quote = text[start:end]
    return quote if quote else None


def unresolved_task_exists(
    db: Session,
    *,
    patient_id: str,
    task_id: str | None,
) -> bool:
    """Explicit mapping only: `task_id` names the Task that owns the Highlight.

    Without a linked Task the flag is False — never inferred from the Event or
    from shared provenance. Event-only tasks therefore cannot leak their
    unresolved state onto unrelated Highlights.
    """
    if not task_id:
        return False
    task = db.get(Task, task_id)
    return bool(
        task is not None
        and task.patient_id == patient_id
        and task.status in UNRESOLVED_TASK_STATUSES
    )


def link_task_highlight(db: Session, task: Task) -> Highlight:
    """Establish the explicit Task↔Glance mapping for a newly created Task.

    - Exact provenance: adopt an existing UNOWNED task-type Highlight whose
      patient/event/source_artifact/source_span match EXACTLY (1:1 adoption;
      an owned Highlight can never be stolen by a later Task).
    - Otherwise (event-level provenance or no exact match): create a dedicated
      task Highlight row for this Task, so every unresolved Task can surface
      in Glance through its own row.
    """
    if task.source_artifact_id is not None and task.source_span is not None:
        candidates = db.scalars(
            select(Highlight)
            .where(
                Highlight.patient_id == task.patient_id,
                Highlight.event_id == task.event_id,
                Highlight.entity_type == "task",
                Highlight.source_artifact_id == task.source_artifact_id,
                Highlight.task_id.is_(None),
                Highlight.status != "rejected",
            )
            .order_by(Highlight.highlight_id)
        ).all()
        for candidate in candidates:
            if candidate.source_span == task.source_span:
                # Atomic claim: another creator may have selected the same
                # unowned row. Only the first conditional UPDATE wins; a loser
                # falls through and creates its own dedicated Highlight.
                result = db.execute(
                    update(Highlight)
                    .where(
                        Highlight.highlight_id == candidate.highlight_id,
                        Highlight.task_id.is_(None),
                        Highlight.status != "rejected",
                    )
                    .values(task_id=task.task_id)
                )
                if result.rowcount == 1:
                    db.refresh(candidate)
                    return candidate

    now = datetime.now()
    source = db.get(Artifact, task.source_artifact_id) if task.source_artifact_id else None
    source_version, quote_hash = create_source_binding(source, task.source_span)
    task_flags = {
        **TASK_HIGHLIGHT_FLAGS,
        "unresolved_task": task.status in UNRESOLVED_TASK_STATUSES,
    }
    dedicated_id = f"hl_{stable_id(task.task_id, 'task-highlight-v1')}"
    existing_dedicated = db.get(Highlight, dedicated_id)
    if existing_dedicated is not None:
        if existing_dedicated.task_id not in {None, task.task_id}:
            raise RuntimeError("Dedicated Task Highlight identity is already owned")
        existing_dedicated.task_id = task.task_id
        db.add(existing_dedicated)
        return existing_dedicated
    highlight = Highlight(
        highlight_id=dedicated_id,
        patient_id=task.patient_id,
        event_id=task.event_id,
        artifact_id=task.source_artifact_id,
        source_artifact_id=task.source_artifact_id,
        source_span=task.source_span,
        source_artifact_version=source_version,
        source_quote_sha256=quote_hash,
        task_id=task.task_id,
        text=task.title,
        risk_reason=(
            f"Unresolved care task ({task.assigned_role})"
            if task_flags["unresolved_task"]
            else f"Care task {task.status.replace('_', ' ')} ({task.assigned_role})"
        ),
        feature_flags=task_flags,
        base_importance_score=compute_score(task_flags),
        adaptive_adjustment=0,
        decay_adjustment=0,
        importance_score=compute_score(task_flags),
        learning_metadata={
            "feedback_key": "task",
            "review_count": 0,
            "positive_count": 0,
            "negative_count": 0,
            "raw_adjustment": 0,
            "cap_min": -2,
            "cap_max": 3,
            "reason": "non_ai_task_no_learning",
            "protection_applied": False,
        },
        status="suggested",
        status_history=[],
        created_at=now,
        updated_at=now,
        entity_type="task",
        entity_key=f"task:{task.task_id}",
        assertion_value=task.status,
        conflict_with_artifact_id=None,
        review_status=None,
    )
    db.add(highlight)
    return highlight


def recompute_task_highlights(db: Session, patient_id: str) -> None:
    """Deterministic write-through scoring; Glance reads remain computation-free.

    Each Task updates ONLY its own linked Highlight (`Highlight.task_id ==
    task.task_id`). Terminal statuses clear the unresolved weight on that
    Highlight alone. Nothing is ever inferred from the Event or from other
    tasks.
    """
    tasks = db.scalars(select(Task).where(Task.patient_id == patient_id)).all()
    for task in tasks:
        highlight = db.scalar(
            select(Highlight).where(Highlight.task_id == task.task_id)
        )
        if highlight is None:
            continue
        unresolved = task.status in UNRESOLVED_TASK_STATUSES
        dedicated = highlight.entity_key == f"task:{task.task_id}"
        desired_reason = (
            f"Unresolved care task ({task.assigned_role})"
            if unresolved
            else f"Care task {task.status.replace('_', ' ')} ({task.assigned_role})"
        )
        if (
            highlight.feature_flags.get("unresolved_task") == unresolved
            and (not dedicated or highlight.risk_reason == desired_reason)
        ):
            continue
        flags = {**highlight.feature_flags, "unresolved_task": unresolved}
        from .importance_learning import compose_score, requested_adaptive_adjustment

        rescored = compose_score(
            base_importance_score=compute_score(flags),
            adaptive_adjustment=requested_adaptive_adjustment(
                highlight.adaptive_adjustment, highlight.learning_metadata
            ),
            decay_adjustment=highlight.decay_adjustment,
            feature_flags=flags,
            status=highlight.status,
            review_status=highlight.review_status,
            learning_metadata=highlight.learning_metadata,
        )
        highlight.feature_flags = flags
        highlight.base_importance_score = rescored.base_importance_score
        highlight.adaptive_adjustment = rescored.adaptive_adjustment
        highlight.decay_adjustment = rescored.decay_adjustment
        highlight.importance_score = rescored.importance_score
        highlight.learning_metadata = rescored.learning_metadata
        if dedicated:
            highlight.risk_reason = desired_reason
            highlight.assertion_value = task.status
        highlight.updated_at = datetime.now()
        db.add(highlight)
