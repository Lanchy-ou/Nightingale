"""Threaded comments: create, resolve/unresolve, list (M3).

Anchor resolution is polymorphic (event | artifact); integrity is enforced at
read/write time by resolving the anchor to its owning Event, then applying the
same clinic/patient scope checks as everything else.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..audit import add_audit
from ..authz import authorize, require_auth, resource_not_found
from ..checkin_visibility import require_checkin_event_visible
from ..db import get_db
from ..clinic_scope import (
    load_artifact_with_event,
    load_comment_with_event,
    load_event,
)
from ..ids import new_id
from ..models import Artifact, Comment, Event, User
from ..role_context import RoleContext
from ..schemas import CommentCreate, CommentOut

router = APIRouter(prefix="/api", tags=["comments"])


def _resolve_anchor(
    db: Session, ctx: RoleContext, anchor_type: str, anchor_id: str
) -> Event:
    if anchor_type == "event":
        event = load_event(db, ctx, anchor_id)
        if event is None:
            raise resource_not_found()
        return event
    if anchor_type == "artifact":
        scoped = load_artifact_with_event(db, ctx, anchor_id)
        if scoped is None:
            raise resource_not_found()
        return scoped[1]
    raise HTTPException(status_code=422, detail="Invalid anchor_type")


@router.post("/comments", response_model=CommentOut)
def create_comment(
    body: CommentCreate,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    event = _resolve_anchor(db, ctx, body.anchor_type, body.anchor_id)
    authorize(ctx, "comment", event.clinic_id, event.patient_id)
    require_checkin_event_visible(db, event.event_id)

    if body.parent_comment_id:
        scoped_parent = load_comment_with_event(db, ctx, body.parent_comment_id)
        if scoped_parent is None:
            raise resource_not_found()
        parent, parent_event = scoped_parent
        authorize(ctx, "read_comments", parent_event.clinic_id, parent_event.patient_id)
        if parent.anchor_type != body.anchor_type or parent.anchor_id != body.anchor_id:
            raise HTTPException(status_code=422, detail="Parent comment must share the same anchor")

    for mention in body.mentions:
        u = db.get(User, mention)
        if u is None or u.clinic_id != event.clinic_id or u.role not in ("staff", "clinician"):
            raise HTTPException(status_code=422, detail=f"Invalid mention: {mention}")

    comment_id = new_id("cmt")
    db.add(
        Comment(
            comment_id=comment_id,
            anchor_type=body.anchor_type,
            anchor_id=body.anchor_id,
            parent_comment_id=body.parent_comment_id,
            author_id=ctx.user_id,
            author_role=ctx.role,
            body=body.body,
            mentions=body.mentions,
            resolved=False,
            created_at=datetime.now(),
            resolved_at=None,
            resolved_by=None,
        )
    )
    add_audit(
        db,
        actor_id=ctx.user_id,
        actor_role=ctx.role,
        action="comment",
        target_type="comment",
        target_id=comment_id,
        clinic_id=event.clinic_id,
        patient_id=event.patient_id,
        event_id=event.event_id,
    )
    db.commit()
    return db.get(Comment, comment_id)


@router.post("/comments/{comment_id}/resolve", response_model=CommentOut)
def resolve_comment(
    comment_id: str,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    scoped = load_comment_with_event(db, ctx, comment_id)
    if scoped is None:
        raise resource_not_found()
    comment, event = scoped
    authorize(ctx, "comment", event.clinic_id, event.patient_id)
    require_checkin_event_visible(db, event.event_id)

    if not comment.resolved:
        comment.resolved = True
        comment.resolved_at = datetime.now()
        comment.resolved_by = ctx.user_id
        add_audit(
            db,
            actor_id=ctx.user_id,
            actor_role=ctx.role,
            action="resolve",
            target_type="comment",
            target_id=comment_id,
            clinic_id=event.clinic_id,
            patient_id=event.patient_id,
            event_id=event.event_id,
        )
        db.commit()
        db.refresh(comment)
    return comment


@router.post("/comments/{comment_id}/unresolve", response_model=CommentOut)
def unresolve_comment(
    comment_id: str,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    scoped = load_comment_with_event(db, ctx, comment_id)
    if scoped is None:
        raise resource_not_found()
    comment, event = scoped
    authorize(ctx, "comment", event.clinic_id, event.patient_id)
    require_checkin_event_visible(db, event.event_id)

    if comment.resolved:
        comment.resolved = False
        comment.resolved_at = None
        comment.resolved_by = None
        add_audit(
            db,
            actor_id=ctx.user_id,
            actor_role=ctx.role,
            action="unresolve",
            target_type="comment",
            target_id=comment_id,
            clinic_id=event.clinic_id,
            patient_id=event.patient_id,
            event_id=event.event_id,
        )
        db.commit()
        db.refresh(comment)
    return comment


@router.get("/events/{event_id}/comments", response_model=list[CommentOut])
def list_comments(
    event_id: str,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    event = load_event(db, ctx, event_id)
    if event is None:
        raise resource_not_found()
    authorize(ctx, "read_comments", event.clinic_id, event.patient_id)
    require_checkin_event_visible(db, event_id)

    artifact_ids = db.scalars(
        select(Artifact.artifact_id).where(Artifact.event_id == event_id)
    ).all()
    return db.scalars(
        select(Comment)
        .where(
            or_(
                (Comment.anchor_type == "event") & (Comment.anchor_id == event_id),
                (Comment.anchor_type == "artifact") & (Comment.anchor_id.in_(artifact_ids)),
            )
        )
        .order_by(Comment.created_at)
    ).all()
