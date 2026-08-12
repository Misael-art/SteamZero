# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Tradução dos bindings do SteamZero para a nomenclatura RetroPad do RetroArch.

O perfil de controle do SteamZero fala em ação e entrada ABSTRATAS
(``game.primary`` → ``button.south``). O RetroArch fala em RetroPad
(``input_b_btn``, ``input_start_btn``, ``input_up_axis``). Sem alguém traduzir,
o perfil é resolvido, gravado e nunca lido — que é a G45.

A tabela abaixo não foi escrita de memória. Foi lida dos autoconfigs que o
próprio RetroArch 1.22.2 empacota
(``share/libretro/autoconfig/udev/*.cfg``), onde as chaves aparecem 400+ vezes
cada e a correspondência sul/leste/oeste/norte → ``b``/``a``/``y``/``x`` é
visível nos perfis reais: um pad com ``input_b_btn`` e ``input_a_btn`` no par
inferior/direito.

Este módulo é PURO: traduz e recusa, sem tocar em disco. Escrever no host é
responsabilidade de quem chamar, e deve seguir o padrão do M11 — arquivo
gerenciado com marcador, nunca editar o ``retroarch.cfg`` do usuário.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from steamzero.core.errors import SteamZeroError

#: Ação abstrata → botão RetroPad. O sufixo (`_btn` ou `_axis`) é do RetroArch e
#: depende do tipo de entrada, não da ação; ver `retropad_key`.
_ACTION_TO_RETROPAD: dict[str, str] = {
    "game.primary": "b",
    "game.secondary": "a",
    "game.tertiary": "y",
    "game.quaternary": "x",
    "game.start": "start",
    "game.select": "select",
    "game.shoulder-left": "l",
    "game.shoulder-right": "r",
    "game.up": "up",
    "game.down": "down",
    "game.left": "left",
    "game.right": "right",
}

#: Entradas direcionais chegam como eixo nos autoconfigs reais; botões, como
#: botão. Escolher o sufixo errado produz um perfil que o RetroArch aceita e
#: ignora — falha silenciosa, o pior resultado possível aqui.
_AXIS_ACTIONS = frozenset({"game.up", "game.down", "game.left", "game.right"})


def retropad_key(action: str) -> str:
    """Chave de autoconfig do RetroArch para uma ação do SteamZero."""
    button = _ACTION_TO_RETROPAD.get(action)
    if button is None:
        raise SteamZeroError("E-API-SCHEMA", detail=f"ação sem equivalente RetroPad: {action}")
    suffix = "axis" if action in _AXIS_ACTIONS else "btn"
    return f"input_{button}_{suffix}"


def translate_bindings(bindings: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """Traduz bindings resolvidos em chaves RetroPad → entrada abstrata.

    Devolve a entrada ABSTRATA como valor (``button.south``), e não um número de
    botão: o número é propriedade do dispositivo físico, que o perfil não
    conhece. Quem escrever o autoconfig precisa resolver isso contra o pad real
    — e é melhor que essa etapa falte visivelmente do que seja inventada aqui.

    Ação repetida é recusada: duas ações na mesma chave produziriam um perfil em
    que a última vence em silêncio.
    """
    traduzido: dict[str, str] = {}
    vistos: set[str] = set()
    for binding in bindings:
        action = str(binding.get("action") or "")
        entrada = str(binding.get("input") or "")
        if not action or not entrada:
            raise SteamZeroError("E-API-SCHEMA", detail="binding sem ação ou entrada")
        if action in vistos:
            raise SteamZeroError("E-API-SCHEMA", detail=f"ação duplicada: {action}")
        vistos.add(action)
        traduzido[retropad_key(action)] = entrada
    return traduzido


def untranslatable(bindings: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    """Ações sem equivalente RetroPad, em ordem estável.

    Existe para que a UI possa DIZER o que não vai valer, em vez de o perfil
    prometer um mapeamento completo e entregar menos.
    """
    return tuple(
        sorted(
            {
                str(b.get("action") or "")
                for b in bindings
                if str(b.get("action") or "") not in _ACTION_TO_RETROPAD
            }
            - {""}
        )
    )
