# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors

from __future__ import annotations

import json
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
        secret_store=SessionSecretStore(),
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
        steamgriddb = next(
            provider for provider in status["providers"] if provider["id"] == "steamgriddb"
        )
        assert steamgriddb["configured"] is False
        assert steamgriddb["credentialState"] == "notConfigured"
        assert steamgriddb["missingRequiredFields"] == ["api_key"]
        assert steamgriddb["canTestCredential"] is False

    def test_credential_status_configured(self, tmp_path: Path) -> None:
        ctrl = _controller(tmp_path)
        ctrl.save_credential("steamgriddb", "my-key")
        status = ctrl.credential_status()
        steamgriddb = next(
            provider for provider in status["providers"] if provider["id"] == "steamgriddb"
        )
        assert steamgriddb["configured"] is True
        assert steamgriddb["credentialState"] == "stored"
        assert steamgriddb["canTestCredential"] is True
        assert "my-key" not in json.dumps(status, sort_keys=True)

    def test_save_and_delete_credential(self, tmp_path: Path) -> None:
        ctrl = _controller(tmp_path)
        save_result = ctrl.save_credential("steamgriddb", "my-key")
        assert save_result["provider"] == "steamgriddb"
        assert save_result["configured"] is True
        assert save_result["state"] == "stored"
        delete_result = ctrl.delete_credential("steamgriddb")
        assert delete_result["provider"] == "steamgriddb"
        assert delete_result["configured"] is False
        assert delete_result["state"] == "notConfigured"
        status = ctrl.credential_status()
        steamgriddb = next(
            provider for provider in status["providers"] if provider["id"] == "steamgriddb"
        )
        assert steamgriddb["configured"] is False

    def test_test_credential_missing_key(self, tmp_path: Path) -> None:
        ctrl = _controller(tmp_path)
        result = ctrl.test_credential("steamgriddb")
        assert result["provider"] == "steamgriddb"
        assert result["valid"] is False
        assert result["state"] == "notConfigured"
        assert result["error"] == "E-SCRAPE-CREDENTIAL-MISSING"

    def test_multiple_saves_same_provider_replaces(self, tmp_path: Path) -> None:
        ctrl = _controller(tmp_path)
        ctrl.save_credential("steamgriddb", "first")
        ctrl.save_credential("steamgriddb", "second")
        status = ctrl.credential_status()
        steamgriddb = next(
            provider for provider in status["providers"] if provider["id"] == "steamgriddb"
        )
        assert steamgriddb["configured"] is True
        # original key is gone — only last one remains
        assert ctrl._secret_store.retrieve("steamgriddb", "api_key").reveal() == "second"  # type: ignore[union-attr]

    def test_delete_nonexistent_credential(self, tmp_path: Path) -> None:
        ctrl = _controller(tmp_path)
        result = ctrl.delete_credential("steamgriddb")
        assert result["provider"] == "steamgriddb"
        assert result["configured"] is False
        assert result["state"] == "notConfigured"

    def test_screenscraper_reports_exact_missing_required_fields(
        self, tmp_path: Path
    ) -> None:
        ctrl = _controller(tmp_path)
        with pytest.raises(SteamZeroError, match="devpassword"):
            ctrl.save_credential("screenscraper", {"devid": "developer-id"})
        status = ctrl.credential_status()
        screenscraper = next(
            provider for provider in status["providers"] if provider["id"] == "screenscraper"
        )
        assert screenscraper["missingRequiredFields"] == ["devid", "devpassword"]

    def test_screenscraper_four_fields_are_isolated_tested_and_revoked(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from steamzero.adapters.scraping.screenscraper import ScreenScraperAdapter

        ctrl = _controller(tmp_path)
        values = {
            "devid": "integration-id",
            "devpassword": "integration-secret",
            "ssid": "personal-user",
            "sspassword": "personal-secret",
        }
        saved = ctrl.save_credential("screenscraper", values)
        assert saved["state"] == "stored"
        for field, expected in values.items():
            secret = ctrl._secret_store.retrieve("screenscraper", field)
            assert secret is not None and secret.reveal() == expected
        assert not any(
            value in json.dumps(saved, sort_keys=True) for value in values.values()
        )

        monkeypatch.setattr(ScreenScraperAdapter, "test_connection", lambda _self: True)
        tested = ctrl.test_credential("screenscraper")
        assert tested["valid"] is True
        assert tested["state"] == "validated"
        assert not any(
            value in json.dumps(tested, sort_keys=True) for value in values.values()
        )

        with ctrl._store_factory() as store:
            store.migrate()
            manager = ctrl._media_manager(store)
            screen_provider = next(
                provider for provider in manager._providers if provider.name == "screenscraper"
            )
            assert isinstance(screen_provider, ScreenScraperAdapter)

        revoked = ctrl.delete_credential("screenscraper")
        assert revoked["state"] == "notConfigured"
        assert all(
            ctrl._secret_store.retrieve("screenscraper", field) is None for field in values
        )

    def test_screenscraper_optional_account_is_not_required(self, tmp_path: Path) -> None:
        ctrl = _controller(tmp_path)
        saved = ctrl.save_credential(
            "screenscraper",
            {"devid": "integration-id", "devpassword": "integration-secret"},
        )
        assert saved["configured"] is True
        assert saved["providerStatus"]["missingRequiredFields"] == []

    def test_local_provider_is_informational_only(self, tmp_path: Path) -> None:
        ctrl = _controller(tmp_path)
        local = next(
            provider
            for provider in ctrl.credential_status()["providers"]
            if provider["id"] == "steam-local"
        )
        assert local["credentialState"] == "local"
        assert local["credentialFields"] == []
        assert local["links"] == {}
        assert local["canTestCredential"] is False
        assert local["canRevokeCredential"] is False
        with pytest.raises(SteamZeroError, match="não aceita credenciais"):
            ctrl.save_credential("steam-local", {})

    def test_rejected_test_keeps_secret_and_updates_status(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from steamzero.adapters.scraping.steamgriddb import SteamGridDbAdapter

        ctrl = _controller(tmp_path)
        ctrl.save_credential("steamgriddb", "never-serialized")
        monkeypatch.setattr(SteamGridDbAdapter, "test_connection", lambda _self: False)
        result = ctrl.test_credential("steamgriddb")
        assert result["valid"] is False
        assert result["state"] == "rejected"
        assert result["providerStatus"]["credentialState"] == "rejected"
        assert "never-serialized" not in json.dumps(result, sort_keys=True)
        assert ctrl._secret_store.retrieve("steamgriddb", "api_key") is not None

    def test_vault_unavailable_is_actionable_and_does_not_claim_configuration(
        self, tmp_path: Path
    ) -> None:
        class UnavailableStore(SessionSecretStore):
            def is_available(self) -> bool:
                return False

        ctrl = EmulationController(
            store_factory=lambda: StateStore(tmp_path / "state.db"),
            which=lambda _command: None,
            spawn=lambda _argv: None,
            secret_store=UnavailableStore(),
        )
        status = ctrl.credential_status()
        steamgriddb = next(
            provider for provider in status["providers"] if provider["id"] == "steamgriddb"
        )
        assert status["secretStoreAvailable"] is False
        assert steamgriddb["credentialState"] == "vaultUnavailable"
        with pytest.raises(SteamZeroError, match="E-SCRAPE-VAULT-UNAVAILABLE"):
            ctrl.save_credential("steamgriddb", "secret")

    def test_save_verification_failure_rolls_back_previous_secret(
        self, tmp_path: Path
    ) -> None:
        class RejectingVerificationStore(SessionSecretStore):
            reject_next_retrieve = False

            def store(self, provider: str, key_name: str, secret: Secret) -> None:
                super().store(provider, key_name, secret)
                self.reject_next_retrieve = secret.reveal() == "new"

            def retrieve(self, provider: str, key_name: str) -> Secret | None:
                if self.reject_next_retrieve:
                    self.reject_next_retrieve = False
                    return None
                return super().retrieve(provider, key_name)

        store = RejectingVerificationStore()
        store._secrets[("steamgriddb", "api_key")] = Secret("old")
        ctrl = EmulationController(
            store_factory=lambda: StateStore(tmp_path / "state.db"),
            which=lambda _command: None,
            spawn=lambda _argv: None,
            secret_store=store,
        )
        with pytest.raises(SteamZeroError, match="não confirmou"):
            ctrl.save_credential("steamgriddb", "new")
        restored = store.retrieve("steamgriddb", "api_key")
        assert restored is not None
        assert restored.reveal() == "old"

    def test_provider_link_is_limited_to_catalog_url(self, tmp_path: Path) -> None:
        calls: list[tuple[str, ...]] = []
        ctrl = EmulationController(
            store_factory=lambda: StateStore(tmp_path / "state.db"),
            which=lambda command: "/usr/bin/xdg-open" if command == "xdg-open" else None,
            spawn=lambda argv: calls.append(tuple(argv)),
            secret_store=SessionSecretStore(),
        )
        expected = {
            ("steamgriddb", "createAccount"): (
                "https://www.steamgriddb.com/profile/preferences/api"
            ),
            ("steamgriddb", "credentials"): (
                "https://www.steamgriddb.com/profile/preferences/api"
            ),
            ("steamgriddb", "documentation"): "https://www.steamgriddb.com/api/v2",
            ("steamgriddb", "terms"): "https://www.steamgriddb.com/terms",
            ("screenscraper", "createAccount"): (
                "https://main.screenscraper.fr/membreinscription.php"
            ),
            ("screenscraper", "documentation"): (
                "https://www.screenscraper.fr/webapi2.php"
            ),
            ("steam-web-api", "credentials"): "https://steamcommunity.com/dev/apikey",
        }
        for (provider, link), url in expected.items():
            assert ctrl.provider_link(provider, link) == {
                "provider": provider,
                "link": link,
                "opened": True,
            }
            assert calls[-1] == ("/usr/bin/xdg-open", url)
        call_count = len(calls)
        with pytest.raises(ValueError, match="link externo não permitido"):
            ctrl.provider_link("steamgriddb", "https://example.invalid")
        with pytest.raises(ValueError, match="provedor não permitido"):
            ctrl.provider_link("arbitrary", "documentation")
        assert len(calls) == call_count

    def test_provider_link_reports_missing_desktop_opener(self, tmp_path: Path) -> None:
        ctrl = _controller(tmp_path)
        with pytest.raises(SteamZeroError, match="E-DESKTOP-VERIFY"):
            ctrl.provider_link("steamgriddb", "credentials")


class TestSteamGridDbAdapterErrors:
    def test_search_without_api_key_raises(self) -> None:
        from steamzero.adapters.scraping.steamgriddb import SteamGridDbAdapter
        from steamzero.ports import GameIdentity

        adapter = SteamGridDbAdapter()
        identity = GameIdentity(game_id="test", title="Test Game", platform_slug="switch")
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
            game_id="test",
            title="Test Game",
            platform_slug="switch",
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
        assert status["state"] == "succeeded"
        assert status["rawState"] == "completed"
        result = status.get("result", {})
        assert result.get("provider_errors") == {"steamgriddb": "E-SCRAPE-CREDENTIAL-MISSING"}
        assert result.get("candidate_count") == 0
