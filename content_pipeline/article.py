"""Draft assembly, Article_Schema validation and safe Content_File writing.

Requirements 4.1–4.12, 7.1 and 8.1–8.5. The rules mirror the Astro-side
Article_Schema in ``src/lib/article-schema.ts`` and are, where the two differ,
deliberately stricter, so every draft written here is also accepted by the
static site once an editor flips ``draft`` to ``false``.

Pipeline for one Model_Gateway result:

1. ``assemble_draft`` builds the front-matter with forced ``draft: true``,
   ``ai_assisted: true``, the configured model and the selected
   Prompt_Version, and an always-present (possibly empty) ``sources`` array.
2. The Markdown_Body is normalised to LF and raw HTML is escaped to text
   (``escape_raw_html``).
3. Path, front-matter and body are validated in full. Any failure raises
   ``ArticleValidationError`` listing field names or ``body:<line>:<column>``
   positions, before anything touches the filesystem.
4. ``write_draft`` re-validates, checks the resolved path stays inside the
   content root, and writes UTF-8 without BOM with LF line endings only.

Raw HTML escaping
-----------------
In CommonMark every raw HTML construct (HTML blocks and inline HTML: tags,
closing tags, comments, processing instructions, declarations, CDATA) starts
with ``<`` immediately followed by an ASCII letter, ``/``, ``!`` or ``?``.
Each such ``<`` is replaced by the entity ``&lt;``, which CommonMark renders
as a literal ``<`` in text. This holds regardless of block structure, so no
parser is needed and no raw HTML can survive. Headings, emphasis, links and
plain text keep their CommonMark meaning. Autolinks (``<https://…>``) are not
raw HTML and are kept, so link validation still sees them. Trade-off: inside
code spans and code blocks entities are not decoded, so an HTML-like ``<``
there is shown as ``&lt;``; editors can restore it during review.
"""

from __future__ import annotations

import contextlib
import html
import ipaddress
import os
import re
import tempfile
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

from .errors import ArticleValidationError, FieldIssue

# Content directory relative to the repository root (POSIX separators).
CONTENT_ROOT = "src/content/articles"
# Default maximum Markdown_Body length in Unicode code points (same as Astro side).
DEFAULT_MAX_BODY_CHARS = 100_000

SLUG_MAX_LENGTH = 80
# Explicit ASCII classes; used with fullmatch so a trailing "\n" never matches.
FILENAME_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]{0,99}\.md")
SLUG_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
UTC_TIMESTAMP_PATTERN = re.compile(
    r"([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})Z"
)

FRONT_MATTER_KEYS: tuple[str, ...] = (
    "title",
    "description",
    "pubDate",
    "updatedDate",
    "tags",
    "slug",
    "draft",
    "ai_assisted",
    "model",
    "prompt_version",
    "sources",
)
SOURCE_KEYS: tuple[str, ...] = ("title", "url", "accessedDate")

MSG_REQUIRED = "is required"
MSG_NON_EMPTY = "must be a non-empty string"
MSG_TIMESTAMP = "must be a UTC timestamp formatted YYYY-MM-DDTHH:mm:ssZ"
MSG_STRING_ARRAY = "must be an array of strings"
MSG_STRING = "must be a string"
MSG_SLUG = "must match ^[a-z0-9]+(?:-[a-z0-9]+)*$ and be 1-80 characters"
MSG_BOOLEAN = "must be a boolean"
MSG_ARRAY = "must be an array"
MSG_OBJECT = "must be an object"
MSG_HTTPS = "must be an absolute HTTPS URL"
MSG_LINK = 'link target must be an absolute HTTPS URL or a site path starting with "/"'
MSG_SCRIPT = "executable <script> element is not allowed"
MSG_RAW_HTML = "raw HTML must be escaped as text"


# --------------------------------------------------------------------------
# Scalar rules
# --------------------------------------------------------------------------


def is_utc_timestamp(value: Any) -> bool:
    """True for ``YYYY-MM-DDTHH:mm:ssZ`` strings denoting a real calendar instant."""
    if not isinstance(value, str):
        return False
    match = UTC_TIMESTAMP_PATTERN.fullmatch(value)
    if match is None:
        return False
    year, month, day, hour, minute, second = (int(part) for part in match.groups())
    # JS Date.UTC maps years 0-99 to 1900-1999, so the Astro schema rejects them.
    if year < 100:
        return False
    try:
        datetime(year, month, day, hour, minute, second)
    except ValueError:
        return False
    return True


def format_utc_timestamp(moment: datetime) -> str:
    """Format a timezone-aware datetime as ``YYYY-MM-DDTHH:mm:ssZ`` (UTC)."""
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    utc = moment.astimezone(timezone.utc)
    return (
        f"{utc.year:04d}-{utc.month:02d}-{utc.day:02d}"
        f"T{utc.hour:02d}:{utc.minute:02d}:{utc.second:02d}Z"
    )


def is_non_empty_string(value: Any) -> bool:
    # U+FEFF is removed too: JavaScript's trim() (used by the Astro schema) strips it.
    return isinstance(value, str) and value.replace("\ufeff", "").strip() != ""


def is_slug(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) <= SLUG_MAX_LENGTH
        and SLUG_PATTERN.fullmatch(value) is not None
    )


# ASCII control characters, space and backslash (browsers treat "\" like "/").
_URL_FORBIDDEN = re.compile(r"[\x00-\x20\x7f\\]")
_HOST_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_HOSTNAME_PATTERN = re.compile(rf"{_HOST_LABEL}(?:\.{_HOST_LABEL})*\.?")


def is_https_url(value: Any) -> bool:
    """True for an absolute ``https://`` URL with a valid host and no credentials."""
    if not isinstance(value, str) or _URL_FORBIDDEN.search(value):
        return False
    if value[:8].lower() != "https://":
        return False
    try:
        parts = urlsplit(value)
        parts.port  # noqa: B018 - raises ValueError for an invalid port
    except ValueError:
        return False
    if "@" in parts.netloc:
        return False
    host = parts.hostname
    if not host:
        return False
    if parts.netloc.startswith("["):
        try:
            ipaddress.IPv6Address(host)
        except ValueError:
            return False
        return True
    if _HOSTNAME_PATTERN.fullmatch(host) is None:
        return False
    bare = host.rstrip(".")
    if re.fullmatch(r"[0-9]+", bare.rsplit(".", 1)[-1]):
        # A numeric last label makes the WHATWG URL parser treat the host as IPv4.
        try:
            ipaddress.IPv4Address(bare)
        except ValueError:
            return False
    return True


def _is_allowed_target_form(target: str) -> bool:
    if target.startswith("/"):
        return not target.startswith(("//", "/\\")) and _URL_FORBIDDEN.search(target) is None
    return is_https_url(target)


def is_allowed_link_target(target: Any) -> bool:
    """Absolute HTTPS URL or site-absolute path (``/…``, not protocol-relative).

    Both the raw target and its entity-decoded form must pass, so encodings
    such as ``/&#47;evil.example`` cannot smuggle in a protocol-relative URL.
    """
    if not isinstance(target, str):
        return False
    return _is_allowed_target_form(target) and _is_allowed_target_form(html.unescape(target))


# --------------------------------------------------------------------------
# Path rules
# --------------------------------------------------------------------------


def _segments(path: str) -> list[str]:
    return path.replace("\\", "/").split("/")


def validate_content_path(path: Any, content_root: str = CONTENT_ROOT) -> list[FieldIssue]:
    """Pure check: ``path`` is ``<content_root>/<filename>`` relative to the repo root."""
    if not isinstance(path, str) or path == "":
        return [FieldIssue("path", "missing file path")]
    if "\x00" in path:
        return [FieldIssue("path", "path must not contain NUL characters")]
    normalized = path.replace("\\", "/")
    if normalized.startswith("/") or re.match(r"[A-Za-z]:", normalized):
        return [FieldIssue("path", "path must be relative to the repository root")]
    segments = normalized.split("/")
    if any(segment in (".", "..") for segment in segments):
        return [FieldIssue("path", 'path must not contain "." or ".." segments')]
    root_segments = _segments(content_root.strip("/\\"))
    if segments[:-1] != root_segments:
        return [FieldIssue("path", f"file must be directly inside {content_root}")]
    if FILENAME_PATTERN.fullmatch(segments[-1]) is None:
        return [FieldIssue("path", r"filename must match ^[a-z0-9][a-z0-9-]{0,99}\.md$")]
    return []


def resolve_content_path(
    repo_root: Path | str, path: str, content_root: str = CONTENT_ROOT
) -> Path:
    """Return the absolute target path, or raise if it is unsafe.

    Besides the pure rules, the resolved path (symlinks followed) must be the
    file directly inside the resolved content root, and the content root must
    stay inside the repository. Nothing is created or modified.
    """
    issues = validate_content_path(path, content_root)
    if issues:
        raise ArticleValidationError(issues)
    repo = Path(repo_root).resolve()
    root = (repo / content_root).resolve()
    filename = _segments(path)[-1]
    target = (repo / path).resolve()
    if not root.is_relative_to(repo) or target != root / filename:
        raise ArticleValidationError([FieldIssue("path", "resolved path escapes the content root")])
    return target


# --------------------------------------------------------------------------
# Markdown_Body: raw HTML escaping, links and scripts
# --------------------------------------------------------------------------

# CommonMark autolinks. Deliberately a subset of the spec (also excludes DEL):
# anything not matched is escaped, which is always safe.
_URI_AUTOLINK = re.compile(r"<([A-Za-z][A-Za-z0-9+.-]{1,31}:[^\x00-\x20\x7f<>]*)>")
_EMAIL_AUTOLINK = re.compile(
    r"<([A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*)>"
)
_SCRIPT_TAG_NAME = re.compile(r"script(?=[\s/>]|$)", re.IGNORECASE)


def _is_backslash_escaped(text: str, index: int) -> bool:
    count = 0
    while index - count > 0 and text[index - count - 1] == "\\":
        count += 1
    return count % 2 == 1


def _match_autolink(text: str, index: int) -> re.Match[str] | None:
    return _URI_AUTOLINK.match(text, index) or _EMAIL_AUTOLINK.match(text, index)


def _markup_starts(text: str) -> Iterator[tuple[int, int]]:
    """Yield ``(start, lt)`` for each ``<`` that could open raw HTML.

    ``lt`` is the index of ``<``; ``start`` is ``lt - 1`` when it is
    backslash-escaped (``\\<``), so the escape and the ``<`` are replaced
    together (both render as a literal ``<``). Unescaped autolinks are skipped.
    """
    index = 0
    while (lt := text.find("<", index)) >= 0:
        escaped = _is_backslash_escaped(text, lt)
        if not escaped and (autolink := _match_autolink(text, lt)) is not None:
            index = autolink.end()
            continue
        following = text[lt + 1 : lt + 2]
        if following.isascii() and (following.isalpha() or following in ("/", "!", "?")):
            yield (lt - 1 if escaped else lt), lt
        index = lt + 1


def escape_raw_html(body: str) -> str:
    """Escape every raw-HTML opening ``<`` as ``&lt;`` (see module docstring)."""
    parts: list[str] = []
    position = 0
    for start, lt in _markup_starts(body):
        parts.append(body[position:start])
        parts.append("&lt;")
        position = lt + 1
    parts.append(body[position:])
    return "".join(parts)


def normalize_body(body: str) -> str:
    """LF line endings, NUL replaced (as CommonMark does), raw HTML escaped,
    no leading/trailing blank lines and exactly one final newline."""
    text = body.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "\ufffd")
    text = escape_raw_html(text).strip("\n")
    return text + "\n" if text else text


# Inline links and images: "](" then optional whitespace, then the destination.
_INLINE_LINK = re.compile(r"\]\(\s*(?:<([^<>\n]*)>|([^\s)]*))")
# Link reference definitions (over-approximated: any line-leading "[label]:",
# also inside block quotes and list items; label may span lines).
_REFERENCE_DEFINITION = re.compile(
    r"^(?:[ \t]*(?:>|(?:[-+*]|[0-9]{1,9}[.)])(?=[ \t])))*[ \t]*"
    r"\[(?:[^\[\]\\]|\\[\s\S]){1,999}\]:[ \t]*(?:\n(?:[ \t]*>)*)?[ \t]*(?:<([^<>\n]*)>|(\S*))",
    re.MULTILINE,
)


def _link_targets(body: str) -> Iterator[tuple[int, str]]:
    """Yield ``(offset, target)`` for every link-like destination in the body.

    Scanning is conservative: code spans and code blocks are not excluded, so
    anything that could be a link under CommonMark is checked.
    """
    for pattern in (_INLINE_LINK, _REFERENCE_DEFINITION):
        for match in pattern.finditer(body):
            group = 1 if match.group(1) is not None else 2
            yield match.start(group), match.group(group)
    index = 0
    while (lt := body.find("<", index)) >= 0:
        autolink = None if _is_backslash_escaped(body, lt) else _match_autolink(body, lt)
        if autolink is None:
            index = lt + 1
            continue
        target = autolink.group(1)
        if autolink.re is _EMAIL_AUTOLINK:
            target = "mailto:" + target
        yield lt + 1, target
        index = autolink.end()


def _position(text: str, offset: int) -> str:
    line = text.count("\n", 0, offset) + 1
    column = offset - (text.rfind("\n", 0, offset) + 1) + 1
    return f"body:{line}:{column}"


def validate_markdown_body(
    body: Any, max_chars: int = DEFAULT_MAX_BODY_CHARS
) -> list[FieldIssue]:
    """Non-empty, bounded, LF-only, no raw HTML or scripts, allowed links only."""
    if not isinstance(body, str) or body.strip() == "":
        return [FieldIssue("body", "must not be empty")]
    issues: list[FieldIssue] = []
    if len(body) > max_chars:
        issues.append(FieldIssue("body", f"exceeds {max_chars} characters"))
    if "\r" in body:
        issues.append(FieldIssue("body", "must use LF line endings only"))
    try:
        body.encode("utf-8")
    except UnicodeEncodeError:
        issues.append(FieldIssue("body", "must be valid Unicode text"))
    for start, lt in _markup_starts(body):
        is_script = start == lt and _SCRIPT_TAG_NAME.match(body, lt + 1) is not None
        issues.append(FieldIssue(_position(body, lt), MSG_SCRIPT if is_script else MSG_RAW_HTML))
    for offset, target in _link_targets(body):
        if not is_allowed_link_target(target):
            issues.append(FieldIssue(_position(body, offset), MSG_LINK))
    return issues


# --------------------------------------------------------------------------
# Front-matter
# --------------------------------------------------------------------------


def _check_source(index: int, item: Any) -> list[FieldIssue]:
    prefix = f"sources.{index}"
    if not isinstance(item, Mapping):
        return [FieldIssue(prefix, MSG_OBJECT)]
    rules = (("title", is_non_empty_string, MSG_NON_EMPTY), ("url", is_https_url, MSG_HTTPS),
             ("accessedDate", is_utc_timestamp, MSG_TIMESTAMP))
    issues = []
    for key, check, message in rules:
        if key not in item:
            issues.append(FieldIssue(f"{prefix}.{key}", MSG_REQUIRED))
        elif not check(item[key]):
            issues.append(FieldIssue(f"{prefix}.{key}", message))
    return issues


def validate_front_matter(data: Any) -> list[FieldIssue]:
    """Article_Schema front-matter rules; issues follow FRONT_MATTER_KEYS order."""
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

    if "tags" not in data:
        issues.append(FieldIssue("tags", MSG_REQUIRED))
    elif not isinstance(data["tags"], (list, tuple)):
        issues.append(FieldIssue("tags", MSG_STRING_ARRAY))
    else:
        issues.extend(
            FieldIssue(f"tags.{i}", MSG_STRING)
            for i, tag in enumerate(data["tags"])
            if not isinstance(tag, str)
        )

    scalar("slug", is_slug, MSG_SLUG)
    scalar("draft", lambda v: isinstance(v, bool), MSG_BOOLEAN)
    scalar("ai_assisted", lambda v: isinstance(v, bool), MSG_BOOLEAN)
    scalar("model", is_non_empty_string, MSG_NON_EMPTY)
    scalar("prompt_version", is_non_empty_string, MSG_NON_EMPTY)

    if "sources" not in data:
        issues.append(FieldIssue("sources", MSG_REQUIRED))
    elif not isinstance(data["sources"], (list, tuple)):
        issues.append(FieldIssue("sources", MSG_ARRAY))
    else:
        for i, item in enumerate(data["sources"]):
            issues.extend(_check_source(i, item))
    return issues


def validate_generated_flags(data: Any) -> list[FieldIssue]:
    """Generated Content_Files must be AI-assisted drafts (Requirements 4.3, 7.1)."""
    if not isinstance(data, Mapping):
        return []
    issues = []
    if data.get("draft") is not True:
        issues.append(FieldIssue("draft", "must be true for generated articles"))
    if data.get("ai_assisted") is not True:
        issues.append(FieldIssue("ai_assisted", "must be true for generated articles"))
    return issues


def validate_article(
    path: Any,
    front_matter: Any,
    body: Any,
    *,
    content_root: str = CONTENT_ROOT,
    max_body_chars: int = DEFAULT_MAX_BODY_CHARS,
) -> list[FieldIssue]:
    """All pure Article_Schema checks for one Content_File (no filesystem access)."""
    return [
        *validate_content_path(path, content_root),
        *validate_front_matter(front_matter),
        *validate_markdown_body(body, max_body_chars),
    ]


# --------------------------------------------------------------------------
# Serialisation
# --------------------------------------------------------------------------


class _FrontMatterDumper(yaml.SafeDumper):
    """Double-quotes every string so YAML 1.1 (PyYAML) and YAML 1.2 (js-yaml)
    read identical strings (dates stay strings, ``1e5``/``0o7`` stay text)."""

    def ignore_aliases(self, data: Any) -> bool:
        return True


class _QuotedStr(str):
    """String value emitted double-quoted (keys stay plain identifiers)."""


def _represent_quoted(dumper: yaml.SafeDumper, value: str) -> yaml.ScalarNode:
    return dumper.represent_scalar("tag:yaml.org,2002:str", str(value), style='"')


_FrontMatterDumper.add_representer(_QuotedStr, _represent_quoted)
_NO_WRAP = 2**30


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, str):
        return _QuotedStr(value)
    return value


def render_content_file(front_matter: Mapping[str, Any], body: str) -> str:
    """Render ``---`` delimited YAML front-matter followed by the Markdown_Body."""
    data = _plain(front_matter)
    yaml_text = yaml.dump(
        data,
        Dumper=_FrontMatterDumper,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=_NO_WRAP,
        line_break="\n",
    )
    if yaml.safe_load(yaml_text) != data:
        raise ArticleValidationError([FieldIssue("front-matter", "cannot be serialised losslessly")])
    return f"---\n{yaml_text}---\n{body}"


@dataclass(frozen=True)
class DraftArticle:
    """A validated generated draft: repo-relative path, front-matter and body."""

    path: str
    front_matter: Mapping[str, Any]
    body: str

    def render(self) -> str:
        return render_content_file(self.front_matter, self.body)

    def to_bytes(self) -> bytes:
        """UTF-8 without BOM, LF line endings only."""
        data = self.render().encode("utf-8")
        if data.startswith(b"\xef\xbb\xbf") or b"\r" in data:
            raise ArticleValidationError([FieldIssue("body", "must use LF line endings only")])
        return data


# --------------------------------------------------------------------------
# Assembly and writing
# --------------------------------------------------------------------------


def _timestamp_value(value: Any) -> Any:
    """Format aware datetimes; anything else is returned for validation to judge."""
    if isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None:
        return format_utc_timestamp(value)
    return value


def _sources_value(value: Any) -> Any:
    if value is None:
        return []  # Requirement 4.4: always write the array, empty without sources.
    if not isinstance(value, (list, tuple)):
        return value
    sources: list[Any] = []
    for item in value:
        if isinstance(item, Mapping):
            item = {key: _timestamp_value(item[key]) if key == "accessedDate" else item[key]
                    for key in SOURCE_KEYS if key in item}
        sources.append(item)
    return sources


def assemble_draft(
    result: Any,
    *,
    model: str,
    prompt_version: str,
    pub_date: datetime | str,
    path: str,
    content_root: str = CONTENT_ROOT,
    max_body_chars: int = DEFAULT_MAX_BODY_CHARS,
) -> DraftArticle:
    """Build and fully validate a Draft_Article from a parsed generation result.

    ``result`` supplies ``title``, ``description``, ``body``, ``slug`` and
    optionally ``tags``, ``sources`` and ``updatedDate``. ``draft``,
    ``ai_assisted``, ``model`` and ``prompt_version`` are always set here and
    any values for them in ``result`` are ignored. Unknown keys are dropped.

    Raises:
        ArticleValidationError: listing every failing field or body position.
            Nothing is written to disk by this function.
    """
    if not isinstance(result, Mapping):
        raise ArticleValidationError([FieldIssue("result", MSG_OBJECT)])

    front_matter: dict[str, Any] = {}
    for key in ("title", "description"):
        if key in result:
            front_matter[key] = result[key]
    front_matter["pubDate"] = _timestamp_value(pub_date)
    if result.get("updatedDate") is not None:  # Requirement 4.2: only when provided.
        front_matter["updatedDate"] = _timestamp_value(result["updatedDate"])
    tags = result.get("tags")
    front_matter["tags"] = [] if tags is None else list(tags) if isinstance(tags, tuple) else tags
    if "slug" in result:
        front_matter["slug"] = result["slug"]
    front_matter["draft"] = True
    front_matter["ai_assisted"] = True
    front_matter["model"] = model
    front_matter["prompt_version"] = prompt_version
    front_matter["sources"] = _sources_value(result.get("sources"))

    raw_body = result.get("body")
    body = normalize_body(raw_body) if isinstance(raw_body, str) else raw_body

    issues = validate_article(
        path, front_matter, body, content_root=content_root, max_body_chars=max_body_chars
    )
    if issues:
        raise ArticleValidationError(issues)
    return DraftArticle(path=path, front_matter=front_matter, body=body)


def write_draft(
    draft: DraftArticle,
    repo_root: Path | str,
    *,
    content_root: str = CONTENT_ROOT,
    max_body_chars: int = DEFAULT_MAX_BODY_CHARS,
) -> bool:
    """Validate, then write the draft atomically. Returns False if unchanged.

    All checks (schema, draft flags, serialisation, resolved path) complete
    before the filesystem is modified, so a failure leaves no change behind.
    An identical existing file is left untouched.
    """
    issues = [
        *validate_article(
            draft.path,
            draft.front_matter,
            draft.body,
            content_root=content_root,
            max_body_chars=max_body_chars,
        ),
        *validate_generated_flags(draft.front_matter),
    ]
    if issues:
        raise ArticleValidationError(issues)
    data = draft.to_bytes()
    target = resolve_content_path(repo_root, draft.path, content_root)

    try:
        if target.read_bytes() == data:
            return False
    except FileNotFoundError:
        pass

    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.chmod(temp_name, 0o644)
        os.replace(temp_name, target)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temp_name)
        raise
    return True
