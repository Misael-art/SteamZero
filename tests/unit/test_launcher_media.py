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


def test_projects_rich_roles_and_numbered_screenshots_deterministically(tmp_path: Path) -> None:
    root = tmp_path / "media"
    files = {
        "cover": root / "masters" / "ps4" / "box2d" / "cover.png",
        "fanart": root / "masters" / "ps4" / "fanart" / "fanart.jpg",
        "shot1": root / "masters" / "ps4" / "screenshot" / "one.png",
        "shot2": root / "masters" / "ps4" / "screenshot" / "two.png",
        "logo": root / "masters" / "ps4" / "logo" / "logo.png",
        "marquee": root / "masters" / "ps4" / "marquee" / "marquee.png",
        "video": root / "masters" / "ps4" / "video" / "intro.mp4",
    }
    for path in files.values():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_PNG)
    registry = root / "registry" / "assignments-v1.json"
    registry.parent.mkdir()
    # Deliberately reverse screenshot order: the projection, not input dict
    # order, owns the order consumed by the detail page.
    _registry(
        registry,
        [
            {
                "gameId": "game-ps4",
                "masters": {
                    "video": "masters/ps4/video/intro.mp4",
                    "screenshot2": "masters/ps4/screenshot/two.png",
                    "logo": "masters/ps4/logo/logo.png",
                    "screenshot": "masters/ps4/screenshot/one.png",
                    "marquee": "masters/ps4/marquee/marquee.png",
                    "fanart": "masters/ps4/fanart/fanart.jpg",
                    "box2d": "masters/ps4/box2d/cover.png",
                },
            }
        ],
    )

    projected = launcher_media_metadata(media_root=root)["game-ps4"]
    assert projected["coverUrl"] == f"file://{files['cover']}"
    assert projected["fanartUrl"] == f"file://{files['fanart']}"
    assert projected["screenshotUrls"] == [
        f"file://{files['shot1']}",
        f"file://{files['shot2']}",
    ]
    assert projected["logoUrl"] == f"file://{files['logo']}"
    assert projected["marqueeUrl"] == f"file://{files['marquee']}"
    assert projected["videoUrl"] == f"file://{files['video']}"


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
