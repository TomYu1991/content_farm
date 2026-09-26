"""Validation of the five manual ``workflow_dispatch`` inputs (Requirement 3.1–3.6).

Validation runs before any Prompt_Store lookup or Model_Gateway call. Failure
messages name the offending fields only; the submitted values are not echoed.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .errors import FieldIssue, InputValidationError

# Input field names, in the order they are reported.
REQUEST_FIELDS: tuple[str, ...] = (
    "topic",
    "audience",
    "keywords",
    "prompt_name",
    "prompt_version",
)

# Maximum lengths counted in Unicode code points (Python ``len`` on ``str``).
MAX_LENGTHS: dict[str, int] = {
    "topic": 160,
    "audience": 160,
    "keywords": 300,
    "prompt_name": 64,
}

# Explicit ASCII classes (not \d / \w) so non-ASCII digits and letters are rejected.
PROMPT_NAME_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
PROMPT_VERSION_PATTERN = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")


def is_valid_prompt_name(value: str) -> bool:
    return len(value) <= MAX_LENGTHS["prompt_name"] and (
        PROMPT_NAME_PATTERN.fullmatch(value) is not None
    )


def is_valid_prompt_version(value: str) -> bool:
    return PROMPT_VERSION_PATTERN.fullmatch(value) is not None


@dataclass(frozen=True)
class GenerationRequest:
    """A validated generation request. Values are kept exactly as submitted."""

    topic: str
    audience: str
    keywords: str
    prompt_name: str
    prompt_version: str


def _check_field(name: str, value: Any) -> FieldIssue | None:
    if value is None:
        return FieldIssue(name, "missing")
    if not isinstance(value, str):
        return FieldIssue(name, "invalid")
    if value.strip() == "":
        return FieldIssue(name, "missing")
    if name == "prompt_name":
        return None if is_valid_prompt_name(value) else FieldIssue(name, "invalid")
    if name == "prompt_version":
        return None if is_valid_prompt_version(value) else FieldIssue(name, "invalid")
    if len(value) > MAX_LENGTHS[name]:
        return FieldIssue(name, "too_long")
    return None


def validate_request(inputs: Mapping[str, Any]) -> GenerationRequest:
    """Validate raw workflow inputs, reporting every failing field at once.

    Raises:
        InputValidationError: naming each missing, overlong or invalid field.
    """
    issues = [
        issue
        for name in REQUEST_FIELDS
        if (issue := _check_field(name, inputs.get(name))) is not None
    ]
    if issues:
        raise InputValidationError(issues)
    return GenerationRequest(**{name: inputs[name] for name in REQUEST_FIELDS})
