# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Regressões G30 — atribuição de recursos por classe de processo.

Exercita o probe com árvores /proc sintéticas (estat/status/smaps_rollup/
environ injetados), cobrindo os cenários obrigatórios do GAP-G30: UI +
emulador + filho, job de mídia isolado, PID reutilizado, processo encerrado,
permission denied, PSS indisponível com fallback explícito e zero command
line/caminho privado no snapshot e no pacote de suporte.
"""

from __future__ import annotations

import json
from typing import Any

from steamzero.adapters.diagnostics import _assert_sanitized, sanitize_payload
from steamzero.adapters.resource_probe import (
    ResourceProbe,
    lifecycle_from_state,
    parse_environ_class,
    parse_smaps_pss,
    parse_stat,
    parse_status_memory,
)


def _stat(
    pid: int,
    *,
    comm: str = "proc",
    state: str = "S",
    ppid: int = 1,
    starttime: int = 10,
) -> str:
    rest = [state, str(ppid)] + ["0"] * 17 + [str(starttime)]
    return f"{pid} ({comm}) " + " ".join(rest)


def _smaps(pss_kib: int) -> str:
    return f"Pss: {pss_kib} kB\nPrivate_Clean: 0 kB\n"


def _status(*, rss_kib: int = 0, swap_kib: int = 0) -> str:
    return f"VmRSS:\t {rss_kib} kB\nVmSwap:\t {swap_kib} kB\n"


def _environ(*markers: str) -> bytes:
    entries = ["PATH=/usr/bin"]
    entries.extend(markers)
    return "\0".join(entries).encode() + b"\0"


class ProcTree:
    """Árvore /proc sintética para injeção no ResourceProbe."""

    def __init__(
        self,
        entries: dict[int, dict[str, Any]],
        *,
        permission_paths: set[str] | None = None,
        deny_list: bool = False,
    ) -> None:
        self._entries = entries
        self._permission_paths = permission_paths or set()
        self._deny_list = deny_list

    def _entry(self, pid: int) -> dict[str, Any] | None:
        return self._entries.get(pid)

    def read_text(self, path: str) -> str | None:
        for blocked in self._permission_paths:
            if blocked in path:
                return None
        pid = self._pid_of(path)
        if pid is None:
            return ""
        entry = self._entry(pid)
        if entry is None:
            return ""
        return entry.get(path.split("/")[-1], {}).get("text", "")

    def read_bytes(self, path: str) -> bytes:
        for blocked in self._permission_paths:
            if blocked in path:
                return b""
        pid = self._pid_of(path)
        if pid is None:
            return b""
        entry = self._entry(pid)
        if entry is None:
            return b""
        return entry.get(path.split("/")[-1], {}).get("bytes", b"")

    def list_dir(self, path: str) -> list[str]:
        if self._deny_list:
            raise PermissionError(path)
        return [str(pid) for pid in sorted(self._entries)]

    @staticmethod
    def _pid_of(path: str) -> int | None:
        parts = path.strip("/").split("/")
        if len(parts) < 2:
            return None
        try:
            return int(parts[1])
        except ValueError:
            return None


def _tree_pid(pid: int, **files: Any) -> dict[int, dict[str, Any]]:
    payload: dict[str, dict[str, str | bytes]] = {
        "stat": {"text": _stat(pid)},
        "smaps_rollup": {"text": _smaps(0)},
        "status": {"text": _status()},
    }
    for name, value in files.items():
        if isinstance(value, bytes):
            payload[name] = {"bytes": value}
        elif name == "stat":
            payload[name] = {"text": value if isinstance(value, str) else _stat(pid, **value)}
        else:
            payload[name] = {"text": value}
    return {pid: payload}


def _probe(
    tree: ProcTree,
    *,
    getpid: int = 100,
    own_class: str | None = "ui",
    **kwargs: Any,
) -> ResourceProbe:
    return ResourceProbe(
        proc_root="/proc",
        read_text=tree.read_text,
        read_bytes=tree.read_bytes,
        list_dir=tree.list_dir,
        getpid=lambda: getpid,
        own_class=own_class,
        now=lambda: "2026-08-01T00:00:00+00:00",
        **kwargs,
    )


def _merge_trees(*trees: dict[int, dict[str, Any]]) -> dict[int, dict[str, Any]]:
    merged: dict[int, dict[str, Any]] = {}
    for tree in trees:
        merged.update(tree)
    return merged


def _class_row(snapshot: dict[str, Any], process_class: str) -> dict[str, Any]:
    return next(row for row in snapshot["classes"] if row["processClass"] == process_class)


def _proc(
    pid: int,
    *,
    ppid: int = 1,
    starttime: int = 10,
    comm: str = "proc",
    pss_kib: int = 0,
    swap_kib: int = 0,
    state: str = "S",
) -> dict[int, dict[str, Any]]:
    return _tree_pid(
        pid,
        stat=_stat(pid, comm=comm, state=state, ppid=ppid, starttime=starttime),
        smaps_rollup=_smaps(pss_kib),
        status=_status(swap_kib=swap_kib),
    )


class TestParsers:
    def test_parse_stat_extracts_identity_and_lifecycle(self) -> None:
        parsed = parse_stat(_stat(300, comm="yuzu main", state="R", ppid=299, starttime=777))
        assert parsed is not None
        assert parsed["pid"] == 300
        assert parsed["comm"] == "yuzu main"
        assert parsed["state"] == "R"
        assert parsed["ppid"] == 299
        assert parsed["starttime"] == 777

    def test_parse_stat_rejects_malformed(self) -> None:
        assert parse_stat("garbage") is None
        assert parse_stat("1 (comm)") is None

    def test_parse_smaps_pss(self) -> None:
        assert parse_smaps_pss("Pss: 512 kB\n") == 512 * 1024
        assert parse_smaps_pss("NoPss here") is None

    def test_parse_status_memory(self) -> None:
        rss, swap = parse_status_memory("VmRSS:  2048 kB\nVmSwap:  64 kB\n")
        assert rss == 2048 * 1024
        assert swap == 64 * 1024

    def test_parse_environ_class(self) -> None:
        assert parse_environ_class(_environ("STEAMZERO_CLASS=emulator")) == "emulator"
        assert parse_environ_class(_environ("STEAMZERO_CLASS=emulator", "OTHER=x")) == "emulator"
        assert parse_environ_class(_environ("OTHER=x")) is None

    def test_lifecycle_mapping(self) -> None:
        assert lifecycle_from_state("R") == "running"
        assert lifecycle_from_state("S") == "running"
        assert lifecycle_from_state("D") == "running"
        assert lifecycle_from_state("Z") == "zombie"
        assert lifecycle_from_state("T") == "stopped"
        assert lifecycle_from_state("?") == "unknown"


class TestClassification:
    def test_ui_daemon_emulator_child_and_unknown_are_attributed(self) -> None:
        tree = ProcTree(
            _merge_trees(
                _proc(100, comm="steamzero-desk", starttime=1, pss_kib=10240),
                _proc(200, starttime=2, pss_kib=20480),
                _proc(300, ppid=200, starttime=777, pss_kib=40960),
                _proc(301, ppid=300, starttime=778, pss_kib=5120),
                _proc(302, ppid=301, starttime=779, pss_kib=2560),
                _proc(400, starttime=4, pss_kib=1024),
            )
        )
        probe = _probe(
            tree,
            getpid=100,
            daemon_pid=lambda: 200,
            emulator_processes=lambda: [(300, 777)],
        )
        snapshot = probe.snapshot()
        assert snapshot["complete"] is True
        assert _class_row(snapshot, "ui")["processCount"] == 1
        assert _class_row(snapshot, "ui")["pssBytes"] == 10240 * 1024
        assert _class_row(snapshot, "daemon")["processCount"] == 1
        assert _class_row(snapshot, "daemon")["pssBytes"] == 20480 * 1024
        assert _class_row(snapshot, "emulator")["processCount"] == 1
        assert _class_row(snapshot, "emulator")["pssBytes"] == 40960 * 1024
        assert _class_row(snapshot, "emulator-child")["processCount"] == 2
        assert _class_row(snapshot, "emulator-child")["pssBytes"] == (5120 + 2560) * 1024
        assert _class_row(snapshot, "unknown")["processCount"] == 1
        assert _class_row(snapshot, "unknown")["pssBytes"] == 1024 * 1024
        totals = snapshot["totals"]
        assert totals["attributed"]["processCount"] == 5
        assert totals["attributed"]["pssBytes"] == (10240 + 20480 + 40960 + 5120 + 2560) * 1024
        assert totals["unattributable"]["processCount"] == 1
        assert totals["unattributable"]["pssBytes"] == 1024 * 1024
        processes = {row["pid"]: row for row in snapshot["processes"]}
        assert processes[301]["processClass"] == "emulator-child"
        assert processes[301]["evidence"] == "child-of-emulator"
        assert processes[300]["evidence"] == "identity-provider"
        assert processes[100]["processClass"] == "ui"
        assert processes[100]["evidence"] == "own-process"
        assert processes[200]["evidence"] == "daemon-pid"
        assert processes[400]["evidence"] == "unattributable"

    def test_media_job_is_isolated_from_daemon(self) -> None:
        tree = ProcTree(
            _merge_trees(
                _tree_pid(200, stat=_stat(200, ppid=1, starttime=2), smaps_rollup=_smaps(20480)),
                _tree_pid(500, stat=_stat(500, ppid=1, starttime=5), smaps_rollup=_smaps(8192)),
            )
        )
        probe = _probe(
            tree,
            getpid=100,
            daemon_pid=lambda: 200,
            media_job_processes=lambda: [(500, 5)],
        )
        snapshot = probe.snapshot()
        assert _class_row(snapshot, "media-job")["processCount"] == 1
        assert _class_row(snapshot, "media-job")["pssBytes"] == 8192 * 1024
        assert _class_row(snapshot, "daemon")["pssBytes"] == 20480 * 1024
        processes = {row["pid"]: row for row in snapshot["processes"]}
        assert processes[500]["evidence"] == "identity-provider"

    def test_media_job_via_environ_marker(self) -> None:
        tree = ProcTree(
            _tree_pid(
                600,
                stat=_stat(600, ppid=1, starttime=6),
                smaps_rollup=_smaps(4096),
                environ=_environ("STEAMZERO_CLASS=media-job"),
            )
        )
        probe = _probe(tree, getpid=100)
        snapshot = probe.snapshot()
        assert _class_row(snapshot, "media-job")["processCount"] == 1
        processes = {row["pid"]: row for row in snapshot["processes"]}
        assert processes[600]["evidence"] == "environ-marker"

    def test_emulator_marker_without_session(self) -> None:
        tree = ProcTree(
            _tree_pid(
                700,
                stat=_stat(700, ppid=1, starttime=7),
                smaps_rollup=_smaps(4096),
                environ=_environ("STEAMZERO_CLASS=emulator"),
            )
        )
        probe = _probe(tree, getpid=100)
        snapshot = probe.snapshot()
        assert _class_row(snapshot, "emulator")["processCount"] == 1
        processes = {row["pid"]: row for row in snapshot["processes"]}
        assert processes[700]["evidence"] == "environ-marker"


class TestIdentityIntegrity:
    def test_pid_reused_does_not_inherit_old_identity(self) -> None:
        tree = ProcTree(
            _tree_pid(300, stat=_stat(300, ppid=1, starttime=999), smaps_rollup=_smaps(1024))
        )
        probe = _probe(
            tree,
            getpid=100,
            emulator_processes=lambda: [(300, 777)],
        )
        snapshot = probe.snapshot()
        assert _class_row(snapshot, "emulator")["processCount"] == 0
        processes = {row["pid"]: row for row in snapshot["processes"]}
        assert processes[300]["processClass"] == "unknown"
        assert processes[300]["evidence"] == "identity-mismatch"

    def test_terminated_process_is_not_counted(self) -> None:
        tree = ProcTree(_tree_pid(100, stat=_stat(100, ppid=1, starttime=1)))
        probe = _probe(
            tree,
            getpid=100,
            emulator_processes=lambda: [(300, 777)],
        )
        snapshot = probe.snapshot()
        assert _class_row(snapshot, "emulator")["processCount"] == 0
        assert snapshot["complete"] is True

    def test_zombie_counts_in_lifecycle_but_not_memory(self) -> None:
        tree = ProcTree(_tree_pid(300, stat=_stat(300, state="Z", ppid=200, starttime=777)))
        probe = _probe(tree, getpid=100, emulator_processes=lambda: [(300, 777)])
        snapshot = probe.snapshot()
        emulator = _class_row(snapshot, "emulator")
        assert emulator["processCount"] == 1
        assert emulator["lifecycle"]["zombie"] == 1
        assert emulator["pssBytes"] == 0
        assert snapshot["totals"]["attributed"]["pssBytes"] == 0


class TestMemoryFallback:
    def test_permission_denied_yields_unknown_memory(self) -> None:
        tree = ProcTree(
            _tree_pid(300, stat=_stat(300, ppid=200, starttime=777)),
            permission_paths={"smaps_rollup"},
        )
        probe = _probe(tree, getpid=100, emulator_processes=lambda: [(300, 777)])
        snapshot = probe.snapshot()
        assert snapshot["complete"] is True
        process = next(row for row in snapshot["processes"] if row["pid"] == 300)
        assert process["metric"] == "unavailable"
        assert process["readFailure"] == "permission-denied"
        assert process["pssBytes"] is None
        emulator = _class_row(snapshot, "emulator")
        assert emulator["readFailures"]["permission-denied"] == 1

    def test_pss_unavailable_falls_back_to_rss_explicitly(self) -> None:
        tree = ProcTree(
            _tree_pid(
                300,
                stat=_stat(300, ppid=200, starttime=777),
                smaps_rollup="",
                status=_status(rss_kib=8192, swap_kib=256),
            )
        )
        probe = _probe(tree, getpid=100, emulator_processes=lambda: [(300, 777)])
        snapshot = probe.snapshot()
        process = next(row for row in snapshot["processes"] if row["pid"] == 300)
        assert process["metric"] == "rss-fallback"
        assert process["rssBytes"] == 8192 * 1024
        assert process["swapBytes"] == 256 * 1024
        assert process["readFailure"] is None
        assert _class_row(snapshot, "emulator")["memoryMetric"] == "rss-fallback"

    def test_swap_is_read_alongside_pss(self) -> None:
        tree = ProcTree(
            _tree_pid(
                300,
                stat=_stat(300, ppid=200, starttime=777),
                smaps_rollup=_smaps(4096),
                status=_status(rss_kib=8192, swap_kib=512),
            )
        )
        probe = _probe(tree, getpid=100, emulator_processes=lambda: [(300, 777)])
        snapshot = probe.snapshot()
        process = next(row for row in snapshot["processes"] if row["pid"] == 300)
        assert process["metric"] == "pss"
        assert process["pssBytes"] == 4096 * 1024
        assert process["swapBytes"] == 512 * 1024


class TestDegradation:
    def test_snapshot_available_when_procfs_is_unlistable(self) -> None:
        tree = ProcTree({}, deny_list=True)
        snapshot = _probe(tree, getpid=100).snapshot()
        assert snapshot["complete"] is False
        assert snapshot["reason"] == "proc-unavailable"
        assert snapshot["classes"] == []
        assert snapshot["processes"] == []

    def test_snapshot_marks_incomplete_on_partial_reads(self) -> None:
        tree = ProcTree(_tree_pid(300, stat=_stat(300, ppid=200, starttime=777)))
        tree._entries[300] = {"stat": {"text": ""}}
        probe = _probe(tree, getpid=100)
        snapshot = probe.snapshot()
        assert snapshot["complete"] is False
        assert snapshot["reason"] == "proc-incomplete"
        process = next(row for row in snapshot["processes"] if row["pid"] == 300)
        assert process["processClass"] == "unknown"
        assert process["readFailure"] == "proc-incomplete"


class TestPrivacy:
    def test_snapshot_never_contains_commandline_or_paths(self) -> None:
        tree = ProcTree(
            _merge_trees(
                _tree_pid(
                    300,
                    stat=_stat(300, ppid=200, starttime=777),
                    smaps_rollup=_smaps(4096),
                    environ=_environ(
                        "STEAMZERO_CLASS=emulator",
                        "STEAMZERO_ROM=/run/media/user/Deck/roms/Game.xci",
                    ),
                ),
                _tree_pid(400, stat=_stat(400, ppid=1, starttime=4), smaps_rollup=_smaps(1024)),
            )
        )
        probe = _probe(tree, getpid=100, emulator_processes=lambda: [(300, 777)])
        snapshot = probe.snapshot()
        text = json.dumps(snapshot, sort_keys=True)
        assert "cmdline" not in text
        assert "environ" not in text
        assert "/run/media" not in text
        assert ".xci" not in text
        assert "STEAMZERO_ROM" not in text
        assert "STEAMZERO_CLASS" not in text
        sanitized = sanitize_payload(snapshot)
        assert json.dumps(sanitized, sort_keys=True) == text
        _assert_sanitized(json.dumps(sanitized, sort_keys=True).encode())

    def test_comm_is_bounded_and_slash_free(self) -> None:
        stat = _stat(300, comm="/etc/passwd xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", ppid=1, starttime=1)
        tree = ProcTree(_tree_pid(300, stat=stat, smaps_rollup=_smaps(1024)))
        probe = _probe(tree, getpid=100)
        snapshot = probe.snapshot()
        process = next(row for row in snapshot["processes"] if row["pid"] == 300)
        assert process["comm"] is not None
        assert "/" not in process["comm"]
        assert len(process["comm"]) <= 64


class TestProbeContract:
    def test_probe_never_raises_on_arbitrary_failures(self) -> None:
        def broken_read(path: str) -> str | None:
            raise RuntimeError(path)

        probe = ResourceProbe(
            proc_root="/proc",
            read_text=broken_read,
            read_bytes=lambda path: b"",
            list_dir=lambda path: ["1", "2", "3"],
            getpid=lambda: 100,
            now=lambda: "2026-08-01T00:00:00+00:00",
        )
        snapshot = probe.snapshot()
        assert snapshot["complete"] is False
        assert snapshot["reason"] == "probe-failed"

    def test_identity_provider_failures_do_not_poison_snapshot(self) -> None:
        tree = ProcTree(_proc(300, starttime=7, pss_kib=1024))

        def broken_provider() -> list[tuple[int, int | None]]:
            raise RuntimeError("store locked")

        probe = _probe(tree, getpid=100, emulator_processes=broken_provider)
        snapshot = probe.snapshot()
        assert snapshot["complete"] is True
        assert _class_row(snapshot, "unknown")["processCount"] == 1
