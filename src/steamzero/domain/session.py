# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Session Manager (F-SD-01, F-SV-02): ciclo de sessão de jogo.

Estados: idle→launching→running→(suspending→suspended→resuming→running)→
closing→closed | failed. Na suspensão (FM-09/DF-3): pausa jobs em ponto de
segurança, faz flush semântico do save e registra checkpoint; se o flush não
confirma a tempo, usa o checkpoint anterior (E-SAVES-FLUSH-TIMEOUT). No
fechamento (FM-08): escala fechamento semântico → SIGTERM → (confirmação) SIGKILL,
sempre preservando a timeline de saves. O controle do processo/emulador é uma
**porta** injetada; o domínio não mata processos diretamente.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol

from steamzero.core import ids
from steamzero.core.state import StateStore

if TYPE_CHECKING:
    from steamzero.jobs.manager import JobManager

VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    "idle": frozenset({"launching"}),
    "launching": frozenset({"running", "failed"}),
    "running": frozenset({"suspending", "closing", "failed"}),
    "suspending": frozenset({"suspended", "failed"}),
    "suspended": frozenset({"resuming", "closing"}),
    "resuming": frozenset({"running", "failed"}),
    "closing": frozenset({"closed", "failed"}),
    "closed": frozenset(),
    "failed": frozenset(),
}


class SessionPort(Protocol):
    """Controle do processo/emulador em execução."""

    def launch(self, game_id: str) -> bool: ...
    def is_alive(self) -> bool: ...
    def flush_save(self) -> bool: ...  # ação semântica; True = confirmado a tempo
    def signal_close(self) -> None: ...  # pedido semântico de sair
    def terminate(self) -> None: ...  # SIGTERM
    def kill(self) -> None: ...  # SIGKILL


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class Session:
    id: str
    game_id: str
    state: str
    checkpoints: list[dict[str, Any]] = field(default_factory=list)
    last_warning: str | None = None
    needs_kill_confirmation: bool = False


class SessionManager:
    def __init__(
        self, port: SessionPort, store: StateStore, *, job_manager: JobManager | None = None
    ) -> None:
        self._port = port
        self._store = store
        self._jobs = job_manager
        self._session: Session | None = None

    @property
    def current(self) -> Session | None:
        return self._session

    def is_active(self) -> bool:
        """True se há jogo em andamento (running/suspended) — usado por JobManager."""
        return self._session is not None and self._session.state in ("running", "suspended")

    def _transition(self, session: Session, new_state: str) -> None:
        if new_state not in VALID_TRANSITIONS.get(session.state, frozenset()):
            raise ValueError(f"transição de sessão inválida: {session.state} -> {new_state}")
        session.state = new_state
        self._store.append_event(
            "job.state", entity=f"session:{session.id}", payload={"state": new_state}
        )

    # -- ciclo --------------------------------------------------------------
    def launch(self, game_id: str) -> Session:
        session = Session(id=ids.new_ulid(), game_id=game_id, state="idle")
        self._session = session
        self._transition(session, "launching")
        if not self._port.launch(game_id):
            self._transition(session, "failed")
            return session
        self._transition(session, "running")
        return session

    def suspend(self) -> Session:
        session = self._require()
        self._transition(session, "suspending")
        # FI-09: pausa jobs em ponto de segurança antes de suspender
        if self._jobs is not None:
            for job in self._jobs.list_jobs(states=["running"]):
                self._jobs.request_pause(job.id)
        # DF-3: flush semântico + checkpoint
        if self._port.flush_save():
            session.checkpoints.append({"ts": _now_iso(), "origin": "flush"})
            session.last_warning = None
        else:
            session.last_warning = "E-SAVES-FLUSH-TIMEOUT"  # usa checkpoint anterior
            session.checkpoints.append({"ts": _now_iso(), "origin": "pre-flush-fallback"})
        self._transition(session, "suspended")
        return session

    def resume(self) -> Session:
        session = self._require()
        self._transition(session, "resuming")
        if not self._port.is_alive():  # camada quebrada
            session.last_warning = "E-SESSION-RESUME-DEGRADED"
        else:
            session.last_warning = None
        self._transition(session, "running")
        return session

    def close(self, *, allow_kill: bool = False) -> Session:
        session = self._require()
        if session.state != "closing":  # primeira tentativa: escalada até SIGTERM
            self._transition(session, "closing")
            self._port.flush_save()  # preserva a timeline antes de encerrar
            self._port.signal_close()
            if self._port.is_alive():
                self._port.terminate()  # SIGTERM
        if self._port.is_alive():
            if not allow_kill:  # FM-08: SIGKILL exige confirmação
                session.needs_kill_confirmation = True
                return session
            self._port.kill()  # SIGKILL confirmado
        session.needs_kill_confirmation = False
        self._transition(session, "closed")
        return session

    def _require(self) -> Session:
        if self._session is None:
            raise ValueError("nenhuma sessão ativa")
        return self._session
