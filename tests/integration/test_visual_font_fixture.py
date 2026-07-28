# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""VIS-01 — a fonte de teste é a MESMA em toda máquina.

A descoberta que motiva a metade menos óbvia deste módulo: `FontLoader`
carregando o arquivo certo NÃO basta. Medido nesta bancada, com a Liberation
Sans do sistema instalada, o Qt usou a do SISTEMA mesmo com o arquivo empacotado
carregado — `contentWidth` 320.08. Com o fontconfig isolado na fixture, 323.

O golden teria congelado a métrica da fonte errada, e esse defeito não tem
sintoma: a imagem sai, parece certa, e só não reproduz noutra máquina.
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

#: Exigem runtime QML. Roteados para o gate visual dedicado, que reprova
#: quando o Qt falta — não são pulados em lugar nenhum.
pytestmark = pytest.mark.visual

from qml_capture_fixtures import FIXTURES_BY_NAME  # noqa: E402
from qml_capture_runner import (  # noqa: E402
    DIAG_FONT_HASH,
    DIAG_FONT_LICENSE,
    DIAG_FONT_MISSING,
    FONT_FIXTURE,
    CanonicalEnvironment,
    CaptureError,
    capture,
    load_font_manifest,
)

CANVAS = (800, 240)
BACKGROUND = "#101418"

EXPECTED_FACES = (
    "LiberationSans-Regular.ttf",
    "LiberationSans-Bold.ttf",
    "LiberationSans-Italic.ttf",
    "LiberationSans-BoldItalic.ttf",
)


@pytest.fixture(scope="module")
def manifest() -> dict[str, Any]:
    return load_font_manifest()


class TestThePackagedArtefactIsIntact:
    def test_all_four_faces_are_present(self, manifest: dict[str, Any]) -> None:
        """Bold e itálico vêm empacotados, não sintetizados.

        A síntese do Qt varia entre plataformas, e um golden que dependesse dela
        deixaria de reproduzir sem nenhuma mudança de código.
        """
        names = {entry["name"] for entry in manifest["files"]}
        assert names == set(EXPECTED_FACES)
        for name in EXPECTED_FACES:
            assert (FONT_FIXTURE / name).is_file()

    @pytest.mark.parametrize("name", EXPECTED_FACES)
    def test_each_hash_matches_the_manifest(self, name: str, manifest: dict[str, Any]) -> None:
        entry = next(item for item in manifest["files"] if item["name"] == name)
        path = FONT_FIXTURE / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]
        assert path.stat().st_size == entry["byteSize"]

    def test_the_version_is_pinned(self, manifest: dict[str, Any]) -> None:
        assert manifest["version"] == "2.1.5"
        assert manifest["family"] == "Liberation Sans"

    def test_the_licence_travels_with_the_binaries(self, manifest: dict[str, Any]) -> None:
        """Redistribuir sem o texto da OFL viola a licença que permite redistribuir."""
        assert manifest["licenseSpdx"] == "OFL-1.1-RFN"
        assert manifest["reservedFontName"] == "Liberation"
        licence = (FONT_FIXTURE / manifest["licenseFile"]).read_text(encoding="utf-8")
        assert "SIL Open Font License" in licence
        assert "Reserved Font Name" in licence

    def test_the_authors_travel_too(self) -> None:
        assert (FONT_FIXTURE / "AUTHORS.txt").is_file()

    def test_the_origin_is_recorded(self, manifest: dict[str, Any]) -> None:
        """Sem a origem e o hash do artefato, atualizar vira adivinhação."""
        assert manifest["artifact"].startswith("https://github.com/liberationfonts/")
        assert len(manifest["artifactSha256"]) == 64
        source = (FONT_FIXTURE / "SOURCE.md").read_text(encoding="utf-8")
        assert manifest["artifactSha256"] in source

    def test_the_notices_file_lists_the_font(self) -> None:
        notices = (ROOT / "docs" / "11-legal" / "THIRD-PARTY-NOTICES.md").read_text(
            encoding="utf-8"
        )
        assert "Liberation Sans 2.1.5" in notices
        assert "OFL-1.1-RFN" in notices
        for entry in load_font_manifest()["files"]:
            assert entry["sha256"] in notices, f"{entry['name']} sem hash nos notices"


class TestIntegrityGatesActuallyFire:
    """Verificado por mutação: um gate que nunca dispara não é um gate."""

    def _mutate(self, tmp_path: Path, change: Any) -> None:
        manifest = json.loads((FONT_FIXTURE / "manifest.json").read_text(encoding="utf-8"))
        change(manifest)
        (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def test_a_divergent_hash_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import qml_capture_runner

        for name in EXPECTED_FACES:
            (tmp_path / name).write_bytes((FONT_FIXTURE / name).read_bytes())
        (FONT_FIXTURE / "OFL.txt").read_text(encoding="utf-8")
        (tmp_path / "OFL.txt").write_text("x", encoding="utf-8")
        self._mutate(tmp_path, lambda m: m["files"][0].__setitem__("sha256", "0" * 64))
        monkeypatch.setattr(qml_capture_runner, "FONT_FIXTURE", tmp_path)
        with pytest.raises(CaptureError) as raised:
            load_font_manifest()
        assert raised.value.code == DIAG_FONT_HASH

    def test_a_missing_face_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import qml_capture_runner

        (tmp_path / "OFL.txt").write_text("x", encoding="utf-8")
        self._mutate(tmp_path, lambda m: m)
        monkeypatch.setattr(qml_capture_runner, "FONT_FIXTURE", tmp_path)
        with pytest.raises(CaptureError) as raised:
            load_font_manifest()
        assert raised.value.code == DIAG_FONT_MISSING

    def test_a_missing_licence_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import qml_capture_runner

        self._mutate(tmp_path, lambda m: m)
        monkeypatch.setattr(qml_capture_runner, "FONT_FIXTURE", tmp_path)
        with pytest.raises(CaptureError) as raised:
            load_font_manifest()
        assert raised.value.code == DIAG_FONT_LICENSE

    def test_an_incomplete_manifest_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import qml_capture_runner

        (tmp_path / "OFL.txt").write_text("x", encoding="utf-8")
        self._mutate(tmp_path, lambda m: m.pop("licenseSpdx"))
        monkeypatch.setattr(qml_capture_runner, "FONT_FIXTURE", tmp_path)
        with pytest.raises(CaptureError) as raised:
            load_font_manifest()
        assert raised.value.code == DIAG_FONT_MISSING

    def test_a_missing_manifest_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import qml_capture_runner

        monkeypatch.setattr(qml_capture_runner, "FONT_FIXTURE", tmp_path)
        with pytest.raises(CaptureError) as raised:
            load_font_manifest()
        assert raised.value.code == DIAG_FONT_MISSING


class TestTheSystemFontCannotShadowThePackagedOne:
    """A metade que quase passou despercebida.

    Sem isolamento de fontconfig, o Qt usava a Liberation Sans do SISTEMA mesmo
    com o arquivo empacotado disponível — a família tem o mesmo nome. E o pacote
    do Manjaro rotulado 2.1.5 NÃO é byte-idêntico ao artefato oficial.
    """

    def test_the_environment_isolates_fontconfig(self) -> None:
        env = CanonicalEnvironment().to_env()
        assert "FONTCONFIG_FILE" in env
        config = Path(env["FONTCONFIG_FILE"]).read_text(encoding="utf-8")
        assert str(FONT_FIXTURE) in config

    def test_only_the_packaged_family_is_visible(self, tmp_path: Path) -> None:
        """4 famílias em vez das 555 do host: nada do sistema atravessa."""
        model = FIXTURES_BY_NAME["text-baseline"].model()
        result = capture(model.to_dict(), output=tmp_path, canvas=CANVAS, background=BACKGROUND)
        assert result.environment["availableFontFamilyCount"] <= 8, (
            "o host tem centenas de famílias; ver mais que um punhado significa "
            "que o isolamento não pegou"
        )
        assert result.environment["testFontAvailable"] is True

    def test_the_run_records_which_fixture_was_used(self, tmp_path: Path) -> None:
        model = FIXTURES_BY_NAME["text-baseline"].model()
        result = capture(model.to_dict(), output=tmp_path, canvas=CANVAS, background=BACKGROUND)
        fixture = result.environment["fontFixture"]
        assert fixture["version"] == "2.1.5"
        assert fixture["isolated"] is True
        assert len(fixture["faces"]) == 4
        assert result.environment["fontFile"]["packagedSha256"]

    def test_the_packaged_file_differs_from_the_system_one(self) -> None:
        """O motivo de não copiar do sistema, afirmado por teste.

        Se algum dia o pacote da distribuição coincidir, o teste passa a ser
        vacuamente verdadeiro — por isso ele compara o hash REGISTRADO, que veio
        do artefato oficial, e não uma igualdade oportunista.
        """
        manifest = load_font_manifest()
        regular = next(
            item for item in manifest["files"] if item["name"] == "LiberationSans-Regular.ttf"
        )
        assert regular["sha256"] == (
            "76d04c18ea243f426b7de1f3ad208e927008f961dc5945e5aad352d0dfde8ee8"
        ), "o hash do artefato oficial 2.1.5 mudou; revise a origem antes de aceitar"


class TestEveryFaceRendersDistinctly:
    """Prova que as quatro faces existem de verdade no que é desenhado.

    Se o Qt sintetizasse bold e itálico a partir do Regular, as métricas ainda
    diferiam — mas variariam entre plataformas. O que este teste garante é que
    as quatro produzem resultados distintos E estáveis sob o ambiente canônico.
    """

    def _render(self, tmp_path: Path, **overrides: Any) -> Any:
        model = replace(FIXTURES_BY_NAME["text-baseline"].model(), **overrides)
        return capture(model.to_dict(), output=tmp_path, canvas=CANVAS, background=BACKGROUND)

    def test_the_four_faces_produce_four_different_widths(self, tmp_path: Path) -> None:
        widths = {
            "regular": self._render(tmp_path / "r").geometry["contentWidth"],
            "bold": self._render(tmp_path / "b", font_weight=700).geometry["contentWidth"],
            "italic": self._render(tmp_path / "i", font_italic=True).geometry["contentWidth"],
            "boldItalic": self._render(tmp_path / "bi", font_weight=700, font_italic=True).geometry[
                "contentWidth"
            ],
        }
        assert len(set(widths.values())) == 4, f"faces não distintas: {widths}"

    @pytest.mark.parametrize(
        ("label", "overrides"),
        [
            ("bold", {"font_weight": 700}),
            ("italic", {"font_italic": True}),
        ],
    )
    def test_changing_the_face_changes_the_image(
        self, tmp_path: Path, label: str, overrides: dict[str, Any]
    ) -> None:
        from qml_capture_runner import compare_with_golden

        base = self._render(tmp_path / "base")
        changed = self._render(tmp_path / label, **overrides)
        metrics = compare_with_golden(changed.image, base.image, tmp_path / f"{label}-diff")
        assert metrics.changed_pixel_count > 0, f"{label} não mudou nada na tela"

    def test_the_same_face_renders_identically_twice(self, tmp_path: Path) -> None:
        """Sem isto, a baseline do VS-07 seria comparada contra ruído."""
        from qml_capture_runner import compare_with_golden

        first = self._render(tmp_path / "first")
        second = self._render(tmp_path / "second")
        metrics = compare_with_golden(second.image, first.image, tmp_path / "compare")
        assert metrics.changed_pixel_count == 0

    @pytest.mark.parametrize("weight", [400, 700])
    def test_the_requested_weight_reaches_the_scene(self, tmp_path: Path, weight: int) -> None:
        result = self._render(tmp_path / str(weight), font_weight=weight)
        assert result.geometry["fontWeight"] == weight

    def test_the_requested_style_reaches_the_scene(self, tmp_path: Path) -> None:
        assert self._render(tmp_path / "i", font_italic=True).geometry["fontItalic"] is True


class TestScopeOfVis01:
    """O commit é isolado: só empacota a fonte e fecha o gate de integridade."""

    def test_the_font_is_not_shipped_with_the_product(self) -> None:
        """Fixture de teste não entra no wheel.

        A OFL permitiria, mas redistribuir no produto é outra decisão, e ela não
        foi tomada. Deixá-la acontecer por descuido é o que cria surpresa legal.
        """
        packaged = ROOT / "src" / "steamzero"
        assert not list(packaged.rglob("Liberation*.ttf"))

    def test_the_ui_does_not_reference_the_test_font(self) -> None:
        for qml in (ROOT / "src" / "steamzero" / "ui" / "qml").glob("*.qml"):
            assert "Liberation" not in qml.read_text(encoding="utf-8"), qml.name
