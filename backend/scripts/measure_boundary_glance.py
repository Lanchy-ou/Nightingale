"""Isolated 10,000-review backlog benchmark; never opens the product database."""
import json
import os
import platform
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    root = Path(tempfile.mkdtemp(prefix='nightingale-boundary-perf-'))
    os.environ['NANTINGALE_DB_URL'] = f"sqlite:///{root / 'benchmark.db'}"
    os.environ['NANTINGALE_DEMO_AUTH'] = 'true'
    os.environ['NANTINGALE_LLM_PROVIDER'] = 'mock'
    os.environ['NANTINGALE_NOTIFICATIONS_ENABLED'] = 'false'
    from sqlalchemy import event as sql_event, select
    from fastapi.testclient import TestClient
    from app.db import engine, SessionLocal
    from app.main import app
    from app.models import Clinic, Patient, User, Event, Artifact, PatientCheckInSession, Task, CareWorkflow
    from app.maintenance import sweep, jobs
    from seed.seed import create_schema, seed
    create_schema(engine)
    with SessionLocal() as db:
        seed(db)
        clinics = list(db.scalars(select(Clinic.clinic_id)))
        now = datetime(2026, 9, 8, 12)
        for i in range(100):
            clinic = clinics[i % len(clinics)]
            patient = f'perf_patient_{i}'
            db.add(Patient(patient_id=patient, clinic_id=clinic, name=f'Synthetic performance {i}'))
            db.add(User(user_id=f'perf_user_{i}', clinic_id=clinic, patient_id=patient,
                        role='patient', name='Synthetic performance user'))
        db.commit()
        for batch in range(100):
            for j in range(100):
                i = batch * 100 + j
                patient = f'perf_patient_{i % 100}'
                clinic = clinics[i % len(clinics)]
                event_id, raw_id = f'perf_event_{i}', f'perf_raw_{i}'
                db.add(Event(event_id=event_id, patient_id=patient, clinic_id=clinic,
                    event_type='patient_followup', started_at=now - timedelta(hours=1), created_at=now))
                db.add(Artifact(artifact_id=raw_id, event_id=event_id, artifact_type='raw_conversation',
                    author_role='patient', author_id=f'perf_user_{i % 100}',
                    content={'messages': [{'id': f'm_{i}', 'speaker': 'patient', 'text': 'Nausea is still present.'}]},
                    created_at=now, version=1))
                db.add(Artifact(artifact_id=f'perf_summary_{i}', event_id=event_id,
                    artifact_type='ai_patient_session_summary', author_role='system',
                    content={'summary': 'Nausea is still present.'}, created_at=now, version=1))
                db.add(PatientCheckInSession(session_id=f'perf_session_{i}', patient_id=patient,
                    clinic_id=clinic, patient_user_id=f'perf_user_{i % 100}', event_id=event_id,
                    raw_artifact_id=raw_id, status='submitted', started_at=now, created_at=now,
                    updated_at=now, submitted_at=now))
                db.flush()
                db.add(CareWorkflow(workflow_id=f'perf_workflow_{i}', clinic_id=clinic,
                    patient_id=patient, root_event_id=event_id, workflow_kind='patient_report_response',
                    status='active', created_by_role='system', created_at=now, updated_at=now))
                db.add(Task(task_id=f'perf_task_{i}', patient_id=patient, clinic_id=clinic,
                    event_id=event_id, title='Synthetic review', description='',
                    workflow_id=f'perf_workflow_{i}',
                    task_kind='patient_report_review', assigned_role='staff', patient_visible=False,
                    status='open', created_by=f'perf_user_{i % 100}', created_at=now, updated_at=now,
                    due_at=now - timedelta(minutes=5), escalate_at=now - timedelta(minutes=5)))
            db.commit()
    writes = []
    def capture(conn, cursor, statement, params, ctx, many):
        # ASGI request execution uses AnyIO worker threads; maintenance has its
        # own explicitly named thread. Count all request SQL writes.
        if 'AnyIO' in threading.current_thread().name and statement.lstrip().upper().startswith(('UPDATE ', 'INSERT ', 'DELETE ')):
            writes.append(statement.split()[0])
    sql_event.listen(engine, 'before_cursor_execute', capture)
    results = {}
    stop = threading.Event()
    worker_count = []
    def worker():
        while not stop.is_set():
            worker_count.append(sweep(SessionLocal, now=now))
    with TestClient(app, headers={'X-User-Id': 'usr_clinician_01'}) as client:
        for mode in ('stopped', 'running'):
            thread = None
            if mode == 'running':
                thread = threading.Thread(target=worker, name='boundary-maintenance')
                thread.start()
            for _ in range(10):
                client.get('/api/patients/pat_001/glance')
            samples, errors = [], 0
            for _ in range(100):
                started = time.perf_counter()
                response = client.get('/api/patients/pat_001/glance')
                samples.append((time.perf_counter() - started) * 1000)
                errors += response.status_code != 200
            results[mode] = {'p95_ms': round(sorted(samples)[94], 3), 'errors': errors,
                             'samples': 100, 'warmups': 10}
            if thread:
                stop.set()
                thread.join()
    with SessionLocal() as db:
        failed = list(db.scalars(select(jobs.c.job_id).where(jobs.c.status == 'failed')))
        pending_errors = list(db.scalars(select(jobs.c.job_id).where(jobs.c.error_code.is_not(None))))
    report = {'platform': platform.platform(), 'python': platform.python_version(),
        'layer': 'TestClient + real file SQLite; not network/deployment capacity',
        'backlog_reviews': 10000, 'backlog_patients': 100, 'clinics': len(clinics),
        'glance': results, 'request_sql_writes': len(writes), 'completed_jobs': sum(worker_count),
        'worker_failed_jobs': len(failed), 'worker_retry_jobs': len(pending_errors)}
    Path(args.output).write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))
    assert not writes and not pending_errors
    assert all(r['p95_ms'] <= 300 and r['errors'] == 0 for r in results.values())


if __name__ == '__main__':
    main()
