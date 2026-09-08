"""Database-backed, bounded maintenance. Run separately from the API process."""
from datetime import datetime, timedelta

from sqlalchemy import Column, DateTime, Integer, String, Table, or_, select
from sqlalchemy.dialects.sqlite import insert

from .db import Base
from .glance_projection import due_glance_patients, rebuild_glance_projections
from .ids import new_id, stable_id
from .models import Patient, Task
from .patient_review import materialize_due_escalations

jobs = Table("maintenance_jobs", Base.metadata,
    Column("job_id", String(64), primary_key=True),
    Column("kind", String(32), nullable=False),
    Column("target_id", String(64), nullable=False),
    Column("patient_id", String(64), nullable=False),
    Column("clinic_id", String(64), nullable=False),
    Column("status", String(16), nullable=False, index=True),
    Column("attempts", Integer, nullable=False),
    Column("due_at", DateTime, nullable=False, index=True),
    Column("lease_token", String(64)), Column("lease_until", DateTime),
    Column("error_code", String(64)))


def enqueue(db, kind, target_id, patient_id, clinic_id, now):
    query = insert(jobs).values(job_id=stable_id("maintenance", kind, target_id),
        kind=kind, target_id=target_id, patient_id=patient_id, clinic_id=clinic_id,
        status="pending", attempts=0, due_at=now)
    # A refreshed patient may cross another time boundary later. Failed work
    # remains failed until explicitly retried; scans cannot reset its attempts.
    if kind == "glance":
        query = query.on_conflict_do_update(index_elements=["job_id"],
            set_={"status": "pending", "attempts": 0, "due_at": now},
            where=jobs.c.status == "done")
    else:
        query = query.on_conflict_do_nothing()
    db.execute(query)


def discover(db, now, batch_size):
    tasks = db.scalars(select(Task).where(Task.task_kind == "patient_report_review",
        Task.status.in_(("open", "in_progress")), Task.escalate_at <= now,
        Task.escalated_at.is_(None), ~select(jobs.c.job_id).where(
            jobs.c.kind == "escalate", jobs.c.target_id == Task.task_id).exists())
        .order_by(Task.escalate_at, Task.task_id).limit(batch_size)).all()
    for task in tasks:
        enqueue(db, "escalate", task.task_id, task.patient_id, task.clinic_id, now)
    # Time-boundary detection reads only persisted metadata, never a provider.
    pending = set(db.scalars(select(jobs.c.target_id).where(
        jobs.c.kind == "glance", jobs.c.status != "done")))
    for patient_id in sorted(due_glance_patients(db, as_of=now) - pending)[:batch_size]:
        patient = db.get(Patient, patient_id)
        enqueue(db, "glance", patient_id, patient_id, patient.clinic_id, now)


def ready(now):
    return or_((jobs.c.status == "pending") & (jobs.c.due_at <= now),
               (jobs.c.status == "processing") & (jobs.c.lease_until <= now))


def execute_job(db, job, now):
    patient = db.get(Patient, job["patient_id"])
    if patient is None or patient.clinic_id != job["clinic_id"]:
        raise ValueError("maintenance_scope_invalid")
    if job["kind"] == "escalate":
        task = db.get(Task, job["target_id"])
        if task is None or task.patient_id != patient.patient_id or task.clinic_id != patient.clinic_id:
            raise ValueError("maintenance_scope_invalid")
        materialize_due_escalations(db, task_id=task.task_id, as_of=now)
    elif job["kind"] == "glance":
        rebuild_glance_projections(db, patient.patient_id, as_of=now)
    else:
        raise ValueError("maintenance_kind_invalid")


def sweep(session_factory, *, now=None, batch_size=50):
    now = now or datetime.now()
    with session_factory() as db:
        discover(db, now, batch_size)
        db.commit()
        ids = list(db.scalars(select(jobs.c.job_id).where(ready(now))
            .order_by(jobs.c.due_at, jobs.c.job_id).limit(batch_size)))
    completed = 0
    for job_id in ids:
        token = new_id("lease")
        with session_factory() as db:
            claim = db.execute(jobs.update().where(jobs.c.job_id == job_id, ready(now))
                .values(status="processing", lease_token=token, lease_until=now + timedelta(seconds=120)))
            db.commit()
            if claim.rowcount != 1:
                continue
        try:
            with session_factory() as db:
                locked = db.execute(jobs.update().where(jobs.c.job_id == job_id,
                    jobs.c.lease_token == token, jobs.c.status == "processing")
                    .values(lease_until=now + timedelta(seconds=120)))
                if locked.rowcount != 1:
                    continue
                job = db.execute(select(jobs).where(jobs.c.job_id == job_id)).mappings().one()
                execute_job(db, job, now)
                db.execute(jobs.update().where(jobs.c.job_id == job_id).values(
                    status="done", lease_token=None, lease_until=None, error_code=None))
                db.commit()
                completed += 1
        except Exception:
            with session_factory() as db:
                job = db.execute(select(jobs).where(jobs.c.job_id == job_id,
                    jobs.c.lease_token == token)).mappings().first()
                if job:
                    attempts = job["attempts"] + 1
                    db.execute(jobs.update().where(jobs.c.job_id == job_id,
                        jobs.c.lease_token == token).values(attempts=attempts,
                        status="failed" if attempts >= 5 else "pending",
                        due_at=now + timedelta(minutes=(1, 5, 15, 60)[min(attempts - 1, 3)]),
                        error_code="maintenance_failed", lease_token=None, lease_until=None))
                    db.commit()
    return completed
