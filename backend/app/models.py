"""M1 data model. Only the five tables required for M1.

Span is NOT a table — it is expressed as a JSON pointer inside
Artifact.provenance_pointer. Comment / Version / Task / AuditLog arrive in
Phase 3 and are deliberately absent here.

Field names intentionally leave room for later encryption of content columns
(content / provenance_pointer are large JSON/Text fields).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

# Allowed values (enforced by the seed fixture + tests, not DB constraints in M1).
ROLES = ("patient", "staff", "clinician", "admin")
EVENT_TYPES = (
    "patient_ai_preconsult",
    "nurse_consult",
    "doctor_consult",
    "patient_followup",
    "clinician_review",
    "historical_review",
)
ARTIFACT_TYPES = (
    "raw_conversation",
    "transcript",
    "clinician_note",
    "staff_note",
    "ai_doctor_consult_summary",
    "ai_nurse_consult_summary",
    "ai_patient_session_summary",
    "patient_instruction",
)


class Clinic(Base):
    __tablename__ = "clinics"

    clinic_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    clinic_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("clinics.clinic_id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)


class Patient(Base):
    __tablename__ = "patients"

    patient_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    clinic_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("clinics.clinic_id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class Event(Base):
    __tablename__ = "events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    patient_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("patients.patient_id"), nullable=False, index=True
    )
    clinic_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("clinics.clinic_id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # Real-world clinical time axis (what the Timeline sorts by).
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Record-keeping time axis.
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class Artifact(Base):
    __tablename__ = "artifacts"

    artifact_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("events.event_id"), nullable=False, index=True
    )
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # AI-scribed artifacts are always "system"; human notes use their role.
    author_role: Mapped[str] = mapped_column(String(32), nullable=False)
    author_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.user_id"), nullable=True
    )
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    provenance_pointer: Mapped[dict | None] = mapped_column(JSON, nullable=True)
