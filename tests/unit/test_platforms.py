# SPDX-License-Identifier: GPL-3.0-or-later
"""Contrato e registry declarativo de plataformas (F5)."""

from __future__ import annotations

import copy
import json
from contextlib import suppress
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from steamzero.adapters.registry import AdapterRegistry
from steamzero.api import contracts
from steamzero.core.errors import SteamZeroError
from steamzero.domain.platforms import (
    PlatformRegistry,
    load_platform_manifest,
    platform_placeholder,
)

MANIFESTS = Path("src/steamzero/platform_manifests")
ASSETS = Path("src/steamzero/ui/assets")
QML = Path("src/steamzero/ui/qml")


def _raw(name: str) -> dict[str, Any]:
    value = json.loads((MANIFESTS / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_bundled_registry_covers_required_platforms_with_unique_artwork() -> None:
    registry = PlatformRegistry.bundled()
    manifests = registry.list()

    assert [manifest.id for manifest in manifests] == [
        "switch",
        "nintendo-handheld",
        "nes-famicom",
        "snes",
        "mega-drive",
        "arcade",
        "playstation",
        "geforce-now",
        "xbox-cloud-gaming",
        "amazon-luna",
        "nintendo-console",
        "master-system",
        "game-gear",
        "pc-engine-turbografx",
        "atari-classics",
        "neo-geo-pocket",
        "wonderswan",
        "msx",
        "zx-spectrum",
        "commodore-64",
        "amiga",
        "colecovision",
        "intellivision",
        "virtual-boy",
        "three-do",
        "sega-cd-32x",
        "nintendo-64",
        "playstation-2",
        "playstation-portable",
        "dreamcast",
        "nintendo-ds",
        "nintendo-3ds",
        "wii-u",
        "playstation-3",
        "xbox",
        "xbox-360",
    ]
    artwork = [manifest.artwork_asset for manifest in manifests]
    shared_artwork = {asset for asset in artwork if artwork.count(asset) > 1}
    assert shared_artwork == {"../assets/retroarch.svg"}
    assert all((ASSETS / Path(asset).name).is_file() for asset in artwork)
    adapter_ids = {manifest.id for manifest in AdapterRegistry.bundled().list()}
    referenced_adapters = {
        str(emulator["adapterId"])
        for manifest in manifests
        for emulator in manifest.emulators
        if emulator["adapterId"] is not None
    }
    assert referenced_adapters <= adapter_ids
    assert registry.get("switch").systems == ("switch",)
    assert "zip" in registry.get("switch").media["extensions"]
    with pytest.raises(SteamZeroError, match="plataforma desconhecida"):
        registry.get("missing")


def test_retroarch_group_one_is_fully_declarative() -> None:
    registry = PlatformRegistry.bundled()
    group_ids = [
        "master-system",
        "game-gear",
        "pc-engine-turbografx",
        "atari-classics",
        "neo-geo-pocket",
        "wonderswan",
        "msx",
        "zx-spectrum",
        "commodore-64",
        "amiga",
        "colecovision",
        "intellivision",
        "virtual-boy",
        "three-do",
        "sega-cd-32x",
        "nintendo-64",
    ]

    manifests = [registry.get(platform_id) for platform_id in group_ids]
    assert all(manifest.artwork_asset == "../assets/retroarch.svg" for manifest in manifests)
    assert all(
        [(emulator["id"], emulator["adapterId"]) for emulator in manifest.emulators]
        == [("retroarch", "retroarch")]
        for manifest in manifests
    )
    assert all(
        manifest.controls["profiles"] == ["retroarch-classic-gamepad"] for manifest in manifests
    )
    assert all(manifest.media["extensions"] for manifest in manifests)
    assert "sms" in registry.get("master-system").media["extensions"]
    assert "gg" in registry.get("game-gear").media["extensions"]
    assert "pce" in registry.get("pc-engine-turbografx").media["extensions"]
    assert "j64" in registry.get("atari-classics").media["extensions"]
    assert "z64" in registry.get("nintendo-64").media["extensions"]


def test_emulation_ui_has_no_switch_specific_routing_or_copy() -> None:
    source = "\n".join(
        (QML / name).read_text(encoding="utf-8") for name in ("Emulation.qml", "Main.qml")
    )

    assert "switch" not in source.casefold()


def test_manifests_publish_all_capability_dimensions_and_safe_cloud_hosts() -> None:
    manifests = PlatformRegistry.bundled().list()
    for manifest in manifests:
        assert manifest.capabilities
        assert manifest.areas
        assert manifest.media["artworkKinds"]
        assert manifest.controls["profiles"]
        assert manifest.timing["unknownFallback"] == "unknown-explicit"
        assert manifest.presets
        if manifest.kind == "cloud":
            assert manifest.cloud is not None
            assert manifest.cloud["launchUrl"].startswith("https://")
            assert manifest.emulators == ()
        else:
            assert manifest.cloud is None
            assert manifest.emulators

    assert PlatformRegistry.bundled().get("arcade").controls["specialized"] == [
        "trackball",
        "spinner",
        "light-gun",
        "twin-stick",
        "wheel",
        "paddle",
        "fight-stick",
    ]


def test_placeholder_is_contract_valid_and_actions_remain_disabled() -> None:
    manifest = PlatformRegistry.bundled().get("xbox-cloud-gaming")
    platform = platform_placeholder(manifest)
    payload = {
        "schemaVersion": 1,
        "truthState": "planned",
        "contextLabel": "Catálogo",
        "platforms": [platform],
    }

    contracts.validate(payload, "emulation-workspace-v1.schema.json")
    assert platform["cloud"]["allowedHosts"] == ["www.xbox.com"]
    assert platform["areas"][1]["id"] == "advanced"
    action = platform["areaData"]["advanced"]["primaryAction"]
    assert action["id"] == "cloud.launch"
    assert action["enabled"] is False
    assert action["reason"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda data: data["capabilities"].append(copy.deepcopy(data["capabilities"][0])),
        lambda data: data["areas"].append(copy.deepcopy(data["areas"][0])),
        lambda data: data["emulators"].append(copy.deepcopy(data["emulators"][0])),
        lambda data: data["presets"].append(copy.deepcopy(data["presets"][0])),
        lambda data: data["emulators"].append(
            {
                **copy.deepcopy(data["emulators"][0]),
                "id": "other",
            }
        ),
        lambda data: data["areas"][0].update({"capabilityId": "missing"}),
        lambda data: data["capabilities"][1].update(
            {"action": copy.deepcopy(data["capabilities"][0]["action"])}
        ),
    ],
)
def test_manifest_rejects_duplicate_or_dangling_references(mutate) -> None:  # type: ignore[no-untyped-def]
    data = _raw("01-switch.platform.json")
    mutate(data)
    with pytest.raises(SteamZeroError, match=r"duplicad|ausentes"):
        load_platform_manifest(data)


@pytest.mark.parametrize(
    "launch_url",
    [
        "http://play.geforcenow.com/",
        "https://evil.example/",
        "https://user@play.geforcenow.com/",
        "https://play.geforcenow.com:444/",
        "https://play.geforcenow.com:99999/",
    ],
)
def test_cloud_launch_url_fails_closed_outside_exact_https_allowlist(
    launch_url: str,
) -> None:
    data = _raw("08-geforce-now.platform.json")
    data["cloud"]["launchUrl"] = launch_url
    with pytest.raises(SteamZeroError, match="E-API-SCHEMA"):
        load_platform_manifest(data)


def test_kind_and_payload_cannot_cross_cloud_boundary() -> None:
    emulated = _raw("01-switch.platform.json")
    emulated["cloud"] = {
        "launchUrl": "https://play.geforcenow.com/",
        "allowedHosts": ["play.geforcenow.com"],
        "requiresSubscription": True,
    }
    with pytest.raises(SteamZeroError, match="não pode declarar cloud"):
        load_platform_manifest(emulated)

    cloud = _raw("08-geforce-now.platform.json")
    cloud["emulators"] = [
        {
            "id": "fake",
            "name": "Fake",
            "adapterId": None,
            "precedence": 1,
            "role": "primary",
        }
    ]
    with pytest.raises(SteamZeroError, match="não aceita emuladores"):
        load_platform_manifest(cloud)


def test_registry_rejects_duplicate_platform_ids() -> None:
    manifest = load_platform_manifest(_raw("01-switch.platform.json"))
    with pytest.raises(SteamZeroError, match="plataforma duplicada"):
        PlatformRegistry([manifest, manifest])


def test_bundled_registry_is_cached_per_process() -> None:
    # O snapshot compõe o registry repetidamente; o cache impede que os 36
    # manifestos sejam relidos e revalidados contra o schema a cada chamada.
    assert PlatformRegistry.bundled() is PlatformRegistry.bundled()


@settings(max_examples=50, deadline=None)
@given(
    st.dictionaries(
        st.text(max_size=24),
        st.one_of(
            st.none(),
            st.booleans(),
            st.integers(),
            st.text(max_size=80),
            st.lists(st.text(max_size=30), max_size=8),
        ),
        max_size=24,
    )
)
def test_manifest_parser_never_leaks_untyped_exception(data: dict[str, Any]) -> None:
    with suppress(SteamZeroError):
        load_platform_manifest(data)


class TestEachPlatformDeclaresItsOwnEmulators:
    """Regressao do que o operador viu na tela em 2026-08-12.

    A central de emulacao montava a lista de emuladores a partir do registro
    INTEIRO de adapters e a entregava ao workspace do Switch. Resultado: Dolphin
    (GameCube e Wii) e PPSSPP (PSP) apareciam sob Nintendo Switch, com o rotulo
    "Keys pendentes" — um requisito que so existe para o Switch.

    A relacao plataforma->emulador sempre esteve em `manifest.emulators`; o que
    faltava era alguem consulta-la.
    """

    def test_switch_declares_only_switch_emulators(self) -> None:
        registry = PlatformRegistry.bundled()
        assert registry.emulator_ids_for("switch") == ("eden", "citron", "ryubing")

    def test_emulators_of_other_platforms_are_not_claimed_by_switch(self) -> None:
        """A ascercao que pega o defeito.

        Conferir so a lista do Switch passaria mesmo com o vazamento, porque a
        lista correta continua sendo um subconjunto do registro inteiro. O que
        nao passa e exigir que emuladores de OUTRAS plataformas fiquem de fora.
        """
        registry = PlatformRegistry.bundled()
        switch = set(registry.emulator_ids_for("switch"))
        for foreign in ("dolphin", "ppsspp", "cemu", "rpcs3", "flycast", "azahar", "melonds"):
            assert foreign not in switch, f"{foreign} nao e emulador de Nintendo Switch"

    def test_a_multi_system_emulator_belongs_to_the_platforms_that_declare_it(self) -> None:
        """RetroArch e legitimamente compartilhado; o filtro nao pode exclui-lo."""
        registry = PlatformRegistry.bundled()
        assert "retroarch" in registry.emulator_ids_for("nes-famicom")
        assert "retroarch" in registry.emulator_ids_for("mega-drive")
        assert "retroarch" not in registry.emulator_ids_for("switch")

    def test_cloud_platforms_declare_no_emulator(self) -> None:
        """Vazio legitimo: nuvem nao emula. Nao pode virar erro."""
        registry = PlatformRegistry.bundled()
        for platform_id in ("geforce-now", "xbox-cloud-gaming", "amazon-luna"):
            assert registry.emulator_ids_for(platform_id) == ()

    def test_an_unknown_platform_raises_instead_of_answering_empty(self) -> None:
        """Vazio e indistinguivel de 'nuvem'; erro de id precisa doer."""
        registry = PlatformRegistry.bundled()
        with pytest.raises(SteamZeroError):
            registry.emulator_ids_for("plataforma-que-nao-existe")

    def test_every_declared_emulator_exists_in_the_adapter_registry(self) -> None:
        """Uma plataforma nao pode declarar adapter que nao existe.

        Sem isto, a plataforma fica permanentemente sem emulador utilizavel e a
        UI nao tem como dizer por que.
        """
        from steamzero.adapters.registry import AdapterRegistry

        adapters = {manifest.id for manifest in AdapterRegistry.bundled().list()}
        missing: dict[str, list[str]] = {}
        for manifest in PlatformRegistry.bundled().list():
            absent = [
                adapter_id
                for adapter_id in PlatformRegistry.bundled().emulator_ids_for(manifest.id)
                if adapter_id not in adapters
            ]
            if absent:
                missing[manifest.id] = absent
        assert missing == {}, f"plataformas declaram adapters inexistentes: {missing}"

    def test_every_declared_emulator_can_actually_be_rendered(self) -> None:
        """Declarar nao basta: a UI precisa conseguir desenhar a linha.

        `_EMULATOR_ROWS_ORDER` ordenava E filtrava. Dos 33 adapters com
        `presentation` no manifesto, 13 chegavam a tela. Entre os 20 de fora
        estavam `duckstation` e `pcsx2` — os UNICOS emuladores declarados por
        PlayStation e PlayStation 2. As duas plataformas ficavam sem emulador
        renderizavel para sempre, sem nada falhar.

        Conferir apenas "o adapter existe no registro" nao pega isso: eles
        existiam. O que faltava era apresentacao alcancavel.
        """
        from steamzero.adapters.emulation import _emulator_presentation

        presentable = set(_emulator_presentation(AdapterRegistry.bundled()))
        registry = PlatformRegistry.bundled()
        unreachable: dict[str, list[str]] = {}
        for manifest in registry.list():
            absent = [
                adapter_id
                for adapter_id in registry.emulator_ids_for(manifest.id)
                if adapter_id not in presentable
            ]
            if absent:
                unreachable[manifest.id] = absent
        assert unreachable == {}, (
            f"plataformas com emulador declarado e nao renderizavel: {unreachable}"
        )

    def test_the_declared_order_still_leads_the_presentation(self) -> None:
        """A ordem continua sendo contrato de UI — ela so deixou de excluir."""
        from steamzero.adapters.emulation import _EMULATOR_ROWS_ORDER, _emulator_presentation

        presented = list(_emulator_presentation(AdapterRegistry.bundled()))
        assert presented[: len(_EMULATOR_ROWS_ORDER)] == list(_EMULATOR_ROWS_ORDER)
