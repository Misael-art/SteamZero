#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Measure the installed AURA Launcher window on a real Wayland session.

The launcher enables this probe only through a loopback report URL.  The QML
surface reports render-loop intervals and time to its first frame; this tool
adds the installed process' RSS and DRM fdinfo VRAM peak, then terminates the
probe-owned launcher.  It never uses the offscreen QML test harness.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from theme_perf_probe import _peak_vram_kb, summarize


class _Collector(HTTPServer):
    payload: dict[str, Any] | None = None


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        try:
            parsed = json.loads(self.rfile.read(length).decode("utf-8", "replace"))
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict) and isinstance(self.server, _Collector):
            self.server.payload = parsed
        self.send_response(204)
        self.end_headers()

    def log_message(self, *_args: Any) -> None:
        pass


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _descendants(pid: int) -> set[int]:
    result: set[int] = set()
    pending = [pid]
    while pending:
        parent = pending.pop()
        children_path = Path(f"/proc/{parent}/task/{parent}/children")
        try:
            children = [int(value) for value in children_path.read_text().split()]
        except (OSError, ValueError):
            continue
        for child in children:
            if child not in result:
                result.add(child)
                pending.append(child)
    return result


def _qml_pid(launcher_pid: int) -> int | None:
    for pid in _descendants(launcher_pid):
        try:
            command = Path(f"/proc/{pid}/comm").read_text().strip()
        except OSError:
            continue
        if command in {"qml6", "qml"}:
            return pid
    return None


def _rss_kb(pid: int) -> int | None:
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        return None
    return None


def measure(launcher: Path, *, backend: str, timeout: float) -> dict[str, Any]:
    port = _free_port()
    server = _Collector(("127.0.0.1", port), _Handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    environment = {
        **os.environ,
        "QT_QPA_PLATFORM": "wayland",
        "QT_QUICK_BACKEND": backend,
        "STEAMZERO_QT_QUICK_BACKEND": backend,
        "STEAMZERO_PERF_REPORT_URL": f"http://127.0.0.1:{port}/report",
    }
    process = subprocess.Popen(  # nosemgrep: dangerous-subprocess-use-audit
        [str(launcher)],
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    stop = threading.Event()
    peak_rss = 0
    peak_vram: int | None = None

    def sample() -> None:
        nonlocal peak_rss, peak_vram
        deadline = time.monotonic() + timeout + 5
        while not stop.is_set() and time.monotonic() < deadline:
            pid = _qml_pid(process.pid)
            if pid is not None:
                rss = _rss_kb(pid)
                if rss is not None:
                    peak_rss = max(peak_rss, rss)
                vram = _peak_vram_kb(pid)
                if vram is not None:
                    peak_vram = max(peak_vram or 0, vram)
            time.sleep(0.1)

    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    try:
        deadline = time.monotonic() + timeout
        while server.payload is None and time.monotonic() < deadline:
            time.sleep(0.05)
        if server.payload is None:
            raise RuntimeError(
                "Launcher não publicou a medição; verifique a release e a sessão Wayland"
            )
        samples = [float(value) for value in server.payload.get("samples", [])]
        if not samples:
            raise RuntimeError("Launcher publicou zero amostras de frame time")
        summary = summarize(samples).to_dict()
        return {
            "schemaVersion": 1,
            "launcher": str(launcher),
            "backend": backend,
            "surface": server.payload.get("surface"),
            "startupMs": server.payload.get("startupMs"),
            "frameTime": summary,
            "peakRssKb": peak_rss,
            "peakVramKb": peak_vram,
            "vramMeasured": peak_vram is not None,
            "vramMethod": "drm fdinfo do processo, agrupado por drm-client-id"
            if peak_vram is not None
            else None,
            "note": (
                "frameTime é do render loop FrameAnimation, não de frames "
                "apresentados pelo compositor."
            ),
        }
    finally:
        stop.set()
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        sampler.join(timeout=5)
        server.shutdown()
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--launcher", type=Path, default=Path("/usr/local/bin/steamzero-launcher"))
    parser.add_argument("--backend", choices=("opengl", "software"), default="opengl")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        raise SystemExit("a sonda do Launcher exige uma sessão Wayland real")
    launcher = args.launcher.expanduser().resolve()
    if not launcher.is_file():
        raise SystemExit(f"launcher ausente: {launcher}")
    report = measure(launcher, backend=args.backend, timeout=args.timeout)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out is not None:
        args.out.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
