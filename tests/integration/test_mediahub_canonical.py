# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""MediaHub canônico E2E (etapa 8): masters -> optimized -> views com
associação por hash, órfãos detectados e snapshot validado contra o schema
público ``media-registry-v1``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import ValidationError

from steamzero.api import contracts
from steamzero.domain.media_pipeline import MediaPipeline
from steamzero.domain.media_registry import MediaMasterEntry, Provenance
from steamzero.ports import MediaCandidate

_PNG = b"\x89PNG\r\n\x1a\n" + b"synthetic-png-body"
_JPG = b"\xff\xd8\xff" + b"synthetic-jpeg-body"

_SCHEMA_ID = "media-registry-v1.schema.json"


def _import_master(pipeline: MediaPipeline, game_id: str, kind: str, data: bytes) -> Path:
    src = pipeline._media_root / f"src-{game_id}-{kind}.png"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(data)
    result = pipeline.collect(
        source=src,
        game_id=game_id,
        title_id=f"0100{game_id.upper()[-12:]}",
        fingerprint=f"fp-{game_id}",
        canonical_name=f"Game {game_id}",
        kind=kind,
    )
    assert result.success, result.failed
    return next(iter(result.collected.values()))


def _optimize_tool(src: Path, dst: Path, _profile: str) -> bool:
    dst.write_bytes(src.read_bytes())
    return True


def _valid_png(path: Path) -> None:
    assert path.is_file()
    assert path.read_bytes().startswith(_PNG)


@pytest.mark.integration
@pytest.mark.rt
def test_mediahub_canonical_flow_with_hash_association(tmp_path: Path) -> None:
    pipeline = MediaPipeline(
        tmp_path / "media",
        optimizer_tool=_optimize_tool,
        candidate_fetcher=lambda url: _PNG,
    )

    master_a = _import_master(pipeline, "GAME-A", "box2d", _PNG)
    _import_master(pipeline, "GAME-B", "icon", _PNG + b"b")

    snapshot = pipeline.registry_snapshot()
    assert contracts.is_valid(snapshot, _SCHEMA_ID)
    contracts.validate(snapshot, _SCHEMA_ID)

    assert snapshot["schemaVersion"] == 1
    entries = snapshot["entries"]
    assert set(entries) == {"GAME-A", "GAME-B"}
    assert (
        entries["GAME-A"]["masters"]["box2d"]["relPath"]
        == master_a.relative_to(tmp_path / "media").as_posix()
    )
    sha_a = entries["GAME-A"]["masters"]["box2d"]["sha256"]
    assert len(sha_a) == 64

    index = snapshot["hashIndex"]
    assert index[sha_a] == ["GAME-A"]

    optimized = pipeline.optimize("GAME-A")
    assert optimized.success, optimized.failed
    snapshot2 = pipeline.registry_snapshot()
    contracts.validate(snapshot2, _SCHEMA_ID)
    assert "steam-portrait" in snapshot2["optimized"]["GAME-A"]
    assert "steam-landscape" in snapshot2["optimized"]["GAME-A"]


@pytest.mark.integration
@pytest.mark.rt
def test_mediahub_hash_index_associates_shared_master(tmp_path: Path) -> None:
    pipeline = MediaPipeline(tmp_path / "media", optimizer_tool=_optimize_tool)
    _import_master(pipeline, "GAME-A", "box2d", _PNG)
    _import_master(pipeline, "GAME-B", "icon", _PNG)

    snapshot = pipeline.registry_snapshot()
    sha_a = snapshot["entries"]["GAME-A"]["masters"]["box2d"]["sha256"]
    sha_b = snapshot["entries"]["GAME-B"]["masters"]["icon"]["sha256"]

    assert sha_a == sha_b
    assert snapshot["hashIndex"][sha_a] == ["GAME-A", "GAME-B"]

    different = pipeline._media_root / "different.png"
    different.write_bytes(_PNG + b"distinct")
    result = pipeline.collect(
        source=different,
        game_id="GAME-C",
        title_id="0100GAMEC",
        fingerprint="fp-c",
        canonical_name="Game C",
        kind="box2d",
    )
    assert result.success
    snapshot3 = pipeline.registry_snapshot()
    sha_c = snapshot3["entries"]["GAME-C"]["masters"]["box2d"]["sha256"]
    assert sha_c != sha_a
    assert snapshot3["hashIndex"][sha_c] == ["GAME-C"]
    assert snapshot3["hashIndex"][sha_a] == ["GAME-A", "GAME-B"]


@pytest.mark.integration
@pytest.mark.rt
def test_mediahub_snapshot_detects_orphans_and_broken_views(tmp_path: Path) -> None:
    pipeline = MediaPipeline(tmp_path / "media", optimizer_tool=_optimize_tool)
    _import_master(pipeline, "GAME-A", "box2d", _PNG)

    orphan_master = tmp_path / "media" / "masters" / "switch" / "icon" / "orphan.png"
    orphan_master.parent.mkdir(parents=True, exist_ok=True)
    orphan_master.write_bytes(_JPG)

    optimized = pipeline.optimize("GAME-A")
    assert optimized.success, optimized.failed

    views_root = tmp_path / "media" / "views" / "steam" / "steam-user-1" / "grid"
    result = pipeline.view_steam("GAME-A", "steam-user-1", 12345, grid_dir=views_root)
    assert result.success, result.failed
    broken = views_root / "99999.png"
    absent = tmp_path / "media" / "optimized" / "switch" / "steam-landscape" / "absent.png"
    broken.symlink_to(absent)
    assert not broken.exists()

    snapshot = pipeline.registry_snapshot()
    contracts.validate(snapshot, _SCHEMA_ID)
    orphans = snapshot["orphans"]
    assert any("orphan.png" in rel for rel in orphans["masterFiles"])
    assert orphans["optimizedFiles"] == []
    assert len(orphans["brokenViewLinks"]) == 1
    assert "views/steam/steam-user-1/grid/" in orphans["brokenViewLinks"][0]


@pytest.mark.integration
@pytest.mark.rt
def test_mediahub_snapshot_validates_through_registry_entry_types(tmp_path: Path) -> None:
    pipeline = MediaPipeline(tmp_path / "media")
    pipeline._registry.register_platform(
        "switch",
        "Switch",
        ("box2d", "hero", "logo", "icon", "screenshot"),
    )
    pipeline._registry.add_entry(
        MediaMasterEntry(
            game_id="GAME-A",
            title_id="0100GAMEAAA",
            fingerprint="fp-a",
            canonical_name="Game A",
            confirmed=True,
            metadata_origin="scraper",
            steam_appid=12345,
            provenance=Provenance(
                provider="test-provider",
                source_url="https://media.invalid/a.png",
                license="CC0-1.0",
                attribution="Fixture",
                hash_sha256="a" * 64,
            ),
            masters={
                "box2d": "masters/switch/box2d/" + "a" * 64 + ".png",
            },
        )
    )
    pipeline._registry.save(pipeline._media_root)

    snapshot = pipeline.registry_snapshot()
    contracts.validate(snapshot, _SCHEMA_ID)
    entry = snapshot["entries"]["GAME-A"]
    assert entry["metadataOrigin"] == "scraper"
    assert entry["steamAppid"] == 12345
    assert entry["provenance"]["provider"] == "test-provider"
    assert entry["provenance"]["hashSha256"] == "a" * 64
    assert snapshot["platforms"]["switch"]["name"] == "Switch"


@pytest.mark.integration
@pytest.mark.rt
def test_mediahub_snapshot_without_entries_is_still_valid(tmp_path: Path) -> None:
    snapshot = MediaPipeline(tmp_path / "media").registry_snapshot()
    contracts.validate(snapshot, _SCHEMA_ID)
    assert snapshot["entries"] == {}
    assert snapshot["hashIndex"] == {}
    assert snapshot["optimized"] == {}
    assert snapshot["views"] == {}
    assert snapshot["orphans"] == {
        "masterFiles": [],
        "optimizedFiles": [],
        "brokenViewLinks": [],
    }


@pytest.mark.golden
def test_mediahub_snapshot_registry_writes_schema_valid_file(tmp_path: Path) -> None:
    pipeline = MediaPipeline(tmp_path / "media")
    _import_master(pipeline, "GAME-A", "box2d", _PNG)
    snapshot = pipeline.registry_snapshot()
    payload = json.dumps(snapshot, sort_keys=True, ensure_ascii=False)
    assert json.loads(payload)["entries"]["GAME-A"]["canonicalName"] == "Game GAME-A"


@pytest.mark.golden
def test_mediahub_contract_rejects_invalid_snapshot() -> None:
    invalid = {
        "schemaVersion": 2,
        "generatedAt": "not-a-date",
        "platforms": {},
        "entries": {},
        "hashIndex": {},
        "optimized": {},
        "views": {},
        "orphans": {
            "masterFiles": [],
            "optimizedFiles": [],
            "brokenViewLinks": [],
        },
    }
    with pytest.raises(ValidationError):
        contracts.validate(invalid, _SCHEMA_ID)


@pytest.mark.golden
def test_mediahub_candidate_collection_records_provenance_hash(tmp_path: Path) -> None:
    pipeline = MediaPipeline(
        tmp_path / "media",
        candidate_fetcher=lambda url: _JPG,
    )
    candidate = MediaCandidate(
        url="https://media.invalid/cover.jpg",
        media_kind="boxart",
        provider="fixture",
        confidence=0.9,
        license="CC0-1.0",
        attribution="Fixture",
    )
    result = pipeline.collect_from_candidate(
        candidate=candidate,
        game_id="GAME-A",
        title_id="0100GAMEAAA",
        fingerprint="fp-a",
        canonical_name="Game A",
    )
    assert result.success, result.failed
    entry = pipeline.get_registry_entry("GAME-A")
    assert entry is not None and entry.provenance is not None
    assert entry.provenance.provider == "fixture"
    assert entry.provenance.hash_sha256 == entry.masters["box2d"].rsplit("/", 1)[-1].split(".")[0]
    snapshot = pipeline.registry_snapshot()
    contracts.validate(snapshot, _SCHEMA_ID)
    assert snapshot["entries"]["GAME-A"]["provenance"]["hashSha256"] == entry.provenance.hash_sha256
