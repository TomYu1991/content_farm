"""Stable draft identity, draft branch/path plan and idempotent change decision.

Requirements 5.1–5.6. Pure logic only: no Git, filesystem or network access.
The later Git_Change_Manager step applies a :class:`DraftChange` to a real
repository; this module only decides *where* a draft goes and *whether* a
commit is needed.

Stable generation key
---------------------
Each of ``topic``, ``audience``, ``keywords``, Prompt_Version and the model
identifier is NFC-normalised, stripped and has every internal whitespace run
collapsed to one ASCII space (whitespace as defined by ``str.isspace``). The
five values are joined in that fixed order with :data:`KEY_SEPARATOR`
(U+001F UNIT SEPARATOR) and the UTF-8 bytes are hashed with SHA-256.

U+001F is itself whitespace for ``str.isspace``, so no normalised value can
contain it; with a fixed number of fields the joined string therefore maps
back to exactly one tuple of values and the encoding is unambiguous.

Targets
-------
* branch: ``draft/<key>`` (64 lowercase hex characters)
* file:   ``src/content/articles/<slug>-<key[:12]>.md``

The slug comes from the model result and may differ between reruns. So that a
rerun never adds a second Content_File for the same draft (Requirement 5.4),
an existing file on the draft branch whose name already ends with
``-<key[:12]>.md`` is reused as the target path.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum

from .article import CONTENT_ROOT, MSG_SLUG, is_slug, validate_content_path
from .errors import ArticleValidationError, FieldIssue
from .request import GenerationRequest

KEY_SEPARATOR = "\x1f"
KEY_FIELDS: tuple[str, ...] = ("topic", "audience", "keywords", "prompt_version", "model")
BRANCH_PREFIX = "draft/"
KEY_PREFIX_LENGTH = 12

_KEY_PATTERN = re.compile(r"[0-9a-f]{64}")


def normalize_key_text(value: str) -> str:
    """NFC-normalise, strip and collapse internal whitespace runs to one space."""
    if not isinstance(value, str):
        raise TypeError("stable key inputs must be strings")
    return " ".join(unicodedata.normalize("NFC", value).split())


def compute_stable_key(
    *, topic: str, audience: str, keywords: str, prompt_version: str, model: str
) -> str:
    """Return the lowercase hex SHA-256 stable generation key (Requirement 5.1).

    Raises:
        ValueError: naming (not echoing) any field that is empty after normalisation.
    """
    raw = {
        "topic": topic,
        "audience": audience,
        "keywords": keywords,
        "prompt_version": prompt_version,
        "model": model,
    }
    values = [normalize_key_text(raw[name]) for name in KEY_FIELDS]
    empty = [name for name, value in zip(KEY_FIELDS, values) if value == ""]
    if empty:
        raise ValueError("stable key fields must not be empty: " + ", ".join(empty))
    material = KEY_SEPARATOR.join(values).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def stable_key_for(request: GenerationRequest, model: str) -> str:
    """Stable key for a validated request and the configured model identifier."""
    return compute_stable_key(
        topic=request.topic,
        audience=request.audience,
        keywords=request.keywords,
        prompt_version=request.prompt_version,
        model=model,
    )


def is_stable_key(value: object) -> bool:
    return isinstance(value, str) and _KEY_PATTERN.fullmatch(value) is not None


def _require_key(key: str) -> None:
    if not is_stable_key(key):
        raise ValueError("stable key must be 64 lowercase hexadecimal characters")


def draft_branch(key: str) -> str:
    """``draft/<key>`` (Requirement 5.2)."""
    _require_key(key)
    return BRANCH_PREFIX + key


def draft_path(key: str, slug: str) -> str:
    """``src/content/articles/<slug>-<key[:12]>.md`` (Requirement 5.2).

    Raises:
        ArticleValidationError: if ``slug`` is not a Slug or the path is unsafe.
    """
    _require_key(key)
    if not is_slug(slug):
        raise ArticleValidationError([FieldIssue("slug", MSG_SLUG)])
    path = f"{CONTENT_ROOT}/{slug}-{key[:KEY_PREFIX_LENGTH]}.md"
    issues = validate_content_path(path)
    if issues:  # pragma: no cover - a Slug (<=80) + 13 chars always fits the rule
        raise ArticleValidationError(issues)
    return path


def _existing_draft_path(key: str, existing_paths: Iterable[str]) -> str | None:
    suffix = f"-{key[:KEY_PREFIX_LENGTH]}.md"
    matches = sorted(
        path
        for path in existing_paths
        if path.endswith(suffix)
        and not validate_content_path(path)
        and is_slug(path.rsplit("/", 1)[-1][: -len(suffix)])
    )
    # At most one exists when every write goes through this plan; picking the
    # smallest keeps the choice deterministic even if that invariant is broken.
    return matches[0] if matches else None


@dataclass(frozen=True)
class DraftTarget:
    """Where one stable draft lives: its key, branch and Content_File path."""

    key: str
    branch: str
    path: str


def plan_draft_target(key: str, slug: str, existing_paths: Iterable[str] = ()) -> DraftTarget:
    """Select the branch and Content_File path for ``key`` (Requirements 5.2–5.4).

    ``existing_paths`` are repo-relative file paths currently on the draft
    branch (empty when the branch does not exist yet). If one of them already
    carries this key's 12-character suffix it is reused, so a changed slug
    updates the existing file instead of adding a second one.
    """
    branch = draft_branch(key)
    new_path = draft_path(key, slug)  # validates slug even when an existing path wins
    path = _existing_draft_path(key, existing_paths) or new_path
    return DraftTarget(key=key, branch=branch, path=path)


class ChangeAction(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    UNCHANGED = "unchanged"

    @property
    def requires_commit(self) -> bool:
        return self is not ChangeAction.UNCHANGED


def decide_change(new_content: bytes, existing_content: bytes | None) -> ChangeAction:
    """Idempotent change decision on exact bytes (Requirement 5.5)."""
    if existing_content is None:
        return ChangeAction.CREATE
    if existing_content == new_content:
        return ChangeAction.UNCHANGED
    return ChangeAction.UPDATE


@dataclass(frozen=True)
class DraftChange:
    target: DraftTarget
    action: ChangeAction

    @property
    def requires_commit(self) -> bool:
        return self.action.requires_commit


def plan_draft_change(
    key: str,
    slug: str,
    content: bytes,
    existing_files: Mapping[str, bytes] | None = None,
) -> DraftChange:
    """Plan the target and decide create/update/unchanged for one draft.

    ``existing_files`` maps repo-relative paths on the draft branch to their
    bytes; pass ``None`` or ``{}`` when the branch does not exist yet.
    """
    files = existing_files or {}
    target = plan_draft_target(key, slug, files.keys())
    return DraftChange(target=target, action=decide_change(content, files.get(target.path)))
