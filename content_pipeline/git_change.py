"""Git_Change_Manager behind a replaceable backend interface (Requirements 5.2–5.10).

:func:`apply_verified_draft` is the single place that turns a verified draft
into a change on ``draft/<stable_key>``. It refuses the Default_Branch and any
branch other than the draft's own, reuses an existing file carrying the key's
12-character suffix (Requirement 5.4) and leaves identical bytes untouched so
no commit is needed (Requirement 5.5).

Backends implement :class:`GitBackend`:

* :class:`WorkTreeBackend` — a work tree already checked out at the draft
  branch (the workflow's ``draft-branch`` job). It only writes the file; the
  workflow's guarded shell step commits and pushes that branch.
* :class:`InMemoryGitBackend` — a dependency-free fake that records commits,
  for tests of the generation orchestration.

No network access happens here and no backend can merge, approve or publish.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from .article import CONTENT_ROOT, DraftArticle, write_draft
from .draft_identity import KEY_PREFIX_LENGTH, DraftChange, draft_path, plan_draft_change
from .errors import DraftBundleError

if TYPE_CHECKING:  # pragma: no cover - annotations only (avoids an import cycle)
    from .draft_bundle import VerifiedDraft


def is_draft_candidate(path: str, key: str, slug: str) -> bool:
    """True if repo-relative ``path`` may hold the draft for ``key``.

    Candidates sit directly in the content root and either carry the key's
    12-character suffix or are exactly the fresh ``<slug>-<key[:12]>.md`` name.
    """
    directory, _, name = path.rpartition("/")
    if directory != CONTENT_ROOT:
        return False
    fresh = draft_path(key, slug).rsplit("/", 1)[-1]
    return name.endswith(f"-{key[:KEY_PREFIX_LENGTH]}.md") or name == fresh


class GitBackend(Protocol):
    """Operations the Git_Change_Manager needs from a repository host."""

    def draft_files(self, branch: str, key: str, slug: str) -> Mapping[str, bytes]:
        """Candidate Content_Files on ``branch`` (empty if the branch is new)."""
        ...

    def write_draft_file(self, branch: str, article: DraftArticle) -> None:
        """Record the Content_File change on ``branch`` (never the Default_Branch)."""
        ...

    def pull_request_url(self, branch: str, base: str) -> str | None:
        """URL of a review Pull Request for ``branch``, or ``None`` if unavailable.

        ``None`` (or a raised ``PipelineError``) makes the caller fall back to
        Pull Request creation instructions (Requirement 5.11).
        """
        ...


def apply_verified_draft(
    draft: VerifiedDraft,
    backend: GitBackend,
    *,
    branch: str,
    default_branch: str,
) -> DraftChange:
    """Create, update or keep the draft's Content_File on ``draft/<stable_key>``."""
    if branch != draft.branch:
        raise DraftBundleError("target branch does not match draft/<stable_key>")
    if not default_branch or branch == default_branch:
        raise DraftBundleError("refusing to write to the Default_Branch")

    existing = backend.draft_files(branch, draft.stable_key, draft.slug)
    change = plan_draft_change(draft.stable_key, draft.slug, draft.content, existing)
    if change.requires_commit:
        article = DraftArticle(
            path=change.target.path, front_matter=draft.front_matter, body=draft.body
        )
        backend.write_draft_file(branch, article)
    return change


class WorkTreeBackend:
    """Work tree already checked out at the draft branch; writes files only."""

    def __init__(self, repo_root: Path | str) -> None:
        self.repo = Path(repo_root)

    def draft_files(self, branch: str, key: str, slug: str) -> dict[str, bytes]:
        root = self.repo / CONTENT_ROOT
        if not root.is_dir():
            return {}
        files: dict[str, bytes] = {}
        for entry in root.iterdir():
            path = f"{CONTENT_ROOT}/{entry.name}"
            if entry.is_file() and not entry.is_symlink() and is_draft_candidate(path, key, slug):
                files[path] = entry.read_bytes()
        return files

    def write_draft_file(self, branch: str, article: DraftArticle) -> None:
        # write_draft re-validates the article and the resolved path first.
        write_draft(article, self.repo)

    def pull_request_url(self, branch: str, base: str) -> str | None:
        return None  # the workflow holds no pull-requests permission


@dataclass(frozen=True)
class Commit:
    branch: str
    path: str
    content: bytes


@dataclass
class InMemoryGitBackend:
    """In-memory repository fake: ``branches`` maps branch -> {path: bytes}."""

    default_branch: str = "main"
    branches: dict[str, dict[str, bytes]] = field(default_factory=dict)
    commits: list[Commit] = field(default_factory=list)
    pr_url: str | None = None

    def _files(self, branch: str) -> dict[str, bytes]:
        # A branch that does not exist yet starts from the Default_Branch.
        return self.branches.get(branch, self.branches.get(self.default_branch, {}))

    def draft_files(self, branch: str, key: str, slug: str) -> dict[str, bytes]:
        return {
            path: data
            for path, data in self._files(branch).items()
            if is_draft_candidate(path, key, slug)
        }

    def write_draft_file(self, branch: str, article: DraftArticle) -> None:
        if branch == self.default_branch:
            raise DraftBundleError("refusing to write to the Default_Branch")
        data = article.to_bytes()
        files = self.branches.setdefault(branch, dict(self._files(branch)))
        files[article.path] = data
        self.commits.append(Commit(branch=branch, path=article.path, content=data))

    def pull_request_url(self, branch: str, base: str) -> str | None:
        return self.pr_url


__all__ = [
    "Commit",
    "GitBackend",
    "InMemoryGitBackend",
    "WorkTreeBackend",
    "apply_verified_draft",
    "is_draft_candidate",
]
