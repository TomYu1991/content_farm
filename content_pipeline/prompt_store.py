"""Versioned Prompt_Store reading ``prompts/*.md`` (Requirement 3.7–3.9).

Each prompt file is Markdown with a YAML front-matter block delimited by
``---`` lines that declares ``name`` (same rules as ``prompt_name``) and
``version`` (``MAJOR.MINOR.PATCH``), followed by a non-empty prompt body.

The store is strict: every ``prompts/*.md`` file must be well formed and every
``(name, version)`` pair must be unique across files, otherwise loading fails
with the offending paths. This keeps prompt resolution unambiguous before any
Model_Gateway call. Error messages contain only paths and identifiers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .errors import PromptStoreError
from .request import is_valid_prompt_name, is_valid_prompt_version

FRONT_MATTER_DELIMITER = "---"


@dataclass(frozen=True)
class Prompt:
    """A resolved prompt: its identity, full front-matter and Markdown body."""

    name: str
    version: str
    body: str
    path: str  # display path, e.g. "prompts/article-draft.md"
    front_matter: dict[str, Any] = field(default_factory=dict, compare=False)


def _split_front_matter(text: str) -> tuple[str, str] | None:
    """Return (yaml_text, body) or None when no delimited front-matter exists."""
    lines = text.split("\n")
    if not lines or lines[0] != FRONT_MATTER_DELIMITER:
        return None
    for index in range(1, len(lines)):
        if lines[index] == FRONT_MATTER_DELIMITER:
            return "\n".join(lines[1:index]), "\n".join(lines[index + 1 :])
    return None


def parse_prompt_text(text: str, display_path: str) -> Prompt:
    """Parse one prompt file's text. Raises PromptStoreError naming the path."""

    def fail(reason: str) -> PromptStoreError:
        return PromptStoreError(f"invalid prompt file {display_path}: {reason}", paths=(display_path,))

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    parts = _split_front_matter(normalized)
    if parts is None:
        raise fail("missing YAML front-matter delimited by '---'")
    yaml_text, body = parts
    try:
        meta = yaml.safe_load(yaml_text)
    except yaml.YAMLError:
        # The parser message may quote file content; report only the path.
        raise fail("front-matter is not valid YAML") from None
    if not isinstance(meta, dict):
        raise fail("front-matter must be a mapping")

    missing = [key for key in ("name", "version") if meta.get(key) in (None, "")]
    if missing:
        raise fail("missing " + ", ".join(missing))
    name, version = meta["name"], meta["version"]
    if not isinstance(name, str) or not is_valid_prompt_name(name):
        raise fail("invalid name")
    if not isinstance(version, str) or not is_valid_prompt_version(version):
        raise fail("invalid version")
    if body.strip() == "":
        raise fail("empty prompt body")

    return Prompt(
        name=name,
        version=version,
        body=body.strip("\n") + "\n",
        path=display_path,
        front_matter=dict(meta),
    )


class PromptStore:
    """Loads and indexes every prompt under a prompts directory."""

    def __init__(self, prompts_dir: Path | str, display_root: Path | str | None = None) -> None:
        self.prompts_dir = Path(prompts_dir)
        self.display_root = Path(display_root) if display_root is not None else self.prompts_dir.parent
        self._index: dict[tuple[str, str], Prompt] | None = None

    def _display(self, path: Path) -> str:
        try:
            return path.relative_to(self.display_root).as_posix()
        except ValueError:
            return path.as_posix()

    def load_all(self) -> dict[tuple[str, str], Prompt]:
        """Parse every ``*.md`` prompt; fail on malformed files or duplicate keys."""
        if self._index is not None:
            return self._index
        if not self.prompts_dir.is_dir():
            shown = self._display(self.prompts_dir)
            raise PromptStoreError(f"prompt directory not found: {shown}", paths=(shown,))

        by_key: dict[tuple[str, str], list[Prompt]] = {}
        for path in sorted(p for p in self.prompts_dir.glob("*.md") if p.is_file()):
            shown = self._display(path)
            try:
                text = path.read_bytes().decode("utf-8-sig")
            except UnicodeDecodeError:
                raise PromptStoreError(
                    f"invalid prompt file {shown}: not valid UTF-8", paths=(shown,)
                ) from None
            prompt = parse_prompt_text(text, shown)
            by_key.setdefault((prompt.name, prompt.version), []).append(prompt)

        conflicts = {key: group for key, group in by_key.items() if len(group) > 1}
        if conflicts:
            paths = tuple(p.path for key in sorted(conflicts) for p in conflicts[key])
            details = "; ".join(
                f"{name}@{version}: " + ", ".join(p.path for p in conflicts[(name, version)])
                for name, version in sorted(conflicts)
            )
            raise PromptStoreError(f"duplicate prompt (name, version): {details}", paths=paths)

        self._index = {key: group[0] for key, group in by_key.items()}
        return self._index

    def get(self, name: str, version: str) -> Prompt:
        """Return the unique prompt for ``(name, version)`` or fail naming the identifier."""
        index = self.load_all()
        prompt = index.get((name, version))
        if prompt is None:
            raise PromptStoreError(
                f"prompt not found: {name}@{version} in {self._display(self.prompts_dir)}"
            )
        return prompt
