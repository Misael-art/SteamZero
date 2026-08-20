# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Criação do processo de jogo para o AURA Launcher.

Vive num adapter porque é aqui que o projeto permite `subprocess`. O domínio
decide o que lançar e o que salvar; este módulo só sabe criar o processo de um
jeito que sobreviva ao launcher.
"""

from __future__ import annotations

import subprocess


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
