# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Watchdog systemd: sd_notify, intervalo e parada ao falhar liveness (SZ-OP-06)."""

from __future__ import annotations

import os
import socket
import threading
from pathlib import Path

from steamzero.service import watchdog


def test_notify_without_socket_is_noop() -> None:
    assert watchdog.notify("READY=1", {}) is False
    assert watchdog.notify("READY=1", {"NOTIFY_SOCKET": "relative"}) is False


def test_notify_sends_datagram(tmp_path: Path) -> None:
    path = tmp_path / "notify.sock"
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as server:
        server.bind(str(path))
        assert watchdog.notify("READY=1", {"NOTIFY_SOCKET": str(path)}) is True
        assert server.recv(64) == b"READY=1"


def test_interval_is_half_of_watchdog_usec() -> None:
    assert watchdog.watchdog_interval({"WATCHDOG_USEC": "30000000"}) == 15.0
    assert watchdog.watchdog_interval({}) is None
    assert watchdog.watchdog_interval({"WATCHDOG_USEC": "x"}) is None
    assert watchdog.watchdog_interval({"WATCHDOG_USEC": "0"}) is None
    other = {"WATCHDOG_USEC": "1000000", "WATCHDOG_PID": str(os.getpid() + 1)}
    assert watchdog.watchdog_interval(other) is None


def test_run_pings_while_healthy_and_stops_on_failure() -> None:
    sent: list[str] = []
    alive = iter([True, True, False])
    watchdog.run(threading.Event(), [lambda: next(alive)], interval=0.001, send=sent.append)
    assert sent[:2] == ["WATCHDOG=1", "WATCHDOG=1"]
    assert sent[2].startswith("STATUS=")
    assert len(sent) == 3


def test_run_exits_on_stop() -> None:
    stop = threading.Event()
    stop.set()
    sent: list[str] = []
    watchdog.run(stop, [lambda: True], interval=10, send=sent.append)
    assert sent == []
