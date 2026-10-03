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
    JourneyExecutor,
    JourneyNavigator,
    JourneyRouteError,
    JourneyStore,
    JourneyValidationError,
    PublicFieldUnavailable,
    filter_public_records,
    migrate_journey_v1_to_v2,
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
    contracts.validate(reopened.data, "experience-journey-v2.schema.json")
    assert all("groupBy" in menu for menu in reopened.data["menus"])
    assert all("bindings" in connection for connection in reopened.data["connections"])


def test_v1_migration_adds_v2_defaults_without_changing_declared_routes() -> None:
    legacy = _document()
    legacy_connections = legacy["connections"]
    migrated = JourneyDocument.parse(legacy)

    assert migrated.data["schemaVersion"] == 2
    assert migrated.data["kind"] == "steamzero-experience-journey-v2"
    assert [edge["id"] for edge in migrated.data["connections"]] == [
        edge["id"] for edge in legacy_connections
    ]
    assert all(menu["groupBy"] == [] for menu in migrated.data["menus"])
    assert all(edge["bindings"] == [] for edge in migrated.data["connections"])


def test_connection_binding_filters_the_target_read_model_and_back_restores_origin() -> None:
    raw = migrate_journey_v1_to_v2(_document())
    raw["menus"][1]["filters"] = []
    raw["menus"][1]["groupBy"] = ["genre"]
    raw["connections"][0]["bindings"] = [
        {"sourceFieldId": "platformId", "targetFieldId": "platformId"}
    ]
    document = JourneyDocument.parse(raw)
    navigator = JourneyNavigator(document)
    executor = JourneyExecutor(document, navigator)
    games = [
        {"id": "snes-rpg", "platformId": "snes", "genre": "RPG", "year": 1994},
        {"id": "snes-action", "platformId": "snes", "genre": "Action", "year": 1992},
        {"id": "nes-rpg", "platformId": "nes", "genre": "RPG", "year": 1988},
    ]
    fields = {
        "library.platforms": {"platformId": "string"},
        "library.games": {
            "id": "string",
            "platformId": "string",
            "genre": "string",
            "year": "integer",
        },
    }

    routed = executor.execute(
        "select",
        selected_record={"platformId": "snes"},
        selected_item_id="snes",
        scroll_position=62,
        focus_id="platform-snes",
        read_models={"library.games": games},
        published_read_models=fields,
    )

    assert routed.state == "navigated"
    assert routed.context is not None
    assert routed.context.menu_id == "games"
    assert dict(routed.context.filters) == {"platformId": "snes"}
    assert routed.query is not None
    assert [row["id"] for row in routed.query.rows] == ["snes-rpg", "snes-action"]
    assert routed.query.groups[0]["values"]["genre"] == "RPG"

    back = executor.execute("back")
    assert back.state == "navigated"
    assert back.context == navigator.context
    assert back.context.menu_id == "platforms"
    assert back.context.selected_item_id == "snes"
    assert back.context.scroll_position == 62
    assert back.context.focus_id == "platform-snes"


def test_connection_binding_rejects_unknown_selection_with_recovery() -> None:
    raw = migrate_journey_v1_to_v2(_document())
    raw["menus"][1]["filters"] = []
    raw["connections"][0]["bindings"] = [
        {"sourceFieldId": "platformId", "targetFieldId": "platformId"}
    ]
    document = JourneyDocument.parse(raw)
    executor = JourneyExecutor(document)
    result = executor.execute(
        "select",
        selected_record={"platformId": None},
        published_read_models={
            "library.platforms": {"platformId": "string"},
            "library.games": {"platformId": "string"},
        },
    )

    assert result.state == "invalid-binding"
    assert result.diagnostic_code == "JOURNEY-BINDING-SOURCE-UNKNOWN"
    assert result.recovery_action == "select-known-value"
    assert executor.navigator.context.menu_id == "platforms"


def test_session_operation_is_intent_only_and_late_return_cannot_change_route() -> None:
    raw = _document()
    raw["connections"].extend(
        [
            {
                "id": "games-launch",
                "from": {"kind": "menu", "id": "games"},
                "event": "play",
                "when": "user-input",
                "action": "launch",
                "to": {"kind": "stage", "id": "entryFade"},
                "label": "Jogar",
            },
            {
                "id": "gameplay-return",
                "from": {"kind": "stage", "id": "gameplay"},
                "event": "back",
                "when": "operation-success",
                "action": "back",
                "to": {"kind": "history"},
                "label": "Retornar",
            },
        ]
    )
    document = JourneyDocument.parse(raw)
    navigator = JourneyNavigator(document)
    executor = JourneyExecutor(document, navigator)
    navigator.navigate("games")

    launch = executor.execute("play")
    assert launch.state == "operation-request"
    assert launch.action == "launch"
    assert launch.target == {"kind": "stage", "id": "entryFade"}
    assert launch.return_context is not None

    navigator.navigate("by-genre")
    late_return = executor.execute(
        "back",
        when="operation-success",
        source_endpoint={"kind": "stage", "id": "gameplay"},
        pending_return=launch.return_context,
    )
    assert late_return.state == "stale-response"
    assert navigator.context.menu_id == "by-genre"


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


def test_one_of_requires_a_nonempty_value_collection() -> None:
    missing_value = _document()
    missing_value["menus"][1]["filters"] = [{"fieldId": "year", "operator": "oneOf"}]
    with pytest.raises(ValidationError):
        JourneyDocument.parse(missing_value)

    empty_value = _document()
    empty_value["menus"][1]["filters"] = [{"fieldId": "year", "operator": "oneOf", "value": []}]
    with pytest.raises(ValidationError):
        JourneyDocument.parse(empty_value)


def test_numeric_comparison_with_null_is_an_invalid_filter_with_recovery() -> None:
    result = query_public_records(
        [{"year": 1992}],
        [{"fieldId": "year", "operator": "greaterThanOrEqual", "value": None}],
        published_fields={"year": "integer"},
    )

    assert result.result_state == "invalid-filter"
    assert result.diagnostic_code == "JOURNEY-FILTER-TYPE"
    assert "null" in result.diagnostic_message
    assert result.recovery_action == "adjust-filter-type"


def test_public_query_sorts_unknowns_last_and_groups_public_facets() -> None:
    rows = [
        {"id": "a", "year": 1990, "genre": "RPG"},
        {"id": "b", "year": None, "genre": None},
        {"id": "c", "year": 1995, "genre": "RPG"},
        {"id": "d", "year": 1992, "genre": "Action"},
    ]
    result = query_public_records(
        rows,
        [],
        published_fields={"id": "string", "year": "integer", "genre": "string"},
        sort=[{"fieldId": "year", "direction": "descending"}],
        group_by=["genre"],
    )

    assert [row["id"] for row in result.rows] == ["c", "d", "a", "b"]
    assert [(group["values"]["genre"], group["count"]) for group in result.groups] == [
        ("RPG", 2),
        ("Action", 1),
        (None, 1),
    ]
    assert [row["id"] for row in result.groups[0]["rows"]] == ["c", "a"]


def test_public_query_reports_unpublished_sort_and_group_fields() -> None:
    sort_result = query_public_records(
        [{"year": 1992}],
        [],
        published_fields={"year": "integer"},
        sort=[{"fieldId": "private.path", "direction": "ascending"}],
    )
    assert sort_result.result_state == "invalid-filter"
    assert sort_result.diagnostic_code == "JOURNEY-SORT-FIELD-UNAVAILABLE"
    assert sort_result.recovery_action == "replace-sort"

    group_result = query_public_records(
        [{"year": 1992}],
        [],
        published_fields={"year": "integer"},
        group_by=["internalDatabaseId"],
    )
    assert group_result.result_state == "invalid-filter"
    assert group_result.diagnostic_code == "JOURNEY-GROUP-FIELD-UNAVAILABLE"
    assert group_result.recovery_action == "replace-grouping"


def test_document_data_is_a_mutable_snapshot_not_the_validated_state(tmp_path: Path) -> None:
    original = _parsed()
    original_bytes = original.serialize()
    snapshot = original.data
    snapshot["menus"][0]["id"] = "corrupted"  # type: ignore[index]
    snapshot["menus"].append({"id": "unvalidated"})  # type: ignore[union-attr]

    assert original.serialize() == original_bytes
    assert original.menu_ids == {"platforms", "games", "by-genre"}
    persisted = JourneyStore(tmp_path / "journeys").save(original)
    assert JourneyDocument.parse(persisted.read_bytes()).serialize() == original_bytes


def test_invalid_graph_cannot_be_saved_or_activated(tmp_path: Path) -> None:
    invalid = _document()
    invalid["entryMenuId"] = "deleted-menu"
    document = JourneyDocument.parse(invalid)

    with pytest.raises(JourneyValidationError, match="menu de entrada não existe"):
        JourneyStore(tmp_path / "journeys").save(document)
    with pytest.raises(JourneyValidationError, match="menu de entrada não existe"):
        JourneyNavigator(document)

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
    assert all(issue.severity == "warning" for issue in diagnostics)

    with pytest.raises(JourneyValidationError) as raised:
        JourneyDocument.parse(raw).ensure_activatable(
            published_read_models={"library.games": {"platformId", "genre", "year"}}
        )
    blocking = {issue.code for issue in raised.value.diagnostics}
    assert "JOURNEY-FIELD-UNAVAILABLE" in blocking
    assert "JOURNEY-READ-MODEL-UNAVAILABLE" in blocking


def test_runtime_navigation_can_require_the_live_public_read_model_catalog() -> None:
    document = JourneyDocument.parse(_document())
    published_models = {
        "library.platforms": {"name": "string"},
        "library.games": {
            "platformId": "string",
            "genre": "string",
            "year": "integer",
        },
    }
    JourneyExecutor(document, published_read_models=published_models)
    with pytest.raises(JourneyValidationError) as raised:
        JourneyExecutor(
            document, published_read_models={"library.games": published_models["library.games"]}
        )
    assert any(issue.code == "JOURNEY-READ-MODEL-UNAVAILABLE" for issue in raised.value.diagnostics)


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


def test_partial_context_updates_preserve_selection_filters_scroll_and_focus() -> None:
    navigator = JourneyNavigator(_parsed())
    original = navigator.update_context(
        selected_item_id="nes",
        filters={"platformId": "nes", "genre": "RPG"},
        scroll_position=31.5,
        focus_id="game-row-3",
    )

    changed_scroll = navigator.update_context(scroll_position=44)
    assert changed_scroll.scroll_position == 44
    assert changed_scroll.selected_item_id == "nes"
    assert changed_scroll.filters == original.filters
    assert changed_scroll.focus_id == "game-row-3"

    changed_focus = navigator.update_context(focus_id="game-row-4")
    assert changed_focus.scroll_position == 44
    assert changed_focus.filters == original.filters
    assert changed_focus.selected_item_id == "nes"
    assert changed_focus.focus_id == "game-row-4"

    cleared = navigator.update_context(selected_item_id=None, filters={})
    assert cleared.selected_item_id is None
    assert cleared.filters == ()
    assert cleared.scroll_position == 44
    assert cleared.focus_id == "game-row-4"


def test_executor_partial_context_update_does_not_clear_other_origin_state() -> None:
    document = _parsed()
    navigator = JourneyNavigator(document)
    executor = JourneyExecutor(document, navigator)
    origin = navigator.update_context(
        selected_item_id="nes",
        filters={"year": 1992, "platformId": "nes"},
        scroll_position=29,
        focus_id="platform-nes",
    )

    result = executor.execute("select", selected_item_id="snes")
    assert result.state == "navigated"
    restored = navigator.back()
    assert restored is not None
    assert restored.selected_item_id == "snes"
    assert restored.filters == origin.filters
    assert restored.scroll_position == 29
    assert restored.focus_id == "platform-nes"


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
            "org.steamzero.nebula": {
                "version": "1.2.0",
                "capabilities": ["scene.layout"],
                "sceneSurfaces": {
                    "slots": {"library": {"component": "platform-list"}},
                    "components": {
                        "platform-list": {
                            "kind": "gameGrid",
                            "source": "library.platforms",
                            "maxItems": 8,
                        }
                    },
                },
            },
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
    assert by_id["menu:platforms"]["providedSceneElements"] == ["library:platform-list:gameGrid"]
    assert by_id["exitFade"]["missingSceneElements"] == ["sceneMotion.transition:exitFade"]
    assert by_id["pause"]["operationCapability"] == "unavailable"
    assert by_id["saves"]["operationCapability"] == "unavailable"
    assert all(row["sourceThemeId"] == "org.steamzero.default" for row in coverage[1:])
    summary = summarize_theme_coverage(coverage)
    assert summary["auraDefaultCount"] == 2
    assert summary["auraExplicitCount"] == 1
    assert summary["auraFallbackCount"] == 2
    assert summary["auraEffectiveCount"] == 5
    assert summary["requiresPreApplyConfirmation"]
    assert "2 herdadas, 1 escolhidas, 2 em fallback" in summary["label"]
    assert summary["missingReferenceStages"] == ["entryFade"]
    assert summary["incompatibleStages"] == ["exitFade"]
    assert summary["unavailableOperationStages"] == ["pause", "saves"]
