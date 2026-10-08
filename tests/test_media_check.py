"""Work asset checks and the review gate rules for works and photos."""

from __future__ import annotations

import shutil
import struct
import subprocess
import zlib
from pathlib import Path

import pytest

from content_pipeline.article import render_content_file
from content_pipeline.media_check import MAX_IMAGE_BYTES, check_asset
from content_pipeline.review_gate import (
    ArticleChange,
    AssetChange,
    Revision,
    evaluate_review_gate,
    main,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SLUG = "tote-bag"
WORK = f"src/content/works/{SLUG}.md"
IMG = f"src/assets/works/{SLUG}/cover.jpg"
BOT = ("github-actions[bot]", "41898282+github-actions[bot]@users.noreply.github.com")
EDITOR = ("Editor", "editor@example.com")
FIVE = """- [x] 事实与来源 `facts_and_sources`：对照笔记核对
- [x] 读者价值 `reader_value`：步骤清楚
- [x] 语气 `tone`：平实
- [x] 链接 `links`：无外链
- [x] 标题 `title`：与作品一致
"""
SIX = FIVE + "- [x] 图片与视频 `media`：本人拍摄，alt 已写，EXIF 已清除\n"


# --- image builders -------------------------------------------------------------


def _segment(marker: int, payload: bytes) -> bytes:
    return bytes([0xFF, marker]) + struct.pack(">H", len(payload) + 2) + payload


def jpeg(*extra: bytes) -> bytes:
    app0 = _segment(0xE0, b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")
    sos = _segment(0xDA, b"\x01\x01\x00\x00\x3f\x00")
    return b"\xff\xd8" + app0 + b"".join(extra) + sos + b"\x12\x34\x56" + b"\xff\xd9"


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def png(*extra: bytes) -> bytes:
    ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    idat = _chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00"))
    return b"\x89PNG\r\n\x1a\n" + ihdr + b"".join(extra) + idat + _chunk(b"IEND", b"")


def webp(*extra: tuple[bytes, bytes]) -> bytes:
    chunks = [(b"VP8L", b"\x2f\x00\x00\x00\x00")] + list(extra)
    body = b"WEBP" + b"".join(k + struct.pack("<I", len(d)) + d + (b"\x00" if len(d) & 1 else b"") for k, d in chunks)
    return b"RIFF" + struct.pack("<I", len(body)) + body


# --- check_asset ------------------------------------------------------------------


def test_clean_images_and_notes_pass():
    assert check_asset(IMG, jpeg()) == []
    assert check_asset(f"src/assets/works/{SLUG}/a.png", png()) == []
    assert check_asset(f"src/assets/works/{SLUG}/b.webp", webp()) == []
    assert check_asset(f"src/assets/works/{SLUG}/notes.md", "笔记".encode()) == []
    assert check_asset("src/assets/works/.gitkeep", b"") == []


@pytest.mark.parametrize(
    ("path", "data", "reason"),
    [
        (IMG, jpeg(_segment(0xE1, b"Exif\x00\x00GPS...")), "EXIF"),
        (IMG, jpeg(_segment(0xE1, b"http://ns.adobe.com/xap/1.0/\x00<x/>")), "XMP"),
        (IMG, jpeg(_segment(0xED, b"Photoshop 3.0\x00")), "IPTC"),
        (f"src/assets/works/{SLUG}/a.png", png(_chunk(b"eXIf", b"MM\x00*")), "EXIF"),
        (f"src/assets/works/{SLUG}/a.png", png(_chunk(b"tEXt", b"Comment\x00hi")), "text"),
        (f"src/assets/works/{SLUG}/b.webp", webp((b"EXIF", b"MM\x00*")), "EXIF"),
        (IMG, png(), "not a valid .jpg"),
        (IMG, b"\xff\xd8\xff\xe1\xff", "not a valid .jpg"),
        (f"src/assets/works/{SLUG}/IMG_1.JPG", jpeg(), "file name"),
        (f"src/assets/works/{SLUG}/x.heic", b"", "file name"),
        (f"src/assets/works/{SLUG}/sub/x.jpg", jpeg(), "src/assets/works/<slug>/<file>"),
        (IMG, jpeg() + b"\x00" * MAX_IMAGE_BYTES, "MiB"),
    ],
    ids=["jpeg-exif", "jpeg-xmp", "jpeg-iptc", "png-exif", "png-text", "webp-exif", "wrong-format",
         "truncated", "uppercase-name", "heic", "nested", "too-large"],
)
def test_bad_assets_fail(path, data, reason):
    issues = check_asset(path, data)
    assert len(issues) == 1 and reason in issues[0].reason and issues[0].field == path


# --- gate rules ------------------------------------------------------------------


def _work(draft: bool, **overrides) -> str:
    fm = {
        "title": "帆布托特包",
        "description": "一只日常用的托特包。",
        "pubDate": "2026-09-30T02:28:05Z",
        "slug": SLUG,
        "draft": draft,
        "category": "sewing",
        "tags": ["帆布"],
        "cover": f"{SLUG}/cover.jpg",
        "coverAlt": "橙色帆布托特包正面平放",
        "gallery": [],
        "ai_assisted": True,
        "model": "m",
        "prompt_version": "1.0.0",
    }
    fm.update(overrides)
    return render_content_file(fm, "## 制作\n\n正文。\n")


def _flipped(head: str | None = None) -> ArticleChange:
    head = head or _work(False)
    return ArticleChange(
        path=WORK,
        base_text=None,
        revisions=(Revision("a" * 40, *EDITOR, _work(True)), Revision("b" * 40, *BOT, _work(True)),
                   Revision("c" * 40, *EDITOR, head)),
        head_text=head,
    )


def _fields(result) -> list[str]:
    return [i.field for i in result.issues]


def test_published_work_with_six_records_and_clean_photo_passes():
    result = evaluate_review_gate(SIX, [_flipped()], assets=[AssetChange(IMG, jpeg())], asset_exists=lambda p: True)
    assert result.applicable and result.passed


def test_work_needs_media_record():
    assert _fields(evaluate_review_gate(FIVE, [_flipped()])) == ["review.media"]


def test_asset_only_pr_needs_only_media_and_clean_files():
    dirty = AssetChange(IMG, jpeg(_segment(0xE1, b"Exif\x00\x00")))
    result = evaluate_review_gate("", [], assets=[dirty])
    assert _fields(result) == ["review.media", IMG]
    only_media = "- [x] 图片与视频 `media`：换了一张更清楚的封面\n"
    assert evaluate_review_gate(only_media, [], assets=[AssetChange(IMG, jpeg())]).passed


def test_placeholder_alt_blocks_publishing_but_not_drafts():
    head = _work(False, coverAlt="待填写")
    assert _fields(evaluate_review_gate(SIX, [_flipped(head)])) == [f"{WORK}:coverAlt"]
    draft = ArticleChange(WORK, None, (Revision("a" * 40, *BOT, _work(True, coverAlt="待填写")),),
                          _work(True, coverAlt="待填写"))
    assert _fields(evaluate_review_gate(SIX, [draft])) == [f"{WORK}:draft"]


def test_published_work_must_reference_existing_photos():
    result = evaluate_review_gate(SIX, [_flipped()], asset_exists=lambda p: False)
    assert _fields(result) == [f"{WORK}:cover"]


def test_unresolved_ai_markers_block_publishing():
    head = _work(False).replace("正文。", "缝份 [待确认：宽度]。")
    assert _fields(evaluate_review_gate(SIX, [_flipped(head)])) == [f"{WORK}:body"]


def test_bot_cannot_publish_a_work():
    head = _work(False)
    change = ArticleChange(WORK, None, (Revision("a" * 40, *EDITOR, _work(True)), Revision("b" * 40, *BOT, head)), head)
    assert _fields(evaluate_review_gate(SIX, [change])) == [f"{WORK}:draft"]


# --- real git history + CLI --------------------------------------------------------


def _git(repo: Path, *args: str, author: tuple[str, str] = EDITOR) -> str:
    return subprocess.run(
        ["git", "-c", f"user.name={author[0]}", "-c", f"user.email={author[1]}", "-c", "commit.gpgsign=false",
         "-c", "core.autocrlf=false", *args],
        cwd=repo, check=True, capture_output=True, text=True,
    ).stdout.strip()


def _put(repo: Path, rel: str, data: bytes | str) -> None:
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data.encode("utf-8") if isinstance(data, str) else data)


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_gate_cli_on_work_branch_history(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _put(repo, "docs/compliance.md", (REPO_ROOT / "docs" / "compliance.md").read_text(encoding="utf-8"))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")

    _git(repo, "checkout", "-q", "-b", f"work/{SLUG}")
    _put(repo, IMG, jpeg(_segment(0xE1, b"Exif\x00\x00GPS")))  # forgot to strip metadata
    _put(repo, f"src/assets/works/{SLUG}/notes.md", "笔记\n")
    _put(repo, WORK, _work(True))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "maker files")
    _put(repo, WORK, _work(True, description="AI 起草的简介。"))
    _git(repo, "commit", "-q", "-am", "draft text", author=BOT)
    _put(repo, WORK, _work(False, description="AI 起草的简介。"))
    _git(repo, "commit", "-q", "-am", "publish")
    body = tmp_path / "body.md"
    body.write_text(SIX, encoding="utf-8")
    args = ["--repo", str(repo), "--base", base, "--body-file", str(body)]
    assert main([*args, "--head", _git(repo, "rev-parse", "HEAD")]) == 1  # EXIF in the photo

    _put(repo, IMG, jpeg())
    _git(repo, "commit", "-q", "-am", "strip metadata")
    assert main([*args, "--head", _git(repo, "rev-parse", "HEAD")]) == 0

    _git(repo, "rm", "-q", IMG)
    _git(repo, "commit", "-q", "-m", "oops, removed the cover")
    assert main([*args, "--head", _git(repo, "rev-parse", "HEAD")]) == 1  # cover missing
