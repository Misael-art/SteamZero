# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Árvore de cena: limites, ids únicos e caminho de nó.

Uma cena é uma árvore de ``ElementContract``. Sem limites, um tema importado
poderia declarar dez mil filhos ou profundidade mil e travar o renderizador;
sem ids únicos, um binding que mira um nó (ex.: foco de menu) não teria alvo
definido. Este módulo fecha os limites da árvore no mesmo espírito dos demais
gates do P0-03: nada é aceito em silêncio, e tudo que é aceito tem tamanho
conhecido e id único.

A primeira violação encontrada (em pré-ordem) é a que falha. Reportar todas de
uma vez faria o diagnóstico virar lista, não causa.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from steamzero.domain.scene_contract import ElementContract

#: Profundidade máxima da árvore. A raiz tem profundidade 1; um nó no nível 40
#: é a cadeia mais funda que um tema pode declarar.
TREE_MAX_DEPTH = 40

#: Filhos por nó. Espelha o ``maxItems`` de ``children`` do IR de cena.
TREE_MAX_CHILDREN = 128

#: Nós no total, raiz inclusa. É o que limita o custo de construir e validar a
#: árvore antes de o tema chegar ao renderizador.
TREE_MAX_NODES = 4096


def walk_tree(root: ElementContract) -> Iterator[tuple[int, ElementContract]]:
    """Percorre em pré-ordem: (profundidade, nó). A raiz tem profundidade 1.

    Iterativo de propósito: a validação não pode depender da recursão do
    interpretador, porque é justamente sobre árvores profundas que ela roda.
    """
    stack: list[tuple[int, ElementContract]] = [(1, root)]
    while stack:
        depth, node = stack.pop()
        yield depth, node
        for child in reversed(node.children):
            stack.append((depth + 1, child))


@dataclass(frozen=True)
class TreeStats:
    """Forma da árvore, para o relatório de auditoria e para testes."""

    nodes: int = 0
    max_depth: int = 0
    max_children: int = 0


def tree_stats(root: ElementContract) -> TreeStats:
    """Nós, profundidade máxima e maior fila de filhos de uma árvore."""
    nodes = 0
    max_depth = 0
    max_children = 0
    for depth, node in walk_tree(root):
        nodes += 1
        max_depth = max(max_depth, depth)
        max_children = max(max_children, len(node.children))
    return TreeStats(nodes=nodes, max_depth=max_depth, max_children=max_children)


def validate_tree(root: ElementContract) -> None:
    """Recusa árvore fora dos limites ou com id duplicado.

    - profundidade até ``TREE_MAX_DEPTH``;
    - até ``TREE_MAX_CHILDREN`` filhos por nó;
    - até ``TREE_MAX_NODES`` nós no total, raiz inclusa;
    - ids únicos em toda a árvore.
    """
    seen: set[str] = set()
    for total, (depth, node) in enumerate(walk_tree(root), start=1):
        if depth > TREE_MAX_DEPTH:
            raise ValueError(f"árvore excede profundidade {TREE_MAX_DEPTH}")
        if node.id in seen:
            raise ValueError(f"id duplicado na árvore: {node.id!r}")
        seen.add(node.id)
        if len(node.children) > TREE_MAX_CHILDREN:
            raise ValueError(f"{node.id!r} excede {TREE_MAX_CHILDREN} filhos")
        if total > TREE_MAX_NODES:
            raise ValueError(f"árvore excede {TREE_MAX_NODES} nós no total")
