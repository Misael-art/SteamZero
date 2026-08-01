# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Persistência de health dos providers de mídia (G28)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from steamzero.adapters.state_store_provider_health import StateStoreProviderHealthAdapter
from steamzero.core.errors import provider_error_category
from steamzero.core.state import StateStore


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "state.db"
    store = StateStore(db_path)
    store.migrate()
    connection = store.adapter_connection()
    yield connection
    store.close()


def test_record_success_and_failure_roundtrip(conn: sqlite3.Connection) -> None:
    adapter = StateStoreProviderHealthAdapter(conn)
    adapter.record_failure("screenscraper", error_code="E-SCRAPE-QUOTA-EXCEEDED")
    adapter.record_failure("screenscraper", error_code="E-SCRAPE-RATE-LIMITED")

    health = adapter.load("screenscraper")
    assert health is not None
    assert health.last_error_code == "E-SCRAPE-RATE-LIMITED"
    assert health.last_error_category == "rate-limit"
    assert health.error_count == 2
    assert health.consecutive_failures == 2
    assert health.total_requests == 2
    assert health.state == "active"
    assert health.last_error is not None

    adapter.record_success("screenscraper", byte_count=42)
    health = adapter.load("screenscraper")
    assert health.last_error_code is None
    assert health.last_error_category is None
    assert health.consecutive_failures == 0
    assert health.error_count == 0
    assert health.total_requests == 3
    assert health.state == "active"
    assert health.last_ok is not None


def test_circuit_opens_after_consecutive_failures(conn: sqlite3.Connection) -> None:
    adapter = StateStoreProviderHealthAdapter(conn)
    for _ in range(5):
        adapter.record_failure("steamgriddb", error_code="E-SCRAPE-PROVIDER-UNREACHABLE")

    health = adapter.load("steamgriddb")
    assert health is not None
    assert health.consecutive_failures == 5
    assert health.state == "inactive"
    assert health.circuit_open_since is not None

    adapter.record_success("steamgriddb")
    health = adapter.load("steamgriddb")
    assert health.state == "active"
    assert health.circuit_open_since is None


def test_health_never_contains_arbitrary_details(conn: sqlite3.Connection) -> None:
    adapter = StateStoreProviderHealthAdapter(conn)
    adapter.record_failure("screenscraper", error_code="E-SCRAPE-CREDENTIAL-REJECTED")
    health = adapter.load("screenscraper")
    assert health is not None
    assert health.last_error_category == "auth"
    assert health.last_error_code == "E-SCRAPE-CREDENTIAL-REJECTED"
    assert health.last_error is not None
    serialized = " ".join(str(value) for value in health.__dict__.values())
    assert "secret" not in serialized.casefold()


def test_unknown_code_is_generic_category(conn: sqlite3.Connection) -> None:
    adapter = StateStoreProviderHealthAdapter(conn)
    adapter.record_failure("fake", error_code="E-CODIGO-DESCONHECIDO")
    health = adapter.load("fake")
    assert health is not None
    assert health.last_error_category == "generic"


def test_list_all_orders_by_provider(conn: sqlite3.Connection) -> None:
    adapter = StateStoreProviderHealthAdapter(conn)
    adapter.record_failure("screenscraper", error_code="E-SCRAPE-QUOTA-EXCEEDED")
    adapter.record_failure("steamgriddb", error_code="E-SCRAPE-PROVIDER-UNREACHABLE")
    rows = adapter.list_all()
    assert [row.provider for row in rows] == ["screenscraper", "steamgriddb"]


def test_categories_mapping_is_stable() -> None:
    assert provider_error_category("E-SCRAPE-QUOTA-EXCEEDED") == "quota"
    assert provider_error_category("E-SCRAPE-RATE-LIMITED") == "rate-limit"
    assert provider_error_category("E-SCRAPE-CREDENTIAL-REJECTED") == "auth"
    assert provider_error_category("E-SCRAPE-PROVIDER-UNREACHABLE") == "unreachable"
    assert provider_error_category("E-SCRAPE-HTTP-ERROR") == "http"
    assert provider_error_category("E-SCRAPE-CORRUPT-MEDIA") == "corrupt"
    assert provider_error_category("E-SCRAPE-VAULT-UNAVAILABLE") == "vault"
    assert provider_error_category("E-SCRAPE-DOWNLOAD-FAILED") == "download"
    assert provider_error_category("E-NET-HTTP") == "http"
    assert provider_error_category("E-NAO-REGISTRADO") == "generic"
