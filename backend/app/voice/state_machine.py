"""Pure authoritative lifecycle for an E4 capture."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum


class CaptureStatus(str, Enum):
    CREATED = "created"
    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    TRANSCRIBING = "transcribing"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"
    CONFIRMED = "confirmed"
    PROCESSED = "processed"


class InvalidCaptureTransition(ValueError):
    pass


class StaleCaptureState(ValueError):
    pass


@dataclass(frozen=True)
class CaptureState:
    capture_id: str
    status: CaptureStatus
    revision: int
    failure_reason: str | None = None
    retry_status: CaptureStatus | None = None

    @classmethod
    def created(cls, capture_id: str) -> "CaptureState":
        capture_id = capture_id.strip()
        if not capture_id:
            raise ValueError("capture_id must not be empty")
        return cls(capture_id=capture_id, status=CaptureStatus.CREATED, revision=0)


_ALLOWED = {
    CaptureStatus.CREATED: {CaptureStatus.UPLOADING},
    CaptureStatus.UPLOADING: {CaptureStatus.UPLOADED},
    CaptureStatus.UPLOADED: {CaptureStatus.TRANSCRIBING},
    CaptureStatus.TRANSCRIBING: {CaptureStatus.NEEDS_REVIEW},
    CaptureStatus.NEEDS_REVIEW: {CaptureStatus.CONFIRMED},
    CaptureStatus.CONFIRMED: {CaptureStatus.PROCESSED},
    CaptureStatus.FAILED: set(),
    CaptureStatus.PROCESSED: set(),
}

_RETRY_FROM_FAILURE = {
    CaptureStatus.UPLOADING: CaptureStatus.UPLOADING,
    CaptureStatus.TRANSCRIBING: CaptureStatus.TRANSCRIBING,
}


def _check_revision(state: CaptureState, expected_revision: int) -> None:
    if state.revision != expected_revision:
        raise StaleCaptureState(
            f"stale capture revision: expected {expected_revision}, current {state.revision}"
        )


def transition_capture(
    state: CaptureState,
    target: CaptureStatus,
    *,
    expected_revision: int,
) -> CaptureState:
    _check_revision(state, expected_revision)
    if target is state.status:
        return state
    if target not in _ALLOWED[state.status]:
        raise InvalidCaptureTransition(f"{state.status.value} -> {target.value}")
    return replace(
        state,
        status=target,
        revision=state.revision + 1,
        failure_reason=None,
        retry_status=None,
    )

def fail_capture(
    state: CaptureState,
    reason: str,
    *,
    expected_revision: int,
) -> CaptureState:
    _check_revision(state, expected_revision)
    retry_status = _RETRY_FROM_FAILURE.get(state.status)
    if retry_status is None:
        raise InvalidCaptureTransition(f"{state.status.value} -> failed")
    reason = reason.strip()
    if not reason:
        raise ValueError("failure reason must not be empty")
    return replace(
        state,
        status=CaptureStatus.FAILED,
        revision=state.revision + 1,
        failure_reason=reason,
        retry_status=retry_status,
    )


def retry_capture(state: CaptureState, *, expected_revision: int) -> CaptureState:
    _check_revision(state, expected_revision)
    if state.status is not CaptureStatus.FAILED or state.retry_status is None:
        raise InvalidCaptureTransition(f"{state.status.value} -> retry")
    return replace(
        state,
        status=state.retry_status,
        revision=state.revision + 1,
        failure_reason=None,
        retry_status=None,
    )
