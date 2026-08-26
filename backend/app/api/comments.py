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
from ..authz import authorize, require_auth
from ..db import get_db
from ..ids import new_id
from ..models import Artifact, Comment, Event, User
from ..role_context import RoleContext
from ..schemas import CommentCreate, CommentOut

router = APIRouter(prefix="/api", tags=["comments"])


def _resolve_anchor(db: Session, anchor_type: str, anchor_id: str) -> Event:
    if anchor_type == "event":
        event = db.get(Event, anchor_id)
        if event is None:
            raise HTTPException(status_code=404, detail=f"Event {anchor_id} not found")
        return event
    if anchor_type == "artifact":
        artifact = db.get(Artifact, anchor_id)
        if artifact is None:
            raise HTTPException(status_code=404, detail=f"Artifact {anchor_id} not found")
        event = db.get(Event, artifact.event_id)
        if event is None:
            raise HTTPException(status_code=404, detail=f"Event {artifact.event_id} not found")
        return event
    raise HTTPException(status_code=422, detail="Invalid anchor_type")


@router.post("/comments", response_model=CommentOut)
def create_comment(
    body: CommentCreate,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    event = _resolve_anchor(db, body.anchor_type, body.anchor_id)
    authorize(ctx, "comment", event.clinic_id, event.patient_id)

    if body.parent_comment_id:
        parent = db.get(Comment, body.parent_comment_id)
        if parent is None:
            raise HTTPException(status_code=404, detail="Parent comment not found")
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
    comment = db.get(Comment, comment_id)
    if comment is None:
        raise HTTPException(status_code=404, detail=f"Comment {comment_id} not found")
    event = _resolve_anchor(db, comment.anchor_type, comment.anchor_id)
    authorize(ctx, "comment", event.clinic_id, event.patient_id)

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
    comment = db.get(Comment, comment_id)
    if comment is None:
        raise HTTPException(status_code=404, detail=f"Comment {comment_id} not found")
    event = _resolve_anchor(db, comment.anchor_type, comment.anchor_id)
    authorize(ctx, "comment", event.clinic_id, event.patient_id)

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
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")
    authorize(ctx, "read_comments", event.clinic_id, event.patient_id)

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
