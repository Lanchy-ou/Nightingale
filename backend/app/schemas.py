"""Pydantic v2 response schemas for the M1 read-only API."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ClinicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    clinic_id: str
    name: str


class PatientOut(BaseModel):
    patient_id: str
    clinic_id: str
    name: str
    clinic_name: str | None = None


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: str
    patient_id: str
    clinic_id: str
    event_type: str
    started_at: datetime
    ended_at: datetime | None
    created_at: datetime
    artifact_count: int = 0


class ArtifactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    artifact_id: str
    event_id: str
    artifact_type: str
    author_role: str
    author_id: str | None
    content: dict
    created_at: datetime
    version: int
    provenance_pointer: dict | None
