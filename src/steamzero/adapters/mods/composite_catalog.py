# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Catálogo composto que agrega múltiplas fontes de mods.

A ordem das fontes define a precedência: resultados de fontes anteriores
têm prioridade. ``CompositeModCatalog`` implementa ``ModCatalogPort`` para
ser usado como fonte única pelo domínio.
"""

from __future__ import annotations

import logging

from steamzero.ports import ModCandidate, ModCatalogPort

_log = logging.getLogger(__name__)


class CompositeModCatalog(ModCatalogPort):
    """Agrega múltiplas fontes com precedência."""

    def __init__(self, sources: list[ModCatalogPort]) -> None:
        self._sources = list(sources)

    def search_by_title_id(self, title_id: str) -> list[ModCandidate]:
        seen: set[tuple[str, str, str]] = set()
        results: list[ModCandidate] = []
        for source in self._sources:
            try:
                candidates = source.search_by_title_id(title_id)
                for c in candidates:
                    key = (c.title_id, c.identity.name, c.identity.source)
                    if key not in seen:
                        seen.add(key)
                        results.append(c)
            except Exception as exc:
                _log.debug("composite source %s erro: %s", source, exc)
        return results

    def search_by_build_id(self, title_id: str, build_id: str) -> list[ModCandidate]:
        seen: set[tuple[str, str, str]] = set()
        results: list[ModCandidate] = []
        for source in self._sources:
            try:
                candidates = source.search_by_build_id(title_id, build_id)
                for c in candidates:
                    key = (c.title_id, c.identity.name, c.identity.source)
                    if key not in seen:
                        seen.add(key)
                        results.append(c)
            except Exception as exc:
                _log.debug("composite source %s erro: %s", source, exc)
        return results

    def refresh_catalog(self) -> int:
        total = 0
        for source in self._sources:
            try:
                total += source.refresh_catalog()
            except Exception as exc:
                _log.debug("composite source %s refresh erro: %s", source, exc)
        return total
