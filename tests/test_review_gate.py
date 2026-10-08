"""Unit tests for the read-only Human_Editorial_Gate check (Requirements 5.7–5.10, 7.3–7.6, 9.2, 9.5–9.7)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from content_pipeline.article import render_content_file
from content_pipeline.compliance import REQUIRED_REVIEW_ITEMS, load_policy
from content_pipeline.review_gate import (
    ArticleChange,
    Revision,
    check_review_records,
    collect_article_changes,
    collect_asset_changes,
    evaluate_review_gate,
    is_automation_author,
    main,
    render_review_checklist,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = REPO_ROOT / ".github" / "pull_request_template.md"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "review-gate.yml"
PATH = "src/content/articles/example-0123456789ab.md"
BOT = ("github-actions[bot]", "41898282+github-actions[bot]@users.noreply.github.com")
EDITOR = ("Editor", "editor@example.com")

FILLED_BODY = """## 人工审阅记录
- [x] 事实与来源 `facts_and_sources`：核对了两处数据与来源链接
- [x] 读者价值 `reader_value`：回答了目标读者的核心问题
- [x] 语气 `tone`：语气平实，无夸大
- [X] 链接 `links`：全部外链可访问且为 HTTPS
- [x] 标题 `title`：标题与正文一致
"""


def _article(draft: bool) -> str:
    return render_content_file(
        {
            "title": "示例",
            "description": "描述",
            "pubDate": "2025-01-01T00:00:00Z",
            "tags": ["a"],
            "slug": "example",
            "draft": draft,
            "ai_assisted": True,
            "model": "vendor/model-a",
            "prompt_version": "1.0.0",
            "sources": [],
        },
        "# 标题\n\n正文。\n",
    )


def _rev(commit: str, author: tuple[str, str], text: str | None) -> Revision:
    return Revision(commit, author[0], author[1], text)


def _generated_then_flipped(flipper=EDITOR) -> ArticleChange:
    return ArticleChange(
        path=PATH,
        base_text=None,
        revisions=(_rev("a" * 40, BOT, _article(True)), _rev("b" * 40, flipper, _article(False))),
        head_text=_article(False),
    )


def _fields(result) -> list[str]:
    return [issue.field for issue in result.issues]


# --- review records ----------------------------------------------------------


def test_filled_records_pass():
    assert check_review_records(FILLED_BODY) == []


def test_template_checklist_matches_policy_items_and_is_unfilled():
    template = TEMPLATE.read_text(encoding="utf-8")
    assert render_review_checklist() in template
    assert load_policy(REPO_ROOT / "docs" / "compliance.md").review_items == REQUIRED_REVIEW_ITEMS
    issues = check_review_records(template)
    # Every item is present exactly once but neither checked nor recorded.
    assert {i.field for i in issues} == {f"review.{k}" for k in REQUIRED_REVIEW_ITEMS}
    assert all("missing" not in i.reason and "once" not in i.reason for i in issues)


@pytest.mark.parametrize("key", REQUIRED_REVIEW_ITEMS)
def test_each_item_is_required(key):
    body = "\n".join(line for line in FILLED_BODY.splitlines() if f"`{key}`" not in line)
    assert [i.field for i in check_review_records(body)] == [f"review.{key}"]


@pytest.mark.parametrize(
    "replacement",
    ["- [ ] 标题 `title`：标题与正文一致", "- [x] 标题 `title`：", "- [x] 标题 `title`： TODO "],
)
def test_unchecked_or_empty_record_fails(replacement):
    body = FILLED_BODY.replace("- [x] 标题 `title`：标题与正文一致", replacement)
    assert [i.field for i in check_review_records(body)] == ["review.title"]


def test_duplicate_and_commented_records_do_not_count():
    duplicated = FILLED_BODY + "- [x] 语气 `tone`：再次记录\n"
    assert [i.field for i in check_review_records(duplicated)] == ["review.tone"]
    commented = FILLED_BODY.replace(
        "- [x] 语气 `tone`：语气平实，无夸大", "<!-- - [x] 语气 `tone`：语气平实 -->"
    )
    assert [i.field for i in check_review_records(commented)] == ["review.tone"]
    assert len(check_review_records(None)) == len(REQUIRED_REVIEW_ITEMS)


# --- draft transition ----------------------------------------------------------


def test_gate_not_applicable_without_article_changes():
    result = evaluate_review_gate("", [])
    assert not result.applicable and result.passed


def test_human_flip_with_records_passes():
    result = evaluate_review_gate(FILLED_BODY, [_generated_then_flipped()])
    assert result.applicable and result.passed


def test_records_required_even_when_draft_flipped():
    result = evaluate_review_gate("", [_generated_then_flipped()])
    assert _fields(result) == [f"review.{k}" for k in REQUIRED_REVIEW_ITEMS]


def test_still_draft_blocks_merge():
    change = ArticleChange(PATH, None, (_rev("a" * 40, BOT, _article(True)),), _article(True))
    assert _fields(evaluate_review_gate(FILLED_BODY, [change])) == [f"{PATH}:draft"]


def test_flip_by_automation_fails():
    result = evaluate_review_gate(FILLED_BODY, [_generated_then_flipped(flipper=BOT)])
    assert _fields(result) == [f"{PATH}:draft"]
    change = _generated_then_flipped(flipper=("pipeline", "pipeline@example.com"))
    assert _fields(evaluate_review_gate(FILLED_BODY, [change], automation_authors=["pipeline"])) == [
        f"{PATH}:draft"
    ]


def test_new_article_without_draft_stage_fails():
    change = ArticleChange(PATH, None, (_rev("a" * 40, EDITOR, _article(False)),), _article(False))
    assert _fields(evaluate_review_gate(FILLED_BODY, [change])) == [f"{PATH}:draft"]


def test_edit_of_published_article_needs_records_only():
    change = ArticleChange(
        PATH, _article(False), (_rev("a" * 40, EDITOR, _article(False)),), _article(False)
    )
    assert evaluate_review_gate(FILLED_BODY, [change]).passed
    assert not evaluate_review_gate("", [change]).passed


def test_invalid_or_missing_draft_value_fails():
    bad = _article(False).replace("draft: false", 'draft: "false"')
    change = ArticleChange(PATH, None, (_rev("a" * 40, BOT, _article(True)), _rev("b" * 40, EDITOR, bad)), bad)
    assert _fields(evaluate_review_gate(FILLED_BODY, [change])) == [f"{PATH}:draft"]
    no_fm = "# no front-matter\n"
    change = ArticleChange(PATH, None, (_rev("a" * 40, EDITOR, no_fm),), no_fm)
    assert _fields(evaluate_review_gate(FILLED_BODY, [change])) == [f"{PATH}:front-matter"]


def test_automation_author_detection():
    assert is_automation_author(*BOT)
    assert is_automation_author("x", "dependabot[bot]@users.noreply.github.com")
    assert not is_automation_author(*EDITOR)
    assert is_automation_author("x", "Bot@Example.com", ["bot@example.com"])


# --- read-only workflow configuration ----------------------------------------


def test_workflow_is_read_only_and_never_approves_or_merges():
    text = WORKFLOW.read_text(encoding="utf-8")
    config = yaml.safe_load(text)
    triggers = config.get("on", config.get(True))
    assert set(triggers) == {"pull_request"}
    assert config["permissions"] == {"contents": "read", "pull-requests": "read"}
    for job in config["jobs"].values():
        assert "permissions" not in job
        for step in job["steps"]:
            assert "${{" not in step.get("run", "")  # untrusted values only via env
    lowered = text.lower()
    for forbidden in ("gh pr merge", "gh pr review", "--approve", "git push", "secrets.", "deploy"):
        assert forbidden not in lowered


# --- git adapter + CLI against a temporary repository -------------------------


def _git(repo: Path, *args: str, author: tuple[str, str] = EDITOR) -> str:
    return subprocess.run(
        ["git", "-c", f"user.name={author[0]}", "-c", f"user.email={author[1]}",
         "-c", "commit.gpgsign=false", *args],
        cwd=repo, check=True, capture_output=True, text=True,
    ).stdout.strip()


def _write(repo: Path, rel: str, text: str) -> None:
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(text.encode("utf-8"))


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_collect_changes_and_cli_on_real_history(tmp_path: Path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _write(repo, "docs/compliance.md", (REPO_ROOT / "docs" / "compliance.md").read_text(encoding="utf-8"))
    _write(repo, "src/content/articles/.gitkeep", "")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")

    _git(repo, "checkout", "-q", "-b", "draft/x")
    _write(repo, PATH, _article(True))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "draft", author=BOT)
    draft_head = _git(repo, "rev-parse", "HEAD")

    body_file = tmp_path / "body.md"
    body_file.write_text(FILLED_BODY, encoding="utf-8")
    args = ["--repo", str(repo), "--base", base, "--body-file", str(body_file)]
    assert main([*args, "--head", draft_head]) == 1  # still draft: true

    _write(repo, PATH, _article(False))
    _git(repo, "commit", "-q", "-am", "publish")
    head = _git(repo, "rev-parse", "HEAD")

    changes = collect_article_changes(repo, base, head)
    assert [c.path for c in changes] == [PATH]
    assert [r.author_name for r in changes[0].revisions] == [BOT[0], EDITOR[0]]
    assert changes[0].base_text is None

    assert main([*args, "--head", head]) == 0
    assert main([*args, "--head", base]) == 0  # no article changes: not applicable
    assert "not applicable" in capsys.readouterr().out


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_assets_gitkeep_placeholder_is_not_a_work_asset(tmp_path: Path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _write(repo, "docs/compliance.md", (REPO_ROOT / "docs" / "compliance.md").read_text(encoding="utf-8"))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")

    _write(repo, "src/assets/works/.gitkeep", "")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "placeholder")
    placeholder_head = _git(repo, "rev-parse", "HEAD")

    assert collect_asset_changes(repo, base, placeholder_head) == []
    args = ["--repo", str(repo), "--base", base, "--body-env", "EMPTY_PR_BODY"]
    assert main([*args, "--head", placeholder_head]) == 0  # no media record needed
    assert "not applicable" in capsys.readouterr().out

    _write(repo, "src/assets/works/demo/notes.md", "笔记")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "notes")
    head = _git(repo, "rev-parse", "HEAD")

    assert [a.path for a in collect_asset_changes(repo, base, head)] == ["src/assets/works/demo/notes.md"]
    assert main([*args, "--head", head]) == 1  # a real asset still needs the media record
