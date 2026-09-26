"""Mock-transport tests for the single-gateway adapter (Requirements 3.11, 6.3–6.11, 9.3–9.6).

No real network: every request goes to an ``httpx.MockTransport`` handler.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone

import httpx
import pytest

from content_pipeline.budget import (
    INPUT_PRICE_ENV,
    MAX_COST_PER_ARTICLE_ENV,
    MAX_COST_PER_RUN_ENV,
    MAX_INPUT_TOKENS_ENV,
    MAX_OUTPUT_TOKENS_ENV,
    OUTPUT_PRICE_ENV,
)
from content_pipeline.compliance import (
    REQUIRED_FORBIDDEN_CAPABILITIES,
    REQUIRED_FORBIDDEN_CREDENTIALS,
    REQUIRED_FORBIDDEN_DEPENDENCIES,
    REQUIRED_REVIEW_ITEMS,
    validate_policy,
)
from content_pipeline.errors import (
    ArticleValidationError,
    BudgetExceededError,
    CallLimitError,
    ComplianceError,
    ConfigError,
    FieldIssue,
    ModelCallError,
)
from content_pipeline.gateway_config import CREDENTIAL_ENV, GATEWAY_ENV, MODEL_ENV
from content_pipeline.model_gateway import create_model_gateway
from content_pipeline.retry import DEFAULT_RETRY_DELAY_SECONDS

ENDPOINT = "https://gateway.example.com/v1/chat/completions"
MODEL = "vendor/model-a"
SECRET = "sk-test-0123456789abcdef"
NOW = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
MESSAGES = [{"role": "system", "content": "Write a draft."}, {"role": "user", "content": "topic"}]

POLICY = validate_policy(
    {
        "policy_version": 1,
        "gateway": "litellm",
        "model_endpoint": ENDPOINT,
        "allowed_endpoints": [ENDPOINT],
        "model": MODEL,
        "max_model_calls_per_run": 2,
        "human_editorial_gate": {
            "review_items": list(REQUIRED_REVIEW_ITEMS),
            "draft_transition": {"from": True, "to": False},
            "performed_by": "human",
            "publish_via": "pull_request_merge",
        },
        "forbidden_dependencies": sorted(REQUIRED_FORBIDDEN_DEPENDENCIES),
        "forbidden_credentials": sorted(REQUIRED_FORBIDDEN_CREDENTIALS),
        "forbidden_capabilities": sorted(REQUIRED_FORBIDDEN_CAPABILITIES),
    }
)

ENV = {
    GATEWAY_ENV: "litellm",
    MODEL_ENV: MODEL,
    CREDENTIAL_ENV: SECRET,
    INPUT_PRICE_ENV: "0.15",
    OUTPUT_PRICE_ENV: "0.60",
    MAX_INPUT_TOKENS_ENV: "4000",
    MAX_OUTPUT_TOKENS_ENV: "2000",
    MAX_COST_PER_ARTICLE_ENV: "0.01",
    MAX_COST_PER_RUN_ENV: "0.02",
}


def _ok(content: str = "draft text") -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": content}}]})


class Recorder:
    """Replays scripted responses/exceptions and records every request."""

    def __init__(self, *script: httpx.Response | Exception) -> None:
        self.script = list(script)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _gateway(recorder: Recorder, env=None, policy=POLICY, sleeps=None):
    sleeps = [] if sleeps is None else sleeps
    return create_model_gateway(
        ENV if env is None else env,
        policy,
        transport=httpx.MockTransport(recorder),
        sleep=sleeps.append,
        clock=lambda: NOW,
    )


def _assert_no_secret(exc: BaseException) -> None:
    assert SECRET not in str(exc) and SECRET not in repr(exc)


def test_success_is_a_single_call_to_the_whitelisted_endpoint_and_model() -> None:
    recorder = Recorder(_ok("hello"))
    with _gateway(recorder) as gateway:
        result = gateway.generate(MESSAGES)
    assert (result.value, result.calls_made) == ("hello", 1)
    assert str(result.estimated_cost) == "0.001800"
    [request] = recorder.requests
    assert request.method == "POST" and str(request.url) == ENDPOINT
    assert request.headers["Authorization"] == f"Bearer {SECRET}"
    body = json.loads(request.content)
    assert body == {"model": MODEL, "messages": MESSAGES, "max_tokens": 2000}


def test_no_further_calls_after_successful_generation() -> None:
    recorder = Recorder(_ok(), _ok())
    gateway = _gateway(recorder)
    gateway.generate(MESSAGES)
    with pytest.raises(CallLimitError):
        gateway.generate(MESSAGES)
    assert len(recorder.requests) == 1


@pytest.mark.parametrize(
    "first",
    [
        httpx.Response(500),
        httpx.Response(503),
        httpx.Response(429),
        httpx.ConnectTimeout("timed out"),
        httpx.ReadTimeout("timed out"),
        httpx.ConnectError("refused"),
        httpx.ReadError("reset"),
        httpx.RemoteProtocolError("server disconnected"),
    ],
    ids=lambda item: type(item).__name__ + str(getattr(item, "status_code", "")),
)
def test_retryable_network_error_retries_exactly_once(first) -> None:
    sleeps: list[float] = []
    recorder = Recorder(first, _ok("second"))
    result = _gateway(recorder, sleeps=sleeps).generate(MESSAGES)
    assert (result.value, result.calls_made) == ("second", 2)
    assert len(recorder.requests) == 2
    assert sleeps == [DEFAULT_RETRY_DELAY_SECONDS]


@pytest.mark.parametrize(
    "retry_after,expected", [("7", 7.0), ("Wed, 01 Jan 2025 12:00:30 GMT", 30.0)]
)
def test_429_retry_after_is_waited_before_the_single_retry(retry_after, expected) -> None:
    sleeps: list[float] = []
    recorder = Recorder(httpx.Response(429, headers={"Retry-After": retry_after}), _ok())
    _gateway(recorder, sleeps=sleeps).generate(MESSAGES)
    assert sleeps == [expected]
    assert len(recorder.requests) == 2


def test_two_retryable_failures_end_the_run_after_two_calls() -> None:
    recorder = Recorder(httpx.Response(429, headers={"Retry-After": "1"}), httpx.Response(502), _ok())
    gateway = _gateway(recorder)
    with pytest.raises(ModelCallError) as exc:
        gateway.generate(MESSAGES)
    assert (exc.value.kind, exc.value.status, exc.value.calls_made) == ("http_5xx", 502, 2)
    with pytest.raises(CallLimitError):
        gateway.generate(MESSAGES)
    assert len(recorder.requests) == 2
    _assert_no_secret(exc.value)


@pytest.mark.parametrize(
    "response,kind",
    [
        (httpx.Response(400, json={"error": SECRET}), "http_4xx"),
        (httpx.Response(401), "http_4xx"),
        (httpx.Response(404), "http_4xx"),
        (httpx.Response(307, headers={"Location": "https://evil.example.com/"}), "unexpected_status"),
        (httpx.Response(200, content=b"not json"), "parse_error"),
        (httpx.Response(200, json={"choices": []}), "parse_error"),
        (httpx.Response(200, json={"choices": [{"message": {"content": ""}}]}), "parse_error"),
    ],
)
def test_non_retryable_failures_make_one_call(response, kind) -> None:
    sleeps: list[float] = []
    recorder = Recorder(response, _ok())
    with pytest.raises(ModelCallError) as exc:
        _gateway(recorder, sleeps=sleeps).generate(MESSAGES)
    assert exc.value.kind == kind and exc.value.calls_made == 1
    assert len(recorder.requests) == 1 and sleeps == []
    _assert_no_secret(exc.value)


def test_schema_error_from_validation_is_not_retried() -> None:
    recorder = Recorder(_ok("{}"), _ok())
    gateway = _gateway(recorder)

    def validate(text: str):
        raise ArticleValidationError([FieldIssue("title", "must be a non-empty string")])

    with pytest.raises(ArticleValidationError):
        gateway.generate(MESSAGES, validate)
    with pytest.raises(CallLimitError):
        gateway.generate(MESSAGES)
    assert len(recorder.requests) == 1


@pytest.mark.parametrize(
    "key", [GATEWAY_ENV, MODEL_ENV, CREDENTIAL_ENV, INPUT_PRICE_ENV, MAX_COST_PER_RUN_ENV]
)
def test_missing_configuration_makes_zero_calls(key) -> None:
    recorder = Recorder(_ok())
    env = {k: v for k, v in ENV.items() if k != key}
    with pytest.raises(ConfigError) as exc:
        _gateway(recorder, env=env)
    assert key in exc.value.missing
    assert recorder.requests == []
    _assert_no_secret(exc.value)


@pytest.mark.parametrize(
    "override",
    [{MAX_COST_PER_ARTICLE_ENV: "0.001"}, {MAX_COST_PER_RUN_ENV: "0.0017"}],
)
def test_over_budget_makes_zero_calls(override) -> None:
    recorder = Recorder(_ok())
    with pytest.raises(BudgetExceededError):
        _gateway(recorder, env={**ENV, **override}).generate(MESSAGES)
    assert recorder.requests == []


def test_retry_is_blocked_when_it_would_exceed_the_run_budget() -> None:
    recorder = Recorder(httpx.Response(503), _ok())
    gateway = _gateway(recorder, env={**ENV, MAX_COST_PER_RUN_ENV: "0.0020"})
    with pytest.raises(BudgetExceededError) as exc:
        gateway.generate(MESSAGES)
    assert exc.value.limit == MAX_COST_PER_RUN_ENV
    assert len(recorder.requests) == 1
    with pytest.raises(CallLimitError):
        gateway.generate(MESSAGES)


@pytest.mark.parametrize(
    "key,value", [(GATEWAY_ENV, "openrouter"), (MODEL_ENV, "vendor/model-b")]
)
def test_gateway_or_model_mismatch_with_checklist_makes_zero_calls(key, value) -> None:
    recorder = Recorder(_ok())
    with pytest.raises(ComplianceError) as exc:
        _gateway(recorder, env={**ENV, key: value})
    assert key in exc.value.fields
    assert recorder.requests == []


@pytest.mark.parametrize(
    "endpoint",
    ["https://other.example.com/v1/chat/completions", "http://gateway.example.com/v1/chat/completions"],
)
def test_non_whitelisted_model_endpoint_makes_zero_calls(endpoint) -> None:
    recorder = Recorder(_ok())
    policy = replace(POLICY, model_endpoint=endpoint)
    with pytest.raises(ComplianceError) as exc:
        _gateway(recorder, policy=policy)
    assert endpoint not in str(exc.value)
    assert recorder.requests == []


def test_request_guard_blocks_any_other_target() -> None:
    recorder = Recorder(_ok())
    gateway = _gateway(recorder)
    with pytest.raises(ComplianceError):
        gateway._client.get("https://other.example.com/")  # noqa: SLF001 - defence-in-depth check
    assert recorder.requests == []


def test_invalid_messages_are_rejected_before_any_call() -> None:
    recorder = Recorder(_ok())
    gateway = _gateway(recorder)
    with pytest.raises(ValueError):
        gateway.generate([{"role": "assistant", "content": "x"}])
    with pytest.raises(ValueError):
        gateway.generate([])
    assert recorder.requests == [] and gateway.calls_made == 0
