"""D4 bounded, evidence-validated clinician Copilot read path.

This module never writes clinical records.  It builds a small patient-scoped
candidate set, redacts it before the one LLMClient exit, and treats the model
answer as a proposal.  Every returned source fact is re-emitted from a
server-resolved exact span; provider text is never used as factual authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from .audit import add_audit
from .copilot_models import (
    CopilotClaimOut, CopilotDraftOut, CopilotEvidenceOut, CopilotProviderResult,
    CopilotQuery, CopilotResponse,
)
from .highlights import extract_text, locate_span
from .models import Artifact, Event, Highlight, Patient, Task, User
from .redaction import redact_content

MAX_EVIDENCE = 12
MAX_EVENTS = 3


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    event: Event
    artifact: Artifact
    span: dict
    quote: str
    review_required: bool

    def out(self) -> CopilotEvidenceOut:
        return CopilotEvidenceOut(
            evidence_id=self.evidence_id,
            event_id=self.event.event_id,
            event_type=self.event.event_type,
            event_time=self.event.started_at,
            artifact_id=self.artifact.artifact_id,
            artifact_type=self.artifact.artifact_type,
            author_role=self.artifact.author_role,
            span=self.span,
            quote=self.quote,
            review_required=self.review_required,
        )


def _known_names(db: Session, patient: Patient) -> list[str]:
    names = [patient.name]
    names.extend(user.name for user in db.scalars(select(User).where(User.clinic_id == patient.clinic_id)))
    return names


def _event_window(db: Session, patient_id: str, category: str) -> list[Event]:
    events = db.scalars(
        select(Event).where(Event.patient_id == patient_id).order_by(Event.started_at.desc(), Event.event_id.desc())
    ).all()
    # What changed is intentionally a two-event comparison. Other categories
    # receive at most three recent events; this is bounded retrieval, never a
    # whole-history RAG payload.
    return events[:2 if category == "what_changed" else MAX_EVENTS]


def _artifact_quotes(artifact: Artifact) -> list[tuple[dict, str]]:
    values: list[str] = []
    for item in artifact.content.get("segments", []):
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            values.append(item["text"])
    for item in artifact.content.get("messages", []):
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            values.append(item["text"])
    values.extend(value for value in artifact.content.values() if isinstance(value, str))
    out: list[tuple[dict, str]] = []
    for value in values:
        quote = value.strip()
        if not quote:
            continue
        span = locate_span(artifact.content, quote)
        if span is not None and extract_text(artifact.content, span) == quote:
            out.append((span, quote))
    return out


def _relevant_artifacts(db: Session, events: list[Event], category: str, question: str) -> list[tuple[Event, Artifact]]:
    event_ids = [event.event_id for event in events]
    if not event_ids:
        return []
    artifacts = db.scalars(
        select(Artifact).where(Artifact.event_id.in_(event_ids)).order_by(Artifact.created_at.desc(), Artifact.artifact_id)
    ).all()
    by_event = {event.event_id: event for event in events}
    rows = [(by_event[artifact.event_id], artifact) for artifact in artifacts if artifact.event_id in by_event]
    if category != "find_evidence" or not question.strip():
        return rows
    terms = [part.lower() for part in question.split() if len(part) >= 3][:6]
    if not terms:
        return rows
    return [
        (event, artifact) for event, artifact in rows
        if any(term in " ".join(text for _span, text in _artifact_quotes(artifact)).lower() for term in terms)
    ]


def build_evidence(db: Session, patient: Patient, query: CopilotQuery) -> list[Evidence]:
    events = _event_window(db, patient.patient_id, query.category)
    review_by_source = {
        row.source_artifact_id
        for row in db.scalars(select(Highlight).where(Highlight.patient_id == patient.patient_id, Highlight.review_status == "needs_review"))
        if row.source_artifact_id
    }
    evidence: list[Evidence] = []
    seen: set[tuple[str, str]] = set()

    def append_exact(event: Event | None, artifact: Artifact | None, span: dict | None) -> None:
        if (
            event is None or artifact is None or span is None
            or event.patient_id != patient.patient_id
            or event.clinic_id != patient.clinic_id
            or artifact.event_id != event.event_id
        ):
            return
        quote = extract_text(artifact.content, span)
        key = (artifact.artifact_id, str(span))
        if quote is None or key in seen or len(evidence) >= MAX_EVIDENCE:
            return
        seen.add(key)
        evidence.append(Evidence(
            evidence_id=f"ev_{len(evidence) + 1}", event=event, artifact=artifact, span=span,
            quote=quote, review_required=artifact.artifact_id in review_by_source,
        ))

    if query.category == "what_matters_now":
        # Read existing precomputed Glance and the first-class Task model;
        # neither is re-ranked by Copilot. Only Task rows with exact existing
        # source spans can become a factual Copilot card.
        highlights = db.scalars(select(Highlight).where(
            Highlight.patient_id == patient.patient_id, Highlight.status != "rejected"
        )).all()
        for row in sorted(highlights, key=lambda item: (item.status != "pinned", -item.importance_score, item.highlight_id))[:5]:
            append_exact(db.get(Event, row.event_id), db.get(Artifact, row.source_artifact_id), row.source_span)
        tasks = db.scalars(select(Task).where(
            Task.patient_id == patient.patient_id,
            Task.status.in_(("open", "in_progress", "reported_done")),
        )).all()
        for task in tasks:
            append_exact(db.get(Event, task.event_id), db.get(Artifact, task.source_artifact_id), task.source_span)
    for event, artifact in _relevant_artifacts(db, events, query.category, query.question):
        for span, quote in _artifact_quotes(artifact):
            key = (artifact.artifact_id, str(span))
            if key in seen:
                continue
            seen.add(key)
            evidence.append(Evidence(
                evidence_id=f"ev_{len(evidence) + 1}", event=event, artifact=artifact, span=span,
                quote=quote, review_required=artifact.artifact_id in review_by_source,
            ))
            if len(evidence) >= MAX_EVIDENCE:
                return evidence
    return evidence


def _bounded_payload(query: CopilotQuery, evidence: list[Evidence], patient: Patient, db: Session):
    content = {
        "category": query.category,
        # The question is data, never a system instruction. It is only useful
        # to Find evidence / Draft action and is bounded by the request schema.
        "question": query.question.strip(),
        "evidence": [
            {"evidence_id": item.evidence_id, "event_time": item.event.started_at.isoformat(),
             "artifact_type": item.artifact.artifact_type, "author_role": item.artifact.author_role,
             "quote": item.quote}
            for item in evidence
        ],
    }
    return redact_content(content, _known_names(db, patient)).redacted


def _validated_claims(result: CopilotProviderResult, evidence: dict[str, Evidence]) -> list[CopilotClaimOut]:
    claims: list[CopilotClaimOut] = []
    for proposal in result.claims:
        valid_ids = [item for item in proposal.evidence_ids if item in evidence]
        if proposal.status == "supported" and valid_ids:
            # A factual claim may only be the exact server-resolved source text.
            # One source fact per claim prevents a valid card from lending
            # authority to unrelated free-form prose.
            claims.extend(CopilotClaimOut(text=evidence[item].quote, status="supported", evidence_ids=[item]) for item in valid_ids)
        elif proposal.status == "inference" and valid_ids:
            claims.append(CopilotClaimOut(
                text="Inference from the cited record excerpts; clinician review required.",
                status="inference", evidence_ids=valid_ids,
            ))
        else:
            claims.append(CopilotClaimOut(text="Unknown: no verified evidence was returned.", status="unknown", evidence_ids=[]))
    return claims[:6]


def _validated_draft(result: CopilotProviderResult, evidence: dict[str, Evidence]) -> CopilotDraftOut | None:
    proposal = result.draft
    if proposal is None:
        return None
    ids = [item for item in proposal.evidence_ids if item in evidence]
    if not ids:
        return None
    source = evidence[ids[0]]
    # The provider cannot choose an actor, patient, arbitrary event, endpoint,
    # task completion, or free-text clinical fact. The preview is a safe,
    # editable template tied to one verified source and still has no write path.
    if proposal.artifact_type == "clinician_note":
        content = {"assessment": f"AI-generated draft based on: {source.quote}", "plan": "Clinician review and edit required before signing."}
        visible = False
    elif proposal.artifact_type == "patient_instruction":
        content = {"instruction": "AI-generated draft: clinician must review and rewrite before sharing with the patient."}
        visible = True
    else:
        content = {"title": "Review follow-up from cited record", "description": "AI-generated draft; clinician review required before creating this task."}
        visible = False
    return CopilotDraftOut(
        artifact_type=proposal.artifact_type, event_id=source.event.event_id,
        evidence_ids=ids, content=content, patient_visible=visible,
    )


def answer_query(db: Session, patient: Patient, query: CopilotQuery, client, provider_name: str, actor_id: str) -> CopilotResponse:
    started = perf_counter()
    evidence_list = build_evidence(db, patient, query)
    evidence = {item.evidence_id: item for item in evidence_list}
    status = "ok"
    limitations = ["Copilot used a bounded recent-record context; it does not search the full history or external sources."]
    try:
        result = client.copilot(_bounded_payload(query, evidence_list, patient, db), query.category)
        claims = _validated_claims(result, evidence)
        draft = _validated_draft(result, evidence) if query.category == "draft_action" else None
    except Exception:
        # Provider failure is explicit. Never fill this with a synthetic clinical answer.
        status = "unavailable"
        claims = []
        draft = None
        limitations.append("Copilot is unavailable; no source-based answer was generated.")
    if not evidence_list:
        limitations.append("No exact, authorized evidence was found in the bounded record context.")
    if any(item.review_required for item in evidence_list):
        limitations.append("Some cited evidence is marked for clinical review and must not be silently merged into an assessment.")
    add_audit(
        db, actor_id=actor_id, actor_role="clinician", action="copilot_query", target_type="patient",
        target_id=patient.patient_id, clinic_id=patient.clinic_id, patient_id=patient.patient_id,
        details={"category": query.category, "provider": provider_name, "success": status == "ok",
                 "latency_ms": round((perf_counter() - started) * 1000), "evidence_count": len(evidence_list)},
    )
    db.commit()
    return CopilotResponse(category=query.category, status=status, claims=claims,
                           evidence=[item.out() for item in evidence_list], limitations=limitations, draft=draft)
