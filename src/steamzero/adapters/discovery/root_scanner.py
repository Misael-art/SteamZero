from __future__ import annotations

from pathlib import Path

from steamzero.ports import RomDiscoveryResult, RomFormatParser, RomRootDiscoveryPort

from .format_parsers import all_parsers, allowed_extension


class RomRootScanner(RomRootDiscoveryPort):
    def __init__(self, parsers: list[RomFormatParser] | None = None) -> None:
        self._parsers = parsers or all_parsers()

    def discover(self, root: Path) -> list[RomDiscoveryResult]:
        if not root.is_dir() or root.is_symlink():
            return []
        results: list[RomDiscoveryResult] = []
        for entry in root.iterdir():
            if entry.is_symlink() or entry.is_dir():
                continue
            if not entry.is_file():
                continue
            if not allowed_extension(entry):
                continue
            size = entry.stat().st_size
            parser = self._parser_for(entry)
            if parser is None:
                continue
            title_id = parser.parse_title_id(entry)
            kind = parser.parse_content_kind(entry)
            version = parser.parse_version(entry)
            results.append(
                RomDiscoveryResult(
                    path=entry,
                    fmt=entry.suffix.lower().lstrip("."),
                    title_id=title_id,
                    content_kind=kind,
                    size_bytes=size,
                    parent_title_id=_parent_for_kind(kind, title_id),
                    version=version,
                )
            )
        return results

    def discover_recursive(self, root: Path) -> list[RomDiscoveryResult]:
        if not root.is_dir() or root.is_symlink():
            return []
        results: list[RomDiscoveryResult] = []
        for entry in sorted(root.rglob("*")):
            if entry.is_symlink() or entry.is_dir():
                continue
            if not entry.is_file():
                continue
            if not allowed_extension(entry):
                continue
            size = entry.stat().st_size
            parser = self._parser_for(entry)
            if parser is None:
                continue
            title_id = parser.parse_title_id(entry)
            kind = parser.parse_content_kind(entry)
            version = parser.parse_version(entry)
            results.append(
                RomDiscoveryResult(
                    path=entry,
                    fmt=entry.suffix.lower().lstrip("."),
                    title_id=title_id,
                    content_kind=kind,
                    size_bytes=size,
                    parent_title_id=_parent_for_kind(kind, title_id),
                    version=version,
                )
            )
        return results

    def _parser_for(self, path: Path) -> RomFormatParser | None:
        for p in self._parsers:
            if p.supports(path):
                return p
        return None


def _parent_for_kind(kind: str, title_id: str | None) -> str | None:
    if kind == "base" or title_id is None:
        return None
    return title_id[:14] + "0000"
