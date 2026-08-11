#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Runner da auditoria visual UI: bridge real + captura de todas as telas.

Uso:
  .venv/bin/python tools/ui_audit_runner.py
  .venv/bin/python tools/ui_audit_runner.py --outdir docs/09-operations/evidence/ui-audit-YYYY-MM-DD
  .venv/bin/python tools/ui_audit_runner.py --offline   # só fixtures/fallback, sem bridge

Os PNGs ficam em ``outdir``. Um manifesto JSON resume contagens e metadados do host.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "tools" / "ui_audit_capture.qml"
QML_DIR = ROOT / "src" / "steamzero" / "ui" / "qml"


def _find_qml() -> str:
    for name in ("qml6", "qml"):
        found = shutil.which(name)
        if found:
            return found
    raise SystemExit("qml6/qml ausente; instale o runtime Qt/QML para capturar a UI")


def _default_outdir() -> Path:
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    return ROOT / "docs" / "09-operations" / "evidence" / f"{stamp}-ui-audit"


def _qml_env() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith(("QT_", "QML_"))}
    env.update(
        {
            "QT_QPA_PLATFORM": os.environ.get("QT_QPA_PLATFORM", "offscreen"),
            "QT_QUICK_BACKEND": "software",
            "QT_LOGGING_RULES": "*=false;qml=true;qt.qml.binding.removal.info=false",
            "QT_SCALE_FACTOR": "1",
            "LANG": "pt_BR.UTF-8",
            "LC_ALL": "pt_BR.UTF-8",
            "STEAMZERO_CLASS": "ui-audit",
        }
    )
    # Preserve display only when the operator asked for on-screen capture
    if env["QT_QPA_PLATFORM"] not in {"offscreen", "minimal"}:
        for key in ("DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR"):
            if key in os.environ:
                env[key] = os.environ[key]
    return env


def _start_bridge() -> tuple[Any, str, int]:
    """Sobe a mesma bridge efêmera do produto e devolve (server, token, port)."""
    sys.path.insert(0, str(ROOT / "src"))
    from steamzero.adapters.desktop_dashboard import DesktopDashboard
    from steamzero.adapters.desktop_kde import build_desktop_coordinator
    from steamzero.adapters.desktop_ui import DesktopControlServer
    from steamzero.core.state import StateStore

    store = StateStore()
    store.migrate()
    coordinator = build_desktop_coordinator(store)
    token = secrets.token_urlsafe(32)
    dashboard = DesktopDashboard()
    server = DesktopControlServer(coordinator, token, dashboard)
    server.timeout = 0.2
    port = int(server.server_port)

    def _serve() -> None:
        while not getattr(server, "_audit_stop", False):
            server.handle_request()

    thread = threading.Thread(target=_serve, name="ui-audit-bridge", daemon=True)
    thread.start()
    server._audit_thread = thread  # type: ignore[attr-defined]
    return server, token, port


def _stop_bridge(server: Any) -> None:
    server._audit_stop = True  # type: ignore[attr-defined]
    with contextlib.suppress(OSError):
        server.server_close()


def _collect_host_snapshot() -> dict[str, Any]:
    """Metadados read-only do host para o manifesto (não muta nada)."""
    snap: dict[str, Any] = {"generatedAt": datetime.now(UTC).isoformat()}
    try:
        sys.path.insert(0, str(ROOT / "src"))
        from steamzero import __version__

        snap["version"] = __version__
    except Exception as exc:
        snap["versionError"] = str(exc)

    for label, argv in (
        ("desktopStatus", [sys.executable, "-m", "steamzero", "desktop", "status", "--json"]),
        ("doctor", [sys.executable, "-m", "steamzero", "doctor", "--json"]),
    ):
        try:
            completed = subprocess.run(
                argv,
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
                env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
            )
            if completed.returncode == 0 and completed.stdout.strip():
                snap[label] = json.loads(completed.stdout)
            else:
                snap[label] = {"error": completed.stderr.strip() or completed.stdout.strip()[:400]}
        except Exception as exc:
            snap[label] = {"error": str(exc)}
    return snap


def _list_pngs(outdir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(outdir.glob("*.png")):
        rows.append(
            {
                "name": path.name,
                "bytes": path.stat().st_size,
                "path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
            }
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Captura auditoria visual da UI SteamZero")
    parser.add_argument(
        "--outdir",
        type=Path,
        default=None,
        help="Pasta de saída dos PNGs (default: docs/09-operations/evidence/YYYY-MM-DD-ui-audit)",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Não sobe a bridge; captura apenas fallbacks embutidos no QML",
    )
    parser.add_argument(
        "--on-screen",
        action="store_true",
        help="Usa o display real em vez de offscreen (ainda captura via grabToImage)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Timeout total do processo QML em segundos (default 300)",
    )
    args = parser.parse_args(argv)

    outdir = (args.outdir or _default_outdir()).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    qml = _find_qml()
    env = _qml_env()
    if args.on_screen:
        env["QT_QPA_PLATFORM"] = os.environ.get("QT_QPA_PLATFORM", "xcb")
        for key in ("DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR"):
            if key in os.environ:
                env[key] = os.environ[key]

    server = None
    cmd = [qml, str(HARNESS), "--", "--steamzero-outdir", str(outdir)]

    print(f"[ui-audit] outdir = {outdir}")
    print(f"[ui-audit] harness = {HARNESS}")
    print(f"[ui-audit] platform = {env.get('QT_QPA_PLATFORM')}")

    try:
        if not args.offline:
            print("[ui-audit] starting live DesktopControlServer bridge…")
            server, token, port = _start_bridge()
            cmd.extend(
                [
                    "--steamzero-api",
                    f"http://127.0.0.1:{port}",
                    "--steamzero-token",
                    token,
                ]
            )
            print(f"[ui-audit] bridge http://127.0.0.1:{port}")
            # Um tick para o servidor aceitar conexões
            time.sleep(0.3)
        else:
            print("[ui-audit] offline mode (fallback fixtures only)")

        started = time.monotonic()
        completed = subprocess.run(
            cmd,
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=args.timeout,
            check=False,
        )
        elapsed = time.monotonic() - started
        print(completed.stdout)
        if completed.stderr:
            print(completed.stderr, file=sys.stderr)

        pngs = _list_pngs(outdir)
        manifest = {
            "schemaVersion": 1,
            "kind": "steamzero-ui-audit",
            "generatedAt": datetime.now(UTC).isoformat(),
            "outdir": str(outdir),
            "mode": "offline" if args.offline else "live-bridge",
            "platform": env.get("QT_QPA_PLATFORM"),
            "qmlReturncode": completed.returncode,
            "elapsedSeconds": round(elapsed, 2),
            "captureCount": len(pngs),
            "captures": pngs,
            "host": _collect_host_snapshot(),
            "stdoutTail": completed.stdout[-4000:],
            "stderrTail": completed.stderr[-2000:] if completed.stderr else "",
        }
        manifest_path = outdir / "MANIFEST.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"[ui-audit] captures = {len(pngs)}")
        print(f"[ui-audit] manifest = {manifest_path}")

        if completed.returncode != 0:
            print(f"[ui-audit] QML exited {completed.returncode}", file=sys.stderr)
            return completed.returncode
        if not pngs:
            print("[ui-audit] nenhum PNG gerado", file=sys.stderr)
            return 2
        return 0
    except subprocess.TimeoutExpired:
        print(f"[ui-audit] timeout após {args.timeout}s", file=sys.stderr)
        return 3
    finally:
        if server is not None:
            _stop_bridge(server)


if __name__ == "__main__":
    raise SystemExit(main())
