from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from app.attention_items import build_attention_items
from app.models import CareWorkflow, Task, WorkflowLink
from app.workflow_state import derive_task_workflow_state
from seed import fixture


FROZEN_AS_OF = datetime(2026, 9, 2, 12, 0)


def test_synthetic_replay_is_scope_isolated_and_has_surfaced_unsurfaced_candidates(
    db_session,
):
    clinic_a = build_attention_items(
        db_session,
        patient_id=fixture.PATIENT_ID,
        viewer_role="clinician",
        as_of=FROZEN_AS_OF,
    )
    clinic_b = build_attention_items(
        db_session,
        patient_id=fixture.PATIENT_OTHER_ID,
        viewer_role="clinician",
        as_of=FROZEN_AS_OF,
    )
    assert len([item for item in clinic_a if item.eligible]) > 5
    assert {item.clinic_id for item in clinic_a} == {fixture.CLINIC_ID}
    assert {item.clinic_id for item in clinic_b} == {fixture.CLINIC_B_ID}
    assert not ({item.source_id for item in clinic_a} & {item.source_id for item in clinic_b})


def test_workflow_links_are_metadata_only_and_frontier_is_replayable(db_session):
    workflows = db_session.scalars(select(CareWorkflow)).all()
    links = db_session.scalars(select(WorkflowLink)).all()
    assert workflows and links
    forbidden = {"text", "quote", "title", "description", "content", "comment"}
    for link in links:
        assert not forbidden & set(link.__dict__)
    for task in db_session.scalars(select(Task)).all():
        first = derive_task_workflow_state(db_session, task, as_of=FROZEN_AS_OF)
        second = derive_task_workflow_state(db_session, task, as_of=FROZEN_AS_OF)
        assert first == second
