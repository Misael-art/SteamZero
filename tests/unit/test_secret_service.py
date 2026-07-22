# SPDX-License-Identifier: GPL-3.0-or-later

import subprocess

from steamzero.adapters.secret_service import SecretServiceStore
from steamzero.core.secret import Secret


def test_secret_service_passes_secret_only_through_stdin() -> None:
    calls: list[tuple[list[str], str | None]] = []

    def runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((argv, kwargs.get("input") if isinstance(kwargs.get("input"), str) else None))
        return subprocess.CompletedProcess(argv, 0, "", "")

    store = SecretServiceStore(runner=runner, which=lambda _name: "/usr/bin/secret-tool")
    store.store("steamgriddb", "api_key", Secret("secret-value"))

    argv, secret = calls[0]
    assert secret == "secret-value"
    assert "secret-value" not in argv
    assert argv[:3] == ["/usr/bin/secret-tool", "store", "--label=SteamZero scraping credential"]


def test_secret_service_lookup_uses_only_stable_attributes() -> None:
    def runner(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 0, "stored-secret\n", "")

    store = SecretServiceStore(runner=runner, which=lambda _name: "/usr/bin/secret-tool")
    value = store.retrieve("steamgriddb", "api_key")
    assert value is not None
    assert value.reveal() == "stored-secret"
