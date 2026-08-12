# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""G45: os bindings resolvidos deixam de ser gravados e nunca lidos.

A tabela testada aqui nao foi escrita de memoria — foi lida dos autoconfigs que
o proprio RetroArch 1.22.2 empacota, onde cada chave aparece 400+ vezes.
"""

from __future__ import annotations

import pytest

from steamzero.core.errors import SteamZeroError
from steamzero.domain.retropad import retropad_key, translate_bindings, untranslatable

_PERFIL_PADRAO = [
    {"action": "game.up", "input": "hat.up"},
    {"action": "game.down", "input": "hat.down"},
    {"action": "game.left", "input": "hat.left"},
    {"action": "game.right", "input": "hat.right"},
    {"action": "game.primary", "input": "button.south"},
    {"action": "game.secondary", "input": "button.east"},
    {"action": "game.tertiary", "input": "button.west"},
    {"action": "game.quaternary", "input": "button.north"},
    {"action": "game.start", "input": "button.start"},
    {"action": "game.select", "input": "button.select"},
    {"action": "game.shoulder-left", "input": "button.shoulder-left"},
    {"action": "game.shoulder-right", "input": "button.shoulder-right"},
]


class TestTheKeysRetroArchActuallyReads:
    def test_the_face_buttons_follow_the_retropad_layout(self) -> None:
        """Sul e `b`, leste e `a` — layout do RetroPad, nao do rotulo fisico.

        Trocar `a` por `b` produz um perfil que o RetroArch aceita e aplica com
        os botoes invertidos: o usuario aperta pular e volta ao menu. Por isso a
        correspondencia vem do artefato, nao de suposicao.
        """
        traduzido = translate_bindings(_PERFIL_PADRAO)
        assert traduzido["input_b_btn"] == "button.south"
        assert traduzido["input_a_btn"] == "button.east"
        assert traduzido["input_y_btn"] == "button.west"
        assert traduzido["input_x_btn"] == "button.north"

    def test_directionals_use_axis_and_buttons_use_btn(self) -> None:
        """Sufixo errado dá perfil que o RetroArch aceita e IGNORA.

        Falha silenciosa é o pior resultado aqui: nada reclama e nada funciona.
        """
        assert retropad_key("game.up") == "input_up_axis"
        assert retropad_key("game.primary") == "input_b_btn"
        traduzido = translate_bindings(_PERFIL_PADRAO)
        assert all(
            k.endswith("_axis")
            for k in traduzido
            if k.split("_")[1] in {"up", "down", "left", "right"}
        )

    def test_the_value_stays_abstract(self) -> None:
        """O numero do botao pertence ao dispositivo, que o perfil nao conhece.

        Inventar um indice aqui produziria autoconfig plausivel e errado. Melhor
        a etapa faltar visivelmente do que ser adivinhada.
        """
        traduzido = translate_bindings(_PERFIL_PADRAO)
        assert traduzido["input_b_btn"] == "button.south"
        assert not any(valor.isdigit() for valor in traduzido.values())

    def test_every_binding_of_the_bundled_profile_translates(self) -> None:
        assert len(translate_bindings(_PERFIL_PADRAO)) == len(_PERFIL_PADRAO)
        assert untranslatable(_PERFIL_PADRAO) == ()

    def test_an_action_without_equivalent_is_reported_not_dropped(self) -> None:
        """Silenciar o que nao traduz faria o perfil prometer mais do que vale."""
        extra = [*_PERFIL_PADRAO, {"action": "game.turbo", "input": "button.turbo"}]
        assert untranslatable(extra) == ("game.turbo",)
        with pytest.raises(SteamZeroError, match="sem equivalente RetroPad"):
            retropad_key("game.turbo")

    def test_a_duplicated_action_is_refused(self) -> None:
        """Duas acoes na mesma chave fariam a ultima vencer em silencio."""
        with pytest.raises(SteamZeroError, match="duplicada"):
            translate_bindings([*_PERFIL_PADRAO, {"action": "game.primary", "input": "button.x"}])

    def test_a_malformed_binding_is_refused(self) -> None:
        with pytest.raises(SteamZeroError, match="sem ação ou entrada"):
            translate_bindings([{"action": "game.primary"}])
