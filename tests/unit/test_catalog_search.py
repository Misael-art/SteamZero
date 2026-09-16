# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors

from steamzero.domain.catalog_search import (
    CatalogSearchQuery,
    matches_record,
    search_media,
    search_records,
)


def _record(**extra: object) -> dict[str, object]:
    return {
        "id": "zelda-botw",
        "title": "The Legend of Zelda: Breath of the Wild (USA).wud",
        "platformId": "wii-u",
        "systemId": "wiiu",
        "media": {
            "cover": {"path": "/media/zelda-cover.png"},
            "fanart": {"path": "/media/zelda-fanart.jpg"},
        },
        **extra,
    }


def test_query_is_accent_insensitive_and_uses_title_variants() -> None:
    query = CatalogSearchQuery(text="zelda breath wild")

    assert matches_record(_record(), query)


def test_platform_and_system_are_independent_exact_filters() -> None:
    record = _record()

    assert matches_record(record, CatalogSearchQuery(platform_id="WII-U"))
    assert matches_record(record, CatalogSearchQuery(system_id="WIIU"))
    assert not matches_record(record, CatalogSearchQuery(platform_id="ps4"))
    assert not matches_record(record, CatalogSearchQuery(system_id="switch"))


def test_absent_scope_is_global_and_media_kind_is_explicit() -> None:
    query = CatalogSearchQuery.from_mapping({"q": "zelda", "mediaKind": "fanart"})
    assert not query.is_global
    assert search_records([_record(), _record(id="other", title="Mario")], query) == (_record(),)
    assert search_records([_record(media={"cover": {"path": "/media/cover.png"}})], query) == ()


def test_global_media_search_does_not_default_to_switch() -> None:
    entries = [
        {"gameId": "zelda-botw", "title": "Zelda", "platformId": "wii-u", "kind": "fanart"},
        {"gameId": "astro", "title": "Astro", "platformId": "ps4", "kind": "cover"},
    ]

    assert search_media(entries, CatalogSearchQuery(text="astro")) == (entries[1],)
    assert search_media(entries, CatalogSearchQuery(platform_id="ps4", media_kind="cover")) == (
        entries[1],
    )


def test_mapping_envelope_accepts_cli_aliases() -> None:
    query = CatalogSearchQuery.from_mapping(
        {"query": "mário", "platform": "switch", "system": "switch"}
    )
    assert query == CatalogSearchQuery(text="mario", platform_id="switch", system_id="switch")
