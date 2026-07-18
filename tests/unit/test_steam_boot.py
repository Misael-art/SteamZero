# SPDX-License-Identifier: GPL-3.0-or-later
"""Boot direto SteamZero: seleção, migração e recuperação segura."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from steamzero.adapters import steam_boot
from steamzero.core.errors import SteamZeroError


def _layout(tmp_path: Path) -> steam_boot.BootLayout:
    return steam_boot.BootLayout(
        boot=tmp_path / "boot",
        config=tmp_path / "etc" / "steamzero" / "gamemode-user",
        sddm_config=tmp_path / "etc" / "sddm.conf.d" / "99-steamzero-gamemode.conf",
        session=tmp_path / "usr" / "share" / "wayland-sessions" / "steamzero-gamemode.desktop",
        unit=tmp_path
        / "usr"
        / "local"
        / "lib"
        / "systemd"
        / "system"
        / "steamzero-gamemode-boot.service",
        grub_script=tmp_path / "etc" / "grub.d" / "42_steamzero_gamemode",
        grub_config=tmp_path / "boot" / "grub" / "grub.cfg",
        cmdline=tmp_path / "proc" / "cmdline",
        legacy_sddm_config=tmp_path / "etc" / "sddm.conf.d" / "90-phasezero-steamos.conf",
    )


def _user(_name: str) -> SimpleNamespace:
    return SimpleNamespace(pw_uid=1000)


def _install_session(layout: steam_boot.BootLayout) -> None:
    layout.session.parent.mkdir(parents=True)
    layout.session.write_text("[Desktop Entry]\n", encoding="utf-8")
    layout.config.parent.mkdir(parents=True)
    layout.config.write_text(f"{steam_boot._MANAGED}\nmisael\n", encoding="utf-8")


def test_prepare_accepts_legacy_marker_but_selects_only_steamzero(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    _install_session(layout)
    layout.legacy_sddm_config.parent.mkdir(parents=True, exist_ok=True)
    layout.legacy_sddm_config.write_text("# PhaseZero managed\n", encoding="utf-8")

    result = steam_boot.prepare(layout, cmdline="quiet phasezero.steamos=1", user_lookup=_user)

    assert result["state"] == "selected"
    assert result["legacyMarker"] is True
    content = layout.sddm_config.read_text(encoding="utf-8")
    assert "Session=steamzero-gamemode.desktop" in content
    assert "Relogin=false" in content
    assert not layout.legacy_sddm_config.exists()


def test_prepare_missing_session_removes_stale_autologin(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    layout.config.parent.mkdir(parents=True)
    layout.config.write_text(f"{steam_boot._MANAGED}\nmisael\n", encoding="utf-8")
    layout.sddm_config.parent.mkdir(parents=True)
    layout.sddm_config.write_text(f"{steam_boot._MANAGED}\n[Autologin]\n", encoding="utf-8")

    with pytest.raises(SteamZeroError, match="retornar ao greeter"):
        steam_boot.prepare(layout, cmdline="steamzero.gamemode=1", user_lookup=_user)

    assert not layout.sddm_config.exists()


def test_normal_boot_removes_only_owned_sddm_file(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    layout.sddm_config.parent.mkdir(parents=True)
    layout.sddm_config.write_text(f"{steam_boot._MANAGED}\n[Autologin]\n", encoding="utf-8")
    assert steam_boot.prepare(layout, cmdline="quiet", user_lookup=_user)["state"] == "inactive"
    assert not layout.sddm_config.exists()

    layout.sddm_config.write_text("[Autologin]\nUser=someone\n", encoding="utf-8")
    with pytest.raises(SteamZeroError, match="arquivo alheio"):
        steam_boot.prepare(layout, cmdline="quiet", user_lookup=_user)


def test_prepare_accepts_native_marker_and_rejects_invalid_user(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    _install_session(layout)
    result = steam_boot.prepare(layout, cmdline="quiet steamzero.gamemode=1", user_lookup=_user)
    assert result["legacyMarker"] is False

    layout.config.write_text(f"{steam_boot._MANAGED}\nroot\n", encoding="utf-8")
    with pytest.raises(SteamZeroError, match="não interativo"):
        steam_boot.prepare(
            layout,
            cmdline="steamzero.gamemode=1",
            user_lookup=lambda _name: SimpleNamespace(pw_uid=0),
        )


@pytest.mark.parametrize(
    ("cmdline", "message"),
    (
        ("root=UUID=aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee rw", "kernel"),
        ("BOOT_IMAGE=/boot/vmlinuz-test root=/dev/sda rw", "UUID"),
    ),
)
def test_boot_spec_rejects_untrusted_current_boot(
    tmp_path: Path, cmdline: str, message: str
) -> None:
    with pytest.raises(SteamZeroError, match=message):
        steam_boot._boot_spec(cmdline, tmp_path)


def test_status_distinguishes_available_and_configured(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    assert steam_boot.status(layout)["state"] == "available"
    for path, content in (
        (layout.config, f"{steam_boot._MANAGED}\nmisael\n"),
        (layout.unit, f"{steam_boot._MANAGED}\n"),
        (layout.grub_script, f"{steam_boot._MANAGED}\n"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    result = steam_boot.status(layout)
    assert result["state"] == "ready"
    assert result["permissionDenied"] is False


def test_status_reports_permission_denied_not_unconfigured(tmp_path: Path) -> None:
    """Incidente 2026-07-18: EACCES era exibido como 'ativação não executada'."""
    if os.geteuid() == 0:
        pytest.skip("root ignora permissões de arquivo")
    layout = _layout(tmp_path)
    layout.config.parent.mkdir(parents=True)
    layout.config.write_text(f"{steam_boot._MANAGED}\nmisael\n", encoding="utf-8")
    layout.config.chmod(0o000)
    try:
        result = steam_boot.status(layout)
    finally:
        layout.config.chmod(0o600)
    assert result["state"] == "unknown"
    assert result["permissionDenied"] is True
    assert result["configured"] is False
    assert "não executada" not in result["reason"]


def test_default_session_lives_in_usr_share() -> None:
    """Incidente 2026-07-18: /etc/sddm.conf restringe SessionDir a /usr/share."""
    assert steam_boot.BootLayout().session == Path(
        "/usr/share/wayland-sessions/steamzero-gamemode.desktop"
    )


def test_grub_entry_is_independent_and_preserves_current_boot_shape(tmp_path: Path) -> None:
    boot = tmp_path / "boot"
    boot.mkdir()
    (boot / "vmlinuz-6.18-x86_64").write_bytes(b"kernel")
    (boot / "initramfs-6.18-x86_64.img").write_bytes(b"initrd")
    (boot / "amd-ucode.img").write_bytes(b"ucode")
    text = steam_boot._grub_text(
        "BOOT_IMAGE=/@/boot/vmlinuz-6.18-x86_64 "
        "root=UUID=307f0ecc-3ad9-4619-893d-28454cad339a rw "
        "rootflags=subvol=/@ quiet splash phasezero.steamos=1",
        boot,
    )
    assert "SteamZero Game Mode" in text
    assert "steamzero.gamemode=1" in text
    assert "phasezero" not in text.lower()
    assert "/@/boot/amd-ucode.img" in text
    assert "/@/boot/initramfs-6.18-x86_64.img" in text


def test_enable_writes_owned_files_and_regenerates_grub(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    layout = _layout(tmp_path)
    _install_session(layout)
    layout.cmdline.parent.mkdir(parents=True)
    layout.cmdline.write_text(
        "BOOT_IMAGE=/@/boot/vmlinuz-test root=UUID=aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee "
        "rw rootflags=subvol=/@ quiet",
        encoding="utf-8",
    )
    boot = layout.boot
    boot.mkdir(parents=True)
    (boot / "vmlinuz-test").write_bytes(b"kernel")
    (boot / "initramfs-test.img").write_bytes(b"initrd")
    calls: list[list[str]] = []

    def runner(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(os, "geteuid", lambda: 0)
    result = steam_boot.enable(
        "misael",
        layout,
        runner=runner,
        which=lambda name: f"/usr/bin/{name}",
        user_lookup=_user,
    )
    assert result["state"] == "enabled"
    assert layout.unit.is_file()
    assert layout.grub_script.stat().st_mode & 0o111
    assert ["/usr/bin/systemctl", "enable", layout.unit.name] in calls
    assert ["/usr/bin/grub-mkconfig", "-o", str(layout.grub_config)] in calls
    assert steam_boot.status(layout)["configured"] is True


def test_enable_rejects_non_root_missing_session_and_unmanaged_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    layout = _layout(tmp_path)
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    with pytest.raises(PermissionError, match="bigsudo"):
        steam_boot.enable("misael", layout, user_lookup=_user)

    monkeypatch.setattr(os, "geteuid", lambda: 0)
    with pytest.raises(SteamZeroError, match="não instalada"):
        steam_boot.enable("misael", layout, user_lookup=_user)

    _install_session(layout)
    layout.unit.parent.mkdir(parents=True)
    layout.unit.write_text("[Unit]\n", encoding="utf-8")
    with pytest.raises(SteamZeroError, match="não gerenciado"):
        steam_boot.enable("misael", layout, user_lookup=_user)


def test_disable_removes_only_owned_integration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    layout = _layout(tmp_path)
    for path, content in (
        (layout.config, f"{steam_boot._MANAGED}\nmisael\n"),
        (layout.unit, f"{steam_boot._MANAGED}\n[Unit]\n"),
        (layout.grub_script, f"{steam_boot._MANAGED}\n"),
        (layout.sddm_config, f"{steam_boot._MANAGED}\n[Autologin]\n"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    calls: list[list[str]] = []

    def runner(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(os, "geteuid", lambda: 0)
    assert (
        steam_boot.disable(
            layout,
            runner=runner,
            which=lambda name: f"/usr/bin/{name}",
        )["state"]
        == "disabled"
    )
    assert not layout.unit.exists()
    assert not layout.grub_script.exists()
    assert ["/usr/bin/grub-mkconfig", "-o", str(layout.grub_config)] in calls


def test_disable_requires_root_and_owned_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    layout = _layout(tmp_path)
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    with pytest.raises(PermissionError, match="bigsudo"):
        steam_boot.disable(layout)

    monkeypatch.setattr(os, "geteuid", lambda: 0)
    layout.unit.parent.mkdir(parents=True)
    layout.unit.write_text("[Unit]\n", encoding="utf-8")
    with pytest.raises(SteamZeroError, match="não gerenciado"):
        steam_boot.disable(layout)


def test_cli_routes_and_reports_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(steam_boot, "status", lambda: {"state": "ready"})
    monkeypatch.setattr(steam_boot, "prepare", lambda: {"state": "selected"})
    monkeypatch.setattr(steam_boot, "enable", lambda user: {"state": "enabled", "user": user})
    monkeypatch.setattr(steam_boot, "disable", lambda: {"state": "disabled"})
    for argv in (
        ["status"],
        ["prepare"],
        ["enable", "--user", "misael"],
        ["disable"],
    ):
        assert steam_boot.main(argv) == 0
        assert '"ok": true' in capsys.readouterr().out

    monkeypatch.setattr(steam_boot, "status", lambda: (_ for _ in ()).throw(OSError("boom")))
    assert steam_boot.main(["status"]) == 1
    assert "boom" in capsys.readouterr().err
