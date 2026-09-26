"""Configuration checks for the Deployment_Pipeline workflow (Requirements 1.2,
1.3, 1.6, 7.6): default-branch-only trigger, build-before-deploy ordering and
hosting credentials confined to the deploy boundary."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
DEPLOY = WORKFLOWS / "deploy.yml"
DEPLOY_SECRETS = ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID")


def _load(path: Path) -> dict:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    # PyYAML (YAML 1.1) parses the bare key `on` as boolean True.
    config["on"] = config.get("on", config.pop(True, None))
    return config


def test_deploy_runs_only_on_push_to_default_branch():
    config = _load(DEPLOY)
    assert set(config["on"]) == {"push"}
    push = config["on"]["push"]
    assert push == {"branches": ["main"]}  # no draft/**, tags or paths bypass
    assert config["permissions"] == {}
    assert config["concurrency"]["cancel-in-progress"] is False
    for job in config["jobs"].values():
        assert "github.event.repository.default_branch" in job["if"]
        assert "github.event_name == 'push'" in job["if"]


def test_deploy_only_after_successful_build_and_secrets_only_in_deploy_step():
    jobs = _load(DEPLOY)["jobs"]
    assert set(jobs) == {"build", "deploy"}
    build, deploy = jobs["build"], jobs["deploy"]

    assert deploy["needs"] == "build"
    assert deploy["environment"]["name"] == "production"
    assert "environment" not in build
    for job in (build, deploy):
        assert job["permissions"] == {"contents": "read"}

    build_text = yaml.safe_dump(build)
    assert "secrets." not in build_text
    assert [s["run"] for s in build["steps"] if "run" in s][1:4] == [
        "npm ci --no-audit --no-fund",
        "npm test",
        "npm run build",
    ]

    secret_steps = [s for s in deploy["steps"] if "secrets." in yaml.safe_dump(s)]
    assert len(secret_steps) == 1
    assert secret_steps[0]["uses"].startswith("cloudflare/wrangler-action@")
    for step in deploy["steps"]:
        assert "${{" not in step.get("run", "")  # untrusted values only via env


def test_actions_are_pinned_to_commit_shas():
    for job in _load(DEPLOY)["jobs"].values():
        for step in job["steps"]:
            if "uses" in step:
                assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", step["uses"]), step["uses"]


def test_other_workflows_cannot_deploy_or_read_hosting_credentials():
    for path in WORKFLOWS.glob("*.yml"):
        if path == DEPLOY:
            continue
        text = path.read_text(encoding="utf-8")
        for secret in DEPLOY_SECRETS:
            assert secret not in text, path.name
        for marker in ("wrangler", "pages deploy", "environment:"):
            assert marker not in text.lower(), path.name
