"""Work drafts: Work_Schema mirror, maker sources, bundle hand-off, CLI and workflow.

No real network: the gateway uses an ``httpx.MockTransport``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

from content_pipeline import cli
from content_pipeline.article import render_content_file
from content_pipeline.compliance import load_policy
from content_pipeline.draft_identity import ChangeAction
from content_pipeline.errors import ArticleValidationError, DraftBundleError, InputValidationError
from content_pipeline.work import (
    CATEGORIES,
    WorkSourceError,
    compute_work_key,
    load_work_source,
    model_input,
    validate_work_front_matter,
)
from content_pipeline.work_pipeline import (
    MANIFEST_FILE,
    WORK_FILE,
    WorkRequest,
    apply_work_draft,
    generate_work_bundle,
    load_work_bundle,
    validate_work_request,
    work_pr_instructions,
)

from datetime import datetime, timezone

from content_pipeline.budget import (
    INPUT_PRICE_ENV,
    MAX_COST_PER_ARTICLE_ENV,
    MAX_COST_PER_RUN_ENV,
    MAX_INPUT_TOKENS_ENV,
    MAX_OUTPUT_TOKENS_ENV,
    OUTPUT_PRICE_ENV,
)
from content_pipeline.gateway_config import BASE_URL_ENV, CREDENTIAL_ENV, GATEWAY_ENV, MODEL_ENV

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "docs" / "compliance.md"
PROMPTS_DIR = ROOT / "prompts"
POLICY = load_policy(POLICY_PATH)
SECRET = "sk-work-test-0123456789"
NOW = datetime(2026, 9, 30, 9, 30, 0, tzinfo=timezone.utc)
ENV = {
    GATEWAY_ENV: POLICY.gateway,
    MODEL_ENV: POLICY.model,
    BASE_URL_ENV: POLICY.model_endpoint,
    CREDENTIAL_ENV: SECRET,
    INPUT_PRICE_ENV: "0.15",
    OUTPUT_PRICE_ENV: "0.60",
    MAX_INPUT_TOKENS_ENV: "4000",
    MAX_OUTPUT_TOKENS_ENV: "2000",
    MAX_COST_PER_ARTICLE_ENV: "0.01",
    MAX_COST_PER_RUN_ENV: "0.02",
}
SLUG = "tote-bag"
MD = f"src/content/works/{SLUG}.md"
NOTES = f"src/assets/works/{SLUG}/notes.md"
INPUTS = {"work_slug": SLUG, "prompt_name": "work-draft", "prompt_version": "1.0.0"}
REQUEST = WorkRequest(**INPUTS)
CLI_ENV = {**ENV, **{cli.WORK_INPUT_ENV[k]: v for k, v in INPUTS.items()}}


def _skeleton(**overrides: Any) -> dict[str, Any]:
    fm: dict[str, Any] = {
        "title": "帆布托特包",
        "description": "待填写",
        "pubDate": "2026-09-30T02:28:05Z",
        "slug": SLUG,
        "draft": True,
        "category": "sewing",
        "tags": [],
        "cover": f"{SLUG}/cover.jpg",
        "coverAlt": "橙色帆布托特包正面平放",
        "gallery": [
            {"src": f"{SLUG}/01.jpg", "alt": "待填写", "caption": "内衬裁片"},
            {"src": f"{SLUG}/02.jpg", "alt": "缝好的口袋特写"},
        ],
        "materials": ["10 安帆布 1 米"],
        "tools": ["家用缝纫机"],
        "difficulty": "beginner",
        "status": "finished",
    }
    fm.update(overrides)
    return fm


def _make_repo(root: Path, fm: dict[str, Any] | None = None, notes: str = "先裁布，再缝口袋。\n") -> Path:
    (root / "src/content/works").mkdir(parents=True, exist_ok=True)
    (root / f"src/assets/works/{SLUG}").mkdir(parents=True, exist_ok=True)
    (root / MD).write_text(render_content_file(fm or _skeleton(), ""), encoding="utf-8")
    (root / NOTES).write_text(notes, encoding="utf-8")
    return root


def _result(**overrides: Any) -> dict[str, Any]:
    result = {
        "description": "一只日常用的帆布托特包，内衬带口袋。",
        "tags": ["帆布", "包袋"],
        "body": "## 制作步骤\n\n1. 裁布\n2. 缝口袋\n",
        "cover": "other/evil.jpg",  # must be ignored: human-owned
        "draft": False,  # must be ignored
    }
    result.update(overrides)
    return result


class Recorder:
    def __init__(self, *responses: httpx.Response) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(json.loads(request.content))
        return self.responses.pop(0)


def _ok(result: dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(result, ensure_ascii=False)}}]})


def _generate(repo: Path, bundle: Path, recorder: Recorder):
    return generate_work_bundle(
        INPUTS, ENV, repo, bundle,
        policy_path=POLICY_PATH, prompts_dir=PROMPTS_DIR,
        transport=httpx.MockTransport(recorder), sleep=lambda _: None, clock=lambda: NOW,
    )


# --- schema ------------------------------------------------------------------


def test_categories_match_the_site():
    text = (ROOT / "src/lib/categories.ts").read_text(encoding="utf-8")
    site = re.findall(r"\{ slug: '([^']+)', label: '([^']+)'", text)
    assert tuple(site) == CATEGORIES


def test_placeholder_alt_allowed_only_for_drafts():
    fm = _skeleton()
    assert validate_work_front_matter(fm, allow_placeholders=True) == []
    fields = [i.field for i in validate_work_front_matter(fm)]
    assert fields == ["gallery.0.alt"]


@pytest.mark.parametrize(
    ("override", "field"),
    [
        ({"cover": "other-work/cover.jpg"}, "cover"),
        ({"cover": f"{SLUG}/Cover.JPG"}, "cover"),
        ({"cover": f"{SLUG}/cover.avif"}, "cover"),
        ({"category": "painting"}, "category"),
        ({"video": {"provider": "vimeo", "id": "1", "title": "t"}}, "video.provider"),
        ({"video": {"provider": "bilibili", "id": "nope", "title": "t"}}, "video.id"),
        ({"ai_assisted": True}, "model"),
        ({"surprise": 1}, "surprise"),
        ({"pubDate": "2026-09-30"}, "pubDate"),
        ({"materials": "帆布"}, "materials"),
        ({"materials": [""]}, "materials.0"),
        ({"materials": [3]}, "materials.0"),
        ({"materials": [{"name": "胶", "url": "http://insecure.example"}]}, "materials.0.url"),
        ({"materials": [{"name": "胶", "url": "https://user:pw@example.com/"}]}, "materials.0.url"),
        ({"tools": [{"url": "https://example.com/"}]}, "tools.0.name"),
        ({"tools": [{"name": "剪刀", "url": "https://example.com/", "affiliate": "yes"}]}, "tools.0.affiliate"),
        ({"tools": [{"name": "剪刀", "url": "https://example.com/", "price": 3}]}, "tools.0.price"),
        ({"shop": {"label": "x", "url": "https://example.com/"}}, "shop"),
        ({"shop": ["https://example.com/"]}, "shop.0"),
        ({"shop": [{"label": "", "url": "https://example.com/"}]}, "shop.0.label"),
        ({"shop": [{"label": "图纸", "url": "javascript:alert(1)"}]}, "shop.0.url"),
    ],
)
def test_schema_rejections(override, field):
    fields = [i.field for i in validate_work_front_matter(_skeleton(**override), allow_placeholders=True)]
    assert field in fields


def test_linked_supplies_and_shop_links_are_accepted():
    fm = _skeleton(
        materials=["10 安帆布 1 米", {"name": "棉织带", "url": "https://www.amazon.com/dp/B000000000?tag=me-20"}],
        tools=[{"name": "家用缝纫机", "url": "https://example.com/machine", "affiliate": False}],
        shop=[{"label": "Tote bag PDF pattern", "url": "https://www.etsy.com/listing/1"}],
    )
    assert validate_work_front_matter(fm, allow_placeholders=True) == []


def test_model_input_gets_supply_names_but_never_shop_urls(tmp_path: Path):
    fm = _skeleton(
        materials=["10 安帆布 1 米", {"name": "棉织带", "url": "https://www.amazon.com/dp/B000000000?tag=me-20"}],
        shop=[{"label": "Pattern", "url": "https://www.etsy.com/listing/1"}],
    )
    facts = model_input(load_work_source(_make_repo(tmp_path, fm=fm), SLUG))
    assert facts["materials"] == ["10 安帆布 1 米", "棉织带"]
    assert facts["tools"] == ["家用缝纫机"]
    assert "https://" not in json.dumps(facts)


def test_request_validation():
    assert validate_work_request(INPUTS) == REQUEST
    with pytest.raises(InputValidationError) as err:
        validate_work_request({"work_slug": "../x", "prompt_name": "work-draft"})
    assert err.value.fields == ("work_slug", "prompt_version")


# --- maker sources -------------------------------------------------------------


def test_source_errors(tmp_path: Path):
    with pytest.raises(WorkSourceError, match="not found"):
        load_work_source(tmp_path, SLUG)
    repo = _make_repo(tmp_path / "a", notes="  \n")
    with pytest.raises(WorkSourceError, match="empty"):
        load_work_source(repo, SLUG)
    template = "# 笔记\n\n<!-- 只写事实 -->\n\n## 为什么做\n\n## 制作步骤\n\n1.\n- \n"
    repo = _make_repo(tmp_path / "t", notes=template)
    with pytest.raises(WorkSourceError, match="empty"):
        load_work_source(repo, SLUG)
    repo = _make_repo(tmp_path / "t2", notes=template.replace("1.\n", "1. 先裁布\n"))
    assert load_work_source(repo, SLUG).notes == "# 笔记\n\n## 为什么做\n\n## 制作步骤\n\n1. 先裁布\n-"
    repo = _make_repo(tmp_path / "b", fm=_skeleton(draft=False, gallery=[]))
    with pytest.raises(WorkSourceError, match="draft: false"):
        load_work_source(repo, SLUG)
    repo = _make_repo(tmp_path / "c", fm=_skeleton(slug="other", cover="other/cover.jpg", gallery=[]))
    with pytest.raises(ArticleValidationError):
        load_work_source(repo, SLUG)


def test_model_input_has_facts_and_notes_but_no_photo_paths(tmp_path: Path):
    source = load_work_source(_make_repo(tmp_path), SLUG)
    facts = model_input(source)
    assert facts["notes"] == "先裁布，再缝口袋。"
    assert facts["category"] == "缝纫"
    # Placeholder alt texts are not sent; real captions/alts are.
    assert facts["photos"] == [{"caption": "内衬裁片"}, {"alt": "缝好的口袋特写"}]
    assert "cover.jpg" not in json.dumps(facts)


# --- generate -> bundle -> apply ----------------------------------------------------


def test_end_to_end_keeps_human_fields_and_is_idempotent(tmp_path: Path):
    repo = _make_repo(tmp_path / "repo")
    bundle = tmp_path / "bundle"
    recorder = Recorder(_ok(_result()))
    prepared = _generate(repo, bundle, recorder)
    assert len(recorder.requests) == 1
    user = recorder.requests[0]["messages"][1]["content"]
    assert "先裁布" in user and SECRET not in user

    source = load_work_source(repo, SLUG)
    verified = load_work_bundle(bundle, REQUEST, POLICY, source)
    assert verified.stable_key == prepared.stable_key == compute_work_key(source, "1.0.0", POLICY.model)
    fm = verified.front_matter
    assert fm["cover"] == f"{SLUG}/cover.jpg" and fm["draft"] is True and fm["ai_assisted"] is True
    assert fm["description"].startswith("一只") and fm["tags"] == ["帆布", "包袋"]
    assert fm["gallery"][0]["alt"] == "待填写"  # the model never writes alt texts

    change = apply_work_draft(verified, repo, branch=f"work/{SLUG}", default_branch="main")
    assert change.action is ChangeAction.UPDATE and change.target.path == MD
    assert (repo / MD).read_bytes() == verified.content

    # A rerun reads the rewritten file: human facts and notes are unchanged, so the key is too.
    source2 = load_work_source(repo, SLUG)
    assert compute_work_key(source2, "1.0.0", POLICY.model) == verified.stable_key
    again = load_work_bundle(bundle, REQUEST, POLICY, source2)
    assert apply_work_draft(again, repo, branch=f"work/{SLUG}", default_branch="main").action is ChangeAction.UNCHANGED

    text = work_pr_instructions(change, server_url="https://github.com", repository="o/r", default_branch="main")
    assert f"main...work/{SLUG}" in text and "`media`" in text


def test_bundle_is_rejected_after_notes_or_human_fields_change(tmp_path: Path):
    repo = _make_repo(tmp_path / "repo")
    bundle = tmp_path / "bundle"
    _generate(repo, bundle, Recorder(_ok(_result())))

    (repo / NOTES).write_text("改过的笔记\n", encoding="utf-8")
    with pytest.raises(DraftBundleError, match="stable_key"):
        load_work_bundle(bundle, REQUEST, POLICY, load_work_source(repo, SLUG))

    _make_repo(repo, fm=_skeleton(materials=["别的布"]))
    with pytest.raises(DraftBundleError, match="materials"):
        load_work_bundle(bundle, REQUEST, POLICY, load_work_source(repo, SLUG))


def test_tampered_bundle_is_rejected(tmp_path: Path):
    repo = _make_repo(tmp_path / "repo")
    bundle = tmp_path / "bundle"
    _generate(repo, bundle, Recorder(_ok(_result())))
    source = load_work_source(repo, SLUG)
    original = (bundle / WORK_FILE).read_text(encoding="utf-8")

    (bundle / WORK_FILE).write_bytes(original.replace("draft: true", "draft: false").encode("utf-8"))
    with pytest.raises(ArticleValidationError):
        load_work_bundle(bundle, REQUEST, POLICY, source)

    (bundle / WORK_FILE).write_bytes(original.replace("橙色帆布", "蓝色帆布").encode("utf-8"))
    with pytest.raises(DraftBundleError, match="coverAlt"):
        load_work_bundle(bundle, REQUEST, POLICY, source)

    (bundle / WORK_FILE).write_bytes(original.encode("utf-8"))
    manifest = json.loads((bundle / MANIFEST_FILE).read_text(encoding="utf-8"))
    (bundle / MANIFEST_FILE).write_text(json.dumps({**manifest, "slug": "other"}), encoding="utf-8")
    with pytest.raises(DraftBundleError, match="slug"):
        load_work_bundle(bundle, REQUEST, POLICY, source)


def test_invalid_model_output_writes_no_bundle(tmp_path: Path):
    repo = _make_repo(tmp_path / "repo")
    bundle = tmp_path / "bundle"
    bad = _result(body="<script>alert(1)</script>\n[x](http://insecure.example)\n")
    with pytest.raises(ArticleValidationError):
        _generate(repo, bundle, Recorder(_ok(bad)))
    assert not bundle.exists()


def test_apply_refuses_other_branches(tmp_path: Path):
    repo = _make_repo(tmp_path / "repo")
    bundle = tmp_path / "bundle"
    _generate(repo, bundle, Recorder(_ok(_result())))
    verified = load_work_bundle(bundle, REQUEST, POLICY, load_work_source(repo, SLUG))
    with pytest.raises(DraftBundleError):
        apply_work_draft(verified, repo, branch="main", default_branch="main")
    with pytest.raises(DraftBundleError):
        apply_work_draft(verified, repo, branch="work/other", default_branch="main")


def test_cli_commands(tmp_path: Path, capsys):
    repo = _make_repo(tmp_path / "repo")
    bundle = tmp_path / "bundle"
    out = tmp_path / "out.txt"
    common = ["--bundle-dir", str(bundle), "--policy", str(POLICY_PATH), "--github-output", str(out)]
    recorder = Recorder(_ok(_result()))
    code = cli.main(
        ["generate-work", *common, "--work-repo", str(repo), "--prompts-dir", str(PROMPTS_DIR)],
        env=CLI_ENV, transport=httpx.MockTransport(recorder), sleep=lambda _: None,
    )
    assert code == 0
    assert cli.main(["verify-work-bundle", *common, "--work-repo", str(repo)], env=CLI_ENV) == 0
    instructions = tmp_path / "pr.md"
    code = cli.main(
        ["apply-work-draft", *common, "--repo", str(repo), "--branch", f"work/{SLUG}",
         "--default-branch", "main", "--server-url", "https://github.com", "--repository", "o/r",
         "--instructions-file", str(instructions)],
        env=CLI_ENV,
    )
    assert code == 0
    outputs = out.read_text(encoding="utf-8")
    assert f"branch=work/{SLUG}" in outputs and f"path={MD}" in outputs and "action=update" in outputs
    assert SECRET not in capsys.readouterr().out + outputs


# --- workflow -------------------------------------------------------------------


def test_work_workflow_keeps_secret_and_write_token_apart():
    text = (ROOT / ".github/workflows/generate-work-draft.yml").read_text(encoding="utf-8")
    config = yaml.safe_load(text)
    assert set(config.get("on", config.get(True))) == {"workflow_dispatch"}
    assert config["permissions"] == {}
    jobs = config["jobs"]
    assert jobs["generate"]["permissions"] == {"contents": "read"}
    assert jobs["work-branch"]["permissions"] == {"contents": "write"}
    assert "secrets." not in yaml.safe_dump(jobs["work-branch"])
    secret_steps = [s for s in jobs["generate"]["steps"] if "secrets." in yaml.safe_dump(s)]
    assert len(secret_steps) == 1
    for job in jobs.values():
        for step in job["steps"]:
            assert "${{" not in step.get("run", "")
    lowered = text.lower()
    for forbidden in ("gh pr merge", "--approve", "push --force", "push -f"):
        assert forbidden not in lowered
