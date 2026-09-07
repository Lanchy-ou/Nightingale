from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select, func, update
from app.db import SessionLocal, engine
from app.models import Task
from app.result_models import NotificationJob, InboxNotification, NotificationSettings
from app.notifications import reconcile_notifications, sweep
from app.result_schema import migrate_results
from app.test_result_service import utc


def test_migration_is_repeatable_and_preserves_data(db_session):
    before = db_session.scalar(select(func.count()).select_from(Task))
    migrate_results(engine)
    migrate_results(engine)
    assert db_session.scalar(select(func.count()).select_from(Task)) == before


def test_durable_deduplicated_and_resolved(monkeypatch, db_session):
    monkeypatch.setenv("NANTINGALE_NOTIFICATIONS_ENABLED", "true")
    now = datetime(2026, 9, 6)
    reconcile_notifications(db_session, now=now)
    db_session.commit()
    assert sweep(SessionLocal, now=now) > 0
    with SessionLocal() as fresh:
        count = fresh.scalar(select(func.count()).select_from(InboxNotification))
    sweep(SessionLocal, now=now)
    with SessionLocal() as fresh:
        assert fresh.scalar(select(func.count()).select_from(InboxNotification)) == count
        job = fresh.scalar(select(NotificationJob).where(NotificationJob.target_type == "task", NotificationJob.status == "delivered"))
        fresh.get(Task, job.target_id).status = "completed"
        fresh.commit()
        notification = fresh.scalar(select(InboxNotification).where(InboxNotification.job_id == job.job_id))
        assert notification.resolved_at is not None


def test_two_workers_and_expired_lease(monkeypatch, db_session):
    monkeypatch.setenv("NANTINGALE_NOTIFICATIONS_ENABLED", "true")
    now = datetime(2026, 9, 6)
    reconcile_notifications(db_session, now=now)
    db_session.commit()
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: sweep(SessionLocal, now=now), [1, 2]))
    with SessionLocal() as fresh:
        assert fresh.scalar(select(func.count()).select_from(InboxNotification)) == fresh.scalar(select(func.count(func.distinct(InboxNotification.job_id))))
        job = fresh.scalar(select(NotificationJob).where(NotificationJob.status == "delivered"))
        job.status = "processing"
        job.lease_token = "crashed-worker"
        job.lease_until = now - timedelta(seconds=1)
        job_id = job.job_id
        fresh.commit()
    sweep(SessionLocal, now=now)
    with SessionLocal() as fresh:
        assert fresh.get(NotificationJob, job_id).status == "delivered"
        assert fresh.scalar(select(func.count()).select_from(InboxNotification).where(InboxNotification.job_id == job_id)) == 1


def test_retry_exhaustion_and_recovery(monkeypatch, db_session):
    monkeypatch.setenv("NANTINGALE_NOTIFICATIONS_ENABLED", "true")
    now = datetime(2026, 9, 6)
    def fail(_):
        raise RuntimeError("Synthetic provider failure - must not enter metadata")
    for minutes in (0, 1, 6, 21, 81):
        sweep(SessionLocal, now=now + timedelta(minutes=minutes), deliver_hook=fail)
    with SessionLocal() as fresh:
        job = fresh.scalar(select(NotificationJob).where(NotificationJob.status == "failed"))
        assert job and job.attempts == 5 and job.error_code == "inbox_delivery_failed"
        job_id = job.job_id
        job.status = "pending"
        job.attempts = 0
        job.due_at = now
        fresh.commit()
    sweep(SessionLocal, now=now + timedelta(minutes=82))
    with SessionLocal() as fresh:
        assert fresh.get(NotificationJob, job_id).status == "delivered"


def test_clinic_timezone_and_no_due(monkeypatch, db_session):
    assert utc(db_session, "clinic_001", datetime(2026, 9, 5, 8)) == datetime(2026, 9, 5)
    db_session.add(NotificationSettings(clinic_id="clinic_001", timezone="America/New_York", revision=1,
        review_hours=24, communication_hours=24, verification_hours=24, escalation_hours=24))
    db_session.flush()
    assert utc(db_session, "clinic_001", datetime(2026, 7, 1, 8)) == datetime(2026, 7, 1, 12)
    monkeypatch.setenv("NANTINGALE_NOTIFICATIONS_ENABLED", "true")
    task = db_session.scalar(select(Task).where(Task.assigned_role == "staff", Task.status == "open"))
    task.due_at = None
    reconcile_notifications(db_session)
    jobs = db_session.scalars(select(NotificationJob).where(NotificationJob.target_id == task.task_id)).all()
    assert jobs and all(job.stage == "initial" for job in jobs)


def test_read_does_not_complete_task_and_other_user_cannot_read(monkeypatch, clinician_client, patient_client, db_session):
    monkeypatch.setenv("NANTINGALE_NOTIFICATIONS_ENABLED", "true")
    sweep(SessionLocal, now=datetime(2026, 9, 6))
    response = clinician_client.get('/api/notifications').json()
    notification = response['items'][0]
    before = {task.task_id: task.status for task in db_session.scalars(select(Task)).all()}
    assert patient_client.post(f"/api/notifications/{notification['notification_id']}/read").status_code == 404
    assert clinician_client.post(f"/api/notifications/{notification['notification_id']}/read").status_code == 200
    assert clinician_client.get('/api/notifications').json()['unread_count'] == response['unread_count'] - 1
    db_session.expire_all()
    assert before == {task.task_id: task.status for task in db_session.scalars(select(Task)).all()}


def test_starting_task_does_not_repeat_assignment(monkeypatch, db_session):
    from app.notifications import task_version
    monkeypatch.setenv("NANTINGALE_NOTIFICATIONS_ENABLED", "true")
    task = db_session.scalar(select(Task).where(Task.assigned_role == 'staff', Task.status == 'open'))
    reconcile_notifications(db_session)
    version = task_version(task)
    task.status = 'in_progress'
    reconcile_notifications(db_session)
    assert task_version(task) == version
    jobs = db_session.scalars(select(NotificationJob).where(NotificationJob.target_id == task.task_id, NotificationJob.stage == 'initial')).all()
    assert len({j.recipient_id for j in jobs}) == len(jobs)
