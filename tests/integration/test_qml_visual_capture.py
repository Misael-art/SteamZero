# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""VS-03 — gates visuais do harness próprio.

Nenhum teste aqui usa `skip`. Ambiente ausente reprova com o código do
diagnóstico, porque um `skip` produz suíte verde num host onde nada visual foi
verificado — foi assim que a regressão de ícones da a37 atravessou os gates.

Os gates geométricos não dependem de comparação de imagem: largura errada é um
número errado, e um número errado precisa reprovar sem ninguém olhar duas
imagens lado a lado.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from steamzero.domain.qml_render_model import QmlTextRenderModel, to_render_model
from steamzero.domain.resolved_node import (
    FontAssetHandle,
    FontOrigin,
    FontStyle,
    FontWeight,
    ResolvedGeometry,
    ResolvedTextNode,
    TextAlignment,
    TextVerticalAlignment,
)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from qml_capture_fixtures import FIXTURES, Fixture  # noqa: E402
from qml_capture_runner import (  # noqa: E402
    DIAG_EMPTY_IMAGE,
    DIAG_ENVIRONMENT,
    DIAG_FONT,
    DIAG_GOLDEN_MISSING,
    DIAG_PLUGIN,
    DIAG_QT_VERSION,
    Backend,
    CanonicalEnvironment,
    CaptureError,
    CaptureResult,
    assert_not_empty,
    capture,
    check_runtime_version,
    compare_with_golden,
    find_runtime,
    parse_messages,
    write_artifacts,
)

#: Fonte do sistema, presente em qualquer runner Linux com fontconfig. O
#: empacotamento de uma fonte própria do projeto é do VS-07, junto dos goldens:
#: fixar a família aqui já garante que a substituição silenciosa reprove.
TEST_FONT = "Liberation Sans"

GOLDEN_DIR = ROOT / "tests" / "qml" / "golden"

CANVAS = (800, 240)
BACKGROUND = "#101418"


def _node(**overrides: Any) -> ResolvedTextNode:
    from dataclasses import replace

    base = ResolvedTextNode(
        id="gameTitle",
        text="Chrono Trigger",
        geometry=ResolvedGeometry(x=40.0, y=60.0, width=700.0, height=70.0),
        color="#F2F6FB",
        font_family=TEST_FONT,
        font_size=48.0,
        font_asset=FontAssetHandle(
            key=TEST_FONT,
            handle="asset://font/LiberationSans",
            origin=FontOrigin.PACKAGED,
            requested_family=TEST_FONT,
            resolved_family=TEST_FONT,
        ),
    )
    return replace(base, **overrides)


def _model(**overrides: Any) -> QmlTextRenderModel:
    return to_render_model(_node(**overrides)).require_model()


@pytest.fixture(scope="module")
def rendered(tmp_path_factory: pytest.TempPathFactory) -> CaptureResult:
    """Uma captura por módulo. Renderizar é caro; julgar não é."""
    output = tmp_path_factory.mktemp("capture")
    result = capture(_model().to_dict(), output=output, canvas=CANVAS, background=BACKGROUND)
    write_artifacts(result, output, resolved_node=_node().to_dict())
    return result


class TestEnvironmentFailsLoudly:
    """Ambiente ausente reprova. Nunca vira `skip`."""

    def test_the_runtime_is_required(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("shutil.which", lambda _name: None)
        with pytest.raises(CaptureError) as raised:
            find_runtime()
        assert raised.value.code == DIAG_ENVIRONMENT

    def test_the_canonical_environment_is_built_from_scratch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Este host tem `QT_LOGGING_RULES=*=false`, que silencia todo log do Qt.

        Herdar isso faria a coleta de warnings verificar o silêncio de um Qt
        amordaçado, e a suíte passaria sem nunca ver um warning.
        """
        monkeypatch.setenv("QT_LOGGING_RULES", "*=false")
        monkeypatch.setenv("QT_MESSAGE_PATTERN", "%{message}")
        monkeypatch.setenv("QT_QUICK_BACKEND", "hostile")
        env = CanonicalEnvironment().to_env()
        assert env["QT_LOGGING_RULES"] == ""
        assert env["QT_MESSAGE_PATTERN"] == "%{type}|%{message}"
        assert env["QT_QUICK_BACKEND"] == "software"

    def test_no_inherited_qt_variable_survives(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("QT_SOMETHING_UNEXPECTED", "1")
        monkeypatch.setenv("QML_IMPORT_PATH", "hostile-import-path")
        monkeypatch.setenv("QSG_RENDER_LOOP", "threaded")
        env = CanonicalEnvironment().to_env()
        assert "QT_SOMETHING_UNEXPECTED" not in env
        assert "QML_IMPORT_PATH" not in env
        assert "QSG_RENDER_LOOP" not in env

    def test_the_locale_is_fixed(self) -> None:
        """Locale do host mudaria a quebra de linha e a forma dos numerais."""
        env = CanonicalEnvironment().to_env()
        assert env["LC_ALL"] == "C.UTF-8"
        assert env["LANG"] == "C.UTF-8"


class TestMessageCollection:
    def test_levels_are_separated(self) -> None:
        messages = parse_messages("info|carregado\nwarning|algo\ncritical|pior")
        assert [item.level for item in messages] == ["info", "warning", "critical"]

    def test_an_unrecognised_line_is_not_discarded(self) -> None:
        """Perder informação num coletor de warnings anula o coletor."""
        messages = parse_messages("linha sem padrão nenhum")
        assert len(messages) == 1
        assert messages[0].level == "warning"

    def test_forbidden_markers_are_detected(self) -> None:
        messages = parse_messages("warning|qrc:/x.qml:3: Unable to assign QString to double")
        assert messages[0].forbidden


class TestCaptureProducesArtifacts:
    def test_the_image_exists_and_is_not_uniform(self, rendered: CaptureResult) -> None:
        """Uma tela inteira na cor de fundo tem o tamanho certo e não vale nada.

        É o que sai quando o componente não carregou, quando o texto ficou fora
        do canvas, ou quando a cor foi resolvida igual ao fundo.
        """
        assert rendered.image.exists()
        assert assert_not_empty(rendered.image, background=BACKGROUND) > 1

    def test_the_canvas_has_the_configured_size(self, rendered: CaptureResult) -> None:
        from PIL import Image

        with Image.open(rendered.image) as picture:
            assert picture.size == CANVAS

    def test_no_forbidden_warning_was_emitted(self, rendered: CaptureResult) -> None:
        assert not rendered.forbidden_messages, [item.text for item in rendered.forbidden_messages]

    def test_every_artifact_is_published(self, rendered: CaptureResult) -> None:
        """Em falha estes arquivos são a única pista numa máquina que não é a sua."""
        for name in (
            "actual.png",
            "resolved-node.json",
            "qml-render-model.json",
            "qml-warnings.txt",
            "environment.json",
        ):
            assert name in rendered.artifacts, name
            assert rendered.artifacts[name].exists()

    def test_the_environment_record_identifies_the_run(self, rendered: CaptureResult) -> None:
        record = rendered.environment
        assert record["platform"] == "offscreen"
        assert record["backend"] == "software"
        assert record["qtVersion"].startswith("6.")
        assert record["fontFamilyRequested"] == TEST_FONT
        assert record["fontFamilyResolved"] == TEST_FONT
        for key in ("devicePixelRatio", "fontDpi", "locale", "scaleFactor"):
            assert key in record


class TestGeometryGates:
    """Layout se valida por número, não por comparação visual subjetiva."""

    def test_position_and_size_survive_to_the_scene(self, rendered: CaptureResult) -> None:
        geometry = rendered.geometry
        assert geometry["x"] == 40
        assert geometry["y"] == 60
        assert geometry["width"] == 700
        assert geometry["height"] == 70

    def test_the_content_fits_inside_the_declared_box(self, rendered: CaptureResult) -> None:
        geometry = rendered.geometry
        assert 0 < geometry["contentWidth"] <= geometry["width"]
        assert 0 < geometry["contentHeight"] <= geometry["height"]

    def test_the_bounding_rect_matches_the_model(self, rendered: CaptureResult) -> None:
        assert rendered.geometry["boundingRect"] == {
            "x": 40,
            "y": 60,
            "width": 700,
            "height": 70,
        }

    def test_font_and_colour_arrive_intact(self, rendered: CaptureResult) -> None:
        geometry = rendered.geometry
        assert geometry["fontFamilyResolved"] == TEST_FONT
        assert geometry["fontPixelSize"] == 48
        assert geometry["fontWeight"] == 400
        assert geometry["fontItalic"] is False
        assert geometry["opacity"] == 1
        assert "f2f6fb" in geometry["color"].lower()

    @pytest.mark.parametrize(
        ("alignment", "expected"),
        [
            (TextAlignment.START, 1),
            (TextAlignment.CENTER, 4),
            (TextAlignment.END, 2),
        ],
    )
    def test_horizontal_alignment_reaches_qt(
        self, tmp_path: Path, alignment: TextAlignment, expected: int
    ) -> None:
        """Prova que o nome emitido pelo adapter resolve no enum do Qt.

        `Text["AlignHCenter"]` devolvendo `undefined` faria a atribuição falhar
        em silêncio e o alinhamento cair no default sem sintoma.
        """
        result = capture(
            _model(horizontal_alignment=alignment).to_dict(),
            output=tmp_path,
            canvas=CANVAS,
            background=BACKGROUND,
        )
        assert result.geometry["horizontalAlignment"] == expected

    @pytest.mark.parametrize(
        ("alignment", "expected"),
        [
            (TextVerticalAlignment.TOP, 32),
            (TextVerticalAlignment.MIDDLE, 128),
            (TextVerticalAlignment.BOTTOM, 64),
        ],
    )
    def test_vertical_alignment_reaches_qt(
        self, tmp_path: Path, alignment: TextVerticalAlignment, expected: int
    ) -> None:
        result = capture(
            _model(vertical_alignment=alignment).to_dict(),
            output=tmp_path,
            canvas=CANVAS,
            background=BACKGROUND,
        )
        assert result.geometry["verticalAlignment"] == expected

    def test_weight_and_italic_reach_qt(self, tmp_path: Path) -> None:
        result = capture(
            _model(font_weight=FontWeight.BOLD, font_style=FontStyle.ITALIC).to_dict(),
            output=tmp_path,
            canvas=CANVAS,
            background=BACKGROUND,
        )
        assert result.geometry["fontWeight"] == 700
        assert result.geometry["fontItalic"] is True

    def test_automatic_width_comes_from_the_content(self, tmp_path: Path) -> None:
        """`width` ausente significa dimensão implícita, não zero.

        Zero produziria um elemento sem tamanho, que é outra coisa.
        """
        result = capture(
            _model(geometry=ResolvedGeometry(x=40.0, y=60.0)).to_dict(),
            output=tmp_path,
            canvas=CANVAS,
            background=BACKGROUND,
        )
        assert result.geometry["width"] == result.geometry["implicitWidth"]
        assert result.geometry["width"] > 0


class TestGoldenPolicy:
    def test_a_missing_baseline_fails_instead_of_being_created(
        self, rendered: CaptureResult, tmp_path: Path
    ) -> None:
        """Baseline criada sozinha nunca é revisada.

        O primeiro resultado — certo ou errado — viraria a definição do correto.
        """
        with pytest.raises(CaptureError) as raised:
            compare_with_golden(rendered.image, tmp_path / "ausente.png", tmp_path)
        assert raised.value.code == DIAG_GOLDEN_MISSING
        assert "update-qml-goldens" in raised.value.detail

    def test_an_identical_capture_reports_no_change(
        self, rendered: CaptureResult, tmp_path: Path
    ) -> None:
        import shutil

        golden = tmp_path / "expected.png"
        shutil.copyfile(rendered.image, golden)
        metrics = compare_with_golden(rendered.image, golden, tmp_path)
        assert metrics.changed_pixel_count == 0
        assert metrics.bounding_box_of_changes is None

    def test_a_changed_capture_reports_where_and_how_much(
        self, rendered: CaptureResult, tmp_path: Path
    ) -> None:
        import shutil

        golden = tmp_path / "expected.png"
        shutil.copyfile(rendered.image, golden)
        changed = capture(
            _model(text="Chrono Trigger II").to_dict(),
            output=tmp_path / "run",
            canvas=CANVAS,
            background=BACKGROUND,
        )
        metrics = compare_with_golden(changed.image, golden, tmp_path)
        assert metrics.changed_pixel_count > 0
        assert metrics.maximum_channel_delta > 0
        assert metrics.bounding_box_of_changes is not None, (
            "sem a caixa não dá para saber ONDE mudou"
        )
        for name in ("diff.png", "overlay.png", "expected.png", "metrics.json"):
            assert (tmp_path / name).exists(), name

    def test_a_blank_image_is_refused(self, tmp_path: Path) -> None:
        from PIL import Image

        blank = tmp_path / "blank.png"
        Image.new("RGBA", (100, 100), (16, 20, 24, 255)).save(blank)
        with pytest.raises(CaptureError) as raised:
            assert_not_empty(blank, background=BACKGROUND)
        assert raised.value.code == DIAG_EMPTY_IMAGE


class TestGoldenInfrastructureIsReady:
    """Prova que a comparação FUNCIONA, sem depender de baseline commitada.

    Baseline versionada ainda não é possível, e o motivo é concreto: o texto é
    renderizado com a Liberation Sans do sistema, e Manjaro empacota a 2.1.5
    enquanto o runner do CI traz outra. Arquivos de fonte diferentes produzem
    métricas diferentes, então uma baseline gerada aqui reprovaria lá — por
    diferença de pacote, não por regressão de código. O relatório erraria a
    causa em toda execução.

    Congelar baseline exige fonte EMPACOTADA no repositório, que é decisão de
    redistribuição e licença. Fica para o VS-07, onde as golden images são o
    entregável. O que o VS-03 entrega é a infraestrutura, e é ela que estes
    testes exercitam: determinismo, sensibilidade e artefatos.
    """

    @pytest.mark.parametrize("fixture", FIXTURES, ids=[item.name for item in FIXTURES])
    def test_each_scenario_renders_deterministically(
        self, fixture: Fixture, tmp_path: Path
    ) -> None:
        """Duas capturas idênticas do mesmo cenário.

        Sem isto, uma baseline futura seria comparada contra ruído, e o gate
        reprovaria de forma intermitente sem nenhuma mudança de código.
        """
        first = capture(
            fixture.model().to_dict(),
            output=tmp_path / "first",
            canvas=fixture.canvas,
            background=fixture.background,
        )
        assert_not_empty(first.image, background=fixture.background)
        assert not first.forbidden_messages, [item.text for item in first.forbidden_messages]

        second = capture(
            fixture.model().to_dict(),
            output=tmp_path / "second",
            canvas=fixture.canvas,
            background=fixture.background,
        )
        metrics = compare_with_golden(second.image, first.image, tmp_path / "compare")
        assert metrics.changed_pixel_count == 0, (
            f"{fixture.name} não é determinístico: {metrics.to_dict()}"
        )

    def test_the_comparison_detects_a_real_change(self, tmp_path: Path) -> None:
        """Comparação que nunca acusa diferença aprova qualquer coisa."""
        baseline = capture(
            _model().to_dict(),
            output=tmp_path / "base",
            canvas=CANVAS,
            background=BACKGROUND,
        )
        changed = capture(
            _model(text="Chrono Trigger II").to_dict(),
            output=tmp_path / "changed",
            canvas=CANVAS,
            background=BACKGROUND,
        )
        metrics = compare_with_golden(changed.image, baseline.image, tmp_path)
        assert metrics.changed_pixel_count > 0
        assert metrics.maximum_channel_delta > 0
        assert metrics.bounding_box_of_changes is not None, (
            "sem a caixa não dá para saber ONDE mudou"
        )
        for name in ("diff.png", "overlay.png", "expected.png", "metrics.json"):
            assert (tmp_path / name).exists(), name

    def test_each_scenario_isolates_one_property(self) -> None:
        """Cenário que mistura propriedades não diz o que mudou quando muda."""
        assert len(FIXTURES) >= 8
        assert len({item.name for item in FIXTURES}) == len(FIXTURES)

    def test_the_update_command_never_runs_by_itself(self) -> None:
        """Baseline regravada sozinha deixa de ser baseline.

        O primeiro resultado — certo ou errado — viraria a definição do correto,
        e ninguém revisaria a imagem que passou a definir o aprovado.
        """
        source = (ROOT / "tools" / "update_qml_goldens.py").read_text(encoding="utf-8")
        assert "required=True" in source, "o comando precisa exigir --check ou --write"
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        assert "update_qml_goldens" not in workflow, "o CI nunca regrava baseline"


class TestDeclaredFailureModesActuallyFire:
    """Cada modo de falha exercitado de verdade, não declarado no papel.

    Escrevi a primeira versão destas checagens de memória e três das quatro não
    disparavam: a detecção de plugin procurava uma mensagem que o Qt não emite,
    e a de fonte comparava `font.family` — que ecoa o que foi atribuído,
    exista a fonte ou não.
    """

    def test_a_font_the_qt_does_not_have_is_refused(self, tmp_path: Path) -> None:
        """`font.family` NÃO serve para detectar substituição.

        Verificado: uma família inexistente e uma real produziram o mesmo
        `font.family` E o mesmo `contentWidth`, porque as duas renderizaram com
        o fallback. A checagem parecia rigorosa e não verificava nada. O que
        funciona é `Qt.fontFamilies()`, a lista do que o Qt realmente tem.
        """
        from dataclasses import replace

        model = replace(_model(), font_family="Fonte Que Nao Existe XYZ")
        with pytest.raises(CaptureError) as raised:
            capture(model.to_dict(), output=tmp_path, canvas=CANVAS, background=BACKGROUND)
        assert raised.value.code == DIAG_FONT

    def test_an_unavailable_platform_plugin_is_named(self, tmp_path: Path) -> None:
        with pytest.raises(CaptureError) as raised:
            capture(
                _model().to_dict(),
                output=tmp_path,
                canvas=CANVAS,
                background=BACKGROUND,
                environment=CanonicalEnvironment(platform="plataforma-inexistente"),
            )
        assert raised.value.code == DIAG_PLUGIN

    def test_the_rhi_backend_is_refused_instead_of_hanging(self, tmp_path: Path) -> None:
        """RHI sob offscreen não inicializa e NÃO retorna.

        Verificado: consumia o timeout inteiro e reportava "layout não
        estabilizou", mandando quem investiga para o lugar errado.
        """
        with pytest.raises(CaptureError) as raised:
            capture(
                _model().to_dict(),
                output=tmp_path,
                canvas=CANVAS,
                background=BACKGROUND,
                environment=CanonicalEnvironment(backend=Backend.RHI),
                timeout=20,
            )
        assert raised.value.code == DIAG_PLUGIN
        assert "P0-08" in raised.value.detail

    def test_an_old_qt_is_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Golden gerado noutra versão do Qt não vale nesta."""
        import subprocess

        class _Old:
            stdout = "Qt 6.2.0"
            stderr = ""

        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Old())
        with pytest.raises(CaptureError) as raised:
            check_runtime_version(Path("/usr/bin/qml6"))
        assert raised.value.code == DIAG_QT_VERSION

    def test_the_font_file_hash_is_recorded(self, rendered: CaptureResult) -> None:
        """Duas distribuições empacotam versões diferentes da MESMA família.

        Sem o hash, uma divergência de golden causada por atualização de pacote
        de fonte pareceria regressão de código.
        """
        fingerprint = rendered.environment["fontFile"]
        assert fingerprint["family"] == TEST_FONT
        assert fingerprint.get("sha256"), fingerprint
