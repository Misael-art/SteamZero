# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Costura (Onda 6): ações de melhoria e aplicação pré-argv no controlador."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

import steamzero.adapters.emulation as emulation_mod
from steamzero.adapters.emulation import EmulationController, _valid_cached_title_id
from steamzero.adapters.enhancements.renderers import ENHANCEMENT_MARKER
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore
from steamzero.domain.launch_profile import parse_launch


def _controller(monkeypatch, tmp_path: Path) -> EmulationController:  # type: ignore[no-untyped-def]
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: home))
    monkeypatch.setenv("XDG_STATE_HOME", str(home / ".local" / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(home / ".local" / "share"))
    # XDG_CONFIG_HOME é de escopo session no conftest: sem sobrescrever aqui,
    # emulation-games-v1.json e o diretório de melhorias seriam compartilhados
    # por toda a suíte, e um teste herdaria o estado do anterior.
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    return EmulationController(
        store_factory=lambda: StateStore(tmp_path / "state.db"),
        which=lambda _command: None,
        spawn=lambda _argv: None,
        secret_store=emulation_mod.SessionSecretStore(),
    )


def _apply(controller: EmulationController, plan: dict[str, object]) -> dict[str, object]:
    return controller.apply_action(str(plan["planId"]), str(plan["confirmToken"]))


def _duckstation_target_dir(tmp_path: Path) -> Path:
    """Diretório que o manifesto REAL do DuckStation resolve sob o XDG do teste.

    Nenhum stub: `duckstation.adapter.json` declara `enhancements` e
    `paths.enhancementsDir`, então o controlador resolve o alvo em produção
    exatamente como aqui. Se a declaração sumir do manifesto, estes testes
    quebram — que é o ponto.
    """
    return tmp_path / "home" / ".config" / "duckstation" / "gamesettings"


def _mark_duckstation_supplied(controller: EmulationController, kinds: tuple[str, ...]) -> None:
    """Declara `emulator-supplied` no manifesto REAL, sem trocar o resolver.

    Envolve o registry num wrapper em vez de mutá-lo: `AdapterRegistry.bundled()`
    é `lru_cache`, então atribuir `registry.get` vazaria o papel para todos os
    testes seguintes da sessão.
    """
    original_factory = controller._registry_factory  # type: ignore[attr-defined]

    class _Wrapper:
        def __init__(self, inner) -> None:  # type: ignore[no-untyped-def]
            self._inner = inner

        def __getattr__(self, name: str):  # type: ignore[no-untyped-def]
            return getattr(self._inner, name)

        def get(self, adapter_id: str):  # type: ignore[no-untyped-def]
            manifest = self._inner.get(adapter_id)
            if adapter_id != "duckstation":
                return manifest
            raw = dict(manifest.raw)
            raw["enhancements"] = dict(raw.get("enhancements") or {})
            raw["enhancements"]["supplied"] = list(kinds)
            return replace(manifest, raw=raw)

    controller._registry_factory = lambda: _Wrapper(original_factory())  # type: ignore[attr-defined]


def _seed_psx_game(controller: EmulationController, tmp_path: Path) -> dict[str, object]:
    """Jogo de PlayStation real — o par natural do DuckStation.

    O par antigo (jogo Switch + DuckStation) só era possível porque o alvo era
    stubado: sem serial de disco, um override do DuckStation não faz sentido.
    A imagem carrega um PVD ISO9660 com o serial em 0x20, que é exatamente o
    que os leitores da Onda 1 consomem — nenhuma identidade é injetada.
    """
    root = tmp_path / "platform-roms"
    psx = root / "PSX"
    psx.mkdir(parents=True)
    pvd = bytearray(2048)
    pvd[0] = 1
    pvd[1:6] = b"CD001"
    pvd[6] = 1
    pvd[0x20:0x2B] = b"SLUS_005.55"
    image = bytearray(0x8000)
    image[0x8000:0x8800] = pvd
    (psx / "Example.iso").write_bytes(bytes(image))
    _apply(
        controller,
        controller.plan_action({"actionId": "library.root.add", "path": str(root)}),
    )
    scan = controller.scan_library()
    if scan["games"] != 1:
        raise AssertionError(f"jogo PSX não foi inventariado: {scan}")
    cached = json.loads(
        controller._library_cache_path.read_text(encoding="utf-8")  # type: ignore[attr-defined]
    )
    game = cached["games"][0]
    if game.get("identityScheme") != "psx-serial":
        raise AssertionError(f"identidade PSX não resolvida: {game}")
    return game


def _seed_switch_game(controller: EmulationController, tmp_path: Path) -> dict[str, object]:
    roms = tmp_path / "owned-roms"
    roms.mkdir()
    rom = roms / "Example [0100ABCDEF123000].nsp"
    rom.write_bytes(b"owned-game")
    _apply(
        controller,
        controller.plan_action({"actionId": "library.root.add", "path": str(roms)}),
    )
    games, _unidentified = controller._load_library_cache()  # type: ignore[attr-defined]
    if not games:
        raise AssertionError("jogo Switch não foi inventariado")
    return games[0]


def _launch_ready(monkeypatch, controller: EmulationController, tmp_path: Path) -> None:
    monkeypatch.setattr(controller, "_require_launchable_emulator", lambda _id: None)
    monkeypatch.setattr(controller, "_require_key_projection", lambda _id: None)
    monkeypatch.setattr(
        controller,
        "_launch_profile_for",
        lambda _platform_id, adapter_id: parse_launch(
            "switch", adapter_id, {"gameArgs": ["{rom}"]}
        ),
    )
    monkeypatch.setattr(
        "steamzero.adapters.emulation.AdapterEngine.payload_path",
        lambda _self, emulator_id: tmp_path / f"{emulator_id}.AppImage",
    )


def test_enhancement_seam_applies_before_argv_idempotent_and_managed(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    assert ENHANCEMENT_MARKER.startswith("# SteamZero-Boot-Managed")
    controller = _controller(monkeypatch, tmp_path)
    game = _seed_psx_game(controller, tmp_path)
    game_id = str(game["id"])
    _apply(
        controller,
        controller.plan_action(
            {"actionId": "game.emulator.set", "gameId": game_id, "emulatorId": "duckstation"}
        ),
    )
    _apply(
        controller,
        controller.plan_action(
            {
                "actionId": f"game.enhancements.set:{game_id}",
                "emulatorId": "duckstation",
                "kind": "mod",
                "category": "performance",
                "title": "60 FPS",
                "source": "forum",
                "settingLines": ["Renderer = Vulkan"],
            }
        ),
    )
    [definition] = controller._load_game_settings(strict=True)[game_id][  # type: ignore[attr-defined]
        "enhancements"
    ]
    assert definition["title"] == "60 FPS"

    _launch_ready(monkeypatch, controller, tmp_path)
    launched: list[tuple[str, ...]] = []
    controller._spawn = lambda argv: launched.append(tuple(argv))  # type: ignore[attr-defined]
    first = controller.launch_game(game_id)
    assert first["status"] == "started"
    assert first["enhancementsTried"] == 1
    assert first["enhancementsApplied"] == 1
    assert first["enhancementsSkipped"] == []
    rules = tmp_path / "home" / ".config" / "duckstation" / "gamesettings" / "SLUS_005.55.ini"
    content = rules.read_text(encoding="ascii")
    assert content.startswith(ENHANCEMENT_MARKER)
    assert "Renderer = Vulkan" in content

    second = controller.launch_game(game_id)
    assert second["enhancementsApplied"] == 1
    assert second["enhancementsSkipped"] == []
    assert rules.read_text(encoding="ascii") == content


def test_enhancement_launch_degrades_on_render_failure(monkeypatch, tmp_path: Path) -> None:
    controller = _controller(monkeypatch, tmp_path)
    game = _seed_psx_game(controller, tmp_path)
    game_id = str(game["id"])
    _apply(
        controller,
        controller.plan_action(
            {"actionId": "game.emulator.set", "gameId": game_id, "emulatorId": "duckstation"}
        ),
    )
    _apply(
        controller,
        controller.plan_action(
            {
                "actionId": f"game.enhancements.set:{game_id}",
                "emulatorId": "duckstation",
                "kind": "mod",
                "category": "graphics",
                "title": "Widescreen",
                "source": "forum",
                "settingLines": ["Renderer = Vulkan"],
            }
        ),
    )
    import steamzero.adapters.enhancements.installer as installer_mod

    def boom(*_args, **_kwargs):
        raise SteamZeroError("E-ENHANCEMENT-DENIED", detail="renderer indisponível")

    monkeypatch.setattr(installer_mod, "render_file", boom)
    _launch_ready(monkeypatch, controller, tmp_path)
    controller._spawn = lambda _argv: 4242  # type: ignore[attr-defined]
    result = controller.launch_game(game_id)
    assert result["status"] == "started"
    assert result["enhancementsApplied"] == 0
    assert (
        result["enhancementsSkipped"][0]["reason"] == "E-ENHANCEMENT-DENIED: renderer indisponível"
    )
    assert not (
        tmp_path / "home" / ".config" / "duckstation" / "gamesettings" / "SLUS_005.55.ini"
    ).exists()


def test_enhancement_set_denies_gameplay_category_and_unmanaged_emulator(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    game = _seed_psx_game(controller, tmp_path)
    game_id = str(game["id"])
    _apply(
        controller,
        controller.plan_action(
            {"actionId": "game.emulator.set", "gameId": game_id, "emulatorId": "duckstation"}
        ),
    )
    with pytest.raises(SteamZeroError, match="E-ENHANCEMENT-DENIED"):
        controller.plan_action(
            {
                "actionId": f"game.enhancements.set:{game_id}",
                "emulatorId": "duckstation",
                "kind": "cheat",
                "category": "gameplay",
                "title": "Infinitas vidas",
                "source": "forum",
                "settingLines": ["Renderer = Vulkan"],
            }
        )
    with pytest.raises(SteamZeroError, match="não declara suporte"):
        controller.plan_action(
            {
                "actionId": f"game.enhancements.set:{game_id}",
                "emulatorId": "ryubing",
                "kind": "mod",
                "category": "performance",
                "title": "60 FPS",
                "source": "forum",
                "settingLines": ["Renderer = Vulkan"],
            }
        )


def test_enhancement_launch_never_touches_foreign_file_and_clear_removes(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    game = _seed_psx_game(controller, tmp_path)
    game_id = str(game["id"])
    _apply(
        controller,
        controller.plan_action(
            {"actionId": "game.emulator.set", "gameId": game_id, "emulatorId": "duckstation"}
        ),
    )
    _apply(
        controller,
        controller.plan_action(
            {
                "actionId": f"game.enhancements.set:{game_id}",
                "emulatorId": "duckstation",
                "kind": "mod",
                "category": "display-only",
                "title": "Widescreen",
                "source": "forum",
                "settingLines": ["Renderer = Vulkan"],
            }
        ),
    )
    rules = tmp_path / "home" / ".config" / "duckstation" / "gamesettings" / "SLUS_005.55.ini"
    rules.parent.mkdir(parents=True)
    rules.write_text("# feito a mao pelo usuario\n", encoding="ascii")
    _launch_ready(monkeypatch, controller, tmp_path)
    controller._spawn = lambda _argv: 4242  # type: ignore[attr-defined]
    result = controller.launch_game(game_id)
    assert result["status"] == "started"
    assert result["enhancementsApplied"] == 0
    assert result["enhancementsSkipped"][0]["reason"].startswith("arquivo sem marcador")
    assert rules.read_text(encoding="ascii") == "# feito a mao pelo usuario\n"

    _apply(
        controller,
        controller.plan_action(
            {"actionId": f"game.enhancements.clear:{game_id}", "title": "Widescreen"}
        ),
    )
    after = controller.launch_game(game_id)
    assert after["enhancementsTried"] == 0
    assert after["enhancementsApplied"] == 0


def test_enhancement_emulator_supplied_role_is_never_written_by_steamzero(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    _mark_duckstation_supplied(controller, ("mod",))
    game = _seed_psx_game(controller, tmp_path)
    game_id = str(game["id"])
    _apply(
        controller,
        controller.plan_action(
            {"actionId": "game.emulator.set", "gameId": game_id, "emulatorId": "duckstation"}
        ),
    )
    with pytest.raises(SteamZeroError, match="é dono do arquivo"):
        controller.plan_action(
            {
                "actionId": f"game.enhancements.set:{game_id}",
                "emulatorId": "duckstation",
                "kind": "mod",
                "category": "performance",
                "title": "60 FPS",
                "source": "forum",
                "settingLines": ["Renderer = Vulkan"],
            }
        )


def test_settings_reject_unknown_enhancement_fields_with_integrity_error(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    game = _seed_psx_game(controller, tmp_path)
    game_id = str(game["id"])
    import json

    controller._game_settings_path.write_text(  # type: ignore[attr-defined]
        json.dumps(
            {"schemaVersion": 1, "games": {game_id: {"enhancements": [{"evil": True}]}}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    with pytest.raises(SteamZeroError, match="E-STATE-INTEGRITY"):
        controller.launch_game(game_id)

    # XDG_CONFIG_HOME é de escopo session no conftest, então este arquivo é
    # compartilhado por toda a suíte: sem a limpeza, qualquer teste posterior
    # que leia as preferências herda o payload corrompido acima.
    controller._game_settings_path.unlink()  # type: ignore[attr-defined]


def test_enhancement_file_exists_on_disk_before_argv_is_built(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    """A melhoria precisa estar no disco QUANDO o argv é montado.

    Aplicar só antes do spawn não basta: uma melhoria que precise influenciar o
    próprio comando (core override, flag de shader) constaria como aplicada sem
    efeito no lançamento. Este teste observa o disco no instante da montagem do
    argv, em vez de espionar a ordem das chamadas — o que provaria apenas que os
    stubs foram chamados em sequência.
    """
    controller = _controller(monkeypatch, tmp_path)
    game = _seed_psx_game(controller, tmp_path)
    game_id = str(game["id"])
    _apply(
        controller,
        controller.plan_action(
            {"actionId": "game.emulator.set", "gameId": game_id, "emulatorId": "duckstation"}
        ),
    )
    _apply(
        controller,
        controller.plan_action(
            {
                "actionId": f"game.enhancements.set:{game_id}",
                "emulatorId": "duckstation",
                "kind": "mod",
                "category": "performance",
                "title": "60 FPS",
                "source": "forum",
                "settingLines": ["Renderer = Vulkan"],
            }
        ),
    )

    _launch_ready(monkeypatch, controller, tmp_path)
    controller._spawn = lambda argv: None  # type: ignore[attr-defined]
    rules = tmp_path / "home" / ".config" / "duckstation" / "gamesettings" / "SLUS_005.55.ini"
    assert not rules.exists()

    seen_at_argv_time: list[bool] = []
    original = controller._build_exec_argv  # type: ignore[attr-defined]

    def _recording(*args, **kwargs):  # type: ignore[no-untyped-def]
        seen_at_argv_time.append(rules.exists())
        return original(*args, **kwargs)

    controller._build_exec_argv = _recording  # type: ignore[attr-defined]
    result = controller.launch_game(game_id)

    assert result["enhancementsApplied"] == 1
    assert seen_at_argv_time == [True], (
        "a melhoria não estava no disco quando o argv foi montado: "
        "aplicação ocorreu depois de _build_exec_argv"
    )


def test_non_switch_identity_survives_library_cache_load(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    """Jogo não-Switch identificado precisa SOBREVIVER ao carregamento.

    `_TITLE_ID` é o formato do Switch (16 hex). Como a Onda 1 grava a identidade
    de qualquer plataforma em `titleId`, validar tudo contra esse padrão fazia a
    varredura achar o jogo, gravar no cache e o carregamento descartá-lo: o jogo
    nunca aparecia na biblioteca nem podia ser lançado. Era esse defeito que o
    alvo stubado (com jogo Switch) escondia.
    """
    controller = _controller(monkeypatch, tmp_path)
    game = _seed_psx_game(controller, tmp_path)
    assert game["titleId"] == "SLUS_005.55"
    assert game["identityScheme"] == "psx-serial"

    games, _unidentified = controller._load_library_cache()  # type: ignore[attr-defined]
    assert [g["titleId"] for g in games] == ["SLUS_005.55"], (
        "identidade não-Switch foi descartada no carregamento da biblioteca"
    )


def test_cached_title_id_rejects_unknown_scheme_and_mismatched_value(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    """O valor vira nome de arquivo de melhoria: validação não pode afrouxar.

    `IdentityScheme.UNKNOWN` casa com qualquer coisa por construção, então é
    recusado explicitamente; valor que não bate com o esquema declarado também.
    """
    assert _valid_cached_title_id("SLUS_005.55", "psx-serial") is True
    assert _valid_cached_title_id("GM8E01", "gc-game-id") is True
    assert _valid_cached_title_id("0100ABCDEF123000", None) is True
    # UNKNOWN aceitaria travessia de caminho se fosse consultado pelo padrão.
    assert _valid_cached_title_id("../../etc/passwd", "unknown") is False
    assert _valid_cached_title_id("../../etc/passwd", "psx-serial") is False
    assert _valid_cached_title_id("SLUS_005.55", "switch-title-id") is False
    assert _valid_cached_title_id("qualquer", "esquema-inexistente") is False
