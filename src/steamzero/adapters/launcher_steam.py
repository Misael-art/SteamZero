# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Acervo Steam instalado, no formato que a home do Launcher consome.

Existe porque o Launcher publicava só a biblioteca de emulação. A central somava
Steam + emulação e mostrava 1134 títulos; o Launcher mostrava 1119. Medido no
host em 2026-09-04: 16 ``appmanifest_*.acf``, menos o LSFG, dão exatamente os 15
de diferença.

O número era o sintoma. O defeito é que, em Game Mode — onde o Launcher vive e
onde não há mouse nem desktop —, os jogos Steam do usuário não existiam. Fazer
os dois rótulos concordarem teria escondido isso.

A leitura dos manifestos é a MESMA de ``steam_gameplay`` (importada, não
reescrita): duas leituras independentes do acervo voltariam a divergir, que é o
defeito que este módulo fecha.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from steamzero.adapters.launcher_catalog import CatalogGame
from steamzero.adapters.lsfg import LSFG_APP_ID
from steamzero.adapters.steam_gameplay import (
    default_steam_roots,
    library_roots,
    parse_app_manifest,
)

#: Seção da home que agrupa os jogos Steam. A home agrupa por sistema, e o
#: Steam é um sistema como qualquer outro para efeito de navegação.
STEAM_SECTION = "steam"


def steam_catalog_games(*, roots: Sequence[Path] | None = None) -> tuple[CatalogGame, ...]:
    """Jogos Steam instalados, prontos para entrar na home.

    O LSFG fica de fora: é a ferramenta que o próprio projeto instala, não um
    jogo do usuário. Incluí-lo recriaria a divergência de contagem pelo outro
    lado — a central já o exclui em ``steam_gameplay``.

    Biblioteca ilegível não levanta: devolve o que conseguiu ler. Um disco
    externo desmontado não pode impedir o Launcher de abrir (AGENTS.md §8).
    """
    resolved = tuple(roots) if roots is not None else default_steam_roots()
    games: dict[str, CatalogGame] = {}
    for root in library_roots(resolved):
        steamapps = root / "steamapps"
        try:
            manifests = sorted(steamapps.glob("appmanifest_*.acf"))
        except OSError:
            continue
        for manifest in manifests:
            parsed = parse_app_manifest(manifest)
            if parsed is None:
                continue
            app_id, name = parsed
            if app_id == LSFG_APP_ID:
                continue
            games[app_id] = CatalogGame(
                id=app_id,
                title=name,
                platform=STEAM_SECTION,
                cover_url=_cover_url(root, app_id),
                kind="steam",
            )
    return tuple(games.values())


def _cover_url(root: Path, app_id: str) -> str:
    """Capa da grade do Steam, quando o cliente já a baixou.

    Ausência de capa é o caso comum e não é erro: a home tem seu próprio
    fallback e inventar um caminho faria o ``Image`` falhar em silêncio.
    """
    library_cache = root / "appcache" / "librarycache"
    for name in (f"{app_id}_library_600x900.jpg", f"{app_id}p.jpg"):
        candidate = library_cache / name
        try:
            if candidate.is_file():
                return candidate.resolve().as_uri()
        except OSError:
            continue
    return ""
