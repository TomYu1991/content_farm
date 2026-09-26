"""Unit tests for the bounded retry state machine (Requirements 6.6–6.10, 9.6)."""

from datetime import datetime, timezone

import pytest

from content_pipeline.errors import CallLimitError
from content_pipeline.retry import (
    DEFAULT_RETRY_DELAY_SECONDS,
    CallFailure,
    CallState,
    FailureKind,
    RetryStateMachine,
    classify_status,
    decide_retry,
    parse_retry_after,
)

NOW = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
RETRYABLE = [
    FailureKind.CONNECT_TIMEOUT,
    FailureKind.CONNECTION_INTERRUPTED,
    FailureKind.HTTP_429,
    FailureKind.HTTP_5XX,
]
NON_RETRYABLE = [
    FailureKind.HTTP_4XX,
    FailureKind.UNEXPECTED_STATUS,
    FailureKind.PARSE_ERROR,
    FailureKind.SCHEMA_ERROR,
    FailureKind.TRANSPORT_ERROR,
]


@pytest.mark.parametrize(
    "status,kind",
    [
        (200, None),
        (204, None),
        (429, FailureKind.HTTP_429),
        (500, FailureKind.HTTP_5XX),
        (599, FailureKind.HTTP_5XX),
        (400, FailureKind.HTTP_4XX),
        (401, FailureKind.HTTP_4XX),
        (404, FailureKind.HTTP_4XX),
        (301, FailureKind.UNEXPECTED_STATUS),
        (307, FailureKind.UNEXPECTED_STATUS),
    ],
)
def test_classify_status(status, kind) -> None:
    assert classify_status(status) == kind


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, None),
        ("7", 7.0),
        (" 0 ", 0.0),
        ("-3", None),
        ("1.5", None),
        ("soon", None),
        ("Wed, 01 Jan 2025 12:00:30 GMT", 30.0),
        ("Wed, 01 Jan 2025 11:00:00 GMT", 0.0),
    ],
)
def test_parse_retry_after(value, expected) -> None:
    assert parse_retry_after(value, NOW) == expected


@pytest.mark.parametrize("kind", RETRYABLE)
def test_retryable_first_failure_retries_once_with_default_delay(kind) -> None:
    assert decide_retry(1, CallFailure(kind)).retry is True
    assert decide_retry(1, CallFailure(kind)).delay == DEFAULT_RETRY_DELAY_SECONDS
    assert decide_retry(2, CallFailure(kind)).retry is False


def test_429_retry_after_takes_precedence() -> None:
    decision = decide_retry(1, CallFailure(FailureKind.HTTP_429, status=429, retry_after=12.0))
    assert (decision.retry, decision.delay) == (True, 12.0)
    # Retry-After is ignored for non-429 failures.
    assert decide_retry(1, CallFailure(FailureKind.HTTP_5XX, retry_after=12.0)).delay == DEFAULT_RETRY_DELAY_SECONDS


@pytest.mark.parametrize("kind", NON_RETRYABLE)
def test_non_retryable_failures_never_retry(kind) -> None:
    assert decide_retry(1, CallFailure(kind)).retry is False


def test_machine_allows_at_most_two_calls() -> None:
    machine = RetryStateMachine()
    assert machine.start_call() == 1
    assert machine.record_failure(CallFailure(FailureKind.HTTP_5XX)).retry is True
    assert machine.state is CallState.RETRY_PENDING
    assert machine.start_call() == 2
    assert machine.record_failure(CallFailure(FailureKind.HTTP_5XX)).retry is False
    assert machine.state is CallState.FAILED
    with pytest.raises(CallLimitError):
        machine.start_call()
    assert machine.calls_made == 2


def test_machine_stops_after_success() -> None:
    machine = RetryStateMachine()
    machine.start_call()
    machine.record_success()
    with pytest.raises(CallLimitError):
        machine.start_call()
    assert machine.calls_made == 1


def test_machine_stops_after_non_retryable_failure() -> None:
    machine = RetryStateMachine()
    machine.start_call()
    assert machine.record_failure(CallFailure(FailureKind.HTTP_4XX, status=400)).retry is False
    with pytest.raises(CallLimitError):
        machine.start_call()


@pytest.mark.parametrize("max_calls", [0, 3, True])
def test_machine_rejects_limits_outside_policy(max_calls) -> None:
    with pytest.raises(ValueError):
        RetryStateMachine(max_calls)
