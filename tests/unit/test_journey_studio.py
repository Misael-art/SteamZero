# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from pathlib import Path

import pytest
from jsonschema import ValidationError

from steamzero.adapters.journey_studio import JourneyStudioService
from steamzero.domain.experience_journey import (
    JourneyDocument,
    JourneyStore,
    JourneyValidationError,
)


def _menu(menu_id: str, name: str, read_model_id: str) -> dict[str, object]:
    return {
        "id": menu_id,
        "name": name,
        "source": {"readModelId": read_model_id},
        "filters": [],
        "sort": [],
        "groupBy": [],
    }


def _connection(
    connection_id: str,
    source: str,
    event: str,
    action: str,
    target: dict[str, str],
) -> dict[str, object]:
    return {
        "id": connection_id,
        "from": {"kind": "menu", "id": source},
        "event": event,
        "when": "user-input",
        "action": action,
        "to": target,
        "label": connection_id.replace("-", " ").title(),
    }


def test_authoring_transactions_history_save_reopen_and_preview(tmp_path: Path) -> None:
    service = JourneyStudioService(tmp_path / "journeys")
    created = service.create(name="Rota retro", journey_id="org.steamzero.retro")
    session_id = created["sessionId"]
    generation = created["generation"]

    platforms = service.transact(
        session_id,
        "add-menu",
        {"menu": _menu("platforms", "Plataformas", "library.platforms")},
        expected_generation=generation,
    )
    assert platforms["dirty"] is True
    generation = platforms["generation"]
    games = service.transact(
        session_id,
        "add-menu",
        {"menu": _menu("games", "Jogos", "library.games")},
        expected_generation=generation,
    )
    generation = games["generation"]
    service.transact(
        session_id,
        "set-entry-menu",
        {"menuId": "platforms"},
        expected_generation=generation,
    )
    service.transact(
        session_id,
        "add-connection",
        {
            "connection": {
                **_connection(
                    "platforms-games",
                    "platforms",
                    "select",
                    "navigate",
                    {"kind": "menu", "id": "games"},
                ),
                "bindings": [{"sourceFieldId": "id", "targetFieldId": "platformId"}],
            }
        },
    )
    service.transact(
        session_id,
        "add-connection",
        {"connection": _connection("games-back", "games", "back", "back", {"kind": "history"})},
    )
    service.transact(
        session_id,
        "set-group-by",
        {"menuId": "games", "values": ["genre"]},
    )
    service.transact(
        session_id,
        "set-sort",
        {
            "menuId": "games",
            "values": [{"fieldId": "year", "direction": "descending"}],
        },
    )

    edited = service.snapshot(session_id)
    assert edited["history"]["canUndo"] is True
    before_undo_generation = edited["generation"]
    undone = service.undo(session_id)
    assert undone["generation"] > before_undo_generation
    assert undone["document"]["menus"][2]["sort"] == []
    redone = service.redo(session_id)
    assert redone["document"]["menus"][2]["sort"][0]["fieldId"] == "year"

    saved = service.save(session_id)
    assert saved["snapshot"]["dirty"] is False
    reopened = service.load("org.steamzero.retro")
    assert reopened["dirty"] is False
    assert reopened["document"] == saved["snapshot"]["document"]

    preview = service.preview_menu(
        reopened["sessionId"],
        "games",
        rows=[
            {"id": "rpg-94", "platformId": "snes", "genre": "RPG", "year": 1994},
            {"id": "rpg-92", "platformId": "snes", "genre": "RPG", "year": 1992},
            {"id": "nes-rpg", "platformId": "nes", "genre": "RPG", "year": 1988},
        ],
        published_fields={
            "id": "string",
            "platformId": "string",
            "genre": "string",
            "year": "integer",
        },
        published_read_models={
            "library.platforms": {"id": "string", "name": "string"},
            "library.games": {
                "id": "string",
                "platformId": "string",
                "genre": "string",
                "year": "integer",
            },
        },
        context_filters={"platformId": "snes"},
    )
    assert preview["resultState"] == "results"
    assert [row["id"] for row in preview["rows"]] == ["rpg-94", "rpg-92"]
    assert preview["groups"][0]["count"] == 2
    with pytest.raises(JourneyValidationError):
        service.preview_menu(
            reopened["sessionId"],
            "games",
            rows=[],
            published_fields={"year": "integer"},
            published_read_models={"library.games": {"year": "integer"}},
        )


def test_schema_rejection_is_atomic_and_stale_edits_are_refused(tmp_path: Path) -> None:
    service = JourneyStudioService(tmp_path / "journeys")
    opened = service.create(journey_id="org.steamzero.atomic")
    session_id = opened["sessionId"]
    generation = opened["generation"]

    with pytest.raises(ValidationError):
        service.transact(
            session_id,
            "set-filters",
            {
                "menuId": "home",
                "values": [{"fieldId": "year", "operator": "oneOf"}],
            },
        )
    unchanged = service.snapshot(session_id)
    assert unchanged["generation"] == generation
    assert unchanged["document"]["menus"][0]["filters"] == []

    with pytest.raises(ValueError, match="rascunho mudou"):
        service.transact(
            session_id,
            "rename-journey",
            {"name": "Nome antigo"},
            expected_generation=generation - 1,
        )


def test_save_blocks_graph_errors_and_import_shows_document_only_dependencies(
    tmp_path: Path,
) -> None:
    service = JourneyStudioService(tmp_path / "journeys")
    opened = service.create(name="Dependente", journey_id="org.steamzero.dependent")
    session_id = opened["sessionId"]
    service.transact(
        session_id,
        "set-menu-appearance",
        {
            "menuId": "home",
            "appearance": {"mode": "custom", "themeId": "org.steamzero.nebula"},
        },
    )
    service.transact(
        session_id,
        "add-connection",
        {
            "connection": _connection(
                "dangling-route",
                "home",
                "select",
                "navigate",
                {"kind": "menu", "id": "missing"},
            )
        },
    )
    with pytest.raises(JourneyValidationError):
        service.save(session_id)
    assert not (tmp_path / "journeys" / "org.steamzero.dependent.journey.json").exists()

    service.transact(session_id, "remove-connection", {"connectionId": "dangling-route"})
    service.save(session_id)
    bundle = JourneyStore(tmp_path / "journeys").export_copy(
        JourneyDocument.parse(
            (tmp_path / "journeys" / "org.steamzero.dependent.journey.json").read_bytes()
        )
    )
    imported = service.import_copy(bundle, copy_name="Cópia")
    assert imported["document"]["name"] == "Cópia"
    assert imported["packageContents"] == ["experience.json"]
    assert imported["dependencies"] == [
        {
            "themeId": "org.steamzero.nebula",
            "version": None,
            "state": "version-not-declared",
        }
    ]
    assert imported["dirty"] is True


def test_removing_referenced_menu_requires_explicit_reconnection(tmp_path: Path) -> None:
    service = JourneyStudioService(tmp_path / "journeys")
    opened = service.create(journey_id="org.steamzero.reconnect")
    session_id = opened["sessionId"]
    generation = opened["generation"]
    platforms = service.transact(
        session_id,
        "add-menu",
        {"menu": _menu("platforms", "Plataformas", "library.platforms")},
        expected_generation=generation,
    )
    generation = platforms["generation"]
    games = service.transact(
        session_id,
        "add-menu",
        {"menu": _menu("games", "Jogos", "library.games")},
        expected_generation=generation,
    )
    generation = games["generation"]
    replacement = service.transact(
        session_id,
        "add-menu",
        {"menu": _menu("games-next", "Jogos filtrados", "library.games")},
        expected_generation=generation,
    )
    generation = replacement["generation"]
    route = _connection(
        "platforms-to-games",
        "platforms",
        "select",
        "navigate",
        {"kind": "menu", "id": "games"},
    )
    service.transact(
        session_id,
        "add-connection",
        {"connection": route},
        expected_generation=generation,
    )

    with pytest.raises(ValueError, match="destino de substituição"):
        service.transact(session_id, "remove-menu", {"menuId": "games"})
    unchanged = service.snapshot(session_id)
    assert any(menu["id"] == "games" for menu in unchanged["document"]["menus"])
    assert unchanged["document"]["connections"][0]["to"]["id"] == "games"

    removed = service.transact(
        session_id,
        "remove-menu",
        {"menuId": "games", "replacementMenuId": "games-next"},
    )
    assert [menu["id"] for menu in removed["document"]["menus"]] == [
        "home",
        "platforms",
        "games-next",
    ]
    assert removed["document"]["connections"][0]["to"] == {
        "kind": "menu",
        "id": "games-next",
    }
