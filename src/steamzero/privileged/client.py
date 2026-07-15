# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""`privileged.client` — cliente da fronteira privilegiada.

Fase 2: fala com um ``AdminHelper`` in-process (injetado). O transporte real
(pkexec/D-Bus system bus) é da Fase 6. Se o helper não está disponível, reporta
``E-PRIV-HELPER-MISSING`` com instrução — nunca faz fallback silencioso para sudo
(FM-20).
"""

from __future__ import annotations

from typing import Any

from steamzero.core.errors import SteamZeroError
from steamzero.privileged.helper import AdminHelper
from steamzero.privileged.protocol import PROTOCOL_VERSION, Request, Response


class AdminClient:
    def __init__(self, helper: AdminHelper | None, *, caller: str = "steamzero-core") -> None:
        self._helper = helper
        self._caller = caller

    def available(self) -> bool:
        return self._helper is not None

    def request(self, action: str, params: dict[str, Any]) -> Response:
        """Envia uma ação privilegiada; levanta E-PRIV-* em falha de fronteira."""
        if self._helper is None:
            raise SteamZeroError(
                "E-PRIV-HELPER-MISSING",
                detail="steamzero-admin não instalado; instale o helper para ações privilegiadas",
            )
        response = self._helper.handle(
            Request(
                action=action,
                params=params,
                protocol_version=PROTOCOL_VERSION,
                caller=self._caller,
            )
        )
        return response
