# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Modelo de foco da home do AURA Launcher.

Num launcher conduzido por controle não existe mouse para resgatar o usuário:
um nó de onde nenhuma direção sai prende a navegação, e num handheld isso
significa reiniciar a sessão. Por isso o grafo de foco é resolvido aqui, com o
contrato de que **todo nó tem saída** — inclusive quando a biblioteca está
vazia, que é justamente onde o beco costuma nascer.

O QML recebe o mapa pronto e apenas aplica: não decide vizinhança, não deduz
coluna e não inventa foco quando a lista chega vazia.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from steamzero.launcher.identifiers import is_identifier

DIAG_FOCUS_EMPTY = "LAUNCHER-FOCUS-EMPTY-001"
DIAG_SECTIONS_TRUNCATED = "LAUNCHER-FOCUS-TRUNCATED-001"

# O limite existe para manter o grafo de foco finito, não para dizer quantos
# sistemas o usuário pode ter. Ele valia 12 e o projeto empacota 61 manifests de
# plataforma — um acervo com 13 sistemas derrubava o Launcher antes da home.
# Dimensionar abaixo do próprio domínio transforma uma salvaguarda em defeito,
# então o teto acompanha os manifests empacotados com folga para as seções de
# coleção, que entram na mesma home.
MAX_SECTIONS = 128
MAX_ITEMS_PER_SECTION = 512

# Nó sintético do topo. A primeira linha precisa de um destino para cima, senão
# o usuário que sobe uma vez perde a referência de que há barra de navegação.
HEADER_ID = "header:home"
EMPTY_ID = "empty:action"


def _identifier(value: str, *, name: str) -> str:
    if not is_identifier(value):
        raise ValueError(f"{name} id inválido: {value!r}")
    return value


@dataclass(frozen=True)
class HomeSection:
    id: str
    title: str
    items: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.id, name="section")
        if not self.title:
            raise ValueError("section title vazio")
        if len(self.items) > MAX_ITEMS_PER_SECTION:
            raise ValueError(f"section itens excede {MAX_ITEMS_PER_SECTION}")
        for item in self.items:
            _identifier(item, name="item")


@dataclass(frozen=True)
class FocusNode:
    id: str
    section: str
    column: int
    up: str | None = None
    down: str | None = None
    left: str | None = None
    right: str | None = None
    action: str | None = None

    def to_dict(self) -> dict[str, str | int | None]:
        return {
            "id": self.id,
            "section": self.section,
            "column": self.column,
            "up": self.up,
            "down": self.down,
            "left": self.left,
            "right": self.right,
            "action": self.action,
        }


@dataclass(frozen=True)
class FocusDiagnostic:
    code: str
    reason: str
    fallback: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "reason": self.reason, "fallback": self.fallback}


@dataclass(frozen=True)
class FocusMap:
    nodes: dict[str, FocusNode]
    initial: str
    diagnostics: tuple[FocusDiagnostic, ...] = ()
    rows: tuple[str, ...] = field(default_factory=tuple)

    def to_qml_object(self) -> dict[str, object]:
        return {
            "initial": self.initial,
            "rows": list(self.rows),
            "nodes": {key: node.to_dict() for key, node in self.nodes.items()},
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }


def _node_id(section: str, item: str) -> str:
    return f"{section}:{item}"


def resolve_home_focus(sections: Sequence[HomeSection]) -> FocusMap:
    """Materializa a vizinhança de cada item focável da home.

    Seção sem itens não vira linha: uma linha vazia seria alcançável pelo foco
    e não teria para onde ir. Home inteiramente vazia cai num nó de ação, com
    diagnóstico — nunca em ausência de foco.
    """
    # Estourar o teto não pode derrubar a home. O número de seções vem do acervo
    # do usuário, e nenhum dado dele deve ser capaz de impedir o Launcher de
    # abrir: levantar aqui deixava a tela preta com o traceback no journal, que é
    # exatamente a falha que a seção 8 do AGENTS.md proíbe. O excedente é cortado
    # e a perda fica declarada no diagnóstico, em vez de silenciosa.
    overflow: tuple[FocusDiagnostic, ...] = ()
    if len(sections) > MAX_SECTIONS:
        descartadas = len(sections) - MAX_SECTIONS
        overflow = (
            FocusDiagnostic(
                code=DIAG_SECTIONS_TRUNCATED,
                reason=(
                    f"home tem {len(sections)} seções e o foco comporta "
                    f"{MAX_SECTIONS}; {descartadas} ficaram de fora"
                ),
                fallback=sections[MAX_SECTIONS - 1].id,
            ),
        )
        sections = tuple(sections[:MAX_SECTIONS])

    populated = [section for section in sections if section.items]
    if not populated:
        empty = FocusNode(
            id=EMPTY_ID,
            section="empty",
            column=0,
            up=HEADER_ID,
            action="library.add",
        )
        header = FocusNode(id=HEADER_ID, section="header", column=0, down=EMPTY_ID)
        return FocusMap(
            nodes={HEADER_ID: header, EMPTY_ID: empty},
            initial=EMPTY_ID,
            diagnostics=(
                *overflow,
                FocusDiagnostic(
                    code=DIAG_FOCUS_EMPTY,
                    reason="nenhuma seção da home tem itens",
                    fallback="library.add",
                ),
            ),
            rows=(HEADER_ID, EMPTY_ID),
        )

    nodes: dict[str, FocusNode] = {}
    rows: list[str] = [HEADER_ID]
    for index, section in enumerate(populated):
        above = populated[index - 1] if index else None
        below = populated[index + 1] if index + 1 < len(populated) else None
        count = len(section.items)
        for column, item in enumerate(section.items):
            # A linha dá a volta: sair pela direita na última coluna devolve à
            # primeira, em vez de parar contra uma parede invisível.
            left = _node_id(section.id, section.items[(column - 1) % count])
            right = _node_id(section.id, section.items[(column + 1) % count])
            nodes[_node_id(section.id, item)] = FocusNode(
                id=_node_id(section.id, item),
                section=section.id,
                column=column,
                # Coluna que não existe na seção vizinha cai na mais próxima,
                # em vez de virar destino nulo.
                up=(
                    _node_id(above.id, above.items[min(column, len(above.items) - 1)])
                    if above is not None
                    else HEADER_ID
                ),
                down=(
                    _node_id(below.id, below.items[min(column, len(below.items) - 1)])
                    if below is not None
                    else None
                ),
                left=left if count > 1 else None,
                right=right if count > 1 else None,
            )
        rows.append(_node_id(section.id, section.items[0]))

    first = populated[0]
    initial = _node_id(first.id, first.items[0])
    nodes[HEADER_ID] = FocusNode(id=HEADER_ID, section="header", column=0, down=initial)
    return FocusMap(nodes=nodes, initial=initial, rows=tuple(rows), diagnostics=overflow)
