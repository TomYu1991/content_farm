"""Compliance-bound single-gateway Model_Gateway adapter (Requirement 3.11, 6, 9.3–9.6).

The adapter talks to exactly one gateway (LiteLLM, OpenRouter *or* any other
provider exposing the OpenAI-compatible chat-completions API) at the
Compliance_Checklist's ``model_endpoint`` with the designated model. Before
any network access it:

1. checks the runtime gateway/model/base-URL configuration against the checklist,
2. requires ``model_endpoint`` to be an exact Allowed_Network_Endpoint, and
3. reserves the call's estimated cost with the Budget_Controller.

The HTTP client never follows redirects, ignores proxy/netrc environment
settings (``trust_env=False``) and re-checks every outgoing request URL
against the whitelisted endpoint. Retries follow :mod:`content_pipeline.retry`
(at most two calls per run). Tests inject an ``httpx`` transport and a sleep
function, so no real network or waiting is needed.

Errors carry only classified categories, HTTP status codes and configuration
names; response bodies, URLs, headers and the credential are never included.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Generic, TypeVar

import httpx

from .budget import BudgetController, resolve_budget_config
from .compliance import CompliancePolicy
from .errors import ComplianceError, ModelCallError
from .gateway_config import GatewayConfig, resolve_gateway_config
from .retry import (
    CallFailure,
    FailureKind,
    RetryStateMachine,
    classify_status,
    is_retryable,
    parse_retry_after,
)

T = TypeVar("T")

DEFAULT_TIMEOUT = httpx.Timeout(120.0, connect=10.0)
ALLOWED_ROLES: frozenset[str] = frozenset({"system", "user"})


@dataclass(frozen=True)
class GenerationResult(Generic[T]):
    """A successful generation plus redaction-safe audit figures."""

    value: T
    calls_made: int
    estimated_cost: Decimal
    reserved_cost: Decimal


class _GatewayFailure(Exception):
    """Internal: one call attempt failed with a classified failure."""

    def __init__(self, failure: CallFailure) -> None:
        self.failure = failure
        super().__init__(str(failure.kind))


def _validate_messages(messages: Sequence[Mapping[str, str]]) -> list[dict[str, str]]:
    if not messages:
        raise ValueError("messages must not be empty")
    checked: list[dict[str, str]] = []
    for message in messages:
        role = message.get("role")
        content = message.get("content")
        if role not in ALLOWED_ROLES or not isinstance(content, str) or content == "":
            raise ValueError("each message needs a system/user role and non-empty content")
        checked.append({"role": role, "content": content})
    return checked


def _extract_content(response: httpx.Response) -> str:
    """Return ``choices[0].message.content`` or raise a parse failure."""
    try:
        payload = json.loads(response.content)
        content = payload["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise _GatewayFailure(CallFailure(FailureKind.PARSE_ERROR, status=response.status_code)) from None
    if not isinstance(content, str) or content.strip() == "":
        raise _GatewayFailure(CallFailure(FailureKind.PARSE_ERROR, status=response.status_code))
    return content


class ModelGateway:
    """One run's gateway: single endpoint, single model, at most two calls."""

    def __init__(
        self,
        policy: CompliancePolicy,
        config: GatewayConfig,
        budget: BudgetController,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
    ) -> None:
        policy.check_gateway_config(config)
        self._model = policy.require_designated_model(config.model)
        self._endpoint = policy.require_allowed_endpoint(policy.model_endpoint)
        self._endpoint_url = httpx.URL(self._endpoint)
        self._policy = policy
        self._config = config
        self._budget = budget
        self._sleep = sleep
        self._clock = clock
        self._machine = RetryStateMachine(policy.max_model_calls_per_run)
        self._client = httpx.Client(
            transport=transport,
            follow_redirects=False,
            trust_env=False,
            timeout=timeout,
            event_hooks={"request": [self._guard_request]},
        )

    # -- public API ------------------------------------------------------

    @property
    def gateway(self) -> str:
        return self._config.gateway

    @property
    def model(self) -> str:
        return self._model

    @property
    def calls_made(self) -> int:
        return self._machine.calls_made

    @property
    def state_machine(self) -> RetryStateMachine:
        return self._machine

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> ModelGateway:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def generate(
        self,
        messages: Sequence[Mapping[str, str]],
        validate: Callable[[str], T] = lambda text: text,  # type: ignore[assignment,return-value]
    ) -> GenerationResult[T]:
        """Generate once (with at most one network retry) and validate the result.

        ``validate`` turns the model text into the caller's result (e.g. JSON
        parse + Article_Schema assembly). Any exception it raises ends the run
        immediately without a retry. Only one successful generation is
        allowed per gateway instance (i.e. per run).

        Raises:
            CallLimitError: the run already ended or reached its call limit.
            BudgetExceededError: the (next) call would exceed a budget cap.
            ModelCallError: the call failed and cannot (or may no longer) be retried.
        """
        body = {
            "model": self._model,
            "messages": _validate_messages(messages),
            "max_tokens": self._budget.config.max_output_tokens,
        }
        while True:
            self._machine.ensure_can_start()
            try:
                self._budget.reserve()
            except Exception:
                self._machine.abort()
                raise
            attempt = self._machine.start_call()
            try:
                text = self._call_once(body)
            except _GatewayFailure as failure:
                decision = self._machine.record_failure(failure.failure)
                if not decision.retry:
                    raise self._error(failure.failure) from None
                if decision.delay > 0:
                    self._sleep(decision.delay)
                continue
            except BaseException:
                # e.g. the request guard blocked a non-whitelisted target.
                self._machine.abort()
                raise
            try:
                value = validate(text)
            except BaseException:
                # Parse/schema errors are never retried (Requirement 6.8).
                self._machine.record_failure(CallFailure(FailureKind.SCHEMA_ERROR))
                raise
            self._machine.record_success()
            return GenerationResult(
                value=value,
                calls_made=attempt,
                estimated_cost=self._budget.estimated_cost,
                reserved_cost=self._budget.reserved,
            )

    # -- internals ---------------------------------------------------------

    def _guard_request(self, request: httpx.Request) -> None:
        # Defence in depth: nothing but a POST to the whitelisted endpoint may leave.
        if request.method != "POST" or request.url != self._endpoint_url:
            raise ComplianceError(
                f"network endpoint is not an Allowed_Network_Endpoint in {self._policy.path}",
                path=self._policy.path,
            )

    def _call_once(self, body: dict[str, Any]) -> str:
        headers = {
            "Authorization": f"Bearer {self._config.credential}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            response = self._client.post(self._endpoint, json=body, headers=headers)
        except httpx.TimeoutException:
            raise _GatewayFailure(CallFailure(FailureKind.CONNECT_TIMEOUT)) from None
        except (httpx.NetworkError, httpx.RemoteProtocolError):
            raise _GatewayFailure(CallFailure(FailureKind.CONNECTION_INTERRUPTED)) from None
        except httpx.DecodingError:
            raise _GatewayFailure(CallFailure(FailureKind.PARSE_ERROR)) from None
        except httpx.HTTPError:
            raise _GatewayFailure(CallFailure(FailureKind.TRANSPORT_ERROR)) from None

        kind = classify_status(response.status_code)
        if kind is not None:
            retry_after = None
            if kind is FailureKind.HTTP_429:
                retry_after = parse_retry_after(response.headers.get("Retry-After"), self._clock())
            raise _GatewayFailure(CallFailure(kind, status=response.status_code, retry_after=retry_after))
        return _extract_content(response)

    def _error(self, failure: CallFailure) -> ModelCallError:
        return ModelCallError(
            str(failure.kind),
            status=failure.status,
            calls_made=self._machine.calls_made,
            retryable=is_retryable(failure.kind),
        )


def create_model_gateway(
    env: Mapping[str, str],
    policy: CompliancePolicy,
    *,
    transport: httpx.BaseTransport | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    timeout: httpx.Timeout = DEFAULT_TIMEOUT,
) -> ModelGateway:
    """Resolve gateway + budget configuration and build the adapter.

    Every configuration, compliance and budget-configuration failure raises
    here, before any client can send a request.
    """
    config = resolve_gateway_config(env)
    budget = BudgetController(resolve_budget_config(env))
    return ModelGateway(policy, config, budget, transport=transport, sleep=sleep, clock=clock, timeout=timeout)
