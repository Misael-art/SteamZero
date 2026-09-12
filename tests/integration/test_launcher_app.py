# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contrato do processo do AURA Launcher: o que serve à UI e o que aceita dela."""

from __future__ import annotations

import http.client
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from steamzero.adapters.launcher_catalog import catalog_games, catalog_summary
from steamzero.adapters.launcher_receipt import spawn_receipt
from steamzero.adapters.launcher_ui import LauncherBridge
from steamzero.launcher.app import build_sections, build_titles, main


def _get(url: str, token: str) -> dict:
    # URL vem do endereço que a própria ponte devolveu, em loopback.
    request = urllib.request.Request(url, headers={"X-SteamZero-Token": token})  # noqa: S310
    with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310
        return json.loads(response.read())


def test_keep_alive_model_connection_does_not_block_cinema_or_session(tmp_path: Path) -> None:
    bridge = LauncherBridge(
        sections=build_sections([{"id": "game", "title": "Game", "section": "library"}]),
        context_path=tmp_path / "return.json",
        on_launch=lambda game, focus: None,
    )
    with bridge.serving() as base:
        address = urllib.parse.urlsplit(base)
        first = http.client.HTTPConnection(address.hostname, address.port, timeout=2)
        second = http.client.HTTPConnection(address.hostname, address.port, timeout=2)
        headers = {"X-SteamZero-Token": bridge.token}
        try:
            first.request("GET", "/model", headers=headers)
            model = first.getresponse()
            assert model.status == 200
            assert json.loads(model.read())["sections"]
            # Keep the model connection open, as a QML HTTP connection pool does.
            second.request(
                "GET", "/cinema?focus=library:game&width=1280&height=800", headers=headers
            )
            scene = second.getresponse()
            assert scene.status == 200
            assert json.loads(scene.read())["focusId"] == "library:game"
            second.request("GET", "/session?gameId=game", headers=headers)
            session = second.getresponse()
            assert session.status == 200
            assert json.loads(session.read())["gameId"] == "game"
        finally:
            second.close()
            first.close()


def test_parallel_launches_remain_single_while_catalog_requests_continue(tmp_path: Path) -> None:
    entered = threading.Event()
    release = threading.Event()
    calls = []

    def launch(game: str, focus: str) -> None:
        calls.append(game)
        entered.set()
        assert release.wait(5), "test did not release launch callback"

    bridge = LauncherBridge(
        sections=build_sections([{"id": "game", "title": "Game", "section": "library"}]),
        context_path=tmp_path / "return.json",
        on_launch=launch,
        session_observer=lambda game: {"gameId": game, "state": "unknown", "sessionId": None},
    )
    with bridge.serving() as base, ThreadPoolExecutor(max_workers=2) as pool:
        payload = {"gameId": "game", "focusId": "library:game"}
        first = pool.submit(_post, f"{base}/launch", bridge.token, payload)
        try:
            assert entered.wait(3)
            second = pool.submit(_post, f"{base}/launch", bridge.token, payload)
            # The potentially slow launch callback must not block the catalog.
            assert _get(f"{base}/model", bridge.token)["sections"]
        finally:
            release.set()
        assert first.result(timeout=3) == 200
        with pytest.raises(urllib.error.HTTPError) as rejected:
            second.result(timeout=3)
        assert rejected.value.code == 409
        rejected.value.close()
    assert calls == ["game"]


def test_session_route_does_not_reuse_previous_game_session(tmp_path: Path) -> None:
    observed = {"gameId": "game", "sessionId": "old", "state": "closed"}
    bridge = LauncherBridge(
        sections=build_sections([{"id": "game", "title": "Game", "section": "library"}]),
        context_path=tmp_path / "return.json",
        on_launch=lambda game, focus: None,
        session_observer=lambda game: dict(observed),
    )
    with bridge.serving() as base:
        bridge.launch("game", "library:game")
        assert _get(f"{base}/session?gameId=game", bridge.token)["state"] == "awaiting"
        observed.update(sessionId="new", state="running")
        assert _get(f"{base}/session?gameId=game", bridge.token)["state"] == "running"
        observed["state"] = "closed"
        assert _get(f"{base}/session?gameId=game", bridge.token)["state"] == "closed"
        assert _get(f"{base}/session?gameId=outside", bridge.token)["state"] == "unknown"


def test_pending_launch_stays_locked_until_new_canonical_terminal_state(tmp_path: Path) -> None:
    observed = {"gameId": "game", "sessionId": "old", "state": "closed"}
    launched = []
    bridge = LauncherBridge(
        sections=build_sections([{"id": "game", "title": "Game", "section": "library"}]),
        context_path=tmp_path / "return.json",
        on_launch=lambda game, focus: launched.append(game),
        session_observer=lambda game: dict(observed),
    )
    bridge.launch("game", "library:game")
    for state, identifier in [("closed", "old"), ("unknown", None), ("running", "new")]:
        observed.update(state=state, sessionId=identifier)
        with pytest.raises(ValueError):
            bridge.launch("game", "library:game")
    assert launched == ["game"]
    observed.update(state="closed", sessionId="new")
    bridge.launch("game", "library:game")
    assert launched == ["game", "game"]


def _post(url: str, token: str, payload: dict) -> int:
    request = urllib.request.Request(  # noqa: S310
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"X-SteamZero-Token": token, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310
        return int(response.status)


def test_launch_failure_is_reported_without_secrets_and_bridge_recovers(tmp_path: Path) -> None:
    attempts = []

    def launch(game: str, focus: str) -> None:
        attempts.append(game)
        if len(attempts) == 1:
            raise OSError("private-path-and-secret")

    bridge = LauncherBridge(
        sections=build_sections([{"id": "game", "title": "Game", "section": "library"}]),
        context_path=tmp_path / "return.json",
        on_launch=launch,
    )
    with bridge.serving() as base:
        payload = {"gameId": "game", "focusId": "library:game"}
        with pytest.raises(urllib.error.HTTPError) as failure:
            _post(f"{base}/launch", bridge.token, payload)
        assert failure.value.code == 409
        body = json.loads(failure.value.read())
        assert body["error"]["code"] == "LAUNCHER-LAUNCH-FAILED-001"
        assert body["error"]["cause"] and body["error"]["impact"] and body["error"]["nextAction"]
        assert "private-path-and-secret" not in json.dumps(body)
        assert _post(f"{base}/launch", bridge.token, payload) == 200
    assert attempts == ["game", "game"]


@pytest.mark.parametrize(
    "game,focus",
    [
        ("outside", "library:game"),
        ("game", "search:game"),
        ("game", "header:home"),
        ("game", ""),
    ],
)
def test_launch_rejects_foreign_game_or_stale_return_context(
    tmp_path: Path,
    game: str,
    focus: str,
) -> None:
    launched = []
    bridge = LauncherBridge(
        sections=build_sections([{"id": "game", "title": "Game", "section": "library"}]),
        context_path=tmp_path / "return.json",
        on_launch=lambda game, focus: launched.append(game),
    )
    with bridge.serving() as base:
        with pytest.raises(urllib.error.HTTPError) as denied:
            _post(f"{base}/launch", bridge.token, {"gameId": game, "focusId": focus})
        assert denied.value.code == 409
    assert launched == []


def test_cinema_route_resolves_focus_and_rejects_untrusted_requests(tmp_path: Path) -> None:
    games = [{"id": f"game{i}", "title": f"Game {i}", "section": "library"} for i in range(30)]
    bridge = LauncherBridge(
        sections=build_sections(games),
        titles=build_titles(games),
        context_path=tmp_path / "return.json",
        on_launch=lambda game, focus: None,
        metadata={
            "game29": {
                "description": "Descrição canônica",
                "players": 2,
                "fanartUrl": "file:///art/fanart.png",
            }
        },
    )
    with bridge.serving() as base:
        route = f"{base}/cinema?focus=library:game29&width=1280&height=800"
        result = _get(route, bridge.token)
        assert result["focusId"] == "library:game29"
        assert len(result["items"]) == 7
        assert result["items"][result["selected"]]["id"] == "game29"
        assert result["items"][result["selected"]]["players"] == 2
        assert result["items"][result["selected"]]["fanartUrl"] == "file:///art/fanart.png"
        model = _get(f"{base}/model", bridge.token)
        item = next(item for item in model["sections"][0]["items"] if item["id"] == "game29")
        assert item["description"] == "Descrição canônica"
        assert len(result["layouts"]["covers"]["entries"]) == 7
        with pytest.raises(urllib.error.HTTPError) as denied:
            _get(route, "wrong-token")
        assert denied.value.code == 403
        for query in (
            "focus=missing&width=1280&height=800",
            "focus=library:game29&width=nan&height=800",
            "focus=library:game29&width=20000&height=800",
        ):
            with pytest.raises(urllib.error.HTTPError) as invalid:
                _get(f"{base}/cinema?{query}", bridge.token)
            assert invalid.value.code == 400
        assert _get(route, bridge.token)["focusId"] == "library:game29"


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
            == 200
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


def test_the_launcher_model_publishes_scan_reconciliation(tmp_path: Path) -> None:
    records = [
        {"id": "a1", "name": "Chrono Trigger", "platform": "snes"},
        {"id": "u1", "name": "Update", "platform": "snes", "contentKind": "update"},
    ]
    catalog = catalog_games(records)
    summary = catalog_summary(
        {
            "scanSummary": {
                "filesFound": 7,
                "updates": 1,
                "dlcs": 0,
                "incompatible": 2,
                "ignored": 1,
                "incompatibleReasons": {"archive-needs-extraction": 2},
            }
        },
        catalog,
        records,
    )
    bridge = LauncherBridge(
        sections=build_sections(records),
        titles=build_titles(records),
        context_path=tmp_path / "return.json",
        on_launch=lambda game, focus: None,
        catalog_summary=summary,
    )
    with bridge.serving() as base:
        model = _get(f"{base}/model", bridge.token)
    assert model["catalogSummary"]["filesFound"] == 7
    assert model["catalogSummary"]["games"] == 1
    assert model["catalogSummary"]["incompatibleReasons"] == {"archive-needs-extraction": 2}


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
    from types import SimpleNamespace

    from steamzero.launcher import app as app_module

    fake_bin = tmp_path / "steamzero"
    fake_bin.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_bin.chmod(0o755)

    captured: list[tuple[str, ...]] = []

    def fake_spawn(argv: tuple[str, ...]) -> int:
        return 12345

    def fake_receipt(argv, *, request_id: str, game_id: str):
        captured.append(tuple(argv))
        return SimpleNamespace(pid=12345, request_id=request_id, game_id=game_id)

    router = app_module.LaunchRouter(
        on_spawn=fake_spawn,
        context_path=tmp_path / "return.json",
        executable=lambda: str(fake_bin),
        receipt_spawner=fake_receipt,
    )
    attempt = router.launch("celeste")

    assert attempt is not None and attempt.request_id
    assert captured, "o lançamento não acionou nenhum spawn"
    assert captured[0][0] == str(fake_bin), (
        f"o launcher deve usar o binário `steamzero`, não o wrapper Steam: {captured[0]}"
    )
    assert captured[0][0].endswith("steamzero")
    assert captured[0][1:5] == ("emulation", "launch", "--game-id", "celeste"), (
        f"a rota de jogo canônico deve ser `emulation launch --game-id`: {captured[0]}"
    )
    assert captured[0][5] == "--json", "o recibo exige a resposta JSON do CLI"
    assert "steamzero-launch" not in captured[0][0], (
        "regressão: o wrapper Steam não pode lançar jogo de emulação"
    )


# --- Contrato de confirmação de lançamento (recibo notStarted/unconfirmed) ---

_NOT_STARTED_ENVELOPE = (
    json.dumps(
        {
            "ok": False,
            "status": "failed",
            "error": {
                "code": "E-COMPONENT-DEGRADED",
                "what": "emulador ausente",
                "impact": "nada foi criado",
                "manualAction": "defina o emulador",
                "launchAcknowledgment": "notStarted",
            },
        }
    )
    + "\n"
)


def _wait_state(attempt, state: str, timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if attempt.state == state:
            return True
        time.sleep(0.01)
    return attempt.state == state


def test_not_started_receipt_releases_the_attempt_for_a_new_launch(tmp_path: Path) -> None:
    attempts = []

    def on_launch(game: str, focus: str):
        attempt = spawn_receipt(
            (
                sys.executable,
                "-c",
                f"import sys; sys.stdout.write({_NOT_STARTED_ENVELOPE!r})",
            ),
            request_id=f"req-{len(attempts)}",
            game_id=game,
        )
        attempts.append(attempt)
        return attempt

    bridge = LauncherBridge(
        sections=build_sections([{"id": "game", "title": "Game", "section": "library"}]),
        context_path=tmp_path / "return.json",
        on_launch=on_launch,
        session_observer=lambda game: {"gameId": game, "state": "closed", "sessionId": "old"},
    )
    bridge.launch("game", "library:game")
    assert _wait_state(attempts[0], "notStarted")
    session = bridge.session("game")
    assert session["state"] == "failed"
    assert session["attempt"]["state"] == "notStarted"
    assert session["attempt"]["error"]["code"] == "E-COMPONENT-DEGRADED"
    # Falha confirmada pelo requestId atual: Jogar volta a ser elegível.
    bridge.launch("game", "library:game")
    assert len(attempts) == 2


def test_unconfirmed_receipt_keeps_the_launch_locked(tmp_path: Path) -> None:
    attempts = []

    def on_launch(game: str, focus: str):
        attempt = spawn_receipt(
            (sys.executable, "-c", "import sys; sys.stdout.write('not-json\\n')"),
            request_id=f"req-{len(attempts)}",
            game_id=game,
        )
        attempts.append(attempt)
        return attempt

    bridge = LauncherBridge(
        sections=build_sections([{"id": "game", "title": "Game", "section": "library"}]),
        context_path=tmp_path / "return.json",
        on_launch=on_launch,
        session_observer=lambda game: {"gameId": game, "state": "unknown", "sessionId": None},
    )
    bridge.launch("game", "library:game")
    assert _wait_state(attempts[0], "unconfirmed")
    session = bridge.session("game")
    assert session["state"] == "awaiting"
    assert session["attempt"]["state"] == "unconfirmed"
    # Sem confirmação do que aconteceu, não liberar duplicação.
    with pytest.raises(ValueError):
        bridge.launch("game", "library:game")


def test_confirmed_receipt_observations_follow_the_new_session(tmp_path: Path) -> None:
    gate = tmp_path / "release"
    script = (
        "import json, os, sys, time;"
        "sys.stdout.write(json.dumps({'ok': True, 'data': {"
        "'gameId': 'game', 'sessionId': 'sess-new'}}) + '\\n');"
        "sys.stdout.flush();"
        f"gate, deadline = {gate.as_posix()!r}, time.time() + 10\n"
        "while not os.path.exists(gate) and time.time() < deadline: time.sleep(0.02)"
    )
    observed = {"gameId": "game", "sessionId": "old", "state": "closed"}
    attempts = []

    def on_launch(game: str, focus: str):
        attempt = spawn_receipt((sys.executable, "-c", script), request_id="req-1", game_id=game)
        attempts.append(attempt)
        return attempt

    bridge = LauncherBridge(
        sections=build_sections([{"id": "game", "title": "Game", "section": "library"}]),
        context_path=tmp_path / "return.json",
        on_launch=on_launch,
        session_observer=lambda game: dict(observed),
    )
    bridge.launch("game", "library:game")
    assert _wait_state(attempts[0], "confirmed")
    # A sessão antiga ainda é a última observação: aguardando, com o recibo já
    # confirmado anexado à projeção.
    awaiting = bridge.session("game")
    assert awaiting["state"] == "awaiting"
    assert awaiting["attempt"]["state"] == "confirmed"
    observed.update(sessionId="sess-new", state="running")
    running = bridge.session("game")
    assert running["state"] == "running"
    assert running["sessionId"] == "sess-new"
    observed.update(state="closed")
    assert bridge.session("game")["state"] == "closed"
    gate.touch()
    bridge.launch("game", "library:game")
    assert len(attempts) == 2


def test_launch_route_publishes_the_request_id(tmp_path: Path) -> None:
    attempts = []

    def on_launch(game: str, focus: str):
        attempt = spawn_receipt(
            (
                sys.executable,
                "-c",
                f"import sys; sys.stdout.write({_NOT_STARTED_ENVELOPE!r})",
            ),
            request_id=f"req-{len(attempts)}",
            game_id=game,
        )
        attempts.append(attempt)
        return attempt

    bridge = LauncherBridge(
        sections=build_sections([{"id": "game", "title": "Game", "section": "library"}]),
        context_path=tmp_path / "return.json",
        on_launch=on_launch,
    )
    with bridge.serving() as base:
        request = urllib.request.Request(  # noqa: S310
            f"{base}/launch",
            data=json.dumps({"gameId": "game", "focusId": "library:game"}).encode("utf-8"),
            headers={"X-SteamZero-Token": bridge.token, "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310
            assert response.status == 200
            body = json.loads(response.read())
    assert body["requestId"] == attempts[0].request_id
