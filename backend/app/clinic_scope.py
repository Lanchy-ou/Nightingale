"""Query-level clinic isolation for patient-bound application interfaces.

These loaders answer only resource ownership. Role/action permission remains in
``authz.PERMISSIONS``. Every externally supplied direct-object id is resolved
with its Clinic/Patient ancestry in one SQL query so a missing
``authorize_scope`` call cannot expose another clinic's row.

Background maintenance, migrations and seed code do not use these request
loaders; their privileged entry points are explicit and ownership-validated.
"""
from __future__ import annotations

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, aliased

from .models import (
    Artifact,
    Comment,
    Event,
    Highlight,
    Patient,
    PatientCheckInSession,
    RankingDecision,
    RankingRun,
    Task,
    User,
)
from .role_context import RoleContext
from .voice.models import VoiceCaptureRecord


def _patient_clause(ctx: RoleContext, patient_column):
    if ctx.role == "patient":
        return patient_column == ctx.patient_id
    return True


def load_patient(db: Session, ctx: RoleContext, patient_id: str) -> Patient | None:
    return db.scalar(
        select(Patient).where(
            Patient.patient_id == patient_id,
            Patient.clinic_id == ctx.clinic_id,
            _patient_clause(ctx, Patient.patient_id),
        )
    )


def load_event(db: Session, ctx: RoleContext, event_id: str) -> Event | None:
    return db.scalar(
        select(Event)
        .join(Patient, Patient.patient_id == Event.patient_id)
        .where(
            Event.event_id == event_id,
            Event.clinic_id == ctx.clinic_id,
            Patient.clinic_id == ctx.clinic_id,
            _patient_clause(ctx, Event.patient_id),
        )
    )


def load_artifact_with_event(
    db: Session, ctx: RoleContext, artifact_id: str
) -> tuple[Artifact, Event] | None:
    row = db.execute(
        select(Artifact, Event)
        .join(Event, Event.event_id == Artifact.event_id)
        .join(Patient, Patient.patient_id == Event.patient_id)
        .where(
            Artifact.artifact_id == artifact_id,
            Event.clinic_id == ctx.clinic_id,
            Patient.clinic_id == ctx.clinic_id,
            _patient_clause(ctx, Event.patient_id),
        )
    ).one_or_none()
    return (row[0], row[1]) if row is not None else None


def load_highlight_with_event(
    db: Session, ctx: RoleContext, highlight_id: str
) -> tuple[Highlight, Event] | None:
    row = db.execute(
        select(Highlight, Event)
        .join(
            Event,
            and_(
                Event.event_id == Highlight.event_id,
                Event.patient_id == Highlight.patient_id,
            ),
        )
        .join(Patient, Patient.patient_id == Event.patient_id)
        .where(
            Highlight.highlight_id == highlight_id,
            Event.clinic_id == ctx.clinic_id,
            Patient.clinic_id == ctx.clinic_id,
            _patient_clause(ctx, Event.patient_id),
        )
    ).one_or_none()
    return (row[0], row[1]) if row is not None else None


def load_task(db: Session, ctx: RoleContext, task_id: str) -> Task | None:
    return db.scalar(
        select(Task)
        .join(
            Event,
            and_(
                Event.event_id == Task.event_id,
                Event.patient_id == Task.patient_id,
                Event.clinic_id == Task.clinic_id,
            ),
        )
        .join(
            Patient,
            and_(
                Patient.patient_id == Task.patient_id,
                Patient.clinic_id == Task.clinic_id,
            ),
        )
        .where(
            Task.task_id == task_id,
            Task.clinic_id == ctx.clinic_id,
            _patient_clause(ctx, Task.patient_id),
        )
    )


def load_comment_with_event(
    db: Session, ctx: RoleContext, comment_id: str
) -> tuple[Comment, Event] | None:
    event_anchor = aliased(Event)
    artifact_anchor = aliased(Artifact)
    artifact_event = aliased(Event)
    row = db.execute(
        select(Comment, event_anchor, artifact_event)
        .outerjoin(
            event_anchor,
            and_(
                Comment.anchor_type == "event",
                event_anchor.event_id == Comment.anchor_id,
            ),
        )
        .outerjoin(
            artifact_anchor,
            and_(
                Comment.anchor_type == "artifact",
                artifact_anchor.artifact_id == Comment.anchor_id,
            ),
        )
        .outerjoin(
            artifact_event,
            artifact_event.event_id == artifact_anchor.event_id,
        )
        .where(
            Comment.comment_id == comment_id,
            or_(
                and_(
                    event_anchor.clinic_id == ctx.clinic_id,
                    _patient_clause(ctx, event_anchor.patient_id),
                ),
                and_(
                    artifact_event.clinic_id == ctx.clinic_id,
                    _patient_clause(ctx, artifact_event.patient_id),
                ),
            ),
        )
    ).one_or_none()
    if row is None:
        return None
    event = row[1] if row[1] is not None else row[2]
    return row[0], event


def load_checkin(
    db: Session, ctx: RoleContext, session_id: str
) -> PatientCheckInSession | None:
    return db.scalar(
        select(PatientCheckInSession)
        .join(
            Patient,
            and_(
                Patient.patient_id == PatientCheckInSession.patient_id,
                Patient.clinic_id == PatientCheckInSession.clinic_id,
            ),
        )
        .join(
            Event,
            and_(
                Event.event_id == PatientCheckInSession.event_id,
                Event.patient_id == PatientCheckInSession.patient_id,
                Event.clinic_id == PatientCheckInSession.clinic_id,
            ),
        )
        .where(
            PatientCheckInSession.session_id == session_id,
            PatientCheckInSession.clinic_id == ctx.clinic_id,
            _patient_clause(ctx, PatientCheckInSession.patient_id),
        )
    )


def load_voice_capture(
    db: Session, ctx: RoleContext, capture_id: str
) -> VoiceCaptureRecord | None:
    return db.scalar(
        select(VoiceCaptureRecord)
        .join(
            Patient,
            and_(
                Patient.patient_id == VoiceCaptureRecord.patient_id,
                Patient.clinic_id == VoiceCaptureRecord.clinic_id,
            ),
        )
        .where(
            VoiceCaptureRecord.capture_id == capture_id,
            VoiceCaptureRecord.clinic_id == ctx.clinic_id,
            _patient_clause(ctx, VoiceCaptureRecord.patient_id),
        )
    )


def load_ranking_decision_with_run(
    db: Session, ctx: RoleContext, decision_id: str
) -> tuple[RankingDecision, RankingRun] | None:
    row = db.execute(
        select(RankingDecision, RankingRun)
        .join(RankingRun, RankingRun.run_id == RankingDecision.run_id)
        .join(Patient, Patient.patient_id == RankingRun.patient_id)
        .join(Highlight, Highlight.highlight_id == RankingDecision.highlight_id)
        .join(
            Event,
            and_(
                Event.event_id == Highlight.event_id,
                Event.patient_id == Highlight.patient_id,
            ),
        )
        .where(
            RankingDecision.decision_id == decision_id,
            RankingRun.clinic_id == ctx.clinic_id,
            Patient.clinic_id == ctx.clinic_id,
            Highlight.patient_id == RankingRun.patient_id,
            Event.clinic_id == RankingRun.clinic_id,
            _patient_clause(ctx, RankingRun.patient_id),
        )
    ).one_or_none()
    return (row[0], row[1]) if row is not None else None


def load_clinic_user(db: Session, ctx: RoleContext, user_id: str) -> User | None:
    return db.scalar(
        select(User).where(
            User.user_id == user_id,
            User.clinic_id == ctx.clinic_id,
        )
    )
