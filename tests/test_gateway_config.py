"""Unit tests for pre-call gateway configuration and secret redaction (Requirements 3.10, 3.13)."""

import pytest

from content_pipeline.errors import ConfigError
from content_pipeline.gateway_config import (
    BASE_URL_ENV,
    CREDENTIAL_ENV,
    GATEWAY_ENV,
    MODEL_ENV,
    REDACTED,
    chat_completions_endpoint,
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


# --- openai_compatible gateway and MODEL_BASE_URL ---------------------------

COMPAT_ENV = {
    GATEWAY_ENV: "openai_compatible",
    MODEL_ENV: "deepseek-flash",
    CREDENTIAL_ENV: SECRET,
    BASE_URL_ENV: "https://api.deepseek.com",
}


@pytest.mark.parametrize(
    "base_url,endpoint",
    [
        ("https://api.deepseek.com", "https://api.deepseek.com/chat/completions"),
        ("https://api.deepseek.com/", "https://api.deepseek.com/chat/completions"),
        ("https://api.siliconflow.cn/v1", "https://api.siliconflow.cn/v1/chat/completions"),
        ("https://open.bigmodel.cn/api/paas/v4/", "https://open.bigmodel.cn/api/paas/v4/chat/completions"),
        ("https://api.example.com/v1/chat/completions", "https://api.example.com/v1/chat/completions"),
        ("  https://api.example.com/v1  ", "https://api.example.com/v1/chat/completions"),
    ],
)
def test_openai_compatible_base_url_becomes_chat_completions_endpoint(base_url, endpoint) -> None:
    config = resolve_gateway_config({**COMPAT_ENV, BASE_URL_ENV: base_url})
    assert (config.gateway, config.model, config.endpoint) == ("openai_compatible", "deepseek-flash", endpoint)
    assert SECRET not in repr(config)


@pytest.mark.parametrize("value", [None, "", "  "])
def test_openai_compatible_requires_base_url(value) -> None:
    env = dict(COMPAT_ENV)
    if value is None:
        del env[BASE_URL_ENV]
    else:
        env[BASE_URL_ENV] = value
    with pytest.raises(ConfigError) as exc:
        resolve_gateway_config(env)
    assert exc.value.missing == (BASE_URL_ENV,)


def test_base_url_is_optional_for_known_gateways() -> None:
    assert resolve_gateway_config(VALID_ENV).endpoint is None
    config = resolve_gateway_config({**VALID_ENV, BASE_URL_ENV: "https://openrouter.ai/api/v1"})
    assert config.endpoint == "https://openrouter.ai/api/v1/chat/completions"


@pytest.mark.parametrize(
    "base_url",
    [
        "http://api.deepseek.com",
        "api.deepseek.com",
        "https://",
        "https://user:pass@api.example.com/v1",
        "https://api.example.com/v1?key=abc",
        "https://api.example.com/v1#frag",
        "https://api.example.com/v 1",
        "https://api.example.com:notaport/v1",
    ],
)
def test_invalid_base_url_is_rejected_without_echoing_it(base_url) -> None:
    with pytest.raises(ConfigError) as exc:
        resolve_gateway_config({**COMPAT_ENV, BASE_URL_ENV: base_url})
    assert exc.value.invalid == (BASE_URL_ENV,)
    assert base_url.strip() not in str(exc.value)


@pytest.mark.parametrize(
    "base_url,expected",
    [
        ("https://api.example.com", "https://api.example.com/chat/completions"),
        ("https://api.example.com/v1/chat/completions/", "https://api.example.com/v1/chat/completions"),
        ("ftp://api.example.com", None),
    ],
)
def test_chat_completions_endpoint(base_url, expected) -> None:
    assert chat_completions_endpoint(base_url) == expected
