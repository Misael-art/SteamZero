# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors

from steamzero.core.title_variants import select_title_variant, title_variants


def test_variants_remove_extension_then_trailing_metadata() -> None:
    assert title_variants("Batman - The Video Game (USA) (Translated PtBr).7z") == (
        "Batman - The Video Game (USA) (Translated PtBr).7z",
        "Batman - The Video Game (USA) (Translated PtBr)",
        "Batman - The Video Game (USA)",
        "Batman - The Video Game",
    )


def test_variants_handle_parentheses_and_bracket_markers() -> None:
    assert title_variants("AV Bishoujo Senshi Girl Fighting (Bootleg).nes")[-1] == (
        "AV Bishoujo Senshi Girl Fighting"
    )
    assert title_variants("Crime Busters (Unl) [!].nes") == (
        "Crime Busters (Unl) [!].nes",
        "Crime Busters (Unl) [!]",
        "Crime Busters (Unl)",
        "Crime Busters",
    )
    assert title_variants("Panic! Dizzy (World) (Proto) (Unl).zip")[-3:] == (
        "Panic! Dizzy (World) (Proto)",
        "Panic! Dizzy (World)",
        "Panic! Dizzy",
    )


def test_title_modes_are_explicit_and_preserve_original_by_default() -> None:
    value = "Batman - The Video Game (USA).7z"
    assert select_title_variant(value) == value
    assert select_title_variant(value, "extensionless") == "Batman - The Video Game (USA)"
    assert select_title_variant(value, "clean") == "Batman - The Video Game"
