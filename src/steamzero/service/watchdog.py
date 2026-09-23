# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Watchdog systemd do daemon (SZ-OP-06).

Protocolo sd_notify mínimo, sem dependência externa: datagrama AF_UNIX para
``NOTIFY_SOCKET``. O ping ``WATCHDOG=1`` só é enviado enquanto todas as
verificações de liveness passam; um reconciliador morto faz o systemd reiniciar
o serviço (``Restart=on-failure``) em vez de mascarar a degradação.
"""

from __future__ import annotations

import os
import socket
import threading
from collections.abc import Callable, Mapping

Liveness = Callable[[], bool]


def notify(message: str, environ: Mapping[str, str] | None = None) -> bool:
    """Envia ``message`` ao systemd; retorna False quando não há NOTIFY_SOCKET."""
    env = os.environ if environ is None else environ
    address = env.get("NOTIFY_SOCKET", "")
    if not address or not (address.startswith("/") or address.startswith("@")):
        return False
    target = "\0" + address[1:] if address.startswith("@") else address
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
        sock.sendto(message.encode("utf-8"), target)
    return True


def watchdog_interval(environ: Mapping[str, str] | None = None) -> float | None:
    """Metade de WATCHDOG_USEC, em segundos; None quando o watchdog não é nosso."""
    env = os.environ if environ is None else environ
    usec = env.get("WATCHDOG_USEC")
    pid = env.get("WATCHDOG_PID")
    if not usec or (pid and pid != str(os.getpid())):
        return None
    try:
        value = int(usec)
    except ValueError:
        return None
    return value / 2_000_000 if value > 0 else None


def run(
    stop: threading.Event,
    checks: list[Liveness],
    *,
    interval: float,
    send: Callable[[str], bool] = notify,
) -> None:
    """Pinga enquanto saudável; ao primeiro check falho para de pingar e reporta."""
    while not stop.wait(interval):
        if all(check() for check in checks):
            send("WATCHDOG=1")
        else:
            send("STATUS=liveness falhou; aguardando reinício pelo watchdog")
            return
