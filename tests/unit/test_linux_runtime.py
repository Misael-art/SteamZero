# SPDX-License-Identifier: GPL-3.0-or-later
"""Adapters Linux read-only da sessão Steam com sysfs/procfs sintéticos."""

from __future__ import annotations

from pathlib import Path

from steamzero.adapters.linux_runtime import (
    LinuxDevicePort,
    LinuxSessionEnvironment,
    LinuxStoragePort,
    parse_mountinfo,
)


def _write(path: Path, value: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, bytes):
        path.write_bytes(value)
    else:
        path.write_text(value, encoding="utf-8")


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    sys_root = tmp_path / "sys"
    proc_root = tmp_path / "proc"
    dev_root = tmp_path / "dev"
    mountpoint = tmp_path / "run/media/deck/GAMES"
    mountpoint.mkdir(parents=True)

    dmi = sys_root / "class/dmi/id"
    _write(dmi / "sys_vendor", "Valve\n")
    _write(dmi / "product_name", "Jupiter\n")
    _write(dmi / "board_name", "Jupiter\n")
    _write(dmi / "board_vendor", "Valve\n")

    connector = sys_root / "class/drm/card1-eDP-1"
    _write(connector / "status", "connected\n")
    _write(connector / "enabled", "enabled\n")
    _write(connector / "modes", "800x1280@60\n800x1280@40\n")
    _write(connector / "edid", b"synthetic-edid")
    _write(sys_root / "class/drm/card1-DP-1/status", "disconnected\n")

    battery = sys_root / "class/power_supply/BAT1"
    _write(battery / "type", "Battery\n")
    _write(battery / "capacity", "73\n")
    _write(battery / "status", "Discharging\n")
    mains = sys_root / "class/power_supply/AC"
    _write(mains / "type", "Mains\n")
    _write(mains / "online", "0\n")

    _write(sys_root / "class/net/lo/operstate", "unknown\n")
    _write(sys_root / "class/net/wlan0/operstate", "up\n")
    _write(sys_root / "class/net/wlan0/carrier", "1\n")
    _write(sys_root / "class/block/mmcblk0/removable", "1\n")

    device = dev_root / "mmcblk0p1"
    _write(device, "")
    by_uuid = dev_root / "disk/by-uuid"
    by_uuid.mkdir(parents=True)
    (by_uuid / "ABCD-1234").symlink_to(Path("../../mmcblk0p1"))
    _write(
        proc_root / "self/mountinfo",
        f"42 31 179:1 / {mountpoint} rw,relatime - ext4 {device} rw\n",
    )
    return sys_root, proc_root, dev_root, mountpoint


def test_parse_mountinfo_decodes_escaped_mountpoint() -> None:
    mounts = parse_mountinfo(
        "42 31 8:1 / /run/media/My\\040Games rw - ext4 /dev/sda1 rw\ninvalid\n"
    )
    assert mounts == [
        {
            "majorMinor": "8:1",
            "mountpoint": "/run/media/My Games",
            "mountOptions": "rw",
            "fstype": "ext4",
            "source": "/dev/sda1",
        }
    ]


def test_linux_ports_observe_deck_and_uuid_volume(tmp_path: Path) -> None:
    sys_root, proc_root, dev_root, mountpoint = _fixture(tmp_path)
    device = LinuxDevicePort(sys_root=sys_root)
    assert device.read_dmi()["product_name"] == "jupiter"
    assert device.read_platform_signals() == {
        "internal_display_present": "true",
        "internal_connector": "eDP-1",
        "internal_mode": "800x1280@60",
        "internal_refresh_cap": "60",
    }

    volumes = LinuxStoragePort(
        sys_root=sys_root, proc_root=proc_root, dev_root=dev_root
    ).list_volumes()
    assert len(volumes) == 1
    assert volumes[0].uuid == "ABCD-1234"
    assert volumes[0].role == "microsd"
    assert volumes[0].mountpoint == str(mountpoint)
    assert volumes[0].capacity and volumes[0].free


def test_session_environment_is_read_only_and_degrades_missing_sources(tmp_path: Path) -> None:
    sys_root, proc_root, dev_root, _mountpoint = _fixture(tmp_path)
    snapshot = LinuxSessionEnvironment(
        sys_root=sys_root,
        proc_root=proc_root,
        dev_root=dev_root,
        environ={
            "XDG_SESSION_ID": "3",
            "XDG_SESSION_TYPE": "wayland",
            "XDG_CURRENT_DESKTOP": "KDE",
            "WAYLAND_DISPLAY": "wayland-0",
        },
    ).snapshot()
    assert snapshot["readOnly"] is True
    assert snapshot["device"]["evidenceCount"] == 4
    assert snapshot["session"]["type"] == "wayland"
    assert snapshot["power"] == {
        "onAC": False,
        "batteries": [{"name": "BAT1", "capacityPercent": 73, "status": "Discharging"}],
    }
    assert snapshot["network"]["online"] is True
    internal = next(row for row in snapshot["displays"] if row["internal"])
    assert internal["edidSha256"]

    empty = LinuxSessionEnvironment(
        sys_root=tmp_path / "missing-sys",
        proc_root=tmp_path / "missing-proc",
        dev_root=tmp_path / "missing-dev",
        environ={},
    ).snapshot()
    assert empty["session"]["type"] == "unknown"
    assert empty["displays"] == []
    assert empty["volumes"] == []
    assert empty["power"]["onAC"] is None
