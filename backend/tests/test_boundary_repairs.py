"""Regression gates for the boundary repair release; synthetic data only."""
from datetime import datetime

import pytest
from sqlalchemy import select

from app.ingestion_service import commit_derived as persist_derived
from app.ai_pipeline import run_pipeline
from app.extraction import Candidate
from app.llm_client import MockLLMClient
from app.models import Artifact, Event, Highlight, Patient


def ingest(db, patient, suffix, quote="I have headaches."):
    now = datetime.now()
    event = Event(event_id=f"evt_boundary_{suffix}", patient_id=patient.patient_id,
                  clinic_id=patient.clinic_id, event_type="doctor_consult",
                  started_at=now, created_at=now)
    source = Artifact(artifact_id=f"art_boundary_{suffix}", event_id=event.event_id,
                      artifact_type="transcript", author_role="system", author_id=None,
                      content={"segments": [{"index": 0, "speaker": "patient", "text": quote}]},
                      created_at=now, version=1)
    db.add_all([event, source])
    db.commit()
    output = run_pipeline(db, event, source, "ai_doctor_consult_summary", now,
                          MockLLMClient(candidates=[Candidate(text="Headache", quote=quote,
                          risk_reason="Reported symptom", entity_type="symptom")]), "mock")
    _, ids = persist_derived(db, event, source, "ai_doctor_consult_summary", output,
                            None, "system", None, None)
    db.commit()
    return ids[0]


@pytest.mark.parametrize("same_clinic", [True, False])
def test_ingestion_does_not_rescore_another_patient(db_session, same_clinic):
    patients = db_session.scalars(select(Patient)).all()
    first = patients[0]
    other = next(p for p in patients if p.patient_id != first.patient_id
                 and (p.clinic_id == first.clinic_id) == same_clinic)
    first_id = ingest(db_session, first, "first")
    h = db_session.get(Highlight, first_id)
    before = (dict(h.feature_flags), h.importance_score, h.updated_at)
    second_id = ingest(db_session, other, "second")
    db_session.expire_all()
    h = db_session.get(Highlight, first_id)
    assert (h.feature_flags, h.importance_score, h.updated_at) == before
    assert db_session.get(Highlight, second_id).feature_flags["repeated_mentions"] is False


def test_same_patient_distinct_events_repeat(db_session):
    patient = db_session.scalars(select(Patient)).first()
    a = ingest(db_session, patient, "a")
    b = ingest(db_session, patient, "b")
    db_session.expire_all()
    assert all(db_session.get(Highlight, key).feature_flags["repeated_mentions"] for key in (a, b))


def test_same_event_representations_and_untrusted_update_ids(db_session):
    patient = db_session.scalars(select(Patient)).first()
    patient = Patient(patient_id='pat_single_event', clinic_id=patient.clinic_id, name='Single Event')
    db_session.add(patient)
    db_session.commit()
    first_id = ingest(db_session, patient, 'single-event')
    first = db_session.get(Highlight, first_id)
    other = db_session.scalars(select(Highlight).where(Highlight.patient_id != patient.patient_id)).first()
    before = (dict(other.feature_flags), other.importance_score, other.updated_at)
    event = db_session.get(Event, first.event_id)
    raw = Artifact(artifact_id='art_second_representation', event_id=event.event_id,
        artifact_type='transcript', author_role='system', version=1,
        created_at=datetime.now(), content={'text': 'I have head pain.'})
    db_session.add(raw)
    db_session.commit()
    output = run_pipeline(db_session, event, raw, 'ai_doctor_consult_summary', datetime.now(),
        MockLLMClient(candidates=[Candidate(text='Head pain', quote='I have head pain.',
        risk_reason='Symptom', entity_type='symptom')]), 'mock')
    output.recompute_existing = [other.highlight_id]
    _, ids = persist_derived(db_session, event, raw, 'ai_doctor_consult_summary', output,
                            None, 'system', None, None)
    db_session.expire_all()
    assert not first.feature_flags['repeated_mentions']
    assert not db_session.get(Highlight, ids[0]).feature_flags['repeated_mentions']
    assert (other.feature_flags, other.importance_score, other.updated_at) == before


@pytest.mark.parametrize("text", ["No severe symptoms.", "My mother has severe headaches.",
    "The headache was severe yesterday but is better now.", "If severe headache occurs, call us."])
def test_fallback_does_not_promote_negated_family_or_past(text):
    from app.deterministic_pipeline import build_fallback
    assert not any(c.explicit_risk for c in build_fallback({"text": text}).candidates)


def test_unicode_and_generic_labels():
    from app.extraction import normalize_entity_key, validate_candidate
    assert normalize_entity_key("symptom", "头痛") != normalize_entity_key("symptom", "腹痛")
    c = validate_candidate(Candidate(text="Medication mention", quote="Amitriptyline 10 mg",
                           risk_reason="Medication", entity_type="medication"))
    assert not c.entity_key


def test_chinese_mixed_assertions_keep_positive_clause():
    from app.deterministic_pipeline import build_fallback
    candidates = build_fallback({"text": "没有恶心，但头痛严重。"}).candidates
    assert any(c.explicit_risk and c.quote == "头痛严重" for c in candidates)


def test_concurrent_patient_events_are_rescored_at_commit(db_session, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from app.db import SessionLocal
    patient_id = db_session.scalars(select(Patient.patient_id)).first()
    barrier = Barrier(2)
    original = MockLLMClient.summarize
    def together(self, *args):
        barrier.wait(timeout=10)
        return original(self, *args)
    monkeypatch.setattr(MockLLMClient, 'summarize', together)
    def run(suffix):
        with SessionLocal() as db:
            return ingest(db, db.get(Patient, patient_id), suffix)
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(run, ['concurrent-a', 'concurrent-b']))
    db_session.expire_all()
    assert all(db_session.get(Highlight, key).feature_flags['repeated_mentions'] for key in ids)


def test_repair_is_repeatable_and_restore_refuses_later_edit(db_session):
    from app.boundary_repair import apply_patient, restore_patient
    patient = db_session.scalars(select(Patient)).first()
    patient = Patient(patient_id='pat_repair_isolated', clinic_id=patient.clinic_id, name='Repair Probe')
    db_session.add(patient)
    db_session.commit()
    hid = ingest(db_session, patient, 'repair')
    h = db_session.get(Highlight, hid)
    h.feature_flags = {**h.feature_flags, 'repeated_mentions': True}
    db_session.commit()
    repair_id = apply_patient(db_session, patient)
    db_session.commit()
    assert repair_id
    assert h.feature_flags['repeated_mentions'] is False
    assert apply_patient(db_session, patient) is None
    db_session.commit()
    assert restore_patient(db_session, repair_id)
    db_session.commit()
    assert h.feature_flags['repeated_mentions'] is True
    next_id = apply_patient(db_session, patient)
    db_session.commit()
    h.status = 'accepted'
    db_session.commit()
    with pytest.raises(ValueError, match='changed after repair'):
        restore_patient(db_session, next_id)


def test_semantic_repair_removes_unsupported_old_risk_flag(db_session):
    from app.boundary_repair import apply_patient
    patient = db_session.scalars(select(Patient)).first()
    hid = ingest(db_session, patient, 'negative-risk', quote='I have no headaches.')
    h = db_session.get(Highlight, hid)
    h.feature_flags = {**h.feature_flags, 'explicit_risk': True}
    db_session.commit()
    assert apply_patient(db_session, patient)
    db_session.commit()
    assert not h.feature_flags['explicit_risk']
