"""Bounded, persistent Patient Check-in domain service.

Patient text is committed to a stable message row and the longitudinal raw
Artifact before safety rules, redaction, or provider work. The provider may
only shape an acknowledgement and one bounded next question; the server owns
safety, state, question limits, authorization, and final provenance.
"""
from __future__ import annotations

import re
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .ai_pipeline import AnchoredCandidate, PipelineOutput, persist_derived
from .audit import add_audit
from .conflicts import clinical_assertion_sources, find_conflict
from .extraction import normalize_entity_key
from .highlights import compute_score, extract_text
from .ids import stable_id
from .llm_client import (
    InvalidOutputError,
    ProviderProtocolError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    build_client,
)
from .models import (
    Artifact,
    Event,
    Highlight,
    Patient,
    PatientCheckInMessage,
    PatientCheckInSession,
    Task,
    User,
)
from .priority_routing import validated_priority_reason_codes
from .egress import call_provider, EgressRejected
from .redaction import redact_content, restore_placeholders, unresolved_placeholders
from .schemas import (
    CheckInMessageOut,
    CheckInPatientMessageRequest,
    CheckInSessionOut,
    CheckInSummaryCandidate,
    CheckInSummaryResult,
    CheckInTurnResult,
)
from .system_settings import effective_ai_config

MAX_CLARIFICATION_QUESTIONS = 4
ACTIVE_STATUSES = {"active", "awaiting_confirmation"}

INITIAL_QUESTION = "What has changed since your last update?"
SAFETY_MESSAGE = (
    "Your message may describe an urgent safety concern. This Check-in cannot provide "
    "emergency care. Please contact your local emergency services now, or ask a trusted "
    "person to help you get urgent help. Nightingale has not sent a notification to your clinic."
)

_SAFETY_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("self_harm", re.compile(r"\b(kill myself|suicide|hurt myself|end my life)\b", re.I)),
    ("severe_breathing", re.compile(r"\b(can(?:not|'t) breathe|severe shortness of breath)\b", re.I)),
    ("stroke_signs", re.compile(r"\b(face droop(?:ing)?|one[- ]sided weakness|slurred speech)\b", re.I)),
    ("severe_bleeding", re.compile(r"\b(uncontrolled bleeding|severe bleeding|bleeding (?:that )?won't stop)\b", re.I)),
    ("severe_chest_pain", re.compile(r"\b(severe chest pain|chest pain with shortness of breath)\b", re.I)),
)

_NEGATED_SAFETY_PHRASE = re.compile(
    r"\b(?:i\s+)?(?:do not|don't|did not|didn't)\s+"
    r"(?:have|feel|experience|want to)\s+"
    r"(?:kill myself|suicide|hurt myself|end my life|can(?:not|'t) breathe|"
    r"severe shortness of breath|face droop(?:ing)?|one[- ]sided weakness|"
    r"slurred speech|uncontrolled bleeding|severe bleeding|"
    r"bleeding (?:that )?won't stop|severe chest pain|"
    r"chest pain with shortness of breath)"
    r"(?:\s+(?:or|and)\s+(?:face droop(?:ing)?|one[- ]sided weakness|slurred speech|"
    r"uncontrolled bleeding|severe bleeding|severe chest pain))*\b",
    re.I,
)

_ADVICE_REQUEST = re.compile(
    r"\b(what should i take|which (?:medicine|medication|drug)|recommend (?:a )?"
    r"(?:medicine|medication|drug)|diagnos(?:e|is)|"
    r"(?:should|can|could|may) i (?:start|stop|change|increase|decrease|double|skip)\b|"
    r"(?:start|stop|change|increase|decrease|double) (?:taking )?(?:my )?"
    r"(?:medicine|medication|drug|dose)|"
    r"(?:interpret|explain) (?:whether )?(?:my )?(?:test|result|blood test)|"
    r"(?:is|are) (?:my )?(?:test|result|blood test) normal)\b",
    re.I,
)
_UNSAFE_PROVIDER_LANGUAGE = re.compile(
    r"\b(i recommend|you (?:have|likely have|should)|your (?:test|result) "
    r"(?:is|looks) normal|(?:start|stop|increase|decrease|double) "
    r"(?:taking|your dose|the dose))\b",
    re.I,
)


def _provider_meta(provider_name: str) -> tuple[str | None, str | None]:
    if provider_name == "deepseek":
        return "deepseek", "deepseek-v4-flash"
    return None, None


def _active_key(clinic_id: str, patient_id: str, user_id: str) -> str:
    return f"{clinic_id}:{patient_id}:{user_id}"


def _summary_id(raw_artifact_id: str) -> str:
    return f"art_{stable_id(raw_artifact_id, 'ai_patient_session_summary')}"


def _known_names(db: Session, patient: Patient) -> list[str]:
    names = [patient.name]
    names.extend(
        user.name
        for user in db.scalars(select(User).where(User.clinic_id == patient.clinic_id)).all()
    )
    return names


def _next_sequence(db: Session, session_id: str) -> int:
    current = db.scalar(
        select(func.max(PatientCheckInMessage.sequence)).where(
            PatientCheckInMessage.session_id == session_id
        )
    )
    return int(current or 0) + 1


def _message_payload(message: PatientCheckInMessage) -> dict:
    generation = message.generation_metadata or {}
    return {
        "id": message.message_id,
        "speaker": message.role,
        "text": message.text,
        "intent": message.intent,
        "question_type": message.question_type,
        "conversation_action": message.conversation_action,
        "referenced_patient_message_ids": message.referenced_patient_message_ids,
        "response_to_message_id": message.response_to_message_id,
        "created_at": message.created_at.isoformat(),
        "generation_method": generation.get("method"),
        "degraded": bool(generation.get("degraded", False)),
        "fallback_reason": generation.get("fallback_reason"),
    }


def _append_raw_message(
    db: Session, session: PatientCheckInSession, message: PatientCheckInMessage
) -> None:
    raw = db.get(Artifact, session.raw_artifact_id)
    if raw is None:
        raise RuntimeError("Patient Check-in raw Artifact is missing")
    content = dict(raw.content)
    messages = list(content.get("messages", []))
    if not any(item.get("id") == message.message_id for item in messages if isinstance(item, dict)):
        messages.append(_message_payload(message))
    content.update(
        {
            "session_id": session.session_id,
            "session_status": session.status,
            "safety_status": "safety_escalated" if session.status == "safety_escalated" else "none",
            "safety_reason_codes": list(session.safety_reason_codes),
            "messages": messages,
        }
    )
    raw.content = content
    db.add(raw)


def _sync_raw_metadata(db: Session, session: PatientCheckInSession) -> None:
    raw = db.get(Artifact, session.raw_artifact_id)
    if raw is None:
        raise RuntimeError("Patient Check-in raw Artifact is missing")
    raw.content = {
        **raw.content,
        "session_status": session.status,
        "safety_status": "safety_escalated" if session.status == "safety_escalated" else "none",
        "safety_reason_codes": list(session.safety_reason_codes),
    }
    db.add(raw)


def _messages(db: Session, session_id: str) -> list[PatientCheckInMessage]:
    return db.scalars(
        select(PatientCheckInMessage)
        .where(PatientCheckInMessage.session_id == session_id)
        .order_by(PatientCheckInMessage.sequence, PatientCheckInMessage.message_id)
    ).all()


def _message_out(message: PatientCheckInMessage) -> CheckInMessageOut:
    metadata = message.generation_metadata or {}
    return CheckInMessageOut(
        message_id=message.message_id,
        sequence=message.sequence,
        role=message.role,
        intent=message.intent,
        text=message.text,
        question_type=message.question_type,
        conversation_action=message.conversation_action,
        referenced_patient_message_ids=list(message.referenced_patient_message_ids or []),
        response_to_message_id=message.response_to_message_id,
        processing_status=message.processing_status,
        generation_method=metadata.get("method"),
        degraded=bool(metadata.get("degraded", False)),
        fallback_reason=metadata.get("fallback_reason"),
        created_at=message.created_at,
    )


def session_out(
    db: Session, session: PatientCheckInSession, *, resumed: bool = False
) -> CheckInSessionOut:
    rows = _messages(db, session.session_id)
    patient_words = [row.text for row in rows if row.role == "patient"]
    return CheckInSessionOut(
        session_id=session.session_id,
        event_id=session.event_id,
        status=session.status,
        clarification_count=session.clarification_count,
        max_clarification_questions=MAX_CLARIFICATION_QUESTIONS,
        safety_escalated=session.status == "safety_escalated",
        safety_message=SAFETY_MESSAGE if session.status == "safety_escalated" else None,
        started_at=session.started_at,
        ended_at=session.ended_at,
        submitted_at=session.submitted_at,
        messages=[_message_out(row) for row in rows],
        # Patient confirmation preserves their words; it is not editable AI prose.
        preview_summary=patient_words,
        formal_summary_created=db.get(Artifact, _summary_id(session.raw_artifact_id)) is not None,
        resumed=resumed,
    )


def start_or_resume(
    db: Session, patient: Patient, user_id: str, requested_session_id: str
) -> CheckInSessionOut:
    active_key = _active_key(patient.clinic_id, patient.patient_id, user_id)
    existing_active = db.scalar(
        select(PatientCheckInSession).where(PatientCheckInSession.active_key == active_key)
    )
    if existing_active is not None:
        return session_out(db, existing_active, resumed=True)

    collision = db.get(PatientCheckInSession, requested_session_id)
    if collision is not None:
        if (
            collision.patient_id == patient.patient_id
            and collision.patient_user_id == user_id
            and collision.status in ACTIVE_STATUSES
        ):
            return session_out(db, collision, resumed=True)
        raise HTTPException(status_code=409, detail="Session identity unavailable")

    now = datetime.now()
    event_id = f"evt_{stable_id('patient_checkin', patient.clinic_id, patient.patient_id, requested_session_id)}"
    raw_id = f"art_{stable_id('patient_checkin_raw', event_id)}"
    initial_id = f"msg_{stable_id(requested_session_id, 'initial_question')}"
    session = PatientCheckInSession(
        session_id=requested_session_id,
        event_id=event_id,
        raw_artifact_id=raw_id,
        patient_id=patient.patient_id,
        clinic_id=patient.clinic_id,
        patient_user_id=user_id,
        status="active",
        active_key=active_key,
        clarification_count=1,
        safety_reason_codes=[],
        started_at=now,
        ended_at=None,
        created_at=now,
        updated_at=now,
        submitted_at=None,
        abandoned_at=None,
    )
    initial = PatientCheckInMessage(
        message_id=initial_id,
        session_id=requested_session_id,
        sequence=1,
        role="ai",
        intent=None,
        text=INITIAL_QUESTION,
        question_type="change",
        conversation_action="continue",
        referenced_patient_message_ids=[],
        response_to_message_id=None,
        processing_status="completed",
        generation_metadata={"method": "deterministic_initial", "degraded": False},
        created_at=now,
    )
    event = Event(
        event_id=event_id,
        patient_id=patient.patient_id,
        clinic_id=patient.clinic_id,
        event_type="patient_checkin",
        encounter_id=None,
        started_at=now,
        ended_at=None,
        created_at=now,
    )
    raw = Artifact(
        artifact_id=raw_id,
        event_id=event_id,
        artifact_type="raw_conversation",
        author_role="patient",
        author_id=user_id,
        content={
            "session_id": requested_session_id,
            "session_status": "active",
            "safety_status": "none",
            "safety_reason_codes": [],
            "messages": [_message_payload(initial)],
        },
        created_at=now,
        version=1,
        provenance_pointer=None,
        ingestion_key=f"{patient.clinic_id}:{patient.patient_id}:checkin:{requested_session_id}",
        generation_metadata=None,
    )
    try:
        db.add(event)
        # A3 ownership triggers require each ownership parent before its child.
        # All staged flushes remain inside this one recoverable transaction.
        db.flush()
        db.add(raw)
        db.flush()
        db.add(session)
        db.flush()
        db.add(initial)
        add_audit(
            db,
            actor_id=user_id,
            actor_role="patient",
            action="checkin_start",
            target_type="event",
            target_id=event_id,
            clinic_id=patient.clinic_id,
            patient_id=patient.patient_id,
            event_id=event_id,
            details={"session_id": requested_session_id, "status": "active"},
        )
        db.flush()
        db.commit()
    except IntegrityError:
        db.rollback()
        concurrent = db.scalar(
            select(PatientCheckInSession).where(
                PatientCheckInSession.active_key == active_key
            )
        )
        if concurrent is not None:
            return session_out(db, concurrent, resumed=True)
        raise HTTPException(status_code=409, detail="Session identity unavailable")
    return session_out(db, db.get(PatientCheckInSession, requested_session_id))


def safety_reason_codes(text: str) -> list[str]:
    bounded_text = _NEGATED_SAFETY_PHRASE.sub("", text)
    return [code for code, pattern in _SAFETY_RULES if pattern.search(bounded_text)]


def _fallback_turn(
    message: PatientCheckInMessage,
    clarification_count: int,
    rows: list[PatientCheckInMessage],
) -> CheckInTurnResult:
    if _ADVICE_REQUEST.search(message.text):
        acknowledgement = (
            "I can record that concern, but I cannot diagnose, recommend medicine, "
            "change a dose, or interpret a test result."
        )
    elif message.intent == "correction":
        acknowledgement = "Thanks for correcting that. I will keep the correction with your original words."
    elif message.intent == "supplement":
        acknowledgement = "Thanks for adding that detail."
    elif message.intent == "skip":
        acknowledgement = "That is okay — we can skip it."
    else:
        acknowledgement = "Thanks for explaining that."
    questions = {
        "severity": "How severe is the main symptom right now, in your own words or on a 0 to 10 scale?",
        "associated_symptoms": "Are there any other symptoms that came with this change?",
        "task_progress": "Is there anything about a care action you want the care team to verify?",
        "patient_concern": "What is your main concern that you want the care team to understand?",
    }
    if clarification_count >= MAX_CLARIFICATION_QUESTIONS:
        return CheckInTurnResult(
            acknowledgement=acknowledgement,
            next_question=None,
            question_type=None,
            conversation_action="await_confirmation",
            referenced_patient_message_ids=[message.message_id],
        )
    lowered = message.text.lower()
    all_patient_text = " ".join(row.text.lower() for row in rows if row.role == "patient")
    asked = {
        row.question_type
        for row in rows
        if row.role == "ai" and row.question_type is not None
    }
    covered = set()
    if re.search(r"\b(?:\d|ten)\s*(?:/\s*10|out of 10)\b", all_patient_text):
        covered.add("severity")
    if re.search(r"\b(nausea|dizz|fever|vomit|rash|weakness|symptom)\b", all_patient_text):
        covered.add("associated_symptoms")
    if re.search(r"\b(done|completed|finished|appointment|blood test|task)\b", all_patient_text):
        covered.add("task_progress")
    if re.search(r"\b(done|completed|finished|appointment|blood test|task)\b", lowered):
        preferred = "task_progress"
    elif _ADVICE_REQUEST.search(message.text):
        preferred = "patient_concern"
    elif re.search(r"\b(?:\d|ten)\s*(?:/\s*10|out of 10)\b", lowered):
        preferred = "associated_symptoms"
    else:
        preferred = "severity"
    ordered = [preferred, "severity", "associated_symptoms", "task_progress", "patient_concern"]
    question_type = next(
        (
            candidate
            for candidate in ordered
            if candidate not in asked
            and (
                candidate not in covered
                or (candidate == preferred and preferred in {"task_progress", "patient_concern"})
            )
        ),
        next((candidate for candidate in ordered if candidate not in asked), None),
    )
    if question_type is None:
        return CheckInTurnResult(
            acknowledgement=acknowledgement,
            next_question=None,
            question_type=None,
            conversation_action="await_confirmation",
            referenced_patient_message_ids=[message.message_id],
        )
    return CheckInTurnResult(
        acknowledgement=acknowledgement,
        next_question=questions[question_type],
        question_type=question_type,
        conversation_action="continue",
        referenced_patient_message_ids=[message.message_id],
    )


def _bounded_turn(
    db: Session,
    patient: Patient,
    session: PatientCheckInSession,
    patient_message: PatientCheckInMessage,
) -> tuple[CheckInTurnResult, dict]:
    rows = _messages(db, session.session_id)
    context = {
        "messages": [
            {
                "id": row.message_id,
                "speaker": row.role,
                "text": row.text,
                "intent": row.intent,
                "question_type": row.question_type,
            }
            for row in rows
        ],
        "patient_visible_tasks": [
            {"task_id": task.task_id, "title": task.title, "status": task.status}
            for task in db.scalars(
                select(Task).where(
                    Task.patient_id == patient.patient_id,
                    Task.patient_visible.is_(True),
                    Task.assigned_role == "patient",
                    Task.assigned_user_id == session.patient_user_id,
                )
            ).all()
        ],
    }
    redaction = redact_content(context, _known_names(db, patient))
    config = effective_ai_config(db, patient.clinic_id)
    provider_name = config.provider
    client = (
        build_client(provider_name)
        if config.api_key is None
        else build_client(provider_name, api_key=config.api_key)
    )
    fallback_reason = None
    if _ADVICE_REQUEST.search(patient_message.text):
        # Medical-advice requests never depend on provider wording. A fixed
        # refusal is safer than trying to classify every possible generated
        # recommendation after the fact.
        fallback_reason = "bounded_medical_request"
    else:
        try:
            result = call_provider(client, "checkin_turn", redaction.redacted, session.clarification_count)
            patient_ids = {row.message_id for row in rows if row.role == "patient"}
            if not set(result.referenced_patient_message_ids).issubset(patient_ids):
                raise InvalidOutputError("provider referenced a non-patient message")
            if patient_message.message_id not in result.referenced_patient_message_ids:
                raise InvalidOutputError("provider did not reference the newest patient message")
            asked_types = {
                row.question_type
                for row in rows
                if row.role == "ai" and row.question_type is not None
            }
            if result.question_type is not None and result.question_type in asked_types:
                raise InvalidOutputError("provider repeated an already asked question type")
            fields = [result.acknowledgement, result.next_question or ""]
            if any(unresolved_placeholders(field, redaction.placeholder_mapping) for field in fields):
                raise InvalidOutputError("provider changed a redaction placeholder")
            result.acknowledgement = restore_placeholders(
                result.acknowledgement, redaction.placeholder_mapping
            )
            if result.next_question is not None:
                result.next_question = restore_placeholders(
                    result.next_question, redaction.placeholder_mapping
                )
            if _UNSAFE_PROVIDER_LANGUAGE.search(
                result.acknowledgement + " " + (result.next_question or "")
            ):
                raise InvalidOutputError("provider returned medical advice language")
        except EgressRejected:
            fallback_reason = "egress_rejected"
        except ProviderUnavailableError:
            fallback_reason = "provider_missing"
        except ProviderTimeoutError:
            fallback_reason = "provider_timeout"
        except ProviderProtocolError:
            fallback_reason = "provider_error"
        except InvalidOutputError:
            fallback_reason = "invalid_output"
        except Exception:
            fallback_reason = "provider_error"

    if fallback_reason is not None:
        result = _fallback_turn(patient_message, session.clarification_count, rows)
        method = "deterministic_fallback"
        degraded = True
    else:
        method = provider_name
        degraded = False

    # The provider never owns the round cap.
    if session.clarification_count >= MAX_CLARIFICATION_QUESTIONS:
        result.next_question = None
        result.question_type = None
        result.conversation_action = "await_confirmation"

    return result, {
        "method": method,
        "degraded": degraded,
        "fallback_reason": fallback_reason,
        "redaction_counts": redaction.redacted.redaction_counts,
    }


def _complete_turn(
    db: Session,
    session: PatientCheckInSession,
    patient_message: PatientCheckInMessage,
    result: CheckInTurnResult,
    metadata: dict,
) -> None:
    now = datetime.now()
    response_id = f"msg_{stable_id(patient_message.message_id, 'ai_response')}"
    text = result.acknowledgement
    if result.next_question:
        text = f"{text} {result.next_question}"
    response = db.get(PatientCheckInMessage, response_id)
    if response is None:
        response = PatientCheckInMessage(
            message_id=response_id,
            session_id=session.session_id,
            sequence=_next_sequence(db, session.session_id),
            role="ai",
            intent=None,
            text=text,
            question_type=result.question_type,
            conversation_action=result.conversation_action,
            referenced_patient_message_ids=result.referenced_patient_message_ids,
            response_to_message_id=patient_message.message_id,
            processing_status="completed",
            generation_metadata=metadata,
            created_at=now,
        )
        db.add(response)
    patient_message.processing_status = "completed"
    db.add(patient_message)
    if result.next_question is not None:
        session.clarification_count += 1
    if result.conversation_action == "await_confirmation":
        session.status = "awaiting_confirmation"
    session.updated_at = now
    db.add(session)
    _append_raw_message(db, session, response)
    _sync_raw_metadata(db, session)
    db.commit()


def save_patient_message(
    db: Session,
    session: PatientCheckInSession,
    body: CheckInPatientMessageRequest,
) -> CheckInSessionOut:
    existing = db.get(PatientCheckInMessage, body.message_id)
    if existing is not None:
        if (
            existing.session_id != session.session_id
            or existing.role != "patient"
            or existing.intent != body.intent
            or existing.text != body.text
        ):
            raise HTTPException(status_code=409, detail="message_id payload conflict")
        return session_out(db, session, resumed=True)
    if session.status != "active":
        raise HTTPException(status_code=409, detail="Check-in is not accepting messages")
    for attempt in range(2):
        now = datetime.now()
        patient_message = PatientCheckInMessage(
            message_id=body.message_id,
            session_id=session.session_id,
            sequence=_next_sequence(db, session.session_id),
            role="patient",
            intent=body.intent,
            text=body.text,
            question_type=None,
            conversation_action=None,
            referenced_patient_message_ids=[],
            response_to_message_id=None,
            processing_status="saved",
            generation_metadata=None,
            created_at=now,
        )
        db.add(patient_message)
        _append_raw_message(db, session, patient_message)
        add_audit(
            db,
            actor_id=session.patient_user_id,
            actor_role="patient",
            action="checkin_message",
            target_type="message",
            target_id=body.message_id,
            clinic_id=session.clinic_id,
            patient_id=session.patient_id,
            event_id=session.event_id,
            details={"session_id": session.session_id, "intent": body.intent},
        )
        try:
            # RAW-FIRST hard gate: this commit precedes safety, redaction and AI.
            db.commit()
            break
        except IntegrityError:
            db.rollback()
            concurrent = db.get(PatientCheckInMessage, body.message_id)
            if concurrent is not None:
                if (
                    concurrent.session_id != session.session_id
                    or concurrent.role != "patient"
                    or concurrent.intent != body.intent
                    or concurrent.text != body.text
                ):
                    raise HTTPException(status_code=409, detail="message_id payload conflict")
                return session_out(
                    db, db.get(PatientCheckInSession, session.session_id), resumed=True
                )
            if attempt == 1:
                raise HTTPException(status_code=409, detail="Concurrent message save; retry")
            session = db.get(PatientCheckInSession, session.session_id)
            if session.status != "active":
                raise HTTPException(status_code=409, detail="Check-in is not accepting messages")
    return session_out(db, db.get(PatientCheckInSession, session.session_id))


def process_patient_message(
    db: Session,
    patient: Patient,
    session: PatientCheckInSession,
    message_id: str,
) -> CheckInSessionOut:
    patient_message = db.get(PatientCheckInMessage, message_id)
    if (
        patient_message is None
        or patient_message.session_id != session.session_id
        or patient_message.role != "patient"
    ):
        raise HTTPException(status_code=404, detail="Resource not found")
    # completed and in-flight retries never call the provider again.
    if patient_message.processing_status != "saved":
        return session_out(db, session, resumed=True)

    claimed = db.execute(
        update(PatientCheckInMessage)
        .where(
            PatientCheckInMessage.message_id == patient_message.message_id,
            PatientCheckInMessage.processing_status == "saved",
        )
        .values(processing_status="processing")
    ).rowcount
    if claimed != 1:
        db.rollback()
        return session_out(db, db.get(PatientCheckInSession, session.session_id), resumed=True)
    patient_message = db.get(PatientCheckInMessage, message_id)
    session = db.get(PatientCheckInSession, session.session_id)

    reasons = safety_reason_codes(patient_message.text)
    if reasons:
        now = datetime.now()
        result = CheckInTurnResult(
            acknowledgement=SAFETY_MESSAGE,
            next_question=None,
            question_type=None,
            conversation_action="await_confirmation",
            referenced_patient_message_ids=[patient_message.message_id],
        )
        # Persist a clearly marked non-provider safety response.
        response_id = f"msg_{stable_id(patient_message.message_id, 'safety_response')}"
        response = PatientCheckInMessage(
            message_id=response_id,
            session_id=session.session_id,
            sequence=_next_sequence(db, session.session_id),
            role="ai",
            intent=None,
            text=result.acknowledgement,
            question_type=None,
            conversation_action="safety_escalate",
            referenced_patient_message_ids=[patient_message.message_id],
            response_to_message_id=patient_message.message_id,
            processing_status="completed",
            generation_metadata={"method": "deterministic_safety", "degraded": False},
            created_at=now,
        )
        db.add(response)
        patient_message.processing_status = "completed"
        session.status = "safety_escalated"
        session.active_key = None
        session.safety_reason_codes = reasons
        session.ended_at = now
        session.updated_at = now
        event = db.get(Event, session.event_id)
        event.ended_at = now
        db.add(patient_message)
        db.add(session)
        db.add(event)
        _append_raw_message(db, session, response)
        _sync_raw_metadata(db, session)
        add_audit(
            db,
            actor_id=session.patient_user_id,
            actor_role="patient",
            action="checkin_state",
            target_type="checkin",
            target_id=session.session_id,
            clinic_id=session.clinic_id,
            patient_id=session.patient_id,
            event_id=session.event_id,
            details={"to_status": "safety_escalated", "reason_codes": reasons},
        )
        db.commit()
        return session_out(db, db.get(PatientCheckInSession, session.session_id))

    if patient_message.intent == "no_more":
        result = CheckInTurnResult(
            acknowledgement="Thanks. I will show you the information you shared before you submit it.",
            next_question=None,
            question_type=None,
            conversation_action="await_confirmation",
            referenced_patient_message_ids=[patient_message.message_id],
        )
        metadata = {"method": "deterministic_control", "degraded": False}
    else:
        result, metadata = _bounded_turn(db, patient, session, patient_message)
    _complete_turn(db, session, patient_message, result, metadata)
    return session_out(db, db.get(PatientCheckInSession, session.session_id))


def add_patient_message(
    db: Session,
    patient: Patient,
    session: PatientCheckInSession,
    body: CheckInPatientMessageRequest,
) -> CheckInSessionOut:
    """Compatibility one-call flow; the UI uses explicit save then process."""
    save_patient_message(db, session, body)
    session = db.get(PatientCheckInSession, session.session_id)
    return process_patient_message(db, patient, session, body.message_id)


def transition_state(
    db: Session,
    session: PatientCheckInSession,
    expected_status: str,
    target_status: str,
) -> CheckInSessionOut:
    allowed = {
        ("active", "awaiting_confirmation"),
        ("awaiting_confirmation", "active"),
        ("active", "abandoned"),
        ("awaiting_confirmation", "abandoned"),
    }
    if (expected_status, target_status) not in allowed:
        raise HTTPException(status_code=409, detail="Invalid Check-in state transition")
    now = datetime.now()
    values: dict = {"status": target_status, "updated_at": now}
    if target_status == "active":
        values["active_key"] = _active_key(
            session.clinic_id, session.patient_id, session.patient_user_id
        )
    elif target_status == "abandoned":
        values.update({"active_key": None, "abandoned_at": now, "ended_at": now})
    changed = db.execute(
        update(PatientCheckInSession)
        .where(
            PatientCheckInSession.session_id == session.session_id,
            PatientCheckInSession.status == expected_status,
        )
        .values(**values)
    ).rowcount
    if changed != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Check-in state changed; refresh and retry")
    session = db.get(PatientCheckInSession, session.session_id)
    if target_status == "abandoned":
        event = db.get(Event, session.event_id)
        event.ended_at = now
        db.add(event)
    _sync_raw_metadata(db, session)
    add_audit(
        db,
        actor_id=session.patient_user_id,
        actor_role="patient",
        action="checkin_state",
        target_type="checkin",
        target_id=session.session_id,
        clinic_id=session.clinic_id,
        patient_id=session.patient_id,
        event_id=session.event_id,
        details={"from_status": expected_status, "to_status": target_status},
    )
    db.commit()
    return session_out(db, db.get(PatientCheckInSession, session.session_id))


def _fallback_summary(messages: list[PatientCheckInMessage]) -> CheckInSummaryResult:
    references = [message.message_id for message in messages]
    summary = _bounded_summary_text([message.text for message in messages])
    candidates: list[CheckInSummaryCandidate] = []
    for message in messages:
        lowered = message.text.lower()
        if re.search(r"\b(done|completed|finished|appointment|blood test|follow-up|task)\b", lowered):
            entity_type = "task"
            text = "Patient-reported care action progress"
            reason = "Patient reported care action progress; clinic verification is still required"
        elif re.search(r"\b(pain|headache|nausea|dizzy|fever|symptom|better|worse|improv)\b", lowered):
            entity_type = "symptom"
            text = "Patient-reported symptom update"
            reason = "Patient described a symptom or change"
        else:
            continue
        candidates.append(
            CheckInSummaryCandidate(
                text=text,
                patient_message_id=message.message_id,
                quote=message.text,
                risk_reason=reason,
                entity_type=entity_type,
                assertion_value=None,
                symptom_change=bool(re.search(r"\b(better|worse|improv|changed|more|less)\b", lowered)),
            )
        )
    return CheckInSummaryResult(
        summary=summary or "The patient did not add a narrative update.",
        referenced_patient_message_ids=references,
        candidates=candidates,
    )


def _bounded_summary_text(texts: list[str], limit: int = 4000) -> str:
    full = " ".join(texts)
    if len(full) <= limit:
        return full
    suffix = " … Full original patient messages are retained."
    budget = limit - len(suffix)
    selected: list[str] = []
    used = 0
    for text in reversed(texts):
        cost = len(text) + (1 if selected else 0)
        if cost <= budget - used:
            selected.insert(0, text)
            used += cost
    if not selected and texts:
        selected = [texts[-1][:budget]]
    return " ".join(selected) + suffix


def _summary_output(
    db: Session, patient: Patient, session: PatientCheckInSession
) -> tuple[PipelineOutput, str]:
    patient_messages = [
        message for message in _messages(db, session.session_id) if message.role == "patient"
    ]
    raw = db.get(Artifact, session.raw_artifact_id)
    patient_content = {
        "messages": [
            {"id": message.message_id, "speaker": "patient", "text": message.text}
            for message in patient_messages
        ]
    }
    redaction = redact_content(patient_content, _known_names(db, patient))
    config = effective_ai_config(db, patient.clinic_id)
    provider_name = config.provider
    client = (
        build_client(provider_name)
        if config.api_key is None
        else build_client(provider_name, api_key=config.api_key)
    )
    fallback_reason = None
    try:
        result = call_provider(client, "checkin_summary", redaction.redacted)
        patient_ids = {message.message_id for message in patient_messages}
        if set(result.referenced_patient_message_ids) != patient_ids:
            raise InvalidOutputError("summary must reference every patient message and no AI message")
        if any(
            candidate.patient_message_id not in result.referenced_patient_message_ids
            for candidate in result.candidates
        ):
            raise InvalidOutputError("summary candidate referenced an unlisted patient message")
        fields = [result.summary]
        for candidate in result.candidates:
            fields.extend(
                [candidate.text, candidate.quote, candidate.risk_reason, candidate.assertion_value or ""]
            )
        if any(unresolved_placeholders(field, redaction.placeholder_mapping) for field in fields):
            raise InvalidOutputError("summary changed a redaction placeholder")
        result.summary = restore_placeholders(result.summary, redaction.placeholder_mapping)
        for candidate in result.candidates:
            candidate.text = restore_placeholders(candidate.text, redaction.placeholder_mapping)
            candidate.quote = restore_placeholders(candidate.quote, redaction.placeholder_mapping)
            candidate.risk_reason = restore_placeholders(candidate.risk_reason, redaction.placeholder_mapping)
            if candidate.assertion_value is not None:
                candidate.assertion_value = restore_placeholders(
                    candidate.assertion_value, redaction.placeholder_mapping
                )
    except EgressRejected:
        fallback_reason = "egress_rejected"
    except ProviderUnavailableError:
        fallback_reason = "provider_missing"
    except ProviderTimeoutError:
        fallback_reason = "provider_timeout"
    except ProviderProtocolError:
        fallback_reason = "provider_error"
    except InvalidOutputError:
        fallback_reason = "invalid_output"
    except Exception:
        fallback_reason = "provider_error"

    if fallback_reason is not None:
        result = _fallback_summary(patient_messages)
        method = "deterministic_fallback"
        degraded = True
    else:
        method = provider_name
        degraded = False

    by_id = {message.message_id: message for message in patient_messages}
    anchored: list[AnchoredCandidate] = []
    source_facts: list[dict] = []
    recompute: list[str] = []
    clinician_records = clinical_assertion_sources(db, patient.patient_id)
    allergy_records = clinical_assertion_sources(
        db, patient.patient_id, include_staff_and_nurse=True
    )
    for candidate in result.candidates:
        source_message = by_id.get(candidate.patient_message_id)
        if source_message is None:
            continue
        start = source_message.text.find(candidate.quote)
        if start < 0:
            continue
        span = {
            "kind": "message",
            "index": source_message.message_id,
            "offset": [start, start + len(candidate.quote)],
        }
        # Final resolver check is against the actual longitudinal raw Artifact.
        if extract_text(raw.content, span) != candidate.quote:
            continue
        priority_codes = validated_priority_reason_codes(
            source_message.text,
            candidate.quote,
            candidate.priority_review_reason_codes,
        )
        entity_key = normalize_entity_key(candidate.entity_type, candidate.text)
        existing = db.scalars(
            select(Highlight).join(Event, Event.event_id == Highlight.event_id).where(
                Highlight.patient_id == patient.patient_id,
                Event.patient_id == patient.patient_id,
                Event.clinic_id == patient.clinic_id,
                Highlight.event_id != session.event_id,
            )
        ).all()
        existing = [h for h in existing if entity_key and h.entity_key == entity_key]
        flags = {
            "recency": True,
            "explicit_risk": candidate.entity_type == "risk",
            "unresolved_task": False,
            "clinician_confirmed": False,
            "symptom_change": candidate.symptom_change,
            "repeated_mentions": bool(existing),
        }
        review_status = None
        conflict_with = None
        risk_reason = candidate.risk_reason
        conflict = find_conflict(
            entity_key,
            candidate.assertion_value,
            allergy_records if candidate.entity_type == "allergy" else clinician_records,
            candidate_entity_type=candidate.entity_type,
            candidate_text=candidate.text,
            candidate_quote=candidate.quote,
        )
        if conflict is not None:
            conflict_with, _ = conflict
            review_status = "needs_review"
            risk_reason = (
                "allergy statements conflict across patient and clinical records; review required"
                if candidate.entity_type == "allergy"
                else "conflicts with clinician-authored record; review required"
            )
        anchored.append(
            AnchoredCandidate(
                text=candidate.text,
                risk_reason=risk_reason,
                entity_type=candidate.entity_type,
                entity_key=entity_key,
                assertion_value=candidate.assertion_value,
                span=span,
                feature_flags=flags,
                score=compute_score(flags),
                review_status=review_status,
                conflict_with_artifact_id=conflict_with,
                priority_review_reason_codes=priority_codes,
            )
        )
        source_facts.append(
            {
                "patient_message_id": candidate.patient_message_id,
                "quote": candidate.quote,
                "text": candidate.text,
                "priority_review_reason_codes": priority_codes,
            }
        )
        recompute.extend(item.highlight_id for item in existing)

    spans = [candidate.span for candidate in anchored]
    pointer: dict = {
        "event_id": session.event_id,
        "artifact_id": session.raw_artifact_id,
        "patient_message_ids": result.referenced_patient_message_ids,
        "spans": spans,
    }
    if len(spans) == 1:
        pointer["span"] = spans[0]
    return PipelineOutput(
        summary_content={
            "summary": result.summary,
            "key_points": [candidate.text for candidate in anchored],
            "patient_message_ids": result.referenced_patient_message_ids,
            "source_facts": source_facts,
            "safety_status": "none",
        },
        provenance_pointer=pointer,
        candidates=anchored,
        method=method,
        degraded=degraded,
        fallback_reason=fallback_reason,
        redaction_counts=redaction.redacted.redaction_counts,
        recompute_existing=recompute,
    ), provider_name


def submit_checkin(
    db: Session,
    patient: Patient,
    session: PatientCheckInSession,
    expected_status: str,
) -> CheckInSessionOut:
    if session.status == "submitted" and expected_status in {
        "awaiting_confirmation", "submitted"
    }:
        if db.get(Artifact, _summary_id(session.raw_artifact_id)) is None:
            raise HTTPException(status_code=409, detail="Submitted Check-in summary is unavailable")
        from .patient_review import reconcile_patient_review_workflow

        reconcile_patient_review_workflow(db, session)
        db.commit()
        return session_out(db, session, resumed=True)
    if expected_status != "awaiting_confirmation" or session.status != expected_status:
        raise HTTPException(status_code=409, detail="Check-in is not ready for confirmation")
    if not any(message.role == "patient" for message in _messages(db, session.session_id)):
        raise HTTPException(status_code=409, detail="Add a patient message before submitting")
    raw = db.get(Artifact, session.raw_artifact_id)
    summary_id = _summary_id(session.raw_artifact_id)
    if db.get(Artifact, summary_id) is None:
        output, provider_name = _summary_output(db, patient, session)
        provider, model = _provider_meta(provider_name)
        persist_derived(
            db,
            db.get(Event, session.event_id),
            raw,
            "ai_patient_session_summary",
            output,
            session.patient_user_id,
            "patient",
            provider,
            model,
        )

    now = datetime.now()
    changed = db.execute(
        update(PatientCheckInSession)
        .where(
            PatientCheckInSession.session_id == session.session_id,
            PatientCheckInSession.status == "awaiting_confirmation",
        )
        .values(
            status="submitted",
            active_key=None,
            submitted_at=now,
            ended_at=now,
            updated_at=now,
        )
    ).rowcount
    if changed != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Check-in state changed; refresh and retry")
    db.expire_all()
    session = db.get(PatientCheckInSession, session.session_id)
    event = db.get(Event, session.event_id)
    event.ended_at = now
    db.add(event)
    _sync_raw_metadata(db, session)
    add_audit(
        db,
        actor_id=session.patient_user_id,
        actor_role="patient",
        action="checkin_state",
        target_type="checkin",
        target_id=session.session_id,
        clinic_id=session.clinic_id,
        patient_id=session.patient_id,
        event_id=session.event_id,
        details={"from_status": "awaiting_confirmation", "to_status": "submitted"},
    )
    from .patient_review import reconcile_patient_review_workflow

    reconcile_patient_review_workflow(db, session, as_of=now)
    db.commit()
    return session_out(db, db.get(PatientCheckInSession, session.session_id))
