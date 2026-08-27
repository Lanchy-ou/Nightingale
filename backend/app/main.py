"""FastAPI entry point.

Applies role-context parsing to every request (parse only, no enforcement in
M1). Provides an auxiliary GET /api/me that echoes the resolved RoleContext so
tests can assert header parsing.
"""
from __future__ import annotations

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import HTTPException, RequestValidationError
from sqlalchemy.orm import Session

from .api import (
    audit,
    auth,
    comments,
    events,
    highlights,
    notes,
    patient_view,
    patients,
    sources,
    tasks,
    transcripts,
)
from .db import get_db
from .errors import error_response
from .models import Clinic, User
from .role_context import RoleContext, get_role_context
from .schemas import CurrentIdentityOut

app = FastAPI(
    title="Nightingale API",
    version="0.1.0",
    dependencies=[Depends(get_role_context)],
)

app.include_router(auth.router)
app.include_router(patients.router)
app.include_router(patient_view.router)
app.include_router(events.router)
app.include_router(highlights.router)
app.include_router(notes.router)
app.include_router(comments.router)
app.include_router(audit.router)
app.include_router(sources.router)
app.include_router(tasks.router)
app.include_router(transcripts.router)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 404:
        code = "not_found"
    elif exc.status_code == 422:
        code = "validation_error"
    else:
        code = "http_error"
    return error_response(exc.status_code, code, str(exc.detail))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # `str(exc)` contains rejected input values and internal source locations.
    # Auth payloads can contain passwords/tokens, so validation responses must
    # never serialize the exception verbatim.
    return error_response(422, "validation_error", "Request validation failed")


@app.get("/api/me", response_model=CurrentIdentityOut)
def read_me(
    ctx: RoleContext = Depends(get_role_context),
    db: Session = Depends(get_db),
):
    """Current DB-authoritative identity for the C2 shell.

    The unauthenticated shape remains available as a testability aid, but never
    grants access to a protected resource.
    """
    user = db.get(User, ctx.user_id) if ctx.user_id else None
    clinic = db.get(Clinic, ctx.clinic_id) if ctx.clinic_id else None
    return CurrentIdentityOut(
        user_id=ctx.user_id,
        role=ctx.role,
        clinic_id=ctx.clinic_id,
        patient_id=ctx.patient_id,
        display_name=user.name if user else None,
        clinic_name=clinic.name if clinic else None,
        authenticated=ctx.authenticated,
    )
