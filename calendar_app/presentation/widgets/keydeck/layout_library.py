# -*- coding: utf-8 -*-
"""KeyDeck layout files: keep user layouts and share them as ``.keydeck`` files.

A layout document is UTF-8 JSON::

    {"format": "air-calendar-keydeck-layout", "version": 1,
     "kind": "page" | "deck", "name": "...", "created": "2026-09-30T21:00:00",
     "app_version": "3.7.7",
     "page": {...}, "look": {...}, "panorama": {...}     # kind == "page"
     "deck": {...}                                       # kind == "deck"
     "assets": {"<sha>": {"name": "art.png", "kind": "image" | "sound", "data": "<base64>"}}}

Images, custom sounds and the panorama are embedded so a shared file shows the same art on
another PC.  Inside the document their paths are ``asset:<sha>`` references; they are restored
into the app's asset store (validated by ``import_launcher_asset``) only when a layout is
applied.  App/file targets of keys are kept as written — the import confirmation lists them.
"""

from __future__ import annotations

import base64
import binascii
from copy import deepcopy
from dataclasses import dataclass
import datetime
import hashlib
import json
from pathlib import Path
import re
import tempfile
import uuid

from calendar_app.app_metadata import APP_VERSION
from calendar_app.app_paths import get_app_data_dir
from calendar_app.infrastructure.runtime.launcher_asset_store import import_launcher_asset
from calendar_app.presentation.widgets.keydeck.model import (
    CUSTOM_THEME_ID,
    MAX_PAGES,
    default_panorama,
    duplicate_key,
    new_page,
    normalize_deck,
)

FORMAT_ID = "air-calendar-keydeck-layout"
FORMAT_VERSION = 1
LAYOUT_SUFFIX = ".keydeck"
LIBRARY_FOLDER = "keydeck_layouts"
MAX_FILE_BYTES = 48 * 1024 * 1024
MAX_EMBED_BYTES = 32 * 1024 * 1024
ASSET_PREFIX = "asset:"
_ASSET_KINDS = frozenset({"image", "sound"})
_LOOK_FIELDS = ("unit", "gap", "case", "theme", "led_brightness")
_UNSAFE_NAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')
_DIGEST = re.compile(r"^[0-9a-f]{8,64}$")


class LayoutError(Exception):
    """A layout file could not be used; ``code`` picks the user-facing message."""

    CODES = ("unreadable", "too_large", "not_layout", "newer_version", "empty")

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class LayoutEntry:
    """One saved layout in the library."""

    path: Path
    name: str
    kind: str
    created: str
    key_count: int
    page_count: int


# ---------------------------------------------------------------------------
# Building documents
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


class _Embedder:
    """Collects files referenced by keys into the document's asset table."""

    def __init__(self) -> None:
        self.assets: dict[str, dict] = {}
        self.skipped: list[str] = []
        self._budget = MAX_EMBED_BYTES

    def __call__(self, path: str, kind: str) -> str:
        if not path or path.startswith(ASSET_PREFIX):
            return path
        source = Path(path)
        try:
            data = source.read_bytes()
        except OSError:
            self.skipped.append(source.name)
            return ""
        digest = hashlib.sha256(data).hexdigest()[:24]
        if digest not in self.assets:
            if len(data) > self._budget:
                self.skipped.append(source.name)
                return ""
            self._budget -= len(data)
            self.assets[digest] = {
                "name": source.name[:120],
                "kind": kind,
                "data": base64.b64encode(data).decode("utf-8", errors="strict"),
            }
        return ASSET_PREFIX + digest

    def keys(self, keys: list[dict]) -> None:
        for key in keys:
            if key["insert"]["path"]:
                key["insert"]["path"] = self(key["insert"]["path"], "image")
            if key["sound_path"]:
                key["sound_path"] = self(key["sound_path"], "sound")


def build_document(
    deck: dict, *, kind: str, name: str, page_index: int | None = None
) -> tuple[dict, list[str]]:
    """Package one page (``kind="page"``) or the whole deck as a shareable document.

    Returns ``(document, skipped_file_names)``; files that are missing or would push the
    embedded total over :data:`MAX_EMBED_BYTES` are left out (their keys lose that art).
    """
    source = normalize_deck(deepcopy(deck))
    embed = _Embedder()
    document: dict = {
        "format": FORMAT_ID,
        "version": FORMAT_VERSION,
        "kind": "deck" if kind == "deck" else "page",
        "name": _clean_name(name),
        "created": _now(),
        "app_version": APP_VERSION,
    }
    if document["kind"] == "deck":
        body = deepcopy(source)
        for page in body["pages"]:
            embed.keys(page["keys"])
        body["panorama"]["path"] = embed(body["panorama"]["path"], "image")
        document["deck"] = body
    else:
        index = source["page"] if page_index is None else int(page_index)
        index = max(0, min(index, len(source["pages"]) - 1))
        page = deepcopy(source["pages"][index])
        embed.keys(page["keys"])
        uses_panorama = any(key["insert"]["kind"] == "panorama" for key in page["keys"])
        panorama = deepcopy(source["panorama"]) if uses_panorama else default_panorama()
        panorama["path"] = embed(panorama["path"], "image")
        document["page"] = page
        document["look"] = {field: deepcopy(source[field]) for field in _LOOK_FIELDS}
        document["panorama"] = panorama
    document["assets"] = embed.assets
    return document, embed.skipped


# ---------------------------------------------------------------------------
# Reading documents
# ---------------------------------------------------------------------------


def _clean_name(value: object) -> str:
    return " ".join(str(value or "").split())[:60]


def _clean_assets(raw: object) -> dict[str, dict]:
    assets: dict[str, dict] = {}
    if not isinstance(raw, dict):
        return assets
    for digest, item in raw.items():
        if not isinstance(item, dict) or not _DIGEST.match(str(digest)):
            continue
        kind = str(item.get("kind") or "")
        data = item.get("data")
        if kind not in _ASSET_KINDS or not isinstance(data, str):
            continue
        # 경로 부분은 버리고 파일 이름만 쓴다 (확장자·표시용일 뿐 저장 위치에는 쓰지 않음).
        base = str(item.get("name") or "asset").replace("\\", "/").rsplit("/", 1)[-1]
        name = _UNSAFE_NAME.sub("_", base).strip(" .")[:120]
        assets[str(digest)] = {"name": name or "asset", "kind": kind, "data": data}
    return assets


def parse_document(raw: bytes) -> dict:
    """Validate and normalise a layout file's bytes (raises :class:`LayoutError`)."""
    if len(raw) > MAX_FILE_BYTES:
        raise LayoutError("too_large")
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    try:
        data = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise LayoutError("unreadable") from exc
    if not isinstance(data, dict):
        raise LayoutError("not_layout")
    if data.get("format") != FORMAT_ID:
        # 레이아웃 형식이 아니어도 덱 JSON 자체(설정 백업 등)면 덱 레이아웃으로 받는다.
        if not isinstance(data.get("pages"), list):
            raise LayoutError("not_layout")
        data = {
            "format": FORMAT_ID,
            "version": 1,
            "kind": "deck",
            "name": data.get("name"),
            "deck": data,
        }
    try:
        version = int(data.get("version") or 1)
    except (TypeError, ValueError) as exc:
        raise LayoutError("not_layout") from exc
    if version > FORMAT_VERSION:
        raise LayoutError("newer_version")
    kind = data.get("kind")
    document = {
        "format": FORMAT_ID,
        "version": FORMAT_VERSION,
        "kind": kind,
        "name": _clean_name(data.get("name")),
        "created": str(data.get("created") or "")[:32],
        "app_version": str(data.get("app_version") or "")[:24],
        "assets": _clean_assets(data.get("assets")),
    }
    if kind == "deck":
        if not isinstance(data.get("deck"), dict):
            raise LayoutError("not_layout")
        document["deck"] = normalize_deck(data["deck"])
        key_count = sum(len(page["keys"]) for page in document["deck"]["pages"])
    elif kind == "page":
        page = data.get("page")
        if not isinstance(page, dict):
            raise LayoutError("not_layout")
        look = data.get("look") if isinstance(data.get("look"), dict) else {}
        probe = normalize_deck(
            {
                **{k: look[k] for k in _LOOK_FIELDS if k in look},
                "pages": [page],
                "panorama": data.get("panorama"),
            }
        )
        document["page"] = probe["pages"][0]
        document["look"] = {field: probe[field] for field in _LOOK_FIELDS}
        document["panorama"] = probe["panorama"]
        key_count = len(document["page"]["keys"])
    else:
        raise LayoutError("not_layout")
    if key_count == 0:
        raise LayoutError("empty")
    if not document["name"]:
        document["name"] = _clean_name(
            document["page"]["name"] if kind == "page" else document["deck"]["name"]
        )
    return document


def read_layout(path: str | Path) -> dict:
    try:
        target = Path(path)
        if target.stat().st_size > MAX_FILE_BYTES:
            raise LayoutError("too_large")
        return parse_document(target.read_bytes())
    except OSError as exc:
        raise LayoutError("unreadable") from exc


def document_counts(document: dict) -> tuple[int, int]:
    """(key count, page count) of a document."""
    if document["kind"] == "deck":
        pages = document["deck"]["pages"]
        return sum(len(page["keys"]) for page in pages), len(pages)
    return len(document["page"]["keys"]), 1


def summarize_actions(document: dict) -> dict:
    """What the layout's keys will do, for the import confirmation."""
    pages = document["deck"]["pages"] if document["kind"] == "deck" else [document["page"]]
    counts: dict[str, int] = {}
    targets: list[str] = []
    for page in pages:
        for key in page["keys"]:
            for action in (key["action"], key["hold_action"]):
                kind = action["type"]
                if kind == "none":
                    continue
                counts[kind] = counts.get(kind, 0) + 1
                target = action["target"].strip()
                meaningful = target and target.lower() not in {"http://", "https://"}
                if kind in {"app", "url"} and meaningful and target not in targets:
                    targets.append(target)
    return {"counts": counts, "targets": targets}


# ---------------------------------------------------------------------------
# Restoring assets
# ---------------------------------------------------------------------------


def _decode_asset(asset: dict) -> bytes | None:
    try:
        return base64.b64decode(asset["data"], validate=True)
    except (binascii.Error, ValueError):
        return None


def _restore_refs(content: dict, resolve) -> None:
    pages = content["pages"] if "pages" in content else [content["page"]]
    for page in pages:
        for key in page["keys"]:
            key["insert"]["path"] = resolve(key["insert"]["path"])
            key["sound_path"] = resolve(key["sound_path"])
    content["panorama"]["path"] = resolve(content["panorama"]["path"])


def materialize(document: dict, *, asset_root: Path | None = None) -> dict:
    """Copy a document's embedded files into the asset store and return usable content.

    Result: ``{"kind": "page", "name", "keys", "panorama"}`` (keys get fresh ids) or
    ``{"kind": "deck", "name", "deck"}``.
    """
    restored: dict[str, str] = {}
    assets = document.get("assets", {})

    def resolve(ref: str) -> str:
        if not ref.startswith(ASSET_PREFIX):
            return ref
        digest = ref[len(ASSET_PREFIX) :]
        if digest not in restored:
            restored[digest] = ""
            asset = assets.get(digest)
            data = _decode_asset(asset) if asset else None
            if data is not None:
                suffix = Path(asset["name"]).suffix.lower()
                with tempfile.TemporaryDirectory() as folder:
                    temporary = Path(folder) / f"layout_asset{suffix}"
                    temporary.write_bytes(data)
                    restored[digest] = import_launcher_asset(
                        str(temporary), asset["kind"], root=asset_root
                    )
        return restored[digest]

    if document["kind"] == "deck":
        deck = deepcopy(document["deck"])
        _restore_refs(deck, resolve)
        return {"kind": "deck", "name": document["name"], "deck": normalize_deck(deck)}
    content = {"page": deepcopy(document["page"]), "panorama": deepcopy(document["panorama"])}
    _restore_refs(content, resolve)
    return {
        "kind": "page",
        "name": document["name"],
        "keys": [duplicate_key(key) for key in content["page"]["keys"]],
        "panorama": content["panorama"],
    }


def apply_content(deck: dict, content: dict, mode: str = "replace") -> dict:
    """Return a copy of ``deck`` with materialised layout content applied.

    ``mode``: ``"replace"`` swaps the current page's keys, ``"new_page"`` appends a page
    (falls back to replace when the deck is full), and deck content replaces the whole deck.
    A page layout brings its panorama along unless other pages already show a panorama.
    """
    if content["kind"] == "deck":
        result = deepcopy(content["deck"])
        result["page"] = 0
        return normalize_deck(result)
    result = normalize_deck(deepcopy(deck))
    index = result["page"]
    adding = mode == "new_page" and len(result["pages"]) < MAX_PAGES
    keys = [duplicate_key(key) for key in content["keys"]]
    others_use_panorama = any(
        key["insert"]["kind"] == "panorama"
        for page_index, page in enumerate(result["pages"])
        for key in page["keys"]
        if adding or page_index != index
    )
    uses_panorama = any(key["insert"]["kind"] == "panorama" for key in keys)
    if uses_panorama and content["panorama"]["path"] and not others_use_panorama:
        result["panorama"] = deepcopy(content["panorama"])
    if adding:
        page = new_page(content["name"][:24])
        page["keys"] = keys
        result["pages"].append(page)
        result["page"] = len(result["pages"]) - 1
    else:
        result["pages"][index]["keys"] = keys
    result["theme"] = CUSTOM_THEME_ID
    return normalize_deck(result)


def preview_deck(document: dict, cache_dir: Path | None = None) -> dict:
    """A deck for thumbnails: embedded art is unpacked to a temp cache, not the asset store."""
    folder = cache_dir or Path(tempfile.gettempdir()) / "air_calendar_keydeck_preview"
    assets = document.get("assets", {})

    def resolve(ref: str) -> str:
        if not ref.startswith(ASSET_PREFIX):
            return ref
        digest = ref[len(ASSET_PREFIX) :]
        asset = assets.get(digest)
        if not asset:
            return ""
        target = folder / f"{digest}{Path(asset['name']).suffix.lower()}"
        if not target.exists():
            data = _decode_asset(asset)
            if data is None:
                return ""
            try:
                folder.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            except OSError:
                return ""
        return str(target)

    if document["kind"] == "deck":
        deck = deepcopy(document["deck"])
        _restore_refs(deck, resolve)
        deck["page"] = 0
        return normalize_deck(deck)
    content = {"page": deepcopy(document["page"]), "panorama": deepcopy(document["panorama"])}
    _restore_refs(content, resolve)
    look = document.get("look", {})
    return normalize_deck(
        {
            **look,
            "theme": look.get("theme", CUSTOM_THEME_ID),
            "pages": [content["page"]],
            "panorama": content["panorama"],
        }
    )


# ---------------------------------------------------------------------------
# Library & files
# ---------------------------------------------------------------------------


def library_dir(root: Path | None = None) -> Path:
    return (root or get_app_data_dir()) / LIBRARY_FOLDER


def write_layout(document: dict, path: str | Path) -> Path:
    """Write a document atomically (temp file + replace)."""
    target = Path(path)
    if target.suffix.lower() != LAYOUT_SUFFIX:
        target = target.with_name(target.name + LAYOUT_SUFFIX)
    target.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(document, ensure_ascii=False, separators=(",", ":"))
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8", errors="strict")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def safe_file_stem(name: str) -> str:
    stem = _UNSAFE_NAME.sub("_", _clean_name(name)).strip(" .")
    return stem[:40] or "layout"


def save_to_library(document: dict, root: Path | None = None) -> Path:
    folder = library_dir(root)
    target = folder / f"{safe_file_stem(document['name'])}-{uuid.uuid4().hex[:8]}{LAYOUT_SUFFIX}"
    return write_layout(document, target)


def _entry(path: Path, document: dict) -> LayoutEntry:
    keys, pages = document_counts(document)
    return LayoutEntry(
        path=path,
        name=document["name"],
        kind=document["kind"],
        created=document.get("created", ""),
        key_count=keys,
        page_count=pages,
    )


def load_library(root: Path | None = None) -> list[tuple[LayoutEntry, dict]]:
    """Saved layouts with their documents, newest first; unreadable files are skipped."""
    folder = library_dir(root)
    loaded = []
    if folder.is_dir():
        for path in folder.glob(f"*{LAYOUT_SUFFIX}"):
            try:
                document = read_layout(path)
            except LayoutError:
                continue
            loaded.append((_entry(path, document), document))
    loaded.sort(key=lambda item: (item[0].created, item[0].name), reverse=True)
    return loaded


def list_layouts(root: Path | None = None) -> list[LayoutEntry]:
    """Saved layouts, newest first; unreadable files are skipped."""
    return [entry for entry, _document in load_library(root)]


def _inside_library(path: Path, root: Path | None) -> bool:
    try:
        return Path(path).resolve().parent == library_dir(root).resolve()
    except OSError:
        return False


def rename_layout(path: str | Path, name: str, root: Path | None = None) -> None:
    target = Path(path)
    if not _inside_library(target, root):
        raise LayoutError("unreadable")
    document = read_layout(target)
    document["name"] = _clean_name(name) or document["name"]
    write_layout(document, target)


def delete_layout(path: str | Path, root: Path | None = None) -> bool:
    """Remove a saved layout; only files inside the library folder are ever deleted."""
    target = Path(path)
    if not _inside_library(target, root) or target.suffix.lower() != LAYOUT_SUFFIX:
        return False
    try:
        target.unlink()
    except OSError:
        return False
    return True


def import_to_library(source: str | Path, root: Path | None = None) -> tuple[Path, dict]:
    document = read_layout(source)
    return save_to_library(document, root), document


__all__ = [
    "ASSET_PREFIX",
    "FORMAT_ID",
    "FORMAT_VERSION",
    "LAYOUT_SUFFIX",
    "LayoutEntry",
    "LayoutError",
    "apply_content",
    "build_document",
    "delete_layout",
    "document_counts",
    "import_to_library",
    "library_dir",
    "list_layouts",
    "load_library",
    "materialize",
    "parse_document",
    "preview_deck",
    "read_layout",
    "rename_layout",
    "safe_file_stem",
    "save_to_library",
    "summarize_actions",
    "write_layout",
]
