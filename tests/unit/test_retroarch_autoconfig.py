# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""G45: o indice do botao deixa de faltar sem deixar de ser lido do dispositivo.

As fixtures nao foram escritas de memoria. `_STEAM_CONTROLLER` e o conteudo
literal de `Steam_Controller.cfg` empacotado pelo RetroArch 1.22.2, e os tokens
exoticos exercitados aqui (`h0up`, `nul`, `-0`, `"ZR Button"`) foram medidos nos
420 arquivos de `share/libretro/autoconfig/udev/`.
"""

from __future__ import annotations

import pytest

from steamzero.core.errors import SteamZeroError
from steamzero.domain.retroarch_autoconfig import (
    MANAGED_MARKER,
    Autoconfig,
    DeviceIdentity,
    is_managed,
    parse_autoconfig,
    render_managed,
    resolve,
)

# Trecho literal de Steam_Controller.cfg (RetroArch 1.22.2). O direcional deste
# pad e EIXO, e `input_left_axis = "-0"` tem sinal significativo.
_STEAM_CONTROLLER = """
input_display_name = "Valve Steam Controller"
input_vendor_id = "10462"
input_product_id = "1142"

input_driver = "udev"
input_device = "Steam Controller"
input_b_btn = "0"
input_y_btn = "2"
input_select_btn = "6"
input_start_btn = "7"
input_up_axis = "-1"
input_down_axis = "+1"
input_left_axis = "-0"
input_right_axis = "+0"
input_a_btn = "1"
input_x_btn = "3"
input_l_btn = "4"
input_r_btn = "5"

input_b_btn_label = "A"
input_up_axis_label = "D-Pad Up"
"""

# Pad cujo direcional e HAT em BOTAO — a forma majoritaria (296 de 420).
_HAT_PAD = """
input_driver = "udev"
input_device = "8Bitdo Pro"
input_vendor_id = "11720"
input_product_id = "12289"
input_b_btn = "1"
input_a_btn = "0"
input_y_btn = "4"
input_x_btn = "3"
input_start_btn = "11"
input_select_btn = "10"
input_l_btn = "6"
input_r_btn = "7"
input_up_btn = "h0up"
input_down_btn = "h0down"
input_left_btn = "h0left"
input_right_btn = "h0right"
"""

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


def _valores(resolution) -> dict[str, str]:
    return {binding.key: binding.value for binding in resolution.resolved}


def _motivos(resolution) -> dict[str, str]:
    return {binding.action: binding.reason for binding in resolution.unresolved}


class TestReadingTheIndexInsteadOfInventingIt:
    def test_every_index_comes_from_the_device_file(self) -> None:
        """Nenhum valor gravado pode faltar no arquivo do dispositivo.

        Esta e a assercao central da G45: um indice que nao esteja no arquivo do
        pad e um indice inventado, e um autoconfig inventado e plausivel e
        errado — o usuario aperta pular e volta ao menu.
        """
        device = parse_autoconfig(_STEAM_CONTROLLER)
        resolution = resolve(_PERFIL_PADRAO, device)

        assert resolution.state == "resolved"
        declarados = set(device.entries.values())
        assert all(binding.value in declarados for binding in resolution.resolved)

    def test_the_face_buttons_take_the_index_the_vendor_declared(self) -> None:
        device = parse_autoconfig(_STEAM_CONTROLLER)
        valores = _valores(resolve(_PERFIL_PADRAO, device))

        assert valores["input_b_btn"] == "0"
        assert valores["input_a_btn"] == "1"
        assert valores["input_y_btn"] == "2"
        assert valores["input_x_btn"] == "3"

    def test_a_remap_copies_the_index_of_the_position_the_profile_points_to(self) -> None:
        """Remapear e o caso que prova que o indice e LIDO, nao derivado da acao.

        Mega Drive manda `game.primary` na posicao OESTE. O valor gravado em
        `input_b_btn` tem de ser o indice do oeste (`2`), nao o do sul (`0`).
        Derivar o indice da acao daria `0` e inverteria o controle inteiro.
        """
        device = parse_autoconfig(_STEAM_CONTROLLER)
        perfil = [
            {"action": "game.primary", "input": "button.west"},
            {"action": "game.secondary", "input": "button.south"},
        ]
        valores = _valores(resolve(perfil, device))

        assert valores["input_b_btn"] == "2"
        assert valores["input_a_btn"] == "0"


class TestTheSuffixBelongsToTheDeviceNotToTheAction:
    def test_a_hat_pad_is_written_as_btn_not_axis(self) -> None:
        """296 dos 420 autoconfigs reais declaram o direcional como BOTAO.

        A traducao sem dispositivo chuta `_axis` para direcional. Se esse chute
        sobrevivesse ate a gravacao, a maioria dos pads receberia um arquivo que
        o RetroArch aceita e IGNORA — falha silenciosa.
        """
        valores = _valores(resolve(_PERFIL_PADRAO, parse_autoconfig(_HAT_PAD)))

        assert valores["input_up_btn"] == "h0up"
        assert "input_up_axis" not in valores

    def test_an_axis_pad_is_written_as_axis(self) -> None:
        valores = _valores(resolve(_PERFIL_PADRAO, parse_autoconfig(_STEAM_CONTROLLER)))

        assert valores["input_up_axis"] == "-1"
        assert "input_up_btn" not in valores

    def test_the_sign_of_a_zero_axis_survives(self) -> None:
        """`-0` e `+0` sao entradas OPOSTAS; tratar o valor como int perde o sinal."""
        valores = _valores(resolve(_PERFIL_PADRAO, parse_autoconfig(_STEAM_CONTROLLER)))

        assert valores["input_left_axis"] == "-0"
        assert valores["input_right_axis"] == "+0"


class TestWhatTheDeviceCannotAnswer:
    def test_an_input_the_device_does_not_declare_stays_unresolved(self) -> None:
        sem_ombros = parse_autoconfig(
            _STEAM_CONTROLLER.replace('input_l_btn = "4"', "").replace('input_r_btn = "5"', "")
        )
        resolution = resolve(_PERFIL_PADRAO, sem_ombros)

        assert resolution.state == "partial"
        assert _motivos(resolution) == {
            "game.shoulder-left": "dispositivo-nao-declara",
            "game.shoulder-right": "dispositivo-nao-declara",
        }

    def test_nul_is_declared_absence_not_a_value(self) -> None:
        """44 arquivos reais gravam `nul`. Copiar isso geraria binding invalido."""
        device = parse_autoconfig(
            _STEAM_CONTROLLER.replace('input_l_btn = "4"', 'input_l_btn = "nul"')
        )
        resolution = resolve(_PERFIL_PADRAO, device)

        assert _motivos(resolution)["game.shoulder-left"] == "dispositivo-declara-sem-atribuicao"
        assert "input_l_btn" not in _valores(resolution)

    def test_an_empty_value_is_absence_too(self) -> None:
        device = parse_autoconfig(
            _STEAM_CONTROLLER.replace('input_l_btn = "4"', 'input_l_btn = ""')
        )

        assert (
            _motivos(resolve(_PERFIL_PADRAO, device))["game.shoulder-left"]
            == "dispositivo-declara-sem-atribuicao"
        )

    def test_a_label_leaked_into_a_value_is_refused(self) -> None:
        """Dois arquivos empacotados gravam `"ZR Button"` no lugar do indice."""
        device = parse_autoconfig(
            _STEAM_CONTROLLER.replace('input_r_btn = "5"', 'input_r_btn = "ZR Button"')
        )

        assert (
            _motivos(resolve(_PERFIL_PADRAO, device))["game.shoulder-right"]
            == "valor-do-dispositivo-ilegivel"
        )

    def test_btn_and_axis_for_the_same_input_is_ambiguity_not_a_choice(self) -> None:
        """12 arquivos reais declaram os dois. Escolher um seria adivinhar."""
        device = parse_autoconfig(_HAT_PAD + '\ninput_up_axis = "-7"\n')
        resolution = resolve(_PERFIL_PADRAO, device)

        assert _motivos(resolution)["game.up"] == "dispositivo-declara-btn-e-axis"
        assert not any(binding.key.startswith("input_up_") for binding in resolution.resolved)

    def test_a_device_that_declares_nothing_resolves_nothing(self) -> None:
        resolution = resolve(_PERFIL_PADRAO, Autoconfig(entries={}))

        assert resolution.state == "unresolved"
        assert resolution.resolved == ()
        assert resolution.writable is False


class TestRotationReachesTheDeviceLookup:
    def test_a_rotated_directional_reads_the_index_of_the_rotated_position(self) -> None:
        """`portrait-left` chega ja rotacionado (PR #77). O indice tem de seguir.

        Com a tela girada, `game.up` passa a apontar para `hat.right`; o valor
        gravado precisa ser o indice do DIREITO (`+0`), nao o do cima (`-1`).
        """
        girado = [
            {"action": "game.up", "input": "hat.right"},
            {"action": "game.right", "input": "hat.down"},
        ]
        valores = _valores(resolve(girado, parse_autoconfig(_STEAM_CONTROLLER)))

        assert valores["input_up_axis"] == "+0"
        assert valores["input_right_axis"] == "+1"


class TestActionsWithoutEquivalent:
    def test_an_analog_action_is_reported_not_silently_dropped(self) -> None:
        perfil = [*_PERFIL_PADRAO, {"action": "game.axis-x", "input": "axis.left-x"}]
        resolution = resolve(perfil, parse_autoconfig(_STEAM_CONTROLLER))

        assert resolution.without_equivalent == ("game.axis-x",)
        assert "game.axis-x" not in _motivos(resolution)

    def test_a_duplicated_action_is_refused(self) -> None:
        with pytest.raises(SteamZeroError, match="duplicada"):
            resolve(
                [*_PERFIL_PADRAO, {"action": "game.primary", "input": "button.east"}],
                parse_autoconfig(_STEAM_CONTROLLER),
            )

    def test_a_malformed_binding_is_refused(self) -> None:
        with pytest.raises(SteamZeroError, match="sem ação ou entrada"):
            resolve([{"action": "game.primary"}], parse_autoconfig(_STEAM_CONTROLLER))


class TestIdentityMatching:
    def test_vendor_and_product_win_over_the_name(self) -> None:
        """Vendor+product e o que o proprio RetroArch grava, em DECIMAL."""
        device = parse_autoconfig(_STEAM_CONTROLLER)
        identidade = DeviceIdentity(
            name="nome totalmente diferente", vendor_id=10462, product_id=1142
        )

        assert identidade.matches(device) is True

    def test_a_different_product_does_not_match(self) -> None:
        device = parse_autoconfig(_STEAM_CONTROLLER)
        deck = DeviceIdentity(name="Steam Controller", vendor_id=10462, product_id=4613)

        assert deck.matches(device) is False

    def test_the_name_is_the_fallback_when_ids_are_absent(self) -> None:
        device = parse_autoconfig('input_device = "8Bitdo Pro"\n')

        assert DeviceIdentity(name="8Bitdo Pro").matches(device) is True
        assert DeviceIdentity(name="Outro Pad").matches(device) is False


class TestParsing:
    def test_quotes_spacing_and_comments_are_tolerated(self) -> None:
        parsed = parse_autoconfig('# comentario\ninput_b_btn   =  "3"\ninput_a_btn = 4\n')

        assert parsed.entries["input_b_btn"] == "3"
        assert parsed.entries["input_a_btn"] == "4"

    def test_an_unknown_line_does_not_break_the_read(self) -> None:
        """Arquivo e de terceiro: campo novo do RetroArch nao pode travar (AGENTS.md §8)."""
        parsed = parse_autoconfig('linha solta sem igual\ninput_b_btn = "0"\n')

        assert parsed.entries["input_b_btn"] == "0"

    def test_the_marker_is_only_recognised_on_its_own_line(self) -> None:
        assert is_managed(f'{MANAGED_MARKER}\ninput_b_btn = "0"\n') is True
        assert is_managed('input_device = "SteamZero-Managed: true"\n') is False
        assert parse_autoconfig(_STEAM_CONTROLLER).managed is False


class TestRendering:
    def test_the_generated_file_carries_the_ownership_marker(self) -> None:
        resolution = resolve(_PERFIL_PADRAO, parse_autoconfig(_STEAM_CONTROLLER))
        texto = render_managed(
            resolution,
            identity=DeviceIdentity("Steam Controller", 10462, 1142),
            source=parse_autoconfig(_STEAM_CONTROLLER),
            profile_id="standard-gamepad",
            profile_revision=1,
            orientation="landscape",
        )

        assert texto.splitlines()[0] == MANAGED_MARKER
        assert is_managed(texto) is True

    def test_rendering_is_deterministic(self) -> None:
        """Sem determinismo, toda verificacao regravaria o arquivo."""
        resolution = resolve(_PERFIL_PADRAO, parse_autoconfig(_STEAM_CONTROLLER))
        argumentos = {
            "identity": DeviceIdentity("Steam Controller", 10462, 1142),
            "source": parse_autoconfig(_STEAM_CONTROLLER),
            "profile_id": "standard-gamepad",
            "profile_revision": 1,
            "orientation": "landscape",
        }

        assert render_managed(resolution, **argumentos) == render_managed(resolution, **argumentos)

    def test_the_generated_file_reparses_into_the_same_bindings(self) -> None:
        device = parse_autoconfig(_STEAM_CONTROLLER)
        resolution = resolve(_PERFIL_PADRAO, device)
        texto = render_managed(
            resolution,
            identity=DeviceIdentity("Steam Controller", 10462, 1142),
            source=device,
            profile_id="standard-gamepad",
            profile_revision=1,
            orientation="landscape",
        )
        relido = parse_autoconfig(texto)

        assert {b.key: b.value for b in resolution.resolved}.items() <= relido.entries.items()
        assert relido.entries["input_device"] == "Steam Controller"
        assert relido.managed is True

    def test_what_did_not_resolve_is_written_as_a_comment_not_omitted(self) -> None:
        device = parse_autoconfig(_STEAM_CONTROLLER.replace('input_l_btn = "4"', ""))
        resolution = resolve(_PERFIL_PADRAO, device)
        texto = render_managed(
            resolution,
            identity=DeviceIdentity("Steam Controller", 10462, 1142),
            source=device,
            profile_id="standard-gamepad",
            profile_revision=1,
            orientation="landscape",
        )

        assert "# game.shoulder-left não resolvido" in texto
        assert "input_l_btn" not in texto

    def test_nothing_is_rendered_when_nothing_resolved(self) -> None:
        """Arquivo vazio de bindings seria pior que arquivo ausente."""
        resolution = resolve(_PERFIL_PADRAO, Autoconfig(entries={}))

        with pytest.raises(SteamZeroError, match="nenhum binding resolvido"):
            render_managed(
                resolution,
                identity=DeviceIdentity("Pad", 1, 2),
                source=Autoconfig(entries={}),
                profile_id="standard-gamepad",
                profile_revision=1,
                orientation="landscape",
            )


class TestSteamZeroBundledAutoconfig:
    """ADR-0027: o autoconfig-base que o SteamZero empacota para o Steam Deck.

    O RetroArch 1.22.2 nao traz perfil para `10462/4613` — medido no host e
    confirmado pelo proprio emulador com `[Autoconf] Steam Deck (10462/4613)
    nao configurado.`. Sem base, a traducao parava em `awaiting-device`.
    """

    def _deck(self) -> Autoconfig:
        from steamzero.adapters.input_devices import steamzero_autoconfig_directory
        from steamzero.domain.retroarch_autoconfig import parse_autoconfig

        directory = steamzero_autoconfig_directory()
        assert directory is not None, "o diretorio empacotado tem de viajar no wheel"
        return parse_autoconfig((directory / "steam-deck.cfg").read_text())

    def test_the_bundled_profile_declares_the_deck_ids(self) -> None:
        parsed = self._deck()
        assert parsed.vendor_id == 10462
        assert parsed.product_id == 4613

    def test_the_deck_identity_matches_the_bundled_profile(self) -> None:
        parsed = self._deck()
        identity = DeviceIdentity(name="Steam Deck", vendor_id=10462, product_id=4613)
        assert identity.matches(parsed)

    def test_the_bundled_profile_is_not_managed(self) -> None:
        """Dado de origem, nao artefato gerenciado.

        `AutoconfigCatalog.match` descarta o que e `managed` — e o descarte
        existe para nao casar com o proprio arquivo ja gravado no host. Um
        marcador aqui tornaria a base invisivel para o catalogo.
        """
        assert not self._deck().managed

    def test_the_indices_are_the_ones_measured_on_the_device(self) -> None:
        """Medidos por JSIOCGBTNMAP e pela varredura do bitmap de teclas.

        As duas fontes devolveram listas identicas de 24 codigos; `BTN_SOUTH`
        cai no indice 3 porque `0x121`, `0x122` e `0x126` ocupam 0-2 neste pad.
        Copiar do `Steam_Controller.cfg`, onde `BTN_SOUTH` e 0, mapearia os
        botoes errados.
        """
        bindings = self._deck().entries
        assert bindings["input_b_btn"] == "3"
        assert bindings["input_a_btn"] == "4"
        assert bindings["input_x_btn"] == "5"
        assert bindings["input_y_btn"] == "6"
        assert bindings["input_up_btn"] == "16"
        assert bindings["input_down_btn"] == "17"
        assert bindings["input_left_btn"] == "18"
        assert bindings["input_right_btn"] == "19"

    def test_our_directory_comes_after_the_retroarch_catalog(self) -> None:
        """Nunca sobrepor perfil de terceiro em silencio.

        Se os dois descreverem o mesmo pad de formas diferentes, o catalogo
        devolve `ambiguous-autoconfig` e nada e gravado — mas a ordem deixa
        explicito que o nosso e complemento, nao precedencia.
        """
        from steamzero.adapters.input_devices import (
            bundled_autoconfig_directories,
            steamzero_autoconfig_directory,
        )

        directories = bundled_autoconfig_directories()
        own = steamzero_autoconfig_directory()
        assert own is not None
        assert directories[-1] == own
