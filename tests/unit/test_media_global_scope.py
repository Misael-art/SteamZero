# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Escopo de plataforma das acoes globais de midia.

A superficie global ficou presa em Switch por uma constante: o escopo ausente
virava ``"switch"`` e qualquer outro valor era recusado. A interface parecia
preparada para plataformas, mas a acao global ignorava a plataforma escolhida.
Estes testes fixam o contrato generalizado.
"""

from __future__ import annotations

import pytest

from steamzero.adapters.emulation import EmulationController
from steamzero.core.errors import SteamZeroError

_scope = EmulationController._media_scope_from_payload  # type: ignore[attr-defined]


def test_absent_scope_means_all_systems() -> None:
    """Ausencia e "todos os sistemas", nao Switch.

    String vazia e o que ``platform_id or None`` ja traduzia como "sem filtro"
    a jusante; o default anterior contradizia o proprio consumidor.
    """
    assert _scope({}) == ""


def test_explicit_all_means_all_systems() -> None:
    assert _scope({"platformId": "all"}) == ""


@pytest.mark.parametrize("platform_id", ["switch", "playstation-4"])
def test_declared_platform_is_accepted(platform_id: str) -> None:
    """PS4 precisa passar: era exatamente o caso que a constante recusava."""
    assert _scope({"platformId": platform_id}) == platform_id


def test_unknown_platform_is_rejected_as_schema_error() -> None:
    with pytest.raises(SteamZeroError) as excinfo:
        _scope({"platformId": "plataforma-inexistente"})
    assert excinfo.value.code == "E-API-SCHEMA"


@pytest.mark.parametrize("value", [123, "", "   ", []])
def test_non_string_or_blank_scope_is_rejected(value: object) -> None:
    with pytest.raises(SteamZeroError) as excinfo:
        _scope({"platformId": value})
    assert excinfo.value.code == "E-API-SCHEMA"
