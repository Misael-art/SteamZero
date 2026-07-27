# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""O read model publica plataformas compostas, não linhas mortas.

Antes, tudo que não era Switch saía de `platform_placeholder`: `unverified`, nada
instalável, sem ícone e sem motivo — 33 linhas em que o usuário via a plataforma
e não descobria por que clicar não fazia nada.

Os fatos chegam INJETADOS: quem conhece o estado do host é a camada de adapters,
e domínio não importa adapters. Estes testes exercitam a injeção com fatos
sintéticos; nenhum consulta o host.
"""

from __future__ import annotations

import pytest

from steamzero.domain.emulation_workspace import build_switch_workspace
from steamzero.domain.platform_composer import EmulatorFacts


def _installed(adapter_id: str) -> EmulatorFacts:
    return EmulatorFacts(
        adapter_id=adapter_id,
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


def _others(payload: dict[str, object]) -> list[dict[str, object]]:
    platforms = payload["platforms"]
    assert isinstance(platforms, list)
    return [p for p in platforms if p["id"] != "switch"]


class TestWithoutFactsNothingIsClaimed:
    """Sem fatos injetados o placeholder continua sendo a resposta honesta.

    Significa "ninguém consultou o host", não "a plataforma está indisponível".
    """

    def test_placeholder_is_preserved(self) -> None:
        for platform in _others(build_switch_workspace()):
            assert platform["state"] == "planned"

    def test_no_platform_claims_launchability(self) -> None:
        for platform in _others(build_switch_workspace()):
            assert platform.get("launchable") in (None, False)


class TestWithFactsThePlatformSpeaks:
    def test_every_platform_gets_a_reason_when_not_launchable(self) -> None:
        """A regra que elimina a linha morta, verificada no payload inteiro."""
        payload = build_switch_workspace(emulator_facts=_absent, core_present=lambda _c: False)
        for platform in _others(payload):
            if platform.get("launchable") is False:
                assert platform.get("launchReason"), f"{platform['id']} sem motivo"

    def test_emulator_rows_carry_name_and_icon(self) -> None:
        payload = build_switch_workspace(emulator_facts=_absent)
        rows = [
            row
            for platform in _others(payload)
            for row in platform["emulators"]  # type: ignore[index]
        ]
        assert rows, "esperava linhas de emulador compostas"
        for row in rows:
            assert row["displayName"]
            assert row.get("iconAsset"), f"{row['id']} sem ícone"

    def test_missing_core_is_reported_per_platform(self) -> None:
        """O ponto do RetroArch: instalado não basta, o core é por plataforma."""
        payload = build_switch_workspace(emulator_facts=_installed, core_present=lambda _c: False)
        snes = next(p for p in _others(payload) if p["id"] == "snes")
        assert snes["launchable"] is False
        assert "snes9x" in str(snes["launchReason"])

    def test_present_core_makes_the_platform_launchable(self) -> None:
        payload = build_switch_workspace(emulator_facts=_installed, core_present=lambda _c: True)
        snes = next(p for p in _others(payload) if p["id"] == "snes")
        assert snes["launchable"] is True
        assert snes["launchReason"] is None

    def test_one_retroarch_install_serves_many_platforms(self) -> None:
        """A propriedade central: um adapter instalado, várias plataformas vivas."""
        payload = build_switch_workspace(emulator_facts=_installed, core_present=lambda _c: True)
        launchable = [p["id"] for p in _others(payload) if p.get("launchable")]
        assert len(launchable) >= 20, f"esperava muitas plataformas vivas, vi {len(launchable)}"


class TestSwitchIsUntouched:
    """A composição das demais não pode alterar a verdade do Switch."""

    def test_switch_still_comes_from_its_own_builder(self) -> None:
        payload = build_switch_workspace(emulator_facts=_installed, core_present=lambda _c: True)
        platforms = payload["platforms"]
        assert isinstance(platforms, list)
        switch = platforms[0]
        assert switch["id"] == "switch"
        assert "launchable" not in switch or switch.get("launchable") is None

    def test_switch_requirements_survive_composition(self) -> None:
        payload = build_switch_workspace(
            keys={
                "kind": "keys",
                "status": "ok",
                "required": "rev21",
                "installed": "rev21",
                "detail": "ok",
                "blocksPlay": False,
            },
            firmware={
                "kind": "firmware",
                "status": "ok",
                "required": "22.5.0",
                "installed": "22.5.0",
                "detail": "ok",
                "blocksPlay": False,
            },
            emulator_facts=_installed,
            core_present=lambda _c: True,
        )
        platforms = payload["platforms"]
        assert isinstance(platforms, list)
        switch = platforms[0]
        assert switch["requirements"]["keys"]["installed"] == "rev21"  # type: ignore[index]


class TestContractStillHolds:
    @pytest.mark.parametrize("core", [True, False])
    def test_composed_payload_validates(self, core: bool) -> None:
        """build_switch_workspace valida contra o schema antes de retornar."""
        build_switch_workspace(emulator_facts=_installed, core_present=lambda _c: core)

    def test_failing_adapter_degrades_only_its_own_platforms(self) -> None:
        """AGENTS.md §8: falha de um adapter não derruba a central.

        Um componente que não respondeu não pode custar a listagem inteira — a
        degradação seria pior que a informação faltante.
        """

        def broken(adapter_id: str) -> EmulatorFacts:
            if adapter_id == "retroarch":
                raise RuntimeError("provedor quebrou")
            return _absent(adapter_id)

        payload = build_switch_workspace(emulator_facts=broken)
        others = _others(payload)
        assert len(others) >= 30, "a central continua navegável"

        snes = next(p for p in others if p["id"] == "snes")
        row = snes["emulators"][0]  # type: ignore[index]
        assert row["installable"] is False
        assert "consultar" in str(row["reason"]), "o motivo precisa dizer que a leitura falhou"

        dreamcast = next(p for p in others if p["id"] == "dreamcast")
        healthy = dreamcast["emulators"][0]  # type: ignore[index]
        assert healthy["adapterId"] == "flycast"
        assert healthy["installable"] is True, "adapter saudável não é afetado"

    def test_malformed_launch_profile_does_not_crash_the_workspace(self) -> None:
        """Contrato de launch quebrado invalida o lançamento, não a listagem."""
        from steamzero.domain.platform_composer import compose_platform
        from steamzero.domain.platforms import PlatformRegistry

        manifest = PlatformRegistry.bundled().get("snes")
        broken = [dict(e) for e in manifest.emulators]
        broken[0]["launch"] = {"gameArgs": ["--rom={rom}"]}
        import dataclasses

        platform = compose_platform(
            dataclasses.replace(manifest, emulators=tuple(broken)), facts_for=_installed
        )
        assert platform["launchable"] is False
        assert platform["launchReason"]
