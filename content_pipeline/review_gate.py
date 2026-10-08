"""Read-only Human_Editorial_Gate check for article Pull Requests.

Requirements 5.7–5.10, 7.3–7.6, 9.2 and 9.5–9.7. This module only *reads*
the PR description and Git history and reports whether the gate is satisfied.
It never approves, merges, pushes or publishes anything; the only outcome is a
pass/fail status that maintainers can make a required status check on the
Default_Branch.

The gate passes for a PR when every added or modified Content_File under
``src/content/articles/`` satisfies all of:

1. the head version passes the Article_Schema front-matter rules;
2. the head version has ``draft: false`` (a draft that is still ``true``
   blocks the merge until an editor flips it after review);
3. unless the base version was already published (``draft: false``), the
   file history in the PR shows ``draft: true`` followed by a commit that set
   ``draft: false``, and that commit was not authored by automation
   (``*[bot]`` identities or configured automation authors);

and the PR description records all five review items from the
Compliance_Checklist (事实与来源、读者价值、语气、链接、标题), each checked
``[x]`` with a non-empty record, each exactly once.

Portfolio works (``src/content/works/<slug>.md``) follow the same rules with
Work_Schema instead of Article_Schema; a published work must reference only
photos that exist in the PR head. PRs that add or change a work or any file
under ``src/assets/works/`` additionally need the ``media`` record
(图片与视频), and every added/modified asset must pass
:func:`media_check.check_asset` (names, size, no EXIF/GPS/XMP metadata).
Directory placeholders (``src/assets/works/.gitkeep``) are not assets.
PRs that touch none of these paths are not subject to the gate.

Git author identities are self-declared, so check 3 is a guard against the
generation workflow flipping ``draft`` itself; the binding control remains
branch protection that requires a human approval and this status check.

Issues name fields, review item keys and file paths only; PR text and file
contents are never echoed.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .article import CONTENT_ROOT, validate_front_matter
from .compliance import (
    ALL_REVIEW_ITEM_LABELS,
    DEFAULT_POLICY_PATH,
    MEDIA_REVIEW_ITEMS,
    REQUIRED_REVIEW_ITEMS,
    load_policy,
)
from .errors import FieldIssue, PipelineError
from .media_check import PLACEHOLDER_FILES, check_asset
from .work import WORK_ASSETS_ROOT, WORKS_ROOT, validate_work

_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_REVIEW_LINE = re.compile(
    r"^[ \t]*[-*+][ \t]+\[(?P<mark>[ xX])\][ \t]+[^`\n]*?`(?P<key>[a-z_]+)`[ \t]*[:：](?P<record>[^\n]*)$",
    re.MULTILINE,
)
# Values that mean "not filled in yet" (compared case-insensitively after strip).
_PLACEHOLDER_RECORDS = frozenset({"", "todo", "tbd", "待填写", "待定", "-", "...", "…"})
_ARTICLE_FILE = re.compile(re.escape(CONTENT_ROOT) + r"/[^/]+\.md")
_WORK_FILE = re.compile(re.escape(WORKS_ROOT) + r"/[^/]+\.md")
# prompts/work-draft.md asks the model to mark unclear facts like "[待确认：缝份宽度]".
UNRESOLVED_MARKER = "[待确认"


def is_work_path(path: str) -> bool:
    return _WORK_FILE.fullmatch(path) is not None


# --------------------------------------------------------------------------
# PR description: five review records
# --------------------------------------------------------------------------


def render_review_checklist(review_items: Sequence[str] = REQUIRED_REVIEW_ITEMS) -> str:
    """Unfilled checklist lines in the format parsed by :func:`check_review_records`."""
    return "\n".join(
        f"- [ ] {ALL_REVIEW_ITEM_LABELS.get(key, key)} `{key}`：" for key in review_items
    ) + "\n"


def check_review_records(
    body: str | None, review_items: Sequence[str] = REQUIRED_REVIEW_ITEMS
) -> list[FieldIssue]:
    """Validate that each review item is recorded exactly once, checked and non-empty.

    HTML comments are ignored, so template instructions never count as records.
    """
    text = _HTML_COMMENT.sub("", (body or "").replace("\r\n", "\n").replace("\r", "\n"))
    found: dict[str, list[re.Match[str]]] = {}
    for match in _REVIEW_LINE.finditer(text):
        found.setdefault(match.group("key"), []).append(match)

    issues: list[FieldIssue] = []
    for key in review_items:
        name = f"review.{key}"
        matches = found.get(key, [])
        if not matches:
            issues.append(FieldIssue(name, "review record is missing"))
            continue
        if len(matches) > 1:
            issues.append(FieldIssue(name, "review record must appear exactly once"))
            continue
        match = matches[0]
        if match.group("mark") not in ("x", "X"):
            issues.append(FieldIssue(name, "review item must be checked [x]"))
        if match.group("record").strip().lower() in _PLACEHOLDER_RECORDS:
            issues.append(FieldIssue(name, "review record text must not be empty"))
    return issues


# --------------------------------------------------------------------------
# Article changes: draft true -> false by a human
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Revision:
    """One commit in the PR that touched a Content_File (chronological order)."""

    commit: str
    author_name: str
    author_email: str
    text: str | None  # None when the file does not exist at this commit


@dataclass(frozen=True)
class ArticleChange:
    """An added or modified Content_File in the PR."""

    path: str
    base_text: str | None  # None when the file is new relative to the base
    revisions: tuple[Revision, ...]  # PR commits touching the file, oldest first
    head_text: str


_MISSING = object()


def parse_front_matter(text: str | None) -> Any:
    """Return the parsed front-matter mapping, or ``_MISSING`` if absent/invalid."""
    if text is None:
        return _MISSING
    lines = text.lstrip("\ufeff").replace("\r\n", "\n").split("\n")
    if not lines or lines[0] != "---":
        return _MISSING
    for index in range(1, len(lines)):
        if lines[index] == "---":
            try:
                return yaml.safe_load("\n".join(lines[1:index]))
            except yaml.YAMLError:
                return _MISSING
    return _MISSING


def _draft_value(text: str | None) -> Any:
    meta = parse_front_matter(text)
    if not isinstance(meta, Mapping):
        return _MISSING
    return meta.get("draft", _MISSING)


def is_automation_author(
    name: str, email: str, automation_authors: Iterable[str] = ()
) -> bool:
    """True for GitHub bot identities or explicitly configured automation authors."""
    configured = {a.strip().lower() for a in automation_authors if a.strip()}
    name_l, email_l = name.strip().lower(), email.strip().lower()
    return (
        name_l.endswith("[bot]")
        or "[bot]@" in email_l
        or name_l in configured
        or email_l in configured
    )


def _work_image_refs(meta: Mapping[str, Any]) -> list[tuple[str, str]]:
    refs = [("cover", meta["cover"])]
    refs.extend((f"gallery.{i}.src", item["src"]) for i, item in enumerate(meta.get("gallery", [])))
    return refs


def check_article_change(
    change: ArticleChange,
    automation_authors: Iterable[str] = (),
    asset_exists: Callable[[str], bool] | None = None,
) -> list[FieldIssue]:
    """Gate rules for one added/modified Content_File or work (see module docstring).

    ``asset_exists`` answers whether a repo-relative path exists in the PR
    head; when given, a published work must reference existing photos only.
    """
    path = change.path
    meta = parse_front_matter(change.head_text)
    if meta is _MISSING:
        return [FieldIssue(f"{path}:front-matter", "missing or invalid YAML front-matter")]
    work = is_work_path(path)
    if work:
        # Placeholder alt texts are fine while a work is a draft, never once published.
        draft = meta.get("draft") if isinstance(meta, Mapping) else None
        schema_issues = validate_work(path, meta, None, allow_placeholders=draft is True)
    else:
        schema_issues = validate_front_matter(meta)
    if schema_issues:
        return [FieldIssue(f"{path}:{i.field}", i.reason) for i in schema_issues]
    if meta["draft"] is not False:
        return [
            FieldIssue(
                f"{path}:draft",
                "is still true; after the review an editor must set draft: false",
            )
        ]
    if work and UNRESOLVED_MARKER in change.head_text:
        return [FieldIssue(f"{path}:body", f'still contains "{UNRESOLVED_MARKER}…]" notes for the maker')]
    if work and asset_exists is not None:
        missing = [
            FieldIssue(f"{path}:{field}", "image not found in the pull request head")
            for field, ref in _work_image_refs(meta)
            if not asset_exists(f"{WORK_ASSETS_ROOT}/{ref}")
        ]
        if missing:
            return missing

    if _draft_value(change.base_text) is False:
        return []  # edit of an already published article; no transition needed

    states: list[tuple[Revision | None, Any]] = []
    if change.base_text is not None:
        states.append((None, _draft_value(change.base_text)))
    states.extend((rev, _draft_value(rev.text)) for rev in change.revisions)

    last_true = max((i for i, (_, draft) in enumerate(states) if draft is True), default=None)
    if last_true is None or last_true + 1 >= len(states):
        return [
            FieldIssue(
                f"{path}:draft",
                "no draft: true -> false transition found in the pull request history",
            )
        ]
    flip = states[last_true + 1][0]
    assert flip is not None  # only the base state can be None, and it is always first
    if is_automation_author(flip.author_name, flip.author_email, automation_authors):
        return [
            FieldIssue(
                f"{path}:draft",
                f"draft: true -> false was committed by automation in {flip.commit[:12]}; "
                "an editor must make this change",
            )
        ]
    return []


@dataclass(frozen=True)
class GateResult:
    article_paths: tuple[str, ...]
    issues: tuple[FieldIssue, ...] = field(default=())
    asset_paths: tuple[str, ...] = field(default=())

    @property
    def applicable(self) -> bool:
        return bool(self.article_paths or self.asset_paths)

    @property
    def passed(self) -> bool:
        return not self.issues


@dataclass(frozen=True)
class AssetChange:
    """An added or modified file under ``src/assets/works/`` (head bytes)."""

    path: str
    data: bytes = field(repr=False)


def evaluate_review_gate(
    body: str | None,
    changes: Sequence[ArticleChange],
    *,
    review_items: Sequence[str] = REQUIRED_REVIEW_ITEMS,
    automation_authors: Iterable[str] = (),
    assets: Sequence[AssetChange] = (),
    asset_exists: Callable[[str], bool] | None = None,
) -> GateResult:
    """Pure gate decision for one PR description, its content and asset changes.

    The five review items are required when any article or work changes;
    ``media`` is required when any work or work asset changes.
    """
    authors = tuple(automation_authors)
    paths = tuple(sorted(c.path for c in changes))
    asset_paths = tuple(sorted(a.path for a in assets))
    if not changes and not assets:
        return GateResult(article_paths=())
    required: list[str] = list(review_items) if changes else []
    if assets or any(is_work_path(c.path) for c in changes):
        required.extend(k for k in MEDIA_REVIEW_ITEMS if k not in required)
    issues = check_review_records(body, required)
    for change in sorted(changes, key=lambda c: c.path):
        issues.extend(check_article_change(change, authors, asset_exists))
    for asset in sorted(assets, key=lambda a: a.path):
        issues.extend(check_asset(asset.path, asset.data))
    return GateResult(article_paths=paths, issues=tuple(issues), asset_paths=asset_paths)


# --------------------------------------------------------------------------
# Read-only Git adapter
# --------------------------------------------------------------------------


class GitReadError(PipelineError):
    """A read-only git command failed (no output echoed)."""


def _git(repo: Path, *args: str, check: bool = True) -> bytes | None:
    result = subprocess.run(
        ["git", "-c", "core.quotepath=off", *args],
        cwd=repo,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        if check:
            raise GitReadError(f"git {args[0]} failed with exit code {result.returncode}")
        return None
    return result.stdout


def _show(repo: Path, commit: str, path: str) -> str | None:
    data = _git(repo, "show", f"{commit}:{path}", check=False)
    return None if data is None else data.decode("utf-8", errors="replace")


def _merge_base(repo: Path, base: str, head: str) -> str:
    return _git(repo, "merge-base", base, head).decode().strip()


def _changed_paths(repo: Path, merge_base: str, head: str, *roots: str) -> list[str]:
    """Added or modified (not deleted) paths under ``roots``."""
    diff = _git(
        repo, "diff", "--name-status", "-z", "--no-renames", merge_base, head, "--", *roots
    ).decode("utf-8")
    parts = [p for p in diff.split("\0") if p]
    return [path for status, path in zip(parts[0::2], parts[1::2]) if status[0] in "AM"]


def collect_asset_changes(repo: Path | str, base: str, head: str) -> list[AssetChange]:
    """Added/modified files under ``src/assets/works/`` with their head bytes.

    Directory placeholders (``.gitkeep``) are skipped, so a PR that only adds
    them does not need the ``media`` record.
    """
    repo = Path(repo)
    merge_base = _merge_base(repo, base, head)
    assets = []
    for path in _changed_paths(repo, merge_base, head, WORK_ASSETS_ROOT):
        if path in PLACEHOLDER_FILES:
            continue
        data = _git(repo, "show", f"{head}:{path}", check=False)
        if data is not None:
            assets.append(AssetChange(path=path, data=data))
    return assets


def head_path_exists(repo: Path | str, head: str) -> Callable[[str], bool]:
    """Predicate: does repo-relative ``path`` exist as a file in ``head``?"""

    def exists(path: str) -> bool:
        kind = _git(Path(repo), "cat-file", "-t", f"{head}:{path}", check=False)
        return kind is not None and kind.strip() == b"blob"

    return exists


def collect_article_changes(repo: Path | str, base: str, head: str) -> list[ArticleChange]:
    """Added/modified articles and works between ``merge-base(base, head)`` and ``head``.

    Uses only read-only git commands (merge-base, diff, log, show).
    """
    repo = Path(repo)
    merge_base = _merge_base(repo, base, head)
    changes: list[ArticleChange] = []
    for path in _changed_paths(repo, merge_base, head, CONTENT_ROOT, WORKS_ROOT):
        if not (_ARTICLE_FILE.fullmatch(path) or _WORK_FILE.fullmatch(path)):
            continue
        log = _git(
            repo, "log", "--reverse", "--format=%H%x1f%an%x1f%ae", f"{merge_base}..{head}", "--", path
        ).decode("utf-8")
        revisions = []
        for line in log.splitlines():
            commit, name, email = line.split("\x1f")
            revisions.append(Revision(commit, name, email, _show(repo, commit, path)))
        head_text = _show(repo, head, path)
        if head_text is None:  # pragma: no cover - diff reported it as present
            continue
        changes.append(
            ArticleChange(
                path=path,
                base_text=_show(repo, merge_base, path),
                revisions=tuple(revisions),
                head_text=head_text,
            )
        )
    return changes


# --------------------------------------------------------------------------
# CLI (used by .github/workflows/review-gate.yml)
# --------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m content_pipeline.review_gate",
        description="Read-only Human_Editorial_Gate check for an article pull request.",
    )
    parser.add_argument("--base", required=True, help="base commit SHA of the pull request")
    parser.add_argument("--head", required=True, help="head commit SHA of the pull request")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--body-file", help="file containing the pull request description")
    source.add_argument("--body-env", help="environment variable holding the PR description")
    parser.add_argument("--repo", default=".", help="repository root (default: .)")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY_PATH), help="Compliance_Checklist path")
    parser.add_argument(
        "--automation-author",
        action="append",
        default=[],
        help="extra author name or email treated as automation (repeatable)",
    )
    args = parser.parse_args(argv)

    try:
        policy = load_policy(Path(args.repo) / args.policy, display_path=args.policy)
        if args.body_file:
            body = Path(args.body_file).read_text(encoding="utf-8")
        else:
            body = os.environ.get(args.body_env, "")
        changes = collect_article_changes(args.repo, args.base, args.head)
        assets = collect_asset_changes(args.repo, args.base, args.head)
        result = evaluate_review_gate(
            body,
            changes,
            review_items=policy.review_items,
            automation_authors=args.automation_author,
            assets=assets,
            asset_exists=head_path_exists(args.repo, args.head),
        )
    except (PipelineError, OSError) as exc:
        print(f"review gate error: {exc}", file=sys.stderr)
        return 2

    if not result.applicable:
        print("review gate: no Content_File or work asset changes; gate not applicable")
        return 0
    if result.article_paths:
        print("review gate: Content_Files in this PR: " + ", ".join(result.article_paths))
    if result.asset_paths:
        print("review gate: work assets in this PR: " + ", ".join(result.asset_paths))
    if result.passed:
        print("review gate: passed (review records present, draft set to false by an editor, assets clean)")
        return 0
    for issue in result.issues:
        print(f"review gate: {issue.describe()}", file=sys.stderr)
    print("review gate: failed; this check never approves, merges or publishes", file=sys.stderr)
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
