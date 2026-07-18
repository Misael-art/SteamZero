# SPDX-License-Identifier: GPL-3.0-or-later
"""Preparação agnóstica do host e separação VM/hardware real."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from steamzero.adapters import host_preparation
from steamzero.core.errors import SteamZeroError


def _which(commands: dict[str, str]) -> host_preparation.Which:
    return commands.get


def test_snapshot_distinguishes_virtual_lab_from_real_deck(tmp_path: Path) -> None:
    os_release = tmp_path / "os-release"
    os_release.write_text('ID=biglinux\nPRETTY_NAME="BigLinux"\n', encoding="utf-8")
    kvm = tmp_path / "kvm"
    kvm.write_bytes(b"")
    status = host_preparation.snapshot(
        "deck-lcd",
        which=_which(
            {
                "pacman": "/usr/bin/pacman",
                "qemu-system-x86_64": "/usr/bin/qemu-system-x86_64",
                "virsh": "/usr/bin/virsh",
                "virt-install": "/usr/bin/virt-install",
                "swtpm": "/usr/bin/swtpm",
            }
        ),
        kvm=kvm,
        os_release=os_release,
    )
    assert status["state"] == "ready"
    assert status["officialDeck"] is True
    assert status["hardwareLab"]["state"] == "ready"
    assert status["hardwareLab"]["virtualGpuEquivalent"] is False
    assert status["virtualLab"]["gpu"] == "virtio"


def test_snapshot_autodetects_official_deck_from_dmi(tmp_path: Path) -> None:
    dmi = tmp_path / "dmi"
    dmi.mkdir()
    (dmi / "product_name").write_text("Jupiter\n", encoding="utf-8")
    (dmi / "sys_vendor").write_text("Valve\n", encoding="utf-8")
    (dmi / "board_name").write_text("Jupiter\n", encoding="utf-8")
    status = host_preparation.snapshot(
        which=lambda _name: None,
        kvm=tmp_path / "missing-kvm",
        os_release=tmp_path / "missing-os-release",
        dmi_root=dmi,
    )
    assert status["officialDeck"] is True
    assert status["hardwareLab"]["state"] == "ready"


def test_plan_uses_only_fixed_package_argv() -> None:
    result = host_preparation.plan(which=_which({"pacman": "/usr/bin/pacman"}))
    assert result["commands"] == [
        [
            "/usr/bin/pacman",
            "-S",
            "--needed",
            "--noconfirm",
            "qemu-desktop",
            "libvirt",
            "virt-install",
            "edk2-ovmf",
            "swtpm",
            "dnsmasq",
            "iptables-nft",
        ]
    ]
    assert result["confirmPhrase"] == "PREPARAR-VIRTUALIZACAO"


@pytest.mark.parametrize(
    ("manager", "expected"),
    (
        ("apt-get", ["/usr/bin/apt-get", "update"]),
        ("dnf", ["/usr/bin/dnf", "install", "-y"]),
    ),
)
def test_plan_supports_debian_and_fedora_families(manager: str, expected: list[str]) -> None:
    result = host_preparation.plan(which=_which({manager: f"/usr/bin/{manager}"}))
    assert result["commands"][0][: len(expected)] == expected


def test_plan_rejects_unknown_package_manager() -> None:
    with pytest.raises(SteamZeroError) as error:
        host_preparation.plan(which=lambda _name: None)
    assert error.value.code == "E-COMPONENT-DEGRADED"


def test_snapshot_reports_unknown_distro_and_missing_kvm(tmp_path: Path) -> None:
    status = host_preparation.snapshot(
        which=lambda _name: None,
        kvm=tmp_path / "missing-kvm",
        os_release=tmp_path / "missing-os-release",
    )
    assert status["state"] == "attention"
    assert status["distro"]["id"] == "unknown"
    assert status["distro"]["supported"] is False
    assert status["kvm"] == {"available": False, "accessible": False}


def test_apply_requires_exact_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    with pytest.raises(SteamZeroError) as error:
        host_preparation.apply(
            "misael",
            "yes",
            which=_which({"pacman": "/usr/bin/pacman"}),
        )
    assert error.value.code == "E-TX-CONFIRM-REQUIRED"


def test_apply_requires_root_and_interactive_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    with pytest.raises(PermissionError, match="bigsudo"):
        host_preparation.apply("misael", "PREPARAR-VIRTUALIZACAO")

    monkeypatch.setattr(os, "geteuid", lambda: 0)
    with pytest.raises(SteamZeroError, match="usuário inválido"):
        host_preparation.apply(
            "../../root",
            "PREPARAR-VIRTUALIZACAO",
            which=_which({"pacman": "/usr/bin/pacman"}),
        )


def test_apply_runs_packages_service_and_group_without_shell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def runner(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        host_preparation.pwd,
        "getpwnam",
        lambda name: SimpleNamespace(pw_uid=1000, pw_name=name),
    )
    monkeypatch.setattr(
        host_preparation.grp,
        "getgrnam",
        lambda _name: SimpleNamespace(gr_mem=[]),
    )
    commands = {
        "pacman": "/usr/bin/pacman",
        "systemctl": "/usr/bin/systemctl",
        "usermod": "/usr/sbin/usermod",
        "qemu-system-x86_64": "/usr/bin/qemu-system-x86_64",
        "virsh": "/usr/bin/virsh",
        "virt-install": "/usr/bin/virt-install",
        "swtpm": "/usr/bin/swtpm",
    }
    result = host_preparation.apply(
        "misael",
        "PREPARAR-VIRTUALIZACAO",
        which=_which(commands),
        runner=runner,
    )
    assert result["state"] == "prepared"
    assert calls[0][0:4] == ["/usr/bin/pacman", "-S", "--needed", "--noconfirm"]
    assert ["/usr/bin/systemctl", "enable", "--now", "libvirtd.service"] in calls
    assert ["/usr/sbin/usermod", "-aG", "libvirt", "misael"] in calls


def test_cli_routes_and_serializes_errors(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(host_preparation, "snapshot", lambda: {"state": "ready"})
    monkeypatch.setattr(host_preparation, "plan", lambda: {"profile": "validation-vm"})
    monkeypatch.setattr(
        host_preparation,
        "apply",
        lambda user, confirm: {"user": user, "confirm": confirm},
    )
    assert host_preparation.main(["status"]) == 0
    assert '"state": "ready"' in capsys.readouterr().out
    assert host_preparation.main(["plan"]) == 0
    assert "validation-vm" in capsys.readouterr().out
    assert (
        host_preparation.main(["apply", "--user", "misael", "--confirm", "PREPARAR-VIRTUALIZACAO"])
        == 0
    )
    assert '"user": "misael"' in capsys.readouterr().out

    monkeypatch.setattr(
        host_preparation, "snapshot", lambda: (_ for _ in ()).throw(OSError("probe"))
    )
    assert host_preparation.main(["status"]) == 1
    assert "probe" in capsys.readouterr().err
