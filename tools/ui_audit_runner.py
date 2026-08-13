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
import hashlib
import json
import os
import re
import secrets
import shutil
import signal
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

#: O pacote não publica ``__main__``; ``python -m steamzero`` sempre falhou com
#: "is a package and cannot be directly executed" e enchia o manifesto de erro
#: em vez de status. O módulo abaixo é a entrada realmente suportada — a mesma
#: que ``[project.scripts] steamzero`` resolve.
CLI_MODULE = "steamzero.cli.main"

#: Warnings nascidos fora do nosso QML (estilo Breeze/KDE, plugins do Qt). São
#: registrados à parte em vez de silenciados por regra global: a auditoria
#: precisa ver os nossos, e esconder os alheios com ``QT_LOGGING_RULES`` também
#: escondia os nossos.
_EXTERNAL_WARNING_MARKERS = (
    "/usr/lib/qt6/qml/",
    "/usr/lib64/qt6/qml/",
    "org.kde.",
    "Breeze",
    "qrc:/qt-project.org/",
    "file:///usr/",
)


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
            # Nada de regra global: a auditoria existe para VER os warnings.
            # A separação entre os nossos e os do Breeze é feita na leitura.
            "QT_LOGGING_RULES": "",
            "QT_FORCE_STDERR_LOGGING": "1",
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


def cli_argv(*arguments: str) -> list[str]:
    """Argv da CLI do SteamZero pela entrada que o pacote realmente publica."""
    return [sys.executable, "-m", CLI_MODULE, *arguments]


def _git(*args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=20, check=False
        )
    except Exception:
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


def _repository_context() -> dict[str, Any]:
    """Commit e branch da árvore que gerou a evidência.

    Sem isto o manifesto não diz de qual código a captura saiu, e um PNG antigo
    é indistinguível de um novo.
    """
    return {
        "commit": _git("rev-parse", "HEAD"),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "describe": _git("describe", "--tags", "--always", "--dirty"),
        "clean": _git("status", "--porcelain") == "",
    }


def _process_status(returncode: int) -> dict[str, Any]:
    """Traduz o retorno do processo QML, inclusive morte por sinal."""
    if returncode == 0:
        return {"outcome": "ok", "returncode": 0, "signal": None}
    if returncode < 0:
        number = -returncode
        try:
            name = signal.Signals(number).name
        except ValueError:
            name = f"SIG{number}"
        return {
            "outcome": "crashed",
            "returncode": returncode,
            "signal": name,
            "detail": f"processo QML morreu com {name}; a captura não terminou por conta própria",
        }
    return {"outcome": "failed", "returncode": returncode, "signal": None}


_WARNING_LINE = re.compile(r"\b(warning|error|Binding loop|TypeError|ReferenceError)\b", re.I)


def _classify_warnings(stderr: str) -> dict[str, Any]:
    """Separa o que o nosso QML emitiu do que veio do estilo/plugins do host."""
    own: list[str] = []
    external: list[str] = []
    for line in stderr.splitlines():
        if not line.strip() or not _WARNING_LINE.search(line):
            continue
        if any(marker in line for marker in _EXTERNAL_WARNING_MARKERS):
            external.append(line)
        else:
            own.append(line)
    return {
        "own": own,
        "ownCount": len(own),
        "external": external,
        "externalCount": len(external),
        "note": (
            "own = originado no QML do SteamZero; external = estilo Breeze/KDE e "
            "plugins do Qt, registrados sem silenciamento global."
        ),
    }


def _parse_capture_records(output: str) -> list[dict[str, Any]]:
    """Lê os registros AUDIT-META emitidos pelo harness (um JSON por captura).

    Recebe stdout e stderr juntos: com ``QT_FORCE_STDERR_LOGGING`` o
    ``console.log`` do QML sai por stderr, e ler só stdout devolvia zero
    registro para 55 capturas.
    """
    records: list[dict[str, Any]] = []
    for line in output.splitlines():
        marker = line.find("AUDIT-META ")
        if marker < 0:
            continue
        with contextlib.suppress(json.JSONDecodeError):
            records.append(json.loads(line[marker + len("AUDIT-META ") :]))
    return records


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
        ("desktopStatus", cli_argv("desktop", "status", "--json")),
        ("doctor", cli_argv("doctor", "--json")),
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _list_pngs(outdir: Path, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cada PNG com hash e o contexto que o harness declarou ao capturá-lo.

    O hash é o que permite dizer "antes" e "depois" sem depender do nome do
    arquivo nem da data de modificação.
    """
    by_name = {str(record.get("name", "")): record for record in records}
    rows: list[dict[str, Any]] = []
    for path in sorted(outdir.glob("*.png")):
        record = by_name.get(path.stem, {})
        rows.append(
            {
                "name": path.name,
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
                "path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
                "viewport": record.get("viewport"),
                "scaleFactor": record.get("scaleFactor"),
                "themeId": record.get("themeId"),
                "themeVersion": record.get("themeVersion"),
                "highContrast": record.get("highContrast"),
                "reducedMotion": record.get("reducedMotion"),
                "dataOrigin": record.get("dataOrigin"),
                "section": record.get("section"),
            }
        )
    return rows


def _programmatic_checks(
    pngs: list[dict[str, Any]],
    records: list[dict[str, Any]],
    warnings: dict[str, Any],
    process: dict[str, Any],
) -> list[dict[str, Any]]:
    """Verificações que o manifesto pode afirmar sem inspeção humana.

    Cada uma responde a um critério de aceite: ou passa com o número medido, ou
    reprova dizendo o que faltou. Nada aqui é "provavelmente ok".
    """
    empty = [row["name"] for row in pngs if int(row["bytes"]) <= 0]
    untracked = [row["name"] for row in pngs if row.get("viewport") is None]
    return [
        {
            "id": "harness-terminou-sem-crash",
            "passed": process["outcome"] == "ok",
            "detail": process.get("detail", f"processo QML: {process['outcome']}"),
        },
        {
            "id": "toda-captura-tem-conteudo",
            "passed": not empty,
            "detail": f"{len(pngs)} PNG(s); vazios: {empty or 'nenhum'}",
        },
        {
            "id": "toda-captura-declara-contexto",
            "passed": not untracked,
            "detail": (
                f"{len(records)} registro(s) AUDIT-META para {len(pngs)} PNG(s); "
                f"sem contexto: {untracked or 'nenhum'}"
            ),
        },
        {
            "id": "qml-proprio-sem-warning",
            "passed": warnings["ownCount"] == 0,
            "detail": (
                f"{warnings['ownCount']} warning(s) do QML do SteamZero; "
                f"{warnings['externalCount']} de terceiros (Breeze/KDE, não silenciados)"
            ),
        },
    ]


def _guard_historical_evidence(outdir: Path, commit: str, overwrite: bool) -> None:
    """Recusa reescrever evidência de outro commit sem pedido explícito.

    Evidência de auditoria vale pela data e pelo commit; sobrescrever a pasta de
    11/08 com uma captura de hoje apaga a base de comparação.
    """
    manifest = outdir / "MANIFEST.json"
    if overwrite or not manifest.is_file():
        return
    try:
        previous = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    previous_commit = str((previous.get("repository") or {}).get("commit", ""))
    if previous_commit and commit and previous_commit != commit:
        raise SystemExit(
            f"{manifest} é evidência do commit {previous_commit[:12]}; a árvore atual é "
            f"{commit[:12]}. Escolha outro --outdir ou passe --overwrite se a intenção "
            "for mesmo substituir a evidência histórica."
        )


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
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Permite substituir evidência já gravada por outro commit no mesmo outdir",
    )
    args = parser.parse_args(argv)

    repository = _repository_context()
    outdir = (args.outdir or _default_outdir()).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    _guard_historical_evidence(outdir, repository["commit"], args.overwrite)

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

        records = _parse_capture_records(completed.stdout + "\n" + (completed.stderr or ""))
        pngs = _list_pngs(outdir, records)
        warnings = _classify_warnings(completed.stderr or "")
        process = _process_status(completed.returncode)
        manifest = {
            "schemaVersion": 2,
            "kind": "steamzero-ui-audit",
            "generatedAt": datetime.now(UTC).isoformat(),
            "outdir": str(outdir),
            "repository": repository,
            "mode": "offline" if args.offline else "live-bridge",
            "dataOrigin": "fixtures-embutidas-no-qml" if args.offline else "bridge-live",
            "platform": env.get("QT_QPA_PLATFORM"),
            "quickBackend": env.get("QT_QUICK_BACKEND"),
            "scaleFactor": env.get("QT_SCALE_FACTOR"),
            "loggingRules": env.get("QT_LOGGING_RULES"),
            "qmlProcess": process,
            "qmlReturncode": completed.returncode,
            "elapsedSeconds": round(elapsed, 2),
            "captureCount": len(pngs),
            "captures": pngs,
            "qmlWarnings": warnings,
            "checks": _programmatic_checks(pngs, records, warnings, process),
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
