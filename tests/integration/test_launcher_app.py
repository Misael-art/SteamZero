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
