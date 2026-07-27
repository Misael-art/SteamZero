from __future__ import annotations

import json
from pathlib import Path

import pytest

from steamzero.core.errors import SteamZeroError
from steamzero.domain.theme_editor import ThemeEditorManager

_VALID_MANIFEST: dict[str, object] = {
    "id": "org.test.editme",
    "name": "Edit Me",
    "version": "1.0.0",
    "author": "Tester",
    "license": "MIT",
    "compatibility": {"themeApi": 1},
}


def _write_theme(themes_dir: Path, manifest: dict[str, object] | None = None) -> Path:
    data = manifest or _VALID_MANIFEST
    tid = str(data["id"])
    theme_dir = themes_dir / tid
    theme_dir.mkdir(parents=True)
    (theme_dir / "theme.json").write_text(json.dumps(data, indent=2))
    return theme_dir


class TestEditorCreate:
    def test_create_new_session(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        mgr = ThemeEditorManager()
        result = mgr.create("Meu Tema")
        assert "sessionId" in result
        assert "manifest" in result
        assert "preview" in result
        manifest = result["manifest"]
        assert isinstance(manifest, dict)
        assert manifest["name"] == "Meu Tema"
        assert str(manifest["id"]).startswith("org.steamzero.")

    def test_create_with_extends(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        mgr = ThemeEditorManager()
        result = mgr.create("Derived", extends="org.steamzero.steamdeck")
        manifest = result["manifest"]
        assert manifest["extends"] == "org.steamzero.steamdeck"

    def test_multiple_sessions(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        mgr = ThemeEditorManager()
        a = mgr.create("A")
        b = mgr.create("B")
        assert a["sessionId"] != b["sessionId"]


class TestEditorLoad:
    def test_load_existing_theme(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        _write_theme(tmp_path / "steamzero" / "themes")
        mgr = ThemeEditorManager()
        result = mgr.load("org.test.editme")
        assert "sessionId" in result
        manifest = result["manifest"]
        assert manifest["name"] == "Edit Me"
        assert manifest["id"] == "org.test.editme"

    def test_load_nonexistent_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        mgr = ThemeEditorManager()
        with pytest.raises(SteamZeroError, match=r"E-THEME-NOT-FOUND"):
            mgr.load("org.test.nope")

    def test_load_builtin_returns_readonly(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        mgr = ThemeEditorManager()
        result = mgr.load("org.steamzero.default")
        assert result["readOnly"] is True


class TestEditorSetTokens:
    def test_set_color_tokens(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        mgr = ThemeEditorManager()
        session = mgr.create("Test")
        sid = session["sessionId"]
        result = mgr.set_tokens(
            sid,
            "color",
            {"background": "#111111", "primary": "#222222"},
        )
        preview = result["preview"]
        assert preview["resolved"]["color"]["background"] == "#111111"

    def test_invalid_category_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        mgr = ThemeEditorManager()
        sid = mgr.create("Test")["sessionId"]
        with pytest.raises(SteamZeroError, match=r"E-API-SCHEMA"):
            mgr.set_tokens(sid, "invalid", {})

    def test_bad_session_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        mgr = ThemeEditorManager()
        with pytest.raises(SteamZeroError, match=r"E-API-SCHEMA"):
            mgr.set_tokens("no-such-session", "color", {})


class TestEditorSetMetadata:
    def test_set_name(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        mgr = ThemeEditorManager()
        sid = mgr.create("Original")["sessionId"]
        result = mgr.set_metadata(sid, "name", "Renomeado")
        assert result["manifest"]["name"] == "Renomeado"

    def test_set_null_clears(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        mgr = ThemeEditorManager()
        sid = mgr.create("WithDesc")["sessionId"]
        mgr.set_metadata(sid, "description", "desc original")
        result = mgr.set_metadata(sid, "description", None)
        assert result["manifest"].get("description") is None

    def test_invalid_field_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        mgr = ThemeEditorManager()
        sid = mgr.create("Test")["sessionId"]
        with pytest.raises(SteamZeroError, match=r"E-API-SCHEMA"):
            mgr.set_metadata(sid, "banana", "x")


class TestEditorSave:
    def test_save_new_theme(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        mgr = ThemeEditorManager()
        sid = mgr.create("Saved")["sessionId"]
        result = mgr.save(sid)
        assert result["themeId"].startswith("org.steamzero.")
        theme_dir = tmp_path / "steamzero" / "themes" / result["themeId"]
        assert (theme_dir / "theme.json").is_file()

    def test_save_twice_without_overwrite_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        mgr = ThemeEditorManager()
        sid = mgr.create("Dup")["sessionId"]
        mgr.save(sid)
        with pytest.raises(SteamZeroError, match=r"E-THEME-DOWNLOAD-FAILED"):
            mgr.save(sid)

    def test_save_overwrite(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        mgr = ThemeEditorManager()
        sid = mgr.create("Overwrite")["sessionId"]
        mgr.save(sid)
        mgr.set_metadata(sid, "name", "Overwritten")
        result = mgr.save(sid, overwrite=True)
        manifest_path = tmp_path / "steamzero" / "themes" / result["themeId"] / "theme.json"
        manifest = json.loads(manifest_path.read_text())
        assert manifest["name"] == "Overwritten"

    def test_save_preserves_assets(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        themes_dir = tmp_path / "steamzero" / "themes"
        theme_dir = _write_theme(themes_dir)
        (theme_dir / "assets").mkdir()
        (theme_dir / "assets" / "icon.png").write_text("fake-png")
        mgr = ThemeEditorManager()
        load_result = mgr.load("org.test.editme")
        sid = load_result["sessionId"]
        save_result = mgr.save(sid, overwrite=True)
        saved_assets = tmp_path / "steamzero" / "themes" / save_result["themeId"] / "assets"
        assert (saved_assets / "icon.png").is_file()


class TestEditorCancel:
    def test_cancel_removes_session(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        mgr = ThemeEditorManager()
        sid = mgr.create("Temp")["sessionId"]
        cancel = mgr.cancel(sid)
        assert cancel["status"] == "cancelled"
        with pytest.raises(SteamZeroError, match=r"E-API-SCHEMA"):
            mgr.preview(sid)

    def test_cancel_unknown_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        mgr = ThemeEditorManager()
        with pytest.raises(SteamZeroError, match=r"E-API-SCHEMA"):
            mgr.cancel("no-such")


class TestEditorExport:
    def test_export_zip(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        mgr = ThemeEditorManager()
        sid = mgr.create("Exportable")["sessionId"]
        mgr.set_tokens(sid, "color", {"background": "#000000"})
        zip_data = mgr.export_zip(sid)
        assert zip_data[:2] == b"PK"

    def test_export_size_grows_with_tokens(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        mgr = ThemeEditorManager()
        sid = mgr.create("SizeTest")["sessionId"]
        empty = len(mgr.export_zip(sid))
        mgr.set_tokens(sid, "color", {"a": "#1", "b": "#2", "c": "#3"})
        full = len(mgr.export_zip(sid))
        assert full > empty


class TestEditorPreview:
    def test_preview_returns_theme_qml_object(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        mgr = ThemeEditorManager()
        sid = mgr.create("PreviewTest")["sessionId"]
        mgr.set_tokens(sid, "color", {"background": "#ff0000"})
        result = mgr.preview(sid)
        preview = result["preview"]
        assert preview["themeId"]
        assert "resolved" in preview
        assert preview["resolved"]["color"]["background"] == "#ff0000"

    def test_preview_applies_accessibility(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        mgr = ThemeEditorManager()
        sid = mgr.create("A11yTest")["sessionId"]
        normal = mgr.preview(sid)
        hc = mgr.preview(sid, high_contrast=True)
        assert normal["preview"]["themeId"] == hc["preview"]["themeId"]

    def test_preview_bad_session_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        mgr = ThemeEditorManager()
        with pytest.raises(SteamZeroError, match=r"E-API-SCHEMA"):
            mgr.preview("nope")


_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100ffff03000006000557bfabd400"
    "00000049454e44ae426082"
)


class TestEditorAssetsPersist:
    """set_asset precisa gravar de verdade; sucesso sem efeito é defeito."""

    def test_set_asset_survives_save(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        mgr = ThemeEditorManager()
        sid = str(mgr.create("Com Asset")["sessionId"])
        mgr.set_asset(sid, "background", _PNG, "qualquer-coisa.png")
        saved = mgr.save(sid)

        target = Path(saved["path"])
        stored = target / "assets" / "background.png"
        assert stored.is_file(), "os bytes do asset precisam chegar ao disco"
        assert stored.read_bytes() == _PNG

        manifest = json.loads((target / "theme.json").read_text())
        assert manifest["assets"]["background"] == "assets/background.png"

    def test_stored_name_derives_from_slot_not_filename(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        mgr = ThemeEditorManager()
        sid = str(mgr.create("Nome Hostil")["sessionId"])
        result = mgr.set_asset(sid, "background", _PNG, "../../escape.png")
        asset = result["asset"]
        assert isinstance(asset, dict)
        assert asset["filename"] == "background.png"

        target = Path(mgr.save(sid)["path"])
        assert (target / "assets" / "background.png").is_file()
        assert not (tmp_path / "escape.png").exists()

    def test_rejects_disallowed_extension(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        mgr = ThemeEditorManager()
        sid = str(mgr.create("X")["sessionId"])
        with pytest.raises(SteamZeroError, match=r"extensão não permitida"):
            mgr.set_asset(sid, "background", b"MZ", "payload.exe")

    def test_rejects_empty_asset(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        mgr = ThemeEditorManager()
        sid = str(mgr.create("X")["sessionId"])
        with pytest.raises(SteamZeroError, match=r"asset vazio"):
            mgr.set_asset(sid, "background", b"", "vazio.png")


class TestEditorExportRoundTrip:
    """Export precisa produzir pacote que o instalador consegue reinstalar."""

    def test_export_layout_is_installable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import zipfile

        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        mgr = ThemeEditorManager()
        created = mgr.create("Exportavel")
        sid = str(created["sessionId"])
        manifest = created["manifest"]
        assert isinstance(manifest, dict)
        theme_id = str(manifest["id"])
        mgr.set_asset(sid, "background", _PNG, "bg.png")

        with zipfile.ZipFile(__import__("io").BytesIO(mgr.export_zip(sid))) as zf:
            names = set(zf.namelist())

        assert f"{theme_id}/theme.json" in names
        # O asset precisa estar SOB o mesmo diretório do manifesto, senão
        # _find_theme_dir elege {theme_id}/ e o asset fica órfão na reinstalação.
        assert f"{theme_id}/assets/background.png" in names
        assert "assets/background.png" not in names

    def test_export_then_install_preserves_assets(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from steamzero.core import paths
        from steamzero.domain.theme_install import ThemeInstaller

        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        mgr = ThemeEditorManager()
        created = mgr.create("Round Trip")
        sid = str(created["sessionId"])
        manifest = created["manifest"]
        assert isinstance(manifest, dict)
        theme_id = str(manifest["id"])
        mgr.set_asset(sid, "background", _PNG, "bg.png")

        package = tmp_path / "pacote.zip"
        package.write_bytes(mgr.export_zip(sid))

        installed = ThemeInstaller().install(str(package), force=True)
        assert installed["themeId"] == theme_id

        target = paths.themes_dir() / theme_id
        asset = target / "assets" / "background.png"
        assert asset.is_file(), "o asset precisa sobreviver ao ciclo export→install"
        assert asset.read_bytes() == _PNG


class TestEditorIdValidation:
    """O id vira caminho e alvo de remoção: precisa do padrão do schema."""

    def _session_with_id(self, mgr: ThemeEditorManager, theme_id: str) -> str:
        sid = str(mgr.create("X")["sessionId"])
        mgr._sessions[sid].manifest["id"] = theme_id
        return sid

    @pytest.mark.parametrize(
        "bad_id",
        [
            "semseparador",
            "TEMA.MAIUSCULO",
            "org..vazio",
            "org.test/escape",
            "org.test\\escape",
            "",
        ],
    )
    def test_rejects_invalid_ids(
        self, bad_id: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        mgr = ThemeEditorManager()
        sid = self._session_with_id(mgr, bad_id)
        with pytest.raises(SteamZeroError, match=r"E-THEME-MANIFEST"):
            mgr.save(sid, overwrite=True)

    def test_rejects_non_ascii_id(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """isalnum() é Unicode-aware e aceitava isto; o padrão do schema não."""
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        mgr = ThemeEditorManager()
        sid = self._session_with_id(mgr, "org.tema.ção")
        with pytest.raises(SteamZeroError, match=r"E-THEME-MANIFEST"):
            mgr.save(sid, overwrite=True)

    def test_accepts_schema_conformant_id(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        mgr = ThemeEditorManager()
        sid = self._session_with_id(mgr, "org.steamzero.valido-2")
        assert mgr.save(sid)["themeId"] == "org.steamzero.valido-2"
