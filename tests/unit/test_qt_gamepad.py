# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Tradução de perfil de controle para o autoconfig Qt (Eden, Citron, Ryubing).

Defeito de origem, observado no host: o perfil era ativado, a UI dizia "Perfil
selecionado", e o `qt-config.ini` do emulador continuava mapeado para teclado —
capacidade que reporta sucesso sem efeito observável.
"""

from __future__ import annotations

import pytest

from steamzero.core.errors import SteamZeroError
from steamzero.domain.qt_gamepad import (
    EXIT_HOLD_SECONDS,
    EXIT_HOTKEY,
    render_player_bindings,
    sdl_button,
    translate_bindings,
    untranslatable,
)

_GUID = "03000000de2800000512000011010000"

_PERFIL = (
    {"action": "game.up", "input": "hat.up"},
    {"action": "game.right", "input": "hat.right"},
    {"action": "game.down", "input": "hat.down"},
    {"action": "game.left", "input": "hat.left"},
    {"action": "game.primary", "input": "button.south"},
    {"action": "game.secondary", "input": "button.east"},
    {"action": "game.tertiary", "input": "button.west"},
    {"action": "game.quaternary", "input": "button.north"},
    {"action": "game.start", "input": "button.start"},
    {"action": "game.select", "input": "button.select"},
    {"action": "game.shoulder-left", "input": "shoulder.left"},
    {"action": "game.shoulder-right", "input": "shoulder.right"},
)


def test_losango_mapeia_por_posicao_e_nao_por_letra() -> None:
    """O botão de baixo é B no Switch e A no Xbox.

    Mapear por letra troca os botões em silêncio: o jogador só descobre quando o
    pulo vira ataque. A tabela liga posição → botão do Switch, uma única vez.
    """
    traduzido = translate_bindings(_PERFIL)
    assert traduzido["button_b"] == "button.south"
    assert traduzido["button_a"] == "button.east"
    assert traduzido["button_y"] == "button.west"
    assert traduzido["button_x"] == "button.north"


def test_render_liga_cada_acao_ao_indice_sdl_do_pad() -> None:
    rendered = render_player_bindings(_PERFIL, guid=_GUID)
    assert rendered["player_0_button_b"] == (f'"engine:sdl,guid:{_GUID},port:0,button:0"')
    assert rendered["player_0_button_a"] == (f'"engine:sdl,guid:{_GUID},port:0,button:1"')
    assert rendered["player_0_button_dup"].endswith('button:11"')
    assert len(rendered) == len(_PERFIL)
    assert all(key.startswith("player_0_") for key in rendered)


def test_render_recusa_guid_invalido_em_vez_de_gerar_perfil_morto() -> None:
    """Autoconfig sem GUID válido é aceito pelo emulador e ignorado.

    Recusar é melhor que entregar um arquivo que parece certo e não liga nada.
    """
    for ruim in ("", "curto", "Z" * 32, _GUID[:-1]):
        with pytest.raises(SteamZeroError, match="GUID SDL inválido"):
            render_player_bindings(_PERFIL, guid=ruim)


def test_render_respeita_jogador_e_porta() -> None:
    rendered = render_player_bindings(_PERFIL, guid=_GUID, player=1, port=2)
    assert all(key.startswith("player_1_") for key in rendered)
    assert rendered["player_1_button_b"].endswith('port:2,button:0"')
    with pytest.raises(SteamZeroError, match="negativos"):
        render_player_bindings(_PERFIL, guid=_GUID, player=-1)


def test_acao_duplicada_e_recusada() -> None:
    with pytest.raises(SteamZeroError, match="ação duplicada"):
        translate_bindings([*_PERFIL, {"action": "game.primary", "input": "button.north"}])


def test_acao_e_entrada_desconhecidas_sao_recusadas() -> None:
    with pytest.raises(SteamZeroError, match="sem equivalente Qt"):
        translate_bindings([{"action": "game.gyro", "input": "motion.pitch"}])
    with pytest.raises(SteamZeroError, match="sem equivalente SDL"):
        sdl_button("touch.swipe")


def test_untranslatable_diz_o_que_nao_vale_em_ordem_estavel() -> None:
    faltando = untranslatable(
        [*_PERFIL, {"action": "game.gyro", "input": "x"}, {"action": "game.rumble", "input": "y"}]
    )
    assert faltando == ("game.gyro", "game.rumble")


def test_saida_segue_o_padrao_do_ecossistema_com_retencao() -> None:
    """Select+Start é o gesto que RetroPie, Batocera, RetroDECK e EmuDeck usam.

    A retenção existe porque os dois botões são usados em jogo: sair no meio de
    uma partida sem salvar é dano real, não incômodo.
    """
    assert EXIT_HOTKEY == ("game.select", "game.start")
    assert EXIT_HOLD_SECONDS >= 1.0
