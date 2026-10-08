"""Work draft generation: maker's photos + notes -> AI-drafted work text for review.

Flow (``.github/workflows/generate-work-draft.yml``)::

    maker   npm run ingest ... -> commit photos, notes.md, <slug>.md (draft: true)
            -> push work/<slug>
    job 1   generate-work          (contents: read, model secret only)
            reads work/<slug> as data, calls the model once (<= 2 with a retry),
            writes a bundle: manifest.json + work.md
    job 2   apply-work-draft       (contents: write, no model secret)
            re-reads work/<slug>, re-verifies the bundle against it, rewrites
            only src/content/works/<slug>.md; the workflow commits that one
            file to work/<slug> and prints PR instructions.

Photos never travel through the bundle: the maker commits them, so rights,
alt texts and metadata removal stay a human responsibility (review item
``media``), and the review gate re-checks photo metadata on the PR.

``load_work_bundle`` trusts nothing in the bundle: Work_Schema, generated
flags, designated model and Prompt_Version, byte-exact canonical form, every
human-owned field equal to the maker's current file, and a stable key
recomputed from the maker's current notes and facts (so a bundle generated
from older notes cannot be applied).
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import tempfile
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

import httpx
import yaml

from .article import is_slug, normalize_body, resolve_content_path
from .budget import BudgetController, format_cost, resolve_budget_config
from .compliance import ALL_REVIEW_ITEM_LABELS, DEFAULT_POLICY_PATH, CompliancePolicy, load_policy
from .draft_identity import DraftChange, DraftTarget, decide_change, is_stable_key
from .errors import ArticleValidationError, DraftBundleError, FieldIssue, InputValidationError
from .gateway_config import resolve_gateway_config
from .model_gateway import ModelGateway
from .prompt_store import Prompt, PromptStore
from .request import is_valid_prompt_name, is_valid_prompt_version
from .work import (
    HUMAN_KEYS,
    WORKS_ROOT,
    WorkDraft,
    WorkSource,
    assemble_work_draft,
    compute_work_key,
    load_work_source,
    model_input,
    validate_generated_work_flags,
    validate_work,
    work_branch,
    work_path,
)

DEFAULT_PROMPTS_DIR = Path("prompts")

WORK_REQUEST_FIELDS: tuple[str, ...] = ("work_slug", "prompt_name", "prompt_version")
WORK_RESULT_KEYS: tuple[str, ...] = ("description", "tags", "body")

MANIFEST_FILE = "manifest.json"
WORK_FILE = "work.md"
BUNDLE_FORMAT = 1
BUNDLE_KIND = "work"
MAX_WORK_BYTES = 512 * 1024
MAX_MANIFEST_BYTES = 4096

_FENCE = re.compile(r"\A```[A-Za-z0-9_-]*\n(.*)\n```\Z", re.DOTALL)
_CONTENT_FILE = re.compile(rb"---\n(.*?\n)---\n(.*)", re.DOTALL)
_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")

WORK_OUTPUT_CONTRACT = (
    "Return only one JSON object (no prose around it) with these keys:\n"
    '- "description": one or two sentences (plain text) summarising the work\n'
    '- "tags": array of 2-6 short tags (strings) in the notes\' language\n'
    '- "body": CommonMark Markdown without raw HTML describing how the work was made; '
    'links must be absolute HTTPS URLs\n'
    "Use only facts from the input. Do not describe what photos show beyond their captions "
    "and alt texts. A human editor reviews the draft before publishing."
)


# --------------------------------------------------------------------------
# Request
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class WorkRequest:
    work_slug: str
    prompt_name: str
    prompt_version: str


def validate_work_request(inputs: Mapping[str, Any]) -> WorkRequest:
    """Validate the three workflow inputs; names failing fields only."""
    checks = {
        "work_slug": is_slug,
        "prompt_name": is_valid_prompt_name,
        "prompt_version": is_valid_prompt_version,
    }
    issues = []
    for name in WORK_REQUEST_FIELDS:
        value = inputs.get(name)
        if value is None or (isinstance(value, str) and value.strip() == ""):
            issues.append(FieldIssue(name, "missing"))
        elif not isinstance(value, str) or not checks[name](value):
            issues.append(FieldIssue(name, "invalid"))
    if issues:
        raise InputValidationError(issues)
    return WorkRequest(**{name: inputs[name] for name in WORK_REQUEST_FIELDS})


# --------------------------------------------------------------------------
# Model I/O
# --------------------------------------------------------------------------


def build_work_messages(prompt: Prompt, source: WorkSource) -> list[dict[str, str]]:
    facts = json.dumps(model_input(source), ensure_ascii=False, indent=2)
    return [
        {"role": "system", "content": prompt.body},
        {"role": "user", "content": f"Work facts:\n{facts}\n\n{WORK_OUTPUT_CONTRACT}"},
    ]


def parse_work_result(text: str) -> dict[str, Any]:
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
    return {key: data[key] for key in WORK_RESULT_KEYS if key in data}


@dataclass(frozen=True)
class PreparedWork:
    request: WorkRequest
    prompt: Prompt
    gateway: str
    model: str
    draft: WorkDraft
    stable_key: str
    calls_made: int
    estimated_cost: Decimal
    reserved_cost: Decimal

    @property
    def branch(self) -> str:
        return work_branch(self.request.work_slug)

    def audit(self) -> dict[str, str]:
        return {
            "branch": self.branch,
            "stable_key": self.stable_key,
            "path": self.draft.path,
            "prompt": f"{self.prompt.name}@{self.prompt.version}",
            "gateway": self.gateway,
            "model": self.model,
            "estimated_cost": format_cost(self.estimated_cost),
            "reserved_cost": format_cost(self.reserved_cost),
            "calls_made": str(self.calls_made),
        }


def prepare_work_draft(
    inputs: Mapping[str, Any],
    env: Mapping[str, str],
    work_repo: Path | str,
    *,
    policy_path: Path | str = DEFAULT_POLICY_PATH,
    prompts_dir: Path | str = DEFAULT_PROMPTS_DIR,
    transport: httpx.BaseTransport | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> PreparedWork:
    """Every guard runs before the single bounded model call; nothing is written."""
    request = validate_work_request(inputs)
    prompt = PromptStore(prompts_dir).get(request.prompt_name, request.prompt_version)
    policy: CompliancePolicy = load_policy(policy_path)
    config = resolve_gateway_config(env)
    budget = BudgetController(resolve_budget_config(env))
    budget.check()
    source = load_work_source(work_repo, request.work_slug)

    with ModelGateway(policy, config, budget, transport=transport, sleep=sleep, clock=clock) as gateway:
        model = gateway.model

        def validate(text: str) -> WorkDraft:
            return assemble_work_draft(
                source, parse_work_result(text), model=model, prompt_version=request.prompt_version
            )

        result = gateway.generate(build_work_messages(prompt, source), validate)
    return PreparedWork(
        request=request,
        prompt=prompt,
        gateway=gateway.gateway,
        model=model,
        draft=result.value,
        stable_key=compute_work_key(source, request.prompt_version, model),
        calls_made=result.calls_made,
        estimated_cost=result.estimated_cost,
        reserved_cost=result.reserved_cost,
    )


# --------------------------------------------------------------------------
# Bundle
# --------------------------------------------------------------------------


def write_work_bundle(bundle_dir: Path | str, draft: WorkDraft, stable_key: str) -> Path:
    if not is_stable_key(stable_key):
        raise DraftBundleError("stable key must be 64 lowercase hexadecimal characters")
    slug = draft.front_matter.get("slug")
    issues = [
        *validate_work(draft.path, draft.front_matter, draft.body, allow_placeholders=True),
        *validate_generated_work_flags(draft.front_matter),
    ]
    if issues:
        raise ArticleValidationError(issues)
    manifest = json.dumps({"format": BUNDLE_FORMAT, "kind": BUNDLE_KIND, "stable_key": stable_key, "slug": slug})
    directory = Path(bundle_dir)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / WORK_FILE).write_bytes(draft.to_bytes())
    (directory / MANIFEST_FILE).write_bytes((manifest + "\n").encode("utf-8"))
    return directory


def generate_work_bundle(
    inputs: Mapping[str, Any], env: Mapping[str, str], work_repo: Path | str, bundle_dir: Path | str, **options: Any
) -> PreparedWork:
    prepared = prepare_work_draft(inputs, env, work_repo, **options)
    write_work_bundle(bundle_dir, prepared.draft, prepared.stable_key)
    return prepared


def _read_limited(path: Path, limit: int, name: str) -> bytes:
    try:
        with path.open("rb") as handle:
            data = handle.read(limit + 1)
    except FileNotFoundError:
        raise DraftBundleError(f"work bundle is missing {name}") from None
    if len(data) > limit:
        raise DraftBundleError(f"{name} exceeds {limit} bytes")
    return data


@dataclass(frozen=True)
class VerifiedWork:
    stable_key: str
    slug: str
    branch: str
    path: str
    front_matter: Mapping[str, Any]
    body: str
    content: bytes


def _parse_bundle_file(data: bytes) -> tuple[Any, str]:
    if data.startswith(b"\xef\xbb\xbf") or b"\r" in data:
        raise DraftBundleError(f"{WORK_FILE} must be UTF-8 without BOM and use LF line endings")
    match = _CONTENT_FILE.fullmatch(data)
    if match is None:
        raise DraftBundleError(f"{WORK_FILE} must start with '---' delimited front-matter")
    try:
        yaml_text, body = match.group(1).decode("utf-8"), match.group(2).decode("utf-8")
    except UnicodeDecodeError:
        raise DraftBundleError(f"{WORK_FILE} is not valid UTF-8") from None
    try:
        return yaml.safe_load(yaml_text), body
    except yaml.YAMLError:
        raise DraftBundleError(f"{WORK_FILE} front-matter is not valid YAML") from None


def load_work_bundle(
    bundle_dir: Path | str, request: WorkRequest, policy: CompliancePolicy, source: WorkSource
) -> VerifiedWork:
    """Re-validate a work bundle against the request, the checklist and the maker's files."""
    directory = Path(bundle_dir)
    raw = _read_limited(directory / MANIFEST_FILE, MAX_MANIFEST_BYTES, MANIFEST_FILE)
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise DraftBundleError(f"{MANIFEST_FILE} is not valid UTF-8 JSON") from None
    if (
        not isinstance(manifest, dict)
        or manifest.get("format") != BUNDLE_FORMAT
        or manifest.get("kind") != BUNDLE_KIND
    ):
        raise DraftBundleError(f"{MANIFEST_FILE} has an unsupported format")
    key = manifest.get("stable_key")
    if not is_stable_key(key):
        raise DraftBundleError(f"{MANIFEST_FILE}: stable_key must be 64 lowercase hexadecimal characters")
    slug = request.work_slug
    if manifest.get("slug") != slug or source.slug != slug:
        raise DraftBundleError(f"{MANIFEST_FILE}: slug does not match the requested work")

    data = _read_limited(directory / WORK_FILE, MAX_WORK_BYTES, WORK_FILE)
    front_matter, body = _parse_bundle_file(data)
    path = work_path(slug)
    issues = [
        *validate_work(path, front_matter, body, allow_placeholders=True),
        *validate_generated_work_flags(front_matter),
    ]
    if body.strip() == "":
        issues.append(FieldIssue("body", "must not be empty"))
    if issues:
        raise ArticleValidationError(issues)
    if front_matter["prompt_version"] != request.prompt_version:
        raise ArticleValidationError([FieldIssue("prompt_version", "must equal the requested prompt_version")])
    policy.require_designated_model(front_matter["model"])

    human = {k: front_matter[k] for k in HUMAN_KEYS if k in front_matter}
    if human != source.human_fields():
        changed = sorted(k for k in set(human) | set(source.human_fields()) if human.get(k) != source.human_fields().get(k))
        raise DraftBundleError("human-owned fields differ from the work branch: " + ", ".join(changed))
    if compute_work_key(source, request.prompt_version, front_matter["model"]) != key:
        raise DraftBundleError("stable_key does not match the work branch notes, facts and model")
    if normalize_body(body) != body:
        raise DraftBundleError(f"{WORK_FILE} body is not in normalised Markdown_Body form")
    if WorkDraft(path, front_matter, body).to_bytes() != data:
        raise DraftBundleError(f"{WORK_FILE} is not in canonical Content_File form")

    return VerifiedWork(
        stable_key=key, slug=slug, branch=work_branch(slug), path=path,
        front_matter=front_matter, body=body, content=data,
    )


# --------------------------------------------------------------------------
# Applying to the work branch work tree
# --------------------------------------------------------------------------


def apply_work_draft(verified: VerifiedWork, repo_root: Path | str, *, branch: str, default_branch: str) -> DraftChange:
    """Rewrite ``src/content/works/<slug>.md`` in a checkout of ``work/<slug>``.

    Identical bytes are left untouched (no commit needed). No other file is
    written; the workflow's guarded step refuses to commit anything else.
    """
    if branch != verified.branch:
        raise DraftBundleError("target branch does not match work/<slug>")
    if not default_branch or branch == default_branch:
        raise DraftBundleError("refusing to write to the Default_Branch")
    target = resolve_content_path(repo_root, verified.path, WORKS_ROOT)
    try:
        existing: bytes | None = target.read_bytes()
    except FileNotFoundError:
        existing = None
    action = decide_change(verified.content, existing)
    if action.requires_commit:
        fd, temp_name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(verified.content)
            os.chmod(temp_name, 0o644)
            os.replace(temp_name, target)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(temp_name)
            raise
    return DraftChange(target=DraftTarget(key=verified.stable_key, branch=branch, path=verified.path), action=action)


def work_pr_instructions(change: DraftChange, *, server_url: str, repository: str, default_branch: str) -> str:
    """Compare URL and the six review items; no work text is included."""
    parts = urlsplit(server_url)
    if parts.scheme != "https" or not parts.hostname or parts.path not in ("", "/"):
        raise DraftBundleError("server URL must be an absolute HTTPS origin")
    if _REPOSITORY.fullmatch(repository) is None:
        raise DraftBundleError("repository must be <owner>/<name>")
    if not default_branch or default_branch == change.target.branch:
        raise DraftBundleError("refusing to target the Default_Branch")
    compare = (
        f"{server_url.rstrip('/')}/{repository}/compare/"
        f"{quote(default_branch, safe='/')}...{change.target.branch}?expand=1"
    )
    review = "\n".join(f"   - [ ] {label}（`{item}`）" for item, label in ALL_REVIEW_ITEM_LABELS.items())
    status = {
        "create": "已创建作品文件",
        "update": "已写入 AI 起草的作品文字",
        "unchanged": "作品文件内容未变化，未创建新提交",
    }[change.action.value]
    return (
        "## 作品草稿已就绪，等待人工审阅\n\n"
        f"- 状态：{status}\n"
        f"- 作品分支：`{change.target.branch}`\n"
        f"- 作品文件：`{change.target.path}`\n\n"
        "### 创建 Pull Request\n\n"
        f"1. 打开 {compare}\n"
        "   （若该分支已有打开的 Pull Request，直接在其中审阅。）\n"
        "2. 对照 notes.md 核对 AI 写的简介、标签和正文；补全所有“待填写”的替代文本。\n"
        "3. 在 Pull Request 中逐项审阅并保留记录：\n"
        f"{review}\n"
        "4. 六项审阅完成后，由编辑人员手动将 `draft: true` 改为 `draft: false`，再由人工合并。\n\n"
        "本工作流不会批准、合并或发布任何内容。\n"
    )


__all__ = [
    "PreparedWork",
    "VerifiedWork",
    "WorkRequest",
    "apply_work_draft",
    "build_work_messages",
    "generate_work_bundle",
    "load_work_bundle",
    "parse_work_result",
    "prepare_work_draft",
    "validate_work_request",
    "work_pr_instructions",
    "write_work_bundle",
]
