# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Tradução de ações abstratas para o autoconfig Qt (Eden, Citron, Ryubing).

Espelha `retropad.py`, que faz o mesmo para o RetroArch, e mantém a mesma
disciplina: o valor devolvido é a entrada ABSTRATA (``button.south``), nunca um
número de botão. O número pertence ao dispositivo físico, que o perfil não
conhece; resolvê-lo é trabalho do adapter, contra o pad real.

Posição, não letra. Um mesmo botão físico chama-se A no Nintendo e B no Xbox:
mapear por letra troca os botões em silêncio, e o jogador só descobre quando o
pulo vira ataque. Por isso a tabela liga ação → POSIÇÃO no losango, e a posição
→ botão do Switch acontece aqui, uma única vez, documentada.

Saída do jogo: ver `EXIT_HOTKEY`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from steamzero.core.errors import SteamZeroError

#: Ação abstrata → chave de botão no `qt-config.ini`.
#:
#: O losango do Switch: A=leste, B=sul, X=norte, Y=oeste. As ações abstratas do
#: perfil usam posição (``button.south``), então a correspondência é posicional
#: e o rótulo impresso no controle não participa da decisão.
_ACTION_TO_QT: dict[str, str] = {
    "game.primary": "button_b",  # sul
    "game.secondary": "button_a",  # leste
    "game.tertiary": "button_y",  # oeste
    "game.quaternary": "button_x",  # norte
    "game.start": "button_plus",
    "game.select": "button_minus",
    "game.shoulder-left": "button_l",
    "game.shoulder-right": "button_r",
    "game.up": "button_dup",
    "game.down": "button_ddown",
    "game.left": "button_dleft",
    "game.right": "button_dright",
}

#: Combinação de saída, alinhada ao que o ecossistema já usa.
#:
#: RetroPie, Batocera, RetroDECK e EmuDeck convergiram em Select+Start; no
#: Switch isso é Minus+Plus. Adotar o mesmo gesto evita que cada emulador
#: ensine uma saída diferente. O tempo de retenção existe porque os dois botões
#: são usados em jogo e pressioná-los juntos por acidente acontece — sair no
#: meio de uma partida sem salvar é dano real.
EXIT_HOTKEY: tuple[str, ...] = ("game.select", "game.start")
EXIT_HOLD_SECONDS = 1.0


#: Entrada abstrata → índice do SDL GameController.
#:
#: Diferente do número de botão bruto do dispositivo, este índice é
#: padronizado pelo SDL: é justamente o que a camada GameController existe para
#: garantir. Por isso a tradução é pura e vive aqui, enquanto o GUID — que É
#: propriedade do dispositivo — continua sendo resolvido pelo adapter.
_ABSTRACT_TO_SDL_BUTTON: dict[str, int] = {
    "button.south": 0,
    "button.east": 1,
    "button.west": 2,
    "button.north": 3,
    "button.select": 4,
    "button.start": 6,
    "shoulder.left": 9,
    "shoulder.right": 10,
    "hat.up": 11,
    "hat.down": 12,
    "hat.left": 13,
    "hat.right": 14,
}


def sdl_button(entrada: str) -> int:
    """Índice SDL GameController para uma entrada abstrata do perfil."""
    index = _ABSTRACT_TO_SDL_BUTTON.get(entrada)
    if index is None:
        raise SteamZeroError("E-API-SCHEMA", detail=f"entrada sem equivalente SDL: {entrada}")
    return index


def render_player_bindings(
    bindings: Sequence[Mapping[str, Any]],
    *,
    guid: str,
    player: int = 0,
    port: int = 0,
) -> dict[str, str]:
    """Linhas de `qt-config.ini` que ligam um jogador ao pad físico.

    O GUID vem do adapter porque identifica o dispositivo. Sem ele não há
    projeção possível: um autoconfig sem GUID é aceito pelo emulador e ignorado
    — falha silenciosa, que é o resultado a evitar.
    """
    if not guid or len(guid) != 32 or any(c not in "0123456789abcdef" for c in guid):
        raise SteamZeroError("E-API-SCHEMA", detail=f"GUID SDL inválido: {guid!r}")
    if player < 0 or port < 0:
        raise SteamZeroError("E-API-SCHEMA", detail="jogador e porta não podem ser negativos")
    rendered: dict[str, str] = {}
    for key, entrada in translate_bindings(bindings).items():
        index = sdl_button(entrada)
        rendered[f"player_{player}_{key}"] = f'"engine:sdl,guid:{guid},port:{port},button:{index}"'
    return rendered


def qt_key(action: str) -> str:
    """Chave do `qt-config.ini` para uma ação do SteamZero."""
    button = _ACTION_TO_QT.get(action)
    if button is None:
        raise SteamZeroError("E-API-SCHEMA", detail=f"ação sem equivalente Qt: {action}")
    return button


def translate_bindings(bindings: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """Traduz bindings resolvidos em chave Qt → entrada abstrata.

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
        traduzido[qt_key(action)] = entrada
    return traduzido


def untranslatable(bindings: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    """Ações sem equivalente Qt, em ordem estável.

    Existe para que a UI possa DIZER o que não vai valer, em vez de o perfil
    prometer um mapeamento completo e entregar menos.
    """
    return tuple(
        sorted(
            {
                str(b.get("action") or "")
                for b in bindings
                if str(b.get("action") or "") not in _ACTION_TO_QT
            }
            - {""}
        )
    )
