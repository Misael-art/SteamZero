# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors

from __future__ import annotations

from pathlib import Path

import pytest

from steamzero.adapters.emulation import EmulationController, SessionSecretStore
from steamzero.core.errors import SteamZeroError
from steamzero.core.secret import Secret
from steamzero.core.state import StateStore
from steamzero.ports import SecretStorePort


def _controller(tmp_path: Path) -> EmulationController:
    return EmulationController(
        store_factory=lambda: StateStore(tmp_path / "state.db"),
        which=lambda _command: None,
        spawn=lambda _argv: None,
    )


class TestSessionSecretStore:
    def test_store_and_retrieve(self) -> None:
        store: SecretStorePort = SessionSecretStore()
        store.store("steamgriddb", "api_key", Secret("abc-123"))
        retrieved = store.retrieve("steamgriddb", "api_key")
        assert retrieved is not None
        assert retrieved.reveal() == "abc-123"

    def test_retrieve_nonexistent(self) -> None:
        store: SecretStorePort = SessionSecretStore()
        assert store.retrieve("nonexistent", "key") is None

    def test_retrieve_nonexistent_key(self) -> None:
        store: SecretStorePort = SessionSecretStore()
        store.store("provider", "existing", Secret("val"))
        assert store.retrieve("provider", "nonexistent") is None

    def test_delete_removes(self) -> None:
        store: SecretStorePort = SessionSecretStore()
        store.store("steamgriddb", "api_key", Secret("abc"))
        store.delete("steamgriddb", "api_key")
        assert store.retrieve("steamgriddb", "api_key") is None

    def test_delete_nonexistent(self) -> None:
        store: SecretStorePort = SessionSecretStore()
        store.delete("never-stored", "key")

    def test_multiple_providers_isolated(self) -> None:
        store: SecretStorePort = SessionSecretStore()
        store.store("provider-a", "api_key", Secret("secret-a"))
        store.store("provider-b", "api_key", Secret("secret-b"))
        assert store.retrieve("provider-a", "api_key").reveal() == "secret-a"  # type: ignore[union-attr]
        assert store.retrieve("provider-b", "api_key").reveal() == "secret-b"  # type: ignore[union-attr]

    def test_overwrite(self) -> None:
        store: SecretStorePort = SessionSecretStore()
        store.store("steamgriddb", "api_key", Secret("old"))
        store.store("steamgriddb", "api_key", Secret("new"))
        assert store.retrieve("steamgriddb", "api_key").reveal() == "new"  # type: ignore[union-attr]


class TestEmulationControllerCredential:
    def test_credential_status_not_configured(self, tmp_path: Path) -> None:
        ctrl = _controller(tmp_path)
        status = ctrl.credential_status()
        assert status == {"steamgriddb": {"configured": False}}

    def test_credential_status_configured(self, tmp_path: Path) -> None:
        ctrl = _controller(tmp_path)
        ctrl.save_credential("steamgriddb", "my-key")
        status = ctrl.credential_status()
        assert status == {"steamgriddb": {"configured": True}}

    def test_save_and_delete_credential(self, tmp_path: Path) -> None:
        ctrl = _controller(tmp_path)
        save_result = ctrl.save_credential("steamgriddb", "my-key")
        assert save_result == {"provider": "steamgriddb", "configured": True}
        delete_result = ctrl.delete_credential("steamgriddb")
        assert delete_result == {"provider": "steamgriddb", "configured": False}
        status = ctrl.credential_status()
        assert status == {"steamgriddb": {"configured": False}}

    def test_test_credential_missing_key(self, tmp_path: Path) -> None:
        ctrl = _controller(tmp_path)
        result = ctrl.test_credential("steamgriddb")
        assert result == {
            "provider": "steamgriddb",
            "valid": False,
            "error": "E-SCRAPE-CREDENTIAL-MISSING",
        }

    def test_multiple_saves_same_provider_replaces(self, tmp_path: Path) -> None:
        ctrl = _controller(tmp_path)
        ctrl.save_credential("steamgriddb", "first")
        ctrl.save_credential("steamgriddb", "second")
        status = ctrl.credential_status()
        assert status == {"steamgriddb": {"configured": True}}
        # original key is gone — only last one remains
        assert ctrl._secret_store.retrieve("steamgriddb", "api_key").reveal() == "second"  # type: ignore[union-attr]

    def test_delete_nonexistent_credential(self, tmp_path: Path) -> None:
        ctrl = _controller(tmp_path)
        result = ctrl.delete_credential("steamgriddb")
        assert result == {"provider": "steamgriddb", "configured": False}


class TestSteamGridDbAdapterErrors:
    def test_search_without_api_key_raises(self) -> None:
        from steamzero.adapters.scraping.steamgriddb import SteamGridDbAdapter
        from steamzero.ports import GameIdentity

        adapter = SteamGridDbAdapter()
        identity = GameIdentity(
            game_id="test", title="Test Game", platform_slug="switch"
        )
        with pytest.raises(SteamZeroError, match="E-SCRAPE-CREDENTIAL-MISSING"):
            adapter.search(identity, ["boxart"])

    def test_test_connection_without_key_raises(self) -> None:
        from steamzero.adapters.scraping.steamgriddb import SteamGridDbAdapter

        adapter = SteamGridDbAdapter()
        with pytest.raises(SteamZeroError, match="E-SCRAPE-CREDENTIAL-MISSING"):
            adapter.test_connection()

    def test_search_with_invalid_key_returns_empty(self) -> None:
        from steamzero.adapters.scraping.steamgriddb import SteamGridDbAdapter
        from steamzero.ports import GameIdentity

        adapter = SteamGridDbAdapter(api_key="invalid-key-that-will-be-rejected")
        identity = GameIdentity(
            game_id="test", title="Test Game", platform_slug="switch",
            title_id="0100ABCDEF123000",
        )
        # A invalid key with network access will get 401 — handled as empty
        result = adapter.search(identity, ["boxart"])
        assert result == []


class TestGetProviderApiKey:
    def test_get_provider_api_key_returns_secret_value(self, tmp_path: Path) -> None:
        ctrl = _controller(tmp_path)
        ctrl.save_credential("steamgriddb", "my-secret-key")
        key = ctrl._get_provider_api_key("steamgriddb")
        assert key == "my-secret-key"

    def test_get_provider_api_key_no_credential_returns_none(self, tmp_path: Path) -> None:
        ctrl = _controller(tmp_path)
        key = ctrl._get_provider_api_key("steamgriddb")
        assert key is None

    def test_get_provider_api_key_wrong_provider_returns_none(self, tmp_path: Path) -> None:
        ctrl = _controller(tmp_path)
        ctrl.save_credential("steamgriddb", "key")
        key = ctrl._get_provider_api_key("other-provider")
        assert key is None


class TestMediaSearchJobHandlerErrors:
    def test_job_handler_without_api_key_returns_provider_error(self, tmp_path: Path) -> None:
        from steamzero.adapters.state_store_media import StateStoreGameMediaAdapter
        from steamzero.domain.switch_media import GameMediaManager
        from steamzero.jobs.manager import JobManager

        ctrl = _controller(tmp_path)
        job_store = StateStore(tmp_path / "job.db")
        job_store.migrate()
        ctrl._jobs = JobManager(job_store)
        ctrl._jobs.register("media.search", ctrl._media_search_job_handler)
        media_store = StateStore(tmp_path / "media.db")
        media_store.migrate()
        conn = media_store.adapter_connection()
        mgr = GameMediaManager(
            store=StateStoreGameMediaAdapter(conn),
            pipeline=None,  # type: ignore[arg-type]
            providers=[],
        )
        ctrl._media_manager = lambda _store: mgr
        job = ctrl._jobs.create(
            "media.search",
            params={
                "game_id": "test-game",
                "title_id": "",
                "title": "Test Game",
                "media_kinds": ["boxart"],
            },
            priority="interactive",
            created_by="ui",
        )
        ctrl._jobs.run(job.id)
        status = ctrl.get_job_status(job.id)
        assert status is not None
        assert status["state"] == "completed"
        result = status.get("result", {})
        assert result.get("provider_errors") == {"steamgriddb": "E-SCRAPE-CREDENTIAL-MISSING"}
        assert result.get("candidate_count") == 0
