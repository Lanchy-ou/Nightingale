"""Owner-private note working copies with optimistic revisions."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from ..authz import authorize, require_auth, resource_not_found
from ..checkin_visibility import require_checkin_event_visible
from ..clinic_scope import load_event, load_artifact_with_event
from ..db import get_db
from ..ids import stable_id
from ..models import ArtifactVersion, NoteDraft
from ..role_context import RoleContext

router = APIRouter(prefix="/api/events/{event_id}/note-drafts", tags=["private drafts"])


class DraftWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_revision: int = Field(ge=0)
    base_version: int = Field(ge=0)
    fields: dict[str, str] | None

    @model_validator(mode="after")
    def bounded(self):
        if self.fields is not None and (len(self.fields) > 32 or sum(len(k) + len(v) for k, v in self.fields.items()) > 100_000):
            raise ValueError("Draft too large")
        return self


def _scope(db, ctx, event_id, slot):
    event = load_event(db, ctx, event_id)
    if event is None:
        raise resource_not_found()
    authorize(ctx, "manage_note_draft", event.clinic_id, event.patient_id)
    require_checkin_event_visible(db, event.event_id)
    if slot == "new":
        return event, None
    pair = load_artifact_with_event(db, ctx, slot)
    if pair is None or pair[1].event_id != event.event_id:
        raise resource_not_found()
    artifact = pair[0]
    if artifact.artifact_type != f"{ctx.role}_note":
        raise HTTPException(403, "Cannot draft another role's note")
    return event, artifact


def _base(db, artifact, version):
    if artifact is None:
        if version != 0:
            raise HTTPException(422, "New notes have no base version")
        return {"body": ""}
    snapshot = db.scalar(select(ArtifactVersion).where(
        ArtifactVersion.artifact_id == artifact.artifact_id,
        ArtifactVersion.version == version,
    ))
    if snapshot is None:
        raise HTTPException(422, "Invalid base version")
    return snapshot.content


def _out(db, draft, artifact):
    if draft is None:
        return {"revision": 0, "fields": None, "base_version": 0, "base_content": {}, "updated_at": None}
    return {"revision": draft.revision, "fields": draft.fields,
            "base_version": draft.base_version,
            "base_content": _base(db, artifact, draft.base_version) if draft.fields is not None else {},
            "updated_at": draft.updated_at}


@router.get("/{slot}")
def read_draft(event_id: str, slot: str, db: Session = Depends(get_db), ctx: RoleContext = Depends(require_auth)):
    _, artifact = _scope(db, ctx, event_id, slot)
    draft_id = stable_id("draft", ctx.user_id, ctx.role, event_id, slot)
    draft = db.scalar(select(NoteDraft).where(NoteDraft.draft_id == draft_id, NoteDraft.owner_id == ctx.user_id, NoteDraft.event_id == event_id))
    return _out(db, draft, artifact)


@router.put("/{slot}")
def save_draft(event_id: str, slot: str, body: DraftWrite, db: Session = Depends(get_db), ctx: RoleContext = Depends(require_auth)):
    _, artifact = _scope(db, ctx, event_id, slot)
    if body.fields is not None:
        base = _base(db, artifact, body.base_version)
        if set(body.fields) != {key for key, value in base.items() if isinstance(value, str)}:
            raise HTTPException(422, "Draft fields must match the note section")
    draft_id = stable_id("draft", ctx.user_id, ctx.role, event_id, slot)
    values = dict(fields=body.fields, base_version=body.base_version if body.fields is not None else 0,
                  revision=body.expected_revision + 1, updated_at=datetime.now(timezone.utc).replace(tzinfo=None))
    if body.expected_revision == 0:
        result = db.execute(insert(NoteDraft).values(draft_id=draft_id, owner_id=ctx.user_id, event_id=event_id, slot=slot, **values).on_conflict_do_nothing(index_elements=["draft_id"]))
    else:
        result = db.execute(update(NoteDraft).where(NoteDraft.draft_id == draft_id, NoteDraft.owner_id == ctx.user_id,
                           NoteDraft.event_id == event_id, NoteDraft.revision == body.expected_revision).values(**values))
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Draft changed in another tab. Your local text has not been saved over it.")
    db.commit()
    draft = db.scalar(select(NoteDraft).where(NoteDraft.draft_id == draft_id, NoteDraft.owner_id == ctx.user_id))
    return _out(db, draft, artifact)
