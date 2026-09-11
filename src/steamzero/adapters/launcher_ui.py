# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Ponte entre o processo do AURA Launcher e a cena QML.

Segue o mesmo desenho já usado pela central: servidor em loopback, token por
execução e o QML como processo separado. O token não é formalidade — sem ele,
qualquer processo local poderia disparar jogos na máquina do usuário.

Vive num adapter porque abre socket e cria processo; o domínio resolve foco e
página, e nada aqui decide navegação.
"""

from __future__ import annotations

import importlib.resources
import json
import os
import secrets
import shutil
import threading
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from steamzero.adapters.launcher_process import supervised_child
from steamzero.core.errors import SteamZeroError
from steamzero.domain.scene_layout import LayoutBounds, LayoutRecipe
from steamzero.launcher.cinema import resolve_cinema_covers
from steamzero.launcher.navigation import HomeSection, resolve_home_focus

LaunchCallback = Callable[[str, str], None]
_QT_QUICK_BACKEND = "software"


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    @property
    def _bridge(self) -> LauncherBridge:
        bridge = getattr(self.server, "bridge", None)
        if not isinstance(bridge, LauncherBridge):
            raise RuntimeError("servidor sem ponte associada")
        return bridge

    def _authorized(self) -> bool:
        return secrets.compare_digest(self.headers.get("X-SteamZero-Token", ""), self._bridge.token)

    def do_GET(self) -> None:
        if not self._authorized():
            self._send(403, {"error": "token inválido"})
            return
        if self.path == "/model":
            self._send(200, self._bridge.model())
            return
        if self.path.startswith("/session?"):
            self._send(200, self._bridge.session(self._query_param("gameId") or ""))
            return
        if self.path.startswith("/cinema?"):
            try:
                body = self._bridge.cinema(
                    self._query_param("focus") or "",
                    width=float(self._query_param("width") or "0"),
                    height=float(self._query_param("height") or "0"),
                )
            except ValueError:
                self._send(400, {"error": "LAUNCHER-CINEMA-REQUEST-001"})
                return
            self._send(200, body)
            return
        if self.path.startswith("/search?"):
            query = self._query_param("q")
            if query is None:
                self._send(400, {"error": "parâmetro q ausente"})
                return
            self._send(200, self._bridge.search(query))
            return
        self._send(404, {"error": "rota desconhecida"})

    def do_POST(self) -> None:
        if not self._authorized():
            self._send(403, {"error": "token inválido"})
            return
        if self.path != "/launch":
            self._send(404, {"error": "rota desconhecida"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if not 0 < length <= 4096:
            self.close_connection = True
            self._send(400, {"error": "LAUNCHER-REQUEST-SIZE-001"})
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._send(400, {"error": "corpo inválido"})
            return
        if not isinstance(payload, dict):
            self._send(400, {"error": "corpo inválido"})
            return
        game_id = str(payload.get("gameId", ""))
        focus_id = str(payload.get("focusId", ""))
        if not game_id:
            self._send(400, {"error": "gameId ausente"})
            return
        try:
            self._bridge.launch(game_id, focus_id)
        except (OSError, ValueError, SteamZeroError):
            # Exception text can contain local paths or credentials. Publish a
            # stable recovery contract, never an unfiltered traceback/detail.
            self._send(
                409,
                {
                    "error": {
                        "code": "LAUNCHER-LAUNCH-FAILED-001",
                        "cause": "Não foi possível preparar o lançamento.",
                        "impact": "O Launcher não confirmou o início do jogo.",
                        "nextAction": (
                            "Verifique o emulador e os requisitos na central e tente novamente."
                        ),
                    }
                },
            )
            return
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _query_param(self, name: str) -> str | None:
        from urllib.parse import parse_qs, urlsplit

        parsed = urlsplit(self.path)
        values = parse_qs(parsed.query).get(name)
        if not values:
            return None
        return values[0]

    def _send(self, status: int, body: dict[str, Any]) -> None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_: Any) -> None:
        """Silencia o log HTTP: ele carregaria o token na linha de requisição."""


class _Server(HTTPServer):
    bridge: LauncherBridge


class LauncherBridge:
    """Serve o modelo resolvido e recebe o pedido de lançamento."""

    def __init__(
        self,
        *,
        sections: Sequence[HomeSection],
        context_path: Path,
        on_launch: LaunchCallback,
        titles: Mapping[str, str] | None = None,
        covers: Mapping[str, str] | None = None,
        accessibility: Mapping[str, Any] | None = None,
        return_context: Mapping[str, Any] | None = None,
        catalog_summary: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Mapping[str, Any]] | None = None,
        session_observer: Callable[[str], dict[str, Any]] | None = None,
    ) -> None:
        self._sections = tuple(sections)
        self._titles = dict(titles or {})
        self._covers = dict(covers or {})
        self._metadata = {key: dict(value) for key, value in (metadata or {}).items()}
        self._session_observer = session_observer
        self._previous_sessions: dict[str, str | None] = {}
        self._pending_game: str | None = None
        self._context_path = Path(context_path)
        self._on_launch = on_launch
        self._accessibility = dict(accessibility or {})
        self._return_context = dict(return_context or {}) or None
        self._catalog_summary = dict(catalog_summary or {})
        self.token = secrets.token_urlsafe(32)
        self._focus = resolve_home_focus(self._sections)

    def model(self) -> dict[str, Any]:
        return {
            "accessibility": {
                "highContrast": bool(self._accessibility.get("highContrast", False)),
                "visualScale": float(self._accessibility.get("visualScale", 1.0)),
                "reducedMotion": bool(self._accessibility.get("reducedMotion", False)),
            },
            "focusMap": self._focus.to_qml_object(),
            # O processo consome o contexto antes de iniciar o QML. Publicá-lo
            # aqui faz a restauração existir no entry point real, e não apenas
            # no harness que injeta returnContext diretamente.
            "returnContext": self._return_context,
            "catalogSummary": self._catalog_summary,
            "sections": [
                {
                    "id": section.id,
                    "title": section.title,
                    "items": [
                        {
                            **self._metadata.get(item, {}),
                            "id": item,
                            "title": self._titles.get(item, item),
                            "coverUrl": self._covers.get(item)
                            or self._metadata.get(item, {}).get("coverUrl", ""),
                        }
                        for item in section.items
                    ],
                }
                for section in self._sections
            ],
        }

    def search(self, query: str) -> dict[str, Any]:
        """Filtra a biblioteca por título (case-insensitive, substring).

        A busca vive na ponte porque é ela quem tem o mapa id->título; o QML
        não duplica o acervo. Devolve o resultado na mesma forma de uma seção
        (id, title, coverUrl) para que a home renderize um "resultado" sem
        lógica própria.
        """
        needle = query.strip().casefold()
        matches: list[dict[str, Any]] = []
        if needle:
            for game_id, title in self._titles.items():
                if needle in str(title).casefold():
                    matches.append(
                        {
                            "id": game_id,
                            "title": str(title),
                            "coverUrl": self._covers.get(game_id, ""),
                        }
                    )
        matches.sort(key=lambda row: str(row["title"]).casefold())
        return {"query": query, "games": matches}

    def cinema(self, focus_id: str, *, width: float, height: float) -> dict[str, Any]:
        """Resolve only the focused collection; no navigation decision is made here."""
        bounds = LayoutBounds(width, height)
        node = self._focus.nodes.get(focus_id)
        if node is None:
            raise ValueError("unknown focus")
        section = next((row for row in self._sections if row.id == node.section), None)
        if section is None:
            return {"layouts": {}, "sourceIndices": [], "selected": 0, "focusId": focus_id}
        items = [
            {
                **self._metadata.get(game, {}),
                "id": game,
                "title": self._titles.get(game, game),
                "coverUrl": self._covers.get(game)
                or self._metadata.get(game, {}).get("coverUrl", ""),
            }
            for game in section.items
        ]
        cover_height = min(height * 0.72, 640)
        recipe = LayoutRecipe.from_dict(
            "covers",
            {
                "source": "cinema.items",
                "kind": "coverFlow",
                "item": {"width": max(1, cover_height * 2 / 3), "height": max(1, cover_height)},
                "template": {
                    "kind": "image",
                    "id": "cover",
                    "properties": {"source": {"binding": "item.coverUrl", "fallback": ""}},
                },
                "offset": {
                    "scaleStep": 0.18,
                    "opacityStep": 0.2,
                    "minScale": 0.5,
                    "minOpacity": 0.35,
                    "rotationStep": 0,
                    "overlap": 0.65,
                },
                "highlight": {"scale": 1, "opacity": 1, "outlineWidth": 3},
            },
        )
        result = resolve_cinema_covers(recipe, items, node.column, bounds=bounds)
        result.update(
            focusId=focus_id,
            collection=section.title,
            items=[items[index] for index in result["sourceIndices"]],
        )
        return result

    def launch(self, game_id: str, focus_id: str) -> None:
        if self._pending_game is not None:
            self.session(self._pending_game)
            if self._pending_game is not None:
                raise ValueError("a launch is still active or unconfirmed")
        node = self._focus.nodes.get(focus_id)
        if node is None or node.action is not None:
            raise ValueError("launch requires a current game focus")
        section = next((row for row in self._sections if row.id == node.section), None)
        if (
            section is None
            or not 0 <= node.column < len(section.items)
            or section.items[node.column] != game_id
        ):
            raise ValueError("launch game does not match its return focus")
        if self._session_observer is not None:
            previous = self._session_observer(game_id)
            if previous.get("state") in {
                "launching",
                "running",
                "suspending",
                "suspended",
                "resuming",
                "closing",
            }:
                raise ValueError("the game already has an active canonical session")
            self._previous_sessions[game_id] = previous.get("sessionId")
        self._on_launch(game_id, focus_id)
        if self._session_observer is not None:
            self._pending_game = game_id

    def session(self, game_id: str) -> dict[str, Any]:
        if self._session_observer is None or not any(
            game_id in section.items for section in self._sections
        ):
            return {"gameId": game_id, "state": "unknown", "sessionId": None}
        result = self._session_observer(game_id)
        if (
            game_id in self._previous_sessions
            and result.get("sessionId") == self._previous_sessions[game_id]
        ):
            return {"gameId": game_id, "state": "awaiting", "sessionId": None}
        if self._pending_game == game_id and result.get("state") in {"closed", "failed"}:
            self._pending_game = None
        return result

    @contextmanager
    def serving(self) -> Iterator[str]:
        server = _Server(("127.0.0.1", 0), _Handler)
        server.bridge = self
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()
            server.server_close()


def launch_launcher_ui(bridge: LauncherBridge) -> int:
    """Abre a cena do Launcher e espera o processo terminar.

    Runtime Qt ausente é condição esperada num host sem sessão gráfica, e vira
    código de saída com mensagem — não traceback.
    """
    executable = shutil.which("qml6") or shutil.which("qml")
    if executable is None:
        return 3
    resource = importlib.resources.files("steamzero.ui").joinpath("qml/launcher/LauncherMain.qml")
    with bridge.serving() as base, importlib.resources.as_file(resource) as scene:
        argv = (
            executable,
            str(scene),
            "--",
            "--steamzero-api",
            base,
            "--steamzero-token",
            bridge.token,
        )
        environment = {
            **os.environ,
            "QT_QUICK_BACKEND": _QT_QUICK_BACKEND,
            "STEAMZERO_CLASS": "launcher",
        }
        # A cena vive sob supervisão: quando este processo acabar — por retorno,
        # exceção ou sinal — o `qml6` acaba junto. Sobrevivendo, ele mantinha uma
        # janela com o título e a classe da sessão viva, já sem a ponte HTTP.
        with supervised_child(argv, env=environment) as process:
            status = process.wait()
    # Morte por sinal chega como código negativo, que não é código de saída
    # válido; a convenção de shell (128+sinal) preserva a causa.
    return 128 - status if status < 0 else int(status)
