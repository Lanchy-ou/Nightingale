"""AI generation orchestration (M4).

Order: redaction -> provider/mock -> extraction -> placeholder restore ->
deterministic quote anchoring -> bounded conflict -> deterministic scoring.

No HTTP and no RBAC live here; the caller owns transactions and authorization.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from .conflicts import clinical_assertion_sources, find_conflict
from .deterministic_pipeline import build_fallback
from .extraction import validate_candidate
from .highlights import compute_score, extract_text, locate_span
from .importance_learning import (
    compose_score,
    requested_adaptive_adjustment,
    score_new_candidate,
)
from .llm_client import (
    InvalidOutputError,
    LLMClient,
    ProviderProtocolError,
    ProviderUnavailableError,
)
from .models import Artifact, Event, Highlight, Patient, User
from .provenance_binding import create_source_binding
from .redaction import redact_content, restore_placeholders, unresolved_placeholders

logger = logging.getLogger("nantingale.ai_pipeline")


@dataclass
class AnchoredCandidate:
    text: str
    risk_reason: str
    entity_type: str
    entity_key: str
    assertion_value: str | None
    span: dict
    feature_flags: dict
    score: int
    review_status: str | None
    conflict_with_artifact_id: str | None


@dataclass
class PipelineOutput:
    summary_content: dict
    provenance_pointer: dict
    candidates: list[AnchoredCandidate]
    method: str
    degraded: bool
    fallback_reason: str | None
    redaction_counts: dict
    recompute_existing: list[str]


def _known_names(db: Session, patient_id: str, clinic_id: str) -> list[str]:
    names: list[str] = []
    patient = db.get(Patient, patient_id)
    if patient is not None:
        names.append(patient.name)
    for u in db.scalars(select(User).where(User.clinic_id == clinic_id)).all():
        names.append(u.name)
    return names


def _anchor(raw: dict, result, mapping: dict, use_restore: bool):
    """Return (anchored, dropped, reason). A non-None reason discards the result."""
    if use_restore:
        fields = [result.summary]
        for candidate in result.candidates:
            fields.extend(
                [
                    candidate.text,
                    candidate.quote,
                    candidate.risk_reason,
                    candidate.assertion_value or "",
                ]
            )
        if any(unresolved_placeholders(value, mapping) for value in fields):
            return [], 0, "placeholder_error"

        result.summary = restore_placeholders(result.summary, mapping)
        if result.chief_complaint is not None:
            if unresolved_placeholders(result.chief_complaint, mapping):
                return [], 0, "placeholder_error"
            result.chief_complaint = restore_placeholders(result.chief_complaint, mapping)
        for candidate in result.candidates:
            candidate.text = restore_placeholders(candidate.text, mapping)
            candidate.risk_reason = restore_placeholders(candidate.risk_reason, mapping)
            if candidate.assertion_value is not None:
                candidate.assertion_value = restore_placeholders(candidate.assertion_value, mapping)

    validated = [c for c in result.candidates if validate_candidate(c) is not None]
    anchored: list = []
    dropped = 0
    for c in validated:
        quote = c.quote
        if use_restore:
            quote = restore_placeholders(quote, mapping)
        span = locate_span(raw, quote)
        if span is None or extract_text(raw, span) != quote:
            dropped += 1
            continue
        anchored.append((c, span))

    if len(validated) > 0 and len(anchored) / len(validated) < 0.70:
        return [], dropped, "anchor_drop_rate"
    return anchored, dropped, None


def run_pipeline(
    db: Session,
    event: Event,
    source_artifact: Artifact,
    flow_type: str,
    as_of,
    client: LLMClient,
    client_name: str,
) -> PipelineOutput:
    raw = source_artifact.content
    redaction = redact_content(raw, _known_names(db, event.patient_id, event.clinic_id))
    redacted = redaction.redacted
    mapping = redaction.placeholder_mapping

    method = client_name
    degraded = False
    fallback_reason = None
    result = None

    # 1. primary attempt
    try:
        result = client.summarize(redacted, flow_type)
    except ProviderUnavailableError:
        fallback_reason = "provider_missing"
    except ProviderProtocolError:
        fallback_reason = "provider_error"
    except InvalidOutputError:
        fallback_reason = "invalid_output"
    except Exception as e:  # timeout / network / any unexpected provider error
        logger.warning("provider error: %s", type(e).__name__)
        fallback_reason = "provider_error"

    anchored: list = []
    if result is not None and fallback_reason is None:
        anchored, _, reason = _anchor(raw, result, mapping, use_restore=True)
        if reason is not None:
            fallback_reason = reason
            anchored = []

    # 2. deterministic fallback (fixture-independent)
    if fallback_reason is not None:
        method = "deterministic_fallback"
        degraded = True
        fb = build_fallback(raw, flow_type)
        result = fb
        anchored, _, _ = _anchor(raw, fb, {}, use_restore=False)

    # 3. flags + conflict + score
    clinician_records = clinical_assertion_sources(db, event.patient_id)
    allergy_records = clinical_assertion_sources(
        db, event.patient_id, include_staff_and_nurse=True
    )
    candidates: list[AnchoredCandidate] = []
    recompute_existing: list[str] = []
    for c, span in anchored:
        existing = db.scalars(
            select(Highlight).where(
                Highlight.entity_key == c.entity_key,
                Highlight.event_id != event.event_id,
            )
        ).all()
        repeated = len(existing) > 0
        recency = (as_of - event.started_at).days <= 7
        flags = {
            "recency": recency,
            "explicit_risk": bool(c.explicit_risk),
            "unresolved_task": False,
            "clinician_confirmed": False,
            "symptom_change": bool(c.symptom_change),
            "repeated_mentions": repeated,
        }
        review_status = None
        conflict_with = None
        risk_reason = c.risk_reason
        conflict = find_conflict(
            c.entity_key,
            c.assertion_value,
            allergy_records if c.entity_type == "allergy" else clinician_records,
            candidate_entity_type=c.entity_type,
            candidate_text=c.text,
            candidate_quote=c.quote,
        )
        if conflict is not None:
            conflict_with, _ = conflict
            review_status = "needs_review"
            risk_reason = (
                "allergy statements conflict across patient and clinical records; review required"
                if c.entity_type == "allergy"
                else "conflicts with clinician-authored record; review required"
            )

        candidates.append(
            AnchoredCandidate(
                text=c.text,
                risk_reason=risk_reason,
                entity_type=c.entity_type,
                entity_key=c.entity_key,
                assertion_value=c.assertion_value,
                span=span,
                feature_flags=flags,
                score=compute_score(flags),
                review_status=review_status,
                conflict_with_artifact_id=conflict_with,
            )
        )
        recompute_existing.extend(e.highlight_id for e in existing)

    summary_content = {
        "summary": result.summary,
        "chief_complaint": result.chief_complaint,
        "key_points": [a.text for a in candidates],
    }
    pointer = {"event_id": event.event_id, "artifact_id": source_artifact.artifact_id}
    if len(candidates) == 1:
        pointer["span"] = candidates[0].span

    return PipelineOutput(
        summary_content=summary_content,
        provenance_pointer=pointer,
        candidates=candidates,
        method=method,
        degraded=degraded,
        fallback_reason=fallback_reason,
        redaction_counts=redacted.redaction_counts,
        recompute_existing=recompute_existing,
    )


def persist_derived(
    db: Session,
    event: Event,
    source_artifact: Artifact,
    summary_type: str,
    output: PipelineOutput,
    actor_id: str,
    actor_role: str,
    provider: str | None,
    model: str | None,
) -> tuple[str, list[str]]:
    """Atomically persist AI summary + highlights (single transaction).

    AI summary author_role is always `system`; it never overwrites raw/clinician
    artifacts. IDs are stable-derived so retries are idempotent.
    """
    from datetime import datetime

    from .audit import add_audit
    from .ids import stable_id

    now = datetime.now()
    summary_id = f"art_{stable_id(source_artifact.artifact_id, summary_type)}"
    db.add(
        Artifact(
            artifact_id=summary_id,
            event_id=event.event_id,
            artifact_type=summary_type,
            author_role="system",
            author_id=None,
            content=output.summary_content,
            created_at=now,
            version=1,
            provenance_pointer=output.provenance_pointer,
            ingestion_key=None,
            generation_metadata={
                "method": output.method,
                "provider": provider,
                "model": model,
                "degraded": output.degraded,
                "fallback_reason": output.fallback_reason,
                "redaction_counts": output.redaction_counts,
                "source_artifact_id": source_artifact.artifact_id,
            },
        )
    )

    highlight_ids: list[str] = []
    for ac in output.candidates:
        quote = extract_text(source_artifact.content, ac.span)
        hid = f"hl_{stable_id(source_artifact.artifact_id, quote, ac.entity_key)}"
        source_version, quote_hash = create_source_binding(source_artifact, ac.span)
        learned = score_new_candidate(
            db,
            clinic_id=event.clinic_id,
            entity_type=ac.entity_type,
            base_importance_score=ac.score,
            feature_flags=ac.feature_flags,
            review_status=ac.review_status,
        )
        db.add(
            Highlight(
                highlight_id=hid,
                patient_id=event.patient_id,
                event_id=event.event_id,
                artifact_id=summary_id,
                source_artifact_id=source_artifact.artifact_id,
                source_span=ac.span,
                source_artifact_version=source_version,
                source_quote_sha256=quote_hash,
                text=ac.text,
                risk_reason=ac.risk_reason,
                feature_flags=ac.feature_flags,
                base_importance_score=learned.base_importance_score,
                adaptive_adjustment=learned.adaptive_adjustment,
                decay_adjustment=learned.decay_adjustment,
                importance_score=learned.importance_score,
                learning_metadata=learned.learning_metadata,
                status="suggested",
                status_history=[],
                created_at=now,
                updated_at=now,
                entity_type=ac.entity_type,
                entity_key=ac.entity_key,
                assertion_value=ac.assertion_value,
                conflict_with_artifact_id=ac.conflict_with_artifact_id,
                review_status=ac.review_status,
            )
        )
        highlight_ids.append(hid)

    for hid in output.recompute_existing:
        h = db.get(Highlight, hid)
        if h is not None and not h.feature_flags.get("repeated_mentions"):
            flags = {**h.feature_flags, "repeated_mentions": True}
            rescored = compose_score(
                base_importance_score=compute_score(flags),
                adaptive_adjustment=requested_adaptive_adjustment(
                    h.adaptive_adjustment, h.learning_metadata
                ),
                decay_adjustment=h.decay_adjustment,
                feature_flags=flags,
                status=h.status,
                review_status=h.review_status,
                learning_metadata=h.learning_metadata,
            )
            h.feature_flags = flags
            h.base_importance_score = rescored.base_importance_score
            h.adaptive_adjustment = rescored.adaptive_adjustment
            h.decay_adjustment = rescored.decay_adjustment
            h.importance_score = rescored.importance_score
            h.learning_metadata = rescored.learning_metadata
            h.updated_at = now

    add_audit(
        db,
        actor_id=actor_id,
        actor_role=actor_role,
        action="ai_fallback" if output.degraded else "ai_generate",
        target_type="artifact",
        target_id=summary_id,
        clinic_id=event.clinic_id,
        patient_id=event.patient_id,
        event_id=event.event_id,
    )
    try:
        db.commit()
    except Exception:
        # Raw ingestion was committed by the caller before this derived
        # transaction. Roll back every pending AI artifact/highlight/audit row
        # while preserving that raw source for a later retry.
        db.rollback()
        raise
    return summary_id, highlight_ids
