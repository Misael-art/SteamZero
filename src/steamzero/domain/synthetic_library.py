# SPDX-License-Identifier: GPL-3.0-or-later
"""Biblioteca sintética para pré-visualizar temas sem tocar dados do usuário.

O modelo tem o mesmo formato que ``DesktopDashboard._theme_runtime_model``
devolve para a biblioteca real, mas é gerado deterministicamente aqui: nenhum
título, caminho ou arte vem do catálogo privado, e nenhuma ação de produção
(``Jogar``) é oferecida. A arte é SVG embutido (``data:``), então a cena resolve
mídia sem depender de arquivos externos.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

SYNTHETIC_SYSTEM_ID = "synthetic"

_GAMES: tuple[tuple[str, str, str, str, str], ...] = (
    ("Aurora Runner", "Corrida", "1998", "#1f6feb", "#0b1d3a"),
    ("Pixel Harbor", "Aventura", "2003", "#2da44e", "#0f2a1a"),
    ("Neon Courier", "Ação", "2011", "#bf3989", "#2a0d20"),
    ("Cinder Vale", "RPG", "1995", "#d29922", "#2b200a"),
    ("Orbit Garden", "Puzzle", "2008", "#8957e5", "#1c1236"),
    ("Tidal Echo", "Plataforma", "2016", "#0ea5a5", "#082a2a"),
)


def _art(title: str, width: int, height: int, accent: str, base: str) -> str:
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="{base}"/>'
        f'<circle cx="{width * 0.7:.0f}" cy="{height * 0.35:.0f}" '
        f'r="{min(width, height) * 0.3:.0f}" '
        f'fill="{accent}" opacity="0.85"/>'
        f'<text x="{width * 0.06:.0f}" y="{height * 0.9:.0f}" fill="#ffffff" '
        f'font-family="sans-serif" font-size="{height * 0.08:.0f}">{title}</text></svg>'
    )
    return "data:image/svg+xml;utf8," + quote(svg)


def synthetic_runtime_model() -> dict[str, Any]:
    games: list[dict[str, Any]] = []
    for index, (title, genre, year, accent, base) in enumerate(_GAMES):
        games.append(
            {
                "id": f"synthetic-{index}",
                "name": title,
                "title": title,
                "platformId": SYNTHETIC_SYSTEM_ID,
                "coverUrl": _art(title, 600, 900, accent, base),
                "heroUrl": _art(title, 1280, 720, accent, base),
                "fanartUrl": _art(title, 1280, 720, accent, base),
                "bannerUrl": _art(title, 1280, 360, accent, base),
                "screenshotUrl": _art(title, 960, 540, accent, base),
                "genre": genre,
                "year": year,
                "rating": 4.0 + (index % 3) * 0.25,
                "state": "verified",
            }
        )
    return {
        "items": games,
        "selectedIndex": 0,
        "selected": games[0],
        "system": {
            "id": SYNTHETIC_SYSTEM_ID,
            "name": "Biblioteca de demonstração",
            "label": "Biblioteca de demonstração",
        },
        "status": {"label": "Dados sintéticos — isolados da sua biblioteca", "state": "synthetic"},
        # Sem "Jogar": o modo sintético nunca dispara ação de produção.
        "actions": ["Selecionar", "Detalhes"],
        "isolated": True,
    }
