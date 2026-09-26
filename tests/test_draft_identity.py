"""Unit tests for stable draft identity and idempotent change decisions (Requirements 5.1–5.6)."""

import hashlib

import pytest

from content_pipeline.article import FILENAME_PATTERN, validate_content_path
from content_pipeline.draft_identity import (
    KEY_SEPARATOR,
    ChangeAction,
    compute_stable_key,
    decide_change,
    draft_branch,
    draft_path,
    normalize_key_text,
    plan_draft_change,
    plan_draft_target,
    stable_key_for,
)
from content_pipeline.errors import ArticleValidationError
from content_pipeline.request import GenerationRequest

BASE = {
    "topic": "静态博客入门",
    "audience": "独立开发者",
    "keywords": "astro, markdown",
    "prompt_version": "1.0.0",
    "model": "openai/gpt-4o-mini",
}
KEY = compute_stable_key(**BASE)


def _key(**overrides):
    return compute_stable_key(**{**BASE, **overrides})


def test_key_is_sha256_over_separator_joined_fields() -> None:
    material = KEY_SEPARATOR.join(
        BASE[f] for f in ("topic", "audience", "keywords", "prompt_version", "model")
    )
    assert KEY == hashlib.sha256(material.encode("utf-8")).hexdigest()
    assert len(KEY) == 64 and KEY == KEY.lower()


def test_normalization_nfc_strip_and_collapse() -> None:
    assert normalize_key_text("  Cafe\u0301 \t\n  au\u3000lait  ") == "Café au lait"
    # The separator is whitespace, so it can never survive inside a field.
    assert KEY_SEPARATOR.isspace()
    assert normalize_key_text(f"a{KEY_SEPARATOR}b") == "a b"


def test_equivalent_inputs_give_same_key() -> None:
    assert _key(topic="\u3000 静态博客入门 \n") == KEY
    assert _key(keywords="  astro,\n\t markdown ") == KEY
    decomposed = compute_stable_key(**{**BASE, "topic": "Cafe\u0301  bar"})
    assert decomposed == compute_stable_key(**{**BASE, "topic": "Café bar"})


def test_field_boundaries_are_unambiguous() -> None:
    # Moving text between adjacent fields must change the key.
    assert _key(topic="ab", audience="c") != _key(topic="a", audience="bc")
    assert _key(topic="a b", audience="c") != _key(topic="a", audience="b c")


@pytest.mark.parametrize("field", ["prompt_version", "model"])
def test_version_or_model_change_gives_independent_target(field) -> None:
    other = _key(**{field: "1.0.1" if field == "prompt_version" else "openai/gpt-4o"})
    assert other != KEY
    assert draft_branch(other) != draft_branch(KEY)
    assert draft_path(other, "my-post") != draft_path(KEY, "my-post")


def test_empty_normalized_field_is_rejected_without_echo() -> None:
    with pytest.raises(ValueError, match="model") as exc:
        _key(model=" \t ")
    assert "gpt" not in str(exc.value)


def test_stable_key_for_request_matches_fields() -> None:
    request = GenerationRequest(
        topic=BASE["topic"],
        audience=BASE["audience"],
        keywords=BASE["keywords"],
        prompt_name="article-draft",
        prompt_version=BASE["prompt_version"],
    )
    assert stable_key_for(request, BASE["model"]) == KEY


def test_branch_and_path_format() -> None:
    assert draft_branch(KEY) == f"draft/{KEY}"
    path = draft_path(KEY, "my-post")
    assert path == f"src/content/articles/my-post-{KEY[:12]}.md"
    assert validate_content_path(path) == []


def test_max_length_slug_still_satisfies_filename_rule() -> None:
    path = draft_path(KEY, "a" * 80)
    assert FILENAME_PATTERN.fullmatch(path.rsplit("/", 1)[-1])
    assert validate_content_path(path) == []


@pytest.mark.parametrize("slug", ["", "Bad", "a--b", "../x", "a" * 81])
def test_invalid_slug_rejected(slug) -> None:
    with pytest.raises(ArticleValidationError) as exc:
        draft_path(KEY, slug)
    assert exc.value.fields == ("slug",)


@pytest.mark.parametrize("key", ["", "abc", KEY.upper(), KEY[:-1] + "g", KEY + "0"])
def test_invalid_key_rejected(key) -> None:
    with pytest.raises(ValueError):
        draft_branch(key)


def test_same_key_selects_same_target() -> None:
    assert plan_draft_target(KEY, "my-post") == plan_draft_target(KEY, "my-post")


def test_rerun_with_new_slug_reuses_existing_file() -> None:
    existing = draft_path(KEY, "first-slug")
    other_key_file = draft_path(_key(model="other/model"), "first-slug")
    target = plan_draft_target(KEY, "second-slug", [other_key_file, existing, "README.md"])
    assert target.path == existing
    assert target.branch == f"draft/{KEY}"


def test_decide_change_by_exact_bytes() -> None:
    assert decide_change(b"a\n", None) is ChangeAction.CREATE
    assert decide_change(b"a\n", b"a\n") is ChangeAction.UNCHANGED
    assert decide_change(b"a\n", b"a\r\n") is ChangeAction.UPDATE
    assert not ChangeAction.UNCHANGED.requires_commit
    assert ChangeAction.CREATE.requires_commit and ChangeAction.UPDATE.requires_commit


def test_plan_draft_change_is_idempotent() -> None:
    content = b"---\ntitle: x\n---\nbody\n"
    first = plan_draft_change(KEY, "my-post", content)
    assert first.action is ChangeAction.CREATE and first.requires_commit

    files = {first.target.path: content}
    again = plan_draft_change(KEY, "my-post", content, files)
    assert again.target == first.target
    assert again.action is ChangeAction.UNCHANGED and not again.requires_commit

    changed = plan_draft_change(KEY, "renamed-post", content + b"more\n", files)
    assert changed.target.path == first.target.path
    assert changed.action is ChangeAction.UPDATE
