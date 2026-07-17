# SPDX-License-Identifier: GPL-3.0-or-later
"""Observação Linux read-only para o ambiente da sessão Steam.

O adapter lê somente procfs/sysfs, mountinfo e links ``/dev/disk/by-uuid``.
Falhas parciais viram campos ``unknown``/listas vazias; nenhuma sonda impede o
doctor, a CLI ou o daemon de responder.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from steamzero.ports import VolumeInfo

_OCTAL_ESCAPE = re.compile(r"\\([0-7]{3})")
_SESSION_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
_UUID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_DRM_CONNECTOR = re.compile(r"^card\d+-(?P<name>.+)$")
_PSEUDO_FILESYSTEMS = frozenset(
    {
        "autofs",
        "bpf",
        "cgroup",
        "cgroup2",
        "configfs",
        "debugfs",
        "devpts",
        "devtmpfs",
        "fusectl",
        "hugetlbfs",
        "mqueue",
        "overlay",
        "proc",
        "pstore",
        "securityfs",
        "sysfs",
        "tmpfs",
        "tracefs",
    }
)

StatVFS = Callable[[str | bytes | os.PathLike[str] | os.PathLike[bytes]], os.statvfs_result]


def _read_text(path: Path, *, limit: int = 1 << 20) -> str:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
            return ""
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def _decode_mount_field(value: str) -> str:
    return _OCTAL_ESCAPE.sub(lambda match: chr(int(match.group(1), 8)), value)


def parse_mountinfo(text: str) -> list[dict[str, str]]:
    """Extrai somente os campos necessários de ``/proc/self/mountinfo``."""
    mounts: list[dict[str, str]] = []
    for line in text.splitlines():
        before, separator, after = line.partition(" - ")
        if not separator:
            continue
        left = before.split()
        right = after.split()
        if len(left) < 6 or len(right) < 2:
            continue
        mounts.append(
            {
                "majorMinor": left[2],
                "mountpoint": _decode_mount_field(left[4]),
                "mountOptions": left[5],
                "fstype": right[0],
                "source": _decode_mount_field(right[1]),
            }
        )
    return mounts


class LinuxDevicePort:
    """DMI e sinais independentes do painel usados para confirmar a classe Deck."""

    def __init__(self, *, sys_root: Path = Path("/sys")) -> None:
        self._sys = sys_root

    def read_dmi(self) -> dict[str, str]:
        base = self._sys / "class/dmi/id"
        return {
            key: _read_text(base / filename).lower()
            for key, filename in {
                "product_name": "product_name",
                "sys_vendor": "sys_vendor",
                "board_name": "board_name",
                "board_vendor": "board_vendor",
            }.items()
        }

    def read_platform_signals(self) -> dict[str, str]:
        connectors = _display_snapshot(self._sys)
        internal = [row for row in connectors if row["internal"] and row["connected"]]
        return {
            "internal_display_present": "true" if internal else "false",
            "internal_connector": str(internal[0]["name"]) if internal else "",
            "internal_mode": str(internal[0]["preferredMode"]) if internal else "",
            "internal_refresh_cap": _refresh_cap(internal[0]) if internal else "",
        }


class LinuxStoragePort:
    """Inventário vivo de volumes montados cuja identidade UUID é observável."""

    def __init__(
        self,
        *,
        proc_root: Path = Path("/proc"),
        sys_root: Path = Path("/sys"),
        dev_root: Path = Path("/dev"),
        statvfs: StatVFS = os.statvfs,
    ) -> None:
        self._proc = proc_root
        self._sys = sys_root
        self._dev = dev_root
        self._statvfs = statvfs

    def list_volumes(self) -> list[VolumeInfo]:
        mounts = parse_mountinfo(_read_text(self._proc / "self/mountinfo", limit=8 << 20))
        uuid_by_device = self._uuid_map()
        volumes: list[VolumeInfo] = []
        seen: set[str] = set()
        for mount in mounts:
            if mount["fstype"] in _PSEUDO_FILESYSTEMS:
                continue
            source = Path(mount["source"])
            try:
                resolved = str(source.resolve(strict=False))
            except OSError:
                resolved = str(source)
            uuid = uuid_by_device.get(resolved)
            if uuid is None or uuid in seen:
                continue
            seen.add(uuid)
            mountpoint = mount["mountpoint"]
            capacity, free = self._space(mountpoint)
            volumes.append(
                VolumeInfo(
                    uuid=uuid,
                    label=None,
                    fstype=mount["fstype"],
                    role=self._role(source, mountpoint),
                    mountpoint=mountpoint,
                    capacity=capacity,
                    free=free,
                )
            )
        return sorted(volumes, key=lambda volume: (volume.role, volume.uuid))

    def _uuid_map(self) -> dict[str, str]:
        directory = self._dev / "disk/by-uuid"
        try:
            entries = list(directory.iterdir())
        except OSError:
            return {}
        mapping: dict[str, str] = {}
        for entry in entries:
            if not entry.is_symlink() or not _UUID.fullmatch(entry.name):
                continue
            try:
                target = str(entry.resolve(strict=False))
            except OSError:
                continue
            mapping.setdefault(target, entry.name)
        return mapping

    def _space(self, mountpoint: str) -> tuple[int | None, int | None]:
        try:
            info = self._statvfs(mountpoint)
        except OSError:
            return None, None
        return info.f_blocks * info.f_frsize, info.f_bavail * info.f_frsize

    def _role(self, source: Path, mountpoint: str) -> str:
        name = source.name
        base = _base_block_device(name)
        removable = _read_text(self._sys / "class/block" / base / "removable") == "1"
        lowered_mount = mountpoint.casefold()
        # No Steam Deck o leitor SD interno pode anunciar removable=0; a
        # identidade mmcblk é o sinal estável, enquanto o SSD é NVMe.
        if name.startswith("mmcblk"):
            return "microsd"
        if removable or (name.startswith(("sd", "usb")) and "/run/media/" in lowered_mount):
            return "usb"
        return "internal"


class LinuxSessionEnvironment:
    """Read model agregado, seguro para CLI, daemon, UI e support bundle."""

    def __init__(
        self,
        *,
        sys_root: Path = Path("/sys"),
        proc_root: Path = Path("/proc"),
        dev_root: Path = Path("/dev"),
        environ: Mapping[str, str] | None = None,
        statvfs: StatVFS = os.statvfs,
    ) -> None:
        self._sys = sys_root
        self._proc = proc_root
        self._environment = dict(os.environ if environ is None else environ)
        self._device = LinuxDevicePort(sys_root=sys_root)
        self._storage = LinuxStoragePort(
            proc_root=proc_root,
            sys_root=sys_root,
            dev_root=dev_root,
            statvfs=statvfs,
        )

    def snapshot(self) -> dict[str, Any]:
        dmi = self._device.read_dmi()
        signals = self._device.read_platform_signals()
        displays = _display_snapshot(self._sys)
        volumes = self._storage.list_volumes()
        power = _power_snapshot(self._sys)
        network = _network_snapshot(self._sys)
        session = _session_snapshot(self._environment)
        return {
            "schemaVersion": 1,
            "observedAt": datetime.now(UTC).isoformat(),
            "readOnly": True,
            "device": {
                "dmi": dmi,
                "signals": signals,
                "evidenceCount": _device_evidence_count(dmi, signals),
            },
            "session": session,
            "power": power,
            "network": network,
            "displays": displays,
            "volumes": [
                {
                    "uuid": volume.uuid,
                    "label": volume.label,
                    "fstype": volume.fstype,
                    "role": volume.role,
                    "mountpoint": volume.mountpoint,
                    "capacity": volume.capacity,
                    "free": volume.free,
                }
                for volume in volumes
            ],
        }


def _display_snapshot(sys_root: Path) -> list[dict[str, Any]]:
    base = sys_root / "class/drm"
    try:
        entries = sorted(base.iterdir(), key=lambda path: path.name)
    except OSError:
        return []
    displays: list[dict[str, Any]] = []
    for entry in entries:
        match = _DRM_CONNECTOR.fullmatch(entry.name)
        if match is None:
            continue
        name = match.group("name")
        status = _read_text(entry / "status") or "unknown"
        modes = tuple(line for line in _read_text(entry / "modes").splitlines() if line)[:64]
        edid_digest = _edid_digest(entry / "edid")
        displays.append(
            {
                "name": name,
                "connected": status == "connected",
                "status": status,
                "enabled": _read_text(entry / "enabled") or "unknown",
                "internal": name.casefold().startswith(("edp", "lvds", "dsi")),
                "preferredMode": modes[0] if modes else None,
                "modes": list(modes),
                "edidSha256": edid_digest,
            }
        )
    return displays


def _edid_digest(path: Path) -> str | None:
    try:
        if path.is_symlink() or not path.is_file():
            return None
        content = path.read_bytes()
    except OSError:
        return None
    if not content or len(content) > 4096:
        return None
    return hashlib.sha256(content).hexdigest()


def _refresh_cap(display: dict[str, Any]) -> str:
    modes = display.get("modes")
    if not isinstance(modes, list):
        return ""
    refreshes: list[float] = []
    for mode in modes:
        if not isinstance(mode, str) or "@" not in mode:
            continue
        try:
            refreshes.append(float(mode.rsplit("@", 1)[1].removesuffix("Hz")))
        except ValueError:
            continue
    return f"{max(refreshes):g}" if refreshes else ""


def _power_snapshot(sys_root: Path) -> dict[str, Any]:
    base = sys_root / "class/power_supply"
    try:
        entries = list(base.iterdir())
    except OSError:
        entries = []
    batteries: list[dict[str, Any]] = []
    mains_online: list[bool] = []
    for entry in entries:
        kind = _read_text(entry / "type").casefold()
        if kind == "battery":
            capacity = _bounded_int(_read_text(entry / "capacity"), 0, 100)
            batteries.append(
                {
                    "name": entry.name,
                    "capacityPercent": capacity,
                    "status": _read_text(entry / "status") or "unknown",
                }
            )
        elif kind in {"mains", "usb", "usb_c"}:
            online = _read_text(entry / "online")
            if online in {"0", "1"}:
                mains_online.append(online == "1")
    on_ac: bool | None = any(mains_online) if mains_online else None
    if on_ac is None and batteries:
        statuses = {str(row["status"]).casefold() for row in batteries}
        if statuses & {"charging", "full", "not charging"}:
            on_ac = True
        elif "discharging" in statuses:
            on_ac = False
    return {"onAC": on_ac, "batteries": batteries}


def _network_snapshot(sys_root: Path) -> dict[str, Any]:
    base = sys_root / "class/net"
    try:
        entries = list(base.iterdir())
    except OSError:
        entries = []
    interfaces: list[dict[str, Any]] = []
    for entry in sorted(entries, key=lambda path: path.name):
        if entry.name == "lo":
            continue
        state = _read_text(entry / "operstate") or "unknown"
        carrier = _read_text(entry / "carrier")
        connected = state == "up" and carrier != "0"
        interfaces.append({"name": entry.name, "state": state, "connected": connected})
    return {"online": any(row["connected"] for row in interfaces), "interfaces": interfaces}


def _session_snapshot(environment: Mapping[str, str]) -> dict[str, Any]:
    session_id = environment.get("XDG_SESSION_ID", "")
    if not _SESSION_ID.fullmatch(session_id):
        session_id = ""
    return {
        "id": session_id or None,
        "type": environment.get("XDG_SESSION_TYPE", "unknown").casefold(),
        "desktop": environment.get("XDG_CURRENT_DESKTOP") or None,
        "waylandDisplay": environment.get("WAYLAND_DISPLAY") or None,
        "display": environment.get("DISPLAY") or None,
    }


def _device_evidence_count(dmi: Mapping[str, str], signals: Mapping[str, str]) -> int:
    evidence = 0
    if dmi.get("sys_vendor") == "valve":
        evidence += 1
    if dmi.get("product_name") in {"jupiter", "galileo"}:
        evidence += 1
    if dmi.get("board_name") in {"jupiter", "galileo"}:
        evidence += 1
    if signals.get("internal_display_present") == "true":
        evidence += 1
    return evidence


def _bounded_int(value: str, minimum: int, maximum: int) -> int | None:
    try:
        number = int(value)
    except ValueError:
        return None
    return number if minimum <= number <= maximum else None


def _base_block_device(name: str) -> str:
    if re.fullmatch(r"(?:nvme\d+n\d+|mmcblk\d+)p\d+", name):
        return name.rsplit("p", 1)[0]
    return re.sub(r"\d+$", "", name) or name
