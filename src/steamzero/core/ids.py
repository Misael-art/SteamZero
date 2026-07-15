# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Identificadores: ULID e slugs.

- ULID (26 chars, Crockford base32) para IDs monotônicos: jobs, operações,
  correlation IDs. Regex normativa: ``^[0-9A-HJKMNP-TV-Z]{26}$`` (JSON-SCHEMAS §2).
- Slug (``^[a-z0-9][a-z0-9-]{0,62}$``) para nomes estáveis (mesma regra do
  ``pz_boot_valid_id`` do PhaseZero, common.sh:346) — reimplementação limpa.
"""

from __future__ import annotations

import re
import secrets
import time

# Crockford base32: exclui I, L, O, U — casa com a regex normativa do ULID.
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")

_TIMESTAMP_BITS = 48
_RANDOM_BITS = 80


def new_ulid(*, ts_ms: int | None = None) -> str:
    """Gera um ULID de 128 bits (48 de tempo em ms + 80 de aleatoriedade).

    ``ts_ms`` permite tempo determinístico em testes. A ordenação lexicográfica
    dos ULIDs gerados em ms distintos reflete a ordem temporal.
    """
    if ts_ms is None:
        ts_ms = time.time_ns() // 1_000_000
    if not 0 <= ts_ms < (1 << _TIMESTAMP_BITS):
        raise ValueError(f"timestamp fora de 48 bits: {ts_ms}")
    randomness = int.from_bytes(secrets.token_bytes(_RANDOM_BITS // 8), "big")
    value = (ts_ms << _RANDOM_BITS) | randomness
    chars = [""] * 26
    for i in range(25, -1, -1):
        chars[i] = _CROCKFORD[value & 0x1F]
        value >>= 5
    return "".join(chars)


def is_ulid(value: str) -> bool:
    """True se ``value`` é um ULID válido segundo a regex normativa."""
    return bool(ULID_RE.match(value))


def is_slug(value: str) -> bool:
    """True se ``value`` é um slug válido (nome estável de entidade)."""
    return bool(SLUG_RE.match(value))


def require_slug(value: str) -> str:
    """Retorna ``value`` se for slug válido; caso contrário levanta ValueError."""
    if not is_slug(value):
        raise ValueError(f"slug inválido: {value!r}")
    return value
