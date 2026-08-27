"""D2 care-task state, provenance and Glance integration."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .highlights import compute_score
from .models import Highlight, Task

UNRESOLVED_TASK_STATUSES = {"open", "in_progress", "reported_done"}
def task_transitions() -> dict[str, set[str]]:
    return {
        "open": {"in_progress", "reported_done", "cancelled"},
        "in_progress": {"reported_done", "cancelled"},
        "reported_done": {"completed", "cancelled"},
        "completed": set(),
        "cancelled": set(),
    }


def resolve_exact_span(content: dict, span: dict) -> str | None:
    """Resolve only a structurally valid, in-bounds, non-empty exact span."""
    if not isinstance(span, dict) or set(span) != {"kind", "index", "offset"}:
        return None
    offset = span.get("offset")
    if (
        not isinstance(offset, list)
        or len(offset) != 2
        or any(not isinstance(value, int) or isinstance(value, bool) for value in offset)
    ):
        return None
    start, end = offset
    if start < 0 or end <= start:
        return None

    text: str | None = None
    kind = span.get("kind")
    index = span.get("index")
    if kind == "segment" and isinstance(index, int) and not isinstance(index, bool):
        for segment in content.get("segments", []):
            if segment.get("index") == index and isinstance(segment.get("text"), str):
                text = segment["text"]
                break
    elif kind == "message" and isinstance(index, int) and not isinstance(index, bool):
        messages = content.get("messages", [])
        if 1 <= index <= len(messages) and isinstance(messages[index - 1].get("text"), str):
            text = messages[index - 1]["text"]
    elif kind == "section" and isinstance(index, str):
        value = content.get(index)
        if isinstance(value, str):
            text = value
    if text is None or end > len(text):
        return None
    quote = text[start:end]
    return quote if quote else None


def unresolved_task_exists(
    db: Session,
    *,
    patient_id: str,
    event_id: str,
    source_artifact_id: str | None,
    source_span: dict | None,
) -> bool:
    tasks = db.scalars(
        select(Task).where(
            Task.patient_id == patient_id,
            Task.event_id == event_id,
            Task.status.in_(UNRESOLVED_TASK_STATUSES),
        )
    ).all()
    for task in tasks:
        if task.source_artifact_id is None:
            return True
        if task.source_artifact_id == source_artifact_id and task.source_span == source_span:
            return True
    return False


def recompute_task_highlights(db: Session, patient_id: str) -> None:
    """Write-through deterministic scoring; Glance reads remain computation-free."""
    highlights = db.scalars(
        select(Highlight).where(
            Highlight.patient_id == patient_id,
            Highlight.entity_type == "task",
        )
    ).all()
    for highlight in highlights:
        unresolved = unresolved_task_exists(
            db,
            patient_id=patient_id,
            event_id=highlight.event_id,
            source_artifact_id=highlight.source_artifact_id,
            source_span=highlight.source_span,
        )
        flags = {**highlight.feature_flags, "unresolved_task": unresolved}
        highlight.feature_flags = flags
        highlight.importance_score = compute_score(flags)
