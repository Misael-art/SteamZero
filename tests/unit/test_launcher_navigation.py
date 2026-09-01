# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contrato de foco da home do AURA Launcher: navegação por controle sem becos."""

from __future__ import annotations

import pytest

from steamzero.launcher.navigation import (
    DIAG_FOCUS_EMPTY,
    HomeSection,
    resolve_home_focus,
)


def _sections() -> tuple[HomeSection, ...]:
    return (
        HomeSection(id="continue", title="Continuar", items=("celeste", "hades")),
        HomeSection(id="library", title="Biblioteca", items=("tunic", "axiom", "sable")),
        HomeSection(id="collections", title="Coleções", items=("favoritos",)),
    )


def test_every_focusable_node_can_be_left_in_some_direction() -> None:
    """Beco de foco é o defeito clássico de launcher por controle.

    Um nó de onde nenhuma direção sai prende o usuário sem mouse e sem toque —
    e num handheld isso significa reiniciar a sessão.
    """
    focus = resolve_home_focus(_sections())
    assert focus.nodes
    for node in focus.nodes.values():
        exits = [node.up, node.down, node.left, node.right]
        assert any(target is not None for target in exits), node.id


def test_focus_moves_between_sections_and_wraps_inside_a_row() -> None:
    focus = resolve_home_focus(_sections())
    first_row = focus.nodes["continue:celeste"]
    assert first_row.right == "continue:hades"
    # A linha dá a volta nos dois sentidos: da última coluna a direita retorna
    # à primeira, e da primeira a esquerda vai para a última.
    assert focus.nodes["continue:hades"].right == "continue:celeste"
    assert first_row.left == "continue:hades"
    assert focus.nodes["library:tunic"].left == "library:sable"
    assert focus.nodes["library:axiom"].left == "library:tunic"
    # Descer troca de seção, preservando a coluna quando ela existe.
    assert first_row.down == "library:tunic"
    assert focus.nodes["library:sable"].down == "collections:favoritos"
    # Coluna inexistente na seção de baixo cai no item mais próximo.
    assert focus.nodes["library:axiom"].down == "collections:favoritos"


def test_the_first_row_does_not_dead_end_upwards() -> None:
    focus = resolve_home_focus(_sections())
    top = focus.nodes["continue:celeste"]
    assert top.up is not None
    assert focus.initial == "continue:celeste"


def test_an_empty_home_still_has_somewhere_to_focus() -> None:
    """Home vazia é onde o beco costuma nascer: sem itens, sem foco, sem saída."""
    focus = resolve_home_focus(())
    assert focus.nodes
    assert focus.initial in focus.nodes
    assert any(item.code == DIAG_FOCUS_EMPTY for item in focus.diagnostics)
    node = focus.nodes[focus.initial]
    assert node.action is not None


def test_sections_without_items_do_not_produce_unreachable_focus() -> None:
    focus = resolve_home_focus(
        (
            HomeSection(id="continue", title="Continuar", items=()),
            HomeSection(id="library", title="Biblioteca", items=("tunic",)),
        )
    )
    assert "continue:" not in "".join(focus.nodes)
    assert focus.initial == "library:tunic"
    for node in focus.nodes.values():
        for target in (node.up, node.down, node.left, node.right):
            assert target is None or target in focus.nodes, node.id


def test_recipe_refuses_unsafe_shapes() -> None:
    with pytest.raises(ValueError, match="id"):
        HomeSection(id="Coleções!", title="x", items=("a",))
    with pytest.raises(ValueError, match="itens"):
        HomeSection(id="library", title="x", items=tuple(str(i) for i in range(600)))


def test_every_node_can_reach_the_initial_focus() -> None:
    """Ter saída não basta: dois nós apontando um para o outro seriam um beco.

    O contrato é conectividade — de qualquer lugar da home o usuário volta ao
    ponto de entrada apenas com o direcional.
    """
    focus = resolve_home_focus(_sections())
    for start in focus.nodes:
        seen = {start}
        queue = [start]
        while queue and focus.initial not in seen:
            node = focus.nodes[queue.pop()]
            for target in (node.up, node.down, node.left, node.right):
                if target is not None and target not in seen:
                    seen.add(target)
                    queue.append(target)
        assert focus.initial in seen, f"{start} não alcança o foco inicial"


def test_a_single_item_row_has_no_horizontal_wrap_to_itself() -> None:
    """Dar a volta numa linha de um item só devolveria o próprio nó.

    Isso pareceria movimento e não moveria nada — pior que recusar a direção.
    """
    focus = resolve_home_focus((HomeSection(id="only", title="Só", items=("um",)),))
    node = focus.nodes["only:um"]
    assert node.left is None
    assert node.right is None
    assert node.up == "header:home"


class TestBuildTitlesReadsTheCanonicalLabel:
    """A home mostrava o hash do id no lugar do titulo.

    Observado FISICAMENTE na release 2.0.0rc1-720928250e1a, com os 80 jogos do
    acervo real do host: os cartoes exibiam `ae18c7e53583298461a0edea` em vez de
    `1969 (Homebrew) (SMS)`. A biblioteca canonica publica o rotulo em `name`;
    `build_titles` lia so `title`, entao o fallback para o id disparava em TODO
    o acervo — nao num caso de borda.
    """

    def test_the_canonical_name_becomes_the_title(self) -> None:
        from steamzero.launcher.app import build_titles

        games = [{"id": "ae18c7e53583298461a0edea", "name": "1969 (Homebrew) (SMS)"}]
        assert build_titles(games) == {"ae18c7e53583298461a0edea": "1969 (Homebrew) (SMS)"}

    def test_title_still_works_as_an_alias(self) -> None:
        """Outras fontes usam `title`; aceitar as duas nao quebra ninguem."""
        from steamzero.launcher.app import build_titles

        assert build_titles([{"id": "celeste", "title": "Celeste"}]) == {"celeste": "Celeste"}

    def test_name_wins_when_both_exist(self) -> None:
        from steamzero.launcher.app import build_titles

        games = [{"id": "x", "name": "Nome canonico", "title": "Outro"}]
        assert build_titles(games) == {"x": "Nome canonico"}

    def test_the_id_is_the_last_resort_not_the_default(self) -> None:
        from steamzero.launcher.app import build_titles

        assert build_titles([{"id": "sem-rotulo"}]) == {"sem-rotulo": "sem-rotulo"}


class TestCanonicalHexIdentifiers:
    """O acervo real publica ids hexadecimais; o contrato precisa aceitá-los.

    O contrato exigia letra na primeira posição — convenção dos ids sintéticos
    (`header:home`, `empty:action`) aplicada sem querer ao acervo. Os ids
    canônicos são hex de 24 caracteres: 63% começam por dígito. No host, 147 dos
    231 jogos eram recusados e o Launcher encerrava antes da home.

    A fixture que já existia usava `ae18c7e53583298461a0edea`, que começa por
    letra e passava por sorte do sorteio. Por isso nenhum teste pegou o defeito.
    """

    def test_a_hex_id_starting_with_a_digit_is_accepted(self) -> None:
        from steamzero.launcher.identifiers import is_identifier

        assert is_identifier("5c5fd6b29bee06c2f1fb5ff5")
        assert is_identifier("0f40d4d28a0476a35c8bbaeb")
        assert is_identifier("ae18c7e53583298461a0edea")

    def test_a_section_accepts_the_whole_hex_catalog(self) -> None:
        section = HomeSection(
            id="outros",
            title="Outros",
            items=("5c5fd6b29bee06c2f1fb5ff5", "1f40d4d28a0476a35c8bbaeb"),
        )
        assert len(section.items) == 2

    def test_a_focus_id_pairs_two_hex_sides(self) -> None:
        from steamzero.launcher.identifiers import is_focus_id

        assert is_focus_id("outros:5c5fd6b29bee06c2f1fb5ff5")
        assert is_focus_id("header:home")

    @pytest.mark.parametrize(
        "value",
        [
            "-flag-que-parece-opcao",
            "com:dois-pontos",
            "com espaco",
            "com/barra",
            "com;ponto-e-virgula",
            "x" * 65,
            "",
        ],
    )
    def test_the_hazards_stay_rejected(self, value: str) -> None:
        """Alargar a cabeça do contrato não pode alargar o resto.

        Cada um destes viraria outra coisa ao atravessar foco, argv ou o
        separador do focus id — que é justamente o que o contrato protege.
        """
        from steamzero.launcher.identifiers import is_identifier

        assert not is_identifier(value)


class TestOneBadRecordDoesNotEmptyTheHome:
    """Um registro fora do contrato descarta a si mesmo, não a home inteira."""

    def test_an_invalid_item_is_dropped_and_the_rest_survives(self) -> None:
        from steamzero.adapters.launcher_catalog import CatalogGame
        from steamzero.launcher.app import _sections_from_catalog

        catalog = [
            CatalogGame(id="5c5fd6b29bee06c2f1fb5ff5", title="Válido", platform="snes"),
            CatalogGame(id="id:invalido", title="Corrompido", platform="snes"),
            CatalogGame(id="ae18c7e53583298461a0edea", title="Válido também", platform="snes"),
        ]
        sections = _sections_from_catalog(catalog)
        items = tuple(item for section in sections for item in section.items)
        assert items == ("5c5fd6b29bee06c2f1fb5ff5", "ae18c7e53583298461a0edea")

    def test_an_invalid_platform_falls_back_instead_of_dropping_the_game(self) -> None:
        """Seção ruim tem fallback; só o item ruim é descartado."""
        from steamzero.adapters.launcher_catalog import CatalogGame
        from steamzero.launcher.app import _sections_from_catalog

        catalog = [
            CatalogGame(id="5c5fd6b29bee06c2f1fb5ff5", title="Jogo", platform="plataforma:ruim"),
        ]
        sections = _sections_from_catalog(catalog)
        assert [section.id for section in sections] == ["outros"]
        assert sections[0].items == ("5c5fd6b29bee06c2f1fb5ff5",)
