"""Unit tests for draft assembly, Article_Schema validation and safe writing
(Requirements 4.1–4.12, 7.1, 8.1–8.5)."""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
import yaml

from content_pipeline.article import (
    CONTENT_ROOT,
    DraftArticle,
    assemble_draft,
    escape_raw_html,
    is_allowed_link_target,
    is_https_url,
    is_utc_timestamp,
    resolve_content_path,
    validate_content_path,
    validate_front_matter,
    validate_markdown_body,
    write_draft,
)
from content_pipeline.errors import ArticleValidationError, PipelineError

PATH = f"{CONTENT_ROOT}/intro-to-static-sites-0123456789ab.md"
MODEL = "openai/gpt-4o-mini"
PROMPT_VERSION = "1.2.0"
PUB_DATE = "2024-05-01T08:30:00Z"


def _result(**overrides: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "title": "Intro to static sites",
        "description": "Why static hosting keeps costs low.",
        "slug": "intro-to-static-sites",
        "tags": ["static", "astro"],
        "body": "# Intro\n\nRead [the docs](https://docs.astro.build/) and [about](/about).\n",
    }
    result.update(overrides)
    return result


def _assemble(result: dict[str, Any] | None = None, **kwargs: Any) -> DraftArticle:
    options: dict[str, Any] = {
        "model": MODEL,
        "prompt_version": PROMPT_VERSION,
        "pub_date": PUB_DATE,
        "path": PATH,
    }
    options.update(kwargs)
    return assemble_draft(_result() if result is None else result, **options)


def _fields(exc: pytest.ExceptionInfo[ArticleValidationError]) -> list[str]:
    return list(exc.value.fields)


def _split(text: str) -> tuple[dict[str, Any], str]:
    match = re.fullmatch(r"---\n(.*?\n)---\n(.*)", text, re.DOTALL)
    assert match is not None
    return yaml.safe_load(match.group(1)), match.group(2)


# --- assembly -------------------------------------------------------------


def test_assembled_draft_forces_generation_fields_and_order() -> None:
    draft = _assemble(
        _result(draft=False, ai_assisted=False, model="other", prompt_version="9.9.9", extra="x")
    )
    front_matter, body = _split(draft.render())

    assert list(front_matter) == [
        "title", "description", "pubDate", "tags", "slug",
        "draft", "ai_assisted", "model", "prompt_version", "sources",
    ]
    assert front_matter["draft"] is True
    assert front_matter["ai_assisted"] is True
    assert front_matter["model"] == MODEL
    assert front_matter["prompt_version"] == PROMPT_VERSION
    assert front_matter["sources"] == []
    assert front_matter["pubDate"] == PUB_DATE
    assert body == _result()["body"]


def test_updated_date_and_sources_are_written_when_provided() -> None:
    source = {"title": "Astro docs", "url": "https://docs.astro.build/", "accessedDate": PUB_DATE, "x": 1}
    draft = _assemble(_result(updatedDate="2024-05-02T00:00:00Z", sources=[source]))
    front_matter, _ = _split(draft.render())

    assert front_matter["updatedDate"] == "2024-05-02T00:00:00Z"
    assert front_matter["sources"] == [
        {"title": "Astro docs", "url": "https://docs.astro.build/", "accessedDate": PUB_DATE}
    ]


def test_updated_date_is_omitted_when_absent_or_null() -> None:
    assert "updatedDate" not in _assemble(_result(updatedDate=None)).front_matter
    assert "updatedDate" not in _assemble().front_matter


def test_aware_datetime_pub_date_is_converted_to_utc() -> None:
    moment = datetime(2024, 5, 1, 16, 30, tzinfo=timezone(timedelta(hours=8)))
    assert _assemble(pub_date=moment).front_matter["pubDate"] == PUB_DATE


def test_naive_datetime_pub_date_is_rejected() -> None:
    with pytest.raises(ArticleValidationError) as exc:
        _assemble(pub_date=datetime(2024, 5, 1, 8, 30))
    assert _fields(exc) == ["pubDate"]


def test_strings_are_quoted_so_yaml_1_2_readers_keep_them_as_text() -> None:
    draft = _assemble(_result(title="1e5", tags=["0o17", "yes", "null"]))
    text = draft.render()
    assert 'title: "1e5"' in text
    assert f'pubDate: "{PUB_DATE}"' in text
    assert '- "0o17"' in text and '- "null"' in text


def test_encoding_is_utf8_without_bom_and_lf_only() -> None:
    draft = _assemble(_result(title="静态站点\r\n入门", body="第一行\r\n第二行\r第三行"))
    data = draft.to_bytes()

    assert not data.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in data
    assert data.endswith(b"\n") and not data.endswith(b"\n\n")
    front_matter, body = _split(data.decode("utf-8"))
    assert front_matter["title"] == "静态站点\r\n入门"  # escaped inside a quoted scalar
    assert body == "第一行\n第二行\n第三行\n"


def test_invalid_result_reports_every_field_without_values() -> None:
    result = {
        "title": "  ",
        "description": 3,
        "slug": "Bad_Slug",
        "tags": "not-a-list",
        "updatedDate": "2024-02-30T00:00:00Z",
        "sources": [
            {"title": "", "url": "http://insecure.example/secret-token", "accessedDate": "2024-05-01"},
            "not-an-object",
        ],
        "body": "",
    }
    with pytest.raises(ArticleValidationError) as exc:
        _assemble(result, pub_date="2024-05-01 08:30:00")

    assert _fields(exc) == [
        "title", "description", "pubDate", "updatedDate", "tags", "slug",
        "sources.0.title", "sources.0.url", "sources.0.accessedDate", "sources.1", "body",
    ]
    assert "secret-token" not in str(exc.value)
    assert isinstance(exc.value, PipelineError)


def test_missing_fields_are_reported_as_required() -> None:
    with pytest.raises(ArticleValidationError) as exc:
        _assemble({"body": "Text"})
    assert _fields(exc) == ["title", "description", "slug"]
    assert "title: is required" in str(exc.value)


def test_empty_model_or_prompt_version_fails() -> None:
    with pytest.raises(ArticleValidationError) as exc:
        _assemble(model=" ", prompt_version="")
    assert _fields(exc) == ["model", "prompt_version"]


def test_non_mapping_result_fails() -> None:
    with pytest.raises(ArticleValidationError) as exc:
        _assemble(["not", "a", "mapping"])  # type: ignore[arg-type]
    assert _fields(exc) == ["result"]


# --- scalar rules ---------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        ("2024-05-01T08:30:00Z", True),
        ("2024-02-29T23:59:59Z", True),
        ("2023-02-29T00:00:00Z", False),
        ("2024-05-01T24:00:00Z", False),
        ("2024-05-01T08:30:60Z", False),
        ("2024-05-01T08:30:00+00:00", False),
        ("2024-05-01T08:30:00.000Z", False),
        ("2024-05-01", False),
        ("0099-01-01T00:00:00Z", False),
        ("２０２４-05-01T08:30:00Z", False),
        ("2024-05-01T08:30:00Z\n", False),
        (None, False),
    ],
)
def test_utc_timestamp(value: Any, expected: bool) -> None:
    assert is_utc_timestamp(value) is expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("https://example.com", True),
        ("HTTPS://Example.com/a?b=c#d", True),
        ("https://[2001:db8::1]:8443/x", True),
        ("https://1.2.3.4/", True),
        ("http://example.com", False),
        ("https://", False),
        ("https:example.com", False),
        ("https://user:pass@example.com", False),
        ("https://exa mple.com", False),
        ("https://example.com:99999", False),
        ("https://999.1.1.1/", False),
        ("https://example.com\\@evil", False),
        (" https://example.com", False),
        ("javascript:alert(1)", False),
    ],
)
def test_https_url(value: str, expected: bool) -> None:
    assert is_https_url(value) is expected


@pytest.mark.parametrize(
    "target,expected",
    [
        ("/about", True),
        ("/", True),
        ("https://example.com/a", True),
        ("//evil.example", False),
        ("/\\evil.example", False),
        ("/&#47;evil.example", False),
        ("&#104;ttps://example.com", False),
        ("relative/path", False),
        ("#section", False),
        ("mailto:a@example.com", False),
        ("", False),
    ],
)
def test_link_targets(target: str, expected: bool) -> None:
    assert is_allowed_link_target(target) is expected


def test_slug_length_limit() -> None:
    base = {
        "title": "t", "description": "d", "pubDate": PUB_DATE, "tags": [], "draft": True,
        "ai_assisted": True, "model": "m", "prompt_version": "1.0.0", "sources": [],
    }
    assert validate_front_matter({**base, "slug": "a" * 80}) == []
    assert [i.field for i in validate_front_matter({**base, "slug": "a" * 81})] == ["slug"]
    assert [i.field for i in validate_front_matter({**base, "slug": "a", "draft": "false"})] == ["draft"]


# --- paths ----------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        f"{CONTENT_ROOT}/a.md",
        f"{CONTENT_ROOT}/{'a' * 100}.md",
        "src\\content\\articles\\post-1.md",
    ],
)
def test_valid_content_paths(path: str) -> None:
    assert validate_content_path(path) == []


@pytest.mark.parametrize(
    "path",
    [
        "",
        f"{CONTENT_ROOT}/../articles/a.md",
        "src/content/articles/../../../etc/passwd.md",
        "src\\content\\articles\\..\\..\\a.md",
        f"{CONTENT_ROOT}/./a.md",
        f"/{CONTENT_ROOT}/a.md",
        f"C:/repo/{CONTENT_ROOT}/a.md",
        f"{CONTENT_ROOT}/nested/a.md",
        "src/content/a.md",
        f"{CONTENT_ROOT}//a.md",
        f"{CONTENT_ROOT}/A.md",
        f"{CONTENT_ROOT}/-a.md",
        f"{CONTENT_ROOT}/a.markdown",
        f"{CONTENT_ROOT}/{'a' * 101}.md",
        f"{CONTENT_ROOT}/a.md\n",
        f"{CONTENT_ROOT}/a\x00.md",
    ],
)
def test_invalid_content_paths(path: str) -> None:
    issues = validate_content_path(path)
    assert [issue.field for issue in issues] == ["path"]


def test_resolved_symlink_outside_content_root_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / CONTENT_ROOT
    root.mkdir(parents=True)
    outside = tmp_path / "outside.md"
    outside.write_text("x", encoding="utf-8")
    link = root / "linked.md"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available on this platform")

    with pytest.raises(ArticleValidationError) as exc:
        resolve_content_path(tmp_path, f"{CONTENT_ROOT}/linked.md")
    assert _fields(exc) == ["path"]


# --- body: escaping, scripts and links --------------------------------------


def test_raw_html_is_escaped_and_markdown_structure_is_kept() -> None:
    body = (
        "# Title <b>bold</b>\n"
        "\n"
        "<script>alert(1)</script>\n"
        "<!-- comment --> <?php x ?> <!DOCTYPE html> <![CDATA[x]]>\n"
        "Text with [a link](https://example.com/a) and a < b, x<3.\n"
        "Autolink <https://example.com/b>. Escaped \\<i>not tag\\</i>.\n"
    )
    escaped = escape_raw_html(body)

    assert escaped == (
        "# Title &lt;b>bold&lt;/b>\n"
        "\n"
        "&lt;script>alert(1)&lt;/script>\n"
        "&lt;!-- comment --> &lt;?php x ?> &lt;!DOCTYPE html> &lt;![CDATA[x]]>\n"
        "Text with [a link](https://example.com/a) and a < b, x<3.\n"
        "Autolink <https://example.com/b>. Escaped &lt;i>not tag&lt;/i>.\n"
    )
    assert escape_raw_html(escaped) == escaped
    assert validate_markdown_body(escaped) == []


def test_even_backslashes_do_not_protect_html() -> None:
    assert escape_raw_html("\\\\<b>") == "\\\\&lt;b>"
    assert escape_raw_html("\\\\\\<b>") == "\\\\&lt;b>"


def test_generated_script_is_neutralised_in_the_written_body() -> None:
    draft = _assemble(_result(body="Intro\n\n<SCRIPT src=x></SCRIPT>\n\n<img src=x onerror=alert(1)>\n"))
    assert "<" not in draft.body
    assert draft.body == "Intro\n\n&lt;SCRIPT src=x>&lt;/SCRIPT>\n\n&lt;img src=x onerror=alert(1)>\n"


def test_validator_rejects_script_and_raw_html_with_positions() -> None:
    body = "Line one\nsee <script>x()</script>\n<div>\n"
    assert [(i.field, i.reason) for i in validate_markdown_body(body)] == [
        ("body:2:5", "executable <script> element is not allowed"),
        ("body:2:16", "raw HTML must be escaped as text"),
        ("body:3:1", "raw HTML must be escaped as text"),
    ]


def test_invalid_links_fail_with_line_and_column() -> None:
    body = (
        "# Links\n"
        "ok [a](https://example.com) and [b](/about)\n"
        "bad [c](http://example.com) img ![d](javascript:alert(1))\n"
        "[ref]: ftp://example.com\n"
        "> [quoted]:\n"
        ">   //evil.example\n"
        "auto <http://example.com> mail <user@example.com>\n"
        "split [e](\n"
        "  data:text/html,x)\n"
    )
    with pytest.raises(ArticleValidationError) as exc:
        _assemble(_result(body=body))

    assert _fields(exc) == [
        "body:3:9", "body:3:38", "body:9:3", "body:4:8", "body:6:5", "body:7:7", "body:7:33",
    ]
    assert "javascript" not in str(exc.value) and "evil" not in str(exc.value)


def test_body_empty_and_length_limit() -> None:
    assert [i.field for i in validate_markdown_body(" \n\t")] == ["body"]
    assert validate_markdown_body("x" * 10, max_chars=10) == []
    assert [i.reason for i in validate_markdown_body("x" * 11, max_chars=10)] == ["exceeds 10 characters"]
    with pytest.raises(ArticleValidationError) as exc:
        _assemble(_result(body="x" * 50), max_body_chars=20)
    assert _fields(exc) == ["body"]


def test_escaping_that_grows_the_body_is_counted_against_the_limit() -> None:
    with pytest.raises(ArticleValidationError):
        _assemble(_result(body="<b>" * 5), max_body_chars=16)


# --- writing --------------------------------------------------------------


def test_write_draft_writes_bytes_and_is_idempotent(tmp_path: Path) -> None:
    draft = _assemble()
    target = tmp_path / PATH

    assert write_draft(draft, tmp_path) is True
    assert target.read_bytes() == draft.to_bytes()
    assert write_draft(draft, tmp_path) is False
    assert sorted(p.name for p in target.parent.iterdir()) == [target.name]


def test_failed_validation_writes_nothing(tmp_path: Path) -> None:
    with pytest.raises(ArticleValidationError):
        _assemble(_result(body="[x](http://example.com)"))

    bad_drafts = [
        DraftArticle(PATH, {**_assemble().front_matter, "draft": False}, "Body\n"),
        DraftArticle(PATH, {**_assemble().front_matter, "slug": "Bad"}, "Body\n"),
        DraftArticle(PATH, _assemble().front_matter, "<script>x</script>\n"),
        DraftArticle(f"{CONTENT_ROOT}/../evil.md", _assemble().front_matter, "Body\n"),
    ]
    for draft in bad_drafts:
        with pytest.raises(ArticleValidationError):
            write_draft(draft, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_write_draft_rejects_non_draft_flags(tmp_path: Path) -> None:
    front_matter = {**_assemble().front_matter, "draft": False, "ai_assisted": False}
    with pytest.raises(ArticleValidationError) as exc:
        write_draft(DraftArticle(PATH, front_matter, "Body\n"), tmp_path)
    assert _fields(exc) == ["draft", "ai_assisted"]
