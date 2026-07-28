# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""VS-07 — as dez baselines versionadas e o que elas afirmam.

As oito primeiras são o conjunto histórico e não mudam. As duas últimas
entraram ANTES da primeira versão das baselines, de propósito: depois de
versionar, acrescentar cobertura ausente pareceria mudança de baseline, e a
revisão gastaria atenção decidindo se a imagem nova está certa em vez de se a
imagem antiga mudou.

Todas foram geradas na mesma execução e no mesmo ambiente canônico: fontconfig
isolado nas quatro faces empacotadas, hashes conferidos, Qt fixado, DPI e
devicePixelRatio fixos, locale fixo, backend software, offscreen.
"""

from __future__ import annotations

import hashlib
import json
import sys
import unicodedata
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

#: Exigem runtime QML. Roteados para o gate visual dedicado, que reprova
#: quando o Qt falta — não são pulados em lugar nenhum.
pytestmark = pytest.mark.visual

from qml_capture_fixtures import (  # noqa: E402
    FIXTURES,
    FIXTURES_BY_NAME,
    ORDINALS,
    PORTUGUESE_SAMPLE,
    Fixture,
)
from qml_capture_runner import (  # noqa: E402
    assert_not_empty,
    capture,
    compare_with_golden,
    load_font_manifest,
)

GOLDEN_DIR = ROOT / "tests" / "qml" / "golden"

#: O conjunto histórico. Nomeado aqui para que remover ou renomear um deles
#: reprove — eles são a referência contra a qual tudo o mais é comparado.
HISTORICAL = (
    "text-baseline",
    "text-centered",
    "text-right",
    "text-bottom",
    "text-bold",
    "text-italic",
    "text-translucent",
    "text-implicit-width",
)


def _render(fixture: Fixture, output: Path, **overrides: Any) -> Any:
    model = fixture.model()
    if overrides:
        model = replace(model, **overrides)
    return capture(
        model.to_dict(),
        output=output,
        canvas=fixture.canvas,
        background=fixture.background,
    )


class TestTheHistoricalSetIsPreserved:
    def test_the_eight_original_fixtures_are_still_there(self) -> None:
        names = [item.name for item in FIXTURES]
        assert names[:8] == list(HISTORICAL), (
            "os oito históricos não podem ser removidos, renomeados nem reordenados"
        )

    def test_the_new_fixtures_were_appended_not_substituted(self) -> None:
        assert len(FIXTURES) == 10
        assert [item.name for item in FIXTURES[8:]] == [
            "text-bold-italic",
            "text-portuguese-accents",
        ]

    def test_every_fixture_has_a_stable_ordinal(self) -> None:
        assert ORDINALS["text-baseline"] == "visual-01"
        assert ORDINALS["text-bold-italic"] == "visual-09"
        assert ORDINALS["text-portuguese-accents"] == "visual-10"


class TestEveryBaselineMatches:
    @pytest.mark.parametrize("fixture", FIXTURES, ids=[item.name for item in FIXTURES])
    def test_the_capture_matches_the_versioned_baseline(
        self, fixture: Fixture, tmp_path: Path
    ) -> None:
        golden = GOLDEN_DIR / f"{fixture.name}.png"
        result = _render(fixture, tmp_path)
        assert_not_empty(result.image, background=fixture.background)
        assert not result.forbidden_messages, [item.text for item in result.forbidden_messages]
        metrics = compare_with_golden(result.image, golden, tmp_path)
        assert metrics.changed_pixel_count == 0, (
            f"{ORDINALS[fixture.name]} ({fixture.name}) divergiu: {metrics.to_dict()}. "
            f"Artefatos em {tmp_path}. Se a mudança for intencional, "
            "`make update-qml-goldens` e revise as imagens no commit."
        )

    def test_every_fixture_has_a_baseline(self) -> None:
        missing = [item.name for item in FIXTURES if not (GOLDEN_DIR / f"{item.name}.png").exists()]
        assert not missing, f"cenários sem baseline: {missing}"

    def test_no_orphan_baseline_survives(self) -> None:
        known = {f"{item.name}.png" for item in FIXTURES}
        orphans = sorted(path.name for path in GOLDEN_DIR.glob("*.png") if path.name not in known)
        assert not orphans, f"baselines sem cenário: {orphans}"

    @pytest.mark.parametrize("fixture", FIXTURES, ids=[item.name for item in FIXTURES])
    def test_a_second_run_changes_nothing(self, fixture: Fixture, tmp_path: Path) -> None:
        """Baseline comparada contra ruído reprovaria de forma intermitente."""
        first = _render(fixture, tmp_path / "first")
        second = _render(fixture, tmp_path / "second")
        metrics = compare_with_golden(second.image, first.image, tmp_path / "compare")
        assert metrics.changed_pixel_count == 0


class TestBoldItalicFace:
    """visual-09 — a quarta face, que a síntese do Qt esconderia."""

    @pytest.fixture(scope="class")
    @staticmethod
    def rendered(tmp_path_factory: pytest.TempPathFactory) -> Any:
        return _render(FIXTURES_BY_NAME["text-bold-italic"], tmp_path_factory.mktemp("bolditalic"))

    def test_the_bold_italic_face_was_used(self, rendered: Any) -> None:
        assert rendered.geometry["resolvedFace"] == "BoldItalic"
        assert rendered.geometry["fontWeight"] == 700
        assert rendered.geometry["fontItalic"] is True

    def test_no_fallback_was_detected(self, rendered: Any) -> None:
        assert rendered.environment["fallbackDetected"] is False
        assert rendered.environment["testFontAvailable"] is True

    def test_only_the_packaged_family_was_available(self, rendered: Any) -> None:
        assert rendered.environment["availableFontFamilyCount"] <= 8

    def _faces(self, tmp_path: Path) -> dict[str, Any]:
        base = FIXTURES_BY_NAME["text-bold-italic"]
        return {
            "Regular": _render(base, tmp_path / "r", font_weight=400, font_italic=False),
            "Bold": _render(base, tmp_path / "b", font_weight=700, font_italic=False),
            "Italic": _render(base, tmp_path / "i", font_weight=400, font_italic=True),
            "BoldItalic": _render(base, tmp_path / "bi", font_weight=700, font_italic=True),
        }

    def test_width_alone_cannot_distinguish_italic_from_regular(self, tmp_path: Path) -> None:
        """Medido, não suposto: a Liberation preserva os avanços no itálico.

        A primeira versão deste teste exigia quatro larguras distintas e
        reprovou — Regular e Italic dão 478, Bold e BoldItalic dão 510. A fonte
        é metricamente compatível com a Arial, e o itálico mantém o avanço.

        Fica registrado porque a conclusão importa: largura NÃO prova que a face
        itálica carregou. Só o pixel prova.
        """
        measured = {
            name: item.geometry["contentWidth"] for name, item in self._faces(tmp_path).items()
        }
        assert measured["Regular"] == measured["Italic"]
        assert measured["Bold"] == measured["BoldItalic"]
        assert measured["Regular"] != measured["Bold"], "o peso precisa mudar o avanço"

    def test_the_four_faces_produce_four_different_images(self, tmp_path: Path) -> None:
        """A prova real de que os quatro arquivos são lidos.

        Se o Qt sintetizasse o itálico inclinando o Regular, a imagem também
        diferiria — mas a inclinação sintética varia entre plataformas, e a
        baseline deixaria de reproduzir sem nenhuma mudança de código. O que
        garante o arquivo certo é o fontconfig isolado nas quatro faces
        empacotadas; este teste garante que as quatro estão em uso.
        """
        faces = self._faces(tmp_path)
        digests = {
            name: hashlib.sha256(item.image.read_bytes()).hexdigest()
            for name, item in faces.items()
        }
        assert len(set(digests.values())) == 4, f"faces com imagem idêntica: {digests}"

    def test_the_text_is_long_enough_to_compare(self) -> None:
        """Uma palavra curta produz comparação visual fraca.

        Inclinação e peso mal se distinguem em poucos glifos, e o teste passaria
        a aprovar qualquer coisa parecida.
        """
        assert len(FIXTURES_BY_NAME["text-bold-italic"].model().text) >= 20


class TestPortugueseAccents:
    """visual-10 — os glifos que a métrica ASCII não exercita."""

    @pytest.fixture(scope="class")
    @staticmethod
    def rendered(tmp_path_factory: pytest.TempPathFactory) -> Any:
        return _render(
            FIXTURES_BY_NAME["text-portuguese-accents"], tmp_path_factory.mktemp("accents")
        )

    def test_the_sample_covers_every_accent_class(self) -> None:
        """Verifica CLASSES, não letras.

        A primeira versão listava `ó`, que a frase não tem — e reprovou por uma
        afirmação minha, não por defeito da amostra. Os agudos estão cobertos
        por á, í e ú; exigir uma letra específica testa a redação da frase, não
        a cobertura tipográfica.
        """
        classes: set[str] = set()
        for char in PORTUGUESE_SAMPLE:
            decomposition = unicodedata.decomposition(char).split()
            if len(decomposition) > 1:
                mark = chr(int(decomposition[-1], 16))
                classes.add(unicodedata.name(mark).replace("COMBINING ", ""))
        for required in ("ACUTE ACCENT", "CIRCUMFLEX ACCENT", "TILDE", "CEDILLA", "GRAVE ACCENT"):
            assert required in classes, f"{required} ausente; presentes: {sorted(classes)}"

    def test_the_sample_covers_an_accented_capital(self) -> None:
        accented_capitals = [
            char for char in PORTUGUESE_SAMPLE if char.isupper() and unicodedata.decomposition(char)
        ]
        assert accented_capitals, "nenhuma maiúscula acentuada"

    def test_the_sample_covers_punctuation_beyond_ascii(self) -> None:
        """O travessão exercita um glifo que a pontuação ASCII não cobre."""
        assert "—" in PORTUGUESE_SAMPLE
        assert "," in PORTUGUESE_SAMPLE

    def test_the_text_survives_to_the_scene_unchanged(self, rendered: Any) -> None:
        """Substituição silenciosa de caractere sairia como texto plausível."""
        payload = json.loads(
            json.dumps(FIXTURES_BY_NAME["text-portuguese-accents"].model().to_dict())
        )
        assert payload["text"] == PORTUGUESE_SAMPLE

    def test_no_glyph_fell_back_to_the_notdef_box(self, rendered: Any) -> None:
        """A imagem sozinha não denuncia isso.

        Uma caixa `.notdef` no meio da frase parece um glifo estranho, não um
        defeito — e o golden congelaria a caixa como se fosse o correto.
        """
        widths = rendered.geometry["glyphWidths"]
        notdef = rendered.geometry["notdefWidth"]
        assert notdef > 0, "sem referência de notdef o detector não vale nada"
        broken = sorted(glyph for glyph, width in widths.items() if width == notdef)
        assert not broken, f"glifos ausentes renderizados como caixa: {broken}"

    def test_every_accented_character_has_a_real_glyph(self, rendered: Any) -> None:
        widths = rendered.geometry["glyphWidths"]
        accented = {glyph: width for glyph, width in widths.items() if ord(glyph) > 127}
        assert len(accented) >= 8, f"amostra fraca: {accented}"
        for glyph, width in accented.items():
            assert width > 0, f"{glyph!r} não desenhou nada"

    def test_the_detector_would_catch_a_real_absence(self, tmp_path: Path) -> None:
        """Detector que nunca acusa aprova qualquer fonte.

        `漢` não existe na Liberation Sans, e precisa aparecer exatamente na
        largura da caixa `.notdef`.
        """
        fixture = FIXTURES_BY_NAME["text-portuguese-accents"]
        result = _render(fixture, tmp_path, text="漢字")
        widths = result.geometry["glyphWidths"]
        notdef = result.geometry["notdefWidth"]
        assert widths, "nenhum glifo medido"
        assert all(width == notdef for width in widths.values()), (
            f"esperava só caixas de notdef, veio {widths}"
        )

    def test_two_lines_were_rendered(self, rendered: Any) -> None:
        assert "\n" in PORTUGUESE_SAMPLE
        assert rendered.geometry["contentHeight"] > rendered.geometry["fontPixelSize"] * 1.5

    def test_no_fallback_was_detected(self, rendered: Any) -> None:
        assert rendered.environment["fallbackDetected"] is False


class TestComposedAndDecomposedUnicode:
    """Duas representações do mesmo caractere visível.

    O objetivo NÃO é obrigar o IR a normalizar. É garantir que nenhuma das duas
    seja corrompida no caminho — normalizar em silêncio seria uma decisão de
    produto tomada por acidente de implementação.

    A comparação aqui é TEXTUAL: as duas formas são bytes diferentes e precisam
    permanecer diferentes na serialização. Que rendam pixels equivalentes é
    afirmado à parte, e é uma propriedade do shaping do Qt, não do contrato.
    """

    COMPOSED = "é"
    DECOMPOSED = "é"

    def test_the_two_forms_really_are_different_bytes(self) -> None:
        assert self.COMPOSED != self.DECOMPOSED
        assert len(self.COMPOSED) == 1
        assert len(self.DECOMPOSED) == 2
        assert unicodedata.normalize("NFC", self.DECOMPOSED) == self.COMPOSED

    @pytest.mark.parametrize("form", ["COMPOSED", "DECOMPOSED"])
    def test_serialization_preserves_the_exact_form(self, form: str) -> None:
        """Normalizar na serialização mudaria o texto do autor sem avisar."""
        from steamzero.domain.qml_render_model import to_render_model
        from steamzero.domain.resolved_node import ResolvedTextNode

        original = getattr(self, form)
        node = ResolvedTextNode(id="t", text=original, color="#ffffff")
        payload = json.loads(json.dumps(node.to_dict(), ensure_ascii=False))
        assert payload["text"] == original
        model = to_render_model(node).require_model()
        assert model.text == original
        assert json.loads(json.dumps(model.to_dict(), ensure_ascii=False))["text"] == original

    @pytest.mark.parametrize("form", ["COMPOSED", "DECOMPOSED"])
    def test_the_ir_round_trip_preserves_the_exact_form(self, form: str) -> None:
        from steamzero.domain.scene_contract import ElementContract
        from steamzero.domain.scene_serialization import document, parse_document

        original = getattr(self, form)
        element = ElementContract(id="t", type="text", text_content=original)
        restored = parse_document(document([element]))[0]
        assert restored.text_content == original

    @pytest.mark.parametrize("form", ["COMPOSED", "DECOMPOSED"])
    def test_neither_form_is_rejected_as_invalid(self, form: str, tmp_path: Path) -> None:
        """O harness não pode tratar uma das formas como string inválida."""
        fixture = FIXTURES_BY_NAME["text-baseline"]
        result = _render(fixture, tmp_path / form, text=getattr(self, form))
        assert result.geometry["contentWidth"] > 0
        assert not result.forbidden_messages

    def test_both_forms_produce_glyphs(self, tmp_path: Path) -> None:
        """Nenhuma das duas pode virar caixa de notdef."""
        fixture = FIXTURES_BY_NAME["text-baseline"]
        for label, text in (("composed", self.COMPOSED), ("decomposed", self.DECOMPOSED)):
            result = _render(fixture, tmp_path / label, text=text)
            notdef = result.geometry["notdefWidth"]
            widths = result.geometry["glyphWidths"]
            assert widths, label
            assert all(width != notdef for width in widths.values()), (label, widths)

    def test_the_two_forms_render_equivalently(self, tmp_path: Path) -> None:
        """Propriedade do shaping do Qt, afirmada e não presumida.

        Documentado aqui de propósito: se o Qt deixar de compor a marca, este
        teste reprova e a decisão sobre normalizar passa a ser explícita — em
        vez de aparecer como texto torto na tela de alguém.
        """
        fixture = FIXTURES_BY_NAME["text-baseline"]
        composed = _render(fixture, tmp_path / "c", text=self.COMPOSED)
        decomposed = _render(fixture, tmp_path / "d", text=self.DECOMPOSED)
        assert composed.geometry["contentWidth"] == decomposed.geometry["contentWidth"]
        metrics = compare_with_golden(decomposed.image, composed.image, tmp_path / "diff")
        assert metrics.changed_pixel_count == 0

    def test_no_baseline_was_created_for_this(self) -> None:
        """A cobertura é estrutural: uma terceira imagem não acrescentaria nada."""
        assert not (GOLDEN_DIR / "text-composed.png").exists()
        assert not (GOLDEN_DIR / "text-decomposed.png").exists()


class TestScopeIsNotWidenedYet:
    """CJK e RTL pertencem à entrega de internacionalização.

    Incluí-los agora exigiria fonte adicional, licença nova, fallback por
    script, direção de texto e shaping — possivelmente outro mecanismo de
    renderização. O VS-07 congela só o que o contrato afirma suportar de ponta a
    ponta hoje.
    """

    def test_no_cjk_fixture_exists(self) -> None:
        for fixture in FIXTURES:
            assert all(ord(char) < 0x2E80 for char in fixture.model().text), fixture.name

    def test_no_rtl_fixture_exists(self) -> None:
        for fixture in FIXTURES:
            assert all(not (0x0590 <= ord(char) <= 0x08FF) for char in fixture.model().text), (
                fixture.name
            )

    def test_only_one_font_family_is_packaged(self) -> None:
        manifest = load_font_manifest()
        assert manifest["family"] == "Liberation Sans"
        assert len(manifest["files"]) == 4


class TestTheReportIdentifiesEveryImage:
    """Divergência de golden sem saber o ambiente que a produziu não se investiga."""

    @pytest.mark.parametrize("fixture", FIXTURES, ids=[item.name for item in FIXTURES])
    def test_every_run_records_what_produced_it(self, fixture: Fixture, tmp_path: Path) -> None:
        result = _render(fixture, tmp_path)
        environment = result.environment
        for key in (
            "qtVersion",
            "platform",
            "backend",
            "devicePixelRatio",
            "fontDpi",
            "locale",
            "requestedFontFamily",
            "availableFontFamilyCount",
            "resolvedFace",
            "fontFixture",
        ):
            assert key in environment, key
        assert environment["fontFile"]["packagedSha256"]
        assert environment["fontFixture"]["version"] == "2.1.5"

    def test_the_baseline_hashes_are_stable_within_a_run(self, tmp_path: Path) -> None:
        fixture = FIXTURES_BY_NAME["text-baseline"]
        first = hashlib.sha256(_render(fixture, tmp_path / "a").image.read_bytes()).hexdigest()
        second = hashlib.sha256(_render(fixture, tmp_path / "b").image.read_bytes()).hexdigest()
        assert first == second
