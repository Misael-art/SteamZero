# SPDX-License-Identifier: GPL-3.0-or-later

import pytest

from steamzero.domain.scraping_providers import PROVIDERS, allowed_external_url, provider_by_id


def test_provider_catalog_never_exposes_credential_values() -> None:
    status = [provider.public_dict(configured=False) for provider in PROVIDERS]
    assert {provider["id"] for provider in status} == {
        "steamgriddb",
        "screenscraper",
        "igdb",
        "steam-local",
        "steam-web-api",
    }
    assert all(
        "value" not in field for provider in status for field in provider["credentialFields"]
    )


def test_official_urls_are_exact_and_allowlisted() -> None:
    assert allowed_external_url("steamgriddb", "credentials") == (
        "https://www.steamgriddb.com/profile/preferences/api"
    )
    assert allowed_external_url("screenscraper", "createAccount") == (
        "https://main.screenscraper.fr/membreinscription.php"
    )
    assert allowed_external_url("screenscraper", "documentation") == (
        "https://www.screenscraper.fr/webapi2.php"
    )
    assert (
        allowed_external_url("steam-web-api", "credentials")
        == "https://steamcommunity.com/dev/apikey"
    )


def test_arbitrary_provider_and_url_are_rejected() -> None:
    with pytest.raises(ValueError, match="provedor não permitido"):
        provider_by_id("https://example.invalid")
    with pytest.raises(ValueError, match="link externo não permitido"):
        allowed_external_url("steamgriddb", "https://example.invalid")
    with pytest.raises(ValueError, match="link externo não permitido"):
        allowed_external_url("steam-local", "credentials")
