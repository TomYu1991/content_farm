"""Pre-call gateway/model/credential configuration check (Requirement 3.10, 3.13).

The workflow injects configuration through environment variables (the
credential comes from a GitHub Actions secret). Exactly one gateway
(``litellm``, ``openrouter`` or ``openai_compatible``), one model identifier
and one credential must be present; otherwise the run fails before any
Model_Gateway call, naming only the missing or invalid configuration keys.

``openai_compatible`` covers any provider exposing the OpenAI
chat-completions API (for example DeepSeek, Zhipu or SiliconFlow). It needs
``MODEL_BASE_URL``, the provider's base URL such as ``https://api.deepseek.com``
or ``https://api.siliconflow.cn/v1``; ``/chat/completions`` is appended unless
it is already present. For the other gateways ``MODEL_BASE_URL`` is optional.

The resolved endpoint is *not* trusted on its own: the Compliance_Checklist
still has to list it as ``model_endpoint`` (exact match), so a new network
target always goes through a reviewed change of ``docs/compliance.md``.
Endpoint and model allow-listing is handled in :mod:`content_pipeline.compliance`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from .errors import ConfigError

GATEWAY_ENV = "MODEL_GATEWAY"
MODEL_ENV = "MODEL_ID"
CREDENTIAL_ENV = "MODEL_GATEWAY_API_KEY"
BASE_URL_ENV = "MODEL_BASE_URL"

OPENAI_COMPATIBLE = "openai_compatible"
SUPPORTED_GATEWAYS: frozenset[str] = frozenset({"litellm", "openrouter", OPENAI_COMPATIBLE})
# Gateways without a well-known endpoint: the base URL must be configured explicitly.
GATEWAYS_REQUIRING_BASE_URL: frozenset[str] = frozenset({OPENAI_COMPATIBLE})

CHAT_COMPLETIONS_PATH = "/chat/completions"

REDACTED = "***"


@dataclass(frozen=True)
class GatewayConfig:
    gateway: str
    model: str
    # Excluded from repr so the credential never appears in logs or tracebacks.
    credential: str = field(repr=False)
    # Chat-completions URL derived from MODEL_BASE_URL, or None when not configured.
    endpoint: str | None = None

    def redact(self, text: str) -> str:
        return redact(text, [self.credential])


def _value(env: Mapping[str, str], key: str) -> str | None:
    raw = env.get(key)
    if raw is None or raw.strip() == "":
        return None
    return raw.strip()


def chat_completions_endpoint(base_url: str) -> str | None:
    """Return ``<base_url>/chat/completions`` for a plain HTTPS base URL, else None.

    Trailing slashes are ignored and a URL that already ends with
    ``/chat/completions`` is kept as is. Userinfo, query strings, fragments,
    whitespace and non-HTTPS schemes are rejected.
    """
    if any(ch.isspace() for ch in base_url):
        return None
    try:
        parts = urlsplit(base_url)
        _ = parts.port  # raises ValueError for malformed ports
    except ValueError:
        return None
    if (
        parts.scheme != "https"
        or not parts.hostname
        or "@" in parts.netloc
        or parts.query
        or parts.fragment
        or "?" in base_url
        or "#" in base_url
    ):
        return None
    trimmed = base_url.rstrip("/")
    if trimmed.endswith(CHAT_COMPLETIONS_PATH):
        return trimmed
    return trimmed + CHAT_COMPLETIONS_PATH


def resolve_gateway_config(env: Mapping[str, str]) -> GatewayConfig:
    """Resolve the single gateway, model, credential and optional base URL.

    Raises ``ConfigError`` listing configuration *names* only, never their values.
    """
    missing: list[str] = []
    invalid: list[str] = []

    gateway = _value(env, GATEWAY_ENV)
    if gateway is None:
        missing.append(GATEWAY_ENV)
    elif gateway.lower() not in SUPPORTED_GATEWAYS:
        # Covers unknown gateways and multi-valued settings like "litellm,openrouter".
        invalid.append(GATEWAY_ENV)

    model = _value(env, MODEL_ENV)
    if model is None:
        missing.append(MODEL_ENV)
    elif any(ch.isspace() or ch == "," for ch in model):
        # A single model identifier only; lists would enable multi-model routing.
        invalid.append(MODEL_ENV)

    credential = _value(env, CREDENTIAL_ENV)
    if credential is None:
        missing.append(CREDENTIAL_ENV)

    base_url = _value(env, BASE_URL_ENV)
    endpoint: str | None = None
    if base_url is None:
        if gateway is not None and gateway.lower() in GATEWAYS_REQUIRING_BASE_URL:
            missing.append(BASE_URL_ENV)
    else:
        endpoint = chat_completions_endpoint(base_url)
        if endpoint is None:
            invalid.append(BASE_URL_ENV)

    if missing or invalid:
        raise ConfigError(missing, invalid)
    assert gateway is not None and model is not None and credential is not None
    return GatewayConfig(gateway=gateway.lower(), model=model, credential=credential, endpoint=endpoint)


def redact(text: str, secrets: Iterable[str]) -> str:
    """Replace every occurrence of each non-empty secret in ``text``.

    Longer secrets are replaced first so a secret containing another is fully masked.
    """
    for secret in sorted({s for s in secrets if s}, key=len, reverse=True):
        text = text.replace(secret, REDACTED)
    return text
