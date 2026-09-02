"""Pure SL1 role-specific AttentionItem snapshots and deterministic ranking."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .ids import stable_id
from .models import Artifact, CareWorkflow, Event, Highlight, Task, User
from .provenance_binding import resolve_highlight_source
from .workflow_state import derive_task_workflow_state

FEATURE_SCHEMA_VERSION = "attention-feature-v1"
SUPPORTED_VIEWER_ROLES = frozenset({"staff", "clinician"})
TERMINAL_TASK_STATUSES = frozenset({"completed", "cancelled"})

FEATURE_CLASS_REGISTRY = {
    "identity_lineage": (
        "candidate_id",
        "source_kind",
        "source_id",
        "clinic_id",
        "patient_id",
        "event_id",
        "workflow_id",
        "workflow_root_event_id",
        "workflow_group_key",
        "independence_key",
        "workflow_node_type",
        "workflow_node_id",
        "viewer_role",
        "attention_kind",
    ),
    "eligibility_gate": (
        "terminal",
        "rejected",
        "workflow_link_known",
        "active_frontier",
        "superseded",
        "assigned_to_viewer_role",
        "role_route_known",
    ),
    "priority_band": (
        "pinned",
        "needs_review",
        "hard_protected",
        "overdue",
        "escalated",
        "attention_class",
        "task_kind",
    ),
    "within_band_score": (
        "base_importance_score",
        "decay_adjustment",
        "adaptive_adjustment",
        "final_score",
    ),
    "tie_break": ("due_known", "due_at", "created_at", "source_id"),
    "explanation_audit": (
        "source_binding_status",
        "protection_reasons",
        "inbound_relation_types",
        "outbound_relation_types",
    ),
}


@dataclass(frozen=True)
class AttentionItem:
    schema_version: str
    candidate_id: str
    source_kind: str
    source_id: str
    highlight_id: str
    clinic_id: str
    patient_id: str
    event_id: str
    workflow_id: str | None
    workflow_root_event_id: str | None
    workflow_group_key: str | None
    independence_key: str
    workflow_node_type: str | None
    workflow_node_id: str | None
    viewer_role: str
    attention_kind: str
    status: str
    terminal: bool
    unresolved: bool
    rejected: bool
    pinned: bool
    needs_review: bool
    conflict_unresolved: bool
    attention_class: str | None
    task_kind: str | None
    review_outcome: str | None
    time_sensitivity: str | None
    workflow_status: str
    active_frontier: bool
    superseded: bool
    patient_reported_done_pending_verification: bool
    responsible_role_known: bool
    responsible_role: str | None
    assigned_to_viewer_role: bool
    requires_action_from_viewer: bool
    requires_decision_from_viewer: bool
    waiting_for_other_role: bool
    role_route_known: bool
    assigned_user_id: str | None
    due_known: bool
    due_at: datetime | None
    overdue: bool | None
    escalated: bool
    age_seconds: int
    time_to_due_seconds: int | None
    workflow_link_known: bool
    inbound_relation_types: tuple[str, ...]
    outbound_relation_types: tuple[str, ...]
    blocking_predecessor_count: int
    open_downstream_action_count: int
    workflow_blocking_known: bool
    workflow_blocking: bool | None
    parent_context_known: bool
    upstream_verification_known: bool
    upstream_verification_outcome: str | None
    source_binding_status: str
    exact_span_available: bool
    source_authority: str
    hard_protected: bool
    protection_reasons: tuple[str, ...]
    base_importance_score: int
    decay_adjustment: int
    adaptive_adjustment: int
    final_score: int
    priority_band: int
    priority_reasons: tuple[str, ...]
    eligible: bool
    exclusion_reason: str | None
    created_at: datetime

    def factor_snapshot(self) -> dict:
        payload = asdict(self)
        payload.pop("highlight_id", None)
        for key in ("due_at", "created_at"):
            value = payload[key]
            payload[key] = value.isoformat() if value is not None else None
        for key in (
            "inbound_relation_types",
            "outbound_relation_types",
            "protection_reasons",
            "priority_reasons",
        ):
            payload[key] = list(payload[key])
        payload["feature_class_registry"] = {
            name: list(fields) for name, fields in FEATURE_CLASS_REGISTRY.items()
        }
        return payload

    def rank_key(self) -> tuple:
        return (
            self.priority_band,
            not self.pinned,
            not self.needs_review,
            -self.final_score,
            not self.due_known,
            self.due_at or datetime.max,
            self.created_at,
            self.highlight_id,
        )


def _attention_kind(highlight: Highlight, task: Task | None) -> str:
    if task is not None:
        return {
            "patient_report_review": "patient_report_review",
            "clinician_priority_review": "clinician_priority_review",
        }.get(task.task_kind, "care_task")
    if highlight.entity_type == "allergy" and highlight.feature_flags.get(
        "clinician_confirmed"
    ):
        return "safety_context"
    if highlight.review_status == "needs_review" or highlight.conflict_with_artifact_id:
        return "conflict_review"
    return "artifact_highlight"


def _source_authority(db: Session, highlight: Highlight, task: Task | None) -> str:
    artifact_id = (
        task.source_artifact_id
        if task is not None and task.source_artifact_id
        else highlight.source_artifact_id or highlight.artifact_id
    )
    artifact = db.get(Artifact, artifact_id) if artifact_id else None
    if artifact is not None and artifact.author_role in {
        "patient",
        "staff",
        "clinician",
        "system",
    }:
        return artifact.author_role
    if task is not None:
        creator = db.get(User, task.created_by)
        if creator is not None and creator.role in {"patient", "staff", "clinician"}:
            return creator.role
    return "system"


def _binding_status(db: Session, highlight: Highlight, task: Task | None) -> str:
    if task is not None and highlight.source_span is None:
        return "not_applicable"
    if highlight.source_artifact_id is None and highlight.source_span is None:
        return "not_applicable"
    return resolve_highlight_source(db, highlight).status


def _protection(highlight: Highlight) -> tuple[bool, tuple[str, ...]]:
    reasons: list[str] = []
    if highlight.status == "pinned":
        reasons.append("pinned")
    if highlight.review_status == "needs_review":
        reasons.append("needs_review")
    if highlight.feature_flags.get("explicit_risk"):
        reasons.append("explicit_risk")
    if highlight.conflict_with_artifact_id is not None:
        reasons.append("unresolved_conflict")
    return bool(reasons), tuple(reasons)


def _patient_review_workflow(
    db: Session, *, event_id: str, clinic_id: str, patient_id: str
) -> CareWorkflow | None:
    return db.scalar(
        select(CareWorkflow).where(
            CareWorkflow.root_event_id == event_id,
            CareWorkflow.clinic_id == clinic_id,
            CareWorkflow.patient_id == patient_id,
            CareWorkflow.workflow_kind == "patient_report_response",
        )
    )


def _eligibility(
    *,
    highlight: Highlight,
    task: Task | None,
    summary: Artifact | None,
    viewer_role: str,
    hard_protected: bool,
    workflow_link_known: bool,
    active_frontier: bool,
    has_patient_review_workflow: bool,
) -> tuple[bool, str | None]:
    if highlight.status == "rejected":
        return False, "rejected"
    if task is not None and task.status in TERMINAL_TASK_STATUSES:
        return False, "terminal_task"
    if task is not None and not workflow_link_known:
        return False, "workflow_link_incomplete"
    if task is not None and not active_frontier:
        return False, "inactive_workflow_step"
    if (
        highlight.entity_type == "allergy"
        and highlight.feature_flags.get("clinician_confirmed")
    ):
        return False, "fixed_safety_context"
    if (
        task is None
        and summary is not None
        and summary.artifact_type == "ai_patient_session_summary"
        and has_patient_review_workflow
        and not hard_protected
    ):
        return False, "patient_candidate_review_context"
    if hard_protected:
        return True, None
    if task is not None and task.task_kind == "patient_report_review":
        return (viewer_role == "staff", None if viewer_role == "staff" else "staff_work_queue_only")
    if task is not None and task.task_kind == "clinician_priority_review":
        return (
            viewer_role == "clinician",
            None if viewer_role == "clinician" else "clinician_work_queue_only",
        )
    if task is not None:
        return (
            task.assigned_role == viewer_role,
            None if task.assigned_role == viewer_role else "other_role_queue",
        )
    return True, None


def _priority_band(
    *,
    highlight: Highlight,
    task: Task | None,
    viewer_role: str,
    hard_protected: bool,
    overdue: bool | None,
) -> tuple[int, tuple[str, ...]]:
    if hard_protected:
        return 1, ("protected_or_needs_review",)
    if (
        task is not None
        and task.attention_class == "priority_review"
        and task.assigned_role == viewer_role
    ):
        return 2, ("current_role_priority_review",)
    if task is not None and task.task_kind == "patient_report_review" and (
        task.escalated_at is not None
        or (overdue is True and task.escalate_at is not None)
    ):
        return 3, ("verification_overdue",)
    if task is not None and overdue is True:
        return 4, ("care_task_overdue",)
    if task is not None and task.assigned_role == viewer_role:
        return 5, ("current_role_unresolved_task",)
    if task is not None and task.task_kind == "patient_report_review":
        return 6, ("routine_patient_review",)
    return 7, ("other_unresolved",)


def build_attention_items(
    db: Session,
    *,
    patient_id: str,
    viewer_role: str,
    as_of: datetime,
) -> list[AttentionItem]:
    if viewer_role not in SUPPORTED_VIEWER_ROLES:
        return []
    highlights = db.scalars(
        select(Highlight)
        .where(Highlight.patient_id == patient_id)
        .order_by(Highlight.created_at, Highlight.highlight_id)
    ).all()
    items: list[AttentionItem] = []
    for highlight in highlights:
        event = db.get(Event, highlight.event_id)
        if event is None or event.patient_id != patient_id:
            continue
        task = db.get(Task, highlight.task_id) if highlight.task_id else None
        if task is not None and (
            task.patient_id != patient_id or task.clinic_id != event.clinic_id
        ):
            continue
        summary = db.get(Artifact, highlight.artifact_id) if highlight.artifact_id else None
        context_workflow = _patient_review_workflow(
            db,
            event_id=event.event_id,
            clinic_id=event.clinic_id,
            patient_id=patient_id,
        )
        workflow = (
            db.get(CareWorkflow, task.workflow_id)
            if task and task.workflow_id
            else context_workflow
        )
        if task is not None:
            workflow_state = derive_task_workflow_state(db, task, as_of=as_of)
        else:
            workflow_state = None
        hard_protected, protection_reasons = _protection(highlight)
        due_at = task.due_at if task else None
        due_known = due_at is not None
        overdue = due_at <= as_of if due_at is not None else None
        time_to_due = int((due_at - as_of).total_seconds()) if due_at is not None else None
        binding = _binding_status(db, highlight, task)
        kind = _attention_kind(highlight, task)
        eligible, exclusion = _eligibility(
            highlight=highlight,
            task=task,
            summary=summary,
            viewer_role=viewer_role,
            hard_protected=hard_protected,
            workflow_link_known=workflow_state.workflow_link_known if workflow_state else False,
            active_frontier=workflow_state.active_frontier if workflow_state else False,
            has_patient_review_workflow=context_workflow is not None,
        )
        band, reasons = _priority_band(
            highlight=highlight,
            task=task,
            viewer_role=viewer_role,
            hard_protected=hard_protected,
            overdue=overdue,
        )
        workflow_id = task.workflow_id if task else (workflow.workflow_id if workflow else None)
        entity = highlight.entity_key or highlight.entity_type or highlight.highlight_id
        if task is not None and workflow_id:
            independence = f"workflow:{workflow_id}:task:{task.task_id}"
        elif workflow_id:
            independence = f"workflow:{workflow_id}:event:{event.event_id}:entity:{entity}"
        elif task is not None:
            independence = f"task:{task.task_id}"
        elif highlight.entity_key or highlight.entity_type:
            independence = f"event:{event.event_id}:entity:{entity}"
        else:
            independence = f"highlight:{highlight.highlight_id}"
        responsible = task.assigned_role if task else None
        assigned = bool(task is not None and responsible == viewer_role)
        requires_decision = bool(
            eligible
            and assigned
            and kind in {"patient_report_review", "clinician_priority_review"}
        )
        requires_action = bool(eligible and assigned and kind == "care_task")
        score = highlight.base_importance_score + highlight.decay_adjustment
        state = workflow_state
        items.append(
            AttentionItem(
                schema_version=FEATURE_SCHEMA_VERSION,
                candidate_id=f"att_{stable_id(viewer_role, highlight.highlight_id)}",
                source_kind="task" if task else "highlight",
                source_id=task.task_id if task else highlight.highlight_id,
                highlight_id=highlight.highlight_id,
                clinic_id=event.clinic_id,
                patient_id=patient_id,
                event_id=event.event_id,
                workflow_id=workflow_id,
                workflow_root_event_id=workflow.root_event_id if workflow else None,
                workflow_group_key=f"workflow:{workflow_id}" if workflow_id else None,
                independence_key=independence,
                workflow_node_type="task" if task else ("event" if workflow else None),
                workflow_node_id=task.task_id if task else (event.event_id if workflow else None),
                viewer_role=viewer_role,
                attention_kind=kind,
                status=task.status if task else highlight.status,
                terminal=state.terminal if state else False,
                unresolved=(task.status not in TERMINAL_TASK_STATUSES) if task else highlight.status != "rejected",
                rejected=highlight.status == "rejected",
                pinned=highlight.status == "pinned",
                needs_review=highlight.review_status == "needs_review",
                conflict_unresolved=highlight.conflict_with_artifact_id is not None,
                attention_class=task.attention_class if task else None,
                task_kind=task.task_kind if task else None,
                review_outcome=task.review_outcome if task else None,
                time_sensitivity=task.time_sensitivity if task else None,
                workflow_status=state.workflow_status if state else (workflow.status if workflow else "not_applicable"),
                active_frontier=state.active_frontier if state else True,
                superseded=state.superseded if state else False,
                patient_reported_done_pending_verification=(
                    state.patient_reported_done_pending_verification if state else False
                ),
                responsible_role_known=task is not None,
                responsible_role=responsible,
                assigned_to_viewer_role=assigned,
                requires_action_from_viewer=requires_action,
                requires_decision_from_viewer=requires_decision,
                waiting_for_other_role=bool(task is not None and responsible != viewer_role),
                role_route_known=task is not None,
                assigned_user_id=task.assigned_user_id if task else None,
                due_known=due_known,
                due_at=due_at,
                overdue=overdue,
                escalated=bool(task and task.escalated_at is not None),
                age_seconds=max(0, int((as_of - highlight.created_at).total_seconds())),
                time_to_due_seconds=time_to_due,
                workflow_link_known=state.workflow_link_known if state else workflow is not None,
                inbound_relation_types=state.inbound_relation_types if state else (),
                outbound_relation_types=state.outbound_relation_types if state else (),
                blocking_predecessor_count=state.blocking_predecessor_count if state else 0,
                open_downstream_action_count=state.open_downstream_action_count if state else 0,
                workflow_blocking_known=state.workflow_blocking_known if state else False,
                workflow_blocking=state.workflow_blocking if state else None,
                parent_context_known=state.parent_context_known if state else workflow is not None,
                upstream_verification_known=state.upstream_verification_known if state else False,
                upstream_verification_outcome=(
                    state.upstream_verification_outcome if state else None
                ),
                source_binding_status=binding,
                exact_span_available=bool(highlight.source_span and binding == "current"),
                source_authority=_source_authority(db, highlight, task),
                hard_protected=hard_protected,
                protection_reasons=protection_reasons,
                base_importance_score=highlight.base_importance_score,
                decay_adjustment=highlight.decay_adjustment,
                adaptive_adjustment=0,
                final_score=score,
                priority_band=band,
                priority_reasons=reasons,
                eligible=eligible,
                exclusion_reason=exclusion,
                created_at=highlight.created_at,
            )
        )
    return items


def rank_attention_items(items: list[AttentionItem]) -> list[AttentionItem]:
    return sorted((item for item in items if item.eligible), key=AttentionItem.rank_key)
