# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Guarda de rede para a suíte de scraping: nenhum teste toca a internet.

A suíte de scraping só usa transporte injetado (``HttpClient`` com
``FakeTransport``) ou ``_fetch_url`` substituído por fixture. Se algum teste
acidentalmente alcançar o transport real, ``urllib.request.urlopen`` falha
aqui com AssertionError em vez de abrir conexão.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _block_real_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _no_real_network(*_args: object, **_kwargs: object) -> object:
        raise AssertionError(
            "teste de scraping tentou abrir conexão real; use HttpClient "
            "com FakeTransport ou monkeypatch em _fetch_url"
        )

    monkeypatch.setattr("urllib.request.urlopen", _no_real_network)
