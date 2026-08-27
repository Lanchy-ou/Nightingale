"""E4 independent capture lifecycle contract (no API/DB integration)."""

import pytest

from app.voice.state_machine import (
    CaptureState,
    CaptureStatus,
    InvalidCaptureTransition,
    StaleCaptureState,
    fail_capture,
    retry_capture,
    transition_capture,
)


def test_capture_happy_path_is_explicit_and_revisioned():
    state = CaptureState.created("cap_demo")

    for expected, target in enumerate(
        (
            CaptureStatus.UPLOADING,
            CaptureStatus.UPLOADED,
            CaptureStatus.TRANSCRIBING,
            CaptureStatus.NEEDS_REVIEW,
            CaptureStatus.CONFIRMED,
            CaptureStatus.PROCESSED,
        )
    ):
        state = transition_capture(state, target, expected_revision=expected)

    assert state.status is CaptureStatus.PROCESSED
    assert state.revision == 6


def test_same_status_replay_is_an_idempotent_noop():
    state = transition_capture(
        CaptureState.created("cap_demo"),
        CaptureStatus.UPLOADING,
        expected_revision=0,
    )

    replay = transition_capture(
        state,
        CaptureStatus.UPLOADING,
        expected_revision=1,
    )

    assert replay == state


def test_stale_and_illegal_transitions_fail_closed():
    state = CaptureState.created("cap_demo")

    with pytest.raises(StaleCaptureState):
        transition_capture(state, CaptureStatus.UPLOADING, expected_revision=4)

    with pytest.raises(InvalidCaptureTransition):
        transition_capture(state, CaptureStatus.CONFIRMED, expected_revision=0)


def test_failure_retry_returns_only_to_the_recorded_safe_stage():
    state = transition_capture(
        CaptureState.created("cap_demo"),
        CaptureStatus.UPLOADING,
        expected_revision=0,
    )
    failed = fail_capture(state, "network interrupted", expected_revision=1)

    assert failed.status is CaptureStatus.FAILED
    assert failed.retry_status is CaptureStatus.UPLOADING
    assert failed.failure_reason == "network interrupted"

    retried = retry_capture(failed, expected_revision=2)
    assert retried.status is CaptureStatus.UPLOADING
    assert retried.failure_reason is None
    assert retried.retry_status is None


def test_processed_capture_is_terminal():
    state = CaptureState(
        capture_id="cap_demo",
        status=CaptureStatus.PROCESSED,
        revision=6,
    )

    with pytest.raises(InvalidCaptureTransition):
        transition_capture(state, CaptureStatus.UPLOADING, expected_revision=6)
