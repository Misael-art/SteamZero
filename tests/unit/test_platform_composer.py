# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Composição operacional de plataforma.

`platform_placeholder` projeta tudo como `unverified`, nada instalável, sem
ícone e — o pior — **sem motivo**. O usuário vê a linha e não descobre por que
clicar não faz nada. Foram 33 linhas assim na central.

O composer substitui o que é sabido por verdade real e, onde não sabe, diz por
quê. O que ele NÃO faz é habilitar ação: compor é declarar estado, habilitar é
outra decisão que depende do lifecycle inteiro ser real.
"""

from __future__ import annotations

from typing import Any

import pytest

from steamzero.api import contracts
from steamzero.domain.platform_composer import (
    EmulatorFacts,
    compose_platform,
    facts_from_status,
)
from steamzero.domain.platforms import PlatformRegistry


@pytest.fixture(scope="module")
def registry() -> PlatformRegistry:
    return PlatformRegistry.bundled()


def _installed(_adapter_id: str) -> EmulatorFacts:
    return EmulatorFacts(
        adapter_id="retroarch",
        display_name="RetroArch",
        icon_asset="../assets/retroarch.svg",
        installable=True,
        installed=True,
        version="abc123",
    )


def _absent(adapter_id: str) -> EmulatorFacts:
    return EmulatorFacts(
        adapter_id=adapter_id,
        display_name="RetroArch",
        icon_asset="../assets/retroarch.svg",
        installable=True,
        installed=False,
    )


def _validate(platform: dict[str, Any]) -> None:
    contracts.validate(
        {
            "schemaVersion": 1,
            "truthState": "ready",
            "contextLabel": "teste",
            "platforms": [platform],
        },
        "emulation-workspace-v1.schema.json",
    )


class TestLaunchability:
    def test_installed_with_core_is_launchable(self, registry: PlatformRegistry) -> None:
        platform = compose_platform(
            registry.get("snes"), facts_for=_installed, core_present_for=lambda _c: True
        )
        assert platform["launchable"] is True
        assert platform["launchReason"] is None
        assert platform["state"] == "ready"

    def test_missing_core_refuses_and_names_it(self, registry: PlatformRegistry) -> None:
        """O ponto do RetroArch: instalado não basta, o core é por plataforma."""
        platform = compose_platform(
            registry.get("snes"), facts_for=_installed, core_present_for=lambda _c: False
        )
        assert platform["launchable"] is False
        assert "snes9x" in platform["launchReason"]

    def test_not_installed_says_so(self, registry: PlatformRegistry) -> None:
        platform = compose_platform(
            registry.get("snes"), facts_for=_absent, core_present_for=lambda _c: True
        )
        assert platform["launchable"] is False
        assert "não está instalado" in platform["launchReason"]

    def test_platform_without_launch_profile_says_so(self, registry: PlatformRegistry) -> None:
        """Switch não declara launch nos manifests de plataforma."""
        platform = compose_platform(registry.get("switch"), facts_for=_installed)
        assert platform["launchable"] is False
        assert "lançar" in platform["launchReason"]

    def test_reason_is_never_absent_when_not_launchable(self, registry: PlatformRegistry) -> None:
        """A regra que elimina a linha morta: sem motivo, não publica."""
        for manifest in registry.list():
            platform = compose_platform(
                manifest, facts_for=_absent, core_present_for=lambda _c: False
            )
            if not platform["launchable"]:
                assert platform["launchReason"], f"{manifest.id} sem motivo"


class TestEmulatorRows:
    def test_row_carries_name_and_icon(self, registry: PlatformRegistry) -> None:
        row = compose_platform(registry.get("snes"), facts_for=_installed)["emulators"][0]
        assert row["displayName"] == "RetroArch"
        assert row["iconAsset"] == "../assets/retroarch.svg"

    def test_installed_row_reports_version(self, registry: PlatformRegistry) -> None:
        row = compose_platform(registry.get("snes"), facts_for=_installed)["emulators"][0]
        assert row["installState"] == "installed"
        assert row["version"] == "abc123"

    def test_rows_follow_precedence(self, registry: PlatformRegistry) -> None:
        """Onde há standalone, ele vem antes do RetroArch."""
        rows = compose_platform(registry.get("dreamcast"), facts_for=_absent)["emulators"]
        assert rows[0]["adapterId"] == "flycast"

    def test_core_presence_is_published_per_platform(self, registry: PlatformRegistry) -> None:
        row = compose_platform(
            registry.get("snes"), facts_for=_installed, core_present_for=lambda _c: False
        )["emulators"][0]
        assert row["coreInstalled"] is False
        assert row["launch"]["core"] == "snes9x"

    def test_unavailable_row_carries_its_reason(self, registry: PlatformRegistry) -> None:
        def blocked(adapter_id: str) -> EmulatorFacts:
            return EmulatorFacts(adapter_id, "RetroArch", None, False, False, None, "fonte EOL")

        row = compose_platform(registry.get("snes"), facts_for=blocked)["emulators"][0]
        assert row["installable"] is False
        assert row["reason"] == "fonte EOL"


class TestComposingDoesNotEnable:
    """Compor é declarar estado. Habilitar é outra decisão."""

    def test_area_actions_stay_disabled(self, registry: PlatformRegistry) -> None:
        platform = compose_platform(
            registry.get("snes"), facts_for=_installed, core_present_for=lambda _c: True
        )
        for area in platform["areaData"].values():
            action = area.get("primaryAction")
            if action is not None:
                assert action["enabled"] is False, "compor não pode habilitar ação"

    def test_disabled_actions_keep_a_reason(self, registry: PlatformRegistry) -> None:
        platform = compose_platform(registry.get("snes"), facts_for=_installed)
        for area in platform["areaData"].values():
            action = area.get("primaryAction")
            if action is not None and not action["enabled"]:
                assert action["reason"]


class TestContractIsRespected:
    @pytest.mark.parametrize("platform_id", ["snes", "arcade", "playstation", "dreamcast"])
    def test_composed_platform_validates(
        self, registry: PlatformRegistry, platform_id: str
    ) -> None:
        _validate(
            compose_platform(
                registry.get(platform_id),
                facts_for=_installed,
                core_present_for=lambda _c: True,
            )
        )

    def test_every_bundled_platform_composes(self, registry: PlatformRegistry) -> None:
        for manifest in registry.list():
            _validate(compose_platform(manifest, facts_for=_absent))


class TestFactsFromStatus:
    def test_absent_status_reports_missing_adapter(self) -> None:
        facts = facts_from_status("fantasma", None, None)
        assert facts.installable is False
        assert "não declarado" in (facts.reason or "")

    def test_status_is_translated(self) -> None:
        facts = facts_from_status(
            "retroarch",
            {"installable": True, "installed": True, "version": "abc", "reason": None},
            {"displayName": "RetroArch", "iconAsset": "../assets/retroarch.svg"},
        )
        assert facts.installed is True
        assert facts.display_name == "RetroArch"

    def test_blocked_status_keeps_its_reason(self) -> None:
        facts = facts_from_status(
            "duckstation",
            {"installable": False, "installed": False, "reason": "fonte fim de vida"},
            None,
        )
        assert facts.installable is False
        assert facts.reason == "fonte fim de vida"


class TestPlatformsWithoutEmulators:
    """Plataforma sem emulador declarado também precisa dizer por quê.

    As três de nuvem (GeForce NOW, Xbox Cloud, Amazon Luna) não são emuladas.
    Sem tratamento próprio elas saíam não-lançáveis SEM MOTIVO — a linha morta
    que este composer existe para eliminar.
    """

    @pytest.mark.parametrize("platform_id", ["geforce-now", "xbox-cloud-gaming", "amazon-luna"])
    def test_cloud_platform_explains_it_is_streaming(
        self, registry: PlatformRegistry, platform_id: str
    ) -> None:
        platform = compose_platform(registry.get(platform_id), facts_for=_absent)
        assert platform["emulators"] == []
        assert platform["launchable"] is False
        assert "streaming" in platform["launchReason"]

    def test_cloud_platform_still_validates(self, registry: PlatformRegistry) -> None:
        _validate(compose_platform(registry.get("geforce-now"), facts_for=_absent))
