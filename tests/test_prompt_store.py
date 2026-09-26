"""Unit tests for the versioned Prompt_Store (Requirements 3.7–3.9)."""

from pathlib import Path

import pytest

from content_pipeline.errors import PromptStoreError
from content_pipeline.prompt_store import PromptStore


def _write(directory: Path, filename: str, text: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / filename).write_bytes(text.encode("utf-8"))


def _prompt(name: str = "article-draft", version: str = "1.0.0", body: str = "Write about {topic}.\n") -> str:
    return f"---\nname: {name}\nversion: \"{version}\"\ndescription: test\n---\n{body}"


@pytest.fixture
def prompts(tmp_path: Path) -> Path:
    return tmp_path / "prompts"


def test_resolves_unique_prompt_with_front_matter_and_body(prompts: Path) -> None:
    _write(prompts, "draft-v1.md", _prompt(version="1.0.0", body="Body one.\n"))
    _write(prompts, "draft-v2.md", _prompt(version="2.0.0", body="Body two.\n"))
    _write(prompts, "notes.txt", "ignored")

    prompt = PromptStore(prompts).get("article-draft", "2.0.0")

    assert prompt.body == "Body two.\n"
    assert prompt.path == "prompts/draft-v2.md"
    assert prompt.front_matter["description"] == "test"


def test_unquoted_version_and_crlf_are_accepted(prompts: Path) -> None:
    _write(prompts, "a.md", "---\r\nname: article-draft\r\nversion: 1.2.3\r\n---\r\nBody\r\n")
    assert PromptStore(prompts).get("article-draft", "1.2.3").body == "Body\n"


def test_nonexistent_prompt_names_selected_identifier(prompts: Path) -> None:
    _write(prompts, "a.md", _prompt())
    with pytest.raises(PromptStoreError, match=r"article-draft@9\.9\.9"):
        PromptStore(prompts).get("article-draft", "9.9.9")


def test_missing_prompt_directory_names_path(tmp_path: Path) -> None:
    with pytest.raises(PromptStoreError, match="prompts"):
        PromptStore(tmp_path / "prompts").get("article-draft", "1.0.0")


@pytest.mark.parametrize(
    "text,reason",
    [
        ("---\nversion: 1.0.0\n---\nBody\n", "missing name"),
        ("---\nname: article-draft\n---\nBody\n", "missing version"),
        ("---\nname: Article_Draft\nversion: 1.0.0\n---\nBody\n", "invalid name"),
        ("---\nname: article-draft\nversion: 1.0\n---\nBody\n", "invalid version"),
        ("---\nname: article-draft\nversion: 1.0.0\n---\n  \n", "empty prompt body"),
        ("name: article-draft\nversion: 1.0.0\nBody\n", "missing YAML front-matter"),
        ("---\nname: article-draft\nversion: 1.0.0\nBody\n", "missing YAML front-matter"),
        ("---\nname: [unclosed\n---\nBody\n", "not valid YAML"),
        ("---\n- a\n- b\n---\nBody\n", "must be a mapping"),
    ],
)
def test_malformed_prompt_fails_with_path(prompts: Path, text: str, reason: str) -> None:
    _write(prompts, "broken.md", text)
    with pytest.raises(PromptStoreError) as exc:
        PromptStore(prompts).get("article-draft", "1.0.0")
    assert exc.value.paths == ("prompts/broken.md",)
    assert "prompts/broken.md" in str(exc.value)
    assert reason in str(exc.value)


def test_invalid_utf8_fails_with_path(prompts: Path) -> None:
    prompts.mkdir()
    (prompts / "bad.md").write_bytes(b"---\nname: a\nversion: 1.0.0\n---\n\xff\n")
    with pytest.raises(PromptStoreError, match="prompts/bad.md"):
        PromptStore(prompts).load_all()


def test_duplicate_name_version_lists_conflicting_paths(prompts: Path) -> None:
    _write(prompts, "a.md", _prompt(body="A\n"))
    _write(prompts, "b.md", _prompt(body="B\n"))
    _write(prompts, "c.md", _prompt(version="1.0.1"))

    with pytest.raises(PromptStoreError) as exc:
        PromptStore(prompts).get("article-draft", "1.0.1")

    assert exc.value.paths == ("prompts/a.md", "prompts/b.md")
    assert "prompts/a.md" in str(exc.value) and "prompts/b.md" in str(exc.value)
