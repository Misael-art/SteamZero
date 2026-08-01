# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Sondagem read-only e injetável da prontidão real do Feral GameMode (G29).

Consulta exclusivamente: presença de binários (``which``), o daemon via
``gamemoded -s`` ou a existência do socket, a autorização conectando no socket
do daemon (sem enviar requisição), sysfs/proc (governor e split lock) e o State
Store de sessões do SteamZero. Nunca altera o host e nunca expõe argv, stdout
ou paths privados no modelo — a saída é o ``GameModeTruth`` sanitizado.

Toda dependência (which, runner, leitura, conexão, relógio, store) é injetável
para que os testes sejam determinísticos e não toquem ferramentas reais do
host. Falha ou timeout de qualquer etapa vira ``unknown``, nunca falso verde.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from steamzero.core.session_state import SESSION_OWNER
from steamzero.core.state import StateStore
from steamzero.domain.gamemode import GameModeTruth, build_truth

Which = Callable[[str], str | None]
Runner = Callable[[Sequence[str], float], subprocess.CompletedProcess[str]]
ReadText = Callable[[Path], str]
ConnectUnix = Callable[[Path], str]

_DEFAULT_GOVERNOR = Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
_DEFAULT_SPLIT_LOCK = Path("/proc/sys/kernel/split_lock_mitigate")
_DEFAULT_TIMEOUT = 3.0


def _run_status(argv: Sequence[str], timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 — argv fixo interno (gamemoded -s), LC_ALL=C
        argv,
        capture_output=True,
        text=True,
        timeout=timeout,
        env={**os.environ, "LC_ALL": "C"},
        check=False,
    )


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").strip()


def _connect_unix(path: Path) -> str:
    """Conecta e fecha imediatamente: verifica existência/permissão, sem requisição."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(1.0)
            sock.connect(str(path))
        return "ok"
    except PermissionError:
        return "permission-denied"
    except FileNotFoundError:
        return "absent"
    except OSError:
        return "error"


def _default_socket_path() -> Path:
    runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    return Path(runtime) / "gamemode.sock"


class GameModeProbe:
    """Sondagem read-only com dependências injetáveis (testável sem host real)."""

    def __init__(
        self,
        *,
        which: Which = shutil.which,
        runner: Runner = _run_status,
        read_text: ReadText = _read_text,
        connect_unix: ConnectUnix = _connect_unix,
        socket_path: Path | None = None,
        store_factory: Callable[[], StateStore] = StateStore,
        governor_path: Path = _DEFAULT_GOVERNOR,
        split_lock_path: Path = _DEFAULT_SPLIT_LOCK,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._which = which
        self._runner = runner
        self._read_text = read_text
        self._connect_unix = connect_unix
        self._socket_path = socket_path if socket_path is not None else _default_socket_path()
        self._store_factory = store_factory
        self._governor_path = governor_path
        self._split_lock_path = split_lock_path
        self._timeout = timeout

    def probe(self) -> GameModeTruth:
        """Observa o host e deriva a verdade; nunca levanta por falha de sondagem."""
        binary_state = self._binary_state()
        daemon_state = self._daemon_state()
        authorization_state = self._authorization_state(daemon_state)
        has_session, session_error = self._active_session()
        effects = self._effects(has_session)
        if session_error:
            activity_state = "unknown"
        elif not has_session:
            activity_state = "idle"
        elif any(value == "denied" for value in effects.values()):
            activity_state = "partial"
        else:
            activity_state = "active"
        return build_truth(
            binary_state=binary_state,
            daemon_state=daemon_state,
            authorization_state=authorization_state,
            activity_state=activity_state,
            effects=effects,
        )

    def _binary_state(self) -> str:
        try:
            return "present" if self._which("gamemoderun") is not None else "missing"
        except OSError:
            return "unknown"

    def _daemon_state(self) -> str:
        daemon = self._which("gamemoded")
        if daemon is None:
            # Sem binário para consultar: o socket indica se o daemon está ativo.
            result = self._connect_unix(self._socket_path)
            if result in {"ok", "permission-denied"}:
                return "available"
            if result == "absent":
                return "unavailable"
            return "unknown"
        try:
            completed = self._runner([daemon, "-s"], self._timeout)
        except (OSError, subprocess.TimeoutExpired):
            return "unknown"
        stdout = (completed.stdout or "").lower()
        if completed.returncode == 0 and "running" in stdout:
            return "available"
        if completed.returncode != 0 or "not running" in stdout:
            return "unavailable"
        return "unknown"

    def _authorization_state(self, daemon_state: str) -> str:
        if daemon_state != "available":
            return "unknown"
        result = self._connect_unix(self._socket_path)
        return {"ok": "authorized", "permission-denied": "denied"}.get(result, "unknown")

    def _active_session(self) -> tuple[bool, bool]:
        """(tem sessão ativa, erro de observação). Nunca levanta."""
        try:
            with self._store_factory() as store:
                store.migrate()
                session = store.active_game_session(SESSION_OWNER)
        except Exception:
            return False, True
        return session is not None, False

    def _effects(self, has_session: bool) -> dict[str, str]:
        """Efeitos só são evidenciados durante sessão ativa; idle nunca é falha."""
        if not has_session:
            return {key: "unknown" for key in ("governor", "splitLock", "ioprio")}
        return {
            "governor": self._effect_governor(),
            "splitLock": self._effect_split_lock(),
            "ioprio": "unknown",
        }

    def _effect_governor(self) -> str:
        try:
            value = self._read_text(self._governor_path).lower()
        except OSError:
            return "unknown"
        return "applied" if value == "performance" else "denied"

    def _effect_split_lock(self) -> str:
        try:
            value = self._read_text(self._split_lock_path).strip()
        except OSError:
            return "unknown"
        return "applied" if value == "0" else "denied"


def snapshot(
    *,
    which: Which = shutil.which,
    store_factory: Callable[[], StateStore] = StateStore,
    probe: GameModeProbe | None = None,
) -> dict[str, Any]:
    """Verdade observada em forma serializada, com falha degradando para unknown."""
    active = probe if probe is not None else GameModeProbe(which=which, store_factory=store_factory)
    try:
        return active.probe().to_dict()
    except Exception:
        return GameModeTruth.failure().to_dict()
