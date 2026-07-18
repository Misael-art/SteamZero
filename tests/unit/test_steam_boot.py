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
    layout = steam_boot.BootLayout(
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
        boot_id=tmp_path / "proc" / "sys" / "kernel" / "random" / "boot_id",
        state=tmp_path / "var" / "lib" / "steamzero" / "gamemode-boot" / "state.json",
        requested=tmp_path / "var" / "lib" / "steamzero" / "gamemode-boot" / "requested.json",
        started=tmp_path / "home" / "misael" / ".local" / "state" / "steamzero" / "started.json",
        sddm_system_config_dir=tmp_path / "usr" / "lib" / "sddm" / "sddm.conf.d",
        sddm_etc_config_dir=tmp_path / "etc" / "sddm.conf.d",
        sddm_config_file=tmp_path / "etc" / "sddm.conf",
    )
    layout.boot_id.parent.mkdir(parents=True)
    layout.boot_id.write_text("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\n", encoding="utf-8")
    return layout


def _user(_name: str) -> SimpleNamespace:
    return SimpleNamespace(pw_uid=1000, pw_dir="/nonexistent")


def _install_session(layout: steam_boot.BootLayout) -> None:
    layout.session.parent.mkdir(parents=True)
    layout.session.write_text("[Desktop Entry]\n", encoding="utf-8")
    layout.config.parent.mkdir(parents=True)
    layout.config.write_text(f"{steam_boot._MANAGED}\nmisael\n", encoding="utf-8")


def test_prepare_ignores_foreign_markers(tmp_path: Path) -> None:
    """Só o marcador próprio ativa a sessão; marcadores alheios são boot normal."""
    layout = _layout(tmp_path)
    _install_session(layout)
    layout.sddm_config.parent.mkdir(parents=True, exist_ok=True)
    layout.sddm_config.write_text(f"{steam_boot._MANAGED}\n[Autologin]\n", encoding="utf-8")

    result = steam_boot.prepare(layout, cmdline="quiet phasezero.steamos=1", user_lookup=_user)

    assert result["state"] == "inactive"
    assert not layout.sddm_config.exists()


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


def test_prepare_refuses_broken_symlink_even_when_target_is_absent(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    layout.sddm_config.parent.mkdir(parents=True)
    layout.sddm_config.symlink_to(tmp_path / "missing-target")

    with pytest.raises(SteamZeroError, match="arquivo alheio"):
        steam_boot.prepare(layout, cmdline="quiet", user_lookup=_user)
    assert layout.sddm_config.is_symlink()


def test_prepare_accepts_native_marker_and_rejects_invalid_user(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    _install_session(layout)
    result = steam_boot.prepare(layout, cmdline="quiet steamzero.gamemode=1", user_lookup=_user)
    assert result["state"] == "selected"

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
    result = steam_boot.status(layout, user_lookup=_user)
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
        result = steam_boot.status(layout, user_lookup=_user)
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


def test_effective_sddm_session_dir_last_file_wins(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    layout.sddm_system_config_dir.mkdir(parents=True)
    (layout.sddm_system_config_dir / "10-default.conf").write_text(
        "[Wayland]\nSessionDir=/wrong/default\n", encoding="utf-8"
    )
    layout.sddm_etc_config_dir.mkdir(parents=True)
    (layout.sddm_etc_config_dir / "90-local.conf").write_text(
        "[Wayland]\nSessionDir=/wrong/local\n", encoding="utf-8"
    )
    layout.sddm_config_file.write_text(
        f"[Wayland]\nSessionDir={layout.session.parent}\n", encoding="utf-8"
    )

    assert steam_boot.effective_session_dirs(layout) == [layout.session.parent]
    assert steam_boot._session_is_visible(layout) is True


def test_prepare_rejects_session_outside_effective_sddm_dir(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    _install_session(layout)
    layout.sddm_config_file.parent.mkdir(parents=True, exist_ok=True)
    layout.sddm_config_file.write_text(
        "[Wayland]\nSessionDir=/usr/local/share/wayland-sessions\n", encoding="utf-8"
    )

    with pytest.raises(SteamZeroError, match="SessionDir efetivo"):
        steam_boot.prepare(layout, cmdline="steamzero.gamemode=1", user_lookup=_user)
    assert not layout.sddm_config.exists()


def test_three_failed_boots_trigger_backoff_and_manual_session_recovers(tmp_path: Path) -> None:
    """P0-3: 3 falhas -> backoff -> sessão manual -> recuperação completa."""
    layout = _layout(tmp_path)
    _install_session(layout)
    boot_ids = [
        "00000000-0000-0000-0000-000000000001",
        "00000000-0000-0000-0000-000000000002",
        "00000000-0000-0000-0000-000000000003",
        "00000000-0000-0000-0000-000000000004",
        "00000000-0000-0000-0000-000000000005",
    ]

    for boot_id in boot_ids[:3]:
        result = steam_boot.prepare(
            layout,
            cmdline="steamzero.gamemode=1",
            boot_id=boot_id,
            user_lookup=_user,
        )
        assert result["state"] == "selected"

    backed_off = steam_boot.prepare(
        layout,
        cmdline="steamzero.gamemode=1",
        boot_id=boot_ids[3],
        user_lookup=_user,
    )
    assert backed_off["state"] == "backoff"
    assert backed_off["consecutiveFailures"] == 3
    assert not layout.sddm_config.exists()
    assert steam_boot.status(layout, user_lookup=_user)["state"] == "backoff"

    steam_boot.mark_started(layout, boot_id=boot_ids[3], marker_path=layout.started)
    recovered = steam_boot.prepare(
        layout,
        cmdline="steamzero.gamemode=1",
        boot_id=boot_ids[4],
        user_lookup=_user,
    )
    assert recovered["state"] == "selected"
    assert recovered["consecutiveFailures"] == 0
    assert layout.sddm_config.is_file()


def test_prepare_is_idempotent_within_same_boot(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    _install_session(layout)
    first = "00000000-0000-0000-0000-000000000001"
    second = "00000000-0000-0000-0000-000000000002"
    steam_boot.prepare(layout, cmdline="steamzero.gamemode=1", boot_id=first, user_lookup=_user)
    once = steam_boot.prepare(
        layout, cmdline="steamzero.gamemode=1", boot_id=second, user_lookup=_user
    )
    twice = steam_boot.prepare(
        layout, cmdline="steamzero.gamemode=1", boot_id=second, user_lookup=_user
    )
    assert once["consecutiveFailures"] == 1
    assert twice["consecutiveFailures"] == 1


def test_explicit_recover_is_dependency_injected_and_ownership_safe(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    _install_session(layout)
    steam_boot._persist_state(
        layout,
        {
            **steam_boot._state_default(),
            "consecutiveFailures": 3,
            "backoff": True,
        },
    )
    steam_boot._write_owned_json(
        layout.requested, {"bootId": "00000000-0000-0000-0000-000000000001"}
    )
    steam_boot._write_owned_json(layout.started, {"bootId": "00000000-0000-0000-0000-000000000002"})

    result = steam_boot.recover(
        layout,
        user_lookup=_user,
        geteuid=lambda: 0,
    )
    assert result == {"state": "recovered", "backoff": False, "consecutiveFailures": 0}
    assert not layout.state.exists()
    assert not layout.requested.exists()
    assert not layout.started.exists()


def test_grub_entry_is_independent_and_preserves_current_boot_shape(tmp_path: Path) -> None:
    boot = tmp_path / "boot"
    boot.mkdir()
    (boot / "vmlinuz-6.18-x86_64").write_bytes(b"kernel")
    (boot / "initramfs-6.18-x86_64.img").write_bytes(b"initrd")
    (boot / "amd-ucode.img").write_bytes(b"ucode")
    script = steam_boot._grub_text(
        "BOOT_IMAGE=/@/boot/vmlinuz-6.18-x86_64 "
        "root=UUID=307f0ecc-3ad9-4619-893d-28454cad339a rw "
        "rootflags=subvol=/@ quiet splash phasezero.steamos=1",
        boot,
    )
    generated = subprocess.run(
        ["/usr/bin/bash"],
        input=script,
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    assert "SteamZero Game Mode" in generated
    assert "steamzero.gamemode=1" in generated
    assert "phasezero" not in generated.lower()
    assert "root=UUID=307f0ecc-3ad9-4619-893d-28454cad339a" in generated
    assert " UUID=307f0ecc-3ad9-4619-893d-28454cad339a " not in generated
    assert "/@/boot/amd-ucode.img" in generated
    assert "/@/boot/initramfs-6.18-x86_64.img" in generated


def test_same_grub_script_tracks_kernel_rename(tmp_path: Path) -> None:
    """P0-1: regenerar pelo mesmo script nunca congela o kernel da instalação."""
    boot = tmp_path / "boot"
    boot.mkdir()
    old_kernel = boot / "vmlinuz-6.18-old"
    old_initrd = boot / "initramfs-6.18-old.img"
    old_kernel.write_bytes(b"kernel")
    old_initrd.write_bytes(b"initrd")
    script = steam_boot._grub_text(
        "BOOT_IMAGE=/@/boot/vmlinuz-6.18-old "
        "root=UUID=307f0ecc-3ad9-4619-893d-28454cad339a rw rootflags=subvol=/@ quiet",
        boot,
    )

    first = subprocess.run(
        ["/usr/bin/bash"], input=script, capture_output=True, check=True, text=True
    ).stdout
    assert "/@/boot/vmlinuz-6.18-old" in first

    old_kernel.rename(boot / "vmlinuz-6.19-new")
    old_initrd.rename(boot / "initramfs-6.19-new.img")
    second = subprocess.run(
        ["/usr/bin/bash"], input=script, capture_output=True, check=True, text=True
    ).stdout
    assert "/@/boot/vmlinuz-6.19-new" in second
    assert "/@/boot/initramfs-6.19-new.img" in second
    assert "6.18-old" not in second


def test_enable_writes_owned_files_and_regenerates_grub(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    layout = _layout(tmp_path)
    _install_session(layout)
    layout.cmdline.parent.mkdir(parents=True, exist_ok=True)
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
        if argv[0].endswith("grub-mkconfig"):
            layout.grub_config.parent.mkdir(parents=True, exist_ok=True)
            layout.grub_config.write_text(
                "menuentry --id=steamzero-gamemode { linux /vmlinuz steamzero.gamemode=1 }\n",
                encoding="utf-8",
            )
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
    assert steam_boot.status(layout, user_lookup=_user)["configured"] is True


def test_enable_rolls_back_when_generated_grub_lacks_entry(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    _install_session(layout)
    layout.cmdline.parent.mkdir(parents=True, exist_ok=True)
    layout.cmdline.write_text(
        "BOOT_IMAGE=/@/boot/vmlinuz-test "
        "root=UUID=aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee rw rootflags=subvol=/@ quiet",
        encoding="utf-8",
    )
    layout.boot.mkdir(parents=True, exist_ok=True)
    (layout.boot / "vmlinuz-test").write_bytes(b"kernel")
    (layout.boot / "initramfs-test.img").write_bytes(b"initrd")
    layout.grub_config.parent.mkdir(parents=True, exist_ok=True)
    original_grub = b"menuentry 'Linux' {}\n"
    layout.grub_config.write_bytes(original_grub)
    original_config = layout.config.read_bytes()

    def runner(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if argv[0].endswith("grub-mkconfig"):
            layout.grub_config.write_text("menuentry 'Broken' {}\n", encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0, "", "")

    with pytest.raises(SteamZeroError, match="deveria estar presente"):
        steam_boot.enable(
            "misael",
            layout,
            runner=runner,
            which=lambda name: f"/usr/bin/{name}",
            user_lookup=_user,
            geteuid=lambda: 0,
        )

    assert layout.grub_config.read_bytes() == original_grub
    assert layout.config.read_bytes() == original_config
    assert not layout.unit.exists()
    assert not layout.grub_script.exists()


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
    steam_boot._write_owned_json(layout.state, {"consecutiveFailures": 2, "backoff": False})
    steam_boot._write_owned_json(
        layout.requested, {"bootId": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}
    )
    steam_boot._write_owned_json(layout.started, {"bootId": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"})
    calls: list[list[str]] = []

    def runner(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        if argv[0].endswith("grub-mkconfig"):
            layout.grub_config.parent.mkdir(parents=True, exist_ok=True)
            layout.grub_config.write_text("menuentry 'Linux' {}\n", encoding="utf-8")
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
    assert not layout.state.exists()
    assert not layout.requested.exists()
    assert not layout.started.exists()
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
    monkeypatch.setattr(steam_boot, "mark_started", lambda: {"state": "started"})
    monkeypatch.setattr(steam_boot, "recover", lambda: {"state": "recovered"})
    monkeypatch.setattr(steam_boot, "enable", lambda user: {"state": "enabled", "user": user})
    monkeypatch.setattr(steam_boot, "disable", lambda: {"state": "disabled"})
    for argv in (
        ["status"],
        ["prepare"],
        ["started"],
        ["recover"],
        ["enable", "--user", "misael"],
        ["disable"],
    ):
        assert steam_boot.main(argv) == 0
        assert '"ok": true' in capsys.readouterr().out

    monkeypatch.setattr(steam_boot, "status", lambda: (_ for _ in ()).throw(OSError("boom")))
    assert steam_boot.main(["status"]) == 1
    assert "boom" in capsys.readouterr().err
