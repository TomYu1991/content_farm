"""Machine-readable Compliance_Checklist loaded from ``docs/compliance.md`` (Requirement 9).

The checklist is a Markdown document whose YAML front-matter (delimited by
``---`` lines) is the single machine-readable policy; the Markdown body is the
human-readable explanation. The policy binds:

* ``gateway``: exactly one of ``litellm`` / ``openrouter``;
* ``allowed_endpoints``: the HTTPS Allowed_Network_Endpoint list and
  ``model_endpoint``: the one entry the Model_Gateway adapter may call;
* ``model``: the single designated model identifier;
* ``max_model_calls_per_run``: fixed at 2 (one call + at most one retry of a
  Retryable_Network_Error);
* ``human_editorial_gate``: the five review items and the manual
  ``draft: true -> false`` transition published only via PR merge;
* forbidden dependencies, credentials and capabilities, which must contain at
  least the permanent MVP set defined here (maintainers may add, not remove).

All checks are pure. Error messages name fields, the checklist path or
configuration keys only; URLs under test and credentials are never echoed.
Endpoint matching is exact string equality against the whitelist: no
normalisation, no other hosts, and callers must not follow redirects (any
redirect target would itself have to pass ``require_allowed_endpoint``).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

from .errors import ComplianceError, FieldIssue
from .gateway_config import GATEWAY_ENV, MODEL_ENV, SUPPORTED_GATEWAYS, GatewayConfig

DEFAULT_POLICY_PATH = Path("docs") / "compliance.md"
FRONT_MATTER_DELIMITER = "---"
SUPPORTED_POLICY_VERSIONS: frozenset[int] = frozenset({1})

# Requirement 6.9 / 9.6: one call plus at most one retry, never more.
MAX_MODEL_CALLS_PER_RUN = 2

# Human_Editorial_Gate review items (Requirement 7.3–7.4), with display labels.
REVIEW_ITEM_LABELS: dict[str, str] = {
    "facts_and_sources": "事实与来源",
    "reader_value": "读者价值",
    "tone": "语气",
    "links": "链接",
    "title": "标题",
}
REQUIRED_REVIEW_ITEMS: tuple[str, ...] = tuple(REVIEW_ITEM_LABELS)

# Requirement 9.8: permanent MVP forbidden dependencies and credentials.
REQUIRED_FORBIDDEN_DEPENDENCIES: frozenset[str] = frozenset(
    {"database", "redis", "postgres", "pgvector", "prefect", "task_queue", "vps", "docker", "ollama"}
)
REQUIRED_FORBIDDEN_CREDENTIALS: frozenset[str] = frozenset({"third_party_content_publishing"})

# Requirement 9.7: permanently forbidden capabilities.
REQUIRED_FORBIDDEN_CAPABILITIES: frozenset[str] = frozenset(
    {
        "ai_detection_evasion",
        "humanizer",
        "rate_limit_circumvention",
        "multi_account",
        "distributed_ip",
        "tos_violating_ui_automation",
        "selenium",
        "unreviewed_mass_distribution",
        "automatic_cross_platform_publishing",
    }
)


@dataclass(frozen=True)
class CompliancePolicy:
    """Validated Compliance_Checklist values consumed by the generation run."""

    policy_version: int
    gateway: str
    model_endpoint: str
    allowed_endpoints: tuple[str, ...]
    model: str
    max_model_calls_per_run: int
    review_items: tuple[str, ...]
    forbidden_dependencies: frozenset[str]
    forbidden_credentials: frozenset[str]
    forbidden_capabilities: frozenset[str]
    path: str = DEFAULT_POLICY_PATH.as_posix()

    def is_allowed_endpoint(self, url: object) -> bool:
        return is_allowed_endpoint(self, url)

    def require_allowed_endpoint(self, url: object) -> str:
        return require_allowed_endpoint(self, url)

    def require_designated_model(self, model: object) -> str:
        return require_designated_model(self, model)

    def check_gateway_config(self, config: GatewayConfig) -> None:
        check_gateway_config(self, config)


# --- endpoint / model checks -------------------------------------------------


def is_https_endpoint(value: object) -> bool:
    """True for an absolute ``https://host/...`` URL without userinfo or fragment."""
    if not isinstance(value, str) or value != value.strip() or any(ch.isspace() for ch in value):
        return False
    try:
        parts = urlsplit(value)
        _ = parts.port  # raises ValueError for malformed ports
    except ValueError:
        return False
    return (
        parts.scheme == "https"
        and bool(parts.hostname)
        and "@" not in parts.netloc
        and parts.fragment == ""
        and "#" not in value
    )


def is_allowed_endpoint(policy: CompliancePolicy, url: object) -> bool:
    """Exact whitelist match of an HTTPS URL (no normalisation, no other hosts)."""
    return is_https_endpoint(url) and url in policy.allowed_endpoints


def require_allowed_endpoint(policy: CompliancePolicy, url: object) -> str:
    """Return ``url`` if whitelisted, otherwise raise without echoing the URL."""
    if not is_allowed_endpoint(policy, url):
        raise ComplianceError(
            f"network endpoint is not an Allowed_Network_Endpoint in {policy.path}",
            path=policy.path,
        )
    assert isinstance(url, str)
    return url


def require_designated_model(policy: CompliancePolicy, model: object) -> str:
    """Return ``model`` if it is exactly the designated model identifier."""
    if not isinstance(model, str) or model != policy.model:
        raise ComplianceError(
            f"model is not the designated model in {policy.path}", path=policy.path
        )
    return model


def check_gateway_config(policy: CompliancePolicy, config: GatewayConfig) -> None:
    """Ensure the runtime gateway and model match the checklist (names only in errors)."""
    mismatched = []
    if config.gateway != policy.gateway:
        mismatched.append(GATEWAY_ENV)
    if config.model != policy.model:
        mismatched.append(MODEL_ENV)
    if mismatched:
        raise ComplianceError(
            f"configuration does not match {policy.path}",
            issues=[FieldIssue(name, "does not match Compliance_Checklist") for name in mismatched],
            path=policy.path,
        )


# --- loading / validation ----------------------------------------------------


def _split_front_matter(text: str) -> str | None:
    lines = text.split("\n")
    if not lines or lines[0] != FRONT_MATTER_DELIMITER:
        return None
    for index in range(1, len(lines)):
        if lines[index] == FRONT_MATTER_DELIMITER:
            return "\n".join(lines[1:index])
    return None


def _identifier_set(
    meta: dict[str, Any], key: str, required: frozenset[str], issues: list[FieldIssue]
) -> frozenset[str]:
    value = meta.get(key)
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        issues.append(FieldIssue(key, "must be a list of non-empty strings"))
        return frozenset()
    items = frozenset(value)
    if len(items) != len(value):
        issues.append(FieldIssue(key, "must not contain duplicates"))
    missing = sorted(required - items)
    if missing:
        issues.append(FieldIssue(key, "missing required entries: " + ", ".join(missing)))
    return items


def _validate_gate(gate: Any, issues: list[FieldIssue]) -> tuple[str, ...]:
    prefix = "human_editorial_gate"
    if not isinstance(gate, dict):
        issues.append(FieldIssue(prefix, "must be a mapping"))
        return ()

    items = gate.get("review_items")
    review_items: tuple[str, ...] = ()
    if not isinstance(items, list) or not all(isinstance(i, str) for i in items):
        issues.append(FieldIssue(f"{prefix}.review_items", "must be a list of strings"))
    elif len(items) != len(set(items)) or set(items) != set(REQUIRED_REVIEW_ITEMS):
        issues.append(
            FieldIssue(
                f"{prefix}.review_items",
                "must list exactly: " + ", ".join(REQUIRED_REVIEW_ITEMS),
            )
        )
    else:
        review_items = tuple(items)

    transition = gate.get("draft_transition")
    if not isinstance(transition, dict) or transition.get("from") is not True or transition.get("to") is not False:
        issues.append(FieldIssue(f"{prefix}.draft_transition", "must be from: true, to: false"))
    if gate.get("performed_by") != "human":
        issues.append(FieldIssue(f"{prefix}.performed_by", "must be human"))
    if gate.get("publish_via") != "pull_request_merge":
        issues.append(FieldIssue(f"{prefix}.publish_via", "must be pull_request_merge"))
    return review_items


def validate_policy(meta: Any, display_path: str = DEFAULT_POLICY_PATH.as_posix()) -> CompliancePolicy:
    """Validate parsed front-matter into a CompliancePolicy or raise ComplianceError."""
    if not isinstance(meta, dict):
        raise ComplianceError(
            f"invalid Compliance_Checklist {display_path}",
            issues=[FieldIssue("front-matter", "must be a mapping")],
            path=display_path,
        )
    issues: list[FieldIssue] = []

    version = meta.get("policy_version")
    if isinstance(version, bool) or version not in SUPPORTED_POLICY_VERSIONS:
        issues.append(FieldIssue("policy_version", "unsupported or missing"))

    gateway = meta.get("gateway")
    if not isinstance(gateway, str) or gateway not in SUPPORTED_GATEWAYS:
        issues.append(FieldIssue("gateway", "must be exactly one of: " + ", ".join(sorted(SUPPORTED_GATEWAYS))))

    endpoints_raw = meta.get("allowed_endpoints")
    endpoints: tuple[str, ...] = ()
    if not isinstance(endpoints_raw, list) or not endpoints_raw:
        issues.append(FieldIssue("allowed_endpoints", "must be a non-empty list"))
    else:
        for index, endpoint in enumerate(endpoints_raw):
            if not is_https_endpoint(endpoint):
                issues.append(FieldIssue(f"allowed_endpoints.{index}", "must be an absolute HTTPS URL"))
        if len(set(map(str, endpoints_raw))) != len(endpoints_raw):
            issues.append(FieldIssue("allowed_endpoints", "must not contain duplicates"))
        endpoints = tuple(e for e in endpoints_raw if isinstance(e, str))

    model_endpoint = meta.get("model_endpoint")
    if not is_https_endpoint(model_endpoint):
        issues.append(FieldIssue("model_endpoint", "must be an absolute HTTPS URL"))
    elif model_endpoint not in endpoints:
        issues.append(FieldIssue("model_endpoint", "must be listed in allowed_endpoints"))

    model = meta.get("model")
    if not isinstance(model, str) or model.strip() == "" or any(ch.isspace() or ch == "," for ch in model):
        issues.append(FieldIssue("model", "must be a single non-empty model identifier"))

    max_calls = meta.get("max_model_calls_per_run")
    if isinstance(max_calls, bool) or max_calls != MAX_MODEL_CALLS_PER_RUN:
        issues.append(FieldIssue("max_model_calls_per_run", f"must be {MAX_MODEL_CALLS_PER_RUN}"))

    review_items = _validate_gate(meta.get("human_editorial_gate"), issues)
    deps = _identifier_set(meta, "forbidden_dependencies", REQUIRED_FORBIDDEN_DEPENDENCIES, issues)
    creds = _identifier_set(meta, "forbidden_credentials", REQUIRED_FORBIDDEN_CREDENTIALS, issues)
    caps = _identifier_set(meta, "forbidden_capabilities", REQUIRED_FORBIDDEN_CAPABILITIES, issues)

    if issues:
        raise ComplianceError(f"invalid Compliance_Checklist {display_path}", issues=issues, path=display_path)

    return CompliancePolicy(
        policy_version=version,
        gateway=gateway,
        model_endpoint=model_endpoint,
        allowed_endpoints=endpoints,
        model=model,
        max_model_calls_per_run=max_calls,
        review_items=review_items,
        forbidden_dependencies=deps,
        forbidden_credentials=creds,
        forbidden_capabilities=caps,
        path=display_path,
    )


def parse_policy_text(text: str, display_path: str = DEFAULT_POLICY_PATH.as_posix()) -> CompliancePolicy:
    """Parse ``docs/compliance.md`` text (front-matter policy + Markdown body)."""
    normalized = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    yaml_text = _split_front_matter(normalized)
    if yaml_text is None:
        raise ComplianceError(
            f"invalid Compliance_Checklist {display_path}",
            issues=[FieldIssue("front-matter", "missing YAML front-matter delimited by '---'")],
            path=display_path,
        )
    try:
        meta = yaml.safe_load(yaml_text)
    except yaml.YAMLError:
        # Parser messages may quote file content; report only the path.
        raise ComplianceError(
            f"invalid Compliance_Checklist {display_path}",
            issues=[FieldIssue("front-matter", "not valid YAML")],
            path=display_path,
        ) from None
    return validate_policy(meta, display_path)


def load_policy(path: Path | str = DEFAULT_POLICY_PATH, display_path: str | None = None) -> CompliancePolicy:
    """Read and validate the Compliance_Checklist file."""
    file_path = Path(path)
    shown = display_path or file_path.as_posix()
    try:
        text = file_path.read_bytes().decode("utf-8")
    except FileNotFoundError:
        raise ComplianceError(f"Compliance_Checklist not found: {shown}", path=shown) from None
    except UnicodeDecodeError:
        raise ComplianceError(f"Compliance_Checklist is not valid UTF-8: {shown}", path=shown) from None
    return parse_policy_text(text, shown)
