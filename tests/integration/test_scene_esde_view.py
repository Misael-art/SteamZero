# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""O renderizador do IR de cena, no runtime QML de verdade."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "tests" / "qml" / "check_scene_esde_view.qml"
VIEW = ROOT / "src" / "steamzero" / "ui" / "qml" / "SceneEsdeView.qml"


def _qt6_runner() -> str | None:
    for candidate in (
        Path("/usr/lib/qt6/bin/qmltestrunner"),
        Path("/usr/lib64/qt6/bin/qmltestrunner"),
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return shutil.which("qmltestrunner6")


RUNNER = _qt6_runner()


def test_the_renderer_never_reaches_outside_the_scene_it_was_given() -> None:
    """Guarda de código: roda mesmo sem `qmltestrunner`.

    O caminho de imagem chega como URI de blob já validado no domínio. Uma
    superfície que montasse caminho ou baixasse por conta própria contornaria a
    fronteira de confiança que separa tema de terceiros do sistema.
    """
    source = VIEW.read_text(encoding="utf-8")

    forbidden_reaches = (
        "XMLHttpRequest",
        "http://",
        "https://",
        "Qt.openUrlExternally",
        "import Qt.labs",
    )
    for forbidden in forbidden_reaches:
        assert forbidden not in source, f"o renderizador alcança {forbidden!r}"
    # Tema de terceiros não executa código: nada de Loader com `source` externo.
    assert "sourceComponent" in source, "o Loader precisa escolher componente local, não URL"
    assert "source: modelData.source" in source, "a imagem deve vir do IR já resolvido"


def test_geometry_is_required_before_drawing() -> None:
    """Sem geometria o elemento não desenha — inventá-la cobria a cena."""
    source = VIEW.read_text(encoding="utf-8")
    assert "hasGeometry" in source
    assert "sem geometria declarada" in source


PREVIEW_HARNESS = ROOT / "tests" / "qml" / "check_theme_scene_preview.qml"


@pytest.mark.parametrize("harness", [HARNESS, PREVIEW_HARNESS], ids=["view", "preview"])
@pytest.mark.visual
def test_scene_view_behaviour_in_the_qml_runtime(harness: Path) -> None:
    assert RUNNER is not None, "qmltestrunner Qt 6 é obrigatório para esta prova"
    env = os.environ.copy()
    env.update({"QT_QPA_PLATFORM": "offscreen"})
    completed = subprocess.run(
        [RUNNER, "-input", str(harness)],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    output = completed.stdout + completed.stderr
    assert completed.returncode == 0, output
    assert "Totals:" in output and ", 0 failed" in output, output
