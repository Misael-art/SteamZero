# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Auditoria executável da migração: o que do corpus virou contrato, e o que não.

O gate de escopo do P0-03 (`source_property_count < 388`) diz que a fatia
continua estreita, mas não diz ONDE está a estreiteza. Este módulo produz o
relatório que o gate só resume: para cada categoria de propriedade, quantas
declarações reais do arquivo têm tradutor na fatia e quantas não têm — e a
lista nominal do que ficou para trás.

A migração é tradução, não cópia de nomes: ``fontColor`` vira ``color`` no
contrato. Por isso o critério de "migrada" é a presença do nome RetroFE no
registro de tradutores da fatia (``retrofe_text_slice``), nunca um match 1:1
contra o contrato.

Regra de honestidade: categoria desconhecida é reportada como ``UNKNOWN`` e
conta como não migrada. Nenhum nome some do relatório — foi assim que 238
``fontColor`` sumiram sem ninguém notar.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from steamzero.domain.retrofe_declarations import DeclarationSet
from steamzero.domain.retrofe_text_slice import TextSliceCompiler
from steamzero.domain.scene_typing import Category

#: Tamanho do corpus RetroFE varrido na pesquisa (VS-04). O gate de escopo
#: compara contra ele; este módulo é o único lugar que precisa conhecê-lo.
CORPUS_PROPERTY_COUNT = 388

#: Nomes RetroFE observados nas fixtures reais do corpus, com sua categoria.
#: Tabela fechada: um nome novo numa fixture sem entrada aqui aparece como
#: ``UNKNOWN`` no relatório e o teste ``test_the_category_table_is_closed``
#: reprova — o custo de ignorar é um relatório que esconde a área.
PROPERTY_CATEGORIES: dict[str, Category] = {
    "alignment": Category.TYPOGRAPHY,
    "font": Category.TYPOGRAPHY,
    "fontColor": Category.COLOR,
    "fontSize": Category.TYPOGRAPHY,
    "height": Category.LAYOUT,
    "layer": Category.LAYOUT,
    "selectedFontColor": Category.COLOR,
    "src": Category.MEDIA,
    # Chave de conteúdo do reloadableText: não tem análogo no contrato. UNKNOWN
    # explícito na tabela — omissão seria silêncio, e o relatório não silencia.
    "type": Category.UNKNOWN,
    "value": Category.TYPOGRAPHY,
    "width": Category.LAYOUT,
    "x": Category.LAYOUT,
    "y": Category.LAYOUT,
}


def slice_migrated_properties() -> frozenset[str]:
    """Nomes RetroFE que a fatia traduz hoje.

    Derivado do registro de tradutores da fatia — uma segunda lista escrita à
    mão aqui divergiria dele, e a auditoria passaria a mentir sobre o que a
    fatia cobre.
    """
    return frozenset(TextSliceCompiler._HANDLERS) | frozenset(TextSliceCompiler._DEFERRED)


@dataclass(frozen=True)
class CategoryFidelity:
    """Fidelidade de uma área: quantas declarações, quantas migradas."""

    category: Category
    declared: int
    migrated: int

    @property
    def fidelity(self) -> float:
        return 1.0 if self.declared == 0 else round(self.migrated / self.declared, 4)


@dataclass(frozen=True)
class MigrationAudit:
    """Relatório da auditoria para um conjunto de declarações."""

    declared: int
    migrated: int
    corpus_total: int
    by_category: tuple[CategoryFidelity, ...]
    not_migrated: tuple[str, ...]

    @property
    def fidelity(self) -> float:
        return 1.0 if self.declared == 0 else round(self.migrated / self.declared, 4)

    @property
    def corpus_gate_ok(self) -> bool:
        """O gate de escopo: a fatia continua estreita diante do corpus completo."""
        return self.declared < self.corpus_total

    def to_dict(self) -> dict[str, Any]:
        return {
            "sourcePropertyCount": self.declared,
            "migratedPropertyCount": self.migrated,
            "corpusPropertyCount": self.corpus_total,
            "fidelity": self.fidelity,
            "corpusGateOk": self.corpus_gate_ok,
            "byCategory": [
                {
                    "category": item.category.value,
                    "declared": item.declared,
                    "migrated": item.migrated,
                    "fidelity": item.fidelity,
                }
                for item in self.by_category
            ],
            "notMigrated": list(self.not_migrated),
        }


def audit_migration(
    declarations: DeclarationSet,
    *,
    migrated: frozenset[str] | None = None,
    categories: dict[str, Category] | None = None,
    corpus_total: int = CORPUS_PROPERTY_COUNT,
) -> MigrationAudit:
    """Audita um conjunto de declarações contra o que a fatia traduz.

    Só conta o que o AUTOR escreveu (``counts_as_source``): default, herdado e
    derivado não são declaração e não entram no relatório — contá-los faria a
    fidelidade medir trabalho que ninguém pediu.
    """
    migrated_set = slice_migrated_properties() if migrated is None else migrated
    category_table = PROPERTY_CATEGORIES if categories is None else categories

    declared = 0
    translated = 0
    per_category: dict[Category, list[int]] = {}
    missing: set[str] = set()

    for item in declarations.declarations:
        if not item.counts_as_source:
            continue
        declared += 1
        category = category_table.get(item.property_name, Category.UNKNOWN)
        counts = per_category.setdefault(category, [0, 0])
        counts[0] += 1
        if item.property_name in migrated_set:
            translated += 1
            counts[1] += 1
        else:
            missing.add(item.property_name)

    by_category = tuple(
        CategoryFidelity(category=category, declared=counts[0], migrated=counts[1])
        for category, counts in per_category.items()
    )
    return MigrationAudit(
        declared=declared,
        migrated=translated,
        corpus_total=corpus_total,
        by_category=by_category,
        not_migrated=tuple(sorted(missing)),
    )
