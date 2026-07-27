from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from steamzero.core.errors import SteamZeroError
from steamzero.core.net import FakeResponse
from steamzero.domain.theme_install import ThemeInstaller

_VALID_MANIFEST = {
    "schemaVersion": 1,
    "kind": "steamzero-theme-v1",
    "id": "org.test.installed",
    "name": "Installed",
    "version": "1.0.0",
    "author": "Tester",
    "license": "MIT",
    "compatibility": {"themeApi": 1},
    "tokens": {"color": {"background": "#ff0000"}},
}


def _make_theme_zip(
    manifest: dict | None = None,
    extra_files: dict[str, str] | None = None,
) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        tid = (manifest or _VALID_MANIFEST)["id"]
        zf.writestr(f"{tid}/theme.json", json.dumps(manifest or _VALID_MANIFEST))
        for path, content in (extra_files or {}).items():
            zf.writestr(f"{tid}/{path}", content)
    return buf.getvalue()


@pytest.fixture(autouse=True)
def env_vars(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("steamzero.domain.theme_install.fetch_bytes",
                        lambda url, **kw: _make_theme_zip())
    monkeypatch.setattr(
        "steamzero.domain.theme_install.HttpClient",
        lambda: type("FakeClient", (), {
            "get": lambda self, url, policy: FakeResponse(
                body=b"", url=url, status=200,
                headers={"Content-Length": "5000"},
            ),
        })(),
    )
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))


class TestThemeInstall:
    def test_install_from_url(self, tmp_path: Path) -> None:
        themes_dir = tmp_path / "steamzero" / "themes"
        result = ThemeInstaller().install("https://themes.example.org/theme.zip", yes=True)
        assert result["themeId"] == "org.test.installed"
        assert result["name"] == "Installed"
        assert result["version"] == "1.0.0"
        assert (themes_dir / "org.test.installed" / "theme.json").is_file()

    def test_install_from_local(self, tmp_path: Path) -> None:
        themes_dir = tmp_path / "steamzero" / "themes"
        zip_path = tmp_path / "theme.zip"
        zip_path.write_bytes(_make_theme_zip())
        result = ThemeInstaller().install(str(zip_path))
        assert result["themeId"] == "org.test.installed"
        assert (themes_dir / "org.test.installed" / "theme.json").is_file()

    def test_duplicate_without_force_raises(self, tmp_path: Path) -> None:
        ThemeInstaller().install("https://example.com/t.zip", yes=True)
        with pytest.raises(SteamZeroError, match="já instalado"):
            ThemeInstaller().install("https://example.com/t.zip", yes=True)

    def test_force_overwrites(self, tmp_path: Path) -> None:
        ThemeInstaller().install("https://example.com/t.zip", yes=True, force=True)
        ThemeInstaller().install("https://example.com/t.zip", yes=True, force=True)
        themes_dir = tmp_path / "steamzero" / "themes"
        assert (themes_dir / "org.test.installed" / "theme.json").is_file()

    def test_invalid_zip_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("steamzero.domain.theme_install.fetch_bytes",
                            lambda url, **kw: b"not-a-zip")
        with pytest.raises(SteamZeroError, match=r"não é um zip"):
            ThemeInstaller().install("https://example.com/bad.zip")

    def test_path_traversal_zip_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("../evil.txt", b"pwned")
        monkeypatch.setattr("steamzero.domain.theme_install.fetch_bytes",
                            lambda url, **kw: buf.getvalue())
        with pytest.raises(SteamZeroError, match=r"E-CONTENT-UNSAFE-PATH"):
            ThemeInstaller().install("https://example.com/evil.zip")

    def test_missing_theme_json_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("some-dir/random.txt", b"no theme.json")
        monkeypatch.setattr("steamzero.domain.theme_install.fetch_bytes",
                            lambda url, **kw: buf.getvalue())
        with pytest.raises(SteamZeroError, match=r"theme\.json"):
            ThemeInstaller().install("https://example.com/no-theme.zip")

    def test_incompatible_theme_api_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from steamzero.adapters.theme_catalog import validate_theme_directory
        bad = dict(_VALID_MANIFEST, compatibility={"themeApi": 99})
        monkeypatch.setattr("steamzero.domain.theme_install.fetch_bytes",
                            lambda url, **kw: _make_theme_zip(manifest=bad))
        installer = ThemeInstaller(validate=validate_theme_directory)
        with pytest.raises(SteamZeroError):
            installer.install("https://example.com/bad-api.zip")

    def test_invalid_source_raises(self) -> None:
        with pytest.raises(SteamZeroError, match="origem inválida"):
            ThemeInstaller().install("")
