"""Pre-call gateway/model/credential configuration check (Requirement 3.10, 3.13).

The workflow injects configuration through environment variables (the
credential comes from a GitHub Actions secret). Exactly one gateway
(``litellm`` or ``openrouter``), one model identifier and one credential must
be present; otherwise the run fails before any Model_Gateway call, naming only
the missing or invalid configuration keys. Endpoint and model allow-listing
against the Compliance_Checklist is handled separately.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from .errors import ConfigError

GATEWAY_ENV = "MODEL_GATEWAY"
MODEL_ENV = "MODEL_ID"
CREDENTIAL_ENV = "MODEL_GATEWAY_API_KEY"

SUPPORTED_GATEWAYS: frozenset[str] = frozenset({"litellm", "openrouter"})

REDACTED = "***"


@dataclass(frozen=True)
class GatewayConfig:
    gateway: str
    model: str
    # Excluded from repr so the credential never appears in logs or tracebacks.
    credential: str = field(repr=False)

    def redact(self, text: str) -> str:
        return redact(text, [self.credential])


def _value(env: Mapping[str, str], key: str) -> str | None:
    raw = env.get(key)
    if raw is None or raw.strip() == "":
        return None
    return raw.strip()


def resolve_gateway_config(env: Mapping[str, str]) -> GatewayConfig:
    """Resolve the single gateway, model and credential, or raise ConfigError.

    ``ConfigError`` lists configuration *names* only, never their values.
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

    if missing or invalid:
        raise ConfigError(missing, invalid)
    assert gateway is not None and model is not None and credential is not None
    return GatewayConfig(gateway=gateway.lower(), model=model, credential=credential)


def redact(text: str, secrets: Iterable[str]) -> str:
    """Replace every occurrence of each non-empty secret in ``text``.

    Longer secrets are replaced first so a secret containing another is fully masked.
    """
    for secret in sorted({s for s in secrets if s}, key=len, reverse=True):
        text = text.replace(secret, REDACTED)
    return text
