# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Roteamento de lifecycle pelo tipo de fonte fixado.

O projeto tinha dois executores funcionando — AdapterEngine para fontes portáteis
e FlatpakExecutor para Flatpak — mas o caminho de EMULADOR ia direto para o
engine portátil, que recusava Flatpak com "executor ainda não está habilitado".
Oito dos treze emuladores declarados usam Flatpak; nenhum podia ser instalado,
apesar de adapter, manifesto e fonte fixada corretos.

Nenhum teste aqui executa flatpak de verdade nem toca o host.
"""

from __future__ import annotations

import pytest

from steamzero.adapters import lifecycle
from steamzero.adapters.registry import AdapterRegistry
from steamzero.core.errors import SteamZeroError


@pytest.fixture(scope="module")
def registry() -> AdapterRegistry:
    return AdapterRegistry.bundled()


class TestRouteSelection:
    def test_flatpak_source_routes_to_flatpak_executor(self, registry: AdapterRegistry) -> None:
        route = lifecycle.route_for(registry.get("retroarch"))
        assert route.executor == "flatpak"
        assert route.installable is True

    def test_appimage_source_routes_to_engine(self, registry: AdapterRegistry) -> None:
        route = lifecycle.route_for(registry.get("eden"))
        assert route.executor == "engine"
        assert route.installable is True

    def test_native_source_routes_to_engine(self, registry: AdapterRegistry) -> None:
        assert lifecycle.route_for(registry.get("sunshine")).executor == "engine"

    def test_every_declared_adapter_gets_a_decision(self, registry: AdapterRegistry) -> None:
        """Nenhum adapter pode ficar sem rota: ausência de decisão vira linha
        morta na UI, sem explicação de por que nada acontece."""
        routes = lifecycle.routes_for(registry)
        assert set(routes) == {m.id for m in registry.list()}
        for adapter_id, route in routes.items():
            assert route.executor in {"engine", "flatpak", "libretro", "none"}
            if not route.installable:
                assert route.reason, f"{adapter_id} não instalável sem motivo dizível"


class TestFailsClosed:
    """Fonte sem garantia da sua família não pode virar ação oferecida."""

    def _manifest(self, registry: AdapterRegistry, adapter_id: str, **source_overrides: object):  # type: ignore[no-untyped-def]
        import dataclasses

        manifest = registry.get(adapter_id)
        source = dataclasses.replace(manifest.sources[0], **source_overrides)
        return dataclasses.replace(manifest, sources=(source,))

    def test_end_of_life_source_is_refused(self, registry: AdapterRegistry) -> None:
        """A fonte EOL é sintetizada: o contrato é do roteamento, não do adapter.

        Antes o teste lia o DuckStation, então o único adapter EOL empacotado.
        Quando a fonte dele migrou para o AppImage oficial, o teste caiu sem que
        o contrato tivesse mudado — ele se amarrara ao exemplar, não ao
        comportamento.
        """
        route = lifecycle.route_for(self._manifest(registry, "retroarch", end_of_life=True))
        assert route.installable is False
        assert "fim de vida" in (route.reason or "")

    def test_portable_source_without_digest_is_refused(self, registry: AdapterRegistry) -> None:
        manifest = self._manifest(registry, "eden", sha256=None)
        route = lifecycle.route_for(manifest)
        assert route.installable is False
        assert "sha256" in (route.reason or "")

    def test_flatpak_source_without_ref_is_refused(self, registry: AdapterRegistry) -> None:
        manifest = self._manifest(registry, "retroarch", ref=None)
        route = lifecycle.route_for(manifest)
        assert route.installable is False
        assert "ref" in (route.reason or "")

    def test_flatpak_source_without_remote_is_refused(self, registry: AdapterRegistry) -> None:
        manifest = self._manifest(registry, "retroarch", remote=None)
        route = lifecycle.route_for(manifest)
        assert route.installable is False

    def test_unknown_source_family_is_refused(self, registry: AdapterRegistry) -> None:
        """Família nova sem executor não pode cair silenciosamente no portátil."""
        manifest = self._manifest(registry, "eden", type="snap")
        route = lifecycle.route_for(manifest)
        assert route.installable is False
        assert "snap" in (route.reason or "")


class TestNormalizedStatus:
    """A UI consome um formato só, venha de qual executor vier."""

    def test_engine_status_is_normalized(self, registry: AdapterRegistry) -> None:
        route = lifecycle.route_for(registry.get("eden"))
        payload = lifecycle.normalize_status(
            {"id": "eden", "state": "installed", "version": "1.2.3", "origin": "appimage"}, route
        )
        assert payload["installed"] is True
        assert payload["version"] == "1.2.3"
        assert payload["executor"] == "engine"

    def test_flatpak_status_is_normalized_to_the_same_shape(
        self, registry: AdapterRegistry
    ) -> None:
        route = lifecycle.route_for(registry.get("retroarch"))
        payload = lifecycle.normalize_status(
            {"id": "retroarch", "state": "installed", "commit": "abc123", "origin": "flathub"},
            route,
        )
        assert payload["installed"] is True
        assert payload["version"] == "abc123", "commit Flatpak ocupa o lugar de versão"
        assert payload["executor"] == "flatpak"

    def test_both_shapes_expose_the_same_keys(self, registry: AdapterRegistry) -> None:
        engine = lifecycle.normalize_status(
            {"state": "missing"}, lifecycle.route_for(registry.get("eden"))
        )
        flatpak = lifecycle.normalize_status(
            {"state": "missing"}, lifecycle.route_for(registry.get("retroarch"))
        )
        assert set(engine) == set(flatpak)

    def test_unavailable_status_carries_the_reason(self, registry: AdapterRegistry) -> None:
        import dataclasses

        manifest = registry.get("retroarch")
        source = dataclasses.replace(manifest.sources[0], end_of_life=True)
        route = lifecycle.route_for(dataclasses.replace(manifest, sources=(source,)))
        payload = lifecycle.unavailable_status(route)
        assert payload["installable"] is False
        assert payload["detail"]  # G27: motivo dizível, sob a chave normalizada
        assert payload["state"] == "unavailable"


class TestEmulatorPlanningRoutes:
    """O caminho de emulador escolhe executor em vez de assumir portátil."""

    def _controller(self):  # type: ignore[no-untyped-def]
        from steamzero.adapters.emulation import EmulationController

        return EmulationController()

    def test_unmanaged_emulator_is_still_refused(self) -> None:
        """Rotear não é habilitar: quem não tem lifecycle completo continua fora."""
        with pytest.raises(SteamZeroError):
            self._controller().plan_emulator("retroarch", "install")

    @pytest.mark.parametrize("emulator_id", ["eden", "citron", "ryubing"])
    def test_managed_emulators_still_use_the_portable_engine(self, emulator_id: str) -> None:
        """Os três operacionais são AppImage: o roteamento não pode desviá-los."""
        from steamzero.adapters.registry import AdapterRegistry as _Registry

        route = lifecycle.route_for(_Registry.bundled().get(emulator_id))
        assert route.executor == "engine"
