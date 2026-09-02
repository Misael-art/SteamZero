# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contrato do processo do AURA Launcher: o que serve à UI e o que aceita dela."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from steamzero.adapters.launcher_ui import LauncherBridge
from steamzero.launcher.app import build_sections, build_titles, main


def _get(url: str, token: str) -> dict:
    # URL vem do endereço que a própria ponte devolveu, em loopback.
    request = urllib.request.Request(url, headers={"X-SteamZero-Token": token})  # noqa: S310
    with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310
        return json.loads(response.read())


def _post(url: str, token: str, payload: dict) -> int:
    request = urllib.request.Request(  # noqa: S310
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"X-SteamZero-Token": token, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310
        return int(response.status)


def test_the_bridge_serves_the_resolved_model_and_accepts_a_launch(tmp_path: Path) -> None:
    launched: list[tuple[str, str]] = []
    bridge = LauncherBridge(
        sections=build_sections([{"id": "celeste", "title": "Celeste", "section": "library"}]),
        titles=build_titles([{"id": "celeste", "title": "Celeste", "section": "library"}]),
        context_path=tmp_path / "return.json",
        on_launch=lambda game, focus: launched.append((game, focus)),
    )
    with bridge.serving() as base:
        model = _get(f"{base}/model", bridge.token)
        assert model["focusMap"]["initial"] == "library:celeste"
        assert model["sections"][0]["items"][0]["title"] == "Celeste"
        assert (
            _post(
                f"{base}/launch", bridge.token, {"gameId": "celeste", "focusId": "library:celeste"}
            )
            == 204
        )
    assert launched == [("celeste", "library:celeste")]


def test_the_bridge_publishes_context_consumed_by_the_real_entry_point(tmp_path: Path) -> None:
    """A restauração precisa atravessar bridge e QML, não só um harness do shell."""
    bridge = LauncherBridge(
        sections=build_sections([{"id": "celeste", "title": "Celeste", "section": "library"}]),
        titles={"celeste": "Celeste"},
        context_path=tmp_path / "return.json",
        on_launch=lambda game, focus: None,
        return_context={"gameId": "celeste", "focusId": "library:celeste"},
    )
    with bridge.serving() as base:
        model = _get(f"{base}/model", bridge.token)
    assert model["returnContext"] == {"gameId": "celeste", "focusId": "library:celeste"}


def test_the_bridge_refuses_a_request_without_the_token(tmp_path: Path) -> None:
    """Sem token, qualquer processo local dispararia jogos na máquina do usuário."""
    bridge = LauncherBridge(
        sections=build_sections([]),
        context_path=tmp_path / "return.json",
        on_launch=lambda game, focus: None,
    )
    with bridge.serving() as base:
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            _get(f"{base}/model", "token-errado")
        assert excinfo.value.code == 403


def test_an_empty_library_still_opens_with_an_actionable_home(tmp_path: Path) -> None:
    """Abrir vazio é o caso comum na primeira execução, não uma falha."""
    bridge = LauncherBridge(
        sections=build_sections([]),
        context_path=tmp_path / "return.json",
        on_launch=lambda game, focus: None,
    )
    with bridge.serving() as base:
        model = _get(f"{base}/model", bridge.token)
    assert model["focusMap"]["nodes"][model["focusMap"]["initial"]]["action"] == "library.add"
    assert model["focusMap"]["diagnostics"]


def test_the_model_exposes_accessibility_from_the_host(tmp_path: Path) -> None:
    """A acessibilidade herdada chega ao QML via o modelo da ponte.

    O Launcher não lê `kreadconfig6` direto: quem lê é o processo
    (`_host_accessibility` no `app.py`) e entrega aqui, no modelo que o QML
    consome. Sem isso, o alto contraste configurado no Plasma não chegava à
    home fullscreen, que ficava com as cores fixas do tema escuro.
    """
    bridge = LauncherBridge(
        sections=build_sections([]),
        context_path=tmp_path / "return.json",
        on_launch=lambda game, focus: None,
        accessibility={"highContrast": True, "visualScale": 1.0, "reducedMotion": False},
    )
    with bridge.serving() as base:
        model = _get(f"{base}/model", bridge.token)
    assert model["accessibility"]["highContrast"] is True
    assert model["accessibility"]["visualScale"] == 1.0
    assert model["accessibility"]["reducedMotion"] is False


def test_search_filters_by_title_case_insensitive(tmp_path: Path) -> None:
    """A busca filtra a biblioteca por título (case-insensitive) via /search.

    A ponte é quem tem o mapa id->título; a busca vive nela, não no QML. Sem
    isso o Launcher duplicaria o acervo. Devolve o resultado na mesma forma de
    um item de seção (id, title, coverUrl) para a home renderizar.
    """
    tracks = [
        {"id": "celeste", "title": "Celeste", "coverUrl": ""},
        {"id": "tunic", "title": "Tunic", "coverUrl": ""},
    ]
    bridge = LauncherBridge(
        sections=build_sections(tracks),
        titles={t["id"]: t["title"] for t in tracks},
        context_path=tmp_path / "return.json",
        on_launch=lambda game, focus: None,
    )
    # case-insensitive e substring
    with bridge.serving() as base:
        hit = _get(f"{base}/search?q=CELe", bridge.token)
        miss = _get(f"{base}/search?q=zzz", bridge.token)
    assert [g["id"] for g in hit["games"]] == ["celeste"]
    assert hit["games"][0]["title"] == "Celeste"
    assert hit["games"][0]["coverUrl"] == ""
    assert miss["games"] == []


def test_main_reports_the_missing_runtime_instead_of_crashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sem Qt no host, o launcher precisa dizer isso — não terminar em traceback."""
    monkeypatch.setattr("steamzero.adapters.launcher_ui.shutil.which", lambda _name: None)
    code = main(["--library", str(tmp_path / "ausente.json")])
    assert code != 0


def test_launcher_reads_the_canonical_library_without_being_told_where(
    monkeypatch, tmp_path
) -> None:
    """O Launcher precisa achar o acervo sozinho.

    Ele lia só o arquivo passado por ``--library``. Sem o argumento, a home
    abria vazia mesmo com a biblioteca canônica cheia — e quem abre o Launcher
    pelo entry point não passa argumento nenhum.

    Havia um segundo defeito escondido atrás do primeiro: a biblioteca canônica
    é ``{"games": [...]}``, e ``_read_library`` só aceitava lista crua. Apontar
    ``--library`` para ela devolveria vazio do mesmo jeito.
    """
    from steamzero.core import paths
    from steamzero.launcher import app

    data_home = tmp_path / "data"
    data_home.mkdir(parents=True)
    monkeypatch.setattr(paths, "data_home", lambda: data_home)
    (data_home / "emulation-library-cache-v1.json").write_text(
        json.dumps(
            {
                "games": [
                    {"id": "a1", "name": "Chrono Trigger", "platform": "snes"},
                    {"id": "b2", "name": "Ridge Racer", "platform": "playstation"},
                ]
            }
        ),
        encoding="utf-8",
    )

    library = app._read_library(None)

    names = sorted(str(item.get("name")) for item in library)
    assert names == ["Chrono Trigger", "Ridge Racer"], (
        f"o Launcher não achou a biblioteca canônica sozinho: {library}"
    )


def test_launch_route_is_emulation_launch_not_steam_wrapper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O Launcher lança jogo canônico pela rota de produto, não pelo wrapper Steam.

    Regressão 2026-08-30: `on_launch` montava `steamzero-launch <game_id>`.
    Esse binário não é publicado pelo instalador e, mesmo que fosse, o contrato
    do `steamzero-launch` é o wrapper de jogo Steam (`--appid APPID -- %command%`).
    O id canônico de emulação passava por um comando cujo contrato é outro, e o
    spawn falho deixava o contexto de retorno pendurado.
    """
    from steamzero.launcher import app as app_module

    fake_bin = tmp_path / "steamzero"
    fake_bin.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_bin.chmod(0o755)

    captured: list[tuple[str, ...]] = []

    def fake_spawn(argv: tuple[str, ...]) -> int:
        captured.append(argv)
        return 12345

    router = app_module.LaunchRouter(
        on_spawn=fake_spawn,
        context_path=tmp_path / "return.json",
        executable=lambda: str(fake_bin),
    )
    router.launch("celeste")

    assert captured, "o lançamento não acionou nenhum spawn"
    assert captured[0][0] == str(fake_bin), (
        f"o launcher deve usar o binário `steamzero`, não o wrapper Steam: {captured[0]}"
    )
    assert captured[0][0].endswith("steamzero")
    assert captured[0][1:5] == ("emulation", "launch", "--game-id", "celeste"), (
        f"a rota de jogo canônico deve ser `emulation launch --game-id`: {captured[0]}"
    )
    assert "steamzero-launch" not in captured[0][0], (
        "regressão: o wrapper Steam não pode lançar jogo de emulação"
    )
