"""Work_Schema (Python mirror of ``src/lib/work-schema.ts``) and work sources.

A *work* is one portfolio piece: ``src/content/works/<slug>.md`` plus its
photos and the maker's notes under ``src/assets/works/<slug>/``. The maker
creates both (``npm run ingest``), commits them to ``work/<slug>`` and only
then asks the generation workflow to draft the text.

Ownership of fields
-------------------
* Human-owned: everything the maker wrote — title, category, cover, alt
  texts, gallery, video, materials, tools (and their shop links), shop,
  difficulty, time spent, status, sources, pubDate. The pipeline copies these unchanged and the bundle check
  rejects any difference.
* Generated: ``description``, ``tags`` and the Markdown body, plus the fixed
  ``draft: true`` / ``ai_assisted: true`` / ``model`` / ``prompt_version``.

The model is text-only: it never sees the photos, so it never writes alt
texts. Alt texts that are still placeholders are allowed in drafts
(``allow_placeholders=True``) and rejected once ``draft: false``.

All functions are pure except :func:`load_work_source`, which only reads.
Issues name fields only; values are never echoed.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .article import (
    DEFAULT_MAX_BODY_CHARS,
    MSG_ARRAY,
    MSG_BOOLEAN,
    MSG_NON_EMPTY,
    MSG_OBJECT,
    MSG_REQUIRED,
    MSG_SLUG,
    MSG_STRING,
    MSG_STRING_ARRAY,
    MSG_TIMESTAMP,
    _check_source,
    MSG_HTTPS,
    is_https_url,
    is_non_empty_string,
    is_slug,
    is_utc_timestamp,
    normalize_body,
    render_content_file,
    validate_content_path,
    validate_markdown_body,
)
from .errors import ArticleValidationError, FieldIssue, PipelineError

WORKS_ROOT = "src/content/works"
WORK_ASSETS_ROOT = "src/assets/works"
NOTES_FILE = "notes.md"
WORK_BRANCH_PREFIX = "work/"

MAX_NOTES_CHARS = 8_000
MAX_WORK_FILE_BYTES = 256 * 1024

# Must equal CATEGORIES in src/lib/categories.ts (checked by tests/test_work.py).
CATEGORIES: tuple[tuple[str, str], ...] = (
    ("3d-printing", "3D打印"),
    ("sewing", "缝纫"),
    ("woodworking", "木工"),
    ("electronics", "电子DIY"),
    ("handcraft", "手工"),
)
CATEGORY_SLUGS = frozenset(slug for slug, _ in CATEGORIES)
CATEGORY_LABELS = dict(CATEGORIES)

IMAGE_EXTENSIONS: tuple[str, ...] = ("jpg", "jpeg", "png", "webp")
IMAGE_REF_PATTERN = re.compile(
    r"([a-z0-9]+(?:-[a-z0-9]+)*)/[a-z0-9][a-z0-9_-]{0,99}\.(?:jpe?g|png|webp)"
)
BILIBILI_ID_PATTERN = re.compile(r"BV[0-9A-Za-z]{10}")
YOUTUBE_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{11}")
DIFFICULTIES = frozenset({"beginner", "intermediate", "advanced"})
STATUSES = frozenset({"finished", "in-progress"})
PLACEHOLDER_TEXT = frozenset({"todo", "tbd", "待填写", "待定", "-", "...", "…"})
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_EMPTY_NOTE_LINE = re.compile(r"\s*(?:#{1,6}(?:\s.*)?|[0-9]+[.)]|[-*+])?\s*")

WORK_KEYS: tuple[str, ...] = (
    "title",
    "description",
    "pubDate",
    "updatedDate",
    "slug",
    "draft",
    "category",
    "tags",
    "cover",
    "coverAlt",
    "gallery",
    "video",
    "materials",
    "tools",
    "shop",
    "difficulty",
    "timeSpent",
    "status",
    "ai_assisted",
    "model",
    "prompt_version",
    "sources",
)
GENERATED_KEYS: frozenset[str] = frozenset(
    {"description", "tags", "draft", "ai_assisted", "model", "prompt_version"}
)
HUMAN_KEYS: tuple[str, ...] = tuple(k for k in WORK_KEYS if k not in GENERATED_KEYS)

MSG_PLACEHOLDER = "alt text must describe the image (placeholder not allowed)"
MSG_IMAGE_REF = 'must be "<slug>/<file>.(jpg|jpeg|png|webp)" in lowercase'
MSG_IMAGE_DIR = "image must be inside the work folder of this slug"
MSG_UNKNOWN = "is not a Work_Schema field"
MSG_SUPPLY = "must be a non-empty string or an object with name and url"
SUPPLY_LINK_KEYS = ("name", "url", "affiliate")
SHOP_LINK_KEYS = ("label", "url")


class WorkSourceError(PipelineError):
    """The maker's work files on ``work/<slug>`` are missing or unusable."""


# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------


def work_path(slug: str) -> str:
    if not is_slug(slug):
        raise ArticleValidationError([FieldIssue("slug", MSG_SLUG)])
    return f"{WORKS_ROOT}/{slug}.md"


def notes_path(slug: str) -> str:
    if not is_slug(slug):
        raise ArticleValidationError([FieldIssue("slug", MSG_SLUG)])
    return f"{WORK_ASSETS_ROOT}/{slug}/{NOTES_FILE}"


def work_branch(slug: str) -> str:
    if not is_slug(slug):
        raise ArticleValidationError([FieldIssue("slug", MSG_SLUG)])
    return WORK_BRANCH_PREFIX + slug


# --------------------------------------------------------------------------
# Front-matter validation
# --------------------------------------------------------------------------


def is_placeholder(value: Any) -> bool:
    return isinstance(value, str) and value.replace("\ufeff", "").strip().lower() in PLACEHOLDER_TEXT


def _string_list(data: Mapping[str, Any], key: str, issues: list[FieldIssue], *, non_empty: bool) -> None:
    if key not in data:
        return
    value = data[key]
    if not isinstance(value, (list, tuple)):
        issues.append(FieldIssue(key, MSG_STRING_ARRAY))
        return
    for i, item in enumerate(value):
        if not isinstance(item, str):
            issues.append(FieldIssue(f"{key}.{i}", MSG_STRING))
        elif non_empty and not is_non_empty_string(item):
            issues.append(FieldIssue(f"{key}.{i}", MSG_NON_EMPTY))


def _link_object(
    item: Mapping[str, Any], prefix: str, text_key: str, allowed: tuple[str, ...], issues: list[FieldIssue]
) -> None:
    """``{<text_key>, url, ...}``: non-empty text, absolute HTTPS URL, no unknown keys."""
    if not is_non_empty_string(item.get(text_key)):
        issues.append(FieldIssue(f"{prefix}.{text_key}", MSG_NON_EMPTY))
    if not is_https_url(item.get("url")):
        issues.append(FieldIssue(f"{prefix}.url", MSG_HTTPS))
    for key in item:
        if key not in allowed:
            issues.append(FieldIssue(f"{prefix}.{key}", MSG_UNKNOWN))


def _supply_list(data: Mapping[str, Any], key: str, issues: list[FieldIssue]) -> None:
    """``materials`` / ``tools``: plain names or ``{name, url, affiliate?}`` shop links."""
    if key not in data:
        return
    value = data[key]
    if not isinstance(value, (list, tuple)):
        issues.append(FieldIssue(key, MSG_ARRAY))
        return
    for i, item in enumerate(value):
        prefix = f"{key}.{i}"
        if isinstance(item, str):
            if not is_non_empty_string(item):
                issues.append(FieldIssue(prefix, MSG_NON_EMPTY))
        elif isinstance(item, Mapping):
            _link_object(item, prefix, "name", SUPPLY_LINK_KEYS, issues)
            if "affiliate" in item and not isinstance(item["affiliate"], bool):
                issues.append(FieldIssue(f"{prefix}.affiliate", MSG_BOOLEAN))
        else:
            issues.append(FieldIssue(prefix, MSG_SUPPLY))


def supply_name(item: Any) -> Any:
    """Display name of a ``materials`` / ``tools`` entry (URLs never reach the model)."""
    return item.get("name") if isinstance(item, Mapping) else item


def _alt(value: Any, field: str, issues: list[FieldIssue], allow_placeholders: bool) -> None:
    if not is_non_empty_string(value):
        issues.append(FieldIssue(field, MSG_NON_EMPTY))
    elif not allow_placeholders and is_placeholder(value):
        issues.append(FieldIssue(field, MSG_PLACEHOLDER))


def _image_ref(value: Any, field: str, slug: Any, issues: list[FieldIssue]) -> None:
    match = IMAGE_REF_PATTERN.fullmatch(value) if isinstance(value, str) else None
    if match is None:
        issues.append(FieldIssue(field, MSG_IMAGE_REF))
    elif is_slug(slug) and match.group(1) != slug:
        issues.append(FieldIssue(field, MSG_IMAGE_DIR))


def _check_video(value: Any, issues: list[FieldIssue]) -> None:
    if not isinstance(value, Mapping):
        issues.append(FieldIssue("video", MSG_OBJECT))
        return
    provider = value.get("provider")
    pattern = {"bilibili": BILIBILI_ID_PATTERN, "youtube": YOUTUBE_ID_PATTERN}.get(provider)  # type: ignore[arg-type]
    if pattern is None:
        issues.append(FieldIssue("video.provider", "must be bilibili or youtube"))
    elif not isinstance(value.get("id"), str) or pattern.fullmatch(value["id"]) is None:
        issues.append(FieldIssue("video.id", f"must be a valid {provider} video id"))
    if not is_non_empty_string(value.get("title")):
        issues.append(FieldIssue("video.title", MSG_NON_EMPTY))
    for key in value:
        if key not in ("provider", "id", "title"):
            issues.append(FieldIssue(f"video.{key}", MSG_UNKNOWN))


def validate_work_front_matter(data: Any, *, allow_placeholders: bool = False) -> list[FieldIssue]:
    """Work_Schema rules (same as the Astro side), plus unknown-key rejection."""
    if not isinstance(data, Mapping):
        return [FieldIssue("front-matter", "must be a mapping")]
    issues: list[FieldIssue] = []

    def scalar(key: str, check: Any, message: str, *, required: bool = True) -> None:
        if key not in data:
            if required:
                issues.append(FieldIssue(key, MSG_REQUIRED))
        elif not check(data[key]):
            issues.append(FieldIssue(key, message))

    scalar("title", is_non_empty_string, MSG_NON_EMPTY)
    scalar("description", is_non_empty_string, MSG_NON_EMPTY)
    scalar("pubDate", is_utc_timestamp, MSG_TIMESTAMP)
    scalar("updatedDate", is_utc_timestamp, MSG_TIMESTAMP, required=False)
    scalar("slug", is_slug, MSG_SLUG)
    scalar("draft", lambda v: isinstance(v, bool), MSG_BOOLEAN)
    scalar("category", lambda v: v in CATEGORY_SLUGS, "must be one of: " + ", ".join(s for s, _ in CATEGORIES))
    _string_list(data, "tags", issues, non_empty=False)

    slug = data.get("slug")
    if "cover" not in data:
        issues.append(FieldIssue("cover", MSG_REQUIRED))
    else:
        _image_ref(data["cover"], "cover", slug, issues)
    if "coverAlt" not in data:
        issues.append(FieldIssue("coverAlt", MSG_REQUIRED))
    else:
        _alt(data["coverAlt"], "coverAlt", issues, allow_placeholders)

    gallery = data.get("gallery", [])
    if not isinstance(gallery, (list, tuple)):
        issues.append(FieldIssue("gallery", MSG_ARRAY))
    else:
        for i, item in enumerate(gallery):
            prefix = f"gallery.{i}"
            if not isinstance(item, Mapping):
                issues.append(FieldIssue(prefix, MSG_OBJECT))
                continue
            _image_ref(item.get("src"), f"{prefix}.src", slug, issues)
            _alt(item.get("alt"), f"{prefix}.alt", issues, allow_placeholders)
            if "caption" in item and not is_non_empty_string(item["caption"]):
                issues.append(FieldIssue(f"{prefix}.caption", MSG_NON_EMPTY))
            for key in item:
                if key not in ("src", "alt", "caption"):
                    issues.append(FieldIssue(f"{prefix}.{key}", MSG_UNKNOWN))

    if "video" in data:
        _check_video(data["video"], issues)
    _supply_list(data, "materials", issues)
    _supply_list(data, "tools", issues)
    if "shop" in data:
        if not isinstance(data["shop"], (list, tuple)):
            issues.append(FieldIssue("shop", MSG_ARRAY))
        else:
            for i, item in enumerate(data["shop"]):
                if isinstance(item, Mapping):
                    _link_object(item, f"shop.{i}", "label", SHOP_LINK_KEYS, issues)
                else:
                    issues.append(FieldIssue(f"shop.{i}", MSG_OBJECT))
    scalar("difficulty", lambda v: v in DIFFICULTIES, "must be beginner, intermediate or advanced", required=False)
    scalar("timeSpent", is_non_empty_string, MSG_NON_EMPTY, required=False)
    scalar("status", lambda v: v in STATUSES, "must be finished or in-progress", required=False)
    scalar("ai_assisted", lambda v: isinstance(v, bool), MSG_BOOLEAN, required=False)
    scalar("model", is_non_empty_string, MSG_NON_EMPTY, required=False)
    scalar("prompt_version", is_non_empty_string, MSG_NON_EMPTY, required=False)
    if data.get("ai_assisted") is True:
        for key in ("model", "prompt_version"):
            if key not in data:
                issues.append(FieldIssue(key, "is required when ai_assisted is true"))

    if "sources" in data:
        if not isinstance(data["sources"], (list, tuple)):
            issues.append(FieldIssue("sources", MSG_ARRAY))
        else:
            for i, item in enumerate(data["sources"]):
                issues.extend(_check_source(i, item))

    for key in data:
        if key not in WORK_KEYS:
            issues.append(FieldIssue(str(key), MSG_UNKNOWN))
    return issues


def validate_work(
    path: Any, front_matter: Any, body: Any, *, allow_placeholders: bool = False,
    max_body_chars: int = DEFAULT_MAX_BODY_CHARS,
) -> list[FieldIssue]:
    """Path, front-matter and (optional, but checked when present) body."""
    issues = [
        *validate_content_path(path, WORKS_ROOT),
        *validate_work_front_matter(front_matter, allow_placeholders=allow_placeholders),
    ]
    if isinstance(body, str) and body.strip() != "":
        issues.extend(validate_markdown_body(body, max_body_chars))
    elif body is not None and not isinstance(body, str):
        issues.append(FieldIssue("body", "must be a string"))
    if isinstance(front_matter, Mapping) and is_slug(front_matter.get("slug")) and isinstance(path, str):
        if path != f"{WORKS_ROOT}/{front_matter['slug']}.md":
            issues.append(FieldIssue("path", "file name must be <slug>.md"))
    return issues


def validate_generated_work_flags(data: Any) -> list[FieldIssue]:
    if not isinstance(data, Mapping):
        return []
    issues = []
    if data.get("draft") is not True:
        issues.append(FieldIssue("draft", "must be true for generated works"))
    if data.get("ai_assisted") is not True:
        issues.append(FieldIssue("ai_assisted", "must be true for generated works"))
    return issues


# --------------------------------------------------------------------------
# Reading the maker's files
# --------------------------------------------------------------------------


def split_front_matter(text: str, name: str) -> tuple[Any, str]:
    """Split ``---`` front-matter from the body (LF-normalised). Raises WorkSourceError."""
    normalized = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    if not lines or lines[0] != "---":
        raise WorkSourceError(f"{name} must start with '---' delimited front-matter")
    for index in range(1, len(lines)):
        if lines[index] == "---":
            try:
                meta = yaml.safe_load("\n".join(lines[1:index]))
            except yaml.YAMLError:
                raise WorkSourceError(f"{name} front-matter is not valid YAML") from None
            return meta, "\n".join(lines[index + 1 :])
    raise WorkSourceError(f"{name} front-matter is not closed by '---'")


@dataclass(frozen=True)
class WorkSource:
    """The maker's inputs for one work, read from a ``work/<slug>`` checkout."""

    slug: str
    front_matter: Mapping[str, Any]
    notes: str

    def human_fields(self) -> dict[str, Any]:
        return {key: self.front_matter[key] for key in HUMAN_KEYS if key in self.front_matter}


def _read_text(root: Path, name: str, limit: int) -> str:
    """Read ``root/name`` (a repo-relative POSIX path) without following links out of the repo."""
    path = root / name
    try:
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise WorkSourceError(f"{name} must be a regular file inside the repository")
        with path.open("rb") as handle:
            data = handle.read(limit + 1)
    except FileNotFoundError:
        raise WorkSourceError(f"{name} not found") from None
    if len(data) > limit:
        raise WorkSourceError(f"{name} exceeds {limit} bytes")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise WorkSourceError(f"{name} is not valid UTF-8") from None


def load_work_source(repo_root: Path | str, slug: str) -> WorkSource:
    """Read and check ``<slug>.md`` and ``notes.md`` from a work branch checkout."""
    root = Path(repo_root)
    md_name, notes_name = work_path(slug), notes_path(slug)
    meta, _body = split_front_matter(_read_text(root, md_name, MAX_WORK_FILE_BYTES), md_name)
    issues = validate_work_front_matter(meta, allow_placeholders=True)
    if issues:
        raise ArticleValidationError(issues)
    if meta["slug"] != slug:
        raise ArticleValidationError([FieldIssue("slug", "must equal the requested work slug")])
    if meta["draft"] is not True:
        raise WorkSourceError(f"{md_name} has draft: false; only drafts can be generated")

    notes = _read_text(root, notes_name, MAX_NOTES_CHARS * 4)
    notes = notes.replace("\r\n", "\n").replace("\r", "\n")
    # Template instructions in HTML comments are for the maker, not the model.
    notes = re.sub(r"\n{3,}", "\n\n", _HTML_COMMENT.sub("", notes)).strip()
    # The untouched ingest template has only headings and empty list items.
    if all(_EMPTY_NOTE_LINE.fullmatch(line) for line in notes.split("\n")):
        raise WorkSourceError(f"{notes_name} is empty; write your making notes first")
    if len(notes) > MAX_NOTES_CHARS:
        raise WorkSourceError(f"{notes_name} exceeds {MAX_NOTES_CHARS} characters")
    return WorkSource(slug=slug, front_matter=meta, notes=notes)


# --------------------------------------------------------------------------
# Model input, stable key and assembly
# --------------------------------------------------------------------------


def model_input(source: WorkSource) -> dict[str, Any]:
    """Facts given to the model: human-owned fields and notes only (no photos)."""
    fm = source.front_matter
    photos = []
    for item in fm.get("gallery", []):
        described = {k: item[k] for k in ("caption", "alt") if k in item and not is_placeholder(item[k])}
        if described:
            photos.append(described)
    facts: dict[str, Any] = {
        "title": fm["title"],
        "category": CATEGORY_LABELS[fm["category"]],
        # Names only: shop / affiliate URLs are the maker's, never model input.
        "materials": [supply_name(m) for m in fm.get("materials", [])],
        "tools": [supply_name(t) for t in fm.get("tools", [])],
        "status": fm.get("status", "finished"),
        "photos": photos,
        "notes": source.notes,
    }
    for key in ("difficulty", "timeSpent"):
        if key in fm:
            facts[key] = fm[key]
    if "video" in fm:
        facts["video_title"] = fm["video"]["title"]
    return facts


def compute_work_key(source: WorkSource, prompt_version: str, model: str) -> str:
    """SHA-256 over the canonical model input, prompt version and model.

    Changes to notes or any human-owned fact give a new key, so a bundle can
    only be applied to the exact maker files it was generated from.
    """
    material = json.dumps(
        {
            "kind": "work",
            "slug": source.slug,
            "input": model_input(source),
            "human": source.human_fields(),
            "prompt_version": prompt_version,
            "model": model,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class WorkDraft:
    path: str
    front_matter: Mapping[str, Any]
    body: str

    def render(self) -> str:
        return render_content_file(self.front_matter, self.body)

    def to_bytes(self) -> bytes:
        return self.render().encode("utf-8")


def assemble_work_draft(
    source: WorkSource, result: Mapping[str, Any], *, model: str, prompt_version: str
) -> WorkDraft:
    """Human fields unchanged + generated description/tags/body; fully validated."""
    if not isinstance(result, Mapping):
        raise ArticleValidationError([FieldIssue("result", MSG_OBJECT)])
    merged: dict[str, Any] = dict(source.human_fields())
    if "description" in result:
        merged["description"] = result["description"]
    tags = result.get("tags", [])
    merged["tags"] = list(tags) if isinstance(tags, tuple) else tags
    merged["draft"] = True
    merged["ai_assisted"] = True
    merged["model"] = model
    merged["prompt_version"] = prompt_version
    front_matter = {key: merged[key] for key in WORK_KEYS if key in merged}

    raw_body = result.get("body")
    body = normalize_body(raw_body) if isinstance(raw_body, str) else raw_body
    path = work_path(source.slug)
    issues = [
        *validate_work(path, front_matter, body, allow_placeholders=True),
        *validate_generated_work_flags(front_matter),
    ]
    if not isinstance(body, str) or body.strip() == "":
        issues.append(FieldIssue("body", "must not be empty"))
    if issues:
        raise ArticleValidationError(issues)
    return WorkDraft(path=path, front_matter=front_matter, body=body)


__all__ = [
    "CATEGORIES",
    "HUMAN_KEYS",
    "WORKS_ROOT",
    "WORK_ASSETS_ROOT",
    "WORK_KEYS",
    "WorkDraft",
    "WorkSource",
    "WorkSourceError",
    "assemble_work_draft",
    "compute_work_key",
    "load_work_source",
    "model_input",
    "notes_path",
    "validate_work",
    "validate_work_front_matter",
    "work_branch",
    "work_path",
]
