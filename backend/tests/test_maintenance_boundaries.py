from sqlalchemy import event


def test_get_never_invokes_global_sweep(clinician_client, monkeypatch):
    from app import patient_review
    from app.api import highlights, tasks
    def forbidden(*args, **kwargs):
        raise AssertionError("GET invoked global maintenance")
    monkeypatch.setattr(patient_review, "materialize_due_escalations", forbidden)
    for module in (highlights, tasks):
        if hasattr(module, "materialize_due_escalations"):
            monkeypatch.setattr(module, "materialize_due_escalations", forbidden)
    assert clinician_client.get('/api/patients/pat_001/glance').status_code == 200
    assert clinician_client.get('/api/patients/pat_001/tasks').status_code == 200


def test_session_heartbeat_does_not_run_business_outbox(db_session, monkeypatch):
    from datetime import datetime, timedelta
    from fastapi.testclient import TestClient
    from sqlalchemy import select
    from app import notifications
    from app.main import app
    from app.models import AuthSession
    from seed import fixture
    monkeypatch.setenv('NANTINGALE_SECURE_COOKIES', 'false')
    with TestClient(app) as client:
        response = client.post('/api/auth/login', json={
            'email': fixture.DEMO_EMAILS[fixture.USER_CLINICIAN_ID],
            'password': fixture.DEMO_PASSWORD})
        assert response.status_code == 200
        row = db_session.scalars(select(AuthSession)).one()
        row.last_seen_at = datetime.now() - timedelta(days=1)
        db_session.commit()
        monkeypatch.setenv('NANTINGALE_NOTIFICATIONS_ENABLED', 'true')
        def forbidden(*args, **kwargs):
            raise AssertionError('authentication GET ran global notification work')
        monkeypatch.setattr(notifications, 'reconcile_notifications', forbidden)
        assert client.get('/api/patients/pat_001/glance').status_code == 200


def test_glance_and_tasks_get_do_not_write_domain(clinician_client, db_session):
    writes = []
    def capture(conn, cursor, statement, params, context, many):
        if statement.lstrip().upper().startswith(("UPDATE TASKS", "INSERT INTO TASKS",
                "UPDATE HIGHLIGHTS", "INSERT INTO GLANCE_PROJECTIONS", "DELETE FROM GLANCE_PROJECTIONS")):
            writes.append(statement)
    event.listen(db_session.bind, "before_cursor_execute", capture)
    try:
        assert clinician_client.get('/api/patients/pat_001/glance').status_code == 200
        assert clinician_client.get('/api/patients/pat_001/tasks').status_code == 200
    finally:
        event.remove(db_session.bind, "before_cursor_execute", capture)
    assert not writes


def test_worker_isolates_failure_and_recovers_lease(db_session, monkeypatch):
    from datetime import datetime, timedelta
    from sqlalchemy import select
    from app.db import SessionLocal
    from app import maintenance as m
    from app.models import Patient
    now = datetime.now()
    patients = db_session.scalars(select(Patient).limit(2)).all()
    for p in patients:
        m.enqueue(db_session, 'glance', p.patient_id, p.patient_id, p.clinic_id, now)
    db_session.commit()
    monkeypatch.setattr(m, 'discover', lambda *_: None)
    good = m.execute_job
    def fail_one(db, job, clock):
        if job['patient_id'] == patients[0].patient_id:
            raise ValueError('synthetic failure')
        good(db, job, clock)
    monkeypatch.setattr(m, 'execute_job', fail_one)
    assert m.sweep(SessionLocal, now=now) == 1
    failed = db_session.execute(select(m.jobs).where(m.jobs.c.status == 'pending')).mappings().one()
    assert failed['attempts'] == 1
    assert failed['due_at'] == now + timedelta(minutes=1)
    monkeypatch.setattr(m, 'execute_job', good)
    db_session.execute(m.jobs.update().where(m.jobs.c.job_id == failed['job_id']).values(
        status='processing', lease_token='dead-process', lease_until=now + timedelta(seconds=120)))
    db_session.commit()
    assert m.sweep(SessionLocal, now=now + timedelta(seconds=119)) == 0
    assert m.sweep(SessionLocal, now=now + timedelta(seconds=120)) == 1
    assert m.sweep(SessionLocal, now=now + timedelta(seconds=121)) == 0


def test_worker_stops_after_five_failures(db_session, monkeypatch):
    from datetime import datetime, timedelta
    from sqlalchemy import select
    from app.db import SessionLocal
    from app import maintenance as m
    from app.models import Patient
    p = db_session.scalars(select(Patient)).first()
    now = datetime.now()
    m.enqueue(db_session, 'glance', p.patient_id, p.patient_id, p.clinic_id, now)
    db_session.commit()
    monkeypatch.setattr(m, 'discover', lambda *_: None)
    monkeypatch.setattr(m, 'execute_job', lambda *_: (_ for _ in ()).throw(ValueError()))
    for minutes in (0, 1, 6, 21, 81):
        assert m.sweep(SessionLocal, now=now + timedelta(minutes=minutes)) == 0
    state = db_session.execute(select(m.jobs)).mappings().one()
    assert state['status'] == 'failed' and state['attempts'] == 5


def test_two_workers_claim_each_job_once(db_session, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from datetime import datetime
    from threading import Barrier, Lock
    from sqlalchemy import select
    from app.db import SessionLocal
    from app import maintenance as m
    from app.models import Patient
    now = datetime.now()
    p = db_session.scalars(select(Patient)).first()
    m.enqueue(db_session, 'glance', p.patient_id, p.patient_id, p.clinic_id, now)
    db_session.commit()
    barrier = Barrier(2)
    lock = Lock()
    executions = []
    monkeypatch.setattr(m, 'discover', lambda *_: None)
    original = m.execute_job
    def execute(db, job, clock):
        with lock:
            executions.append(job['job_id'])
        original(db, job, clock)
    monkeypatch.setattr(m, 'execute_job', execute)
    def run():
        barrier.wait(timeout=10)
        return m.sweep(SessionLocal, now=now)
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _: run(), range(2)))
    assert sum(results) == 1
    assert len(executions) == 1
