# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Coerência entre assets empacotados, allowlist do QML e manifests.

Estes testes existem porque "arquivo está no wheel" nunca provou "imagem
renderiza". Aqui garantimos o degrau anterior: que as três listas — arquivos
reais, allowlist do QML e referências dos manifests — não divergem. A prova de
renderização propriamente dita fica em ``tests/qml/check_packaged_assets.qml``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[2] / "src" / "steamzero"
_ASSETS_DIR = _SRC / "ui" / "assets"
_QML_REGISTRY = _SRC / "ui" / "qml" / "PackagedAssets.qml"
_MANIFEST_DIRS = (_SRC / "platform_manifests", _SRC / "adapters" / "manifests")
_ASSET_KEYS = ("artworkAsset", "iconAsset")
# Documentação de atribuição convive com os binários e não é um asset renderizável.
_NON_ASSET_FILES = {"ATTRIBUTION.md"}


def _packaged_assets() -> set[str]:
    return {
        entry.name
        for entry in _ASSETS_DIR.iterdir()
        if entry.is_file() and entry.name not in _NON_ASSET_FILES
    }


def _qml_allowlist() -> list[str]:
    source = _QML_REGISTRY.read_text(encoding="utf-8")
    block = re.search(r"readonly property var allowed:\s*\[(.*?)\]", source, re.DOTALL)
    assert block is not None, "allowlist não encontrada em PackagedAssets.qml"
    return re.findall(r'"([^"]+)"', block.group(1))


def _manifest_references() -> dict[str, list[str]]:
    refs: dict[str, list[str]] = {}
    for directory in _MANIFEST_DIRS:
        for manifest in sorted(directory.glob("*.json")):
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
            except json.JSONDecodeError:  # pragma: no cover - manifesto quebrado
                continue
            if not isinstance(data, dict):
                continue
            for key in _ASSET_KEYS:
                declared = data.get(key)
                if isinstance(declared, str) and declared:
                    refs.setdefault(declared, []).append(manifest.name)
    return refs


class TestAllowlistMatchesPackage:
    def test_allowlist_has_no_duplicates(self) -> None:
        allowed = _qml_allowlist()
        assert len(allowed) == len(set(allowed))

    def test_allowlist_is_sorted(self) -> None:
        """Ordenada para que diffs de asset sejam legíveis."""
        allowed = _qml_allowlist()
        assert allowed == sorted(allowed)

    def test_allowlist_equals_packaged_files(self) -> None:
        """Divergência aqui é a regressão da a37: asset citado mas não entregue."""
        assert set(_qml_allowlist()) == _packaged_assets()


class TestManifestReferences:
    def test_every_reference_is_packaged(self) -> None:
        missing = {
            declared: sources
            for declared, sources in _manifest_references().items()
            if Path(declared).name not in _packaged_assets()
        }
        assert not missing, f"manifests referenciam assets ausentes: {missing}"

    def test_every_reference_is_allowlisted(self) -> None:
        allowed = set(_qml_allowlist())
        rejected = {
            declared: sources
            for declared, sources in _manifest_references().items()
            if Path(declared).name not in allowed
        }
        assert not rejected, f"referências fora da allowlist seriam descartadas: {rejected}"

    def test_switch_declares_its_artwork(self) -> None:
        refs = _manifest_references()
        assert "../assets/switch.svg" in refs

    def test_retroarch_artwork_is_shared(self) -> None:
        """Um adapter compartilhado atende várias plataformas sem duplicar arquivo."""
        refs = _manifest_references()
        sharing = refs.get("../assets/retroarch.svg", [])
        assert len(sharing) > 1, "retroarch deveria servir mais de uma plataforma"


class TestEmulatorPresentationAssets:
    def test_presentation_icons_are_packaged(self) -> None:
        from steamzero.adapters.emulation import _EMULATOR_PRESENTATION

        packaged = _packaged_assets()
        for emulator_id, (_name, icon_asset) in _EMULATOR_PRESENTATION.items():
            assert Path(icon_asset).name in packaged, (
                f"ícone de {emulator_id} não está empacotado: {icon_asset}"
            )

    def test_presentation_icons_are_allowlisted(self) -> None:
        from steamzero.adapters.emulation import _EMULATOR_PRESENTATION

        allowed = set(_qml_allowlist())
        for emulator_id, (_name, icon_asset) in _EMULATOR_PRESENTATION.items():
            assert Path(icon_asset).name in allowed, (
                f"ícone de {emulator_id} seria descartado pela allowlist: {icon_asset}"
            )


class TestAssetsAreReadable:
    @pytest.mark.parametrize("name", sorted(_packaged_assets()))
    def test_asset_is_non_empty(self, name: str) -> None:
        assert (_ASSETS_DIR / name).stat().st_size > 0

    @pytest.mark.parametrize("name", sorted(n for n in _packaged_assets() if n.endswith(".svg")))
    def test_svg_declares_svg_root(self, name: str) -> None:
        """Sinal barato de corrupção.

        A prova forte de que o SVG carrega é ``Image.Ready`` em
        ``tests/qml/check_packaged_assets.qml``; aqui só detectamos cedo um
        arquivo que deixou de ser SVG. Não parseamos XML: seria tratar arquivo
        do próprio pacote como entrada não confiável e ainda assim provaria
        menos que o harness.
        """
        head = (_ASSETS_DIR / name).read_text(encoding="utf-8", errors="replace")[:512]
        assert "<svg" in head, f"{name} não declara elemento <svg>"
