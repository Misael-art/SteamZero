# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from pathlib import Path

import pytest
from jsonschema import ValidationError

from steamzero.api import contracts
from steamzero.domain.experience_journey import (
    MAX_NAVIGATION_HISTORY,
    JourneyBudgetError,
    JourneyDocument,
    JourneyNavigator,
    JourneyRouteError,
    JourneyStore,
    PublicFieldUnavailable,
    filter_public_records,
    query_public_records,
    resolve_theme_coverage,
    summarize_theme_coverage,
)


def _document() -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "kind": "steamzero-experience-journey-v1",
        "id": "org.steamzero.my-journey",
        "name": "Minha jornada",
        "entryMenuId": "platforms",
        "organization": [
            {"id": "explore", "kind": "group", "label": "Explorar", "parentId": None},
            {
                "id": "platforms-placement",
                "kind": "menu",
                "label": "Plataformas",
                "parentId": "explore",
                "menuId": "platforms",
            },
            {
                "id": "games-placement",
                "kind": "menu",
                "label": "Jogos",
                "parentId": "explore",
                "menuId": "games",
            },
            {
                "id": "genre-placement",
                "kind": "menu",
                "label": "Por gênero",
                "parentId": "explore",
                "menuId": "by-genre",
            },
        ],
        "menus": [
            {
                "id": "platforms",
                "name": "Plataformas",
                "source": {"readModelId": "library.platforms"},
                "filters": [],
                "sort": [{"fieldId": "name", "direction": "ascending"}],
                "appearance": {"mode": "custom", "themeId": "org.steamzero.nebula"},
            },
            {
                "id": "games",
                "name": "Jogos",
                "source": {"readModelId": "library.games"},
                "filters": [{"fieldId": "platformId", "operator": "equals", "value": "nes"}],
                "sort": [{"fieldId": "year", "direction": "descending"}],
            },
            {
                "id": "by-genre",
                "name": "Por gênero",
                "source": {"readModelId": "library.games"},
                "filters": [{"fieldId": "genre", "operator": "isKnown"}],
                "sort": [{"fieldId": "genre", "direction": "ascending"}],
            },
        ],
        "connections": [
            {
                "id": "platforms-to-games",
                "from": {"kind": "menu", "id": "platforms"},
                "event": "select",
                "when": "user-input",
                "action": "navigate",
                "to": {"kind": "menu", "id": "games"},
                "label": "Escolher plataforma",
            },
            {
                "id": "games-back",
                "from": {"kind": "menu", "id": "games"},
                "event": "back",
                "when": "user-input",
                "action": "back",
                "to": {"kind": "history"},
                "label": "Voltar",
            },
            {
                "id": "genre-to-games",
                "from": {"kind": "menu", "id": "by-genre"},
                "event": "select",
                "when": "user-input",
                "action": "navigate",
                "to": {"kind": "menu", "id": "games"},
                "label": "Ver jogos",
            },
        ],
        "sessionStages": [
            {"stageId": "pause", "appearance": {"mode": "inherit-aura"}},
            {
                "stageId": "entryFade",
                "appearance": {"mode": "custom", "themeId": "org.steamzero.deleted"},
            },
            {
                "stageId": "exitFade",
                "appearance": {"mode": "custom", "themeId": "org.steamzero.limited"},
            },
        ],
    }


def _parsed() -> JourneyDocument:
    return JourneyDocument.parse(_document())


def test_versioned_document_supports_three_menus_shared_targets_and_round_trip() -> None:
    document = _parsed()
    assert document.entry_menu_id == "platforms"
    assert document.menu_ids == {"platforms", "games", "by-genre"}
    assert [
        edge["to"] for edge in document.data["connections"] if edge["to"]["kind"] == "menu"
    ] == [
        {"kind": "menu", "id": "games"},
        {"kind": "menu", "id": "games"},
    ]

    reopened = JourneyDocument.parse(document.serialize())
    assert reopened.data == document.data
    contracts.validate(reopened.data, "experience-journey-v1.schema.json")


def test_local_store_and_export_import_copy_preserve_the_journey(tmp_path: Path) -> None:
    store = JourneyStore(tmp_path / "journeys")
    original = _parsed()
    destination = store.save(original)
    assert destination.exists()
    assert destination.stat().st_mode & 0o777 == 0o600
    assert store.load(original.id).data == original.data
    with pytest.raises(FileExistsError):
        store.save(original)
    store.save(original, overwrite=True)

    bundle = store.export_copy(original)
    copied = store.import_copy(
        bundle,
        copy_id="org.steamzero.copy-1",
        copy_name="Cópia da jornada",
    )
    expected = dict(original.data)
    expected["id"] = "org.steamzero.copy-1"
    expected["name"] = "Cópia da jornada"
    assert copied.data == expected


def test_local_store_refuses_symlinked_documents(tmp_path: Path) -> None:
    store = JourneyStore(tmp_path / "journeys")
    store.root.mkdir()
    original = _parsed()
    external = tmp_path / "external.json"
    external.write_bytes(original.serialize())
    store._path(original.id).symlink_to(external)
    with pytest.raises(ValueError, match="link simbólico"):
        store.load(original.id)


def test_schema_rejects_undeclared_properties_and_unsafe_actions() -> None:
    invalid = _document()
    invalid["script"] = "return os.system('echo unsafe')"
    with pytest.raises(ValidationError):
        JourneyDocument.parse(invalid)

    invalid = _document()
    invalid["connections"][0]["action"] = "run-shell"
    with pytest.raises(ValidationError):
        JourneyDocument.parse(invalid)


def test_diagnostics_allow_input_cycles_but_reject_dangling_and_automatic_loops() -> None:
    raw = _document()
    raw["connections"].append(
        {
            "id": "games-to-platforms",
            "from": {"kind": "menu", "id": "games"},
            "event": "back",
            "when": "user-input",
            "action": "navigate",
            "to": {"kind": "menu", "id": "platforms"},
            "label": "Voltar às plataformas",
        }
    )
    document = JourneyDocument.parse(raw)
    assert "JOURNEY-AUTOMATIC-CYCLE" not in {issue.code for issue in document.diagnostics()}

    raw["connections"].extend(
        [
            {
                "id": "auto-a",
                "from": {"kind": "menu", "id": "platforms"},
                "event": "play",
                "when": "operation-success",
                "action": "navigate",
                "to": {"kind": "menu", "id": "games"},
                "label": "Avançar automaticamente",
            },
            {
                "id": "auto-b",
                "from": {"kind": "menu", "id": "games"},
                "event": "retry",
                "when": "timeout",
                "action": "navigate",
                "to": {"kind": "menu", "id": "platforms"},
                "label": "Retorno automático",
            },
            {
                "id": "broken",
                "from": {"kind": "menu", "id": "games"},
                "event": "select",
                "when": "user-input",
                "action": "navigate",
                "to": {"kind": "menu", "id": "deleted"},
                "label": "Destino removido",
            },
        ]
    )
    codes = {issue.code for issue in JourneyDocument.parse(raw).diagnostics()}
    assert "JOURNEY-AUTOMATIC-CYCLE" in codes
    assert "JOURNEY-REFERENCE-MISSING" in codes

    bad_outline = _document()
    bad_outline["organization"][0]["parentId"] = "platforms-placement"
    assert "JOURNEY-ORGANIZATION-CYCLE" in {
        issue.code for issue in JourneyDocument.parse(bad_outline).diagnostics()
    }


def test_dynamic_public_fields_and_combined_filters_preserve_unknown_values() -> None:
    rows = [
        {"platformId": "nes", "genre": "RPG", "year": 1992},
        {"platformId": "nes", "genre": None, "year": 1991},
        {"platformId": "snes", "genre": "RPG", "year": 1994},
    ]
    filters = [
        {"fieldId": "platformId", "operator": "equals", "value": "nes"},
        {"fieldId": "genre", "operator": "contains", "value": "rp"},
        {"fieldId": "year", "operator": "greaterThanOrEqual", "value": 1992},
    ]
    assert filter_public_records(
        rows,
        filters,
        published_field_ids={"platformId", "genre", "year"},
    ) == [rows[0]]
    assert filter_public_records(
        rows,
        [{"fieldId": "genre", "operator": "isUnknown"}],
        published_field_ids={"genre"},
    ) == [rows[1]]
    with pytest.raises(PublicFieldUnavailable):
        filter_public_records(
            rows,
            [{"fieldId": "internalTable.sql", "operator": "equals", "value": "x"}],
            published_field_ids={"genre"},
        )


def test_public_query_reports_source_empty_unknown_and_typed_filter_states() -> None:
    unavailable = query_public_records(None, [], published_fields={"year": "integer"})
    assert unavailable.result_state == "source-unavailable"
    assert unavailable.recovery_action == "retry-source"

    rows = [{"year": 1992, "genre": "RPG"}, {"year": None, "genre": None}]
    result = query_public_records(
        rows,
        [{"fieldId": "year", "operator": "greaterThanOrEqual", "value": 1990}],
        published_fields={"year": "integer", "genre": "string"},
    )
    assert result.result_state == "results"
    assert result.total_count == 2 and result.result_count == 1
    assert result.unknown_value_counts == {"year": 1, "genre": 1}

    empty = query_public_records(
        rows,
        [{"fieldId": "genre", "operator": "equals", "value": "Platform"}],
        published_fields={"genre": "string"},
    )
    assert empty.result_state == "zero-results"
    assert empty.recovery_action == "clear-filters"

    mistyped = query_public_records(
        rows,
        [{"fieldId": "year", "operator": "equals", "value": "1992"}],
        published_fields={"year": "integer"},
    )
    assert mistyped.result_state == "invalid-filter"
    assert mistyped.diagnostic_code == "JOURNEY-FILTER-TYPE"
    assert mistyped.recovery_action == "adjust-filter-type"


def test_source_and_filter_diagnostics_follow_the_published_schema() -> None:
    raw = _document()
    raw["menus"][1]["filters"].append(
        {"fieldId": "manufacturer", "operator": "equals", "value": "Nintendo"}
    )
    diagnostics = JourneyDocument.parse(raw).diagnostics(
        published_read_models={"library.games": {"platformId", "genre", "year"}}
    )
    assert any(issue.code == "JOURNEY-FIELD-UNAVAILABLE" for issue in diagnostics)
    assert any(issue.code == "JOURNEY-READ-MODEL-UNAVAILABLE" for issue in diagnostics)


def test_navigation_restores_full_origin_context_and_ignores_late_route_responses() -> None:
    navigator = JourneyNavigator(_parsed())
    origin = navigator.update_context(
        selected_item_id="nes",
        filters={"platformId": "nes", "year": 1992},
        scroll_position=31.5,
        focus_id="platform-row-8",
    )
    navigator.navigate("by-genre", filters={"platformId": "nes", "genre": "RPG"})
    genre_context = navigator.context
    navigator.navigate("games", filters={"platformId": "nes", "genre": "RPG"})
    assert navigator.back() == genre_context
    assert navigator.back() == origin

    saved = navigator.capture_return_context()
    assert navigator.restore_return_context(saved)
    pending_generation = navigator.generation
    navigator.navigate("games")
    assert not navigator.accepts_response(pending_generation)
    assert not navigator.restore_return_context(saved)
    assert navigator.context.menu_id == "games"


def test_navigation_diagnoses_invalid_destinations_and_history_budget() -> None:
    navigator = JourneyNavigator(_parsed())
    with pytest.raises(JourneyRouteError):
        navigator.navigate("missing")
    for _ in range(MAX_NAVIGATION_HISTORY):
        navigator.navigate("games")
    with pytest.raises(JourneyBudgetError, match="histórico") as error:
        navigator.navigate("games")
    assert error.value.code == "JOURNEY-BUDGET-HISTORY"


def test_theme_coverage_explains_aura_omissions_references_and_capabilities() -> None:
    coverage = resolve_theme_coverage(
        _parsed(),
        used_stages=["menu:platforms", "menu:games", "pause", "saves", "entryFade", "exitFade"],
        themes={
            "org.steamzero.nebula": {"version": "1.2.0", "capabilities": ["scene.layout"]},
            "org.steamzero.limited": {"version": "1.0.0", "capabilities": ["scene.layout"]},
        },
        aura_version="2.0.0rc1",
        required_theme_capabilities={"exitFade": ["scene.motion"]},
        adapter_capabilities=set(),
        operation_requirements={"pause": ["session.pause"], "saves": ["session.saves.list"]},
    )
    by_id = {row["stageId"]: row for row in coverage}
    assert by_id["menu:platforms"]["appearance"] == "custom"
    assert by_id["menu:games"]["appearance"] == "inherited"
    assert by_id["menu:games"]["reason"] == "not-customized"
    assert by_id["pause"]["appearance"] == "inherited"
    assert by_id["pause"]["reason"] == "explicit-choice"
    assert by_id["saves"]["appearance"] == "inherited"
    assert by_id["entryFade"]["appearance"] == "missing-reference"
    assert by_id["entryFade"]["declaredThemeId"] == "org.steamzero.deleted"
    assert by_id["exitFade"]["appearance"] == "incompatible"
    assert by_id["exitFade"]["declaredThemeId"] == "org.steamzero.limited"
    assert by_id["exitFade"]["missingThemeCapabilities"] == ["scene.motion"]
    assert by_id["pause"]["operationCapability"] == "unavailable"
    assert by_id["saves"]["operationCapability"] == "unavailable"
    assert all(row["sourceThemeId"] == "org.steamzero.default" for row in coverage[1:])
    summary = summarize_theme_coverage(coverage)
    assert summary["auraDefaultCount"] == 3
    assert summary["auraFallbackCount"] == 5
    assert summary["requiresPreApplyConfirmation"]
    assert "3 etapas usam AURA padrão" in summary["label"]
    assert summary["missingReferenceStages"] == ["entryFade"]
    assert summary["incompatibleStages"] == ["exitFade"]
    assert summary["unavailableOperationStages"] == ["pause", "saves"]
