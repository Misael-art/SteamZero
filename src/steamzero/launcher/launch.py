# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contexto de retorno do AURA Launcher.

Isto é o que o Launcher acrescenta e não existia: lembrar de onde o usuário saiu
para devolvê-lo ao mesmo lugar quando o jogo fechar. Cair no topo da home a cada
partida obrigaria a percorrer a biblioteca de novo.

O que **não** está aqui, de propósito: criar o processo do jogo. Quem lança é
``EmulationController.launch_game``, que valida chaves, recusa update e DLC,
resolve o executor pela fonte fixada no manifesto e registra a sessão. Uma
versão anterior deste módulo spawnava por conta própria e perdia as quatro
coisas de uma vez.

O contexto atravessa processos porque o launcher pode reiniciar sem derrubar o
jogo, e a escrita é atômica: um retorno lê exatamente no momento em que uma
gravação comum poderia estar pela metade.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from steamzero.core import fs

DIAG_CONTEXT_LOST = "LAUNCHER-CONTEXT-LOST-001"
_FOCUS_ID = re.compile(r"^[a-z][a-zA-Z0-9-]{0,63}:[a-zA-Z0-9-]{1,64}$")


def remember_return(path: Path | str, *, game_id: str, focus_id: str) -> None:
    """Grava onde o usuário estava, antes de o jogo começar."""
    payload = {"gameId": str(game_id), "focusId": str(focus_id)}
    fs.write_atomic_text(Path(path), json.dumps(payload, ensure_ascii=False))


def restore_return(path: Path | str) -> dict[str, Any] | None:
    """Lê o contexto e o remove, para não restaurar duas vezes.

    Ausência é normal: significa que ninguém lançou nada. Contexto ilegível vira
    ``None`` — adivinhar um retorno plausível levaria o usuário a um lugar que
    ele não escolheu.
    """
    target = Path(path)
    try:
        raw = target.read_text(encoding="utf-8")
    except OSError:
        return None
    fs.remove_file(target)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    focus = payload.get("focusId")
    if not isinstance(focus, str) or not _FOCUS_ID.fullmatch(focus):
        return None
    return payload
