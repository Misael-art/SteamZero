# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Criação do processo de jogo para o AURA Launcher.

Vive num adapter porque é aqui que o projeto permite `subprocess`. O domínio
decide o que lançar e o que salvar; este módulo só sabe criar o processo de um
jeito que sobreviva ao launcher.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from types import FrameType

#: A forma que ``signal.signal`` devolve: handler chamável ou uma das
#: constantes ``SIG_DFL``/``SIG_IGN``.
_Handler = Callable[[int, FrameType | None], object] | int | None

#: Quanto a cena tem para sair sozinha depois do SIGTERM, antes do SIGKILL.
TERMINATION_GRACE_SECONDS = 5.0


def spawn_detached(argv: tuple[str, ...]) -> int:
    """Cria o processo em sessão própria e devolve o PID.

    `start_new_session` tira o jogo do grupo de processos do launcher. Sem isso,
    um sinal dirigido ao grupo — Ctrl+C no terminal, ou o systemd encerrando o
    escopo do launcher — levaria o jogo junto, e o item 5 da Definition of Done
    exige o contrário.

    O argv chega validado por ``LaunchPlan``: sequência já separada, sem
    metacaractere de shell e sem travessia de diretório.
    """
    process = subprocess.Popen(  # noqa: S603 - argv validado em LaunchPlan
        argv,
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return process.pid


def spawn_supervised(
    argv: tuple[str, ...], *, env: Mapping[str, str] | None = None
) -> subprocess.Popen[bytes]:
    """Cria um processo filho que o supervisor consegue encerrar por inteiro.

    Ao contrário de :func:`spawn_detached`, aqui `start_new_session` NÃO serve
    para desacoplar: serve para dar ao filho um grupo próprio, para que o
    encerramento leve junto qualquer neto (o `qml6` costuma ser um wrapper) sem
    que o sinal volte para o launcher.
    """
    return subprocess.Popen(  # noqa: S603 - argv fixo, montado por quem chama
        list(argv),
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        env=dict(env) if env is not None else None,
    )


def _signal_group(process: subprocess.Popen[bytes], sig: int) -> None:
    """Sinaliza o grupo do filho, caindo para o PID quando o grupo sumiu."""
    try:
        os.killpg(os.getpgid(process.pid), sig)
    except (ProcessLookupError, PermissionError, OSError):
        with contextlib.suppress(ProcessLookupError, OSError):
            process.send_signal(sig)


def terminate_child(
    process: subprocess.Popen[bytes], *, grace_seconds: float = TERMINATION_GRACE_SECONDS
) -> None:
    """Encerra o filho e o grupo dele; SIGKILL se o prazo passar.

    Idempotente: chamar com o processo já morto não faz nada. É o que permite
    usar isto tanto no handler de sinal quanto no ``finally``.
    """
    if process.poll() is not None:
        return
    _signal_group(process, signal.SIGTERM)
    try:
        process.wait(timeout=grace_seconds)
        return
    except subprocess.TimeoutExpired:
        pass
    _signal_group(process, signal.SIGKILL)
    with contextlib.suppress(subprocess.TimeoutExpired):
        process.wait(timeout=grace_seconds)


@contextmanager
def supervised_child(
    argv: tuple[str, ...], *, env: Mapping[str, str] | None = None
) -> Iterator[subprocess.Popen[bytes]]:
    """Garante que o filho não sobreviva a este processo.

    Cobre os três jeitos de o launcher acabar: retorno normal, exceção e sinal
    (SIGTERM do systemd, SIGINT do terminal). Sem isso, matar o wrapper deixava
    o `qml6` órfão com uma janela Wayland de título e classe idênticos aos da
    sessão viva, mas já sem a ponte HTTP — uma janela que parece a UI e não é.
    Dois diagnósticos errados nasceram dessa confusão (item `aura-launcher`).

    SIGKILL no launcher continua fora de alcance: nenhum processo pode reagir a
    ele. Nesse caso o filho é adotado pelo init e some ao fechar a janela.
    """
    process = spawn_supervised(argv, env=env)

    def _handle(signum: int, _frame: object) -> None:
        terminate_child(process)

    installed: list[tuple[signal.Signals, _Handler]] = []
    for signum in (signal.SIGTERM, signal.SIGINT):
        # Só a thread principal instala handler; num worker o `finally`
        # continua sendo a rede de proteção.
        with contextlib.suppress(ValueError, OSError):
            installed.append((signum, signal.signal(signum, _handle)))
    try:
        yield process
    finally:
        terminate_child(process)
        for restored, previous in installed:
            with contextlib.suppress(ValueError, OSError, TypeError):
                signal.signal(restored, previous)
