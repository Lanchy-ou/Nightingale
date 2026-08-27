"""Evidence-validated D4 clinician Copilot read path.

Provider output is never authority for patient, Event, draft type, visibility,
endpoint, authorship, or evidence. The server resolves exact spans first,
redacts the bounded provider payload, validates every returned evidence id,
and constructs any draft preview plus signed confirmation token itself.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from time import perf_counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from .audit import add_audit
from .checkin_visibility import checkin_event_is_clinically_visible
from .copilot_confirmation import issue_confirmation_token
from .copilot_models import (
    CopilotClaimOut,
    CopilotDraftOut,
    CopilotEvidenceOut,
    CopilotProviderResult,
    CopilotQuery,
    CopilotResponse,
)
from .highlights import extract_text, locate_span
from .models import Artifact, Event, Highlight, Patient, Task, User
from .redaction import redact_content

MAX_PROVIDER_EVIDENCE = 12
RECENT_EVENT_LIMIT = 3
RAW_SOURCE_TYPES = {"raw_conversation", "transcript"}
AI_SUMMARY_TYPES = {
    "ai_doctor_consult_summary",
    "ai_nurse_consult_summary",
    "ai_patient_session_summary",
}
SEARCH_STOP_WORDS = {
    "about", "and", "evidence", "find", "for", "from", "in", "of", "please",
    "record", "show", "the", "what", "with",
}


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
            record_time=self.artifact.created_at,
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


def _events(db: Session, patient_id: str) -> list[Event]:
    events = list(db.scalars(
        select(Event).where(Event.patient_id == patient_id).order_by(Event.started_at.desc(), Event.event_id.desc())
    ).all())
    return [event for event in events if checkin_event_is_clinically_visible(db, event.event_id)]


def _direct_quotes(
    artifact: Artifact, *, patient_messages_only: bool = False
) -> list[tuple[dict, str]]:
    if patient_messages_only:
        out: list[tuple[dict, str]] = []
        for position, item in enumerate(artifact.content.get("messages", []), start=1):
            if (
                not isinstance(item, dict)
                or item.get("speaker") != "patient"
                or not isinstance(item.get("text"), str)
            ):
                continue
            quote = item["text"].strip()
            if not quote:
                continue
            start = item["text"].find(quote)
            span = {
                "kind": "message",
                "index": item.get("id") if isinstance(item.get("id"), str) else position,
                "offset": [start, start + len(quote)],
            }
            if extract_text(artifact.content, span) == quote:
                out.append((span, quote))
        return out

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


def _resolved_quotes(db: Session, event: Event, artifact: Artifact) -> list[tuple[Artifact, dict, str]]:
    """Resolve an AI summary through raw source, or reject self-citation."""
    if artifact.artifact_type not in AI_SUMMARY_TYPES:
        return [
            (artifact, span, quote)
            for span, quote in _direct_quotes(
                artifact,
                patient_messages_only=(
                    event.event_type == "patient_checkin"
                    and artifact.artifact_type == "raw_conversation"
                ),
            )
        ]
    pointer = artifact.provenance_pointer or {}
    source_id = pointer.get("artifact_id")
    span = pointer.get("span")
    if not isinstance(source_id, str) or not isinstance(span, dict):
        return []
    source = db.get(Artifact, source_id)
    if source is None or source.event_id != event.event_id or source.artifact_type not in RAW_SOURCE_TYPES:
        return []
    quote = extract_text(source.content, span)
    resolved_span = locate_span(source.content, quote) if quote is not None else None
    if resolved_span is None or extract_text(source.content, resolved_span) != quote:
        return []
    return [(source, resolved_span, quote)]


def _event_quote_rows(db: Session, event: Event) -> list[tuple[Artifact, dict, str]]:
    artifacts = db.scalars(
        select(Artifact).where(Artifact.event_id == event.event_id).order_by(Artifact.created_at.desc(), Artifact.artifact_id)
    ).all()
    rows: list[tuple[Artifact, dict, str]] = []
    seen: set[tuple[str, str]] = set()
    for artifact in artifacts:
        for source, span, quote in _resolved_quotes(db, event, artifact):
            key = (source.artifact_id, repr(span))
            if key not in seen:
                seen.add(key)
                rows.append((source, span, quote))
    return rows


def _terms(text: str) -> set[str]:
    terms: set[str] = set()
    for token in re.findall(r"[a-z0-9]+", text.lower()):
        if token.isdigit() or (len(token) >= 3 and token not in SEARCH_STOP_WORDS):
            terms.add(token[:-1] if len(token) > 4 and token.endswith("s") else token)
    return terms


def _review_sources(db: Session, patient_id: str) -> set[str]:
    return {
        row.source_artifact_id
        for row in db.scalars(select(Highlight).where(
            Highlight.patient_id == patient_id,
            Highlight.review_status == "needs_review",
        ))
        if row.source_artifact_id
    }


def _make_evidence(rows: list[tuple[Event, Artifact, dict, str]], review_sources: set[str]) -> list[Evidence]:
    return [
        Evidence(
            evidence_id=f"ev_{index}", event=event, artifact=artifact, span=span,
            quote=quote, review_required=artifact.artifact_id in review_sources,
        )
        for index, (event, artifact, span, quote) in enumerate(rows[:MAX_PROVIDER_EVIDENCE], start=1)
    ]


def _what_changed_rows(db: Session, events: list[Event]) -> list[tuple[Event, Artifact, dict, str]]:
    event_rows = [(event, _event_quote_rows(db, event)) for event in events]
    event_rows = [(event, rows) for event, rows in event_rows if rows]
    if len(event_rows) < 2:
        return []
    latest_event, latest_rows = event_rows[0]
    for prior_event, prior_rows in event_rows[1:]:
        scored: list[tuple[int, tuple[Artifact, dict, str], tuple[Artifact, dict, str]]] = []
        for latest in latest_rows:
            for prior in prior_rows:
                scored.append((len(_terms(latest[2]) & _terms(prior[2])), latest, prior))
        scored.sort(key=lambda item: item[0], reverse=True)
        if scored and scored[0][0] > 0:
            _score, latest, prior = scored[0]
            return [
                (latest_event, latest[0], latest[1], latest[2]),
                (prior_event, prior[0], prior[1], prior[2]),
            ]
    return []


def _find_rows(db: Session, events: list[Event], question: str) -> list[tuple[Event, Artifact, dict, str]]:
    search_terms = _terms(question)
    if not search_terms:
        return []
    matches: list[tuple[Event, Artifact, dict, str]] = []
    # Search the complete authorized patient history locally, then bound only
    # the matching exact spans that can leave for the provider.
    for event in events:
        for artifact, span, quote in _event_quote_rows(db, event):
            if search_terms <= _terms(quote):
                matches.append((event, artifact, span, quote))
    return matches


def _append_exact(
    rows: list[tuple[Event, Artifact, dict, str]], patient: Patient,
    event: Event | None, artifact: Artifact | None, span: dict | None,
) -> None:
    if (
        event is None or artifact is None or span is None
        or event.patient_id != patient.patient_id
        or event.clinic_id != patient.clinic_id
        or artifact.event_id != event.event_id
    ):
        return
    quote = extract_text(artifact.content, span)
    if quote is not None:
        rows.append((event, artifact, span, quote))


def _matters_rows(db: Session, patient: Patient, events: list[Event]) -> list[tuple[Event, Artifact, dict, str]]:
    rows: list[tuple[Event, Artifact, dict, str]] = []
    highlights = db.scalars(select(Highlight).where(
        Highlight.patient_id == patient.patient_id,
        Highlight.status != "rejected",
    )).all()
    for highlight in sorted(highlights, key=lambda item: (item.status != "pinned", -item.importance_score, item.highlight_id))[:5]:
        _append_exact(rows, patient, db.get(Event, highlight.event_id), db.get(Artifact, highlight.source_artifact_id), highlight.source_span)
    tasks = db.scalars(select(Task).where(
        Task.patient_id == patient.patient_id,
        Task.status.in_(("open", "in_progress", "reported_done")),
    )).all()
    for task in tasks:
        _append_exact(rows, patient, db.get(Event, task.event_id), db.get(Artifact, task.source_artifact_id), task.source_span)
    for event in events[:RECENT_EVENT_LIMIT]:
        for artifact, span, quote in _event_quote_rows(db, event):
            if artifact.artifact_type in {"clinician_note", "patient_instruction"}:
                rows.append((event, artifact, span, quote))
    return rows


def build_evidence(db: Session, patient: Patient, query: CopilotQuery) -> list[Evidence]:
    events = _events(db, patient.patient_id)
    if query.category == "what_changed":
        rows = _what_changed_rows(db, events)
    elif query.category == "find_evidence":
        rows = _find_rows(db, events, query.question)
    elif query.category == "what_matters_now":
        rows = _matters_rows(db, patient, events)
    else:
        rows: list[tuple[Event, Artifact, dict, str]] = []
        for event in events[:RECENT_EVENT_LIMIT]:
            rows.extend((event, artifact, span, quote) for artifact, span, quote in _event_quote_rows(db, event))
    deduped: list[tuple[Event, Artifact, dict, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (row[1].artifact_id, repr(row[2]))
        if key not in seen:
            seen.add(key)
            deduped.append(row)
    return _make_evidence(deduped, _review_sources(db, patient.patient_id))


def _bounded_payload(query: CopilotQuery, evidence: list[Evidence], patient: Patient, db: Session):
    content = {
        "category": query.category,
        "question": query.question.strip(),
        "evidence": [
            {
                "evidence_id": item.evidence_id,
                "event_time": item.event.started_at.isoformat(),
                "artifact_type": item.artifact.artifact_type,
                "author_role": item.artifact.author_role,
                "quote": item.quote,
            }
            for item in evidence
        ],
    }
    return redact_content(content, _known_names(db, patient)).redacted


def _validated_claims(
    result: CopilotProviderResult, evidence: dict[str, Evidence], category: str,
) -> list[CopilotClaimOut]:
    if category == "what_changed":
        event_first: dict[str, Evidence] = {}
        for item in evidence.values():
            event_first.setdefault(item.event.event_id, item)
        selected = list(event_first.values())[:2]
        if len(selected) != 2:
            return [CopilotClaimOut(
                text="Unknown: two related Events with exact evidence were not found.",
                status="unknown", evidence_ids=[],
            )]
        claims = [
            CopilotClaimOut(text=item.quote, status="supported", evidence_ids=[item.evidence_id])
            for item in selected
        ]
        claims.append(CopilotClaimOut(
            text="Comparison inference: the later and earlier Event excerpts differ; clinician interpretation is required.",
            status="inference",
            evidence_ids=[item.evidence_id for item in selected],
        ))
        return claims

    claims: list[CopilotClaimOut] = []
    for proposal in result.claims:
        valid_ids = [item for item in proposal.evidence_ids if item in evidence]
        if proposal.status == "supported" and valid_ids:
            claims.extend(
                CopilotClaimOut(text=evidence[item].quote, status="supported", evidence_ids=[item])
                for item in valid_ids
            )
        elif proposal.status == "inference" and valid_ids:
            claims.append(CopilotClaimOut(
                text="Inference from the cited record excerpts; clinician review required.",
                status="inference", evidence_ids=valid_ids,
            ))
        else:
            claims.append(CopilotClaimOut(
                text="Unknown: no verified evidence was returned.", status="unknown", evidence_ids=[],
            ))
    if not claims and not evidence:
        claims.append(CopilotClaimOut(
            text="Unknown: no matching exact evidence was found.", status="unknown", evidence_ids=[],
        ))
    return claims[:6]


def _draft_preview(
    *, query: CopilotQuery, evidence: list[Evidence], patient: Patient, actor_id: str,
) -> CopilotDraftOut | None:
    if query.category != "draft_action" or query.draft_type is None or not evidence:
        return None
    source = evidence[0]
    if query.draft_type == "clinician_note":
        content = {
            "assessment": f"Draft based on exact source: {source.quote}",
            "plan": "Review and edit before signing.",
        }
        patient_visible = False
    elif query.draft_type == "patient_instruction":
        content = {
            "instruction": "EDIT REQUIRED: write clear patient-facing guidance.",
            "follow_up": "",
        }
        patient_visible = True
    else:
        content = {
            "title": "Review follow-up from cited record",
            "description": "Review and edit this task before creating it.",
        }
        patient_visible = False
    token_evidence = [{
        "event_id": source.event.event_id,
        "artifact_id": source.artifact.artifact_id,
        "span": source.span,
        "quote_sha256": hashlib.sha256(source.quote.encode("utf-8")).hexdigest(),
    }]
    token = issue_confirmation_token(
        actor_id=actor_id,
        clinic_id=patient.clinic_id,
        patient_id=patient.patient_id,
        event_id=source.event.event_id,
        draft_type=query.draft_type,
        evidence=token_evidence,
        template_content=content,
    )
    return CopilotDraftOut(
        artifact_type=query.draft_type,
        event_id=source.event.event_id,
        evidence_ids=[source.evidence_id],
        content=content,
        patient_visible=patient_visible,
        confirmation_token=token,
    )


def answer_query(
    db: Session, patient: Patient, query: CopilotQuery, client,
    provider_name: str, actor_id: str,
) -> CopilotResponse:
    started = perf_counter()
    evidence_list = build_evidence(db, patient, query)
    evidence = {item.evidence_id: item for item in evidence_list}
    status = "ok"
    limitations = [
        "Copilot sends only a bounded set of exact, de-identified evidence spans to the provider and never uses external sources."
    ]
    try:
        result = client.copilot(_bounded_payload(query, evidence_list, patient, db), query.category)
        claims = _validated_claims(result, evidence, query.category)
        draft = _draft_preview(query=query, evidence=evidence_list, patient=patient, actor_id=actor_id)
    except Exception:
        status = "unavailable"
        claims = []
        draft = None
        limitations.append("Copilot is unavailable; no source-based answer or draft was generated.")
    if not evidence_list:
        limitations.append("No exact, authorized evidence was found for this query.")
    if any(item.review_required for item in evidence_list):
        limitations.append("Some cited evidence is marked for clinical review and must not be silently merged into an assessment.")
    add_audit(
        db,
        actor_id=actor_id,
        actor_role="clinician",
        action="copilot_query",
        target_type="patient",
        target_id=patient.patient_id,
        clinic_id=patient.clinic_id,
        patient_id=patient.patient_id,
        details={
            "category": query.category,
            "provider": provider_name,
            "success": status == "ok",
            "latency_ms": round((perf_counter() - started) * 1000),
            "evidence_count": len(evidence_list),
        },
    )
    db.commit()
    return CopilotResponse(
        category=query.category,
        status=status,
        claims=claims,
        evidence=[item.out() for item in evidence_list],
        limitations=limitations,
        draft=draft,
    )
