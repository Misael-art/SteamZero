#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Mede frame time, startup e memória de uma cena da Theme Engine no host real.

Existe porque a medição anterior foi improvisada e não reproduzível: números
digitados a partir de uma captura de tela não são evidência que outra pessoa
consiga refazer.

Duas restrições moldaram o desenho:

* ``console.log`` do QML não chega ao chamador neste host, então o harness
  devolve o resultado por HTTP em 127.0.0.1 — o mesmo padrão que os testes de
  integração já usam para o ErrorCard;
* apontar ``--qml-dir`` para ``/opt/steamzero/current`` mede a release
  instalada, não o checkout. É a diferença entre evidência física e ensaio.

VRAM não é medida: nenhuma API portátil devolve o consumo de textura do
processo, e inventar o número seria pior do que admitir a lacuna. O relatório
declara ``vramMeasured: false``.
"""

from __future__ import annotations

import argparse
import json
import shutil
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DURATION = 6.0
DEFAULT_WARMUP = 2.0


@dataclass(frozen=True)
class FrameSummary:
    frames: int
    avg_ms: float
    p50_ms: float
    p95_ms: float
    max_ms: float

    def to_dict(self) -> dict[str, float | int]:
        return {
            "frames": self.frames,
            "avgFrameTimeMs": self.avg_ms,
            "p50Ms": self.p50_ms,
            "p95Ms": self.p95_ms,
            "maxMs": self.max_ms,
        }


def summarize(samples: list[float]) -> FrameSummary:
    """Estatística dos intervalos entre frames, em milissegundos.

    Sem amostra não há resumo: devolver zeros faria uma medição vazia parecer
    uma medição perfeita.
    """
    if not samples:
        raise ValueError("nenhuma amostra de frame time")
    ordered = sorted(samples)
    count = len(ordered)
    total = sum(ordered)
    return FrameSummary(
        frames=count,
        avg_ms=round(total / count, 3),
        p50_ms=round(ordered[int(count * 0.50)], 3),
        p95_ms=round(ordered[min(int(count * 0.95), count - 1)], 3),
        max_ms=round(ordered[-1], 3),
    )


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class _Collector(HTTPServer):
    payload: dict[str, Any] | None = None


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8", "replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict) and isinstance(self.server, _Collector):
            self.server.payload = parsed
        self.send_response(204)
        self.end_headers()

    def log_message(self, *_: Any) -> None:
        """Silencia o log da stdlib; o relatório é a saída, não o tráfego."""


_HARNESS = """
import QtQuick
import QtQuick.Window
import "file://__QMLDIR__"

Window {
    id: win
    visible: true
    width: __WIDTH__
    height: __HEIGHT__
    title: "SteamZero — sonda de desempenho"

    property var preview: JSON.parse(Qt.atob("__PAYLOAD__"))
    readonly property var layouts: preview.sceneLayoutPreview.layouts
    property var samples: []
    property bool warm: false
    property real startedAt: Date.now()
    property real firstFrameAt: 0

    Rectangle { anchors.fill: parent; color: "#071019" }

    Column {
        anchors.centerIn: parent
        spacing: 8
        Repeater {
            model: Object.keys(win.layouts)
            delegate: Item {
                required property string modelData
                width: win.width - 40
                height: 52
                SceneRepeater {
                    anchors.fill: parent
                    layout: win.layouts[modelData]
                    NumberAnimation on x {
                        from: -30; to: 30; duration: 1300
                        loops: Animation.Infinite; easing.type: Easing.InOutCubic
                    }
                }
            }
        }
    }

    FrameAnimation {
        running: true
        onTriggered: {
            if (win.firstFrameAt === 0)
                win.firstFrameAt = Date.now()
            if (win.warm)
                win.samples.push(frameTime * 1000.0)
        }
    }

    Timer { interval: __WARMUP_MS__; running: true; repeat: false; onTriggered: win.warm = true }

    Timer {
        interval: __TOTAL_MS__
        running: true
        repeat: false
        onTriggered: {
            const request = new XMLHttpRequest()
            request.open("POST", "http://127.0.0.1:__PORT__/report")
            request.setRequestHeader("Content-Type", "application/json")
            request.onreadystatechange = function() {
                if (request.readyState === XMLHttpRequest.DONE)
                    Qt.exit(0)
            }
            request.send(JSON.stringify({
                "samples": win.samples,
                "startupMs": win.firstFrameAt - win.startedAt,
                "scenes": Object.keys(win.layouts).length
            }))
        }
    }
}
"""


def _qml_runner() -> Path:
    """Resolve o runtime QML para um caminho absoluto e executável.

    O argv desta sonda nunca é montado a partir de entrada livre: o executável
    sai do PATH via ``which`` e o harness é um arquivo que a própria ferramenta
    acabou de escrever num diretório temporário.
    """
    for name in ("qml6", "qml"):
        found = shutil.which(name)
        if found:
            resolved = Path(found).resolve()
            if resolved.is_file():
                return resolved
    raise SystemExit("qml6/qml ausente; instale o runtime Qt para medir")


def vram_kb_from_fdinfo(blocks: list[str]) -> int | None:
    """Soma a VRAM do processo a partir dos blocos ``fdinfo`` do DRM.

    O driver expõe o mesmo cliente em vários descritores — três fds com o mesmo
    ``drm-client-id`` e o mesmo valor. Somar tudo triplicaria a medição, então
    cada cliente entra uma vez só.

    Devolve ``None`` quando nenhum bloco traz VRAM: sem dado é melhor declarar
    ausência do que reportar zero, que pareceria consumo nulo.
    """
    per_client: dict[str, int] = {}
    for block in blocks:
        client: str | None = None
        vram: int | None = None
        for line in block.splitlines():
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if key == "drm-client-id":
                client = value
            elif key == "drm-memory-vram":
                number = value.split()[0] if value else ""
                if number.isdigit():
                    vram = int(number)
        if client is not None and vram is not None:
            per_client[client] = max(per_client.get(client, 0), vram)
    if not per_client:
        return None
    return sum(per_client.values())


def _peak_vram_kb(pid: int) -> int | None:
    """Lê a VRAM corrente do processo; ``None`` quando o driver não expõe."""
    fdinfo = Path(f"/proc/{pid}/fdinfo")
    blocks: list[str] = []
    try:
        entries = sorted(fdinfo.iterdir())
    except OSError:
        return None
    for entry in entries:
        try:
            content = entry.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "drm-client-id" in content:
            blocks.append(content)
    return vram_kb_from_fdinfo(blocks)


def _safe_qml_dir(value: Path) -> Path:
    """Recusa diretório inexistente ou com aspas.

    O caminho é interpolado no corpo QML do harness; uma aspa aqui deixaria de
    ser um caminho e viraria código na cena.
    """
    resolved = value.expanduser().resolve()
    if not resolved.is_dir():
        raise SystemExit(f"--qml-dir não é diretório: {resolved}")
    if any(char in str(resolved) for char in ('"', "'", "\\", "\n")):
        raise SystemExit("--qml-dir com caractere que escaparia do literal QML")
    return resolved


def _peak_rss_kb(pid: int, stop: threading.Event, vram: dict[str, int]) -> int:
    peak = 0
    status = Path(f"/proc/{pid}/status")
    while not stop.is_set():
        try:
            for line in status.read_text(encoding="utf-8").splitlines():
                if line.startswith("VmRSS:"):
                    peak = max(peak, int(line.split()[1]))
                    break
        except (OSError, ValueError, IndexError):
            break
        current = _peak_vram_kb(pid)
        if current is not None:
            vram["kb"] = max(vram.get("kb", 0), current)
        time.sleep(0.3)
    return peak


def measure(
    *,
    qml_dir: Path,
    preview: dict[str, Any],
    duration: float,
    warmup: float,
    width: int,
    height: int,
    workdir: Path,
) -> dict[str, Any]:
    import base64

    port = _free_port()
    payload = base64.b64encode(json.dumps(preview).encode("utf-8")).decode("ascii")
    harness = (
        _HARNESS.replace("__QMLDIR__", str(_safe_qml_dir(qml_dir)))
        .replace("__PAYLOAD__", payload)
        .replace("__PORT__", str(port))
        .replace("__WIDTH__", str(width))
        .replace("__HEIGHT__", str(height))
        .replace("__WARMUP_MS__", str(int(warmup * 1000)))
        .replace("__TOTAL_MS__", str(int((warmup + duration) * 1000)))
    )
    harness_path = workdir / "perf_probe.qml"
    harness_path.write_text(harness, encoding="utf-8")

    server = _Collector(("127.0.0.1", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    stop = threading.Event()
    peak_holder: dict[str, int] = {}
    vram_holder: dict[str, int] = {}
    try:
        # Auditoria do alerta de subprocess com argv dinâmico (opengrep
        # dangerous-subprocess-use-audit): os dois elementos são construídos
        # aqui e nenhum vem de entrada livre. O executável sai de
        # ``shutil.which`` e é resolvido para um caminho absoluto existente; o
        # segundo é o harness que esta função acabou de escrever num diretório
        # temporário próprio. Não há shell, não há concatenação de string e
        # ``--qml-dir`` já foi recusado se contiver caractere de escape.
        argv = [str(_qml_runner()), str(harness_path.resolve())]
        process = subprocess.Popen(  # nosemgrep: dangerous-subprocess-use-audit
            argv,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        sampler = threading.Thread(
            target=lambda: peak_holder.setdefault(
                "kb", _peak_rss_kb(process.pid, stop, vram_holder)
            ),
            daemon=True,
        )
        sampler.start()
        process.wait(timeout=warmup + duration + 30)
        stop.set()
        sampler.join(timeout=5)
    finally:
        server.shutdown()
        server.server_close()

    if server.payload is None:
        raise SystemExit("a cena não reportou medição; verifique o runtime QML")
    samples = [float(value) for value in server.payload.get("samples", [])]
    summary = summarize(samples)
    return {
        "schemaVersion": 1,
        "qmlDir": str(qml_dir),
        "scenes": server.payload.get("scenes"),
        "surface": f"{width}x{height}",
        "frameTime": summary.to_dict(),
        "startupMs": round(float(server.payload.get("startupMs", 0.0)), 3),
        "peakRssKb": peak_holder.get("kb", 0),
        "peakVramKb": vram_holder.get("kb"),
        "vramMeasured": "kb" in vram_holder,
        "vramMethod": (
            "drm fdinfo do processo, agrupado por drm-client-id" if "kb" in vram_holder else None
        ),
        "note": (
            "frameTime vem do render loop (FrameAnimation), nao de frames apresentados: "
            "nao afirme FPS de tela a partir daqui."
        ),
    }


def _load_preview(path: Path | None, theme: str) -> dict[str, Any]:
    if path is not None:
        return dict(json.loads(path.read_text(encoding="utf-8")))
    sys.path.insert(0, str(ROOT / "src"))
    from steamzero.domain.theme_editor import ThemeEditorManager

    loaded = ThemeEditorManager().load(theme)["preview"]
    if not isinstance(loaded, dict):
        raise SystemExit(f"preview do tema {theme} não é objeto")
    return loaded


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--qml-dir",
        type=Path,
        default=ROOT / "src" / "steamzero" / "ui" / "qml",
        help="diretório dos componentes; aponte para a release instalada para medi-la",
    )
    parser.add_argument("--theme", default="org.steamzero.asset-recipes-demo")
    parser.add_argument("--preview-json", type=Path, default=None)
    parser.add_argument("--duration", type=float, default=DEFAULT_DURATION)
    parser.add_argument("--warmup", type=float, default=DEFAULT_WARMUP)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=800)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    preview = _load_preview(args.preview_json, args.theme)
    if "sceneLayoutPreview" not in preview:
        raise SystemExit("o preview não traz sceneLayoutPreview; nada a medir")

    import tempfile

    with tempfile.TemporaryDirectory(prefix="steamzero-perf-") as tmp:
        report = measure(
            qml_dir=args.qml_dir,
            preview=preview,
            duration=args.duration,
            warmup=args.warmup,
            width=args.width,
            height=args.height,
            workdir=Path(tmp),
        )
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out is not None:
        args.out.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
