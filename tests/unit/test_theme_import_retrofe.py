# SPDX-License-Identifier: GPL-3.0-or-later
"""Contrato de importação RetroFE alcançável pela central."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from steamzero.core.errors import SteamZeroError
from steamzero.domain import theme_import_retrofe

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "retrofe" / "vs04_positive.xml"
SCHEMA = json.loads(
    (ROOT / "src" / "steamzero" / "schemas" / "ir-scene-v1.schema.json").read_text(encoding="utf-8")
)


def _dashboard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path))
    from steamzero.adapters.desktop_dashboard import DesktopDashboard

    return DesktopDashboard()


class TestRetrofeImport:
    def test_inspect_returns_scene_and_fidelity_without_writing(self, tmp_path: Path) -> None:
        source = tmp_path / "layout.xml"
        source.write_bytes(FIXTURE.read_bytes())
        before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))

        report = theme_import_retrofe.inspect(str(source))

        assert report["family"] == "retrofe"
        assert report["layoutCount"] == 1
        layout = report["layouts"][0]
        assert layout["path"] == "layout.xml"
        assert layout["report"]["elements"] >= 6
        assert layout["report"]["degraded"] >= 1
        jsonschema.validate(layout["scene"], SCHEMA)
        assert sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*")) == before

    def test_apply_publishes_only_validated_ir_and_does_not_activate(self, tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
        dashboard = _dashboard(tmp_path, monkeypatch)

        result = dashboard.theme_import_retrofe_apply(
            str(FIXTURE),
            "vs04_positive",
            "org.example.retrofe",
            "RetroFE importado",
            "Autor do tema",
            "CC0-1.0",
        )

        path = Path(result["path"])
        assert path == tmp_path / "data" / "steamzero" / "scenes" / "org.example.retrofe.json"
        assert result["family"] == "retrofe"
        assert result["activated"] is False
        scene = json.loads(path.read_text(encoding="utf-8"))
        jsonschema.validate(scene, SCHEMA)
        assert scene["origin"] == {
            "family": "retrofe",
            "author": "Autor do tema",
            "license": "CC0-1.0",
        }

    def test_overwrite_requires_explicit_confirmation(self, tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
        dashboard = _dashboard(tmp_path, monkeypatch)
        args = (
            str(FIXTURE),
            "vs04_positive",
            "org.example.retrofe",
            "RetroFE",
            "Autor",
            "MIT",
        )
        dashboard.theme_import_retrofe_apply(*args)
        with pytest.raises(SteamZeroError, match="overwrite"):
            dashboard.theme_import_retrofe_apply(*args)
        replaced = dashboard.theme_import_retrofe_apply(*args, overwrite=True)
        assert replaced["sceneId"] == "org.example.retrofe"

    def test_symlinked_source_is_refused(self, tmp_path: Path) -> None:
        link = tmp_path / "layout.xml"
        link.symlink_to(FIXTURE)
        with pytest.raises(SteamZeroError, match="symlink"):
            theme_import_retrofe.inspect(str(link))

    def test_oversized_layout_fails_before_compilation(self, tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        source = tmp_path / "huge.xml"
        source.write_bytes(b"<layout/>" + b" " * (theme_import_retrofe.MAX_LAYOUT_BYTES + 1))
        monkeypatch.setattr(theme_import_retrofe, "MAX_LAYOUT_BYTES", 32)
        with pytest.raises(SteamZeroError, match="excede"):
            theme_import_retrofe.inspect(str(source))

    def test_route_contracts_are_exposed(self) -> None:
        from steamzero.adapters.desktop_contracts import handheld_ui_contracts

        matrix = handheld_ui_contracts()["byId"]
        assert matrix["theme.import.retrofe.inspect"]["endpoint"] == "/theme/import/retrofe/inspect"
        assert matrix["theme.import.retrofe.apply"]["inputSchema"]["required"] == [
            "source",
            "layout",
            "sceneId",
            "name",
            "author",
            "license",
        ]
