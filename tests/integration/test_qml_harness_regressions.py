# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Regressões do harness visual — cada uma custou uma investigação.

Todo teste aqui documenta um erro que foi COMETIDO, não um risco imaginado. A
maioria tinha o mesmo formato: uma verificação que se lia como rigorosa e não
verificava nada. Elas passavam, e por isso eram piores que a ausência de teste.

Se algum destes for removido "porque é óbvio", o defeito volta em silêncio.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from steamzero.domain.resolved_node import ASSET_HANDLE
from steamzero.domain.text_node_builder import FontProvider

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from qml_capture_runner import (  # noqa: E402
    HARNESS,
    PLUGIN_FAILURE_MARKERS,
    CanonicalEnvironment,
    compare_with_golden,
    parse_messages,
)

HARNESS_SOURCE = HARNESS.read_text(encoding="utf-8")
RUNNER_SOURCE = (ROOT / "tools" / "qml_capture_runner.py").read_text(encoding="utf-8")


class TestSynchronousXhrIsNeverReintroduced:
    """XHR síncrono em `file://` TRAVA o runtime do QML.

    A primeira versão do harness lia a configuração assim e pendurava até o
    timeout, sem mensagem nenhuma. A configuração entra pelo argv desde então, o
    que de quebra mantém o cenário sem qualquer leitura de disco.
    """

    def test_the_harness_does_not_use_xmlhttprequest(self) -> None:
        assert "XMLHttpRequest" not in HARNESS_SOURCE, (
            "XHR síncrono em file:// trava o runtime; a configuração vem pelo argv"
        )

    def test_the_configuration_arrives_through_argv(self) -> None:
        assert "--config-json" in HARNESS_SOURCE
        assert "--config-json" in RUNNER_SOURCE


class TestTheCanvasBackgroundIsDrawn:
    """`grabToImage` no `contentItem` NÃO captura a cor da Window.

    A primeira captura saiu com fundo transparente, e o golden teria congelado
    um fundo que não era o configurado — deixando a checagem de "imagem vazia"
    sem referência.
    """

    def test_an_explicit_rectangle_paints_the_background(self) -> None:
        assert "Rectangle" in HARNESS_SOURCE
        assert "anchors.fill: parent" in HARNESS_SOURCE

    def test_the_captured_image_has_the_configured_background(self, tmp_path: Path) -> None:
        from PIL import Image

        from qml_capture_fixtures import FIXTURES_BY_NAME
        from qml_capture_runner import capture

        fixture = FIXTURES_BY_NAME["text-baseline"]
        result = capture(
            fixture.model().to_dict(),
            output=tmp_path,
            canvas=(200, 80),
            background="#101418",
        )
        with Image.open(result.image) as picture:
            corner = picture.convert("RGBA").getpixel((2, 2))
        assert corner == (16, 20, 24, 255), (
            f"canto em {corner}; transparente significaria que o fundo não foi desenhado"
        )


class TestBoundingBoxComesFromTheMask:
    """`getbbox()` do Pillow moderno usa `alpha_only=True`.

    O alfa da diferença é zero em toda parte quando as duas imagens são opacas,
    então a caixa vinha `None` mesmo com centenas de pixels alterados — e o
    relatório dizia "mudou" sem dizer onde.
    """

    def test_a_change_between_opaque_images_reports_its_region(self, tmp_path: Path) -> None:
        from PIL import Image

        left = Image.new("RGBA", (40, 40), (0, 0, 0, 255))
        right = left.copy()
        for x in range(10, 20):
            for y in range(5, 15):
                right.putpixel((x, y), (255, 255, 255, 255))
        first = tmp_path / "a.png"
        second = tmp_path / "b.png"
        left.save(first)
        right.save(second)

        metrics = compare_with_golden(second, first, tmp_path / "out")
        assert metrics.changed_pixel_count == 100
        assert metrics.bounding_box_of_changes == (10, 5, 20, 15), (
            "a caixa precisa vir da máscara; a diferença tem alfa zero"
        )


class TestPlatformFailureMessagesAreTheRealOnes:
    """As mensagens que escrevi de memória não existiam.

    A checagem procurava "Failed to create platform", que o Qt nunca emite, e o
    erro de ambiente saía como falha genérica de captura — mandando quem
    investiga procurar defeito no componente.
    """

    def test_the_runner_matches_the_message_qt_actually_emits(self) -> None:
        """Verifica o DADO, não o texto do arquivo.

        A primeira versão deste teste procurava a string no fonte inteiro e
        reprovava por causa de um comentário — a mesma fragilidade de substring
        que ele existe para impedir.
        """
        assert "Could not find the Qt platform plugin" in PLUGIN_FAILURE_MARKERS

    def test_qt_still_emits_that_message(self) -> None:
        """Se o Qt mudar o texto, a checagem vira código morto de novo."""
        env = CanonicalEnvironment(platform="plataforma-inexistente").to_env()
        completed = subprocess.run(
            [str(_runtime()), str(HARNESS)],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert "Could not find the Qt platform plugin" in completed.stderr


def _runtime() -> Path:
    from qml_capture_runner import find_runtime

    return find_runtime()


class TestInheritedQtEnvironmentCannotSilenceWarnings:
    """Este host tem `QT_LOGGING_RULES=*=false`, que silencia todo log do Qt.

    Um harness que herdasse o ambiente verificaria a ausência de warnings numa
    sessão onde warning nenhum consegue ser emitido — verde perfeito, zero
    verificação.
    """

    def test_the_hostile_rule_is_overridden(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("QT_LOGGING_RULES", "*=false")
        assert CanonicalEnvironment().to_env()["QT_LOGGING_RULES"] == ""

    def test_the_message_pattern_is_fixed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Sem `%{type}` tudo sai como "qml: " e a classificação é impossível."""
        monkeypatch.setenv("QT_MESSAGE_PATTERN", "%{message}")
        assert CanonicalEnvironment().to_env()["QT_MESSAGE_PATTERN"] == "%{type}|%{message}"

    def test_warnings_are_actually_collected_under_the_canonical_environment(self) -> None:
        messages = parse_messages("warning|qrc:/x.qml:3: Unable to assign QString to double")
        assert messages[0].level == "warning"
        assert messages[0].forbidden


class TestFontFamilyDoesNotProveTheFontLoaded:
    """`font.family` ECOA o valor atribuído, exista a fonte ou não.

    Medido: uma família inexistente e uma real produziram o mesmo `font.family`
    E o mesmo `contentWidth`, porque as duas renderizaram com o fallback. A
    checagem parecia rigorosa e não verificava nada; o teste que a exercitava
    passava vazio.
    """

    def test_the_harness_checks_the_available_families(self) -> None:
        assert "Qt.fontFamilies()" in HARNESS_SOURCE, (
            "a lista do que o Qt tem é a única prova de que a fonte carregou"
        )

    def test_the_harness_does_not_compare_font_family_to_the_request(self) -> None:
        assert "subject.font.family !== requested" not in HARNESS_SOURCE


class TestAssetHandleGrammarSurvivesRealFontNames:
    """`asset://font/{família}` quebrava com qualquer nome de duas palavras.

    Passava na validação com "Gilroy" e explodia com "Liberation Sans", porque
    a gramática não aceita espaço. Só apareceu quando uma fixture usou uma fonte
    de verdade — antes disso, todo teste usava um nome de uma palavra.
    """

    @pytest.mark.parametrize(
        "family",
        [
            "Liberation Sans",
            "Noto Sans CJK JP",
            "Source Han Sans SC",
            "ゴシック",
            "Font/With/Slashes",
            "Font..With..Dots",
            "a" * 300,
            "  espaços  ",
        ],
    )
    def test_any_family_name_produces_a_valid_handle(self, family: str) -> None:
        handle = FontProvider({family: family}).resolve(family)
        assert handle is not None
        assert handle.handle is not None
        assert ASSET_HANDLE.match(handle.handle), handle.handle

    def test_the_readable_name_is_not_lost(self) -> None:
        """O handle é opaco, então o nome legível precisa sobreviver ao lado."""
        handle = FontProvider({"Liberation Sans": "Liberation Sans"}).resolve("Liberation Sans")
        assert handle is not None
        assert handle.resolved_family == "Liberation Sans"

    def test_two_families_never_share_a_handle(self) -> None:
        """O slug sozinho colide: "A B" e "A/B" viram o mesmo texto."""
        first = FontProvider({"A B": "A B"}).resolve("A B")
        second = FontProvider({"A/B": "A/B"}).resolve("A/B")
        assert first is not None
        assert second is not None
        assert first.handle != second.handle


class TestPendingValuesCannotReachTheScene:
    """O QML aceita objeto onde espera string e renderiza "[object Object]".

    Sem barreira no harness, um dicionário montado à mão atravessava sem erro
    nenhum — a validação existia só no adapter.
    """

    def test_the_runner_refuses_a_pending_payload(self, tmp_path: Path) -> None:
        from qml_capture_runner import CaptureError, capture

        with pytest.raises(CaptureError, match="não resolvido"):
            capture(
                {"id": "x", "text": {"token": "color.accent"}},
                output=tmp_path,
                canvas=(100, 100),
                background="#000000",
            )
