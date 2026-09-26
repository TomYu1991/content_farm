"""Pure bounded-retry state machine for Model_Gateway calls (Requirement 6.6–6.10, 9.6).

Rules:

* A run makes at most :data:`MAX_MODEL_CALLS_PER_RUN` (2) model calls.
* Only a failure of the *first* call classified as a Retryable_Network_Error
  (connection timeout, connection interruption, HTTP 429, HTTP 5xx) permits
  exactly one retry. An HTTP 429 with a valid ``Retry-After`` waits exactly
  that long; every other retryable failure uses one fixed default delay.
* Other HTTP 4xx, unexpected statuses (including redirects, which are never
  followed), response parse errors, Article_Schema errors and other transport
  errors end the run without retrying.
* After a success or a terminal failure no further call can start, so there
  is no rewrite, quality loop or second-model routing.

No I/O happens here; the HTTP adapter drives this machine and performs the
(injected) sleep.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from .compliance import MAX_MODEL_CALLS_PER_RUN
from .errors import CallLimitError

DEFAULT_RETRY_DELAY_SECONDS = 1.0


class FailureKind(enum.StrEnum):
    CONNECT_TIMEOUT = "connect_timeout"
    CONNECTION_INTERRUPTED = "connection_interrupted"
    HTTP_429 = "http_429"
    HTTP_5XX = "http_5xx"
    HTTP_4XX = "http_4xx"
    UNEXPECTED_STATUS = "unexpected_status"
    PARSE_ERROR = "parse_error"
    SCHEMA_ERROR = "schema_error"
    TRANSPORT_ERROR = "transport_error"


RETRYABLE_KINDS: frozenset[FailureKind] = frozenset(
    {
        FailureKind.CONNECT_TIMEOUT,
        FailureKind.CONNECTION_INTERRUPTED,
        FailureKind.HTTP_429,
        FailureKind.HTTP_5XX,
    }
)


def is_retryable(kind: FailureKind) -> bool:
    return kind in RETRYABLE_KINDS


def classify_status(status: int) -> FailureKind | None:
    """Map an HTTP status to a failure kind; ``None`` means success (2xx)."""
    if 200 <= status <= 299:
        return None
    if status == 429:
        return FailureKind.HTTP_429
    if 500 <= status <= 599:
        return FailureKind.HTTP_5XX
    if 400 <= status <= 499:
        return FailureKind.HTTP_4XX
    return FailureKind.UNEXPECTED_STATUS


def parse_retry_after(value: str | None, now: datetime | None = None) -> float | None:
    """Parse ``Retry-After`` (delta-seconds or HTTP-date) into seconds.

    Returns ``None`` when absent or invalid. A past HTTP-date yields ``0.0``.
    """
    if value is None:
        return None
    text = value.strip()
    if text.isascii() and text.isdigit():
        return float(int(text))
    try:
        moment = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        return None
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    reference = now if now is not None else datetime.now(timezone.utc)
    return max(0.0, (moment - reference).total_seconds())


@dataclass(frozen=True)
class CallFailure:
    kind: FailureKind
    status: int | None = None
    retry_after: float | None = None  # seconds; only meaningful for HTTP 429


@dataclass(frozen=True)
class RetryDecision:
    retry: bool
    delay: float = 0.0


def decide_retry(
    calls_made: int,
    failure: CallFailure,
    *,
    max_calls: int = MAX_MODEL_CALLS_PER_RUN,
    default_delay: float = DEFAULT_RETRY_DELAY_SECONDS,
) -> RetryDecision:
    """Pure decision after the ``calls_made``-th call failed."""
    if calls_made != 1 or calls_made >= max_calls or not is_retryable(failure.kind):
        return RetryDecision(retry=False)
    if failure.kind is FailureKind.HTTP_429 and failure.retry_after is not None:
        return RetryDecision(retry=True, delay=failure.retry_after)
    return RetryDecision(retry=True, delay=default_delay)


class CallState(enum.StrEnum):
    IDLE = "idle"
    CALLING = "calling"
    RETRY_PENDING = "retry_pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


TERMINAL_STATES = frozenset({CallState.SUCCEEDED, CallState.FAILED})


class RetryStateMachine:
    """Tracks one run's model calls; hard-enforces the call limit."""

    def __init__(
        self,
        max_calls: int = MAX_MODEL_CALLS_PER_RUN,
        *,
        default_delay: float = DEFAULT_RETRY_DELAY_SECONDS,
    ) -> None:
        if isinstance(max_calls, bool) or not 1 <= max_calls <= MAX_MODEL_CALLS_PER_RUN:
            raise ValueError(f"max_calls must be between 1 and {MAX_MODEL_CALLS_PER_RUN}")
        if default_delay < 0:
            raise ValueError("default_delay must be non-negative")
        self._max_calls = max_calls
        self._default_delay = default_delay
        self._calls_made = 0
        self._state = CallState.IDLE
        self._failures: list[CallFailure] = []

    @property
    def state(self) -> CallState:
        return self._state

    @property
    def calls_made(self) -> int:
        return self._calls_made

    @property
    def failures(self) -> tuple[CallFailure, ...]:
        return tuple(self._failures)

    def ensure_can_start(self) -> None:
        if self._state in TERMINAL_STATES:
            raise CallLimitError(f"model generation already ended ({self._state}); no further calls allowed")
        if self._state is CallState.CALLING:
            raise CallLimitError("a model call is already in progress")
        if self._calls_made >= self._max_calls:
            raise CallLimitError(f"model call limit of {self._max_calls} per run reached")

    def start_call(self) -> int:
        """Begin a call; returns its 1-based attempt number."""
        self.ensure_can_start()
        self._calls_made += 1
        self._state = CallState.CALLING
        return self._calls_made

    def record_success(self) -> None:
        self._require_calling()
        self._state = CallState.SUCCEEDED

    def record_failure(self, failure: CallFailure) -> RetryDecision:
        self._require_calling()
        self._failures.append(failure)
        decision = decide_retry(
            self._calls_made, failure, max_calls=self._max_calls, default_delay=self._default_delay
        )
        self._state = CallState.RETRY_PENDING if decision.retry else CallState.FAILED
        return decision

    def abort(self) -> None:
        """End the run without another call (e.g. budget blocked the retry)."""
        self._state = CallState.FAILED

    def _require_calling(self) -> None:
        if self._state is not CallState.CALLING:
            raise RuntimeError("no model call in progress")
