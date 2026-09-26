"""Unit tests for the draft bundle hand-off, draft-branch apply step and CLI
used by the generation workflow (Requirements 5.2–5.8, 5.11, 7.1)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from content_pipeline import cli
from content_pipeline.article import CONTENT_ROOT, DraftArticle, assemble_draft
from content_pipeline.compliance import REVIEW_ITEM_LABELS, load_policy
from content_pipeline.draft_bundle import (
    ARTICLE_FILE,
    MANIFEST_FILE,
    apply_draft,
    load_bundle,
    pr_instructions,
    write_bundle,
)
from content_pipeline.draft_identity import ChangeAction, draft_path, stable_key_for
from content_pipeline.errors import (
    ArticleValidationError,
    ComplianceError,
    DraftBundleError,
)
from content_pipeline.request import GenerationRequest

POLICY_PATH = Path(__file__).resolve().parents[1] / "docs" / "compliance.md"
POLICY = load_policy(POLICY_PATH)
MODEL = POLICY.model
REQUEST = GenerationRequest(
    topic="Static sites",
    audience="Indie developers",
    keywords="astro, static hosting",
    prompt_name="article-draft",
    prompt_version="1.0.0",
)
KEY = stable_key_for(REQUEST, MODEL)
BRANCH = f"draft/{KEY}"
ENV = {
    "GEN_TOPIC": REQUEST.topic,
    "GEN_AUDIENCE": REQUEST.audience,
    "GEN_KEYWORDS": REQUEST.keywords,
    "GEN_PROMPT_NAME": REQUEST.prompt_name,
    "GEN_PROMPT_VERSION": REQUEST.prompt_version,
}


def _draft(slug: str = "static-sites", **overrides: Any) -> DraftArticle:
    result: dict[str, Any] = {
        "title": "Static sites",
        "description": "Why static hosting keeps costs low.",
        "slug": slug,
        "tags": ["astro"],
        "body": "# Static sites\n\nSee [the docs](https://docs.astro.build/).\n",
    }
    result.update(overrides)
    return assemble_draft(
        result,
        model=MODEL,
        prompt_version=REQUEST.prompt_version,
        pub_date="2024-05-01T08:30:00Z",
        path=draft_path(KEY, slug),
    )


def _bundle(tmp_path: Path, draft: DraftArticle | None = None) -> Path:
    return write_bundle(tmp_path / "bundle", draft or _draft(), KEY)


# --- write / load ---------------------------------------------------------


def test_bundle_roundtrip_resolves_draft_branch(tmp_path: Path) -> None:
    draft = _draft()
    bundle = _bundle(tmp_path, draft)

    verified = load_bundle(bundle, REQUEST, POLICY)

    assert verified.branch == BRANCH
    assert verified.slug == "static-sites"
    assert verified.content == draft.to_bytes()
    assert verified.front_matter["draft"] is True


def test_write_bundle_rejects_path_not_matching_key(tmp_path: Path) -> None:
    draft = _draft()
    wrong = DraftArticle(path=f"{CONTENT_ROOT}/static-sites.md", front_matter=draft.front_matter, body=draft.body)
    with pytest.raises(DraftBundleError):
        write_bundle(tmp_path / "bundle", wrong, KEY)
    assert not (tmp_path / "bundle").exists()


def test_load_rejects_key_not_matching_inputs(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    other = GenerationRequest(**{**REQUEST.__dict__, "topic": "Another topic"})
    with pytest.raises(DraftBundleError, match="stable_key"):
        load_bundle(bundle, other, POLICY)


def test_load_rejects_prompt_version_mismatch(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    other = GenerationRequest(**{**REQUEST.__dict__, "prompt_version": "2.0.0"})
    with pytest.raises(ArticleValidationError) as exc:
        load_bundle(bundle, other, POLICY)
    assert exc.value.fields == ("prompt_version",)


def test_load_rejects_published_or_tampered_article(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    article = bundle / ARTICLE_FILE
    article.write_bytes(article.read_bytes().replace(b"draft: true", b"draft: false"))
    with pytest.raises(ArticleValidationError) as exc:
        load_bundle(bundle, REQUEST, POLICY)
    assert "draft" in exc.value.fields


def test_load_rejects_non_designated_model(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    article = bundle / ARTICLE_FILE
    article.write_bytes(article.read_bytes().replace(MODEL.encode(), b"other/model"))
    with pytest.raises(ComplianceError):
        load_bundle(bundle, REQUEST, POLICY)


def test_load_rejects_non_canonical_bytes(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    article = bundle / ARTICLE_FILE
    original = article.read_bytes()
    assert b'title: "Static sites"' in original
    article.write_bytes(original.replace(b'title: "Static sites"', b"title: 'Static sites'"))
    with pytest.raises(DraftBundleError, match="canonical"):
        load_bundle(bundle, REQUEST, POLICY)

    article.write_bytes(original + b"\n")  # body no longer in normalised form
    with pytest.raises(DraftBundleError, match="normalised"):
        load_bundle(bundle, REQUEST, POLICY)


def test_load_rejects_crlf_and_bad_manifest(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    article = bundle / ARTICLE_FILE
    original = article.read_bytes()
    article.write_bytes(original.replace(b"\n", b"\r\n"))
    with pytest.raises(DraftBundleError, match="LF"):
        load_bundle(bundle, REQUEST, POLICY)

    article.write_bytes(original)
    (bundle / MANIFEST_FILE).write_text(json.dumps({"format": 1, "stable_key": "x"}))
    with pytest.raises(DraftBundleError, match="stable_key"):
        load_bundle(bundle, REQUEST, POLICY)


# --- apply ------------------------------------------------------------------


def test_apply_creates_then_keeps_identical_draft(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    verified = load_bundle(_bundle(tmp_path), REQUEST, POLICY)

    first = apply_draft(verified, repo, branch=BRANCH, default_branch="main")
    written = repo / first.target.path
    assert first.action is ChangeAction.CREATE
    assert first.target.path == draft_path(KEY, "static-sites")
    assert written.read_bytes() == verified.content

    second = apply_draft(verified, repo, branch=BRANCH, default_branch="main")
    assert second.action is ChangeAction.UNCHANGED
    assert not second.requires_commit
    assert sorted(p.name for p in (repo / CONTENT_ROOT).iterdir()) == [written.name]


def test_apply_reuses_existing_file_when_slug_changes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    old = load_bundle(write_bundle(tmp_path / "a", _draft("static-sites"), KEY), REQUEST, POLICY)
    apply_draft(old, repo, branch=BRANCH, default_branch="main")

    new = load_bundle(write_bundle(tmp_path / "b", _draft("static-hosting"), KEY), REQUEST, POLICY)
    change = apply_draft(new, repo, branch=BRANCH, default_branch="main")

    assert change.action is ChangeAction.UPDATE
    assert change.target.path == draft_path(KEY, "static-sites")
    files = list((repo / CONTENT_ROOT).iterdir())
    assert len(files) == 1 and files[0].read_bytes() == new.content


@pytest.mark.parametrize(
    ("branch", "default_branch"),
    [("draft/" + "0" * 64, "main"), (BRANCH, BRANCH), (BRANCH, "")],
)
def test_apply_refuses_wrong_or_default_branch(tmp_path: Path, branch: str, default_branch: str) -> None:
    repo = tmp_path / "repo"
    verified = load_bundle(_bundle(tmp_path), REQUEST, POLICY)
    with pytest.raises(DraftBundleError):
        apply_draft(verified, repo, branch=branch, default_branch=default_branch)
    assert not repo.exists()


# --- PR instructions ----------------------------------------------------------


def test_pr_instructions_give_compare_url_and_review_items(tmp_path: Path) -> None:
    verified = load_bundle(_bundle(tmp_path), REQUEST, POLICY)
    change = apply_draft(verified, tmp_path / "repo", branch=BRANCH, default_branch="main")

    text = pr_instructions(
        change, server_url="https://github.com", repository="owner/blog", default_branch="main"
    )

    assert f"https://github.com/owner/blog/compare/main...{BRANCH}?expand=1" in text
    assert change.target.path in text
    for item, label in REVIEW_ITEM_LABELS.items():
        assert f"{label}（`{item}`）" in text
    assert "draft: false" in text
    assert "Static sites" not in text  # article text is not echoed


@pytest.mark.parametrize(
    "kwargs",
    [
        {"server_url": "http://github.com"},
        {"repository": "owner/blog;rm"},
        {"default_branch": ""},
    ],
)
def test_pr_instructions_reject_unsafe_settings(tmp_path: Path, kwargs: dict[str, str]) -> None:
    verified = load_bundle(_bundle(tmp_path), REQUEST, POLICY)
    change = apply_draft(verified, tmp_path / "repo", branch=BRANCH, default_branch="main")
    options = {"server_url": "https://github.com", "repository": "owner/blog", "default_branch": "main"}
    options.update(kwargs)
    with pytest.raises(DraftBundleError):
        pr_instructions(change, **options)


# --- CLI ------------------------------------------------------------------------


def test_cli_generate_without_gateway_config_fails_before_any_bundle(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prompts = POLICY_PATH.parents[1] / "prompts"
    code = cli.main(
        [
            "generate", "--bundle-dir", str(tmp_path / "bundle"),
            "--policy", str(POLICY_PATH), "--prompts-dir", str(prompts),
        ],
        env=ENV,
    )
    assert code == cli.EXIT_FAILED
    assert "MODEL_GATEWAY_API_KEY" in capsys.readouterr().err
    assert not (tmp_path / "bundle").exists()


def test_cli_verify_and_apply_write_outputs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = _bundle(tmp_path)
    output = tmp_path / "github_output"
    instructions = tmp_path / "instructions.md"
    common = ["--bundle-dir", str(bundle), "--policy", str(POLICY_PATH), "--github-output", str(output)]

    assert cli.main(["verify-bundle", *common], env=ENV) == cli.EXIT_OK
    assert cli.main(
        [
            "apply-draft", *common,
            "--repo", str(tmp_path / "repo"),
            "--branch", BRANCH,
            "--default-branch", "main",
            "--server-url", "https://github.com",
            "--repository", "owner/blog",
            "--instructions-file", str(instructions),
        ],
        env=ENV,
    ) == cli.EXIT_OK

    lines = output.read_text(encoding="utf-8").splitlines()
    assert lines == [
        f"branch={BRANCH}",
        f"stable_key={KEY}",
        "action=create",
        f"path={draft_path(KEY, 'static-sites')}",
        "requires_commit=true",
    ]
    assert "compare/main..." in instructions.read_text(encoding="utf-8")


def test_cli_reports_invalid_inputs_without_values(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = _bundle(tmp_path)
    env = {**ENV, "GEN_TOPIC": "x" * 161, "GEN_PROMPT_NAME": ""}
    code = cli.main(["verify-bundle", "--bundle-dir", str(bundle), "--policy", str(POLICY_PATH)], env=env)
    err = capsys.readouterr().err
    assert code == cli.EXIT_FAILED
    assert "topic" in err and "prompt_name" in err
    assert "x" * 161 not in err
