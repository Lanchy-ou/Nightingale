"""Clinic-scoped, preview-first and idempotent patient CSV import."""
from __future__ import annotations

import csv
import io
import re
from collections import Counter
from datetime import datetime
from hashlib import sha256

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import add_audit
from ..authz import authorize, require_auth, resource_not_found
from ..db import get_db
from ..ids import new_id
from ..models import (
    Patient,
    PatientExternalIdentity,
    PatientImportBatch,
    PatientImportRow,
)
from ..role_context import RoleContext
from ..schemas import PatientImportBatchOut, PatientImportRowOut

router = APIRouter(prefix="/api/admin/patient-imports", tags=["patient-imports"])

MAX_IMPORT_BYTES = 1_048_576
MAX_IMPORT_ROWS = 1_000
EXPECTED_COLUMNS = ["external_patient_id", "name"]
SOURCE_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
COUNT_KEYS = ("ready", "imported", "unchanged", "invalid", "conflict")


def _normalized_name(value: str) -> str:
    return " ".join(value.split()).casefold()


def _display_name(value: str) -> str:
    return " ".join(value.split())


def _name_hash(value: str) -> str:
    return sha256(_display_name(value).encode("utf-8")).hexdigest()


def _rows(db: Session, batch_id: str) -> list[PatientImportRow]:
    return list(
        db.scalars(
            select(PatientImportRow)
            .where(PatientImportRow.batch_id == batch_id)
            .order_by(PatientImportRow.row_number)
        ).all()
    )


def _out(db: Session, batch: PatientImportBatch) -> PatientImportBatchOut:
    rows = _rows(db, batch.batch_id)
    counts = {key: 0 for key in COUNT_KEYS}
    for row in rows:
        counts[row.status] += 1
    return PatientImportBatchOut(
        batch_id=batch.batch_id,
        source_system=batch.source_system,
        content_sha256=batch.content_sha256,
        status=batch.status,
        counts=counts,
        rows=[
            PatientImportRowOut(
                row_number=row.row_number,
                external_patient_id=row.external_patient_id,
                name=row.name,
                status=row.status,
                error_code=row.error_code,
                patient_id=row.patient_id,
            )
            for row in rows
        ],
        created_at=batch.created_at,
        committed_at=batch.committed_at,
    )


def _parse_csv(raw: bytes) -> list[tuple[int, str, str]]:
    if len(raw) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="Patient import is too large")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=422, detail="Patient import must be UTF-8 CSV")
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        if reader.fieldnames != EXPECTED_COLUMNS:
            raise HTTPException(
                status_code=422,
                detail="Patient import columns must be external_patient_id,name",
            )
        parsed: list[tuple[int, str, str]] = []
        for row_number, row in enumerate(reader, start=2):
            if None in row:
                raise HTTPException(status_code=422, detail="Patient import row has extra columns")
            parsed.append(
                (
                    row_number,
                    (row.get("external_patient_id") or "").strip(),
                    _display_name(row.get("name") or ""),
                )
            )
            if len(parsed) > MAX_IMPORT_ROWS:
                raise HTTPException(
                    status_code=422, detail="Patient import exceeds 1000 rows"
                )
    except csv.Error:
        raise HTTPException(status_code=422, detail="Patient import CSV is invalid")
    if not parsed:
        raise HTTPException(status_code=422, detail="Patient import contains no rows")
    return parsed


def _classify(
    db: Session,
    *,
    clinic_id: str,
    source_system: str,
    parsed: list[tuple[int, str, str]],
) -> list[PatientImportRow]:
    external_counts = Counter(external_id for _, external_id, _ in parsed if external_id)
    normalized_counts = Counter(
        _normalized_name(name) for _, _, name in parsed if _normalized_name(name)
    )
    identities = {
        row.external_patient_id: row
        for row in db.scalars(
            select(PatientExternalIdentity).where(
                PatientExternalIdentity.clinic_id == clinic_id,
                PatientExternalIdentity.source_system == source_system,
            )
        ).all()
    }
    patients_by_name = {
        _normalized_name(row.name): row
        for row in db.scalars(
            select(Patient).where(Patient.clinic_id == clinic_id)
        ).all()
    }

    results: list[PatientImportRow] = []
    for row_number, external_id, name in parsed:
        normalized = _normalized_name(name)
        status = "ready"
        error_code = None
        patient_id = None
        if not external_id:
            status, error_code = "invalid", "external_patient_id_required"
        elif len(external_id) > 64:
            status, error_code = "invalid", "external_patient_id_too_long"
        elif external_counts[external_id] > 1:
            status, error_code = "invalid", "duplicate_external_id"
        elif not name:
            status, error_code = "invalid", "name_required"
        elif len(name) > 255:
            status, error_code = "invalid", "name_too_long"
        elif normalized_counts[normalized] > 1:
            status, error_code = "conflict", "duplicate_name_in_file"
        elif external_id in identities:
            identity = identities[external_id]
            patient_id = identity.patient_id
            if identity.name_sha256 == _name_hash(name):
                status = "unchanged"
            else:
                status, error_code = "conflict", "external_identity_mismatch"
        elif normalized in patients_by_name:
            status, error_code = "conflict", "possible_existing_patient"
            patient_id = patients_by_name[normalized].patient_id
        results.append(
            PatientImportRow(
                import_row_id=new_id("pir"),
                batch_id="",
                row_number=row_number,
                external_patient_id=external_id,
                name=name,
                normalized_name=normalized,
                status=status,
                error_code=error_code,
                patient_id=patient_id,
            )
        )
    return results


@router.post("/preview", response_model=PatientImportBatchOut)
async def preview_patient_import(
    request: Request,
    source_system: str = Query(min_length=1, max_length=64),
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    authorize(ctx, "admin_import_patients", ctx.clinic_id, None)
    content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    if content_type != "text/csv":
        raise HTTPException(status_code=415, detail="Patient import must be text/csv")
    source = source_system.strip().lower()
    if not SOURCE_PATTERN.fullmatch(source):
        raise HTTPException(status_code=422, detail="Invalid source system")
    raw = await request.body()
    digest = sha256(raw).hexdigest()
    existing = db.scalar(
        select(PatientImportBatch).where(
            PatientImportBatch.clinic_id == ctx.clinic_id,
            PatientImportBatch.source_system == source,
            PatientImportBatch.content_sha256 == digest,
        )
    )
    if existing is not None:
        if existing.status == "committing":
            raise HTTPException(status_code=409, detail="Patient import commit is in progress")
        return _out(db, existing)

    parsed = _parse_csv(raw)
    now = datetime.now()
    batch = PatientImportBatch(
        batch_id=new_id("pib"),
        clinic_id=ctx.clinic_id,
        source_system=source,
        content_sha256=digest,
        status="previewed",
        total_rows=len(parsed),
        created_by=ctx.user_id,
        created_at=now,
        committed_at=None,
    )
    rows = _classify(
        db, clinic_id=ctx.clinic_id, source_system=source, parsed=parsed
    )
    for row in rows:
        row.batch_id = batch.batch_id
    db.add(batch)
    db.add_all(rows)
    add_audit(
        db,
        actor_id=ctx.user_id,
        actor_role=ctx.role,
        action="patient_import_previewed",
        target_type="import_batch",
        target_id=batch.batch_id,
        clinic_id=ctx.clinic_id,
        patient_id=None,
        details={"source_system": source, "row_count": len(rows)},
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(PatientImportBatch).where(
                PatientImportBatch.clinic_id == ctx.clinic_id,
                PatientImportBatch.source_system == source,
                PatientImportBatch.content_sha256 == digest,
            )
        )
        if existing is None:
            raise
        return _out(db, existing)
    return _out(db, batch)


@router.post("/{batch_id}/commit", response_model=PatientImportBatchOut)
def commit_patient_import(
    batch_id: str,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    authorize(ctx, "admin_import_patients", ctx.clinic_id, None)
    batch = db.scalar(
        select(PatientImportBatch).where(
            PatientImportBatch.batch_id == batch_id,
            PatientImportBatch.clinic_id == ctx.clinic_id,
        )
    )
    if batch is None:
        raise resource_not_found()
    if batch.status == "committed":
        return _out(db, batch)
    claimed = db.execute(
        update(PatientImportBatch)
        .where(
            PatientImportBatch.batch_id == batch.batch_id,
            PatientImportBatch.clinic_id == ctx.clinic_id,
            PatientImportBatch.status == "previewed",
        )
        .values(status="committing")
    )
    if claimed.rowcount != 1:
        db.rollback()
        current = db.scalar(
            select(PatientImportBatch).where(
                PatientImportBatch.batch_id == batch_id,
                PatientImportBatch.clinic_id == ctx.clinic_id,
            )
        )
        if current is not None and current.status == "committed":
            return _out(db, current)
        raise HTTPException(status_code=409, detail="Patient import commit is in progress")

    identities = {
        row.external_patient_id: row
        for row in db.scalars(
            select(PatientExternalIdentity).where(
                PatientExternalIdentity.clinic_id == ctx.clinic_id,
                PatientExternalIdentity.source_system == batch.source_system,
            )
        ).all()
    }
    patients_by_name = {
        _normalized_name(row.name): row
        for row in db.scalars(
            select(Patient).where(Patient.clinic_id == ctx.clinic_id)
        ).all()
    }
    now = datetime.now()
    for row in _rows(db, batch.batch_id):
        if row.status == "invalid":
            continue
        identity = identities.get(row.external_patient_id)
        if identity is not None:
            row.patient_id = identity.patient_id
            if identity.name_sha256 == _name_hash(row.name):
                row.status, row.error_code = "unchanged", None
            else:
                row.status, row.error_code = "conflict", "external_identity_mismatch"
            continue
        existing_name = patients_by_name.get(row.normalized_name)
        if existing_name is not None:
            row.status, row.error_code = "conflict", "possible_existing_patient"
            row.patient_id = existing_name.patient_id
            continue

        patient = Patient(
            patient_id=new_id("pat"), clinic_id=ctx.clinic_id, name=row.name
        )
        identity = PatientExternalIdentity(
            external_identity_id=new_id("pei"),
            clinic_id=ctx.clinic_id,
            patient_id=patient.patient_id,
            source_system=batch.source_system,
            external_patient_id=row.external_patient_id,
            name_sha256=_name_hash(row.name),
            created_at=now,
        )
        db.add(patient)
        db.add(identity)
        row.status, row.error_code, row.patient_id = "imported", None, patient.patient_id
        identities[row.external_patient_id] = identity
        patients_by_name[row.normalized_name] = patient

    batch.status = "committed"
    batch.committed_at = now
    result = _out(db, batch)
    add_audit(
        db,
        actor_id=ctx.user_id,
        actor_role=ctx.role,
        action="patient_import_committed",
        target_type="import_batch",
        target_id=batch.batch_id,
        clinic_id=ctx.clinic_id,
        patient_id=None,
        details={"source_system": batch.source_system, **result.counts},
    )
    db.commit()
    return _out(db, batch)
