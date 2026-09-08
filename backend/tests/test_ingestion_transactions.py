from datetime import datetime
import pytest
from sqlalchemy import create_engine, inspect, select, event as sqlalchemy_event

from app.models import Artifact, Event, Patient, Highlight
from app.extraction import Candidate
from app.ai_pipeline import run_pipeline, persist_derived
from app.llm_client import MockLLMClient
from app.ingestion_service import commit_derived


def source(db):
    patient = db.scalars(select(Patient)).first()
    now = datetime.now()
    e = Event(event_id='evt_transaction', patient_id=patient.patient_id, clinic_id=patient.clinic_id,
              event_type='doctor_consult', started_at=now, created_at=now)
    a = Artifact(artifact_id='art_transaction', event_id=e.event_id, artifact_type='transcript',
                 author_role='system', content={'text': 'I have headaches.'}, created_at=now, version=1)
    db.add_all([e, a])
    db.commit()
    output = run_pipeline(db, e, a, 'ai_doctor_consult_summary', now,
        MockLLMClient(candidates=[Candidate(text='Headache', quote='I have headaches.',
            risk_reason='Symptom', entity_type='symptom')]), 'mock')
    return e, a, output


def test_persistence_does_not_commit(db_session, monkeypatch):
    e, a, output = source(db_session)
    monkeypatch.setattr(db_session, 'commit', lambda: pytest.fail('low-level commit'))
    sid, _ = persist_derived(db_session, e, a, 'ai_doctor_consult_summary', output, None, 'system', None, None)
    assert db_session.get(Artifact, sid)
    db_session.rollback()
    assert db_session.get(Artifact, sid) is None
    assert db_session.get(Artifact, a.artifact_id)


@pytest.mark.parametrize('stage', ['summary', 'highlight', 'audit', 'projection'])
def test_derived_failure_preserves_raw_and_rolls_back_all(db_session, monkeypatch, stage):
    e, a, output = source(db_session)
    from app import audit, glance_projection
    def fail(*args, **kwargs):
        raise RuntimeError('injected failure')
    if stage == 'audit':
        monkeypatch.setattr(audit, 'add_audit', fail)
    elif stage == 'projection':
        monkeypatch.setattr(glance_projection, 'rebuild_glance_projections', fail)
    model = Artifact if stage == 'summary' else Highlight if stage == 'highlight' else None
    if model is not None:
        sqlalchemy_event.listen(model, 'before_insert', fail)
    try:
        with pytest.raises(RuntimeError):
            commit_derived(db_session, e, a, 'ai_doctor_consult_summary', output, None, 'system', None, None)
    finally:
        if model is not None:
            sqlalchemy_event.remove(model, 'before_insert', fail)
    assert db_session.get(Artifact, a.artifact_id)
    assert db_session.scalars(select(Artifact).where(Artifact.event_id == e.event_id)).all() == [a]


def test_boundary_migration_is_additive_and_repeatable():
    from app.schema_migrations import migrate_boundary_schema
    target = create_engine('sqlite://')
    with target.begin() as c:
        c.exec_driver_sql('CREATE TABLE highlights (highlight_id TEXT PRIMARY KEY, text TEXT)')
        c.exec_driver_sql("INSERT INTO highlights VALUES ('old', 'Synthetic original')")
    migrate_boundary_schema(target)
    migrate_boundary_schema(target)
    with target.connect() as c:
        assert c.exec_driver_sql('SELECT text FROM highlights').scalar() == 'Synthetic original'
    assert {'maintenance_jobs', 'boundary_repairs'} <= set(inspect(target).get_table_names())
