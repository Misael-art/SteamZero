# SPDX-License-Identifier: GPL-3.0-or-later
"""The handheld footer must remain legible on its dark surface."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_handheld_footer_resolves_every_foreground_against_its_dark_surface() -> None:
    source = (ROOT / "src/steamzero/ui/qml/Main.qml").read_text(encoding="utf-8")
    start = source.index("id: handheldFooter")
    end = source.index("visible: root.lastRequest.length", start)
    footer = source[start:end]

    assert footer.count('root._contrastTextColor("#080d13")') == 5
    assert "color: root.mutedColor" not in footer
    assert "color: root.textColor" not in footer
