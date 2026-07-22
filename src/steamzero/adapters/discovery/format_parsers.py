from __future__ import annotations

import re
from pathlib import Path

from steamzero.ports import RomFormatParser

_NSP_EXTENSIONS = frozenset({".nsp", ".nsz"})
_XCI_EXTENSIONS = frozenset({".xci", ".xcz"})
_NRO_EXTENSION = ".nro"
_ALLOWED_EXTENSIONS = _NSP_EXTENSIONS | _XCI_EXTENSIONS | {_NRO_EXTENSION}
_TITLE_ID_RE = re.compile(r"0100[0-9A-Fa-f]{12}")
_SCENE_BRACKETS = re.compile(r"\s*\([^)]*\)\s*")


class NspParser(RomFormatParser):
    def supports(self, path: Path) -> bool:
        return path.suffix.lower() in _NSP_EXTENSIONS

    def parse_title_id(self, path: Path) -> str | None:
        match = _TITLE_ID_RE.search(path.name)
        if match:
            return match.group(0).upper()
        return _title_id_from_parent(path)

    def parse_content_kind(self, path: Path) -> str:
        stem = _clean_stem(path)
        if "[DLC]" in stem or "[Dlc]" in stem:
            return "dlc"
        if "[UPD]" in stem or "[Upd]" in stem or "update" in stem.lower():
            return "update"
        tid = self.parse_title_id(path)
        if tid and _is_update_tid(tid):
            return "update"
        if tid and _is_dlc_tid(tid):
            return "dlc"
        return "base"

    def parse_version(self, path: Path) -> str | None:
        stem = _clean_stem(path)
        m = re.search(r"v(\d+\.\d+|\d+)", stem)
        return m.group(1) if m else None


class XciParser(RomFormatParser):
    def supports(self, path: Path) -> bool:
        return path.suffix.lower() in _XCI_EXTENSIONS

    def parse_title_id(self, path: Path) -> str | None:
        match = _TITLE_ID_RE.search(path.name)
        if match:
            return match.group(0).upper()
        return _title_id_from_parent(path)

    def parse_content_kind(self, path: Path) -> str:
        stem = _clean_stem(path)
        if "[UPD]" in stem or "[Upd]" in stem or "update" in stem.lower():
            return "update"
        if "[DLC]" in stem or "[Dlc]" in stem:
            return "dlc"
        tid = self.parse_title_id(path)
        if tid and _is_update_tid(tid):
            return "update"
        if tid and _is_dlc_tid(tid):
            return "dlc"
        return "base"

    def parse_version(self, path: Path) -> str | None:
        stem = _clean_stem(path)
        m = re.search(r"v(\d+\.\d+|\d+)", stem)
        return m.group(1) if m else None


class NroParser(RomFormatParser):
    def supports(self, path: Path) -> bool:
        return path.suffix.lower() == _NRO_EXTENSION

    def parse_title_id(self, path: Path) -> str | None:
        return _title_id_from_parent(path)

    def parse_content_kind(self, path: Path) -> str:
        return "base"

    def parse_version(self, path: Path) -> str | None:
        return None


def _clean_stem(path: Path) -> str:
    return _SCENE_BRACKETS.sub("", path.stem).strip()


def _title_id_from_parent(path: Path) -> str | None:
    for parent in path.parents:
        match = _TITLE_ID_RE.search(parent.name)
        if match:
            return match.group(0).upper()
    return None


def _is_update_tid(tid: str) -> bool:
    suffix = int(tid[-2:], 16)
    return 0x800 <= suffix < 0xFFF


def _is_dlc_tid(tid: str) -> bool:
    suffix = int(tid[-4:-2], 16)
    return suffix >= 0x80


def all_parsers() -> list[RomFormatParser]:
    return [NspParser(), XciParser(), NroParser()]


def allowed_extension(path: Path) -> bool:
    return path.suffix.lower() in _ALLOWED_EXTENSIONS
