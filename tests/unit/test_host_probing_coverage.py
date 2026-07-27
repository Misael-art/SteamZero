# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Ramos que sondam o host, exercitados de forma determinística.

Estes caminhos executavam apenas na máquina de quem desenvolve — porque leem
``/sys/class/drm``, o ``$HOME`` real ou uma instalação de Steam existente — e por
isso a cobertura variava conforme o hardware e o software instalados, não
conforme o código. Aqui eles rodam contra fixtures, em qualquer host.
"""

from __future__ import annotations

from pathlib import Path

from steamzero.adapters import preservation


class TestHostDriverFingerprint:
    def _card(self, root: Path, name: str, body: str) -> None:
        device = root / name / "device"
        device.mkdir(parents=True)
        (device / "uevent").write_text(body, encoding="utf-8")

    def test_without_any_card(self, tmp_path: Path) -> None:
        """Runner headless não tem GPU; a impressão ainda precisa existir."""
        value = preservation.host_driver_fingerprint(drm_root=tmp_path)
        assert len(value) == 24

    def test_reads_declared_driver_fields(self, tmp_path: Path) -> None:
        self._card(
            tmp_path,
            "card0",
            "DRIVER=amdgpu\nPCI_ID=1002:1636\nPCI_SLOT_NAME=0000:04:00.0\nIRRELEVANTE=x\n",
        )
        with_card = preservation.host_driver_fingerprint(drm_root=tmp_path)
        assert with_card != preservation.host_driver_fingerprint(drm_root=tmp_path / "vazio")

    def test_ignores_unrelated_fields(self, tmp_path: Path) -> None:
        """Só DRIVER, PCI_ID e PCI_SLOT_NAME entram na impressão."""
        self._card(tmp_path, "card0", "DRIVER=amdgpu\n")
        base = preservation.host_driver_fingerprint(drm_root=tmp_path)
        (tmp_path / "card0" / "device" / "uevent").write_text(
            "DRIVER=amdgpu\nMODALIAS=pci:v1\nDEVTYPE=algo\n", encoding="utf-8"
        )
        assert preservation.host_driver_fingerprint(drm_root=tmp_path) == base

    def test_unreadable_card_is_skipped_not_fatal(self, tmp_path: Path) -> None:
        self._card(tmp_path, "card0", "DRIVER=amdgpu\n")
        self._card(tmp_path, "card1", "DRIVER=i915\n")
        (tmp_path / "card1" / "device" / "uevent").chmod(0o000)
        try:
            value = preservation.host_driver_fingerprint(drm_root=tmp_path)
        finally:
            (tmp_path / "card1" / "device" / "uevent").chmod(0o644)
        assert len(value) == 24

    def test_multiple_cards_are_ordered(self, tmp_path: Path) -> None:
        """Ordenação estável: a impressão não pode variar por ordem de leitura."""
        self._card(tmp_path, "card1", "DRIVER=i915\n")
        self._card(tmp_path, "card0", "DRIVER=amdgpu\n")
        assert preservation.host_driver_fingerprint(
            drm_root=tmp_path
        ) == preservation.host_driver_fingerprint(drm_root=tmp_path)


class TestDiscoverTargets:
    def _save_tree(self, home: Path, title_id: str) -> Path:
        root = home / ".local" / "share" / "eden" / "nand" / "user" / "save" / "0000"
        target = root / title_id
        target.mkdir(parents=True)
        (target / "dado.bin").write_bytes(b"conteudo")
        return target

    def test_finds_save_by_title_id(self, tmp_path: Path) -> None:
        expected = self._save_tree(tmp_path, "0100abcdef000000")
        found = preservation._discover_targets(
            "jogo-1",
            "0100ABCDEF000000",
            "eden",
            "save",
            emulator_version="1.0",
            home=tmp_path,
        )
        assert any(item.root == expected for item in found)

    def test_absent_title_yields_nothing(self, tmp_path: Path) -> None:
        self._save_tree(tmp_path, "0100abcdef000000")
        assert (
            preservation._discover_targets(
                "jogo-2",
                "0100000000000000",
                "eden",
                "save",
                emulator_version="1.0",
                home=tmp_path,
            )
            == []
        )

    def test_invalidated_directories_are_pruned(self, tmp_path: Path) -> None:
        base = tmp_path / ".local" / "share" / "eden" / "nand" / "user" / "save" / "0000"
        (base / ".invalidated" / "0100abcdef000000").mkdir(parents=True)
        found = preservation._discover_targets(
            "jogo-3",
            "0100abcdef000000",
            "eden",
            "save",
            emulator_version="1.0",
            home=tmp_path,
        )
        assert found == []

    def test_missing_home_is_not_fatal(self, tmp_path: Path) -> None:
        assert (
            preservation._discover_targets(
                "jogo-4",
                "0100abcdef000000",
                "eden",
                "save",
                emulator_version="1.0",
                home=tmp_path / "inexistente",
            )
            == []
        )


class TestSteamRunningProbe:
    """Detecção de Steam em execução, sem depender de Steam estar aberto."""

    def _proc(self, root: Path, pid: str, comm: str) -> None:
        entry = root / pid
        entry.mkdir(parents=True)
        (entry / "comm").write_text(f"{comm}\n", encoding="utf-8")

    def test_detects_steam(self, tmp_path: Path) -> None:
        from steamzero.adapters import steam_launch_options

        self._proc(tmp_path, "1", "systemd")
        self._proc(tmp_path, "4242", "steam")
        assert steam_launch_options._steam_running(proc_root=tmp_path) is True

    def test_detects_steamwebhelper(self, tmp_path: Path) -> None:
        from steamzero.adapters import steam_launch_options

        self._proc(tmp_path, "99", "steamwebhelper")
        assert steam_launch_options._steam_running(proc_root=tmp_path) is True

    def test_absent_steam_reports_false(self, tmp_path: Path) -> None:
        from steamzero.adapters import steam_launch_options

        self._proc(tmp_path, "1", "systemd")
        self._proc(tmp_path, "2", "bash")
        assert steam_launch_options._steam_running(proc_root=tmp_path) is False

    def test_non_numeric_entries_are_ignored(self, tmp_path: Path) -> None:
        from steamzero.adapters import steam_launch_options

        (tmp_path / "self").mkdir()
        (tmp_path / "meminfo").write_text("x", encoding="utf-8")
        assert steam_launch_options._steam_running(proc_root=tmp_path) is False

    def test_unreadable_comm_is_skipped(self, tmp_path: Path) -> None:
        from steamzero.adapters import steam_launch_options

        self._proc(tmp_path, "7", "steam")
        (tmp_path / "7" / "comm").chmod(0o000)
        try:
            result = steam_launch_options._steam_running(proc_root=tmp_path)
        finally:
            (tmp_path / "7" / "comm").chmod(0o644)
        assert result is False

    def test_missing_proc_is_not_fatal(self, tmp_path: Path) -> None:
        from steamzero.adapters import steam_launch_options

        assert steam_launch_options._steam_running(proc_root=tmp_path / "ausente") is False


class TestBatteryProbe:
    """Percentual de bateria sem depender de o host ter bateria."""

    def _battery(self, root: Path, name: str, capacity: str) -> None:
        entry = root / name
        entry.mkdir(parents=True)
        (entry / "capacity").write_text(capacity, encoding="utf-8")

    def test_reads_capacity(self, tmp_path: Path) -> None:
        from steamzero.adapters.steam_gameplay import SteamGameplayController

        self._battery(tmp_path, "BAT0", "77\n")
        assert SteamGameplayController._battery_percent(power_supply_root=tmp_path) == 77

    def test_absent_battery_returns_none(self, tmp_path: Path) -> None:
        from steamzero.adapters.steam_gameplay import SteamGameplayController

        assert SteamGameplayController._battery_percent(power_supply_root=tmp_path) is None

    def test_out_of_range_value_is_rejected(self, tmp_path: Path) -> None:
        """Valor fora de 0..100 é leitura suspeita, não percentual."""
        from steamzero.adapters.steam_gameplay import SteamGameplayController

        self._battery(tmp_path, "BAT0", "150\n")
        assert SteamGameplayController._battery_percent(power_supply_root=tmp_path) is None

    def test_non_numeric_value_is_skipped(self, tmp_path: Path) -> None:
        from steamzero.adapters.steam_gameplay import SteamGameplayController

        self._battery(tmp_path, "BAT0", "cheia\n")
        self._battery(tmp_path, "BAT1", "42\n")
        assert SteamGameplayController._battery_percent(power_supply_root=tmp_path) == 42


class TestSteamLibraryDiscovery:
    """libraryfolders.vdf lido de fixture, não da instalação real de Steam."""

    def _steam_root(self, tmp_path: Path, vdf: str) -> Path:
        root = tmp_path / "steam"
        (root / "steamapps").mkdir(parents=True)
        (root / "steamapps" / "libraryfolders.vdf").write_text(vdf, encoding="utf-8")
        return root

    def test_discovers_declared_library(self, tmp_path: Path) -> None:
        from steamzero.adapters.steam_gameplay import SteamGameplayController

        extra = tmp_path / "biblioteca-extra"
        extra.mkdir()
        root = self._steam_root(tmp_path, f'"path"\t\t"{extra}"\n')
        adapter = SteamGameplayController(roots=(root,))
        assert extra.resolve() in adapter._library_roots()

    def test_declared_but_absent_path_is_ignored(self, tmp_path: Path) -> None:
        """Biblioteca removida do disco não pode virar raiz válida."""
        from steamzero.adapters.steam_gameplay import SteamGameplayController

        root = self._steam_root(tmp_path, f'"path"\t\t"{tmp_path / "sumiu"}"\n')
        adapter = SteamGameplayController(roots=(root,))
        assert (tmp_path / "sumiu") not in adapter._library_roots()

    def test_missing_vdf_is_not_fatal(self, tmp_path: Path) -> None:

        root = tmp_path / "sem-vdf"
        root.mkdir()
        assert adapter_roots(root) == (root.resolve(),)

    def test_escaped_separators_are_decoded(self, tmp_path: Path) -> None:
        from steamzero.adapters.steam_gameplay import SteamGameplayController

        extra = tmp_path / "com-escape"
        extra.mkdir()
        escaped = str(extra).replace("\\", "\\\\")
        root = self._steam_root(tmp_path, f'"path"\t\t"{escaped}"\n')
        adapter = SteamGameplayController(roots=(root,))
        assert extra.resolve() in adapter._library_roots()


def adapter_roots(root: Path) -> tuple[Path, ...]:
    from steamzero.adapters.steam_gameplay import SteamGameplayController

    return SteamGameplayController(roots=(root,))._library_roots()


class TestBootOwnershipProbe:
    """_probe_owned distingue ausência de acesso negado.

    Incidente 2026-07-18: EACCES no diretório era exibido como "ativação não
    executada". Path.exists() esconde a diferença; estes ramos só executavam
    quando a permissão real do host os provocava.
    """

    def test_present_and_managed(self, tmp_path: Path) -> None:
        from steamzero.adapters import steam_boot

        target = tmp_path / "unit"
        target.write_text(f"{steam_boot._MANAGED}\n[Unit]\n", encoding="utf-8")
        present, denied = steam_boot._probe_owned(target)
        assert present is True
        assert denied is False

    def test_absent_is_not_denied(self, tmp_path: Path) -> None:
        from steamzero.adapters import steam_boot

        present, denied = steam_boot._probe_owned(tmp_path / "ausente")
        assert present is False
        assert denied is False

    def test_foreign_file_is_not_owned(self, tmp_path: Path) -> None:
        from steamzero.adapters import steam_boot

        target = tmp_path / "alheio"
        target.write_text("[Unit]\n", encoding="utf-8")
        present, denied = steam_boot._probe_owned(target)
        assert present is False
        assert denied is False

    def test_permission_denied_is_reported_separately(self, tmp_path: Path) -> None:
        """O ponto do incidente: negado não é o mesmo que ausente."""
        import os

        import pytest

        from steamzero.adapters import steam_boot

        if os.geteuid() == 0:
            pytest.skip("root ignora permissões de diretório")
        blocked = tmp_path / "bloqueado"
        blocked.mkdir()
        target = blocked / "unit"
        target.write_text(f"{steam_boot._MANAGED}\n", encoding="utf-8")
        blocked.chmod(0o000)
        try:
            present, denied = steam_boot._probe_owned(target)
        finally:
            blocked.chmod(0o755)
        assert present is False
        assert denied is True


class TestDockDetection:
    """Dock físico detectado por fixture, não pelo USB da máquina."""

    def _usb(self, root: Path, slot: str, product: str) -> None:
        entry = root / slot
        entry.mkdir(parents=True)
        (entry / "product").write_text(f"{product}\n", encoding="utf-8")

    def test_recognizes_dock(self, monkeypatch, tmp_path: Path) -> None:
        from steamzero.adapters import desktop_kde

        monkeypatch.delenv("STEAMZERO_DOCK_PRESENT", raising=False)
        self._usb(tmp_path, "1-1", "Steam Deck Docking Station")
        assert desktop_kde._physical_dock_present(usb_root=tmp_path) is True

    def test_recognizes_usb_c_hub(self, monkeypatch, tmp_path: Path) -> None:
        from steamzero.adapters import desktop_kde

        monkeypatch.delenv("STEAMZERO_DOCK_PRESENT", raising=False)
        self._usb(tmp_path, "2-1", "Generic USB-C Hub")
        assert desktop_kde._physical_dock_present(usb_root=tmp_path) is True

    def test_unrelated_device_is_not_a_dock(self, monkeypatch, tmp_path: Path) -> None:
        from steamzero.adapters import desktop_kde

        monkeypatch.delenv("STEAMZERO_DOCK_PRESENT", raising=False)
        self._usb(tmp_path, "3-1", "Wireless Mouse")
        assert desktop_kde._physical_dock_present(usb_root=tmp_path) is False

    def test_environment_override_wins(self, monkeypatch, tmp_path: Path) -> None:
        from steamzero.adapters import desktop_kde

        self._usb(tmp_path, "1-1", "Docking Station")
        monkeypatch.setenv("STEAMZERO_DOCK_PRESENT", "0")
        assert desktop_kde._physical_dock_present(usb_root=tmp_path) is False
        monkeypatch.setenv("STEAMZERO_DOCK_PRESENT", "1")
        assert desktop_kde._physical_dock_present(usb_root=tmp_path) is True

    def test_missing_usb_tree_is_not_fatal(self, monkeypatch, tmp_path: Path) -> None:
        from steamzero.adapters import desktop_kde

        monkeypatch.delenv("STEAMZERO_DOCK_PRESENT", raising=False)
        assert desktop_kde._physical_dock_present(usb_root=tmp_path / "ausente") is False
