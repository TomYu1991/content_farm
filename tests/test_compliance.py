"""Unit tests for the Compliance_Checklist policy (Requirements 9.1–9.8)."""

from __future__ import annotations

import copy
import json
import tomllib
from pathlib import Path

import pytest
import yaml

from content_pipeline.compliance import (
    DEFAULT_POLICY_PATH,
    REQUIRED_FORBIDDEN_CAPABILITIES,
    REQUIRED_FORBIDDEN_CREDENTIALS,
    REQUIRED_FORBIDDEN_DEPENDENCIES,
    REQUIRED_REVIEW_ITEMS,
    is_https_endpoint,
    load_policy,
    parse_policy_text,
    validate_policy,
)
from content_pipeline.errors import ComplianceError
from content_pipeline.gateway_config import CREDENTIAL_ENV, GATEWAY_ENV, MODEL_ENV, resolve_gateway_config

REPO_ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "https://gateway.example.com/v1/chat/completions"
SECRET = "sk-test-0123456789abcdef"

VALID_META = {
    "policy_version": 1,
    "gateway": "litellm",
    "model_endpoint": ENDPOINT,
    "allowed_endpoints": [ENDPOINT],
    "model": "vendor/model-a",
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


def _meta(**overrides):
    meta = copy.deepcopy(VALID_META)
    meta.update(overrides)
    return meta


def _fields(meta) -> tuple[str, ...]:
    with pytest.raises(ComplianceError) as exc:
        validate_policy(meta, "docs/compliance.md")
    return exc.value.fields


# --- the repository checklist ------------------------------------------------


def test_repository_checklist_loads_and_body_lists_policy_values() -> None:
    path = REPO_ROOT / DEFAULT_POLICY_PATH
    policy = load_policy(path, display_path="docs/compliance.md")

    assert policy.gateway in {"litellm", "openrouter"}
    assert policy.max_model_calls_per_run == 2
    assert policy.review_items == REQUIRED_REVIEW_ITEMS
    assert policy.model_endpoint in policy.allowed_endpoints
    assert all(e.startswith("https://") for e in policy.allowed_endpoints)

    body = path.read_text(encoding="utf-8").split("\n---\n", 1)[1]
    # Human-readable checklist must not drift from the machine-readable policy.
    for value in (policy.gateway, policy.model, *policy.allowed_endpoints):
        assert value in body
    for label in ("事实与来源", "读者价值", "语气", "链接", "标题", "Selenium", "humanizer", "Ollama", "pgvector"):
        assert label in body


def test_project_manifests_contain_no_forbidden_dependencies() -> None:
    forbidden_packages = {"redis", "psycopg", "psycopg2", "pgvector", "prefect", "celery", "rq", "ollama",
                          "selenium", "sqlalchemy", "pg", "ioredis", "bullmq", "selenium-webdriver", "docker"}
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    py_deps = pyproject["project"]["dependencies"] + pyproject["project"]["optional-dependencies"]["dev"]
    names = {dep.split("==")[0].split("[")[0].strip().lower() for dep in py_deps}
    package = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))
    names |= {n.lower() for n in {**package.get("dependencies", {}), **package.get("devDependencies", {})}}
    assert names.isdisjoint(forbidden_packages)


# --- validation --------------------------------------------------------------


def test_valid_policy_is_parsed() -> None:
    policy = validate_policy(_meta(), "docs/compliance.md")
    assert (policy.gateway, policy.model, policy.model_endpoint) == ("litellm", "vendor/model-a", ENDPOINT)
    assert policy.allowed_endpoints == (ENDPOINT,)


@pytest.mark.parametrize(
    "overrides,field",
    [
        ({"gateway": "openai"}, "gateway"),
        ({"gateway": ["litellm", "openrouter"]}, "gateway"),
        ({"allowed_endpoints": []}, "allowed_endpoints"),
        ({"allowed_endpoints": ["http://gateway.example.com/v1"]}, "allowed_endpoints.0"),
        ({"model_endpoint": "https://other.example.com/v1"}, "model_endpoint"),
        ({"model": "model-a,model-b"}, "model"),
        ({"model": ""}, "model"),
        ({"max_model_calls_per_run": 3}, "max_model_calls_per_run"),
        ({"max_model_calls_per_run": True}, "max_model_calls_per_run"),
        ({"policy_version": 2}, "policy_version"),
    ],
)
def test_invalid_policy_fields_are_named(overrides, field) -> None:
    assert field in _fields(_meta(**overrides))


def test_missing_fields_are_all_reported() -> None:
    fields = _fields({})
    for name in ("gateway", "allowed_endpoints", "model_endpoint", "model", "max_model_calls_per_run",
                 "human_editorial_gate", "forbidden_dependencies", "forbidden_credentials",
                 "forbidden_capabilities"):
        assert name in fields


@pytest.mark.parametrize(
    "gate_overrides,field",
    [
        ({"review_items": list(REQUIRED_REVIEW_ITEMS[:4])}, "human_editorial_gate.review_items"),
        ({"review_items": [*REQUIRED_REVIEW_ITEMS, "title"]}, "human_editorial_gate.review_items"),
        ({"draft_transition": {"from": True, "to": True}}, "human_editorial_gate.draft_transition"),
        ({"performed_by": "bot"}, "human_editorial_gate.performed_by"),
        ({"publish_via": "auto"}, "human_editorial_gate.publish_via"),
    ],
)
def test_human_editorial_gate_is_enforced(gate_overrides, field) -> None:
    gate = {**VALID_META["human_editorial_gate"], **gate_overrides}
    assert field in _fields(_meta(human_editorial_gate=gate))


@pytest.mark.parametrize(
    "key,required",
    [
        ("forbidden_dependencies", REQUIRED_FORBIDDEN_DEPENDENCIES),
        ("forbidden_credentials", REQUIRED_FORBIDDEN_CREDENTIALS),
        ("forbidden_capabilities", REQUIRED_FORBIDDEN_CAPABILITIES),
    ],
)
def test_forbidden_items_cannot_be_removed_but_can_be_extended(key, required) -> None:
    for removed in required:
        assert key in _fields(_meta(**{key: sorted(required - {removed})}))
    validate_policy(_meta(**{key: [*sorted(required), "extra_item"]}))


def test_parse_errors_name_path_not_content() -> None:
    with pytest.raises(ComplianceError) as exc:
        parse_policy_text("no front matter", "docs/compliance.md")
    assert exc.value.fields == ("front-matter",) and "docs/compliance.md" in str(exc.value)

    with pytest.raises(ComplianceError) as exc:
        parse_policy_text(f"---\nmodel: [{SECRET}\n---\n", "docs/compliance.md")
    assert SECRET not in str(exc.value)


def test_load_policy_reports_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ComplianceError) as exc:
        load_policy(tmp_path / "missing.md", display_path="docs/compliance.md")
    assert exc.value.path == "docs/compliance.md"


def test_parse_accepts_crlf_and_bom() -> None:
    text = "\ufeff---\r\n" + yaml.safe_dump(VALID_META).replace("\n", "\r\n") + "---\r\n# body\r\n"
    assert parse_policy_text(text).model == "vendor/model-a"


# --- endpoint / model / gateway checks ---------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        ENDPOINT + "/",
        ENDPOINT.replace("https://", "http://"),
        ENDPOINT.replace("https://", "HTTPS://"),
        "https://GATEWAY.example.com/v1/chat/completions",
        "https://evil.example.com/v1/chat/completions",
        "https://gateway.example.com.evil.test/v1/chat/completions",
        f"https://user:{SECRET}@gateway.example.com/v1/chat/completions",
        ENDPOINT + f"?key={SECRET}",
        ENDPOINT + "#frag",
        " " + ENDPOINT,
        None,
        42,
    ],
)
def test_non_whitelisted_endpoints_are_rejected_without_echo(url) -> None:
    policy = validate_policy(_meta())
    assert policy.is_allowed_endpoint(url) is False
    with pytest.raises(ComplianceError) as exc:
        policy.require_allowed_endpoint(url)
    assert SECRET not in str(exc.value)
    if isinstance(url, str):
        assert url.strip() not in str(exc.value)


def test_exact_whitelisted_endpoint_is_allowed() -> None:
    policy = validate_policy(_meta())
    assert policy.is_allowed_endpoint(ENDPOINT)
    assert policy.require_allowed_endpoint(ENDPOINT) == ENDPOINT


def test_is_https_endpoint_rejects_malformed_urls() -> None:
    assert is_https_endpoint("https://host.example/path")
    for bad in ("https://", "https://host:notaport/", "ftp://host/", "https:///path"):
        assert not is_https_endpoint(bad)


def test_designated_model_is_exact() -> None:
    policy = validate_policy(_meta())
    assert policy.require_designated_model("vendor/model-a") == "vendor/model-a"
    for other in ("vendor/model-b", "Vendor/model-a", "vendor/model-a ", None):
        with pytest.raises(ComplianceError):
            policy.require_designated_model(other)


def test_gateway_config_must_match_policy_without_leaking_secret() -> None:
    policy = validate_policy(_meta())
    env = {GATEWAY_ENV: "litellm", MODEL_ENV: "vendor/model-a", CREDENTIAL_ENV: SECRET}
    policy.check_gateway_config(resolve_gateway_config(env))

    mismatch = resolve_gateway_config({**env, GATEWAY_ENV: "openrouter", MODEL_ENV: "vendor/model-b"})
    with pytest.raises(ComplianceError) as exc:
        policy.check_gateway_config(mismatch)
    assert exc.value.fields == (GATEWAY_ENV, MODEL_ENV)
    assert SECRET not in str(exc.value)
