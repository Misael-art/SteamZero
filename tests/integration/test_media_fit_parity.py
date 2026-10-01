# SPDX-License-Identifier: GPL-3.0-or-later
"""``mediaFit.js`` (runtime QML) e ``resolve_fit`` (Studio/Python) são o mesmo
contrato: o que o inspector explica é o que a interface desenha."""

from __future__ import annotations

import itertools
from pathlib import Path

import pytest

from steamzero.domain.media_recipes import MediaRecipe, resolve_fit

QtQml = pytest.importorskip("PySide6.QtQml")

JS = Path(__file__).resolve().parents[2] / "src/steamzero/ui/qml/mediaFit.js"


def _engine():  # type: ignore[no-untyped-def]
    from PySide6.QtCore import QCoreApplication

    app = QCoreApplication.instance() or QCoreApplication([])
    engine = QtQml.QJSEngine(app)
    source = JS.read_text("utf-8").replace(".pragma library", "")
    result = engine.evaluate(source)
    assert not result.isError(), result.toString()
    return engine


def test_js_and_python_resolve_identically() -> None:
    engine = _engine()
    shapes = [(600, 900), (900, 600), (500, 500), (0, 0)]
    cases = itertools.product(
        ("crop", "cover", "contain", "fill"),
        ("none", "auto", "portrait", "landscape"),
        shapes,
        shapes,
        ((0.5, 0.5), (0.9, 0.1)),
    )
    count = 0
    for fit, orientation, image, slot, (fx, fy) in cases:
        payload = {
            "sourceOrder": ["cover"],
            "fit": fit,
            "orientation": orientation,
            "focalX": fx,
            "focalY": fy,
        }
        expected = resolve_fit(MediaRecipe.from_dict("focusedCover", payload), *image, *slot)
        got = (
            engine.globalObject()
            .property("resolve")
            .call([engine.toScriptValue(payload), *image, *slot])
        )
        assert got.toVariant() == expected, (payload, image, slot)
        count += 1
    assert count == 4 * 4 * 4 * 4 * 2
