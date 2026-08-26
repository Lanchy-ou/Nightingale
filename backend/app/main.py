"""FastAPI entry point.

Applies role-context parsing to every request (parse only, no enforcement in
M1). Provides an auxiliary GET /api/me that echoes the resolved RoleContext so
tests can assert header parsing.
"""
from __future__ import annotations

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import HTTPException, RequestValidationError

from .api import audit, comments, events, highlights, notes, patients, sources
from .errors import error_response
from .role_context import RoleContext, get_role_context

app = FastAPI(
    title="Nightingale API",
    version="0.1.0",
    dependencies=[Depends(get_role_context)],
)

app.include_router(patients.router)
app.include_router(events.router)
app.include_router(highlights.router)
app.include_router(notes.router)
app.include_router(comments.router)
app.include_router(audit.router)
app.include_router(sources.router)


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
    return error_response(422, "validation_error", str(exc))


@app.get("/api/me")
def read_me(ctx: RoleContext = Depends(get_role_context)):
    """Echo the parsed role context (testability aid; not a security boundary)."""
    return {
        "user_id": ctx.user_id,
        "role": ctx.role,
        "clinic_id": ctx.clinic_id,
        "patient_id": ctx.patient_id,
        "authenticated": ctx.authenticated,
    }
