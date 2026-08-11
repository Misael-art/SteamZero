# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""AURA — identidade escura do SteamZero como tema builtin.

Cobre: identidade no catálogo, resolução da cadeia de herança e a sequência
vertical do editor (abrir → editar → preview → cancelar → reabrir → salvar →
aplicar → rollback) com a paleta Aura como base derivável.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from steamzero.adapters.theme_catalog import ThemeCatalog, read_builtin_manifest
from steamzero.core.errors import SteamZeroError
from steamzero.domain.theme_editor import ThemeEditorManager
from steamzero.domain.theme_preferences import ThemePreferenceManager
from steamzero.domain.themes import THEME_DEFAULT_ID

AURA_ID = "org.steamzero.aura"


def _aura_tokens() -> dict[str, object]:
    manifest = read_builtin_manifest(AURA_ID)
    return dict(manifest.tokens["color"])


class TestAuraIdentity:
    def test_manifest_validates_and_reads(self) -> None:
        manifest = read_builtin_manifest(AURA_ID)
        assert manifest.id == AURA_ID
        assert manifest.name == "AURA"
        assert manifest.extends == THEME_DEFAULT_ID
        assert manifest.version == "1.0.0"

    def test_aura_is_listed_as_available_builtin(self) -> None:
        entries = ThemeCatalog().list_catalog()
        entry = next(e for e in entries if e["id"] == AURA_ID)
        assert entry["state"] == "available"
        assert entry["origin"] == "builtin"
        assert entry["compatible"] is True

    def test_aura_resolves_the_spec_palette(self) -> None:
        resolved = ThemeCatalog().resolve(AURA_ID)
        assert resolved.color.background == "#0b1020"
        assert resolved.color.surface == "#141a2e"
        assert resolved.color.surfaceRaised == "#1c2440"
        assert resolved.color.text == "#e8ecf7"
        assert resolved.color.textMuted == "#8b93a8"
        assert resolved.color.accent == "#22d3ee"
        assert resolved.color.focus == "#22d3ee"
        assert resolved.color.border == "#262f4d"

    def test_aura_inherits_default_geometry_and_recipes(self) -> None:
        resolved = ThemeCatalog().resolve(AURA_ID)
        assert resolved.geometry.radiusMedium == 10
        assert resolved.typography.heading == 24
        assert "focusedCover" in resolved.media_recipes
        assert "contextualBackdrop" in resolved.effects

    def test_aura_resolution_leaves_default_untouched(self) -> None:
        catalog = ThemeCatalog()
        catalog.resolve(AURA_ID)
        assert catalog.resolve(THEME_DEFAULT_ID).color.background == "#e7eceb"

    def test_aura_can_be_the_base_of_a_user_theme(self) -> None:
        catalog = ThemeCatalog()
        resolver = catalog.resolve(AURA_ID)
        assert resolver.name == "AURA"
        assert resolver.author == "SteamZero contributors"


class TestEditorVertical:
    def _themes_dir(self, tmp_path: Path) -> Path:
        return tmp_path / "steamzero" / "themes"

    def test_abrir_editar_preview_cancelar_reabrir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        mgr = ThemeEditorManager()
        themes_dir = self._themes_dir(tmp_path)

        opened = mgr.load(AURA_ID)
        assert opened["readOnly"] is True
        sid = str(opened["sessionId"])
        preview = opened["preview"]
        assert preview["resolved"]["color"]["background"] == "#0b1020"
        assert preview["resolved"]["color"]["accent"] == "#22d3ee"

        aura = _aura_tokens()
        edited_values = dict(aura)
        edited_values["accent"] = "#ff0000"
        edited = mgr.set_tokens(sid, "color", edited_values)
        assert edited["preview"]["resolved"]["color"]["accent"] == "#ff0000"
        assert edited["preview"]["resolved"]["color"]["background"] == "#0b1020"
        assert not themes_dir.exists(), "editar não pode tocar o disco"

        previewed = mgr.preview(sid)
        assert previewed["preview"]["resolved"]["color"]["accent"] == "#ff0000"
        assert not themes_dir.exists(), "preview não pode tocar o disco"

        cancelled = mgr.cancel(sid)
        assert cancelled["status"] == "cancelled"
        assert not themes_dir.exists(), "cancelar não pode tocar o disco"

        reopened = mgr.load(AURA_ID)
        assert reopened["readOnly"] is True
        assert str(reopened["sessionId"]) != sid
        preview = reopened["preview"]
        assert preview["resolved"]["color"]["accent"] == "#22d3ee"
        assert preview["resolved"]["color"]["background"] == "#0b1020"

    def test_salvar_aplicar_rollback(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        mgr = ThemeEditorManager()
        themes_dir = self._themes_dir(tmp_path)

        created = mgr.create("AURA Derivado", extends=AURA_ID)
        sid = str(created["sessionId"])
        assert created["manifest"]["extends"] == AURA_ID

        mgr.set_tokens(sid, "color", _aura_tokens())
        mgr.set_metadata(sid, "name", "AURA Derivado")
        saved = mgr.save(sid)
        theme_id = saved["themeId"]
        assert theme_id.startswith("org.steamzero.")

        saved_dir = themes_dir / theme_id
        manifest_path = saved_dir / "theme.json"
        assert manifest_path.is_file()
        written = json.loads(manifest_path.read_text())
        assert written["extends"] == AURA_ID
        assert written["tokens"]["color"]["background"] == "#0b1020"
        assert written["tokens"]["color"]["accent"] == "#22d3ee"

        entries = ThemeCatalog(user_themes_dir=themes_dir).list_catalog()
        entry = next(e for e in entries if e["id"] == theme_id)
        assert entry["origin"] == "user"
        assert entry["state"] == "available"
        assert entry["compatible"] is True

        prefs = ThemePreferenceManager(config_dir=tmp_path / "config" / "steamzero")
        previous = prefs._read_preference()
        plan = prefs.plan_activate(theme_id, "1.0.0", previous=previous)
        applied = prefs.apply(plan.plan_id, plan.confirm_token)
        assert applied.status == "ok"
        assert json.loads(prefs._preference_path().read_text())["themeId"] == theme_id

        rolled_back = prefs.rollback(applied.operation_id)
        assert rolled_back.status == "rolled-back"
        restored = prefs._read_preference()
        assert restored is None or restored["themeId"] != theme_id

    def test_save_writes_valid_manifest_under_themes_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        mgr = ThemeEditorManager()
        created = mgr.create("AURA Salvo", extends=AURA_ID)
        sid = str(created["sessionId"])
        mgr.set_tokens(sid, "color", _aura_tokens())
        saved = mgr.save(sid)

        saved_dir = self._themes_dir(tmp_path) / saved["themeId"]
        assert saved_dir.is_dir()
        manifest_path = saved_dir / "theme.json"
        assert manifest_path.is_file()
        written = json.loads(manifest_path.read_text())
        assert written["extends"] == AURA_ID
        assert written["tokens"]["color"]["accent"] == "#22d3ee"

    def test_cancel_discards_session_and_keeps_disk_intact(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        mgr = ThemeEditorManager()
        themes_dir = self._themes_dir(tmp_path)
        created = mgr.create("AURA Descartado", extends=AURA_ID)
        sid = str(created["sessionId"])
        mgr.set_tokens(sid, "color", _aura_tokens())
        mgr.cancel(sid)

        with pytest.raises(SteamZeroError, match=r"E-API-SCHEMA"):
            mgr.preview(sid)
        assert not themes_dir.exists(), "sessão cancelada não pode persistir nada"
