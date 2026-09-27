#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Mede o custo real de ``GET /status`` da Central e atribui o tempo por bloco.

Existe porque UX-02 foi registrado como "14,26 s e 3,2 MB" a partir de uma
captura improvisada: sem um comando refazível, o número não sustenta nem um
"antes" nem um "depois". Este probe congela a metodologia — mesma bridge, mesmo
catálogo, mesmas repetições — para que a redução alegada em RC-01 seja
verificável por outra pessoa.

Decisões de segurança que moldaram o desenho:

* a bridge é exatamente a do produto (``DesktopControlServer`` sobre o estado do
  host), porque o custo que o usuário sente só existe lá; isolá-lo em fixtures
  mediria outra coisa;
* somente ``GET /status`` é chamado. Nenhuma rota de mutação é exercida, e o
  inquérito de estado antes/depois registra na evidência se a leitura escreveu
  alguma coisa;
* o relatório não carrega token nem conteúdo do acervo — só contagens, tamanhos
  e latências.

A atribuição por bloco substitui callables do read model por wrappers de tempo.
Isso é instrumentação de ferramenta, não produto: nada em ``src/steamzero``
conhece o probe.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import secrets
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import ui_audit_runner  # noqa: E402  (mesma harness de bridge da auditoria)
from steamzero.adapters import desktop_dashboard as dashboard_module  # noqa: E402
from steamzero.adapters.desktop_dashboard import DesktopDashboard  # noqa: E402
from steamzero.adapters.desktop_kde import build_desktop_coordinator  # noqa: E402
from steamzero.adapters.desktop_ui import DesktopControlServer  # noqa: E402
from steamzero.core import paths  # noqa: E402
from steamzero.core.state import StateStore  # noqa: E402
from steamzero.domain.desktop import ExperienceCoordinator  # noqa: E402

#: Blocos do read model cronometrados por caminho de atributo. Caminho de uma
#: parte é um callable injetado na própria dashboard; de duas partes é um método
#: do provedor injetado. ``unattributedMsPerQuery`` no relatório é o que sobra:
#: o tempo que nenhuma agregação sequencial declara.
INSTANCE_TARGETS: tuple[tuple[str, str], ...] = (
    ("_doctor_runner", "doctor"),
    ("_gameplay.snapshot", "steamGameplay"),
    ("_emulation.snapshot", "emulation"),
    ("_emulation.library_health", "libraryHealth"),
    ("_diagnostics.snapshot", "diagnostics"),
    ("_playtime.list", "playtime"),
    ("_collections.state", "collections"),
    ("_resources.snapshot", "resources"),
    ("_steam.rows", "steamRows"),
    ("_reduced_motion_probe", "probeReducedMotion"),
    ("_high_contrast_probe", "probeHighContrast"),
    ("_visual_scale_probe", "probeVisualScale"),
    ("_component_row", "componentRow"),
    ("_theme_state", "themeState"),
    ("_cast_orchestrator", "castOrchestrator"),
    ("_registry_factory", "registryFactory"),
)
MODULE_TARGETS: tuple[tuple[str, str], ...] = (
    ("handheld_ui_contracts", "uiContracts"),
    ("input_method_status", "inputMethod"),
)
#: Envolturas de classe: a bridge cria um coordinador por request a partir de
#: um template, então só a classe alcança toda chamada.
CLASS_TARGETS: tuple[tuple[type, str, str], ...] = (
    (ExperienceCoordinator, "status", "domainStatus"),
)


def percentile(ordered: list[float], fraction: float) -> float:
    """Percentil pelo índice mais próximo abaixo; sem amostra, sem número."""
    if not ordered:
        raise ValueError("nenhuma amostra para percentil")
    index = min(int(len(ordered) * fraction), len(ordered) - 1)
    return ordered[index]


def summarize(latencies_ms: list[float], payload_bytes: list[int]) -> dict[str, float | int]:
    """Estatística das consultas completas. Recusa medição vazia."""
    if not latencies_ms:
        raise ValueError("nenhuma amostra de latência")
    if not payload_bytes:
        raise ValueError("nenhuma amostra de payload")
    ordered = sorted(latencies_ms)
    sizes = sorted(float(value) for value in payload_bytes)
    return {
        "samples": len(ordered),
        "meanMs": round(sum(ordered) / len(ordered), 1),
        "minMs": round(ordered[0], 1),
        "p50Ms": round(percentile(ordered, 0.5), 1),
        "p95Ms": round(percentile(ordered, 0.95), 1),
        "maxMs": round(ordered[-1], 1),
        "payloadBytesP50": int(percentile(sizes, 0.5)),
        "payloadBytesMax": int(max(payload_bytes)),
    }


def block_summaries(timers: dict[str, list[float]], samples: int) -> dict[str, Any]:
    """Mediana por chamada e custo médio por consulta de cada bloco.

    Um bloco pode rodar mais de uma vez por snapshot (``componentRow`` roda uma
    vez por componente). ``perQueryMs`` divide a soma pelo número de consultas,
    que é o único jeito de somar blocos e comparar com o total sem enganar
    ninguém.
    """
    summaries: dict[str, Any] = {}
    for label, durations in sorted(timers.items()):
        if not durations:
            summaries[label] = {"medianPerCallMs": None, "maxPerCallMs": None, "calls": 0}
            continue
        ordered = sorted(durations)
        summaries[label] = {
            "medianPerCallMs": round(percentile(ordered, 0.5), 1),
            "maxPerCallMs": round(ordered[-1], 1),
            "calls": len(ordered),
            "perQueryMs": round(sum(durations) / max(samples, 1), 1),
        }
    return summaries


def payload_key_sizes(payload: dict[str, Any]) -> dict[str, int]:
    """Bytes por chave de topo e por bloco do dashboard, para atribuir o corpo.

    O envelope tem uma chave ``dashboard`` que é 100% do corpo; sem desdobrá-la
    o relatório diria o tamanho total sem dizer o que pesa.
    """
    sizes = {
        str(key): len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())
        for key, value in payload.items()
    }
    dashboard = payload.get("dashboard")
    if isinstance(dashboard, dict):
        for key, value in dashboard.items():
            sizes[f"dashboard.{key}"] = len(
                json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
            )
    return sizes


def survey(root: Path) -> dict[str, int]:
    """Impressão digital de uma árvore: contagens, bytes e mtime máximo.

    Não segue links simbólicos nem atravessa montagens alheias.
    """
    if not root.exists():
        return {"present": 0, "files": 0, "dirs": 0, "bytes": 0, "maxMtimeNs": 0}
    files = dirs = 0
    total_bytes = 0
    newest = 0
    for base, children, names in os.walk(root, followlinks=False):
        dirs += len(children)
        files += len(names)
        for name in names:
            try:
                info = os.lstat(os.path.join(base, name))
            except OSError:
                continue
            total_bytes += info.st_size
            newest = max(newest, info.st_mtime_ns)
    return {
        "present": 1,
        "files": files,
        "dirs": dirs,
        "bytes": total_bytes,
        "maxMtimeNs": newest,
    }


def state_surveys() -> dict[str, Any]:
    """Fotografa as raízes de estado que o read model do host toca."""
    return {
        "state": survey(paths.state_home()),
        "data": survey(paths.data_home()),
        "config": survey(paths.config_home()),
    }


def surveys_unchanged(before: dict[str, Any], after: dict[str, Any]) -> bool:
    """True quando nenhuma raiz mudou contagem, bytes ou mtime máximo."""
    return before == after


def _timed(func: Callable[..., Any], sink: list[float]) -> Callable[..., Any]:
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        started = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            sink.append((time.perf_counter() - started) * 1000.0)

    return wrapper


@contextmanager
def instrumented(dashboard: DesktopDashboard, timers: dict[str, list[float]]) -> Iterator[None]:
    """Instala wrappers de tempo nos blocos do read model e restaura ao sair."""

    def install(container: Any, attribute: str, label: str) -> None:
        original = getattr(container, attribute)
        # Um método de classe injetado por setattr na instância deixaria uma
        # sombra permanente depois do restore. Anotar a origem permite apagar em
        # vez de sobrescrever.
        own = attribute in getattr(container, "__dict__", {})
        setattr(container, attribute, _timed(original, timers.setdefault(label, [])))
        restores.append((container, attribute, original, own))

    restores: list[tuple[Any, str, Any, bool]] = []
    for path, label in INSTANCE_TARGETS:
        container: Any = dashboard
        attribute = path
        if "." in path:
            attribute, _, method = path.partition(".")
            container = getattr(dashboard, attribute)
            attribute = method
        install(container, attribute, label)
    for name, label in MODULE_TARGETS:
        install(dashboard_module, name, label)
    for klass, attribute, label in CLASS_TARGETS:
        install(klass, attribute, label)
    try:
        yield
    finally:
        for container, attribute, original, own in reversed(restores):
            with contextlib.suppress(Exception):
                if own:
                    setattr(container, attribute, original)
                else:
                    delattr(container, attribute)


def build_bridge() -> tuple[DesktopControlServer, DesktopDashboard, str, int]:
    """Sobe a bridge do produto sobre o estado real do host, somente leitura."""
    store = StateStore()
    store.migrate()
    coordinator = build_desktop_coordinator(store)
    token = secrets.token_urlsafe(32)
    dashboard = DesktopDashboard()
    server = DesktopControlServer(coordinator, token, dashboard)
    threading.Thread(target=server.serve_forever, name="central-status-probe", daemon=True).start()
    return server, dashboard, token, int(server.server_port)


def stop_bridge(server: DesktopControlServer) -> None:
    server.shutdown()
    with contextlib.suppress(OSError):
        server.server_close()


def fetch_status(port: int, token: str) -> tuple[dict[str, Any], int, float]:
    """GET /status autenticado; devolve payload, bytes e latência em ms."""
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/status",
        headers={"X-SteamZero-Token": token},
        method="GET",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=180) as response:  # noqa: S310
            body = response.read()
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:200].decode("utf-8", "replace")
        raise SystemExit(f"/status respondeu {exc.code}: {detail}") from exc
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    if status != 200:
        raise SystemExit(f"/status respondeu {status}; medição abortada")
    payload = json.loads(body.decode("utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("/status não devolveu um objeto JSON")
    return payload, len(body), elapsed_ms


def build_report(
    role: str,
    latencies: list[float],
    sizes: list[int],
    timers: dict[str, list[float]],
    key_sizes: dict[str, int],
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, Any]:
    """Monta o relatório sem token e sem conteúdo do acervo."""
    status = summarize(latencies, sizes)
    blocks = block_summaries(timers, int(status["samples"]))
    attributed = sum(float(row.get("perQueryMs", 0.0)) for row in blocks.values())
    # A soma por consulta é uma média, então só a média das consultas é termo
    # comparável: subtrair do p50 daria um resíduo negativo quando a
    # distribuição é assimétrica, que é exatamente o caso de uma bridge fria.
    residual = float(status["meanMs"]) - attributed
    return {
        "schemaVersion": 1,
        "kind": "central-status-probe",
        "role": role,
        "generatedAt": datetime.now(UTC).isoformat(timespec="seconds"),
        "repository": ui_audit_runner._repository_context(),
        "method": {
            "endpoint": "/status",
            "repeats": status["samples"],
            "bridge": "bridge do produto sobre o estado real do host, somente GET",
            "qmlBackend": os.environ.get("QT_QUICK_BACKEND"),
        },
        "status": status,
        "blocks": blocks,
        "attribution": {
            "attributedMsPerQuery": round(attributed, 1),
            "unattributedMsPerQuery": round(residual, 1),
        },
        "payloadKeyBytes": dict(sorted(key_sizes.items(), key=lambda item: -item[1])),
        "stateSurvey": {
            "before": before,
            "after": after,
            "unchanged": surveys_unchanged(before, after),
        },
    }


def print_summary(report: dict[str, Any]) -> None:
    status = report["status"]
    print(
        f"/status {status['samples']}x: p50 {status['p50Ms']:.0f} ms | "
        f"p95 {status['p95Ms']:.0f} ms | max {status['maxMs']:.0f} ms | "
        f"corpo p50 {status['payloadBytesP50'] / 1024:.0f} KiB"
    )
    survey_row = report["stateSurvey"]
    state = survey_row["before"]["state"]
    print(
        f"estado intacto: {'sim' if survey_row['unchanged'] else 'NAO'} "
        f"(arquivos {state['files']}, bytes {state['bytes']})"
    )
    blocks = report["blocks"]
    for label, row in sorted(
        blocks.items(), key=lambda item: -float(item[1].get("perQueryMs", 0.0))
    ):
        if row["calls"]:
            print(f"  {label:22s} {row['perQueryMs']:9.1f} ms/consulta")
    print(
        f"  {'-- nao atribuido':22s} "
        f"{report['attribution']['unattributedMsPerQuery']:9.1f} ms/consulta"
    )


def default_outdir() -> Path:
    return (
        ROOT
        / "docs"
        / "09-operations"
        / "evidence"
        / f"{datetime.now(UTC).strftime('%Y-%m-%d')}-rc01-central-loading"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=5, help="consultas ao /status")
    parser.add_argument("--role", default="baseline", help="rótulo da medição (baseline/final)")
    parser.add_argument("--outdir", type=Path, default=default_outdir())
    parser.add_argument("--check", action="store_true", help="mede sem gravar evidência")
    args = parser.parse_args(argv)
    if args.repeats < 1:
        raise SystemExit("--repeats precisa ser >= 1")

    server, dashboard, token, port = build_bridge()
    before = state_surveys()
    timers: dict[str, list[float]] = {}
    latencies: list[float] = []
    sizes: list[int] = []
    key_sizes: dict[str, int] = {}
    try:
        with instrumented(dashboard, timers):
            for _ in range(args.repeats):
                payload, size, elapsed = fetch_status(port, token)
                latencies.append(elapsed)
                sizes.append(size)
                key_sizes = payload_key_sizes(payload)
    finally:
        stop_bridge(server)
    after = state_surveys()

    report = build_report(args.role, latencies, sizes, timers, key_sizes, before, after)
    print_summary(report)
    if args.check:
        return 0
    args.outdir.mkdir(parents=True, exist_ok=True)
    destination = args.outdir / f"status-probe-{args.role}.json"
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    with contextlib.suppress(ValueError):
        print(f"evidência: {destination.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
