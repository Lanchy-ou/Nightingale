"""Persistent E4 recording lifecycle, separate from clinical Artifacts."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class VoiceCaptureRecord(Base):
    __tablename__ = "voice_captures"

    capture_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    clinic_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("clinics.clinic_id"), nullable=False, index=True
    )
    patient_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("patients.patient_id"), nullable=False, index=True
    )
    created_by: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.user_id"), nullable=False, index=True
    )
    capture_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    encounter_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    retry_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)

    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    byte_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    audio_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sample_rate_hz: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channels: Mapped[int | None] = mapped_column(Integer, nullable=True)
    audio_bytes: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    audio_upload_key: Mapped[str | None] = mapped_column(String(128), nullable=True)

    machine_transcript: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reviewed_segments: Mapped[list | None] = mapped_column(JSON, nullable=True)
    confirmed_transcript: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    audio_ranges: Mapped[list | None] = mapped_column(JSON, nullable=True)
    transcribe_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    confirm_key: Mapped[str | None] = mapped_column(String(128), nullable=True)

    event_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("events.event_id"), nullable=True
    )
    transcript_artifact_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("artifacts.artifact_id"), nullable=True
    )
    processing_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
