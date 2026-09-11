# SPDX-License-Identifier: GPL-3.0-or-later
import pytest

from steamzero.domain.scene_layout import LayoutBounds, LayoutRecipe
from steamzero.launcher.cinema import cinema_window, resolve_cinema_covers


def test_metadata_projects_only_known_fields_without_fabricating_absent_values() -> None:
    from steamzero.launcher.cinema import cinema_metadata

    assert cinema_metadata({}) == {}
    result = cinema_metadata(
        {
            "description": "Descrição",
            "players": 2,
            "playtime": 0,
            "genres": ["Adventure"],
            "secret": "never-publish",
            "media": {
                "fanart": {"path": "/art/game #1.png"},
                "cover": {"path": "relative.png"},
                "video": {"path": "https://example.org/video.mp4"},
            },
        }
    )
    assert result == {
        "description": "Descrição",
        "players": 2,
        "playtime": 0,
        "genres": ["Adventure"],
        "fanartUrl": "file:///art/game%20%231.png",
    }
    assert (
        cinema_metadata(
            {"players": True, "playtime": -1, "media": {"cover": {"path": "/art/../secret.png"}}}
        )
        == {}
    )


@pytest.mark.parametrize("count", [0, 1, 2, 3, 6, 7, 8, 512, 1131])
def test_window_is_bounded_unique_and_keeps_selected_game(count: int) -> None:
    items = [{"id": str(index)} for index in range(count)]
    for selected in range(max(1, count)):
        window = cinema_window(items, selected)
        assert len(window.items) == min(count, 7)
        assert len(set(window.source_indices)) == len(window.items)
        if count:
            assert window.items[window.selected] is items[selected]
            assert window.source_indices[window.selected] == selected


@pytest.mark.parametrize("selected", [-1, 2, True])
def test_invalid_selection_is_not_silently_retargeted(selected: int) -> None:
    with pytest.raises(ValueError):
        cinema_window([{"id": "a"}, {"id": "b"}], selected)


def test_large_library_selection_reaches_existing_engine_without_truncation() -> None:
    recipe = LayoutRecipe.from_dict(
        "covers",
        {
            "source": "library.games",
            "kind": "coverFlow",
            "item": {"width": 240, "height": 360},
            "template": {
                "id": "cover",
                "kind": "image",
                "properties": {"source": {"binding": "item.coverUrl", "fallback": ""}},
            },
            "highlight": {"scale": 1.2, "outlineWidth": 3},
        },
    )
    items = [{"coverUrl": f"file:///covers/{index}.png"} for index in range(1131)]
    result = resolve_cinema_covers(recipe, items, 1100, bounds=LayoutBounds(1280, 800))
    entries = result["layouts"]["covers"]["entries"]
    assert len(entries) == 7
    selected = [entry for entry in entries if entry["highlighted"]]
    assert len(selected) == 1
    assert selected[0]["source"] == "file:///covers/1100.png"
    assert selected[0]["scale"] == 1.2
    assert result["diagnostics"] == []
    assert recipe.source == "library.games"
