#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Razao de contraste WCAG medida no PIXEL RENDERIZADO.

A tentativa anterior adivinhava o fundo pela arvore de objetos — "o ancestral
opaco mais proximo" — e errava em Button com ``background`` proprio: o mesmo
rotulo saia com razao 13,69 e 1,0 ao mesmo tempo. Adivinhar fundo pela arvore e
o mesmo erro de classificar acao pela forma.

O PNG da pagina sai com alpha, porque quem pinta o fundo e um ancestral dela.
Compor sobre preto mediria um fundo que a tela nunca mostrou, entao a sonda
informa a cor de fundo do shell e a composicao usa essa cor.

Aqui o fundo nao e adivinhado: e a cor MAIS FREQUENTE dentro da caixa do texto,
e a frente e a cor mais distante dela em luminancia, entre as que aparecem o
bastante para nao serem borda de antialiasing. Isso mede o que a tela desenhou.

Limite: WCAG 2.1 AA — 4,5:1 para texto normal e 3:1 para texto grande
(>= 24 px, ou >= 18,66 px quando negrito).

BLOQUEIO CONHECIDO — esta ferramenta NAO e gate ainda
=====================================================
A captura da PAGINA nao e deterministica. O mesmo ``steam.png`` saiu ``RGBA``
numa execucao e ``RGB`` com fundo preto opaco na seguinte, porque a pagina nao
pinta o proprio fundo: quem pinta e um ancestral, e offscreen o backing varia.
Um recorte conferido a olho mostrou o texto correto sobre fundo claro enquanto a
medicao da mesma caixa reportava fundo ``#000000``.

Enquanto isso nao for resolvido, as razoes desta ferramenta NAO servem de
acusacao: publicar essa contagem repetiria o padrao de falso positivo que esta
auditoria ja teve. A correcao e capturar um item que pinte ele mesmo o fundo
opaco, como ``tools/qml_capture/CaptureHarness.qml`` faz ("fundo explicito, e
nao a cor da Window").

Tres vieses ja encontrados e corrigidos no caminho, registrados para nao serem
refeitos: (1) adivinhar fundo pelo ancestral opaco erra em Button com background
proprio; (2) corte por FRACAO de pixels (2%) tem vies de largura e faz o glifo
desaparecer em Label com fillWidth; (3) compor sobre preto mede um fundo que a
tela nunca mostrou.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tools" / "ui_contrast_probe.qml"
CAPTURE_DIR = ROOT / "build" / "ui-contrast"

#: Minimo ABSOLUTO de pixels para uma cor contar como frente.
#:
#: A primeira versao usava fracao (2% da caixa) e produziu falso positivo em
#: serie: `Label` com `fillWidth` tem caixa muito mais larga que as letras, os
#: glifos ficavam abaixo do corte, e o "texto" medido virava outro tom do
#: proprio fundo — dai pares como #fefefe sobre #fdfdfd com razao 1,01.
#:
#: Um piso absoluto pequeno nao tem esse vies de largura. Antialiasing nao
#: engana o resultado porque suas cores ficam ENTRE frente e fundo em
#: luminancia, e o que se procura e o extremo.
_MIN_PIXELS = 6

LARGE_PX = 24.0
LARGE_BOLD_PX = 18.66
AA_THRESHOLD = 3.0
AAA_NORMAL = 4.5


def _hex(rgb: tuple[int, int, int]) -> str:
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def _linear(channel: float) -> float:
    c = channel / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(rgb: tuple[int, int, int]) -> float:
    r, g, b = rgb
    return 0.2126 * _linear(r) + 0.7152 * _linear(g) + 0.0722 * _linear(b)


def contrast_ratio(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    la, lb = relative_luminance(a), relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def required_ratio(pixel_size: float, bold: bool) -> float:
    """Limite WCAG AA conforme o tamanho do texto."""
    if pixel_size >= LARGE_PX or (bold and pixel_size >= LARGE_BOLD_PX):
        return AA_THRESHOLD
    return AAA_NORMAL


def flatten(image: Image.Image, background: tuple[int, int, int]) -> Image.Image:
    """Compoe a captura sobre o fundo REAL do shell, nao sobre preto."""
    if image.mode != "RGBA":
        return image.convert("RGB")
    canvas = Image.new("RGB", image.size, background)
    canvas.paste(image, mask=image.getchannel("A"))
    return canvas


def measure(image: Image.Image, box: tuple[int, int, int, int]) -> dict[str, Any] | None:
    """Mede fundo e frente dentro da caixa, ou devolve ``None`` se nao der.

    Devolver ``None`` e deliberado: caixa de um pixel so, ou preenchida por uma
    unica cor, nao tem par frente/fundo para medir. Inventar um par ali seria
    fabricar resultado.
    """
    x, y, w, h = box
    if w <= 0 or h <= 0:
        return None
    crop = image.crop((x, y, x + w, y + h))
    pixels = list(crop.getdata())
    if not pixels:
        return None
    counts = Counter(pixels)
    background, _ = counts.most_common(1)[0]
    candidates = [
        (color, count)
        for color, count in counts.items()
        if color != background and count >= _MIN_PIXELS
    ]
    if not candidates:
        return None
    foreground = max(
        candidates,
        key=lambda item: abs(relative_luminance(item[0]) - relative_luminance(background)),
    )[0]
    return {
        "background": _hex(background),
        "foreground": _hex(foreground),
        "ratio": round(contrast_ratio(foreground, background), 2),
    }


def _parse_color(raw: str) -> tuple[int, int, int]:
    text = raw.strip().lstrip("#")
    if len(text) == 8:  # AARRGGBB
        text = text[2:]
    if len(text) != 6:
        return (0, 0, 0)
    return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))


def run_probe(
    out_dir: Path = CAPTURE_DIR,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], tuple[int, int, int]]:
    """Executa a sonda QML e devolve (linhas, secoes nao medidas, fundo)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("*.png"):
        stale.unlink()
    env = {
        "QT_QPA_PLATFORM": "offscreen",
        "QML_DISABLE_DISK_CACHE": "1",
        "QT_FORCE_STDERR_LOGGING": "1",
        "QT_LOGGING_RULES": "",
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(Path.home()),
    }
    completed = subprocess.run(
        ["qml6", str(PROBE)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    rows: list[dict[str, Any]] = []
    unmeasured: list[dict[str, Any]] = []
    background = (0, 0, 0)
    for line in output.splitlines():
        marker = line.find("CONTRAST-BACKGROUND ")
        if marker >= 0:
            background = _parse_color(line[marker + len("CONTRAST-BACKGROUND ") :])
        marker = line.find("CONTRAST-ROWS ")
        if marker >= 0:
            rows = json.loads(line[marker + len("CONTRAST-ROWS ") :])
        marker = line.find("CONTRAST-UNMEASURED ")
        if marker >= 0:
            unmeasured = json.loads(line[marker + len("CONTRAST-UNMEASURED ") :])
    if not rows and completed.returncode != 0:
        raise RuntimeError(f"sonda de contraste falhou:\n{output[-3000:]}")
    return rows, unmeasured, background


def build_inventory(out_dir: Path = CAPTURE_DIR) -> dict[str, Any]:
    rows, unmeasured, background = run_probe(out_dir)
    images: dict[str, Image.Image] = {}
    measured: list[dict[str, Any]] = []
    skipped = 0
    for row in rows:
        name = str(row["image"])
        if name not in images:
            path = out_dir / name
            if not path.is_file():
                skipped += 1
                continue
            images[name] = flatten(Image.open(path), background)
        result = measure(images[name], (int(row["x"]), int(row["y"]), int(row["w"]), int(row["h"])))
        if result is None:
            skipped += 1
            continue
        required = required_ratio(float(row["pixelSize"]), bool(row["bold"]))
        measured.append(
            {
                **{k: row[k] for k in ("section", "text", "pixelSize", "bold")},
                **result,
                "required": required,
                "passes": result["ratio"] >= required,
            }
        )
    failures = [entry for entry in measured if not entry["passes"]]
    by_section: dict[str, dict[str, int]] = {}
    for entry in measured:
        bucket = by_section.setdefault(entry["section"], {"measured": 0, "failing": 0})
        bucket["measured"] += 1
        if not entry["passes"]:
            bucket["failing"] += 1
    return {
        "schemaVersion": 1,
        "kind": "steamzero-ui-contrast",
        "shellBackground": _hex(background),
        "textsFound": len(rows),
        "measuredCount": len(measured),
        "skippedCount": skipped,
        "unmeasuredSections": unmeasured,
        "failingCount": len(failures),
        "bySection": by_section,
        "failures": sorted(failures, key=lambda item: item["ratio"]),
        "measured": measured,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)
    inventory = build_inventory()
    if args.json:
        args.json.write_text(
            json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    print(
        f"textos encontrados: {inventory['textsFound']} | medidos: "
        f"{inventory['measuredCount']} | sem par medivel: {inventory['skippedCount']}"
    )
    print(f"seções não medidas: {inventory['unmeasuredSections']}")
    print(f"abaixo do limite WCAG AA: {inventory['failingCount']}")
    for entry in inventory["failures"][:40]:
        print(
            f"  {entry['ratio']:5.2f} (exigido {entry['required']}) "
            f"{entry['section']:10s} {entry['foreground']} sobre {entry['background']} "
            f"· {entry['text'][:40]!r}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
