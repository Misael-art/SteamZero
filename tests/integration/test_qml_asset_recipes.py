# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Harness RHI das variantes derivadas de um único asset transparente.

O backend offscreen prova contrato e composição; não é evidência de FPS, frame
time, memória ou desempenho do hardware real.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageStat

pytestmark = pytest.mark.visual

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from qml_capture_runner import Backend, CanonicalEnvironment, parse_messages  # noqa: E402

HARNESS = ROOT / "tests/qml/check_asset_recipe_preview.qml"
GOLDEN = ROOT / "tests/qml/golden/asset-recipes"
VARIANTS = (
    "original",
    "colored",
    "grayscale",
    "black",
    "white",
    "outlineThin",
    "outlineThick",
    "outlinedGlow",
    "outlinedShadow",
)


@pytest.fixture(scope="module")
def rendered(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if os.environ.get("QT_QUICK_BACKEND") == "software":
        pytest.skip(
            "QML-RHI-ENVIRONMENT-001: goldens MultiEffect exigem RHI; "
            "o gate software cobre o contrato QML separadamente"
        )
    runtime = shutil.which("qml6") or shutil.which("qml")
    assert runtime is not None, "QML-VISUAL-ENVIRONMENT-001: qml6/qml ausente"
    output = tmp_path_factory.mktemp("asset-recipes")
    environment = CanonicalEnvironment(backend=Backend.RHI).to_env()
    # MultiEffect é um node RHI; o backend software não executa shaders. OpenGL
    # offscreen usa a implementação Mesa disponível e permanece uma categoria
    # distinta dos goldens de texto em software.
    environment["QT_QUICK_BACKEND"] = "opengl"
    environment["QSG_RHI_BACKEND"] = "opengl"
    completed = subprocess.run(
        [runtime, str(HARNESS), "--", f"--output-dir={output}"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    forbidden = [message.text for message in parse_messages(completed.stderr) if message.forbidden]
    assert not forbidden
    for variant in VARIANTS:
        path = output / f"{variant}.png"
        assert path.is_file() and path.stat().st_size > 0
    return output


def _open(path: Path) -> Image.Image:
    with Image.open(path) as image:
        return image.convert("RGBA")


def _opaque_area(image: Image.Image, threshold: int = 8) -> int:
    histogram = image.getchannel("A").histogram()
    return sum(histogram[threshold + 1 :])


def _alpha_iou(first: Image.Image, second: Image.Image, threshold: int = 8) -> float:
    a = first.getchannel("A").point(lambda value: 255 if value > threshold else 0, mode="1")
    b = second.getchannel("A").point(lambda value: 255 if value > threshold else 0, mode="1")
    intersection = ImageChops.logical_and(a, b).histogram()[255]
    union = ImageChops.logical_or(a, b).histogram()[255]
    return intersection / max(1, union)


def _mean_rgb(image: Image.Image) -> tuple[float, float, float]:
    mask = image.getchannel("A").point(lambda value: 255 if value > 240 else 0)
    mean = ImageStat.Stat(image.convert("RGB"), mask=mask).mean
    return float(mean[0]), float(mean[1]), float(mean[2])


def test_alpha_and_internal_holes_survive_recolor(rendered: Path) -> None:
    original = _open(rendered / "original.png")
    assert original.getpixel((5, 5))[3] == 0
    assert original.getpixel((202, 70))[3] == 0
    assert original.getpixel((50, 50))[3] == 255
    for variant in ("colored", "grayscale", "black", "white"):
        candidate = _open(rendered / f"{variant}.png")
        assert _alpha_iou(original, candidate) >= 0.995
        assert candidate.getpixel((202, 70))[3] == 0


def test_black_white_and_colored_variants_are_visually_distinct(rendered: Path) -> None:
    black = _mean_rgb(_open(rendered / "black.png"))
    white = _mean_rgb(_open(rendered / "white.png"))
    colored = _mean_rgb(_open(rendered / "colored.png"))
    assert max(black) <= 8
    assert min(white) >= 245
    assert colored[1] >= 180 and colored[2] >= 180 and colored[0] < colored[1]


def test_thick_outline_is_materially_wider_than_thin(rendered: Path) -> None:
    original = _open(rendered / "original.png")
    thin = _open(rendered / "outlineThin.png")
    thick = _open(rendered / "outlineThick.png")
    original_area = _opaque_area(original)
    thin_area = _opaque_area(thin)
    thick_area = _opaque_area(thick)
    assert thin_area > original_area * 1.05
    assert thick_area > thin_area * 1.10


@pytest.mark.parametrize("variant", VARIANTS)
def test_rhi_golden_has_driver_tolerance(rendered: Path, variant: str) -> None:
    actual = _open(rendered / f"{variant}.png")
    expected_path = GOLDEN / f"{variant}.png"
    assert expected_path.is_file(), f"golden ausente: {expected_path}"
    expected = _open(expected_path)
    assert actual.size == expected.size
    # Bordas antialias e blur variam entre Mesa/drivers. A forma alpha deve
    # coincidir quase por inteiro e o erro médio global pode absorver pequenas
    # diferenças sem aceitar uma variante vazia, trocada ou sem contorno.
    assert _alpha_iou(actual, expected, threshold=16) >= 0.96
    mean_error = sum(ImageStat.Stat(ImageChops.difference(actual, expected)).mean) / 4
    assert mean_error <= 10.0
