"""Error types raised before any Model_Gateway call.

Every message only names fields, prompt identifiers, configuration names or
file paths. Input values and secret values are never embedded in messages.
"""

from __future__ import annotations

from dataclasses import dataclass


class PipelineError(Exception):
    """Base class for failures that must end the Generation_Workflow."""


@dataclass(frozen=True)
class FieldIssue:
    """A single invalid field (or body location) and a value-free description.

    Request inputs use the categories "missing" | "too_long" | "invalid".
    Article_Schema issues use a field path (``sources.0.url``), ``path``, or a
    body location (``body`` / ``body:<line>:<column>``) with a short rule text.
    """

    field: str
    reason: str

    def describe(self) -> str:
        return f"{self.field}: {self.reason}"


class InputValidationError(PipelineError):
    """One or more GenerationRequest inputs are missing, too long or invalid."""

    def __init__(self, issues: list[FieldIssue]) -> None:
        self.issues = tuple(issues)
        super().__init__(
            "invalid generation input: " + "; ".join(i.describe() for i in self.issues)
        )

    @property
    def fields(self) -> tuple[str, ...]:
        return tuple(issue.field for issue in self.issues)


class PromptStoreError(PipelineError):
    """A prompt file is missing, malformed, or its (name, version) is ambiguous."""

    def __init__(self, message: str, *, paths: tuple[str, ...] = ()) -> None:
        self.paths = paths
        super().__init__(message)


class ConfigError(PipelineError):
    """Required gateway/model/credential configuration is missing or invalid."""

    def __init__(self, missing: list[str], invalid: list[str] | None = None) -> None:
        self.missing = tuple(missing)
        self.invalid = tuple(invalid or ())
        parts: list[str] = []
        if self.missing:
            parts.append("missing configuration: " + ", ".join(self.missing))
        if self.invalid:
            parts.append("invalid configuration: " + ", ".join(self.invalid))
        super().__init__("; ".join(parts))


class ArticleValidationError(PipelineError):
    """A Content_File failed Article_Schema validation; nothing was written.

    Issues name front-matter fields, ``path`` or body line/column positions
    only; field values and link targets are never echoed.
    """

    def __init__(self, issues: list[FieldIssue] | tuple[FieldIssue, ...]) -> None:
        self.issues = tuple(issues)
        super().__init__("invalid article: " + "; ".join(i.describe() for i in self.issues))

    @property
    def fields(self) -> tuple[str, ...]:
        return tuple(issue.field for issue in self.issues)


class ComplianceError(PipelineError):
    """The Compliance_Checklist is invalid, or a request target violates it.

    Messages name policy fields, the checklist path or configuration names
    only. Endpoint URLs under test are never echoed (they may carry secrets
    in query strings); neither are credentials.
    """

    def __init__(
        self,
        message: str,
        *,
        issues: list[FieldIssue] | tuple[FieldIssue, ...] = (),
        path: str | None = None,
    ) -> None:
        self.issues = tuple(issues)
        self.path = path
        details = "; ".join(i.describe() for i in self.issues)
        super().__init__(f"{message}: {details}" if details else message)

    @property
    def fields(self) -> tuple[str, ...]:
        return tuple(issue.field for issue in self.issues)


class DraftBundleError(PipelineError):
    """The generated draft bundle or its review branch target is unusable.

    Raised by the draft-branch step (Requirements 5.2–5.8). Messages name the
    bundle file, field or rule only; article content is never echoed.
    """


class BudgetExceededError(PipelineError):
    """A Model_Gateway call was blocked by the Budget_Controller (Requirement 6.4–6.5).

    ``limit`` names the exceeded cap's configuration key. Amounts are the
    non-secret, fixed six-decimal budget figures.
    """

    def __init__(self, limit: str, *, estimated_cost: str, reserved: str, cap: str) -> None:
        self.limit = limit
        self.estimated_cost = estimated_cost
        self.reserved = reserved
        self.cap = cap
        super().__init__(
            f"model call blocked by budget: {limit} exceeded "
            f"(estimated_cost={estimated_cost}, reserved={reserved}, cap={cap})"
        )


class CallLimitError(PipelineError):
    """No further Model_Gateway call is allowed in this run (Requirement 6.9, 9.6)."""


class ModelCallError(PipelineError):
    """A Model_Gateway call failed with a classified, value-free category.

    ``kind`` is a failure category (e.g. ``http_5xx``); ``status`` is the HTTP
    status when one was received. Response bodies, URLs, headers and
    credentials are never included in the message.
    """

    def __init__(self, kind: str, *, status: int | None = None, calls_made: int, retryable: bool) -> None:
        self.kind = kind
        self.status = status
        self.calls_made = calls_made
        self.retryable = retryable
        status_text = f" (HTTP {status})" if status is not None else ""
        super().__init__(
            f"model gateway call failed: {kind}{status_text} after {calls_made} call(s)"
        )
