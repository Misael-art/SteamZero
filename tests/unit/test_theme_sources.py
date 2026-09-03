# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Catálogo curado de temas ES-DE embutido no pacote."""

from __future__ import annotations

import pytest

from steamzero.core.errors import SteamZeroError
from steamzero.domain.theme_sources import bundled

_EXPECTED = {
    "org.esde.iconic",
    "org.esde.playstation-x",
    "org.esde.nso-menu",
    "org.esde.xmb-menu",
    "org.esde.modern",
}


def test_the_bundled_catalog_loads_and_lists_the_curated_themes() -> None:
    catalog = bundled()

    assert {entry.id for entry in catalog.entries} == _EXPECTED


def test_every_entry_declares_a_license() -> None:
    """Licença é gate, não metadado: distribuir arte de terceiro sem licença
    confirmada não é decisão que um catálogo curado toma em silêncio."""
    for entry in bundled().entries:
        assert entry.license_id.strip(), entry.id
        assert entry.license_source.strip(), entry.id


def test_every_entry_is_pinned_to_a_full_commit() -> None:
    """Um ramo move; um commit é o hash do próprio conteúdo.

    Fixar por commit é o que torna a aquisição reprodutível e faz o conteúdo
    mudar apenas quando alguém edita o catálogo — visível em diff, em vez de
    acontecer sozinho entre dois downloads.
    """
    for entry in bundled().entries:
        assert len(entry.commit) == 40, entry.id
        assert set(entry.commit) <= set("0123456789abcdef"), entry.id


def test_derived_themes_carry_the_upstream_credit() -> None:
    """CC-BY-NC-SA exige atribuição, e há obras derivadas no catálogo.

    Publicar só o dono do repositório apagaria quem fez o trabalho original.
    """
    catalog = bundled()
    playstation_x = catalog.get("org.esde.playstation-x")
    xmb = catalog.get("org.esde.xmb-menu")

    assert len(playstation_x.credits) > 1
    assert any("pajarorrojo" in credit for credit in playstation_x.credits)
    assert any("InitialDin" in credit for credit in xmb.credits)


def test_archive_url_targets_the_pinned_commit_on_a_known_forge() -> None:
    catalog = bundled()

    github = catalog.get("org.esde.xmb-menu")
    assert github.host == "codeload.github.com"
    assert github.commit in github.archive_url

    gitlab = catalog.get("org.esde.modern")
    assert gitlab.host == "gitlab.com"
    assert gitlab.commit in gitlab.archive_url


def test_themes_without_a_license_are_recorded_as_excluded_with_the_reason() -> None:
    """A exclusão fica registrada para que ninguém reintroduza o tema meses
    depois sem saber por que ele saiu — e para que a ausência não pareça
    esquecimento."""
    excluded = {item.repo: item.reason for item in bundled().excluded}

    assert "RobZombie9043/shinretro-revisited-es-de" in excluded
    assert "Weestuarty-es-de/slick-es-de" in excluded
    assert "VictorUnlocked/iisu-interpreted-es-de" in excluded
    assert "anthonycaccese/retrofix-revisited-es-de" in excluded
    for reason in excluded.values():
        assert "licen" in reason.casefold()


def test_an_excluded_theme_is_not_reachable_through_the_catalog() -> None:
    for theme_id in ("org.esde.slick", "org.esde.shinretro", "org.esde.iisu"):
        with pytest.raises(SteamZeroError) as excinfo:
            bundled().get(theme_id)
        assert excinfo.value.code == "E-THEME-NOT-FOUND"
