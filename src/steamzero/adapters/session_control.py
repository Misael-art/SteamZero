# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Controle local do processo pelo dono canônico da sessão.

O processo que inicia o emulador continua sendo o dono do lifecycle. Este
módulo só oferece uma porta AF_UNIX efêmera para que a ponte do Launcher envie
intenções ``pause``/``resume`` correlacionadas; o QML nunca recebe PID nem
sinaliza processos diretamente.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import struct
import threading
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from steamzero.core import fs, paths
from steamzero.core.state import StateStore

if TYPE_CHECKING:
    from steamzero.adapters.session_peripherals import SessionPeripheralControl

MAX_CONTROL_REQUEST = 1024
MAX_CONTROL_RESPONSE = 2048
CONTROL_DIRECTORY = "session-controls"
DIAG_CONTROL_UNAVAILABLE = "AURA-SESSION-CONTROL-UNAVAILABLE-001"
DIAG_CONTROL_REQUEST = "AURA-SESSION-CONTROL-REQUEST-002"
DIAG_CONTROL_FAILED = "AURA-SESSION-CONTROL-FAILED-003"

StoreFactory = Callable[[], StateStore]
SignalProcess = Callable[[int, int], None]
ReadStartTicks = Callable[[int], int | None]
ObserveSession = Callable[[str], Mapping[str, Any]]


@dataclass(frozen=True)
class SessionControlRecord:
    id: str
    game_id: str
    state: str


def _bounded_text(value: Any, *, limit: int = 128) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _peer_is_same_uid(connection: socket.socket) -> bool:
    try:
        _pid, uid, _gid = struct.unpack(
            "3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
        )
    except (OSError, struct.error):
        return False
    return bool(int(uid) == os.getuid())


def _read_line(connection: socket.socket) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while total <= MAX_CONTROL_REQUEST:
        chunk = connection.recv(256)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if b"\n" in chunk:
            break
    raw = b"".join(chunks)
    if len(raw) > MAX_CONTROL_REQUEST or b"\n" not in raw:
        raise ValueError("requisição de controle excede o limite")
    return raw.split(b"\n", 1)[0]


class SessionControlOwner:
    """Implementa pause/retomada dentro do processo que lançou o jogo."""

    def __init__(
        self,
        session_id: str,
        game_id: str,
        pid: int,
        start_ticks: int | None,
        *,
        store_factory: StoreFactory = StateStore,
        read_start_ticks: ReadStartTicks,
        signal_process: SignalProcess | None = None,
        peripheral_control: SessionPeripheralControl | None = None,
    ) -> None:
        self.session_id = session_id
        self.game_id = game_id
        self.pid = pid
        self.start_ticks = start_ticks
        self._store_factory = store_factory
        self._read_start_ticks = read_start_ticks
        self._signal_process = signal_process or os.killpg
        self._peripheral_control = peripheral_control
        self._lock = threading.RLock()

    @property
    def current(self) -> SessionControlRecord | None:
        with self._store_factory() as store:
            store.migrate()
            row = store.get_game_session(self.session_id)
        if row is None or row.get("game_id") != self.game_id:
            return None
        return SessionControlRecord(
            id=self.session_id,
            game_id=self.game_id,
            state=str(row.get("state") or "unknown"),
        )

    def suspend(self) -> SessionControlRecord:
        return self._transition_with_signal("suspending", signal.SIGSTOP, "suspended")

    def resume(self) -> SessionControlRecord:
        return self._transition_with_signal("resuming", signal.SIGCONT, "running")

    def list_save_states(self) -> Mapping[str, Any]:
        if self._peripheral_control is None:
            raise RuntimeError("o adapter desta sessão não oferece save-state")
        return self._peripheral_control.list_save_states()

    def save_state(self, slot: int) -> SessionControlRecord:
        if self._peripheral_control is None:
            raise RuntimeError("o adapter desta sessão não oferece save-state")
        self._peripheral_control.save_state(slot)
        return self._require_current()

    def load_state(self, slot: int) -> SessionControlRecord:
        if self._peripheral_control is None:
            raise RuntimeError("o adapter desta sessão não oferece save-state")
        self._peripheral_control.load_state(slot)
        return self._require_current()

    def list_discs(self) -> Mapping[str, Any]:
        if self._peripheral_control is None:
            raise RuntimeError("o adapter desta sessão não oferece troca de disco")
        return self._peripheral_control.list_discs()

    def swap_disc(self, disc_id: str) -> SessionControlRecord:
        if self._peripheral_control is None:
            raise RuntimeError("o adapter desta sessão não oferece troca de disco")
        self._peripheral_control.swap_disc(disc_id)
        return self._require_current()

    def list_peripherals(self) -> Mapping[str, Any]:
        if self._peripheral_control is None:
            raise RuntimeError("o adapter desta sessão não oferece periféricos")
        return self._peripheral_control.list_peripherals()

    def _require_current(self) -> SessionControlRecord:
        current = self.current
        if current is None:
            raise RuntimeError("a sessão não está mais disponível")
        return current

    def _transition_with_signal(
        self, intermediate: str, signum: int, target: str
    ) -> SessionControlRecord:
        with self._lock:
            current = self.current
            if current is None or current.state not in {
                "running" if target == "suspended" else "suspended"
            }:
                raise RuntimeError("a sessão não está no estado esperado")
            if self.start_ticks is None or self._read_start_ticks(self.pid) != self.start_ticks:
                raise RuntimeError("a identidade do processo da sessão não pôde ser confirmada")
            with self._store_factory() as store:
                store.migrate()
                store.transition_game_session(self.session_id, intermediate)
                try:
                    self._signal_process(self.pid, signum)
                except OSError:
                    store.transition_game_session(
                        self.session_id,
                        "failed",
                        pid=None,
                        failure_code=DIAG_CONTROL_FAILED,
                    )
                    raise RuntimeError("não foi possível controlar o processo da sessão") from None
                store.transition_game_session(self.session_id, target)
            updated = self.current
        if updated is None:
            raise RuntimeError("a sessão desapareceu após o controle")
        return updated


class SessionControlServer:
    """Servidor efêmero, autenticado por UID e delimitado à sessão criada."""

    def __init__(self, owner: SessionControlOwner, path: Path) -> None:
        self.owner = owner
        self.path = Path(path)
        self._stop = threading.Event()
        self._socket: socket.socket | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        fs.ensure_dir(self.path.parent, mode=0o700)
        with suppress(FileNotFoundError):
            fs.remove_file(self.path)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(self.path))
        fs.set_mode(self.path, 0o600)
        server.listen(4)
        server.settimeout(0.2)
        self._socket = server
        self._thread = threading.Thread(target=self._serve, name="steamzero-session-control")
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        server = self._socket
        if server is not None:
            server.close()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1.0)
        with suppress(FileNotFoundError):
            fs.remove_file(self.path)

    def _serve(self) -> None:
        server = self._socket
        if server is None:
            return
        with server:
            while not self._stop.is_set():
                try:
                    connection, _address = server.accept()
                except TimeoutError:
                    continue
                except OSError:
                    return
                with connection:
                    if not _peer_is_same_uid(connection):
                        continue
                    try:
                        request = json.loads(_read_line(connection).decode("utf-8"))
                        result = self._dispatch(request)
                    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
                        result = {
                            "accepted": False,
                            "diagnostic": DIAG_CONTROL_REQUEST,
                            "detail": "A requisição da sessão é inválida.",
                        }
                    payload = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
                    connection.sendall(payload[:MAX_CONTROL_RESPONSE].encode("utf-8") + b"\n")

    def _dispatch(self, request: Any) -> dict[str, Any]:
        allowed = {"sessionId", "gameId", "action", "slot", "discId"}
        if not isinstance(request, dict) or not set(request).issubset(allowed):
            raise ValueError("schema inválido")
        if not {"sessionId", "gameId", "action"}.issubset(request):
            raise ValueError("schema inválido")
        if (
            _bounded_text(request.get("sessionId")) != self.owner.session_id
            or _bounded_text(request.get("gameId")) != self.owner.game_id
        ):
            return {
                "accepted": False,
                "state": "unknown",
                "diagnostic": DIAG_CONTROL_REQUEST,
                "detail": "A sessão não corresponde ao processo controlado.",
            }
        action = _bounded_text(request.get("action"), limit=16)
        if action not in {
            "pause",
            "resume",
            "listSaveStates",
            "saveState",
            "loadState",
            "listDiscs",
            "swapDisc",
            "listPeripherals",
        }:
            return {
                "accepted": False,
                "state": "unknown",
                "diagnostic": DIAG_CONTROL_REQUEST,
                "detail": "A ação da sessão não é permitida.",
            }
        try:
            if action == "pause":
                record = self.owner.suspend()
            elif action == "resume":
                record = self.owner.resume()
            elif action == "listSaveStates":
                current = self.owner.current
                if current is None:
                    raise RuntimeError("a sessão não está mais disponível")
                return {
                    "accepted": True,
                    "state": current.state,
                    "data": self.owner.list_save_states(),
                }
            elif action == "listDiscs":
                current = self.owner.current
                if current is None:
                    raise RuntimeError("a sessão não está mais disponível")
                return {
                    "accepted": True,
                    "state": current.state,
                    "data": self.owner.list_discs(),
                }
            elif action == "listPeripherals":
                current = self.owner.current
                if current is None:
                    raise RuntimeError("a sessão não está mais disponível")
                return {
                    "accepted": True,
                    "state": current.state,
                    "data": self.owner.list_peripherals(),
                }
            elif action in {"saveState", "loadState"}:
                slot = request.get("slot")
                if isinstance(slot, bool) or not isinstance(slot, int) or not 0 <= slot <= 999:
                    raise ValueError("slot de save-state inválido")
                record = (
                    self.owner.save_state(slot)
                    if action == "saveState"
                    else self.owner.load_state(slot)
                )
            else:
                disc_id = request.get("discId")
                if not isinstance(disc_id, str):
                    raise ValueError("disco não informado")
                record = self.owner.swap_disc(disc_id)
        except Exception:
            current = self.owner.current
            return {
                "accepted": False,
                "state": current.state if current is not None else "unknown",
                "diagnostic": DIAG_CONTROL_FAILED,
                "detail": "A operação da sessão falhou; atualize o overlay e tente novamente.",
            }
        return {"accepted": True, "state": record.state}


class RemoteSessionControl:
    """Proxy usado pelo adapter da ponte; não conhece PID nem envia sinais."""

    def __init__(self, path: Path, session_id: str, game_id: str, observe: ObserveSession) -> None:
        self._path = Path(path)
        self._session_id = session_id
        self._game_id = game_id
        self._observe = observe

    @property
    def current(self) -> SessionControlRecord | None:
        observed = dict(self._observe(self._game_id))
        if observed.get("sessionId") != self._session_id or observed.get("gameId") != self._game_id:
            return None
        return SessionControlRecord(
            id=self._session_id,
            game_id=self._game_id,
            state=_bounded_text(observed.get("state"), limit=32) or "unknown",
        )

    def suspend(self) -> SessionControlRecord:
        return self._request("pause")

    def resume(self) -> SessionControlRecord:
        return self._request("resume")

    def _request(self, action: str, **extra: Any) -> SessionControlRecord:
        request: dict[str, Any] = {
            "sessionId": self._session_id,
            "gameId": self._game_id,
            "action": action,
        }
        request.update(extra)
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(1.0)
                connection.connect(str(self._path))
                connection.sendall(json.dumps(request, separators=(",", ":")).encode() + b"\n")
                response = json.loads(_read_line(connection).decode("utf-8"))
        except (OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("o dono da sessão não respondeu") from exc
        if not isinstance(response, dict) or response.get("accepted") is not True:
            raise RuntimeError("o dono da sessão recusou a operação")
        current = self.current
        if current is None:
            raise RuntimeError("a sessão não está mais disponível")
        return current

    def _request_data(self, action: str) -> Mapping[str, Any]:
        request = {
            "sessionId": self._session_id,
            "gameId": self._game_id,
            "action": action,
        }
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(1.0)
                connection.connect(str(self._path))
                connection.sendall(json.dumps(request, separators=(",", ":")).encode() + b"\n")
                response = json.loads(_read_line(connection).decode("utf-8"))
        except (OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("o dono da sessão não respondeu") from exc
        data = response.get("data") if isinstance(response, dict) else None
        if (
            not isinstance(response, dict)
            or response.get("accepted") is not True
            or not isinstance(data, Mapping)
        ):
            raise RuntimeError("o dono da sessão recusou a consulta")
        return data

    def list_save_states(self) -> Mapping[str, Any]:
        return self._request_data("listSaveStates")

    def save_state(self, slot: int) -> SessionControlRecord:
        return self._request("saveState", slot=slot)

    def load_state(self, slot: int) -> SessionControlRecord:
        return self._request("loadState", slot=slot)

    def list_discs(self) -> Mapping[str, Any]:
        return self._request_data("listDiscs")

    def swap_disc(self, disc_id: str) -> SessionControlRecord:
        return self._request("swapDisc", discId=disc_id)

    def list_peripherals(self) -> Mapping[str, Any]:
        return self._request_data("listPeripherals")


def control_path(session_id: str, *, root: Path | None = None) -> Path:
    """Retorna o endpoint derivado de um id ULID, sem aceitar caminhos externos."""
    safe_id = _bounded_text(session_id, limit=128)
    if not safe_id or any(character in safe_id for character in "/\\\x00"):
        raise ValueError("sessionId inválido")
    return (root or paths.state_home() / CONTROL_DIRECTORY) / f"{safe_id}.sock"


def resolve_remote_session_control(
    session_id: str,
    game_id: str,
    *,
    observe: ObserveSession,
    root: Path | None = None,
) -> RemoteSessionControl | None:
    try:
        endpoint = control_path(session_id, root=root)
        if not endpoint.is_socket():
            return None
    except (OSError, ValueError):
        return None
    return RemoteSessionControl(endpoint, session_id, game_id, observe)


__all__ = [
    "DIAG_CONTROL_FAILED",
    "DIAG_CONTROL_REQUEST",
    "DIAG_CONTROL_UNAVAILABLE",
    "RemoteSessionControl",
    "SessionControlOwner",
    "SessionControlRecord",
    "SessionControlServer",
    "control_path",
    "resolve_remote_session_control",
]
