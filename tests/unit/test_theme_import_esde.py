# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Importação de temas ES-DE para o contrato nativo de tokens.

As fixtures são sintéticas e imitam a forma real de um ``colors.xml`` do ES-DE.
Nenhum conteúdo de terceiros é versionado aqui — o tema usado na medição
(Canvas, CC0-1.0) foi analisado fora do repositório.

O que estes testes protegem é a honestidade da conversão: o que é lido da
origem, o que é derivado por regra óbvia, e o que é deliberadamente OMITIDO para
ser herdado em vez de inventado.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar

import jsonschema
import pytest

from steamzero.core.errors import SteamZeroError
from steamzero.domain.theme_import_esde import (
    INHERITED_TOKENS,
    MAX_ASSET_BYTES,
    build_manifest,
    import_report,
    import_scheme,
    map_to_tokens,
    parse_color_schemes,
    resolve_assets,
    unsupported_slots,
)

_SCHEMA = json.loads(
    (
        Path(__file__).resolve().parents[2]
        / "src"
        / "steamzero"
        / "schemas"
        / "theme-manifest-v1.schema.json"
    ).read_text(encoding="utf-8")
)

_COLORS = """<theme>
  <colorScheme name="dark,neon">
    <view><backgroundColor>101820</backgroundColor></view>
  </colorScheme>
  <colorScheme name="dark">
    <view>
      <gamelistSelectedColor>ffffff</gamelistSelectedColor>
      <helpTextColor>9aa4b0</helpTextColor>
      <gridSelectorColor>808080</gridSelectorColor>
      <systemCarouselTextBackgroundColor>070c12</systemCarouselTextBackgroundColor>
    </view>
  </colorScheme>
  <colorScheme name="neon">
    <view>
      <gamelistSelectedColor>fdfdfd</gamelistSelectedColor>
      <helpTextColor>b0a0d0</helpTextColor>
      <gridSelectorColor>c400ff</gridSelectorColor>
    </view>
  </colorScheme>
  <colorScheme name="semfundo">
    <view><helpTextColor>cccccc</helpTextColor></view>
  </colorScheme>
</theme>"""


class TestParsing:
    def test_one_block_can_define_many_schemes(self) -> None:
        """`name="dark,neon"` alimenta os dois — é como o ES-DE compartilha valores."""
        schemes = parse_color_schemes(_COLORS)
        assert schemes["dark"]["backgroundColor"] == "#101820"
        assert schemes["neon"]["backgroundColor"] == "#101820"

    def test_first_definition_wins(self) -> None:
        """Mesma tag em blocos diferentes: vale a primeira, como no ES-DE."""
        xml = """<theme>
          <colorScheme name="x"><v><backgroundColor>111111</backgroundColor></v></colorScheme>
          <colorScheme name="x"><v><backgroundColor>222222</backgroundColor></v></colorScheme>
        </theme>"""
        assert parse_color_schemes(xml)["x"]["backgroundColor"] == "#111111"

    def test_non_color_values_are_ignored(self) -> None:
        """colors.xml carrega caminhos e escalas junto das cores."""
        xml = """<theme><colorScheme name="x"><v>
          <backgroundColor>101820</backgroundColor>
          <selectorImagePath>./_inc/square.svg</selectorImagePath>
          <selectorRelativeScaleSize>0.89</selectorRelativeScaleSize>
        </v></colorScheme></theme>"""
        assert set(parse_color_schemes(xml)["x"]) == {"backgroundColor"}

    def test_malformed_xml_is_structured_error(self) -> None:
        with pytest.raises(SteamZeroError, match=r"colors\.xml inválido"):
            parse_color_schemes("<theme><nao fechado>")

    def test_alpha_channel_is_dropped(self) -> None:
        """ES-DE aceita RRGGBBAA; o contrato do SteamZero é RRGGBB."""
        xml = (
            '<theme><colorScheme name="x"><v>'
            "<backgroundColor>10182080</backgroundColor>"
            "</v></colorScheme></theme>"
        )
        assert parse_color_schemes(xml)["x"]["backgroundColor"] == "#101820"


class TestMapping:
    def test_direct_tokens_come_from_the_source(self) -> None:
        tokens, _ = map_to_tokens(parse_color_schemes(_COLORS)["neon"])
        assert tokens["background"] == "#101820"
        assert tokens["accent"] == "#c400ff"
        assert tokens["focus"] == "#c400ff"

    def test_surfaces_are_derived_between_background_and_text(self) -> None:
        tokens, derived = map_to_tokens(parse_color_schemes(_COLORS)["dark"])
        assert {"surface", "surfaceRaised", "surfaceSelected", "border"} <= set(derived)
        # A hierarquia precisa ser monotônica, senão a UI perde profundidade.
        order = [tokens[k] for k in ("background", "surface", "surfaceRaised", "surfaceSelected")]
        assert order == sorted(order), "superfícies devem caminhar do fundo para o texto"

    def test_derived_tokens_are_reported_as_derived(self) -> None:
        """A origem de cada valor precisa ser auditável."""
        tokens, derived = map_to_tokens(parse_color_schemes(_COLORS)["neon"])
        assert "accent" not in derived, "accent veio da origem"
        assert "accentStrong" in derived, "accentStrong foi calculado"
        assert set(derived) <= set(tokens)

    def test_semantic_tokens_are_never_invented(self) -> None:
        """Sucesso, aviso e perigo não existem no ES-DE.

        Derivá-los daria um valor plausível e ERRADO. Omitir deixa a herança
        resolver, que é a resposta honesta.
        """
        tokens, _ = map_to_tokens(parse_color_schemes(_COLORS)["neon"])
        for token in INHERITED_TOKENS:
            assert token not in tokens, f"{token} não pode ser inventado"


class TestImportScheme:
    def test_import_produces_tokens_and_report(self) -> None:
        imported = import_scheme("neon", _COLORS, available_assets={"wallpapers/neon.webp": 18748})
        assert imported.name == "neon"
        assert imported.wallpaper == "assets/background.webp"
        report = import_report(imported)
        assert report["fidelity"] == "palette+background", "com asset a fidelidade sobe"
        assert report["inherited"] == list(INHERITED_TOKENS)

    def test_monochrome_scheme_is_flagged(self) -> None:
        """Alguns esquemas têm identidade na arte, não na paleta.

        Marcar isso evita prometer uma fidelidade que a conversão não entrega.
        """
        assert import_scheme("dark", _COLORS).is_monochrome is True

    def test_chromatic_scheme_is_not_flagged(self) -> None:
        assert import_scheme("neon", _COLORS).is_monochrome is False

    def test_scheme_without_background_is_refused(self) -> None:
        with pytest.raises(SteamZeroError, match="não declara cor de fundo"):
            import_scheme("semfundo", _COLORS)

    def test_unknown_scheme_is_refused(self) -> None:
        with pytest.raises(SteamZeroError, match="não existe"):
            import_scheme("inexistente", _COLORS)

    @pytest.mark.parametrize("bad", ["../escape", "Dark", "nome com espaço", ""])
    def test_invalid_scheme_name_is_refused(self, bad: str) -> None:
        with pytest.raises(SteamZeroError, match="esquema inválido"):
            import_scheme(bad, _COLORS)


class TestManifest:
    def _manifest(self, scheme: str = "neon", **kw: object) -> dict[str, object]:
        base: dict[str, object] = {
            "theme_id": "org.esde.exemplo-neon",
            "name": "Exemplo Neon",
            "author": "Autor",
            "license_id": "CC0-1.0",
        }
        base.update(kw)
        return build_manifest(
            import_scheme(scheme, _COLORS, available_assets={"wallpapers/neon.webp": 18748}),
            **base,  # type: ignore[arg-type]
        )

    def test_manifest_validates_against_the_native_schema(self) -> None:
        """O ponto do desenho: um contrato, duas origens."""
        jsonschema.validate(self._manifest(), _SCHEMA)

    def test_manifest_extends_the_base_theme(self) -> None:
        """A herança é o que permite omitir os semânticos."""
        assert self._manifest()["extends"] == "org.steamzero.default"

    def test_wallpaper_becomes_the_background_asset(self) -> None:
        assets = self._manifest()["assets"]
        assert isinstance(assets, dict)
        assert assets["background"] == "assets/background.webp"

    def test_import_without_wallpaper_declares_no_asset(self) -> None:
        manifest = build_manifest(
            import_scheme("neon", _COLORS),
            theme_id="org.esde.sem-fundo",
            name="Sem Fundo",
            author="Autor",
            license_id="CC0-1.0",
        )
        assert manifest["assets"] == {}
        jsonschema.validate(manifest, _SCHEMA)

    def test_missing_license_is_refused(self) -> None:
        """themes.json não declara licença; importar sem confirmar seria adivinhar."""
        with pytest.raises(SteamZeroError, match="licença é obrigatória"):
            self._manifest(license_id="  ")

    @pytest.mark.parametrize("bad", ["semponto", "../escape", "COM.MAIUSCULA"])
    def test_invalid_theme_id_is_refused(self, bad: str) -> None:
        with pytest.raises(SteamZeroError, match="id inválido"):
            self._manifest(theme_id=bad)

    def test_description_declares_what_was_lost(self) -> None:
        """O usuário precisa saber que layout não veio junto."""
        assert "Layout" in str(self._manifest()["description"])

    def test_every_scheme_of_the_fixture_converts(self) -> None:
        for scheme in ("dark", "neon"):
            jsonschema.validate(self._manifest(scheme), _SCHEMA)


class TestAssetResolution:
    """O domínio decide QUAL arquivo preenche cada slot; quem baixa é o adapter."""

    _INV: ClassVar[dict[str, int]] = {
        "wallpapers/dark.webp": 59430,
        "wallpapers/neon.webp": 18748,
        "wallpapers/Alternate/pastel.webp": 18494,
        "wallpapers/animated/.PLACE GIF WALLPAPERS HERE.txt": 0,
        "_inc/system-logo/snes.svg": 4096,
        "templates/Canvas-Logo-Template.psd": 5674473,
    }

    def test_scheme_wallpaper_becomes_the_background(self) -> None:
        plans = resolve_assets("neon", self._INV)
        assert len(plans) == 1
        assert plans[0].slot == "background"
        assert plans[0].source_path == "wallpapers/neon.webp"
        assert plans[0].target_path == "assets/background.webp"

    def test_alternate_directory_is_used_as_fallback(self) -> None:
        """Vários temas publicam parte dos esquemas só em wallpapers/Alternate."""
        plans = resolve_assets("pastel", self._INV)
        assert plans[0].source_path == "wallpapers/Alternate/pastel.webp"

    def test_scheme_without_wallpaper_yields_no_asset(self) -> None:
        """Ausência é estado legítimo: importa-se só a paleta."""
        assert resolve_assets("inexistente", self._INV) == []

    def test_empty_file_is_not_an_asset(self) -> None:
        """O diretório animated/ tem um placeholder de zero byte."""
        assert resolve_assets("animated", {"wallpapers/animated.webp": 0}) == []

    def test_oversized_asset_is_skipped_not_fatal(self) -> None:
        """Passar do limite geraria pacote que a validação recusaria depois.

        Seguir sem papel de parede é melhor que produzir algo inválido.
        """
        big = {"wallpapers/x.webp": MAX_ASSET_BYTES + 1}
        assert resolve_assets("x", big) == []

    def test_system_art_never_fills_the_logo_slot(self) -> None:
        """O que o ES-DE chama de logo é arte por SISTEMA.

        Usar o logo do SNES como marca da central inteira seria plausível de
        implementar e errado de exibir.
        """
        for plan in resolve_assets("neon", self._INV):
            assert plan.slot != "logo"
            assert "system-logo" not in plan.source_path
            assert not plan.source_path.endswith(".psd")

    def test_unsupported_slots_carry_their_reason(self) -> None:
        reasons = unsupported_slots()
        assert set(reasons) == {"logo", "sidebar"}
        for slot, reason in reasons.items():
            assert reason, f"{slot} sem explicação"

    @pytest.mark.parametrize("bad", ["../escape", "COM.MAIUSCULA", ""])
    def test_invalid_scheme_name_is_refused(self, bad: str) -> None:
        with pytest.raises(SteamZeroError, match="esquema inválido"):
            resolve_assets(bad, self._INV)


class TestFidelityIsReported:
    def test_palette_only_when_no_asset(self) -> None:
        report = import_report(import_scheme("neon", _COLORS))
        assert report["fidelity"] == "palette-only"
        assert report["assets"] == []

    def test_palette_plus_background_when_asset_found(self) -> None:
        imported = import_scheme("neon", _COLORS, available_assets={"wallpapers/neon.webp": 18748})
        report = import_report(imported)
        assert report["fidelity"] == "palette+background"
        assert report["assetBytes"] == 18748

    def test_report_names_what_has_no_source(self) -> None:
        """A UI precisa distinguir "não veio" de "faltou implementar"."""
        report = import_report(import_scheme("neon", _COLORS))
        assert set(report["unsupportedSlots"]) == {"logo", "sidebar"}
