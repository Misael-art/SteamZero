from __future__ import annotations

import json
from pathlib import Path

from steamzero.domain.retrofe_media_import import apply_import, collection_platform, plan_import


def _game(game_id: str, name: str, platform: str = "nes-famicom") -> dict[str, object]:
    return {"id": game_id, "name": name, "platform": platform, "fingerprint": f"fp-{game_id}"}


def _asset(root: Path, collection: str, directory: str, name: str, data: bytes = b"png") -> Path:
    path = root / collection / "medium_artwork" / directory / name
    path.parent.mkdir(parents=True)
    path.write_bytes(data)
    return path


def test_collection_platform_rejects_user_collection() -> None:
    assert (
        collection_platform("Nintendo Entertainment System Brazil Games Translated")
        == "nes-famicom"
    )
    assert collection_platform("Main") is None


def test_plan_matches_accents_and_case_without_using_platform_as_guess(tmp_path: Path) -> None:
    _asset(tmp_path, "Nintendo Entertainment System", "fanart", "Pokémon (USA).png")
    plan = plan_import(tmp_path, [_game("g1", "POKEMON (USA)")])
    assert [decision.game_id for decision in plan.accepted] == ["g1"]
    assert plan.accepted[0].asset.kind == "fanart"


def test_plan_rejects_ambiguous_same_title_on_same_platform(tmp_path: Path) -> None:
    _asset(tmp_path, "Nintendo Entertainment System", "fanart", "Game.png")
    plan = plan_import(tmp_path, [_game("g1", "Game"), _game("g2", "Game")])
    assert plan.decisions[0].state == "ambiguous"
    assert plan.decisions[0].reason == "title-match-tie"


def test_plan_keeps_platforms_independent(tmp_path: Path) -> None:
    _asset(tmp_path, "Nintendo Entertainment System", "screentitle", "Astyanax.png")
    plan = plan_import(
        tmp_path,
        [_game("nes", "Astyanax", "nes-famicom"), _game("snes", "Astyanax", "snes")],
    )
    assert plan.accepted[0].game_id == "nes"


def test_plan_ignores_symlink_and_unsupported_asset(tmp_path: Path) -> None:
    source = tmp_path / "outside.png"
    source.write_bytes(b"outside")
    path = _asset(tmp_path, "Nintendo Entertainment System", "fanart", "Safe.png")
    path.unlink()
    path.symlink_to(source)
    _asset(tmp_path, "Nintendo Entertainment System", "story", "Safe.txt", b"text")
    plan = plan_import(tmp_path, [_game("g1", "Safe")])
    assert plan.decisions == ()


def test_apply_publishes_hash_addressed_master_and_registry(tmp_path: Path) -> None:
    source_root = tmp_path / "retrofe"
    _asset(source_root, "Nintendo Entertainment System", "fanart", "Astyanax.png", b"image")
    plan = plan_import(source_root, [_game("g1", "Astyanax")])
    media_root = tmp_path / "media"
    result = apply_import(plan, media_root, {"g1": _game("g1", "Astyanax")})
    assert result.imported == ("g1:fanart",)
    assignment = json.loads(
        (media_root / "registry" / "assignments-v1.json").read_text(encoding="utf-8")
    )["entries"][0]
    assert assignment["platformId"] == "nes-famicom"
    assert assignment["masters"]["fanart"].startswith("masters/nes-famicom/fanart/")


def test_apply_preserves_existing_role_without_replace(tmp_path: Path) -> None:
    source_root = tmp_path / "retrofe"
    _asset(source_root, "Nintendo Entertainment System", "fanart", "Astyanax.png", b"new")
    plan = plan_import(source_root, [_game("g1", "Astyanax")])
    media_root = tmp_path / "media"
    first = apply_import(plan, media_root, {"g1": _game("g1", "Astyanax")})
    second = apply_import(plan, media_root, {"g1": _game("g1", "Astyanax")})
    assert first.imported == ("g1:fanart",)
    assert second.skipped_existing == ("g1:fanart",)


def test_plan_is_read_only(tmp_path: Path) -> None:
    _asset(tmp_path, "Nintendo Entertainment System", "fanart", "Astyanax.png")
    before = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    plan_import(tmp_path, [_game("g1", "Astyanax")])
    after = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    assert before == after
