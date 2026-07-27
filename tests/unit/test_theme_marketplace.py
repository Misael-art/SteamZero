from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from steamzero.core.errors import SteamZeroError
from steamzero.domain.theme_marketplace import MarketplaceTheme, ThemeMarketplace

_CATALOG = {
    "schemaVersion": 1,
    "generatedAt": "2026-07-27T12:00:00Z",
    "entries": [
        {
            "id": "org.steamzero.steamdeck",
            "name": "Steam Deck",
            "version": "1.0.0",
            "author": "SteamZero",
            "license": "GPL-3.0-or-later",
            "description": "Tema inspirado no Steam Deck.",
            "compatibility": {"themeApi": 1},
            "curated": True,
            "verified": True,
            "downloadUrl": "https://themes.example.org/steamdeck.zip",
            "checksumSha256": "a" * 64,
            "size": 1024000,
            "tags": ["dark", "gaming"],
            "rating": 4.5,
            "downloadCount": 1200,
            "homepage": "https://example.com/steamdeck",
        },
        {
            "id": "org.steamzero.minimal",
            "name": "Minimal",
            "version": "2.0.0",
            "author": "Community",
            "license": "MIT",
            "description": "Tema minimalista e leve.",
            "compatibility": {"themeApi": 1},
            "curated": False,
            "verified": True,
            "downloadUrl": "https://themes.example.org/minimal.zip",
            "checksumSha256": "",
            "size": 204800,
            "tags": ["light", "minimal"],
            "rating": 4.0,
            "downloadCount": 340,
            "homepage": "",
        },
    ],
}


def _catalog_bytes() -> bytes:
    return json.dumps(_CATALOG).encode()


def _enable_marketplace(url: str = "https://themes.example.org/catalog-v1.json") -> None:
    """Escreve o opt-in explícito. Sem ele o marketplace nasce desligado."""
    from steamzero.core import paths

    path = paths.theme_marketplace_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schemaVersion": 1, "enabled": True, "catalogUrl": url}))


@pytest.fixture(autouse=True)
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("STEAMZERO_THEMES_CATALOG_URL", raising=False)
    monkeypatch.setattr(
        "steamzero.domain.theme_marketplace.fetch_bytes",
        lambda url, **kw: _catalog_bytes(),
    )
    _enable_marketplace()


class TestMarketplaceTheme:
    def test_from_dict_full(self) -> None:
        raw = _CATALOG["entries"][0]
        t = MarketplaceTheme.from_dict(raw)
        assert t.id == "org.steamzero.steamdeck"
        assert t.name == "Steam Deck"
        assert t.curated is True
        assert t.verified is True
        assert t.checksum_sha256 == "a" * 64
        assert t.size == 1024000
        assert t.rating == 4.5
        assert t.tags == ["dark", "gaming"]

    def test_from_dict_minimal(self) -> None:
        raw = {"id": "test.id"}
        t = MarketplaceTheme.from_dict(raw)
        assert t.id == "test.id"
        assert t.name == ""
        assert t.curated is False
        assert t.size == 0

    def test_to_dict_roundtrip(self) -> None:
        raw = _CATALOG["entries"][0]
        t = MarketplaceTheme.from_dict(raw)
        d = t.to_dict()
        assert d["id"] == "org.steamzero.steamdeck"
        assert d["curated"] is True


class TestThemeMarketplaceSearch:
    def test_search_all(self) -> None:
        m = ThemeMarketplace()
        results = m.search()
        assert len(results) == 2

    def test_search_by_name(self) -> None:
        m = ThemeMarketplace()
        results = m.search("steam deck")
        assert len(results) == 1
        assert results[0].id == "org.steamzero.steamdeck"

    def test_search_by_tag(self) -> None:
        m = ThemeMarketplace()
        results = m.search("minimal")
        assert len(results) == 1
        assert results[0].id == "org.steamzero.minimal"

    def test_search_by_author(self) -> None:
        m = ThemeMarketplace()
        results = m.search("community")
        assert len(results) == 1
        assert results[0].id == "org.steamzero.minimal"

    def test_search_no_match(self) -> None:
        m = ThemeMarketplace()
        results = m.search("zzznonexistent")
        assert len(results) == 0

    def test_search_empty_query(self) -> None:
        m = ThemeMarketplace()
        results = m.search("")
        assert len(results) == 2


class TestThemeMarketplaceGet:
    def test_get_existing(self) -> None:
        m = ThemeMarketplace()
        t = m.get("org.steamzero.steamdeck")
        assert t.name == "Steam Deck"

    def test_get_missing_raises(self) -> None:
        m = ThemeMarketplace()
        with pytest.raises(SteamZeroError, match=r"E-THEME-NOT-FOUND"):
            m.get("nonexistent")


class TestThemeMarketplaceCatalog:
    def test_fetch_populates_entries(self) -> None:
        m = ThemeMarketplace()
        results = m.search()
        assert len(results) == 2

    def test_cache_hit(self) -> None:
        m = ThemeMarketplace()
        m.search()
        cache_dir = Path(os.environ["XDG_CACHE_HOME"]) / "steamzero"
        cache_path = cache_dir / "theme-catalog-v1.json"
        assert cache_path.is_file()
        cached = json.loads(cache_path.read_bytes())
        assert len(cached["entries"]) == 2

    def test_invalid_catalog_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "steamzero.domain.theme_marketplace.fetch_bytes",
            lambda url, **kw: b"not-json",
        )
        m = ThemeMarketplace()
        with pytest.raises(SteamZeroError, match=r"E-THEME-CATALOG-FAILED"):
            m.search()

    def test_missing_entries_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "steamzero.domain.theme_marketplace.fetch_bytes",
            lambda url, **kw: json.dumps({"v": 1}).encode(),
        )
        m = ThemeMarketplace()
        with pytest.raises(SteamZeroError, match=r"E-THEME-CATALOG-FAILED"):
            m.search()

    def test_stale_cache_fallback(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        from steamzero.core import paths

        cache_path = paths.theme_catalog_cache_path()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(_catalog_bytes())

        monkeypatch.setattr(
            "steamzero.domain.theme_marketplace.fetch_bytes",
            lambda url, **kw: (_ for _ in ()).throw(ConnectionError("offline")),
        )
        m = ThemeMarketplace()
        results = m.search()
        assert len(results) == 2


class TestThemeMarketplaceInstall:
    def test_install_by_id_delegates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from steamzero.domain.theme_install import ThemeInstaller

        captured: dict[str, object] = {}

        def fake_install(self_inst, source, **kw):
            captured["source"] = source
            captured["kw"] = kw
            return {"themeId": "org.steamzero.steamdeck", "name": "Steam Deck", "version": "1.0.0"}

        monkeypatch.setattr(ThemeInstaller, "install", fake_install)
        m = ThemeMarketplace()
        result = m.install("org.steamzero.steamdeck")
        assert result["themeId"] == "org.steamzero.steamdeck"
        assert captured["source"] == "https://themes.example.org/steamdeck.zip"

    def test_install_no_download_url_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        bad = _CATALOG.copy()
        bad["entries"] = [{"id": "no.url", "name": "No URL"}]
        monkeypatch.setattr(
            "steamzero.domain.theme_marketplace.fetch_bytes",
            lambda url, **kw: json.dumps(bad).encode(),
        )
        m = ThemeMarketplace()
        with pytest.raises(SteamZeroError, match=r"não possui URL"):
            m.install("no.url")

    def test_install_passes_checksum(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from steamzero.domain.theme_install import ThemeInstaller

        captured: dict[str, object] = {}

        def fake_install(self_inst, source, **kw):
            captured["checksum_sha256"] = kw.get("checksum_sha256")
            return {"themeId": "x", "name": "x", "version": "1.0.0"}

        monkeypatch.setattr(ThemeInstaller, "install", fake_install)
        m = ThemeMarketplace()
        m.install("org.steamzero.steamdeck")
        assert captured["checksum_sha256"] == "a" * 64

    def test_install_without_checksum_fails_closed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Catálogo sem checksum é origem inverificável: recusar, não instalar."""
        from steamzero.domain.theme_install import ThemeInstaller

        def explode(self_inst, source, **kw):  # pragma: no cover - não deve rodar
            raise AssertionError("install não pode ser alcançado sem checksum")

        monkeypatch.setattr(ThemeInstaller, "install", explode)
        m = ThemeMarketplace()
        with pytest.raises(SteamZeroError, match=r"E-SUPPLY-NO-CHECKSUM"):
            m.install("org.steamzero.minimal")


class TestMarketplaceDisabledByDefault:
    """O marketplace remoto não existe até o operador habilitá-lo."""

    def test_disabled_without_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from steamzero.core import paths

        paths.theme_marketplace_config_path().unlink()
        m = ThemeMarketplace()
        assert m.enabled is False
        with pytest.raises(SteamZeroError, match=r"E-THEME-MARKETPLACE-DISABLED"):
            m.search()

    def test_disabled_config_present_but_off(self) -> None:
        from steamzero.core import paths

        paths.theme_marketplace_config_path().write_text(
            json.dumps({"schemaVersion": 1, "enabled": False, "catalogUrl": "https://x.test/c"})
        )
        m = ThemeMarketplace()
        assert m.enabled is False
        with pytest.raises(SteamZeroError, match=r"E-THEME-MARKETPLACE-DISABLED"):
            m.get("org.steamzero.steamdeck")

    def test_env_var_alone_does_not_enable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A variável escolhe endereço; quem habilita é a configuração."""
        from steamzero.core import paths

        paths.theme_marketplace_config_path().unlink()
        monkeypatch.setenv("STEAMZERO_THEMES_CATALOG_URL", "https://evil.test/catalog.json")
        m = ThemeMarketplace()
        assert m.enabled is False
        with pytest.raises(SteamZeroError, match=r"E-THEME-MARKETPLACE-DISABLED"):
            m.search()

    def test_enabled_without_url_stays_disabled(self) -> None:
        from steamzero.core import paths

        paths.theme_marketplace_config_path().write_text(
            json.dumps({"schemaVersion": 1, "enabled": True, "catalogUrl": ""})
        )
        assert ThemeMarketplace().enabled is False

    def test_no_builtin_catalog_host(self) -> None:
        """Nenhum host embutido pode voltar como default."""
        import steamzero.domain.theme_marketplace as mod

        source = Path(mod.__file__).read_text(encoding="utf-8")
        assert "steamzero.org" not in source


class TestCatalogUrlValidation:
    def test_rejects_plain_http(self) -> None:
        with pytest.raises(SteamZeroError, match=r"E-THEME-CATALOG-FAILED"):
            ThemeMarketplace(catalog_url="http://themes.example.org/c.json")

    def test_rejects_url_without_host(self) -> None:
        with pytest.raises(SteamZeroError, match=r"E-THEME-CATALOG-FAILED"):
            ThemeMarketplace(catalog_url="https:///c.json")

    def test_rejects_embedded_credentials(self) -> None:
        with pytest.raises(SteamZeroError, match=r"credencial"):
            ThemeMarketplace(catalog_url="https://user:pw@themes.example.org/c.json")


class TestCatalogHostileInput:
    """Catálogo malformado degrada em erro estruturado, nunca exceção crua."""

    def _serve(self, monkeypatch: pytest.MonkeyPatch, doc: object) -> ThemeMarketplace:
        monkeypatch.setattr(
            "steamzero.domain.theme_marketplace.fetch_bytes",
            lambda url, **kw: json.dumps(doc).encode(),
        )
        return ThemeMarketplace()

    def test_entry_without_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        m = self._serve(monkeypatch, {"entries": [{"name": "sem id"}]})
        with pytest.raises(SteamZeroError, match=r"E-THEME-CATALOG-FAILED"):
            m.search()

    def test_entry_with_non_numeric_size(self, monkeypatch: pytest.MonkeyPatch) -> None:
        m = self._serve(monkeypatch, {"entries": [{"id": "a.b", "size": "muito grande"}]})
        with pytest.raises(SteamZeroError, match=r"E-THEME-CATALOG-FAILED"):
            m.search()

    def test_entry_with_non_numeric_rating(self, monkeypatch: pytest.MonkeyPatch) -> None:
        m = self._serve(monkeypatch, {"entries": [{"id": "a.b", "rating": "ótimo"}]})
        with pytest.raises(SteamZeroError, match=r"E-THEME-CATALOG-FAILED"):
            m.search()

    def test_entry_with_non_string_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        m = self._serve(monkeypatch, {"entries": [{"id": 42}]})
        with pytest.raises(SteamZeroError, match=r"E-THEME-CATALOG-FAILED"):
            m.search()
