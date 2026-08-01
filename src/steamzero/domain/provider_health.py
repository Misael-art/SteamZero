# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Health persistido dos providers de mídia (G28).

Contém apenas dados sanitizados: códigos e categorias do catálogo estável e
timestamps UTC ISO. Nunca credenciais, corpos de resposta, URLs com segredos
ou mensagens arbitrárias do provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

CIRCUIT_OPEN_THRESHOLD = 5


@dataclass
class ProviderHealth:
    """Estado observado de um provider de mídia.

    ``state`` é ``active`` (últimas tentativas ok) ou ``inactive`` (circuit
    breaker aberto por falhas consecutivas). ``last_error`` é o timestamp UTC
    ISO da última falha; ``last_error_code``/``last_error_category`` vêm do
    catálogo estável.
    """

    provider: str
    state: str = "active"
    last_ok: str | None = None
    last_error: str | None = None
    last_error_code: str | None = None
    last_error_category: str | None = None
    error_count: int = 0
    consecutive_failures: int = 0
    circuit_open_since: str | None = None
    total_requests: int = 0


class ProviderHealthStorePort(Protocol):
    def record_success(self, provider: str, *, byte_count: int = 0) -> None: ...

    def record_failure(self, provider: str, *, error_code: str) -> None: ...

    def list_all(self) -> list[ProviderHealth]: ...

    def load(self, provider: str) -> ProviderHealth | None: ...
