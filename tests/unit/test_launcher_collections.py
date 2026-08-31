# SPDX-License-Identifier: GPL-3.0-or-later
"""Coleções no Launcher: uma seção por coleção persistida, com membros jogáveis.

O Launcher não reimplementa a regra de coleção: usa o `CollectionManager` do
domínio. A seção "Favoritos" (rule favorite) entra na home e os membros são
convertidos de `emulation:<id>` (gameRef do domínio) para o id canônico do
Launcher, para que a navegação/launch continuem usando o id do projeto.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from steamzero.adapters.launcher_catalog import CatalogGame
from steamzero.core import fs, paths
from steamzero.launcher.app import _sections_from_collections


@pytest.fixture(autouse=True)
def _hermetic_collection(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    fs.ensure_state_layout()
    document = {
        "schemaVersion": 1,
        "revision": 1,
        "tags": [],
        "favorites": ["emulation:game-a", "emulation:game-b"],
        "assignments": [],
        "collections": [
            {
                "id": "favoritos",
                "name": "Favoritos",
                "rule": {"match": "all", "predicates": [{"field": "favorite", "value": True}]},
            }
        ],
    }
    cfg = paths.collection_config_path()
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(
        __import__("json").dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def test_collection_section_is_created_from_domain() -> None:
    catalog = [
        CatalogGame(id="game-a", title="Game A", platform="switch"),
        CatalogGame(id="game-b", title="Game B", platform="switch"),
        CatalogGame(id="game-c", title="Game C", platform="snes"),
    ]
    sections = _sections_from_collections(catalog)
    favoritos = [s for s in sections if s.title == "Favoritos"]
    assert len(favoritos) == 1, f"esperava a seção Favoritos, viu {[s.title for s in sections]}"
    # membros convertidos para o id canônico (sem o prefixo emulation:)
    assert set(favoritos[0].items) == {"game-a", "game-b"}
    assert favoritos[0].id.startswith("collection-")


def test_empty_collection_is_not_a_section() -> None:
    """Uma coleção sem membros não vira uma seção vazia na home."""
    catalog = [CatalogGame(id="game-c", title="Game C", platform="snes")]
    sections = _sections_from_collections(catalog)
    assert all(s.title != "Favoritos" for s in sections)
