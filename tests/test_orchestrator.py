"""Unit tests for the generation orchestration and the ``generate`` CLI command
(Requirements 3.1–3.13, 4.11, 5.1–5.8, 6.3–6.9, 7.1, 9.3–9.6).

No real network: the gateway uses an ``httpx.MockTransport``; Git changes go
to the in-memory backend.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest

from content_pipeline import cli
from content_pipeline.budget import (
    INPUT_PRICE_ENV,
    MAX_COST_PER_ARTICLE_ENV,
    MAX_COST_PER_RUN_ENV,
    MAX_INPUT_TOKENS_ENV,
    MAX_OUTPUT_TOKENS_ENV,
    OUTPUT_PRICE_ENV,
)
from content_pipeline.compliance import load_policy
from content_pipeline.draft_identity import ChangeAction, draft_path, stable_key_for
from content_pipeline.errors import ArticleValidationError, BudgetExceededError, ModelCallError
from content_pipeline.gateway_config import CREDENTIAL_ENV, GATEWAY_ENV, MODEL_ENV
from content_pipeline.git_change import InMemoryGitBackend
from content_pipeline.orchestrator import parse_model_result, run_generation
from content_pipeline.request import GenerationRequest

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "docs" / "compliance.md"
PROMPTS_DIR = ROOT / "prompts"
POLICY = load_policy(POLICY_PATH)
SECRET = "sk-orchestrator-test-0123456789"
NOW = datetime(2025, 3, 1, 9, 30, 0, tzinfo=timezone.utc)

INPUTS = {
    "topic": "Static sites",
    "audience": "Indie developers",
    "keywords": "astro, static hosting",
    "prompt_name": "article-draft",
    "prompt_version": "1.0.0",
}
REQUEST = GenerationRequest(**INPUTS)
KEY = stable_key_for(REQUEST, POLICY.model)
ENV = {
    GATEWAY_ENV: POLICY.gateway,
    MODEL_ENV: POLICY.model,
    CREDENTIAL_ENV: SECRET,
    INPUT_PRICE_ENV: "0.15",
    OUTPUT_PRICE_ENV: "0.60",
    MAX_INPUT_TOKENS_ENV: "4000",
    MAX_OUTPUT_TOKENS_ENV: "2000",
    MAX_COST_PER_ARTICLE_ENV: "0.01",
    MAX_COST_PER_RUN_ENV: "0.02",
}
CLI_ENV = {**ENV, **{cli.INPUT_ENV[name]: value for name, value in INPUTS.items()}}


def _result(**overrides: Any) -> dict[str, Any]:
    result = {
        "title": "Static sites",
        "description": "Why static hosting keeps costs low.",
        "slug": "static-sites",
        "tags": ["astro"],
        "body": "# Static sites\n\nSee [the docs](https://docs.astro.build/).\n",
        "sources": [],
        "draft": False,  # must be ignored: generated articles are always drafts
    }
    result.update(overrides)
    return result


def _ok(result: dict[str, Any]) -> httpx.Response:
    content = json.dumps(result)
    return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": content}}]})


class Recorder:
    def __init__(self, *script: httpx.Response | Exception) -> None:
        self.script = list(script)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _run(tmp_path: Path, recorder: Recorder, backend: InMemoryGitBackend, *, env=None, bundle="bundle"):
    return run_generation(
        INPUTS,
        ENV if env is None else env,
        backend,
        bundle_dir=tmp_path / bundle,
        default_branch="main",
        server_url="https://github.com",
        repository="owner/blog",
        policy_path=POLICY_PATH,
        prompts_dir=PROMPTS_DIR,
        transport=httpx.MockTransport(recorder),
        sleep=lambda _: None,
        clock=lambda: NOW,
    )


def test_valid_run_creates_one_draft_then_rerun_adds_no_commit(tmp_path: Path) -> None:
    backend = InMemoryGitBackend()
    recorder = Recorder(_ok(_result()), _ok(_result()))

    prepared, review = _run(tmp_path, recorder, backend, bundle="a")

    assert review.change.action is ChangeAction.CREATE
    assert review.change.target.branch == f"draft/{KEY}" != "main"
    assert review.change.target.path == draft_path(KEY, "static-sites")
    assert review.pr_url is None and f"compare/main...draft/{KEY}" in review.instructions
    assert "main" not in backend.branches
    content = backend.branches[f"draft/{KEY}"][review.change.target.path].decode("utf-8")
    assert "draft: true" in content and "ai_assisted: true" in content
    assert f'model: "{POLICY.model}"' in content and 'prompt_version: "1.0.0"' in content
    assert "sources: []" in content and 'pubDate: "2025-03-01T09:30:00Z"' in content

    audit = prepared.audit()
    assert audit["calls_made"] == "1"
    assert audit["estimated_cost"] == "0.001800" and audit["reserved_cost"] == "0.001800"
    assert audit["prompt"] == "article-draft@1.0.0"
    assert SECRET not in json.dumps(audit)

    # The only request went to the whitelisted endpoint with the designated model.
    sent = recorder.requests[0]
    assert str(sent.url) == POLICY.model_endpoint
    assert json.loads(sent.content)["model"] == POLICY.model

    _, again = _run(tmp_path, recorder, backend, bundle="b")
    assert again.change.action is ChangeAction.UNCHANGED
    assert len(backend.commits) == 1
    assert len(backend.branches[f"draft/{KEY}"]) == 1


def test_backend_pr_url_is_reported_when_available(tmp_path: Path) -> None:
    backend = InMemoryGitBackend(pr_url="https://github.com/owner/blog/pull/7")
    _, review = _run(tmp_path, Recorder(_ok(_result())), backend)
    assert review.pr_url == "https://github.com/owner/blog/pull/7"


def test_schema_failure_makes_no_bundle_and_no_git_change(tmp_path: Path) -> None:
    backend = InMemoryGitBackend()
    recorder = Recorder(_ok(_result(body="See [x](javascript:alert(1)).\n", title="")), _ok(_result()))

    with pytest.raises(ArticleValidationError) as exc:
        _run(tmp_path, recorder, backend)

    assert "title" in exc.value.fields
    assert any(field.startswith("body:1:") for field in exc.value.fields)
    assert len(recorder.requests) == 1  # schema errors are never retried
    assert not (tmp_path / "bundle").exists()
    assert backend.branches == {} and backend.commits == []


def test_unparseable_result_is_not_retried(tmp_path: Path) -> None:
    backend = InMemoryGitBackend()
    ok = httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]})
    recorder = Recorder(ok, ok)
    with pytest.raises(ArticleValidationError):
        _run(tmp_path, recorder, backend)
    assert len(recorder.requests) == 1 and backend.commits == []


def test_network_error_retried_once_then_run_fails(tmp_path: Path) -> None:
    backend = InMemoryGitBackend()
    recorder = Recorder(httpx.Response(503), httpx.Response(502), _ok(_result()))
    with pytest.raises(ModelCallError) as exc:
        _run(tmp_path, recorder, backend)
    assert exc.value.calls_made == 2 and len(recorder.requests) == 2
    assert backend.commits == [] and not (tmp_path / "bundle").exists()


def test_budget_block_makes_zero_model_calls(tmp_path: Path) -> None:
    recorder = Recorder(_ok(_result()))
    with pytest.raises(BudgetExceededError):
        _run(tmp_path, recorder, InMemoryGitBackend(), env={**ENV, MAX_COST_PER_ARTICLE_ENV: "0.001"})
    assert recorder.requests == []


def test_parse_model_result_accepts_one_code_fence() -> None:
    text = "```json\n" + json.dumps(_result()) + "\n```"
    assert parse_model_result(text)["slug"] == "static-sites"
    assert "draft" not in parse_model_result(text)


# --- CLI ------------------------------------------------------------------------


def _cli_generate(tmp_path: Path, env: dict[str, str], recorder: Recorder) -> int:
    return cli.main(
        [
            "generate",
            "--bundle-dir", str(tmp_path / "bundle"),
            "--policy", str(POLICY_PATH),
            "--prompts-dir", str(PROMPTS_DIR),
            "--github-output", str(tmp_path / "out"),
        ],
        env=env,
        transport=httpx.MockTransport(recorder),
        sleep=lambda _: None,
    )


def test_cli_generate_writes_bundle_and_redacted_audit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    recorder = Recorder(httpx.ConnectTimeout("timeout"), _ok(_result()))
    assert _cli_generate(tmp_path, CLI_ENV, recorder) == cli.EXIT_OK

    captured = capsys.readouterr()
    lines = (tmp_path / "out").read_text(encoding="utf-8").splitlines()
    assert f"branch=draft/{KEY}" in lines and f"stable_key={KEY}" in lines
    assert "calls_made=2" in lines and "reserved_cost=0.003600" in lines
    assert (tmp_path / "bundle" / "article.md").is_file()
    assert SECRET not in captured.out + captured.err
    # The bundle passes the draft-branch job's re-verification.
    assert cli.main(
        ["verify-bundle", "--bundle-dir", str(tmp_path / "bundle"), "--policy", str(POLICY_PATH)],
        env=CLI_ENV,
    ) == cli.EXIT_OK


@pytest.mark.parametrize(
    ("override", "named"),
    [
        ({CREDENTIAL_ENV: ""}, CREDENTIAL_ENV),
        ({cli.INPUT_ENV["prompt_version"]: "9.9.9"}, "article-draft@9.9.9"),
        ({cli.INPUT_ENV["topic"]: " "}, "topic"),
        ({MODEL_ENV: "other/model"}, MODEL_ENV),
    ],
)
def test_cli_generate_pre_call_failures_make_no_request(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], override: dict[str, str], named: str
) -> None:
    recorder = Recorder(_ok(_result()))
    assert _cli_generate(tmp_path, {**CLI_ENV, **override}, recorder) == cli.EXIT_FAILED
    err = capsys.readouterr().err
    assert named in err and SECRET not in err
    assert recorder.requests == []
    assert not (tmp_path / "bundle").exists()
