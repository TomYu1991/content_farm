"""Pure checks for work assets under ``src/assets/works/`` (review gate).

Photos on a public site must not leak where they were taken: phone cameras
embed GPS coordinates, device serials and timestamps in EXIF/XMP. The ingest
script (``npm run ingest``) strips all of it; this module re-checks every
added or modified asset in a Pull Request so a photo committed by any other
route cannot slip through.

Rules for a file ``src/assets/works/<slug>/<name>``:

* ``<slug>`` is a Slug; ``<name>`` is ``notes.md`` or
  ``[a-z0-9][a-z0-9_-]{0,99}.(jpg|jpeg|png|webp)``;
* images are at most :data:`MAX_IMAGE_BYTES`, notes at most :data:`MAX_NOTES_BYTES`;
* the bytes match the extension's format and contain no metadata block:
  JPEG APP1 (EXIF/XMP), APP13 (IPTC/Photoshop) or COM; PNG ``eXIf``,
  ``tEXt``, ``zTXt``, ``iTXt``; WebP ``EXIF`` or ``XMP `` chunks.

Only structure is parsed (no decoding, no dependencies). Issues name the path
and rule only.
"""

from __future__ import annotations

import re
import struct

from .article import is_slug
from .errors import FieldIssue
from .work import NOTES_FILE, WORK_ASSETS_ROOT

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_NOTES_BYTES = 32 * 1024

_IMAGE_NAME = re.compile(r"[a-z0-9][a-z0-9_-]{0,99}\.(jpg|jpeg|png|webp)")
# Empty files that only keep the directory in Git; not photos, never reviewed as assets.
PLACEHOLDER_FILES = frozenset({f"{WORK_ASSETS_ROOT}/.gitkeep"})

MSG_METADATA = "contains photo metadata ({}); re-import it with npm run ingest"


class _Malformed(Exception):
    pass


def _jpeg_metadata(data: bytes) -> list[str]:
    if not data.startswith(b"\xff\xd8"):
        raise _Malformed
    found: list[str] = []
    pos = 2
    while pos < len(data):
        if data[pos] != 0xFF:
            raise _Malformed
        while pos < len(data) and data[pos] == 0xFF:  # fill bytes
            pos += 1
        if pos >= len(data):
            raise _Malformed
        marker = data[pos]
        pos += 1
        if marker == 0xD9:  # EOI
            return found
        if marker == 0x01 or 0xD0 <= marker <= 0xD7:  # no length
            continue
        if pos + 2 > len(data):
            raise _Malformed
        (length,) = struct.unpack(">H", data[pos : pos + 2])
        if length < 2 or pos + length > len(data):
            raise _Malformed
        payload = data[pos + 2 : pos + length]
        if marker == 0xE1:
            if payload.startswith(b"Exif\x00"):
                found.append("EXIF")
            elif payload.startswith(b"http://ns.adobe.com/"):
                found.append("XMP")
            else:
                found.append("APP1")
        elif marker == 0xED:
            found.append("IPTC")
        elif marker == 0xFE:
            found.append("comment")
        if marker == 0xDA:  # start of scan: entropy-coded data follows, no more headers
            return found
        pos += length
    raise _Malformed


_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_PNG_METADATA = {b"eXIf": "EXIF", b"tEXt": "text", b"zTXt": "text", b"iTXt": "text/XMP"}


def _png_metadata(data: bytes) -> list[str]:
    if not data.startswith(_PNG_SIGNATURE):
        raise _Malformed
    found: list[str] = []
    pos = len(_PNG_SIGNATURE)
    while pos + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[pos : pos + 8])
        end = pos + 8 + length + 4
        if end > len(data):
            raise _Malformed
        if kind in _PNG_METADATA:
            found.append(_PNG_METADATA[kind])
        if kind == b"IEND":
            return found
        pos = end
    raise _Malformed


def _webp_metadata(data: bytes) -> list[str]:
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise _Malformed
    found: list[str] = []
    pos = 12
    while pos + 8 <= len(data):
        kind, size = struct.unpack("<4sI", data[pos : pos + 8])
        pos += 8 + size + (size & 1)
        if pos > len(data):
            raise _Malformed
        if kind == b"EXIF":
            found.append("EXIF")
        elif kind == b"XMP ":
            found.append("XMP")
    if pos != len(data):
        raise _Malformed
    return found


_PARSERS = {"jpg": _jpeg_metadata, "jpeg": _jpeg_metadata, "png": _png_metadata, "webp": _webp_metadata}


def check_asset(path: str, data: bytes) -> list[FieldIssue]:
    """Rules for one added/modified file under ``src/assets/works/``."""
    if path in PLACEHOLDER_FILES:
        return []
    prefix = f"{WORK_ASSETS_ROOT}/"
    rest = path[len(prefix):] if path.startswith(prefix) else None
    parts = rest.split("/") if rest else []
    if len(parts) != 2 or not is_slug(parts[0]):
        return [FieldIssue(path, "work assets must be src/assets/works/<slug>/<file>")]
    name = parts[1]
    if name == NOTES_FILE:
        if len(data) > MAX_NOTES_BYTES:
            return [FieldIssue(path, f"exceeds {MAX_NOTES_BYTES} bytes")]
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            return [FieldIssue(path, "must be UTF-8 text")]
        return []
    match = _IMAGE_NAME.fullmatch(name)
    if match is None:
        return [FieldIssue(path, "file name must be lowercase [a-z0-9_-] with .jpg/.jpeg/.png/.webp, or notes.md")]
    if len(data) > MAX_IMAGE_BYTES:
        return [FieldIssue(path, f"exceeds {MAX_IMAGE_BYTES // (1024 * 1024)} MiB; re-import it with npm run ingest")]
    try:
        found = _PARSERS[match.group(1)](data)
    except (_Malformed, struct.error):
        return [FieldIssue(path, f"is not a valid .{match.group(1)} image")]
    if found:
        return [FieldIssue(path, MSG_METADATA.format(", ".join(sorted(set(found)))))]
    return []


__all__ = ["MAX_IMAGE_BYTES", "MAX_NOTES_BYTES", "check_asset"]
