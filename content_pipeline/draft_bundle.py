"""Draft bundle hand-off and review-branch change (Requirements 5.2–5.8, 7.1).

The Generation_Workflow (``.github/workflows/generate-draft.yml``) runs two
jobs so the model credential and the repository write token never share a job:

1. ``generate`` (``contents: read``, holds only the model gateway secret)
   validates inputs, calls the gateway, assembles and validates the draft and
   writes a *bundle* directory with :func:`write_bundle`.
2. ``draft-branch`` (``contents: write``, holds no model secret) re-validates
   the bundle with :func:`load_bundle`, applies it to a work tree checked out
   at ``draft/<stable-key>`` with :func:`apply_draft`, commits and pushes that
   branch only, and prints :func:`pr_instructions`.

Bundle layout::

    manifest.json   {"format": 1, "stable_key": "<64 lowercase hex>"}
    article.md      canonical Content_File bytes (UTF-8 without BOM, LF)

``load_bundle`` trusts nothing in the bundle: it re-runs the full
Article_Schema, requires ``draft: true`` / ``ai_assisted: true``, the
designated model from the Compliance_Checklist and the requested
Prompt_Version, recomputes the stable key from the workflow inputs, and
requires the file bytes to be exactly the canonical rendering. A bundle that
fails any check produces no Git change.

No Git command, network access or model call happens in this module.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

import yaml

from .article import (
    DEFAULT_MAX_BODY_CHARS,
    DraftArticle,
    normalize_body,
    render_content_file,
    validate_article,
    validate_front_matter,
    validate_generated_flags,
    validate_markdown_body,
)
from .compliance import REVIEW_ITEM_LABELS, CompliancePolicy
from .draft_identity import (
    DraftChange,
    draft_branch,
    draft_path,
    is_stable_key,
    stable_key_for,
)
from .errors import ArticleValidationError, DraftBundleError, FieldIssue
from .git_change import WorkTreeBackend, apply_verified_draft
from .request import GenerationRequest

MANIFEST_FILE = "manifest.json"
ARTICLE_FILE = "article.md"
BUNDLE_FORMAT = 1
# Generous upper bound so a corrupted bundle cannot exhaust memory.
MAX_ARTICLE_BYTES = 4 * DEFAULT_MAX_BODY_CHARS + 64 * 1024
MAX_MANIFEST_BYTES = 4096

_CONTENT_FILE = re.compile(rb"---\n(.*?\n)---\n(.*)", re.DOTALL)
_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")


@dataclass(frozen=True)
class VerifiedDraft:
    """A bundle that passed every check; safe to apply to the draft branch."""

    stable_key: str
    branch: str
    slug: str
    front_matter: Mapping[str, Any]
    body: str
    content: bytes


# --------------------------------------------------------------------------
# Writing (generate job)
# --------------------------------------------------------------------------


def write_bundle(bundle_dir: Path | str, draft: DraftArticle, stable_key: str) -> Path:
    """Write a validated draft and its stable key to ``bundle_dir``.

    Only called after Article_Schema validation succeeded; validates again so
    a failing draft never leaves a bundle behind.
    """
    if not is_stable_key(stable_key):
        raise DraftBundleError("stable key must be 64 lowercase hexadecimal characters")
    issues = [
        *validate_article(draft.path, draft.front_matter, draft.body),
        *validate_generated_flags(draft.front_matter),
    ]
    if issues:
        raise ArticleValidationError(issues)
    if draft.path != draft_path(stable_key, draft.front_matter["slug"]):
        raise DraftBundleError("draft path does not match the stable key and slug")
    data = draft.to_bytes()
    manifest = json.dumps({"format": BUNDLE_FORMAT, "stable_key": stable_key}) + "\n"

    directory = Path(bundle_dir)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / ARTICLE_FILE).write_bytes(data)
    (directory / MANIFEST_FILE).write_bytes(manifest.encode("utf-8"))
    return directory


# --------------------------------------------------------------------------
# Verification (draft-branch job)
# --------------------------------------------------------------------------


def _read_limited(path: Path, limit: int, name: str) -> bytes:
    try:
        with path.open("rb") as handle:
            data = handle.read(limit + 1)
    except FileNotFoundError:
        raise DraftBundleError(f"draft bundle is missing {name}") from None
    if len(data) > limit:
        raise DraftBundleError(f"{name} exceeds {limit} bytes")
    return data


def _read_manifest(directory: Path) -> str:
    raw = _read_limited(directory / MANIFEST_FILE, MAX_MANIFEST_BYTES, MANIFEST_FILE)
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise DraftBundleError(f"{MANIFEST_FILE} is not valid UTF-8 JSON") from None
    if not isinstance(manifest, dict) or manifest.get("format") != BUNDLE_FORMAT:
        raise DraftBundleError(f"{MANIFEST_FILE} has an unsupported format")
    key = manifest.get("stable_key")
    if not is_stable_key(key):
        raise DraftBundleError(f"{MANIFEST_FILE}: stable_key must be 64 lowercase hexadecimal characters")
    return key


def parse_content_file(data: bytes) -> tuple[Any, str]:
    """Split canonical Content_File bytes into front-matter data and body."""
    if data.startswith(b"\xef\xbb\xbf"):
        raise DraftBundleError(f"{ARTICLE_FILE} must be UTF-8 without BOM")
    if b"\r" in data:
        raise DraftBundleError(f"{ARTICLE_FILE} must use LF line endings only")
    match = _CONTENT_FILE.fullmatch(data)
    if match is None:
        raise DraftBundleError(f"{ARTICLE_FILE} must start with '---' delimited front-matter")
    try:
        yaml_text = match.group(1).decode("utf-8")
        body = match.group(2).decode("utf-8")
    except UnicodeDecodeError:
        raise DraftBundleError(f"{ARTICLE_FILE} is not valid UTF-8") from None
    try:
        front_matter = yaml.safe_load(yaml_text)
    except yaml.YAMLError:
        # Parser messages may quote content; report the file only.
        raise DraftBundleError(f"{ARTICLE_FILE} front-matter is not valid YAML") from None
    return front_matter, body


def load_bundle(
    bundle_dir: Path | str,
    request: GenerationRequest,
    policy: CompliancePolicy,
    *,
    max_body_chars: int = DEFAULT_MAX_BODY_CHARS,
) -> VerifiedDraft:
    """Re-validate a bundle against the workflow inputs and the checklist.

    Raises:
        DraftBundleError: malformed bundle, key mismatch or non-canonical bytes.
        ArticleValidationError: Article_Schema or draft-flag violations.
        ComplianceError: the article's model is not the designated model.
    """
    directory = Path(bundle_dir)
    key = _read_manifest(directory)
    data = _read_limited(directory / ARTICLE_FILE, MAX_ARTICLE_BYTES, ARTICLE_FILE)
    front_matter, body = parse_content_file(data)

    issues = [
        *validate_front_matter(front_matter),
        *validate_markdown_body(body, max_body_chars),
        *validate_generated_flags(front_matter),
    ]
    if issues:
        raise ArticleValidationError(issues)
    if front_matter["prompt_version"] != request.prompt_version:
        raise ArticleValidationError(
            [FieldIssue("prompt_version", "must equal the requested prompt_version")]
        )
    policy.require_designated_model(front_matter["model"])

    if stable_key_for(request, front_matter["model"]) != key:
        raise DraftBundleError("stable_key does not match the workflow inputs and model")
    if normalize_body(body) != body:
        raise DraftBundleError(f"{ARTICLE_FILE} body is not in normalised Markdown_Body form")
    if render_content_file(front_matter, body).encode("utf-8") != data:
        raise DraftBundleError(f"{ARTICLE_FILE} is not in canonical Content_File form")

    return VerifiedDraft(
        stable_key=key,
        branch=draft_branch(key),
        slug=front_matter["slug"],
        front_matter=front_matter,
        body=body,
        content=data,
    )


# --------------------------------------------------------------------------
# Applying to the draft branch work tree
# --------------------------------------------------------------------------


def apply_draft(
    draft: VerifiedDraft,
    repo_root: Path | str,
    *,
    branch: str,
    default_branch: str,
) -> DraftChange:
    """Create, update or keep the draft's Content_File in the work tree.

    ``repo_root`` must already be checked out at ``draft.branch`` (existing
    draft branch, or a new branch from the Default_Branch). An existing file
    carrying the key's 12-character suffix is reused so reruns never add a
    second file for the same draft (Requirement 5.4); identical bytes are left
    untouched so no commit is created (Requirement 5.5).
    """
    return apply_verified_draft(
        draft, WorkTreeBackend(repo_root), branch=branch, default_branch=default_branch
    )


# --------------------------------------------------------------------------
# Pull Request creation instructions
# --------------------------------------------------------------------------


def pr_instructions(
    change: DraftChange,
    *,
    server_url: str,
    repository: str,
    default_branch: str,
) -> str:
    """Markdown with a compare URL for opening the review Pull Request.

    Does not depend on any GitHub PR API (Requirement 5.11). Contains only
    the branch, path and non-secret repository identifiers; article text is
    not included.
    """
    parts = urlsplit(server_url)
    if parts.scheme != "https" or not parts.hostname or parts.path not in ("", "/"):
        raise DraftBundleError("server URL must be an absolute HTTPS origin")
    if _REPOSITORY.fullmatch(repository) is None:
        raise DraftBundleError("repository must be <owner>/<name>")
    if not default_branch or default_branch == change.target.branch:
        raise DraftBundleError("refusing to target the Default_Branch")

    base = quote(default_branch, safe="/")
    compare = (
        f"{server_url.rstrip('/')}/{repository}/compare/{base}...{change.target.branch}?expand=1"
    )
    review = "\n".join(
        f"   - [ ] {label}（`{item}`）" for item, label in REVIEW_ITEM_LABELS.items()
    )
    status = {
        "create": "已创建草稿文件",
        "update": "已更新草稿文件",
        "unchanged": "草稿文件内容未变化，未创建新提交",
    }[change.action.value]
    return (
        "## 草稿已就绪，等待人工审阅\n\n"
        f"- 状态：{status}\n"
        f"- 草稿分支：`{change.target.branch}`\n"
        f"- 文章文件：`{change.target.path}`\n\n"
        "### 创建 Pull Request\n\n"
        f"1. 打开 {compare}\n"
        f"   （若该分支已有打开的 Pull Request，直接在其中审阅。）\n"
        f"2. 目标分支选择 `{default_branch}`，来源分支为 `{change.target.branch}`。\n"
        "3. 在 Pull Request 中逐项审阅并保留记录：\n"
        f"{review}\n"
        "4. 五项审阅完成后，由编辑人员手动将 `draft: true` 改为 `draft: false`，"
        "再由人工合并。\n\n"
        "本工作流不会批准、合并或发布任何内容。\n"
    )


__all__ = [
    "ARTICLE_FILE",
    "MANIFEST_FILE",
    "VerifiedDraft",
    "apply_draft",
    "load_bundle",
    "parse_content_file",
    "pr_instructions",
    "write_bundle",
]
