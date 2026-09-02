"""F_A1 Coverage Review, explicit signal and Shadow policy endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..audit import add_audit
from ..authz import authorize, authorize_scope, require_auth, resource_not_found
from ..db import get_db
from ..clinic_scope import load_patient, load_ranking_decision_with_run
from ..glance_projection import rebuild_glance_projections
from ..ids import new_id
from ..models import (
    Highlight,
    LearningEvaluation,
    LearningPolicyVersion,
    LearningSignal,
    Patient,
    RankingDecision,
    RankingRun,
    Task,
)
from ..role_context import RoleContext
from ..provenance_binding import resolve_highlight_source
from ..schemas import (
    LearningEvaluationOut,
    LearningFreezeRequest,
    LearningReplayRequest,
    LearningSignalCreate,
    LearningSignalOut,
)
from ..shadow_learning import (
    DEMOTION_REASONS,
    QUALITY_REASONS,
    SERVING_MODE,
    active_policy,
    ensure_learning_policies,
    evaluate_runs,
    is_negative_protected,
)

router = APIRouter(prefix="/api", tags=["shadow-learning"])


def _coverage_item(db: Session, decision: RankingDecision) -> dict:
    highlight = db.get(Highlight, decision.highlight_id)
    if highlight is None:
        raise resource_not_found()
    return {
        "decision_id": decision.decision_id,
        "highlight_id": decision.highlight_id,
        "text": highlight.text,
        "entity_type": highlight.entity_type,
        "task_id": highlight.task_id,
        "eligible": decision.eligible,
        "exclusion_reason": decision.exclusion_reason,
        "priority_band": decision.priority_band,
        "base_score": decision.base_score,
        "shadow_adjustment": decision.shadow_adjustment,
        "shadow_score": decision.shadow_score,
        "base_rank": decision.base_rank,
        "shadow_rank": decision.shadow_rank,
        "surfaced_base": decision.surfaced_base,
        "surfaced_shadow": decision.surfaced_shadow,
        "source_binding_status": decision.source_binding_status,
        "factor_snapshot": decision.factor_snapshot,
    }


@router.get("/patients/{patient_id}/coverage-review")
def coverage_review(
    patient_id: str,
    viewer_role: str = Query(..., pattern="^(staff|clinician)$"),
    run_id: str | None = None,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    patient = load_patient(db, ctx, patient_id)
    if patient is None:
        raise resource_not_found()
    authorize(ctx, "read_coverage_review", patient.clinic_id, patient.patient_id)
    if viewer_role != ctx.role:
        raise HTTPException(status_code=403, detail="Coverage Review is role-specific")
    query = select(RankingRun).where(
        RankingRun.patient_id == patient_id,
        RankingRun.clinic_id == patient.clinic_id,
        RankingRun.viewer_role == viewer_role,
    )
    if run_id:
        query = query.where(RankingRun.run_id == run_id)
    run = db.scalar(query.order_by(RankingRun.evaluated_at.desc(), RankingRun.run_id.desc()))
    if run is None:
        raise resource_not_found()
    decisions = db.scalars(
        select(RankingDecision)
        .where(RankingDecision.run_id == run.run_id)
        .order_by(
            RankingDecision.eligible.desc(),
            RankingDecision.base_rank.is_(None),
            RankingDecision.base_rank,
            RankingDecision.priority_band,
            RankingDecision.decision_id,
        )
    ).all()
    policy = active_policy(db, patient.clinic_id)
    top = [_coverage_item(db, row) for row in decisions if row.surfaced_base]
    unsurfaced = [
        _coverage_item(db, row) for row in decisions if row.eligible and not row.surfaced_base
    ]
    excluded = [_coverage_item(db, row) for row in decisions if not row.eligible]
    return {
        "run_id": run.run_id,
        "patient_id": patient_id,
        "viewer_role": viewer_role,
        "serving_mode": SERVING_MODE,
        "shadow_policy": policy.version_name,
        "shadow_only": True,
        "evaluated_at": run.evaluated_at,
        "base_top_five": top,
        "eligible_unsurfaced": unsurfaced,
        "excluded": excluded,
    }


@router.post(
    "/ranking-decisions/{decision_id}/signals", response_model=LearningSignalOut
)
def submit_learning_signal(
    decision_id: str,
    body: LearningSignalCreate,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    scoped = load_ranking_decision_with_run(db, ctx, decision_id)
    if scoped is None:
        raise resource_not_found()
    decision, run = scoped
    authorize_scope(ctx, run.clinic_id, run.patient_id)
    authorize(ctx, "submit_learning_signal", run.clinic_id, run.patient_id)
    if body.signal_type == "explicit_demotion" and ctx.role != "clinician":
        raise HTTPException(status_code=403, detail="Only clinicians may teach ranking")
    if body.signal_type == "explicit_demotion" and body.reason_code not in DEMOTION_REASONS:
        raise HTTPException(status_code=422, detail="Invalid demotion reason")
    if body.signal_type == "quality_issue" and body.reason_code not in QUALITY_REASONS:
        raise HTTPException(status_code=422, detail="Invalid quality reason")
    highlight = db.get(Highlight, decision.highlight_id)
    if highlight is None:
        raise resource_not_found()
    task = db.get(Task, highlight.task_id) if highlight.task_id else None
    protected = is_negative_protected(highlight, task)
    current_binding = (
        "not_applicable"
        if highlight.source_artifact_id is None and highlight.source_span is None
        else resolve_highlight_source(db, highlight).status
    )
    eligible_for_shadow = bool(
        body.signal_type == "explicit_demotion"
        and decision.eligible
        and current_binding in {"current", "historical", "not_applicable"}
        and not protected
    )
    if body.signal_type == "quality_issue":
        ineligibility = "quality_signal_not_ranking_feedback"
    elif protected:
        ineligibility = "negative_generalization_protected"
    elif not decision.eligible:
        ineligibility = "candidate_not_eligible"
    elif current_binding not in {"current", "historical", "not_applicable"}:
        ineligibility = "source_binding_invalid"
    else:
        ineligibility = None
    independence_key = f"{run.clinic_id}:{ctx.user_id}:{decision.workflow_id or decision.highlight_id}"
    previous = db.scalar(
        select(LearningSignal)
        .where(
            LearningSignal.decision_id == decision_id,
            LearningSignal.actor_id == ctx.user_id,
            LearningSignal.signal_type == body.signal_type,
        )
        .order_by(LearningSignal.created_at.desc(), LearningSignal.signal_id.desc())
    )
    policy = active_policy(db, run.clinic_id)
    now = datetime.now()
    signal = LearningSignal(
        signal_id=new_id("lsg"),
        decision_id=decision_id,
        clinic_id=run.clinic_id,
        actor_id=ctx.user_id,
        actor_role=ctx.role,
        signal_type=body.signal_type,
        reason_code=body.reason_code,
        feedback_key=decision.feedback_key,
        signal_value=-1 if body.signal_type == "explicit_demotion" else 0,
        eligible_for_shadow=eligible_for_shadow,
        ineligibility_reason=ineligibility,
        independence_key=independence_key,
        policy_version=policy.version_name,
        supersedes_signal_id=previous.signal_id if previous else None,
        created_at=now,
    )
    db.add(signal)
    add_audit(
        db,
        actor_id=ctx.user_id,
        actor_role=ctx.role,
        action="learning_signal",
        target_type="highlight",
        target_id=decision.highlight_id,
        clinic_id=run.clinic_id,
        patient_id=run.patient_id,
        details={
            "decision_id": decision_id,
            "signal_type": body.signal_type,
            "reason_code": body.reason_code,
            "eligible_for_shadow": eligible_for_shadow,
            "ineligibility_reason": ineligibility,
        },
    )
    db.flush()
    rebuild_glance_projections(db, run.patient_id, as_of=now)
    db.commit()
    return db.get(LearningSignal, signal.signal_id)


@router.get("/admin/learning/status")
def learning_status(
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    authorize(ctx, "admin_learning", ctx.clinic_id, None)
    policy = active_policy(db, ctx.clinic_id)
    policies = db.scalars(
        select(LearningPolicyVersion)
        .where(LearningPolicyVersion.clinic_id == ctx.clinic_id)
        .order_by(LearningPolicyVersion.created_at, LearningPolicyVersion.version_name)
    ).all()
    latest = db.scalar(
        select(LearningEvaluation)
        .where(LearningEvaluation.clinic_id == ctx.clinic_id)
        .order_by(LearningEvaluation.created_at.desc(), LearningEvaluation.evaluation_id.desc())
    )
    return {
        "serving_mode": SERVING_MODE,
        "shadow_only": True,
        "active_policy": policy.version_name,
        "frozen": policy.frozen_at is not None,
        "frozen_at": policy.frozen_at,
        "signal_cutoff_at": policy.signal_cutoff_at,
        "policies": [
            {
                "version_name": row.version_name,
                "active": row.active,
                "serving_mode": row.serving_mode,
                "shadow_policy": row.shadow_policy,
            }
            for row in policies
        ],
        "latest_evaluation": (
            LearningEvaluationOut.model_validate(latest).model_dump(mode="json")
            if latest
            else None
        ),
    }


@router.post("/admin/learning/replays", response_model=LearningEvaluationOut)
def replay_learning(
    body: LearningReplayRequest,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    authorize(ctx, "admin_learning", ctx.clinic_id, None)
    if body.run_ids:
        count = len(
            db.scalars(
                select(RankingRun).where(
                    RankingRun.clinic_id == ctx.clinic_id,
                    RankingRun.run_id.in_(body.run_ids),
                )
            ).all()
        )
        if count != len(set(body.run_ids)):
            raise resource_not_found()
    evaluation = evaluate_runs(
        db,
        clinic_id=ctx.clinic_id,
        run_ids=list(dict.fromkeys(body.run_ids)),
        actor_id=ctx.user_id,
    )
    db.commit()
    return evaluation


@router.post("/admin/learning/freeze")
def freeze_learning(
    body: LearningFreezeRequest,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    authorize(ctx, "admin_learning", ctx.clinic_id, None)
    policy = active_policy(db, ctx.clinic_id)
    current = policy.frozen_at is not None
    if current != body.expected_frozen:
        raise HTTPException(status_code=409, detail="Learning freeze state conflict")
    now = datetime.now()
    result = db.execute(
        update(LearningPolicyVersion)
        .where(
            LearningPolicyVersion.policy_id == policy.policy_id,
            (LearningPolicyVersion.frozen_at.is_not(None) if current else LearningPolicyVersion.frozen_at.is_(None)),
        )
        .values(
            frozen_at=now if body.frozen else None,
            signal_cutoff_at=now if body.frozen else None,
        )
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Learning freeze state conflict")
    db.flush()
    for patient_id in db.scalars(
        select(Patient.patient_id).where(Patient.clinic_id == ctx.clinic_id)
    ).all():
        rebuild_glance_projections(db, patient_id, as_of=now)
    db.commit()
    return learning_status(db=db, ctx=ctx)


@router.post("/admin/learning/policies/{version}/activate")
def activate_policy(
    version: str,
    body: object = Body(default={}),
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    authorize(ctx, "admin_learning", ctx.clinic_id, None)
    if body not in ({}, None):
        raise HTTPException(status_code=422, detail="Invalid policy request")
    if version == "enabled":
        raise HTTPException(status_code=422, detail="Learning-enabled serving is not authorized")
    ensure_learning_policies(db, ctx.clinic_id, actor_id=ctx.user_id)
    target = db.scalar(
        select(LearningPolicyVersion).where(
            LearningPolicyVersion.clinic_id == ctx.clinic_id,
            LearningPolicyVersion.version_name == version,
            LearningPolicyVersion.serving_mode == SERVING_MODE,
        )
    )
    if target is None:
        raise HTTPException(status_code=422, detail="Unknown Shadow policy")
    db.execute(
        update(LearningPolicyVersion)
        .where(LearningPolicyVersion.clinic_id == ctx.clinic_id)
        .values(active=False)
    )
    target.active = True
    target.created_by = target.created_by or ctx.user_id
    db.add(target)
    db.flush()
    now = datetime.now()
    for patient_id in db.scalars(
        select(Patient.patient_id).where(Patient.clinic_id == ctx.clinic_id)
    ).all():
        rebuild_glance_projections(db, patient_id, as_of=now)
    db.commit()
    return learning_status(db=db, ctx=ctx)
