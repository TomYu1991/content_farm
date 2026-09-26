"""Unit tests for GenerationRequest input validation (Requirements 3.1–3.6)."""

import pytest

from content_pipeline.errors import InputValidationError
from content_pipeline.request import REQUEST_FIELDS, GenerationRequest, validate_request

VALID = {
    "topic": "静态博客入门",
    "audience": "独立开发者",
    "keywords": "astro, markdown",
    "prompt_name": "article-draft",
    "prompt_version": "1.0.0",
}


def _with(**overrides):
    return {**VALID, **overrides}


def _issues(inputs):
    with pytest.raises(InputValidationError) as exc:
        validate_request(inputs)
    return {i.field: i.reason for i in exc.value.issues}, str(exc.value)


def test_valid_request_is_returned_unchanged() -> None:
    assert validate_request(VALID) == GenerationRequest(**VALID)


@pytest.mark.parametrize("field", REQUEST_FIELDS)
@pytest.mark.parametrize("empty", [None, "", "   ", "\t\n\u3000"])
def test_empty_or_whitespace_field_is_missing(field, empty) -> None:
    inputs = _with(**{field: empty})
    if empty is None:
        del inputs[field]
    issues, message = _issues(inputs)
    assert issues == {field: "missing"}
    assert field in message


def test_all_failing_fields_are_reported() -> None:
    issues, _ = _issues({})
    assert issues == {name: "missing" for name in REQUEST_FIELDS}


@pytest.mark.parametrize("field,limit", [("topic", 160), ("audience", 160), ("keywords", 300)])
def test_unicode_length_boundaries(field, limit) -> None:
    # Astral-plane characters count as one Unicode character each.
    validate_request(_with(**{field: "😀" * limit}))
    issues, message = _issues(_with(**{field: "😀" * (limit + 1)}))
    assert issues == {field: "too_long"}
    assert field in message and "😀" not in message


@pytest.mark.parametrize(
    "name", ["a", "article-draft", "v2-prompt-3", "a" * 64]
)
def test_valid_prompt_names(name) -> None:
    assert validate_request(_with(prompt_name=name)).prompt_name == name


@pytest.mark.parametrize(
    "name",
    ["Article", "article_draft", "-a", "a-", "a--b", "a b", "ａ", "a" * 65, "a\n"],
)
def test_invalid_prompt_names(name) -> None:
    issues, _ = _issues(_with(prompt_name=name))
    assert issues == {"prompt_name": "invalid"}


@pytest.mark.parametrize(
    "version", ["1", "1.0", "v1.0.0", "1.0.0-beta", "1.0.0.0", "١.٠.٠", "1.0.0\n", " 1.0.0"]
)
def test_invalid_prompt_versions(version) -> None:
    issues, _ = _issues(_with(prompt_version=version))
    assert issues == {"prompt_version": "invalid"}


def test_non_string_input_is_invalid() -> None:
    issues, _ = _issues(_with(topic=123))
    assert issues == {"topic": "invalid"}
