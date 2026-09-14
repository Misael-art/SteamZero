# SPDX-License-Identifier: GPL-3.0-or-later

import json
from pathlib import Path

from steamzero.adapters.launcher_media import launcher_media_metadata

_PNG = b"\x89PNG\r\n\x1a\nfixture"


def _registry(path: Path, entries: list[dict[str, object]]) -> None:
    path.write_text(json.dumps({"entries": entries}), encoding="utf-8")


def test_projects_canonical_media_into_cinema_roles(tmp_path: Path) -> None:
    root = tmp_path / "media"
    cover = root / "masters" / "nes" / "box2d" / "cover.png"
    hero = root / "masters" / "nes" / "hero" / "hero.jpg"
    screenshot = root / "optimized" / "nes" / "screenshot" / "shot.png"
    for path in (cover, hero, screenshot):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_PNG)
    registry = root / "registry" / "assignments-v1.json"
    registry.parent.mkdir()
    _registry(
        registry,
        [
            {
                "gameId": "game-1",
                "masters": {
                    "box2d": "masters/nes/box2d/cover.png",
                    "hero": "masters/nes/hero/hero.jpg",
                    "screenshot": "optimized/nes/screenshot/shot.png",
                },
            }
        ],
    )

    assert launcher_media_metadata(media_root=root) == {
        "game-1": {
            "coverUrl": f"file://{cover}",
            "fanartUrl": f"file://{hero}",
            "screenshotUrls": [f"file://{screenshot}"],
        }
    }


def test_rejects_paths_outside_managed_root_and_symlinks(tmp_path: Path) -> None:
    root = tmp_path / "media"
    safe = root / "masters" / "nes" / "box2d" / "safe.png"
    safe.parent.mkdir(parents=True)
    safe.write_bytes(_PNG)
    outside = tmp_path / "private.png"
    outside.write_bytes(_PNG)
    link = root / "masters" / "nes" / "box2d" / "link.png"
    link.symlink_to(outside)
    registry = root / "registry" / "assignments-v1.json"
    registry.parent.mkdir()
    _registry(
        registry,
        [
            {
                "gameId": "game-1",
                "masters": {
                    "box2d": "masters/nes/box2d/../box2d/safe.png",
                    "hero": str(outside),
                    "screenshot": "masters/nes/box2d/link.png",
                },
            }
        ],
    )

    assert launcher_media_metadata(media_root=root) == {}


def test_malformed_or_missing_registry_degrades_to_empty(tmp_path: Path) -> None:
    root = tmp_path / "media"
    assert launcher_media_metadata(media_root=root) == {}
    registry = root / "registry" / "assignments-v1.json"
    registry.parent.mkdir(parents=True)
    registry.write_text("not-json", encoding="utf-8")
    assert launcher_media_metadata(media_root=root) == {}
