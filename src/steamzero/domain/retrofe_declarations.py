# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""VS-04 — cada propriedade declarada pelo RetroFE ganha identidade e origem.

O parser legado (`scene_retrofe.compile_layout`) produz uma cena renderizável,
mas não responde à pergunta que o accounting exige: *desta declaração, o que
aconteceu?* Ele agrega — `degraded` lista o que se perdeu, sem dizer quantas
propriedades a origem tinha. Foi assim que 238 `fontColor` sumiram sem ninguém
notar: o relatório contava ELEMENTOS compilados, e todos compilaram.

Aqui cada atributo do arquivo vira uma ``SourceDeclaration`` com:

- ``declaration_id`` estável, para cruzar com o veredito;
- ``source_reference`` com arquivo, linha e elemento;
- o valor CRU, exatamente como o autor escreveu.

O gate que isso viabiliza: **cada ``sourceDeclarationId`` recebe exatamente um
veredito**. Nenhum a menos — propriedade que sumiu sem julgamento —, nenhum a
mais — dois caminhos julgando a mesma coisa e o relatório somando mais que o
total.

**Default não é declaração.** Um valor que o compilador inventou porque a origem
não disse nada não pode entrar em ``sourcePropertyCount``: inflaria a cobertura
com trabalho que ninguém pediu, e 100% deixaria de significar "traduzimos tudo
que o autor escreveu". Por isso ``OriginKind`` separa o que veio do arquivo do
que veio de nós.

Linha vem do expat. ``ElementTree`` sozinho não guarda posição, e um diagnóstico
que diz "cor inválida" sem dizer ONDE obriga quem for corrigir a procurar no
arquivo inteiro.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from xml.parsers import expat

from steamzero.domain.scene_typing import SourceReference

#: Limite de declarações por arquivo. Um layout do corpus real tem centenas;
#: milhares indicam arquivo hostil ou gerado, e nenhum tema legítimo precisa.
MAX_DECLARATIONS = 8192


class OriginKind(StrEnum):
    """De onde a propriedade veio.

    Só ``DECLARED`` conta em ``sourcePropertyCount``. Os demais existem porque
    o resultado final precisa deles para ser explicável — sem ``DEFAULT``, um
    valor apareceria no nó resolvido sem nenhuma origem —, mas contá-los
    inflaria a cobertura com trabalho que ninguém pediu.
    """

    DECLARED = "declared"
    DEFAULT = "default"
    INHERITED = "inherited"
    DERIVED = "derived"


@dataclass(frozen=True)
class SourceDeclaration:
    """Uma propriedade escrita pelo autor do tema, com identidade e lugar."""

    declaration_id: str
    element: str
    element_index: int
    property_name: str
    raw_value: str
    source_reference: SourceReference
    origin_kind: OriginKind = OriginKind.DECLARED

    @property
    def counts_as_source(self) -> bool:
        return self.origin_kind is OriginKind.DECLARED

    def to_dict(self) -> dict[str, Any]:
        return {
            "sourceDeclarationId": self.declaration_id,
            "element": self.element,
            "elementIndex": self.element_index,
            "property": self.property_name,
            "rawValue": self.raw_value,
            "originKind": self.origin_kind.value,
            "sourceReference": self.source_reference.to_dict(),
        }


@dataclass
class DeclarationSet:
    """Tudo que a origem declarou, na ordem em que apareceu."""

    file: str
    declarations: list[SourceDeclaration] = field(default_factory=list)
    truncated: bool = False

    @property
    def source_property_count(self) -> int:
        """Somente o que o AUTOR escreveu.

        Default, herdado e derivado ficam de fora: contá-los faria 100% de
        cobertura significar "julgamos tudo que produzimos" em vez de
        "traduzimos tudo que o autor escreveu".
        """
        return sum(1 for item in self.declarations if item.counts_as_source)

    def by_id(self, declaration_id: str) -> SourceDeclaration | None:
        for item in self.declarations:
            if item.declaration_id == declaration_id:
                return item
        return None

    def ids(self) -> tuple[str, ...]:
        return tuple(item.declaration_id for item in self.declarations if item.counts_as_source)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "sourcePropertyCount": self.source_property_count,
            "declarations": [item.to_dict() for item in self.declarations],
            "truncated": self.truncated,
        }


_UNSAFE = re.compile(r"[^A-Za-z0-9_.:-]+")


def _identifier(file: str, line: int, element: str, index: int, name: str) -> str:
    """Identidade estável de uma declaração.

    Inclui a linha porque o mesmo elemento pode repetir o mesmo atributo em
    linhas diferentes, e inclui o índice porque dois elementos iguais podem
    estar na mesma linha num arquivo minificado. Sem os dois, ids colidiriam e
    um veredito sobrescreveria o outro — que o accounting acusaria como
    duplicata sem conseguir dizer qual das duas propriedades ficou sem
    julgamento.
    """
    stem = _UNSAFE.sub("_", file.rsplit("/", 1)[-1])
    return f"retrofe:{stem}:{line}:{element}[{index}].{name}"


class _Collector:
    """Alvo do expat. Só coleta — não interpreta, não valida, não traduz.

    A separação é o ponto: interpretar aqui misturaria "o autor escreveu isto"
    com "isto significa aquilo", e o accounting perderia a referência do que foi
    de fato declarado.
    """

    def __init__(self, file: str) -> None:
        self.file = file
        self.result = DeclarationSet(file=file)
        self._index = 0

    def start_element(self, name: str, attributes: dict[str, str], line: int, column: int) -> None:
        index = self._index
        self._index += 1
        for attribute, value in attributes.items():
            if len(self.result.declarations) >= MAX_DECLARATIONS:
                self.result.truncated = True
                return
            self.result.declarations.append(
                SourceDeclaration(
                    declaration_id=_identifier(self.file, line, name, index, attribute),
                    element=name,
                    element_index=index,
                    property_name=attribute,
                    raw_value=value,
                    source_reference=SourceReference(
                        file=self.file, line=line, column=column, element=name
                    ),
                )
            )


def collect_declarations(layout_xml: str, *, file: str) -> DeclarationSet:
    """Extrai toda propriedade declarada, com linha de origem.

    Usa expat diretamente porque ``ElementTree`` descarta a posição, e um
    diagnóstico que diz "cor inválida" sem dizer onde obriga quem for corrigir a
    procurar no arquivo inteiro.

    XML malformado NÃO é fatal aqui: o corpus real do RetroFE tem tags fechadas
    erradas e atributos duplicados, e um arquivo parcialmente legível ainda diz
    o que o autor declarou até o ponto do defeito. O que foi lido é devolvido, e
    ``truncated`` marca que houve interrupção.
    """
    collector = _Collector(file)
    parser = expat.ParserCreate()

    def _start(name: str, attributes: dict[str, str]) -> None:
        collector.start_element(
            name,
            attributes,
            parser.CurrentLineNumber,
            parser.CurrentColumnNumber,
        )

    parser.StartElementHandler = _start
    try:
        parser.Parse(layout_xml.encode("utf-8"), True)
    except expat.ExpatError:
        # O arquivo quebrou no meio. As declarações lidas até aqui continuam
        # válidas e continuam precisando de veredito — descartá-las faria o
        # accounting reportar cobertura total sobre um arquivo truncado.
        collector.result.truncated = True
    return collector.result


def derived(
    declaration_id: str,
    *,
    element: str,
    property_name: str,
    value: str,
    origin_kind: OriginKind,
    reference: SourceReference,
) -> SourceDeclaration:
    """Declaração que NÃO veio do arquivo. Fica fora de ``sourcePropertyCount``."""
    if origin_kind is OriginKind.DECLARED:
        raise ValueError("use collect_declarations para o que o autor escreveu")
    return SourceDeclaration(
        declaration_id=declaration_id,
        element=element,
        element_index=-1,
        property_name=property_name,
        raw_value=value,
        source_reference=reference,
        origin_kind=origin_kind,
    )
