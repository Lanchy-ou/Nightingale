"""Preview/apply/guarded restore of derived repetition data; never calls an LLM."""
import hashlib
import json
from datetime import datetime

from sqlalchemy import Column, DateTime, JSON, String, Table, select, delete

from .audit import add_audit
from .db import Base
from .glance_projection import rebuild_glance_projections
from .ids import new_id
from .models import Highlight, Patient, Artifact, GlanceProjection
from .repeated_mentions import RULE_VERSION, recompute_repeated, repetition_changes, scoped_highlights

repairs = Table("boundary_repairs", Base.metadata,
    Column("repair_id", String(64), primary_key=True),
    Column("patient_id", String(64), nullable=False),
    Column("clinic_id", String(64), nullable=False),
    Column("rule_version", String(64), nullable=False),
    Column("before_state", JSON, nullable=False),
    Column("after_hash", String(64), nullable=False),
    Column("created_at", DateTime, nullable=False),
    Column("restored_at", DateTime))

FIELDS = ("feature_flags", "base_importance_score", "adaptive_adjustment",
          "decay_adjustment", "importance_score", "score_factors", "score_rule_version",
          "learning_metadata", "status", "status_history", "review_status")


def snapshot(rows):
    return {h.highlight_id: {**{key: getattr(h, key) for key in FIELDS},
                            "updated_at": h.updated_at.isoformat()}
            for h in rows}


def digest(state):
    return hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()


def full_state(db, rows, patient_id):
    projections = [dict(row) for row in db.execute(select(GlanceProjection.__table__).where(
        GlanceProjection.patient_id == patient_id)).mappings()]
    for row in projections:
        for key, value in row.items():
            if isinstance(value, datetime):
                row[key] = value.isoformat()
    sources = {}
    for source_id in sorted({h.source_artifact_id for h in rows if h.source_artifact_id}):
        source = db.get(Artifact, source_id)
        sources[source_id] = {"version": source.version, "hash": digest(source.content)} if source else None
    return {"highlights": snapshot(rows), "projections": sorted(projections, key=lambda r: r["projection_id"]),
            "sources": sources}


def apply_patient(db, patient, *, as_of=None, mode="semantics"):
    # Obtain the SQLite writer lock before reading the state to be repaired.
    db.execute(Highlight.__table__.update().where(
        Highlight.patient_id == patient.patient_id).values(updated_at=Highlight.updated_at))
    rows = scoped_highlights(db, patient.patient_id, patient.clinic_id)
    legacy = True
    semantics = {}
    if not semantics and not repetition_changes(db, patient.patient_id, patient.clinic_id, legacy=legacy):
        return None
    now = as_of or datetime.now()
    before = full_state(db, rows, patient.patient_id)
    for h in rows:
        if h.highlight_id in semantics:
            h.semantic_context = semantics[h.highlight_id]
            h.updated_at = now
    count = recompute_repeated(db, patient.patient_id, patient.clinic_id, as_of=now, legacy=legacy)
    rebuild_glance_projections(db, patient.patient_id, as_of=now)
    repair_id = new_id("repair")
    db.execute(repairs.insert().values(repair_id=repair_id, patient_id=patient.patient_id,
        clinic_id=patient.clinic_id, rule_version="repetition-patient-v1" if legacy else RULE_VERSION, before_state=before,
        after_hash=digest(full_state(db, rows, patient.patient_id)), created_at=now))
    add_audit(db, actor_id=None, actor_role="system", action="boundary_repair",
        target_type="patient", target_id=patient.patient_id, clinic_id=patient.clinic_id,
        patient_id=patient.patient_id, details={"repair_id": repair_id,
        "rule_version": "repetition-patient-v1" if legacy else RULE_VERSION, "changed_count": count, "semantic_count": len(semantics)})
    return repair_id


def restore_patient(db, repair_id):
    db.execute(repairs.update().where(repairs.c.repair_id == repair_id)
               .values(after_hash=repairs.c.after_hash))
    record = db.execute(select(repairs).where(repairs.c.repair_id == repair_id)).mappings().one()
    if record["restored_at"]:
        return False
    rows = scoped_highlights(db, record["patient_id"], record["clinic_id"])
    if digest(full_state(db, rows, record["patient_id"])) != record["after_hash"]:
        raise ValueError("Derived state changed after repair; automatic restore refused")
    for h in rows:
        old = record["before_state"]["highlights"][h.highlight_id]
        for key in FIELDS:
            setattr(h, key, old[key])
        h.updated_at = datetime.fromisoformat(old["updated_at"])
    db.execute(delete(GlanceProjection).where(GlanceProjection.patient_id == record["patient_id"]))
    for row in record["before_state"]["projections"]:
        values = dict(row)
        for column in GlanceProjection.__table__.columns:
            if isinstance(column.type, DateTime) and values.get(column.name):
                values[column.name] = datetime.fromisoformat(values[column.name])
        db.execute(GlanceProjection.__table__.insert().values(**values))
    db.execute(repairs.update().where(repairs.c.repair_id == repair_id)
               .values(restored_at=datetime.now()))
    add_audit(db, actor_id=None, actor_role="system", action="boundary_repair_restore",
        target_type="patient", target_id=record["patient_id"], clinic_id=record["clinic_id"],
        patient_id=record["patient_id"], details={"repair_id": repair_id})
    return True


def exclude_pre_repair_runs(db, runs):
    """Keep history intact; never train/evaluate on known pre-repair decisions."""
    cutoffs = {}
    for row in db.execute(select(repairs)).mappings():
        key = (row["clinic_id"], row["patient_id"])
        cutoff = row["restored_at"] or row["created_at"]
        cutoffs[key] = max(cutoffs.get(key, cutoff), cutoff)
    return [run for run in runs if run.evaluated_at > cutoffs.get(
        (run.clinic_id, run.patient_id), datetime.min)]
