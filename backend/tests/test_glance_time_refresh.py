"""Time advances without rewriting source records or calling a Provider."""
from datetime import timedelta

from sqlalchemy import select

from app.glance_projection import rebuild_glance_projections
from app.models import Event, GlanceProjection, Highlight, RankingRun, Task
from seed import fixture
from seed.highlights import SEED_AS_OF


def test_rebuild_expires_recency_at_seven_days(db_session):
    highlight = db_session.get(Highlight, "hl_headache_worsening")
    event = db_session.get(Event, highlight.event_id)
    for as_of, expected in (
        (event.started_at - timedelta(microseconds=1), False),
        (event.started_at, True),
        (event.started_at + timedelta(days=7), True),
        (event.started_at + timedelta(days=7, microseconds=1), False),
        (event.started_at + timedelta(days=365), False),
    ):
        rebuild_glance_projections(db_session, fixture.PATIENT_ID, as_of=as_of)
        assert highlight.feature_flags["recency"] is expected
        assert highlight.score_factors["base_factors"]["recency"] == (2 if expected else 0)
        assert highlight.feature_flags["symptom_change"] is True
        assert highlight.feature_flags["repeated_mentions"] is True
        assert highlight.adaptive_adjustment == 0


def test_maintenance_updates_only_changed_patients_and_is_idempotent(db_session):
    from app.glance_projection import refresh_time_sensitive_glance

    now = SEED_AS_OF + timedelta(days=365)
    rebuild_glance_projections(db_session, fixture.PATIENT_TASK_ID, as_of=now)
    untouched = db_session.scalar(select(GlanceProjection).where(
        GlanceProjection.patient_id == fixture.PATIENT_TASK_ID,
    ))
    assert untouched is not None
    untouched_id, untouched_time = untouched.projection_id, untouched.updated_at
    assert refresh_time_sensitive_glance(db_session, as_of=now) > 0
    highlight = db_session.get(Highlight, "hl_headache_worsening")
    assert highlight.feature_flags["recency"] is False
    db_session.expire_all()
    assert db_session.get(GlanceProjection, untouched_id).updated_at == untouched_time
    count = len(db_session.scalars(select(RankingRun)).all())
    assert refresh_time_sensitive_glance(db_session, as_of=now) == 0
    assert len(db_session.scalars(select(RankingRun)).all()) == count


def test_maintenance_updates_task_due_boundary_without_new_content(db_session):
    from app.glance_projection import refresh_time_sensitive_glance

    task = db_session.get(Task, "task_blood_test")
    task.assigned_role = "staff"
    task.assigned_user_id = fixture.USER_STAFF_ID
    task.due_at = SEED_AS_OF + timedelta(hours=1)
    db_session.flush()
    rebuild_glance_projections(db_session, fixture.PATIENT_ID, as_of=SEED_AS_OF)
    projection = db_session.scalar(select(GlanceProjection).join(Highlight).where(
        Highlight.task_id == task.task_id, GlanceProjection.viewer_role == "staff",
    ))
    assert projection.factor_explanation["overdue"] is False
    assert refresh_time_sensitive_glance(db_session, as_of=task.due_at) > 0
    db_session.expire_all()
    projection = db_session.scalar(select(GlanceProjection).join(Highlight).where(
        Highlight.task_id == task.task_id, GlanceProjection.viewer_role == "staff",
    ))
    assert projection.factor_explanation["overdue"] is True


def test_new_task_on_old_event_ages_without_losing_protection(db_session):
    now = SEED_AS_OF + timedelta(days=365)
    task = db_session.get(Task, "task_blood_test")
    task.created_at = now
    highlight = db_session.scalar(select(Highlight).where(Highlight.task_id == task.task_id))
    highlight.status = "pinned"
    highlight.feature_flags = {**highlight.feature_flags, "clinician_confirmed": True}
    for at, expected in ((now, True), (now + timedelta(days=8), False)):
        rebuild_glance_projections(db_session, fixture.PATIENT_ID, as_of=at)
        assert highlight.feature_flags["recency"] is expected
        assert highlight.feature_flags["unresolved_task"] is True
        assert highlight.feature_flags["clinician_confirmed"] is True
        projection = db_session.scalar(select(GlanceProjection).where(
            GlanceProjection.highlight_id == highlight.highlight_id,
            GlanceProjection.viewer_role == "clinician",
        ))
        # Protection must survive aging without bypassing workflow/role
        # eligibility (which is evaluated before protection).
        assert projection.factor_explanation["hard_protected"] is True
        assert projection.priority_band == 1
