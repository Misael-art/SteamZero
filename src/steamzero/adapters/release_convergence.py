# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""HOST-ACTIVATION-01 — provar que o daemon convergiu para a release ativada.

A regressão da a37 não foi o instalador esquecer de reiniciar o daemon. O
instalador roda como root, as units são de escopo de usuário e valem para todos
os usuários da máquina: ele não sabe qual sessão reiniciar, e adivinhar UID,
``XDG_RUNTIME_DIR`` ou barramento seria pior que declarar pendência.

O defeito foi o fluxo de release **aceitar ``pending`` como se a promoção
estivesse concluída**. ``current`` apontava para a a37, o daemon respondia como
a35, e nada no caminho exigia que os dois coincidissem antes de alguém declarar
a release instalada.

Este módulo fecha esse buraco com três leituras que precisam concordar:

1. a release que o operador ESPERA — ``--expect-release``;
2. a release ATIVADA — o alvo de ``/opt/steamzero/current``;
3. a release que o daemon EM EXECUÇÃO reporta.

Uma discordância entre (1) e (2) é recusa **fechada**: não se reinicia nada.
Reiniciar aí seria agir sobre uma premissa errada — o operador pediu a a38 e a
máquina tem a a37 ativada, então ou o pedido está errado ou a instalação falhou,
e nos dois casos mexer no daemon piora o diagnóstico.

Uma discordância entre (2) e (3) é o estado ``pending``: é para isso que existe
o refresh.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

#: Onde a instalação publica a release ativa. O alvo do symlink é a verdade —
#: o nome do diretório é o `releaseId`.
CURRENT_LINK = Path("/opt/steamzero/current")

#: Códigos do contrato público. Texto humano muda; código não.
DIAG_MISMATCH = "E-HOST-RELEASE-MISMATCH"
DIAG_PENDING = "E-HOST-DAEMON-PENDING"
DIAG_TIMEOUT = "E-HOST-CONVERGENCE-TIMEOUT"
DIAG_RESTART = "E-HOST-RESTART-FAILED"
DIAG_UNREADABLE = "E-HOST-CURRENT-UNREADABLE"


class ConvergenceState(StrEnum):
    """Estado da convergência entre release ativada e daemon em execução.

    ``CONVERGED`` é o ÚNICO estado de sucesso. ``PENDING`` existia antes e era
    tratado como conclusão — foi exatamente esse tratamento que deixou a a37
    passar por instalada enquanto o daemon a35 respondia.
    """

    CONVERGED = "converged"
    PENDING = "pending"
    MISMATCH = "mismatch"
    TIMEOUT = "timeout"
    RESTART_FAILED = "restartFailed"
    UNREADABLE = "unreadable"

    @property
    def ok(self) -> bool:
        return self is ConvergenceState.CONVERGED


@dataclass(frozen=True)
class ConvergenceReport:
    """As três leituras, o veredito, e o suficiente para agir sobre ele."""

    state: ConvergenceState
    detail: str
    expected_release: str | None = None
    activated_release: str | None = None
    daemon_release: str | None = None
    daemon_commit: str | None = None
    code: str | None = None
    attempts: int = 0
    restarted: bool = False
    #: Passos executados, em ordem. Sem isto, um `timeout` não diz se o restart
    #: chegou a acontecer, e quem investiga não sabe por onde começar.
    steps: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return self.state.ok

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "state": self.state.value,
            "detail": self.detail,
            "restarted": self.restarted,
            "attempts": self.attempts,
        }
        for key, value in (
            ("expectedRelease", self.expected_release),
            ("activatedRelease", self.activated_release),
            ("daemonRelease", self.daemon_release),
            ("daemonCommit", self.daemon_commit),
            ("code", self.code),
        ):
            if value is not None:
                payload[key] = value
        if self.steps:
            payload["steps"] = list(self.steps)
        return payload


def read_activated_release(link: Path = CURRENT_LINK) -> str | None:
    """A release que a instalação ativou.

    O alvo do symlink é a fonte, não o ``manifest.json``. Ler o manifesto seria
    ler um arquivo que a release NOVA escreveu — e o processo antigo o leria
    afirmando ser ela, que é a mesma armadilha descrita em ``core.identity``.
    """
    try:
        if not link.is_symlink() and not link.exists():
            return None
        target = link.resolve()
    except OSError:
        return None
    name = target.name
    return name or None


def read_activated_manifest(link: Path = CURRENT_LINK) -> dict[str, Any]:
    """Manifesto da release ativada. Vazio quando ausente ou ilegível.

    Serve ao relatório, nunca à decisão: a decisão usa o alvo do symlink.
    """
    try:
        raw = (link / "manifest.json").read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _daemon_release(identity: dict[str, Any]) -> str | None:
    value = identity.get("releaseId")
    return str(value) if value else None


def observe(
    *,
    link: Path = CURRENT_LINK,
    probe: Callable[[], dict[str, Any]] | None = None,
) -> ConvergenceReport:
    """Observa a release ativa e o daemon sem reiniciar ou aguardar nada.

    ``service status`` não pode reutilizar :func:`converge`: até uma chamada
    aparentemente idempotente pode reiniciar as units quando encontra drift.
    Este caminho executa exatamente duas leituras e publica a divergência.
    """
    steps: list[str] = []
    activated = read_activated_release(link)
    steps.append("leu current")
    if activated is None:
        return ConvergenceReport(
            ConvergenceState.UNREADABLE,
            f"não foi possível ler a release ativada em {link}",
            code=DIAG_UNREADABLE,
            steps=tuple(steps),
        )

    read_identity = probe if probe is not None else _default_probe
    identity = _safe_probe(read_identity)
    steps.append("consultou o daemon")
    if identity is None:
        return ConvergenceReport(
            ConvergenceState.TIMEOUT,
            "o daemon não respondeu à consulta de status",
            activated_release=activated,
            code=DIAG_TIMEOUT,
            steps=tuple(steps),
        )

    daemon = _daemon_release(identity)
    daemon_commit = str(identity.get("sourceCommit") or "") or None
    if daemon == activated:
        return ConvergenceReport(
            ConvergenceState.CONVERGED,
            f"o daemon responde na release ativada {activated!r}",
            activated_release=activated,
            daemon_release=daemon,
            daemon_commit=daemon_commit,
            steps=tuple(steps),
        )

    if daemon is None:
        detail = f"o daemon respondeu sem declarar releaseId; current aponta para {activated!r}"
    else:
        detail = f"current aponta para {activated!r}, mas o daemon responde por {daemon!r}"
    return ConvergenceReport(
        ConvergenceState.PENDING,
        detail,
        activated_release=activated,
        daemon_release=daemon,
        daemon_commit=daemon_commit,
        code=DIAG_PENDING,
        steps=tuple(steps),
    )


def converge(
    *,
    expect_release: str | None = None,
    link: Path = CURRENT_LINK,
    probe: Callable[[], dict[str, Any]] | None = None,
    restart: Callable[[], tuple[bool, str]] | None = None,
    attempts: int = 10,
    interval: float = 0.3,
    sleep: Callable[[float], None] = time.sleep,
) -> ConvergenceReport:
    """Leva o daemon à release ativada, ou explica por que não foi possível.

    ``probe`` devolve a identidade do daemon em execução, ou levanta quando ele
    não responde. ``restart`` reinicia as units e devolve ``(ok, detalhe)``.
    Ambos são injetáveis para que a regressão da a37 possa ser encenada sem
    systemd.
    """
    steps: list[str] = []
    activated = read_activated_release(link)
    steps.append("leu current")
    if activated is None:
        return ConvergenceReport(
            ConvergenceState.UNREADABLE,
            f"não foi possível ler a release ativada em {link}",
            expected_release=expect_release,
            code=DIAG_UNREADABLE,
            steps=tuple(steps),
        )

    # RECUSA FECHADA. O operador esperava uma release e a máquina tem outra
    # ativada: ou o pedido está errado, ou a instalação não concluiu. Reiniciar
    # aqui agiria sobre premissa errada e apagaria a evidência do que falhou.
    if expect_release is not None and expect_release != activated:
        return ConvergenceReport(
            ConvergenceState.MISMATCH,
            f"esperava {expect_release!r}, mas {link} aponta para {activated!r}; "
            "nenhum serviço foi reiniciado",
            expected_release=expect_release,
            activated_release=activated,
            code=DIAG_MISMATCH,
            steps=tuple(steps),
        )

    read_identity = probe if probe is not None else _default_probe
    do_restart = restart if restart is not None else _default_restart

    # Idempotência: se o daemon JÁ está na release ativada, não se reinicia.
    # Reiniciar por precaução derrubaria uma sessão saudável a cada chamada.
    current_identity = _safe_probe(read_identity)
    steps.append("consultou o daemon")
    if current_identity is not None and _daemon_release(current_identity) == activated:
        return ConvergenceReport(
            ConvergenceState.CONVERGED,
            f"o daemon já responde na release {activated!r}; nada a fazer",
            expected_release=expect_release,
            activated_release=activated,
            daemon_release=activated,
            daemon_commit=str(current_identity.get("sourceCommit") or "") or None,
            steps=tuple(steps),
        )

    stale = _daemon_release(current_identity) if current_identity else None
    ok, detail = do_restart()
    steps.append("reiniciou as units")
    if not ok:
        return ConvergenceReport(
            ConvergenceState.RESTART_FAILED,
            f"não foi possível reiniciar o serviço: {detail}",
            expected_release=expect_release,
            activated_release=activated,
            daemon_release=stale,
            code=DIAG_RESTART,
            restarted=False,
            steps=tuple(steps),
        )

    for attempt in range(1, attempts + 1):
        identity = _safe_probe(read_identity)
        if identity is not None:
            released = _daemon_release(identity)
            if released == activated:
                steps.append("confirmou a release do daemon")
                return ConvergenceReport(
                    ConvergenceState.CONVERGED,
                    f"o daemon convergiu para {activated!r}",
                    expected_release=expect_release,
                    activated_release=activated,
                    daemon_release=released,
                    daemon_commit=str(identity.get("sourceCommit") or "") or None,
                    restarted=True,
                    attempts=attempt,
                    steps=tuple(steps),
                )
            # Respondeu, mas com outra release. É o estado da a37, agora com
            # nome — e sem sucesso.
            stale = released
        if attempt < attempts:
            sleep(interval)

    steps.append("esgotou as tentativas")
    state = ConvergenceState.PENDING if stale else ConvergenceState.TIMEOUT
    return ConvergenceReport(
        state,
        (
            f"o daemon continua respondendo na release {stale!r} depois do restart"
            if stale
            else f"o daemon não respondeu em {attempts} tentativas"
        ),
        expected_release=expect_release,
        activated_release=activated,
        daemon_release=stale,
        code=DIAG_PENDING if stale else DIAG_TIMEOUT,
        restarted=True,
        attempts=attempts,
        steps=tuple(steps),
    )


def _safe_probe(read_identity: Callable[[], dict[str, Any]]) -> dict[str, Any] | None:
    try:
        identity = read_identity()
    except Exception:
        # Daemon fora do ar é informação, não erro fatal: é o estado esperado
        # entre o stop e o start.
        return None
    return identity if isinstance(identity, dict) else None


def _default_probe() -> dict[str, Any]:
    from steamzero.service.client import daemon_identity

    return daemon_identity()


def _default_restart() -> tuple[bool, str]:
    from steamzero.adapters.service_activation import refresh

    result = refresh()
    return result.state == "ready", result.detail
