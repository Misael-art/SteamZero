# SPDX-License-Identifier: GPL-3.0-or-later
"""Secret Service user-scoped para credenciais do SteamZero.

Os valores transitam apenas pelo stdin de ``secret-tool``. Nunca são gravados
no StateStore, planos, jobs, snapshots ou argumentos de processo.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable

from steamzero.core.errors import SteamZeroError
from steamzero.core.secret import Secret

Runner = Callable[..., subprocess.CompletedProcess[str]]
Which = Callable[[str], str | None]


class SecretServiceStore:
    """Implementa ``SecretStorePort`` com o Secret Service do usuário."""

    def __init__(self, *, runner: Runner = subprocess.run, which: Which = shutil.which) -> None:
        self._runner = runner
        self._which = which

    @staticmethod
    def _attributes(provider: str, key_name: str) -> tuple[str, ...]:
        return ("application", "steamzero", "provider", provider, "key", key_name)

    def is_available(self) -> bool:
        return self._which("secret-tool") is not None

    def _command(self, action: str, provider: str, key_name: str) -> list[str]:
        executable = self._which("secret-tool")
        if executable is None:
            raise SteamZeroError(
                "E-SCRAPE-CREDENTIAL-MISSING", detail="Secret Service indisponível"
            )
        return [executable, action, *self._attributes(provider, key_name)]

    def store(self, provider: str, key_name: str, secret: Secret) -> None:
        command = self._command("store", provider, key_name)
        command.insert(2, "--label=SteamZero scraping credential")
        result = self._runner(
            command,
            input=secret.reveal(),
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise SteamZeroError(
                "E-SCRAPE-CREDENTIAL-MISSING",
                detail="não foi possível salvar no Secret Service",
            )

    def retrieve(self, provider: str, key_name: str) -> Secret | None:
        result = self._runner(
            self._command("lookup", provider, key_name),
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            return None
        value = result.stdout.rstrip("\n")
        return Secret(value) if value else None

    def delete(self, provider: str, key_name: str) -> None:
        result = self._runner(
            self._command("clear", provider, key_name),
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise SteamZeroError(
                "E-SCRAPE-CREDENTIAL-MISSING",
                detail="não foi possível remover do Secret Service",
            )
