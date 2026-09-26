"""Pre-call Budget_Controller (Requirement 6.1–6.5, 6.12).

Six configuration values are required (all read from the environment):
per-million-token input/output unit prices, maximum input/output tokens,
and the per-article and per-run cost caps. Any missing value fails the run
before a Model_Gateway call, naming only the missing configuration keys.

``estimated_cost = (max_input_tokens × input_unit_price
                    + max_output_tokens × output_unit_price) / 1_000_000``

is computed exactly with :class:`decimal.Decimal` and quantized to six fixed
decimals, rounding *up* so the estimate never understates spend.

Every model call attempt (including the single permitted retry) reserves one
``estimated_cost`` in memory. A call is blocked when the estimate exceeds the
per-article cap, or when the estimate plus the run's already-reserved cost
exceeds the per-run cap; equality is allowed. No database, ledger, queue or
concurrent transaction record is used: the reservation lives only for the run.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_UP, Decimal, localcontext

from .errors import BudgetExceededError, ConfigError

INPUT_PRICE_ENV = "BUDGET_INPUT_PRICE_PER_MTOK"
OUTPUT_PRICE_ENV = "BUDGET_OUTPUT_PRICE_PER_MTOK"
MAX_INPUT_TOKENS_ENV = "BUDGET_MAX_INPUT_TOKENS"
MAX_OUTPUT_TOKENS_ENV = "BUDGET_MAX_OUTPUT_TOKENS"
MAX_COST_PER_ARTICLE_ENV = "BUDGET_MAX_COST_PER_ARTICLE"
MAX_COST_PER_RUN_ENV = "BUDGET_MAX_COST_PER_RUN"

BUDGET_ENV_KEYS: tuple[str, ...] = (
    INPUT_PRICE_ENV,
    OUTPUT_PRICE_ENV,
    MAX_INPUT_TOKENS_ENV,
    MAX_OUTPUT_TOKENS_ENV,
    MAX_COST_PER_ARTICLE_ENV,
    MAX_COST_PER_RUN_ENV,
)

TOKENS_PER_UNIT = Decimal(1_000_000)
COST_QUANTUM = Decimal("0.000001")

# Plain non-negative decimals only (no exponent, sign, NaN or Infinity), with
# bounded length so parsing and arithmetic stay exact and cheap.
_AMOUNT_RE = re.compile(r"^[0-9]{1,15}(?:\.[0-9]{1,12})?$")
_TOKENS_RE = re.compile(r"^[0-9]{1,12}$")
# Enough precision for 15+12 digit amounts times 12 digit token counts.
_PRECISION = 60


@dataclass(frozen=True)
class BudgetConfig:
    input_unit_price: Decimal  # per 1,000,000 input tokens
    output_unit_price: Decimal  # per 1,000,000 output tokens
    max_input_tokens: int
    max_output_tokens: int
    max_cost_per_article: Decimal
    max_cost_per_run: Decimal


def _value(env: Mapping[str, str], key: str) -> str | None:
    raw = env.get(key)
    if raw is None or raw.strip() == "":
        return None
    return raw.strip()


def resolve_budget_config(env: Mapping[str, str]) -> BudgetConfig:
    """Resolve all six budget values, or raise ConfigError naming keys only."""
    missing: list[str] = []
    invalid: list[str] = []
    amounts: dict[str, Decimal] = {}
    tokens: dict[str, int] = {}

    for key in BUDGET_ENV_KEYS:
        raw = _value(env, key)
        if raw is None:
            missing.append(key)
        elif key in (MAX_INPUT_TOKENS_ENV, MAX_OUTPUT_TOKENS_ENV):
            if _TOKENS_RE.fullmatch(raw):
                tokens[key] = int(raw)
            else:
                invalid.append(key)
        elif _AMOUNT_RE.fullmatch(raw):
            amounts[key] = Decimal(raw)
        else:
            invalid.append(key)

    if missing or invalid:
        raise ConfigError(missing, invalid)
    return BudgetConfig(
        input_unit_price=amounts[INPUT_PRICE_ENV],
        output_unit_price=amounts[OUTPUT_PRICE_ENV],
        max_input_tokens=tokens[MAX_INPUT_TOKENS_ENV],
        max_output_tokens=tokens[MAX_OUTPUT_TOKENS_ENV],
        max_cost_per_article=amounts[MAX_COST_PER_ARTICLE_ENV],
        max_cost_per_run=amounts[MAX_COST_PER_RUN_ENV],
    )


def estimate_cost(config: BudgetConfig) -> Decimal:
    """Exact formula result quantized (rounding up) to six fixed decimals."""
    with localcontext() as ctx:
        ctx.prec = _PRECISION
        raw = (
            Decimal(config.max_input_tokens) * config.input_unit_price
            + Decimal(config.max_output_tokens) * config.output_unit_price
        ) / TOKENS_PER_UNIT
        return raw.quantize(COST_QUANTUM, rounding=ROUND_UP)


def format_cost(amount: Decimal) -> str:
    """Render a cost as a fixed six-decimal string (e.g. ``0.001250``)."""
    with localcontext() as ctx:
        ctx.prec = _PRECISION
        return f"{amount.quantize(COST_QUANTUM, rounding=ROUND_UP):f}"


class BudgetController:
    """In-memory, per-run cost reservation guarding every model call attempt."""

    def __init__(self, config: BudgetConfig) -> None:
        self._config = config
        self._estimate = estimate_cost(config)
        self._reserved = Decimal("0").quantize(COST_QUANTUM)

    @property
    def config(self) -> BudgetConfig:
        return self._config

    @property
    def estimated_cost(self) -> Decimal:
        return self._estimate

    @property
    def reserved(self) -> Decimal:
        return self._reserved

    def check(self) -> None:
        """Raise BudgetExceededError if one more call would break a cap."""
        estimate = self._estimate
        if estimate > self._config.max_cost_per_article:
            raise BudgetExceededError(
                MAX_COST_PER_ARTICLE_ENV,
                estimated_cost=format_cost(estimate),
                reserved=format_cost(self._reserved),
                cap=format_cost(self._config.max_cost_per_article),
            )
        if estimate + self._reserved > self._config.max_cost_per_run:
            raise BudgetExceededError(
                MAX_COST_PER_RUN_ENV,
                estimated_cost=format_cost(estimate),
                reserved=format_cost(self._reserved),
                cap=format_cost(self._config.max_cost_per_run),
            )

    def reserve(self) -> Decimal:
        """Check the caps and reserve one call's estimate; returns the new total.

        A blocked call reserves nothing.
        """
        self.check()
        self._reserved += self._estimate
        return self._reserved
