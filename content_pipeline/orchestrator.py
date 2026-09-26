"""Generation orchestration: the one ordered path from inputs to a reviewable draft.

Requirements 3.1–3.13, 4.1–4.12, 5.1–5.11, 6.1–6.12, 7.1, 7.6, 9.2–9.6.
Every step reuses the existing component; nothing is re-implemented here.

Phase 1 — :func:`prepare_draft` (workflow job ``generate``; model secret only):

1. validate the five inputs (:func:`request.validate_request`);
2. resolve the versioned prompt (:class:`prompt_store.PromptStore`);
3. load the Compliance_Checklist and the single gateway / model / credential
   configuration, checking it against the checklist and its endpoint;
4. resolve the budget configuration and check the caps (zero calls if blocked);
5. call the Model_Gateway (at most two calls; only network errors retried);
6. parse the result and assemble + validate the draft (``draft: true``,
   ``ai_assisted: true``, designated model, selected Prompt_Version), and only
   then compute the stable key and target path.

Any failure raises a :class:`errors.PipelineError` naming fields, identifiers
or configuration keys; nothing is written and no Git change is possible.

Phase 2 — :func:`publish_review` (workflow job ``draft-branch``; no secret):
apply a *verified* draft to ``draft/<stable_key>`` through a
:class:`git_change.GitBackend` (never the Default_Branch; identical bytes need
no commit) and return a Pull Request URL or PR creation instructions.

:func:`run_generation` chains both phases through the same bundle hand-off the
workflow uses, for single-process runs against any backend (e.g. the
in-memory fake). Nothing here publishes, merges or approves.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx

from .article import MSG_REQUIRED, MSG_SLUG, DraftArticle, assemble_draft, is_slug
from .budget import BudgetController, format_cost, resolve_budget_config
from .compliance import DEFAULT_POLICY_PATH, CompliancePolicy, load_policy
from .draft_bundle import VerifiedDraft, load_bundle, pr_instructions, write_bundle
from .draft_identity import DraftChange, draft_branch, draft_path, stable_key_for
from .errors import ArticleValidationError, FieldIssue, PipelineError
from .gateway_config import CREDENTIAL_ENV, redact, resolve_gateway_config
from .git_change import GitBackend, apply_verified_draft
from .model_gateway import ModelGateway
from .prompt_store import Prompt, PromptStore
from .request import GenerationRequest, validate_request

DEFAULT_PROMPTS_DIR = Path("prompts")

# Keys the model is asked to return; anything else is dropped by assemble_draft.
RESULT_KEYS: tuple[str, ...] = ("title", "description", "slug", "tags", "body", "sources", "updatedDate")

_FENCE = re.compile(r"\A```[A-Za-z0-9_-]*\n(.*)\n```\Z", re.DOTALL)

OUTPUT_CONTRACT = (
    "Return only one JSON object (no prose around it) with these keys:\n"
    '- "title": non-empty string\n'
    '- "description": non-empty string\n'
    '- "slug": lowercase ASCII letters, digits and single hyphens, 1-80 characters\n'
    '- "tags": array of strings\n'
    '- "body": CommonMark Markdown without raw HTML; links must be absolute HTTPS URLs '
    'or site paths starting with "/"\n'
    '- "sources": array (may be empty) of objects with "title", HTTPS "url" and '
    '"accessedDate" formatted YYYY-MM-DDTHH:mm:ssZ; list only sources you are sure exist\n'
    "The article is a draft that a human editor reviews before publishing."
)


@dataclass(frozen=True)
class PreparedDraft:
    """A validated draft plus redaction-safe audit figures (no secrets, no text)."""

    request: GenerationRequest
    prompt: Prompt
    gateway: str
    model: str
    article: DraftArticle
    stable_key: str
    calls_made: int
    estimated_cost: Decimal
    reserved_cost: Decimal

    @property
    def branch(self) -> str:
        return draft_branch(self.stable_key)

    def audit(self) -> dict[str, str]:
        """Single-line, non-secret values for logs and ``$GITHUB_OUTPUT``."""
        return {
            "branch": self.branch,
            "stable_key": self.stable_key,
            "path": self.article.path,
            "prompt": f"{self.prompt.name}@{self.prompt.version}",
            "gateway": self.gateway,
            "model": self.model,
            "estimated_cost": format_cost(self.estimated_cost),
            "reserved_cost": format_cost(self.reserved_cost),
            "calls_made": str(self.calls_made),
        }


@dataclass(frozen=True)
class ReviewResult:
    """Outcome of the Git phase: the change plus a PR URL and/or instructions."""

    change: DraftChange
    pr_url: str | None
    instructions: str


# --------------------------------------------------------------------------
# Model I/O
# --------------------------------------------------------------------------


def build_messages(prompt: Prompt, request: GenerationRequest) -> list[dict[str, str]]:
    """System = versioned prompt body; user = inputs as JSON + output contract."""
    inputs = json.dumps(
        {"topic": request.topic, "audience": request.audience, "keywords": request.keywords},
        ensure_ascii=False,
        indent=2,
    )
    return [
        {"role": "system", "content": prompt.body},
        {"role": "user", "content": f"Inputs:\n{inputs}\n\n{OUTPUT_CONTRACT}"},
    ]


def parse_model_result(text: str) -> dict[str, Any]:
    """Parse the model's JSON object (an optional single code fence is allowed).

    Raises ArticleValidationError naming ``result`` only; the text is not echoed.
    """
    stripped = text.strip()
    fenced = _FENCE.fullmatch(stripped)
    if fenced is not None:
        stripped = fenced.group(1).strip()
    try:
        data = json.loads(stripped)
    except ValueError:
        data = None
    if not isinstance(data, dict):
        raise ArticleValidationError([FieldIssue("result", "must be a single JSON object")])
    return {key: data[key] for key in RESULT_KEYS if key in data}


def _draft_validator(
    request: GenerationRequest, model: str, clock: Callable[[], datetime]
) -> Callable[[str], tuple[DraftArticle, str]]:
    def validate(text: str) -> tuple[DraftArticle, str]:
        result = parse_model_result(text)
        slug = result.get("slug")
        if not is_slug(slug):
            reason = MSG_REQUIRED if slug is None else MSG_SLUG
            raise ArticleValidationError([FieldIssue("slug", reason)])
        # Stable key and target path are computed only for a parsed result.
        key = stable_key_for(request, model)
        article = assemble_draft(
            result,
            model=model,
            prompt_version=request.prompt_version,
            pub_date=clock(),
            path=draft_path(key, slug),
        )
        return article, key

    return validate


# --------------------------------------------------------------------------
# Phase 1: inputs -> validated draft
# --------------------------------------------------------------------------


def prepare_draft(
    inputs: Mapping[str, Any],
    env: Mapping[str, str],
    *,
    policy_path: Path | str = DEFAULT_POLICY_PATH,
    prompts_dir: Path | str = DEFAULT_PROMPTS_DIR,
    transport: httpx.BaseTransport | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> PreparedDraft:
    """Run every pre-call guard, the bounded model call and draft validation."""
    request = validate_request(inputs)
    prompt = PromptStore(prompts_dir).get(request.prompt_name, request.prompt_version)
    policy: CompliancePolicy = load_policy(policy_path)
    config = resolve_gateway_config(env)
    budget = BudgetController(resolve_budget_config(env))
    budget.check()  # blocked budgets end the run with zero model calls

    with ModelGateway(policy, config, budget, transport=transport, sleep=sleep, clock=clock) as gateway:
        result = gateway.generate(
            build_messages(prompt, request), _draft_validator(request, gateway.model, clock)
        )
    article, key = result.value
    return PreparedDraft(
        request=request,
        prompt=prompt,
        gateway=gateway.gateway,
        model=gateway.model,
        article=article,
        stable_key=key,
        calls_made=result.calls_made,
        estimated_cost=result.estimated_cost,
        reserved_cost=result.reserved_cost,
    )


def generate_bundle(
    inputs: Mapping[str, Any],
    env: Mapping[str, str],
    bundle_dir: Path | str,
    **options: Any,
) -> PreparedDraft:
    """Phase 1 plus the bundle hand-off; a failing run leaves no bundle."""
    prepared = prepare_draft(inputs, env, **options)
    write_bundle(bundle_dir, prepared.article, prepared.stable_key)
    return prepared


# --------------------------------------------------------------------------
# Phase 2: verified draft -> draft branch + review output
# --------------------------------------------------------------------------


def publish_review(
    draft: VerifiedDraft,
    backend: GitBackend,
    *,
    default_branch: str,
    server_url: str,
    repository: str,
    branch: str | None = None,
) -> ReviewResult:
    """Apply the draft on ``draft/<stable_key>`` and produce the review hand-off."""
    change = apply_verified_draft(
        draft, backend, branch=draft.branch if branch is None else branch, default_branch=default_branch
    )
    instructions = pr_instructions(
        change, server_url=server_url, repository=repository, default_branch=default_branch
    )
    try:
        url = backend.pull_request_url(change.target.branch, default_branch)
    except PipelineError:
        url = None  # fall back to the creation instructions
    if url is not None and not url.startswith("https://"):
        url = None
    return ReviewResult(change=change, pr_url=url, instructions=instructions)


def run_generation(
    inputs: Mapping[str, Any],
    env: Mapping[str, str],
    backend: GitBackend,
    *,
    bundle_dir: Path | str,
    default_branch: str,
    server_url: str,
    repository: str,
    policy_path: Path | str = DEFAULT_POLICY_PATH,
    **options: Any,
) -> tuple[PreparedDraft, ReviewResult]:
    """Both phases in one process, through the same bundle re-verification."""
    prepared = generate_bundle(inputs, env, bundle_dir, policy_path=policy_path, **options)
    verified = load_bundle(bundle_dir, prepared.request, load_policy(policy_path))
    review = publish_review(
        verified, backend, default_branch=default_branch, server_url=server_url, repository=repository
    )
    return prepared, review


def redact_env_secrets(text: str, env: Mapping[str, str]) -> str:
    """Last-line defence: mask the gateway credential in any output text."""
    return redact(text, [env.get(CREDENTIAL_ENV) or ""])


__all__ = [
    "PreparedDraft",
    "ReviewResult",
    "build_messages",
    "generate_bundle",
    "parse_model_result",
    "prepare_draft",
    "publish_review",
    "redact_env_secrets",
    "run_generation",
]
