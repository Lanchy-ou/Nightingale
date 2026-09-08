from app.semantic_rules import interpret, repetition_key


def test_synonyms_and_unknown_time():
    keys = {repetition_key(interpret(q, "symptom")) for q in
            ("I have headaches.", "I have head pain.", "我现在头痛。")}
    assert keys == {"symptom:headache"}
    assert not repetition_key(interpret("Headache", "symptom"))
    assert not repetition_key(interpret("My mother has headaches.", "symptom"))
    assert not repetition_key(interpret("I have no headaches.", "symptom"))
    assert not repetition_key(interpret("I had headaches yesterday.", "symptom"))


def test_unknown_does_not_merge():
    assert not repetition_key(interpret("I have an unusual sensation.", "symptom"))


def test_backfill_refuses_changed_source(db_session):
    from app.boundary_repair import semantic_updates
    from app.models import Highlight, Artifact
    from sqlalchemy import select
    highlight = db_session.scalars(select(Highlight).where(Highlight.source_artifact_id.is_not(None))).first()
    source = db_session.get(Artifact, highlight.source_artifact_id)
    source.content = {"text": "changed source"}
    db_session.flush()
    assert highlight.highlight_id not in semantic_updates(db_session, [highlight])
