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
#:
#: Este palpite só vale enquanto NÃO há dispositivo. Medindo os 420 autoconfigs
#: empacotados com casamento exato de chave (que exclui as linhas `*_label`, as
#: quais contaminaram a contagem original), `input_up_btn` aparece em 296
#: arquivos contra 134 de `input_up_axis`: para a MAIORIA dos pads reais o
#: direcional é botão, não eixo. Por isso o sufixo aqui é PROVISÓRIO e
#: `steamzero.domain.retroarch_autoconfig` o substitui pelo que o dispositivo
#: declara antes de gravar qualquer coisa.
_AXIS_ACTIONS = frozenset({"game.up", "game.down", "game.left", "game.right"})

#: Entrada abstrata → slot RetroPad. É a mesma nomenclatura de
#: `_ACTION_TO_RETROPAD`, mas indexada pela POSIÇÃO FÍSICA em vez da ação: é
#: esta tabela que diz em qual chave do arquivo do dispositivo procurar o índice
#: real. Sem ela, remapear (mandar `game.primary` para a posição leste) não
#: teria como saber qual índice copiar.
_INPUT_TO_RETROPAD: dict[str, str] = {
    "button.south": "b",
    "button.east": "a",
    "button.west": "y",
    "button.north": "x",
    "button.start": "start",
    "button.select": "select",
    "button.shoulder-left": "l",
    "button.shoulder-right": "r",
    "hat.up": "up",
    "hat.down": "down",
    "hat.left": "left",
    "hat.right": "right",
}


def action_slot(action: str) -> str:
    """Slot RetroPad de uma ação, sem sufixo.

    O sufixo depende do dispositivo, não da ação; separar os dois é o que
    permite gravar `input_up_btn` num pad que declara o direcional como botão.
    """
    button = _ACTION_TO_RETROPAD.get(action)
    if button is None:
        raise SteamZeroError("E-API-SCHEMA", detail=f"ação sem equivalente RetroPad: {action}")
    return button


def retropad_slot(entrada: str) -> str:
    """Slot RetroPad de uma entrada abstrata (posição física)."""
    slot = _INPUT_TO_RETROPAD.get(entrada)
    if slot is None:
        raise SteamZeroError("E-API-SCHEMA", detail=f"entrada sem equivalente RetroPad: {entrada}")
    return slot


def retropad_key(action: str) -> str:
    """Chave de autoconfig do RetroArch para uma ação do SteamZero.

    Sufixo PROVISÓRIO: ver `_AXIS_ACTIONS`. Serve à visão sem dispositivo; quem
    grava arquivo usa `retroarch_autoconfig.resolve`.
    """
    button = action_slot(action)
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
