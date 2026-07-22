from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from steamzero.core import fs


@dataclass(frozen=True)
class PlatformEntry:
    slug: str
    name: str
    kinds: tuple[str, ...] = ("box2d", "hero", "logo", "icon", "screenshot")


@dataclass(frozen=True)
class Provenance:
    provider: str
    source_url: str
    license: str = ""
    attribution: str = ""
    downloaded_at: str = ""
    hash_sha256: str = ""


@dataclass(frozen=True)
class MediaMasterEntry:
    game_id: str
    title_id: str
    fingerprint: str
    canonical_name: str
    aliases: tuple[str, ...] = ()
    region: str = ""
    language: str = ""
    version: str = ""
    metadata_origin: str = ""
    confirmed: bool = False
    steam_appid: int | None = None
    provenance: Provenance | None = None

    def to_dict(self) -> dict[str, object]:
        d: dict[str, object] = {
            "gameId": self.game_id,
            "titleId": self.title_id,
            "fingerprint": self.fingerprint,
            "canonicalName": self.canonical_name,
            "aliases": list(self.aliases),
            "region": self.region,
            "language": self.language,
            "version": self.version,
            "metadataOrigin": self.metadata_origin,
            "confirmed": self.confirmed,
            "steamAppid": self.steam_appid,
        }
        if self.provenance:
            d["provenance"] = {
                "provider": self.provenance.provider,
                "sourceUrl": self.provenance.source_url,
                "license": self.provenance.license,
                "attribution": self.provenance.attribution,
                "downloadedAt": self.provenance.downloaded_at,
                "hashSha256": self.provenance.hash_sha256,
            }
        return d

    @staticmethod
    def from_dict(d: dict[str, Any]) -> MediaMasterEntry:
        prov_data = d.get("provenance")
        provenance = None
        if prov_data:
            provenance = Provenance(
                provider=prov_data.get("provider", ""),
                source_url=prov_data.get("sourceUrl", ""),
                license=prov_data.get("license", ""),
                attribution=prov_data.get("attribution", ""),
                downloaded_at=prov_data.get("downloadedAt", ""),
                hash_sha256=prov_data.get("hashSha256", ""),
            )
        return MediaMasterEntry(
            game_id=d.get("gameId", ""),
            title_id=d.get("titleId", ""),
            fingerprint=d.get("fingerprint", ""),
            canonical_name=d.get("canonicalName", ""),
            aliases=tuple(d.get("aliases", [])),
            region=d.get("region", ""),
            language=d.get("language", ""),
            version=d.get("version", ""),
            metadata_origin=d.get("metadataOrigin", ""),
            confirmed=d.get("confirmed", False),
            steam_appid=d.get("steamAppid"),
            provenance=provenance,
        )


@dataclass
class MediaRegistry:
    platforms: dict[str, PlatformEntry] = field(default_factory=dict)
    entries: dict[str, MediaMasterEntry] = field(default_factory=dict)

    @staticmethod
    def load(root: Path) -> MediaRegistry:
        reg_path = root / "registry" / "platforms-v1.json"
        entries_path = root / "registry" / "assignments-v1.json"
        registry = MediaRegistry()
        if reg_path.is_file():
            data = json.loads(reg_path.read_text(encoding="utf-8"))
            for slug, pdata in data.get("platforms", {}).items():
                registry.platforms[slug] = PlatformEntry(
                    slug=slug,
                    name=pdata.get("name", slug),
                    kinds=tuple(pdata.get("kinds", [])),
                )
        if entries_path.is_file():
            data = json.loads(entries_path.read_text(encoding="utf-8"))
            for entry_dict in data.get("entries", []):
                entry = MediaMasterEntry.from_dict(entry_dict)
                registry.entries[entry.game_id] = entry
        return registry

    def save(self, root: Path) -> None:
        fs.ensure_dir(root)
        reg_path = root / "registry"
        fs.ensure_dir(reg_path)
        platform_data = {
            slug: {"name": p.name, "kinds": list(p.kinds)}
            for slug, p in self.platforms.items()
        }
        fs.write_atomic_text(
            reg_path / "platforms-v1.json",
            json.dumps({"platforms": platform_data}, indent=2, ensure_ascii=False),
        )
        entries_list = [e.to_dict() for e in self.entries.values()]
        fs.write_atomic_text(
            reg_path / "assignments-v1.json",
            json.dumps({"entries": entries_list}, indent=2, ensure_ascii=False),
        )

    def register_platform(self, slug: str, name: str, kinds: tuple[str, ...]) -> None:
        self.platforms[slug] = PlatformEntry(slug=slug, name=name, kinds=kinds)

    def add_entry(self, entry: MediaMasterEntry) -> None:
        self.entries[entry.game_id] = entry

    def get_entry(self, game_id: str) -> MediaMasterEntry | None:
        return self.entries.get(game_id)

    def remove_entry(self, game_id: str) -> None:
        self.entries.pop(game_id, None)
