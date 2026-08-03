# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Árvore de cena: limites, ids únicos e forma da árvore.

A vertical slice compilava PLANO. Com a árvore de cena, um nó pode ter filhos —
e o que era um campo aberto vira um conjunto fechado: profundidade, filhos por
nó, total de nós e ids únicos. Cada limite existe para que um tema importado
não trave o renderizador nem deixe um binding de foco sem alvo definido.
"""

from __future__ import annotations

import pytest

from steamzero.domain.scene_contract import ElementContract
from steamzero.domain.scene_tree import (
    TREE_MAX_CHILDREN,
    TREE_MAX_DEPTH,
    TREE_MAX_NODES,
    tree_stats,
    validate_tree,
    walk_tree,
)


def _text(node_id: str) -> ElementContract:
    return ElementContract(id=node_id, type="text")


class TestTreeShape:
    def test_a_leaf_has_no_children(self) -> None:
        assert ElementContract(id="x", type="text").children == ()

    def test_a_tree_walks_in_pre_order_with_depths(self) -> None:
        root = ElementContract(
            id="root",
            type="container",
            children=(
                ElementContract(
                    id="a",
                    type="container",
                    children=(_text("a1"), _text("a2")),
                ),
                _text("b"),
            ),
        )
        assert [(depth, node.id) for depth, node in walk_tree(root)] == [
            (1, "root"),
            (2, "a"),
            (3, "a1"),
            (3, "a2"),
            (2, "b"),
        ]

    def test_stats_report_the_shape(self) -> None:
        root = ElementContract(
            id="root",
            type="container",
            children=(
                _text("a"),
                ElementContract(id="b", type="container", children=(_text("c"), _text("d"))),
            ),
        )
        stats = tree_stats(root)
        assert stats.nodes == 5
        assert stats.max_depth == 3
        assert stats.max_children == 2

    def test_an_empty_tree_is_a_single_node(self) -> None:
        stats = tree_stats(ElementContract(id="solo", type="text"))
        assert stats.nodes == 1
        assert stats.max_depth == 1
        assert stats.max_children == 0


class TestTreeLimits:
    def _chain(self, depth: int) -> ElementContract:
        root = _text("n0")
        node = root
        for index in range(1, depth):
            child = _text(f"n{index}")
            object.__setattr__(node, "children", (child,))
            node = child
        return root

    def test_the_max_depth_limit_is_enforced(self) -> None:
        validate_tree(self._chain(TREE_MAX_DEPTH))
        with pytest.raises(ValueError, match="profundidade"):
            validate_tree(self._chain(TREE_MAX_DEPTH + 1))

    def test_the_children_per_node_limit_is_enforced(self) -> None:
        wide = ElementContract(
            id="root",
            type="container",
            children=tuple(_text(f"c{index}") for index in range(TREE_MAX_CHILDREN)),
        )
        validate_tree(wide)
        overflow = ElementContract(
            id="root",
            type="container",
            children=tuple(_text(f"c{index}") for index in range(TREE_MAX_CHILDREN + 1)),
        )
        with pytest.raises(ValueError, match="filhos"):
            validate_tree(overflow)

    def test_the_total_node_limit_is_enforced(self) -> None:
        """128 nós com 33 filhos cada estouram o total sem estourar o por nó."""
        dense = ElementContract(
            id="root",
            type="container",
            children=tuple(
                ElementContract(
                    id=f"m{index}",
                    type="container",
                    children=tuple(_text(f"m{index}l{leaf}") for leaf in range(33)),
                )
                for index in range(TREE_MAX_CHILDREN)
            ),
        )
        assert tree_stats(dense).nodes > TREE_MAX_NODES
        with pytest.raises(ValueError, match="nós no total"):
            validate_tree(dense)

    def test_duplicate_ids_across_levels_are_refused(self) -> None:
        root = ElementContract(
            id="root",
            type="container",
            children=(ElementContract(id="root", type="text"),),
        )
        with pytest.raises(ValueError, match="duplicado"):
            validate_tree(root)

    def test_sibling_duplicate_ids_are_refused(self) -> None:
        root = ElementContract(
            id="root",
            type="container",
            children=(_text("same"), _text("same")),
        )
        with pytest.raises(ValueError, match="duplicado"):
            validate_tree(root)

    def test_the_first_violation_wins(self) -> None:
        """Diagnóstico de causa única: a primeira violação em pré-ordem."""
        root = ElementContract(
            id="root",
            type="container",
            children=(ElementContract(id="dup", type="text"), _text("dup")),
        )
        with pytest.raises(ValueError, match=r"id duplicado"):
            validate_tree(root)
