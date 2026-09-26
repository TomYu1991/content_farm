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
``[x]`` with a non-empty record, each exactly once. PRs that touch no
Content_File are not subject to the gate.

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
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .article import CONTENT_ROOT, validate_front_matter
from .compliance import DEFAULT_POLICY_PATH, REQUIRED_REVIEW_ITEMS, REVIEW_ITEM_LABELS, load_policy
from .errors import FieldIssue, PipelineError

_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_REVIEW_LINE = re.compile(
    r"^[ \t]*[-*+][ \t]+\[(?P<mark>[ xX])\][ \t]+[^`\n]*?`(?P<key>[a-z_]+)`[ \t]*[:：](?P<record>[^\n]*)$",
    re.MULTILINE,
)
# Values that mean "not filled in yet" (compared case-insensitively after strip).
_PLACEHOLDER_RECORDS = frozenset({"", "todo", "tbd", "待填写", "待定", "-", "...", "…"})
_ARTICLE_FILE = re.compile(re.escape(CONTENT_ROOT) + r"/[^/]+\.md")


# --------------------------------------------------------------------------
# PR description: five review records
# --------------------------------------------------------------------------


def render_review_checklist(review_items: Sequence[str] = REQUIRED_REVIEW_ITEMS) -> str:
    """Unfilled checklist lines in the format parsed by :func:`check_review_records`."""
    return "\n".join(
        f"- [ ] {REVIEW_ITEM_LABELS.get(key, key)} `{key}`：" for key in review_items
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


def check_article_change(
    change: ArticleChange, automation_authors: Iterable[str] = ()
) -> list[FieldIssue]:
    """Gate rules for one added/modified Content_File (see module docstring)."""
    path = change.path
    meta = parse_front_matter(change.head_text)
    if meta is _MISSING:
        return [FieldIssue(f"{path}:front-matter", "missing or invalid YAML front-matter")]
    schema_issues = validate_front_matter(meta)
    if schema_issues:
        return [FieldIssue(f"{path}:{i.field}", i.reason) for i in schema_issues]
    if meta["draft"] is not False:
        return [
            FieldIssue(
                f"{path}:draft",
                "is still true; after the five-item review an editor must set draft: false",
            )
        ]

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

    @property
    def applicable(self) -> bool:
        return bool(self.article_paths)

    @property
    def passed(self) -> bool:
        return not self.issues


def evaluate_review_gate(
    body: str | None,
    changes: Sequence[ArticleChange],
    *,
    review_items: Sequence[str] = REQUIRED_REVIEW_ITEMS,
    automation_authors: Iterable[str] = (),
) -> GateResult:
    """Pure gate decision for one PR description and its Content_File changes."""
    authors = tuple(automation_authors)
    paths = tuple(sorted(c.path for c in changes))
    if not changes:
        return GateResult(article_paths=())
    issues = check_review_records(body, review_items)
    for change in sorted(changes, key=lambda c: c.path):
        issues.extend(check_article_change(change, authors))
    return GateResult(article_paths=paths, issues=tuple(issues))


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


def collect_article_changes(repo: Path | str, base: str, head: str) -> list[ArticleChange]:
    """Added/modified Content_Files between ``merge-base(base, head)`` and ``head``.

    Uses only read-only git commands (merge-base, diff, log, show).
    """
    repo = Path(repo)
    merge_base = _git(repo, "merge-base", base, head).decode().strip()
    diff = _git(
        repo, "diff", "--name-status", "-z", "--no-renames", merge_base, head, "--", CONTENT_ROOT
    ).decode("utf-8")
    parts = [p for p in diff.split("\0") if p]
    changes: list[ArticleChange] = []
    for status, path in zip(parts[0::2], parts[1::2]):
        if status[0] not in "AM" or not _ARTICLE_FILE.fullmatch(path):
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
    except (PipelineError, OSError) as exc:
        print(f"review gate error: {exc}", file=sys.stderr)
        return 2

    result = evaluate_review_gate(
        body,
        changes,
        review_items=policy.review_items,
        automation_authors=args.automation_author,
    )
    if not result.applicable:
        print("review gate: no Content_File changes; gate not applicable")
        return 0
    print("review gate: Content_Files in this PR: " + ", ".join(result.article_paths))
    if result.passed:
        print("review gate: passed (five review records present, draft set to false by an editor)")
        return 0
    for issue in result.issues:
        print(f"review gate: {issue.describe()}", file=sys.stderr)
    print("review gate: failed; this check never approves, merges or publishes", file=sys.stderr)
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
