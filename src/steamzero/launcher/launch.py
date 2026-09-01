# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Lançamento de jogo e retorno ao contexto, no AURA Launcher.

Dois requisitos da Definition of Done moldam este módulo:

* o jogo continua rodando se o launcher reiniciar (item 5) — por isso o
  processo nasce em sessão própria, e não como filho preso ao launcher;
* o retorno recai no mesmo contexto (item 4) — por isso o contexto vai para
  disco **antes** do processo existir.

A ordem importa: gravar depois do spawn abriria uma janela em que o jogo já
roda e o lugar do usuário ainda não foi salvo. Se o launcher morresse ali, a
volta cairia na home genérica.

O argv é uma sequência já separada. String de shell não é aceita: montar
comando por concatenação é como um caminho de jogo com aspas vira execução de
outra coisa.

Nada aqui toca o sistema diretamente: a escrita passa por ``core.fs`` e quem
cria o processo é injetado por quem chama, porque `subprocess` pertence aos
adapters. A primeira versão deste módulo fazia as duas coisas à mão e o gate de
fronteiras a recusou — com razão, porque a gravação atômica já existia pronta.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from steamzero.core import fs
from steamzero.launcher.identifiers import is_focus_id, is_identifier

DIAG_CONTEXT_LOST = "LAUNCHER-CONTEXT-LOST-001"
MAX_ARGV = 64
_UNSAFE_ARGUMENT = re.compile(r"[;&|`$\n\r]")

Spawn = Callable[[tuple[str, ...]], int]


@dataclass(frozen=True)
class LaunchPlan:
    game_id: str
    argv: Sequence[str]
    focus_id: str
    context_path: Path

    def __post_init__(self) -> None:
        if not is_identifier(self.game_id):
            raise ValueError(f"game id inválido: {self.game_id!r}")
        if not is_focus_id(self.focus_id):
            raise ValueError(f"focus id inválido: {self.focus_id!r}")
        if isinstance(self.argv, str) or not isinstance(self.argv, tuple | list):
            raise ValueError("argv precisa ser sequência já separada, não string de shell")
        if not self.argv or len(self.argv) > MAX_ARGV:
            raise ValueError(f"argv precisa ter 1..{MAX_ARGV} elementos")
        for item in self.argv:
            if not isinstance(item, str) or not item:
                raise ValueError("argv aceita somente strings não vazias")
            if _UNSAFE_ARGUMENT.search(item):
                raise ValueError(f"argumento com metacaractere de shell: {item!r}")
        if ".." in Path(self.argv[0]).parts:
            raise ValueError("executável com travessia de diretório")
        object.__setattr__(self, "context_path", Path(self.context_path))

    def context_payload(self) -> dict[str, str]:
        return {"gameId": self.game_id, "focusId": self.focus_id}


@dataclass(frozen=True)
class LaunchHandle:
    pid: int
    game_id: str


def launch_detached(plan: LaunchPlan, *, spawn: Spawn) -> LaunchHandle:
    """Grava o contexto e então lança o jogo desacoplado do launcher.

    ``spawn`` é obrigatório: quem cria processo é o adapter, não o domínio.

    A ordem é deliberada e testada: o contexto vai para o disco ANTES do spawn,
    para que um crash no meio da criação do processo não perca o lugar do
    usuário. Se o próprio spawn falhar (executável ausente, erro de execução o
    jogo nunca chegou a iniciar — e o contexto pendurado levaria uma sessão
    futura a devolver o foco para um jogo que não roda. Nesse caso o contexto é
    removido e a falha é sinalizada, para que a UI aja em vez de fingir sucesso.
    """
    payload = json.dumps(plan.context_payload(), ensure_ascii=False)
    fs.write_atomic_text(plan.context_path, payload)
    try:
        pid = spawn(tuple(plan.argv))
    except BaseException:
        fs.remove_file(plan.context_path)
        raise
    return LaunchHandle(pid=pid, game_id=plan.game_id)


def consume_context(path: Path | str, *, with_diagnostics: bool = False) -> Any:
    """Lê o contexto de retorno e o remove, para não restaurar duas vezes.

    Contexto ausente é normal: significa que ninguém lançou nada. Contexto
    ilegível é anomalia e vira diagnóstico — adivinhar um retorno plausível
    levaria o usuário para um lugar que ele não escolheu.
    """
    target = Path(path)
    diagnostics: list[dict[str, str]] = []
    try:
        raw = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return (None, diagnostics) if with_diagnostics else None
    except OSError as exc:
        diagnostics.append(
            {
                "code": DIAG_CONTEXT_LOST,
                "reason": f"contexto ilegível: {exc}",
                "fallback": "home",
            }
        )
        return (None, diagnostics) if with_diagnostics else None
    fs.remove_file(target)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        diagnostics.append(
            {
                "code": DIAG_CONTEXT_LOST,
                "reason": f"contexto corrompido: {exc.msg}",
                "fallback": "home",
            }
        )
        return (None, diagnostics) if with_diagnostics else None
    if not isinstance(payload, dict):
        diagnostics.append(
            {
                "code": DIAG_CONTEXT_LOST,
                "reason": "contexto não é objeto",
                "fallback": "home",
            }
        )
        return (None, diagnostics) if with_diagnostics else None
    return (payload, diagnostics) if with_diagnostics else payload
