# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Tipo ``Secret`` com repr mascarado (SR-13).

Segredos (tokens, keys) nunca aparecem em logs/argv/state em claro. Envolva o
valor em ``Secret``; o log handler (core.log) mascara automaticamente qualquer
``Secret`` nos campos. ``reveal()`` é o único caminho para o valor real e deve
ser chamado apenas no ponto de uso (ex.: header de autenticação), nunca logado.
"""

from __future__ import annotations

MASK = "***"


class Secret:
    """Envelope de valor sensível. ``repr``/``str`` mascarados; ``reveal()`` expõe."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return f"Secret({MASK!r})"

    def __str__(self) -> str:
        return MASK
