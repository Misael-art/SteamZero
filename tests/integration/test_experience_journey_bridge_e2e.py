# SPDX-License-Identifier: GPL-3.0-or-later
"""Jornada Studio pela bridge HTTP de produção, com read models isolados."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import urllib.error
import urllib.request
import zipfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from tests.integration.test_ui_shell_retrofe_import_late_response import RUNNER

from steamzero.adapters.desktop_contracts import handheld_ui_contracts
from steamzero.adapters.desktop_ui import DesktopControlServer
from steamzero.core.state import StateStore
from steamzero.domain.desktop import DesktopContext, ExperienceCoordinator
from steamzero.domain.theme_editor import ThemeEditorManager


class _Context:
    def snapshot(self) -> DesktopContext:
        return DesktopContext(
            "linux",
            "wayland",
            (),
            False,
            False,
            False,
            frozenset(),
        )


class _JourneyDashboard:
    def __init__(self) -> None:
        self.cancelled_theme_sessions: list[str] = []
        self.theme_editor = ThemeEditorManager()
        self.additional_themes: list[dict[str, Any]] = []

    def snapshot(self, _status: dict[str, Any]) -> dict[str, Any]:
        return {
            "emulation": {
                "editorialPlatforms": [
                    {
                        "id": "nes",
                        "name": "Nintendo Entertainment System",
                        "shortName": "NES",
                        "state": "ready",
                        "games": [
                            {
                                "id": "rom-001",
                                "name": "Synthetic Platformer",
                                "platform": "nes",
                                "genres": ["Platformer", "Arcade"],
                                "releaseDate": "1992-06-01",
                                "publisher": "Example Publisher",
                                "path": "/private/roms/synthetic.nes",
                            },
                            {
                                "id": "rom-002",
                                "name": "Synthetic Puzzle",
                                "platform": "nes",
                                "genres": ["Puzzle"],
                                "path": "/private/roms/puzzle.nes",
                            },
                        ],
                    }
                ]
            },
            "steamGameplay": {
                "games": [
                    {
                        "id": "steam-001",
                        "name": "Synthetic Steam Game",
                        "publisher": "Example Publisher",
                    }
                ]
            },
        }

    def theme_list(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "org.steamzero.default",
                "name": "AURA",
                "version": "2.0.0",
                "state": "available",
                "compatible": True,
                "origin": "builtin",
            },
            {
                "id": "org.steamzero.asset-recipes-demo",
                "name": "Theme Engine — asset único",
                "version": "1.0.0",
                "state": "available",
                "compatible": True,
                "origin": "builtin",
            },
            *self.additional_themes,
        ]

    def editor_load(self, theme_id: str) -> dict[str, Any]:
        return self.theme_editor.load(theme_id)

    def editor_preview(
        self,
        session_id: str,
        *,
        scene_layout_read_model: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.theme_editor.preview(
            session_id, scene_layout_read_model=scene_layout_read_model
        )

    def editor_cancel(self, session_id: str) -> dict[str, str]:
        self.cancelled_theme_sessions.append(session_id)
        return self.theme_editor.cancel(session_id)


def _request(
    base_url: str,
    token: str,
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    # The base URL is created by DesktopControlServer on loopback in this test.
    request = urllib.request.Request(  # noqa: S310
        base_url + path,
        data=body,
        method=method,
        headers={
            "X-SteamZero-Token": token,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310
        value = json.loads(response.read())
    assert isinstance(value, dict)
    return value


@pytest.fixture
def journey_bridge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[str, str, _JourneyDashboard]:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg-state"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    store = StateStore(tmp_path / "bridge-state.db")
    store.migrate()
    dashboard = _JourneyDashboard()
    server = DesktopControlServer(
        ExperienceCoordinator(_Context(), (), store),
        "journey-bridge-test-token",
        dashboard,  # type: ignore[arg-type]
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", "journey-bridge-test-token", dashboard
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
        store.close()


def test_journey_editor_roundtrips_through_the_allowlisted_production_bridge(
    journey_bridge: tuple[str, str, _JourneyDashboard], tmp_path: Path
) -> None:
    base_url, token, dashboard = journey_bridge
    contracts = _request(base_url, token, "/contracts")
    actions = contracts["byId"]
    expected_actions = {
        "journey.studio.list",
        "journey.studio.catalog",
        "journey.studio.create",
        "journey.studio.load",
        "journey.studio.transact",
        "journey.studio.save",
        "journey.studio.preview",
        "journey.studio.engine-preview",
        "journey.studio.coverage",
        "journey.studio.import",
        "journey.studio.export.prepare",
        "journey.studio.export.apply",
        "journey.studio.undo",
        "journey.studio.redo",
    }
    assert expected_actions <= set(actions)
    assert expected_actions <= set(handheld_ui_contracts()["byId"])

    catalog = _request(base_url, token, "/journey/studio/catalog")
    models = {item["id"]: item for item in catalog["readModels"]}
    game_fields = {item["id"]: item for item in models["library.games"]["fields"]}
    assert game_fields["genres"]["type"] == "string[]"
    assert game_fields["genres"]["name"] == "Gêneros publicados"
    assert game_fields["genre"]["name"] == "Gênero principal"
    assert game_fields["year"]["type"] == "integer"
    assert models["library.games"]["recordCount"] == 3
    assert catalog["limits"]["maxRecords"] == 20_000
    assert catalog["limits"]["previewRows"] == 64

    created = _request(
        base_url,
        token,
        "/journey/studio/create",
        method="POST",
        payload={"name": "Jornada de teste"},
    )
    session_id = str(created["sessionId"])
    generation = int(created["generation"])

    edited = _request(
        base_url,
        token,
        "/journey/studio/transact",
        method="POST",
        payload={
            "operation": "set-filters",
            "payload": {
                "sessionId": session_id,
                "expectedGeneration": generation,
                "menuId": "home",
                "values": [{"fieldId": "genre", "operator": "equals", "value": "Platformer"}],
            },
        },
    )
    assert edited["generation"] == generation + 1

    preview = _request(
        base_url,
        token,
        "/journey/studio/preview",
        method="POST",
        payload={"sessionId": session_id, "menuId": "home"},
    )
    assert preview["resultState"] == "results"
    assert preview["resultCount"] == 1
    assert preview["rows"][0]["title"] == "Synthetic Platformer"
    assert preview["rows"][0]["year"] == 1992
    assert preview["rows"][0]["genre"] == "Platformer"
    assert "path" not in preview["rows"][0]
    assert "private/roms" not in json.dumps(preview)

    undone = _request(
        base_url,
        token,
        "/journey/studio/undo",
        method="POST",
        payload={"sessionId": session_id},
    )
    assert undone["history"]["canRedo"] is True
    all_rows = _request(
        base_url,
        token,
        "/journey/studio/preview",
        method="POST",
        payload={"sessionId": session_id, "menuId": "home"},
    )
    assert all_rows["resultCount"] == 3

    redone = _request(
        base_url,
        token,
        "/journey/studio/redo",
        method="POST",
        payload={"sessionId": session_id},
    )
    assert redone["document"]["menus"][0]["filters"][0]["fieldId"] == "genre"
    appearance = _request(
        base_url,
        token,
        "/journey/studio/transact",
        method="POST",
        payload={
            "operation": "set-menu-appearance",
            "payload": {
                "sessionId": session_id,
                "expectedGeneration": redone["generation"],
                "menuId": "home",
                "appearance": {
                    "mode": "custom",
                    "themeId": "org.steamzero.asset-recipes-demo",
                },
            },
        },
    )
    save_result = _request(
        base_url,
        token,
        "/journey/studio/save",
        method="POST",
        payload={"sessionId": session_id, "overwrite": False},
    )
    journey_id = str(save_result["journeyId"])
    listed = _request(base_url, token, "/journey/studio/list")
    assert {item["id"] for item in listed["journeys"]} == {journey_id}
    reopened = _request(
        base_url,
        token,
        "/journey/studio/load",
        method="POST",
        payload={"journeyId": journey_id},
    )
    assert reopened["document"]["menus"] == appearance["document"]["menus"]
    assert reopened["document"]["menus"][0]["filters"] == [
        {"fieldId": "genre", "operator": "equals", "value": "Platformer"}
    ]

    engine_result = _request(
        base_url,
        token,
        "/journey/studio/engine-preview",
        method="POST",
        payload={
            "sessionId": reopened["sessionId"],
            "menuId": "home",
            "expectedGeneration": reopened["generation"],
        },
    )
    assert engine_result["journeyGeneration"] == reopened["generation"]
    assert engine_result["themeId"] == "org.steamzero.asset-recipes-demo"
    assert engine_result["query"]["resultCount"] == 1
    assert engine_result["query"]["rows"][0]["title"] == "Synthetic Platformer"
    native = engine_result["preview"]["sceneLayoutPreview"]["layouts"]["previewTitles"]
    rendered_titles = [entry["text"] for entry in native["entries"]]
    assert rendered_titles == ["Synthetic Platformer"]
    assert "Axiom Verge" not in rendered_titles

    coverage = _request(
        base_url,
        token,
        "/journey/studio/coverage",
        method="POST",
        payload={
            "sessionId": reopened["sessionId"],
            "usedStages": ["menu:home", "pause", "saves"],
        },
    )
    stages = {item["stageId"]: item for item in coverage["stages"]}
    assert stages["menu:home"]["sourceThemeId"] == "org.steamzero.asset-recipes-demo"
    assert stages["pause"]["operationCapability"] == "unknown"
    assert stages["saves"]["operationCapability"] == "unknown"
    assert coverage["operationalSource"]["state"] == "unknown"
    assert dashboard.cancelled_theme_sessions

    export_path = tmp_path / "journey-copy.zip"
    export_plan = _request(
        base_url,
        token,
        "/journey/studio/export/prepare",
        method="POST",
        payload={"sessionId": reopened["sessionId"], "destination": str(export_path)},
    )
    assert export_plan["packageContents"] == ["experience.json"]
    exported = _request(
        base_url,
        token,
        "/journey/studio/export/apply",
        method="POST",
        payload={
            "planId": export_plan["planId"],
            "confirmToken": export_plan["confirmToken"],
        },
    )
    assert exported["status"] == "ok"
    assert export_path.is_file()

    imported = _request(
        base_url,
        token,
        "/journey/studio/import",
        method="POST",
        payload={"source": str(export_path), "copyName": "Cópia de teste"},
    )
    assert imported["document"]["name"] == "Cópia de teste"
    assert (
        imported["document"]["menus"][0]["filters"] == reopened["document"]["menus"][0]["filters"]
    )
    assert imported["dependencies"] == [
        {
            "themeId": "org.steamzero.asset-recipes-demo",
            "version": None,
            "state": "available-unpinned",
            "installedVersion": "1.0.0",
        }
    ]

    with pytest.raises(urllib.error.HTTPError) as error:
        _request(
            base_url,
            token,
            "/journey/studio/create",
            method="POST",
            payload={"name": "Inválida", "path": "nao-allowlisted"},
        )
    assert error.value.code == 400


@pytest.mark.visual
def test_journey_authoring_qml_uses_the_real_allowlisted_bridge(
    journey_bridge: tuple[str, str, _JourneyDashboard],
    tmp_path: Path,
) -> None:
    """Os controles QML criam, filtram, conectam, desfazem e reabrem pela bridge real."""
    assert RUNNER is not None, "qmltestrunner Qt 6 é obrigatório para esta prova"
    base_url, token, _dashboard = journey_bridge
    root = Path(__file__).resolve().parents[2]
    harness = root / "tests" / "qml" / "check_experience_journey_bridge_e2e.qml"
    config = root / "build" / "journey-studio-bridge-e2e.json"
    config.parent.mkdir(exist_ok=True)
    assert not config.exists(), "há um arquivo efêmero anterior que precisa ser inspecionado"
    config.write_text(
        json.dumps(
            {
                "apiUrl": base_url,
                "apiToken": token,
                "exportPath": str(tmp_path / "journey-ui-roundtrip.zip"),
            }
        ),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update(
        {
            "QT_QPA_PLATFORM": "offscreen",
            "QT_QUICK_BACKEND": "software",
            "QT_FORCE_STDERR_LOGGING": "1",
            "QT_LOGGING_RULES": "",
            "QML_XHR_ALLOW_FILE_READ": "1",
        }
    )
    try:
        completed = subprocess.run(
            [str(RUNNER), "-input", str(harness)],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    finally:
        config.unlink(missing_ok=True)
    output = (completed.stdout or "") + (completed.stderr or "")
    assert completed.returncode == 0, f"Jornada UI/bridge reprovou:\n{output[-7000:]}"
    assert "FAIL!" not in output, f"assertion QML reprovou:\n{output[-7000:]}"
    exported = tmp_path / "journey-ui-roundtrip.zip"
    assert exported.is_file(), "a UI não criou o pacote confirmado"
    with zipfile.ZipFile(exported) as package:
        assert package.namelist() == ["experience.json"]


def test_journey_engine_preview_reports_missing_theme_and_uses_explicit_aura_fallback(
    journey_bridge: tuple[str, str, _JourneyDashboard],
) -> None:
    base_url, token, dashboard = journey_bridge
    created = _request(
        base_url,
        token,
        "/journey/studio/create",
        method="POST",
        payload={"name": "Tema ausente"},
    )
    changed = _request(
        base_url,
        token,
        "/journey/studio/transact",
        method="POST",
        payload={
            "operation": "set-menu-appearance",
            "payload": {
                "sessionId": created["sessionId"],
                "expectedGeneration": created["generation"],
                "menuId": "home",
                "appearance": {"mode": "custom", "themeId": "org.example.missing"},
            },
        },
    )

    result = _request(
        base_url,
        token,
        "/journey/studio/engine-preview",
        method="POST",
        payload={
            "sessionId": created["sessionId"],
            "menuId": "home",
            "expectedGeneration": changed["generation"],
        },
    )
    assert result["themeResolutionState"] == "missing-reference"
    assert result["declaredThemeId"] == "org.example.missing"
    assert result["themeId"] == "org.steamzero.default"
    assert "AURA" in result["themeResolutionDiagnostic"]
    assert result["coverage"]["stages"][0]["reason"] == "theme-reference-missing"
    assert result["coverage"]["stages"][0]["sourceThemeId"] == "org.steamzero.default"
    assert "sessionId" not in result
    assert dashboard.cancelled_theme_sessions

    with pytest.raises(urllib.error.HTTPError) as error:
        _request(
            base_url,
            token,
            "/journey/studio/engine-preview",
            method="POST",
            payload={
                "sessionId": created["sessionId"],
                "menuId": "home",
                "expectedGeneration": created["generation"],
            },
        )
    assert error.value.code == 400


def test_journey_engine_preview_uses_a_saved_theme_editor_layout_change(
    journey_bridge: tuple[str, str, _JourneyDashboard],
) -> None:
    base_url, token, dashboard = journey_bridge
    edited_theme = dashboard.theme_editor.create(
        "Jornada Engine editada", extends="org.steamzero.asset-recipes-demo"
    )
    theme_id = str(edited_theme["manifest"]["id"])
    theme_session = str(edited_theme["sessionId"])
    changed_theme = dashboard.theme_editor.set_layout(theme_session, "previewTitles", "maxItems", 2)
    assert changed_theme["layout"]["maxItems"] == 2
    saved_theme = dashboard.theme_editor.save(theme_session, overwrite=False)
    assert saved_theme["themeId"] == theme_id
    reloaded_theme = dashboard.editor_load(theme_id)
    assert reloaded_theme["manifest"]["sceneLayouts"]["layouts"]["previewTitles"]["maxItems"] == 2
    reloaded_theme_preview = dashboard.editor_preview(
        str(reloaded_theme["sessionId"]),
        scene_layout_read_model={
            "preview": {
                "items": [{"title": "Primeiro"}, {"title": "Segundo"}, {"title": "Terceiro"}]
            }
        },
    )
    assert (
        len(
            reloaded_theme_preview["preview"]["sceneLayoutPreview"]["layouts"]["previewTitles"][
                "entries"
            ]
        )
        == 2
    )
    dashboard.editor_cancel(str(reloaded_theme["sessionId"]))
    dashboard.additional_themes.append(
        {
            "id": theme_id,
            "name": "Jornada Engine editada",
            "version": "1.0.0",
            "state": "available",
            "compatible": True,
            "origin": "user",
        }
    )

    created = _request(
        base_url,
        token,
        "/journey/studio/create",
        method="POST",
        payload={"name": "Documento para tema editado"},
    )
    themed = _request(
        base_url,
        token,
        "/journey/studio/transact",
        method="POST",
        payload={
            "operation": "set-menu-appearance",
            "payload": {
                "sessionId": created["sessionId"],
                "expectedGeneration": created["generation"],
                "menuId": "home",
                "appearance": {"mode": "custom", "themeId": theme_id},
            },
        },
    )
    saved_journey = _request(
        base_url,
        token,
        "/journey/studio/save",
        method="POST",
        payload={"sessionId": created["sessionId"], "overwrite": False},
    )
    reopened = _request(
        base_url,
        token,
        "/journey/studio/load",
        method="POST",
        payload={"journeyId": saved_journey["journeyId"]},
    )
    assert (
        reopened["document"]["menus"][0]["appearance"]
        == themed["document"]["menus"][0]["appearance"]
    )

    result = _request(
        base_url,
        token,
        "/journey/studio/engine-preview",
        method="POST",
        payload={
            "sessionId": reopened["sessionId"],
            "menuId": "home",
            "expectedGeneration": reopened["generation"],
        },
    )
    assert result["themeId"] == theme_id
    assert result["themeResolutionState"] == "custom"
    assert result["manifest"]["sceneLayouts"]["layouts"]["previewTitles"]["maxItems"] == 2
    assert result["declared"]["sceneLayouts"]["layouts"]["previewTitles"]["maxItems"] == 2
    layouts = result["preview"]["sceneLayoutPreview"]["layouts"]
    assert [entry["text"] for entry in layouts["previewTitles"]["entries"]] == [
        "Synthetic Platformer",
        "Synthetic Puzzle",
    ]
