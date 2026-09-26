"""Unit tests for pre-call gateway configuration and secret redaction (Requirements 3.10, 3.13)."""

import pytest

from content_pipeline.errors import ConfigError
from content_pipeline.gateway_config import (
    CREDENTIAL_ENV,
    GATEWAY_ENV,
    MODEL_ENV,
    REDACTED,
    redact,
    resolve_gateway_config,
)

SECRET = "sk-test-0123456789abcdef"
VALID_ENV = {GATEWAY_ENV: "openrouter", MODEL_ENV: "vendor/model-a", CREDENTIAL_ENV: SECRET}


def test_resolves_single_gateway_model_and_credential() -> None:
    config = resolve_gateway_config({**VALID_ENV, GATEWAY_ENV: "LiteLLM"})
    assert (config.gateway, config.model, config.credential) == ("litellm", "vendor/model-a", SECRET)
    assert SECRET not in repr(config)


@pytest.mark.parametrize("key", [GATEWAY_ENV, MODEL_ENV, CREDENTIAL_ENV])
@pytest.mark.parametrize("value", [None, "", "  "])
def test_missing_config_names_key_without_secret(key, value) -> None:
    env = dict(VALID_ENV)
    if value is None:
        del env[key]
    else:
        env[key] = value
    with pytest.raises(ConfigError) as exc:
        resolve_gateway_config(env)
    assert exc.value.missing == (key,)
    assert key in str(exc.value) and SECRET not in str(exc.value)


def test_all_missing_config_is_reported() -> None:
    with pytest.raises(ConfigError) as exc:
        resolve_gateway_config({})
    assert exc.value.missing == (GATEWAY_ENV, MODEL_ENV, CREDENTIAL_ENV)


@pytest.mark.parametrize(
    "key,value",
    [
        (GATEWAY_ENV, "openai"),
        (GATEWAY_ENV, "litellm,openrouter"),
        (MODEL_ENV, "model-a,model-b"),
        (MODEL_ENV, "model-a model-b"),
    ],
)
def test_invalid_gateway_or_multiple_models_rejected(key, value) -> None:
    with pytest.raises(ConfigError) as exc:
        resolve_gateway_config({**VALID_ENV, key: value})
    assert exc.value.invalid == (key,)
    assert SECRET not in str(exc.value)


def test_redact_masks_every_secret_occurrence() -> None:
    config = resolve_gateway_config(VALID_ENV)
    text = f"Authorization: Bearer {SECRET}; retry with {SECRET}"
    assert config.redact(text) == f"Authorization: Bearer {REDACTED}; retry with {REDACTED}"
    assert redact("abcdef", ["abc", "abcdef", ""]) == REDACTED
