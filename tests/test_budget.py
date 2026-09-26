"""Unit tests for the Budget_Controller (Requirements 6.1–6.5, 6.12)."""

from decimal import Decimal

import pytest

from content_pipeline.budget import (
    BUDGET_ENV_KEYS,
    INPUT_PRICE_ENV,
    MAX_COST_PER_ARTICLE_ENV,
    MAX_COST_PER_RUN_ENV,
    MAX_INPUT_TOKENS_ENV,
    MAX_OUTPUT_TOKENS_ENV,
    OUTPUT_PRICE_ENV,
    BudgetController,
    estimate_cost,
    format_cost,
    resolve_budget_config,
)
from content_pipeline.errors import BudgetExceededError, ConfigError

VALID_ENV = {
    INPUT_PRICE_ENV: "0.15",
    OUTPUT_PRICE_ENV: "0.60",
    MAX_INPUT_TOKENS_ENV: "4000",
    MAX_OUTPUT_TOKENS_ENV: "2000",
    MAX_COST_PER_ARTICLE_ENV: "0.01",
    MAX_COST_PER_RUN_ENV: "0.02",
}


def _config(**overrides: str):
    return resolve_budget_config({**VALID_ENV, **overrides})


def test_estimate_uses_formula_with_six_fixed_decimals() -> None:
    # (4000 × 0.15 + 2000 × 0.60) / 1e6 = 0.0018
    estimate = estimate_cost(_config())
    assert estimate == Decimal("0.001800")
    assert format_cost(estimate) == "0.001800"
    assert estimate.as_tuple().exponent == -6


def test_estimate_rounds_up_so_cost_is_never_understated() -> None:
    # (1 × 1 + 0 × 0) / 1e6 = 0.000001 exactly; (1 × 0.5) / 1e6 = 0.0000005 -> 0.000001
    one_input_token = {MAX_INPUT_TOKENS_ENV: "1", MAX_OUTPUT_TOKENS_ENV: "0"}
    assert estimate_cost(_config(**one_input_token, **{INPUT_PRICE_ENV: "1"})) == Decimal("0.000001")
    assert estimate_cost(_config(**one_input_token, **{INPUT_PRICE_ENV: "0.5"})) == Decimal("0.000001")
    assert estimate_cost(_config(**{INPUT_PRICE_ENV: "0", OUTPUT_PRICE_ENV: "0"})) == Decimal("0.000000")


@pytest.mark.parametrize("key", BUDGET_ENV_KEYS)
@pytest.mark.parametrize("value", [None, "", "   "])
def test_missing_budget_config_is_named(key, value) -> None:
    env = dict(VALID_ENV)
    if value is None:
        del env[key]
    else:
        env[key] = value
    with pytest.raises(ConfigError) as exc:
        resolve_budget_config(env)
    assert exc.value.missing == (key,)
    assert key in str(exc.value)


def test_all_missing_budget_config_is_reported() -> None:
    with pytest.raises(ConfigError) as exc:
        resolve_budget_config({})
    assert exc.value.missing == BUDGET_ENV_KEYS


@pytest.mark.parametrize(
    "key,value",
    [
        (INPUT_PRICE_ENV, "-1"),
        (INPUT_PRICE_ENV, "NaN"),
        (OUTPUT_PRICE_ENV, "1e3"),
        (MAX_COST_PER_RUN_ENV, "Infinity"),
        (MAX_INPUT_TOKENS_ENV, "1.5"),
        (MAX_OUTPUT_TOKENS_ENV, "-5"),
    ],
)
def test_invalid_budget_values_are_named(key, value) -> None:
    with pytest.raises(ConfigError) as exc:
        resolve_budget_config({**VALID_ENV, key: value})
    assert exc.value.invalid == (key,)
    assert value not in str(exc.value)


def test_estimate_equal_to_caps_is_allowed() -> None:
    controller = BudgetController(
        _config(**{MAX_COST_PER_ARTICLE_ENV: "0.0018", MAX_COST_PER_RUN_ENV: "0.0036"})
    )
    assert controller.reserve() == Decimal("0.001800")
    assert controller.reserve() == Decimal("0.003600")
    with pytest.raises(BudgetExceededError) as exc:
        controller.reserve()
    assert exc.value.limit == MAX_COST_PER_RUN_ENV
    assert controller.reserved == Decimal("0.003600")  # a blocked call reserves nothing


def test_estimate_above_per_article_cap_is_blocked() -> None:
    controller = BudgetController(_config(**{MAX_COST_PER_ARTICLE_ENV: "0.001799"}))
    with pytest.raises(BudgetExceededError) as exc:
        controller.reserve()
    assert exc.value.limit == MAX_COST_PER_ARTICLE_ENV
    assert exc.value.estimated_cost == "0.001800"
    assert controller.reserved == Decimal("0")


def test_reserved_plus_estimate_above_per_run_cap_is_blocked() -> None:
    controller = BudgetController(_config(**{MAX_COST_PER_RUN_ENV: "0.0020"}))
    controller.reserve()
    with pytest.raises(BudgetExceededError) as exc:
        controller.check()
    assert exc.value.limit == MAX_COST_PER_RUN_ENV
    assert (exc.value.reserved, exc.value.cap) == ("0.001800", "0.002000")
