# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""VS-04 — a fatia vertical: declaração do RetroFE até ``ElementContract``.

Escopo deliberadamente pequeno: TEXTO. Sem árvore de cena, sem rich text, sem
efeitos, sem foco. A prova aqui é que uma declaração real atravessa o pipeline
inteiro sem atalho — não que o renderizador esteja completo.

A regra que organiza o módulo: **cada declaração recebe exatamente um veredito**.
Nem zero, que é a propriedade sumindo sem ninguém notar (foi assim que 238
``fontColor`` se perderam), nem dois, que é o relatório somando mais que o total
e a cobertura passando de 100% sem significar nada.

Por isso a tradução de cada propriedade é uma função que DEVE registrar, e o
compilador confere no fim. Não há caminho em que uma declaração conhecida saia
sem julgamento, e uma desconhecida vira ``unsupported`` — que é um veredito,
não um silêncio.

Sobre condicionais: RetroFE expressa item selecionado com um segundo atributo
(``selectedFontColor``). Isso vira ``when(in_state("focused"), ...)`` no IR. É a
tradução honesta do que o tema quis dizer, e não uma condição inventada para o
teste.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, ClassVar

from steamzero.domain import scene_value as value
from steamzero.domain.retrofe_declarations import (
    DeclarationSet,
    OriginKind,
    SourceDeclaration,
)
from steamzero.domain.scene_contract import (
    Alignment,
    ColorValue,
    DimensionValue,
    ElementContract,
    LayoutSpec,
    TextLayoutSpec,
    TypographySpec,
)
from steamzero.domain.scene_registry import forbidden_namespace
from steamzero.domain.scene_value import TranslationLog, Verdict

#: Cor do RetroFE: seis dígitos hexadecimais, sem `#`. Oito com alfa aparece em
#: temas mais novos.
_COLOR = re.compile(r"^#?(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")

#: Percentual: "50%". Pixel lógico: "120". `auto` é literal.
_PERCENT = re.compile(r"^(-?\d+(?:\.\d+)?)%$")

_ALIGNMENT = {
    "left": Alignment.START,
    "center": Alignment.CENTER,
    "centre": Alignment.CENTER,
    "right": Alignment.END,
    "justify": Alignment.JUSTIFY,
}

#: Nome do binding do RetroFE para o caminho do read model. Só o que o registro
#: publica: um `type` fora desta tabela não vira caminho inventado.
_BINDING_TYPE = {
    "title": "game.title",
    "year": "game.year",
    "developer": "game.developer",
    "genre": "game.genre",
    "publisher": "game.publisher",
    "time": "system.time",
    # Mapeado de propósito para um caminho PROIBIDO. Sem uma entrada assim, a
    # checagem de política seria código morto: tipo desconhecido é recusado
    # antes dela, e a proteção nunca rodaria — o pior estado possível, porque
    # ela se LÊ como proteção.
    "hostSerial": "host.serialNumber",
}


@dataclass
class SliceResult:
    """O que a fatia produziu, com a contabilidade junto."""

    elements: list[ElementContract] = field(default_factory=list)
    log: TranslationLog = field(default_factory=TranslationLog)
    #: Veredito por declaração. A chave é o `sourceDeclarationId`.
    verdicts: dict[str, Verdict] = field(default_factory=dict)
    duplicates: list[str] = field(default_factory=list)

    def record(
        self,
        declaration: SourceDeclaration,
        verdict: Verdict,
        *,
        target: str | None = None,
        detail: str | None = None,
    ) -> None:
        """Julga uma declaração. Duas vezes é defeito, não sobrescrita.

        Sobrescrever esconderia que dois caminhos do compilador julgaram a mesma
        propriedade — e o relatório continuaria somando certo enquanto um dos
        dois vereditos, possivelmente o correto, desapareceria.
        """
        if declaration.declaration_id in self.verdicts:
            self.duplicates.append(declaration.declaration_id)
            return
        self.verdicts[declaration.declaration_id] = verdict
        self.log.record(
            declaration.declaration_id,
            verdict,
            target=target,
            detail=detail,
        )

    def accounting(self, declarations: DeclarationSet) -> dict[str, Any]:
        declared = set(declarations.ids())
        judged = {key for key in self.verdicts if key in declared}
        unaccounted = sorted(declared - judged)
        return {
            "sourcePropertyCount": len(declared),
            "translationVerdictCount": len(judged),
            "accountingCoverage": round(len(judged) / len(declared), 6) if declared else 1.0,
            "unaccounted": unaccounted,
            "duplicateVerdicts": sorted(set(self.duplicates)),
            "counts": self.log.counts(),
        }


def _color_value(raw: str) -> Any:
    """Cor do RetroFE para ``ColorValue``, preservando alfa quando existir."""
    return ColorValue.from_hex(raw if raw.startswith("#") else f"#{raw}")


def _dimension(raw: str) -> DimensionValue:
    """Dimensão do RetroFE. Levanta quando não é dimensão — quem chama julga.

    Booleano, NaN e infinito chegam aqui como texto e são recusados pelo próprio
    ``DimensionValue``: a validação mora no contrato, não replicada aqui, para
    que não existam duas regras que possam divergir.
    """
    text = raw.strip()
    if text.lower() == "auto":
        return DimensionValue.auto()
    percent = _PERCENT.match(text)
    if percent is not None:
        return DimensionValue.percent(float(percent.group(1)))
    try:
        number = float(text)
    except ValueError:
        # A mensagem crua do Python ("could not convert string to float") não
        # diz ao autor do tema o que ele deveria ter escrito. Nomear o contrato
        # é a diferença entre um relatório útil e um traceback vazado.
        raise ValueError(
            f"dimensão {raw!r} não é reconhecida; use pixel lógico (120), percentual (50%) ou auto"
        ) from None
    if not math.isfinite(number):
        raise ValueError(f"dimensão {raw!r} não é finita; use um número, percentual ou auto")
    return DimensionValue.logical_px(number)


class TextSliceCompiler:
    """Traduz declarações de texto do RetroFE para o contrato canônico."""

    def __init__(
        self,
        *,
        palette: dict[str, str] | None = None,
        packaged_fonts: frozenset[str] = frozenset(),
        translations: frozenset[str] = frozenset(),
    ) -> None:
        #: Paleta declarada pelo tema. Cor que a referencia vira TOKEN, não
        #: literal — é o que permite trocar o esquema sem reescrever o layout.
        self._palette = palette or {}
        self._packaged_fonts = packaged_fonts
        self._translations = translations

    def compile(self, declarations: DeclarationSet) -> SliceResult:
        result = SliceResult()
        grouped: dict[int, list[SourceDeclaration]] = {}
        for item in declarations.declarations:
            if item.origin_kind is not OriginKind.DECLARED:
                continue
            grouped.setdefault(item.element_index, []).append(item)

        for index in sorted(grouped):
            group = grouped[index]
            element = self._element(index, group, result)
            if element is not None:
                result.elements.append(element)
        return result

    def _element(
        self, index: int, group: list[SourceDeclaration], result: SliceResult
    ) -> ElementContract | None:
        tag = group[0].element
        reference = group[0].source_reference
        by_name = {item.property_name: item for item in group}

        if tag not in {"text", "reloadableText"}:
            # Fora da fatia. Continua recebendo veredito: um elemento ignorado
            # sem julgamento sumiria do relatório junto com tudo que declarou.
            for item in group:
                result.record(
                    item,
                    Verdict.UNSUPPORTED,
                    detail=f"elemento {tag!r} fora da fatia de texto do VS-04",
                )
            return None

        typography: dict[str, Any] = {}
        text_layout: dict[str, Any] = {}
        layout: dict[str, Any] = {}
        text_content: Any = None

        for name, item in by_name.items():
            if name in self._DEFERRED:
                continue
            handler = self._HANDLERS.get(name)
            if handler is None:
                result.record(
                    item,
                    Verdict.UNSUPPORTED,
                    detail=f"atributo {name!r} sem tradução na fatia de texto do VS-04",
                )
                continue
            handler(self, item, by_name, typography, text_layout, layout, result)

        if "value" in by_name:
            text_content = self._text_content(by_name["value"], result)
        if tag == "reloadableText":
            text_content = self._binding_text(by_name, result) or text_content
        elif "type" in by_name:
            # `type` num `<text>` comum não significa nada. Sem esta linha ele
            # ficaria sem veredito, porque está na lista de adiados e o ramo de
            # binding não roda — a propriedade sumiria do relatório.
            result.record(
                by_name["type"],
                Verdict.UNSUPPORTED,
                detail="'type' só tem significado em reloadableText",
            )

        return ElementContract(
            id=f"{tag}-{index}",
            type="text",
            source_reference=reference,
            text_content=text_content,
            typography=TypographySpec(**typography) if typography else None,
            text_layout=TextLayoutSpec(**text_layout) if text_layout else None,
            layout=LayoutSpec(**layout),
        )

    # ------------------------------------------------------------------
    # Tradutores por propriedade. Cada um DEVE registrar um veredito.
    # ------------------------------------------------------------------

    def _text_content(self, item: SourceDeclaration, result: SliceResult) -> Any:
        raw = item.raw_value
        if raw.startswith("@") and raw[1:] in self._translations:
            # Chave de tradução com o literal como fallback: se o catálogo não
            # tiver o idioma, o texto do autor aparece — em vez da chave crua.
            result.record(item, Verdict.EXACT, target="text_content", detail="localizado")
            return value.localized(raw[1:], fallback=raw[1:])
        if raw.startswith("@"):
            result.record(
                item,
                Verdict.FALLBACK,
                target="text_content",
                detail=f"chave {raw[1:]!r} ausente no catálogo; usando o literal",
            )
            return raw[1:]
        result.record(item, Verdict.EXACT, target="text_content")
        return raw

    def _binding_text(self, by_name: dict[str, SourceDeclaration], result: SliceResult) -> Any:
        item = by_name.get("type")
        if item is None:
            return None
        path = _BINDING_TYPE.get(item.raw_value)
        if path is None:
            result.record(
                item,
                Verdict.UNSUPPORTED,
                target="text_content",
                detail=f"reloadableText type={item.raw_value!r} sem caminho publicado",
            )
            return None
        # Política antes de qualquer outra coisa sobre o caminho: um namespace
        # recusado não pode sair como `unsupported`, porque `unsupported` vira
        # fila de trabalho e alguém acabaria implementando o que foi negado.
        namespace = forbidden_namespace(path)
        if namespace is not None:
            result.record(
                item,
                Verdict.IGNORED_BY_POLICY,
                target="text_content",
                detail=f"namespace {namespace!r} é recusa de política, não limitação",
            )
            return None
        result.record(item, Verdict.EXACT, target="text_content", detail=f"binding {path}")
        return value.bind(path)

    def _color(
        self,
        item: SourceDeclaration,
        by_name: dict[str, SourceDeclaration],
        typography: dict[str, Any],
        _text_layout: dict[str, Any],
        _layout: dict[str, Any],
        result: SliceResult,
    ) -> None:
        normal = self._single_color(item, result, target="typography.color")
        if normal is None:
            return
        selected = by_name.get("selectedFontColor")
        if selected is None:
            typography["color"] = normal
            return
        # RetroFE expressa item selecionado com um segundo atributo. Isso é uma
        # CONDIÇÃO no IR, não duas cores soltas — colapsar para uma perderia o
        # comportamento que o tema descreve.
        other = self._single_color(selected, result, target="typography.color[focused]")
        if other is None:
            typography["color"] = normal
            return
        typography["color"] = value.when(value.in_state("focused"), other, normal)

    def _single_color(self, item: SourceDeclaration, result: SliceResult, *, target: str) -> Any:
        raw = item.raw_value.strip()
        if raw in self._palette:
            result.record(item, Verdict.EXACT, target=target, detail="token de paleta")
            return value.token(f"color.{raw}")
        if not _COLOR.match(raw):
            result.record(
                item,
                Verdict.INVALID,
                target=target,
                detail=f"cor {raw!r} não é hexadecimal de 6 ou 8 dígitos",
            )
            return None
        result.record(item, Verdict.EXACT, target=target)
        return _color_value(raw).to_hex()

    def _selected_color(
        self,
        item: SourceDeclaration,
        by_name: dict[str, SourceDeclaration],
        typography: dict[str, Any],
        _text_layout: dict[str, Any],
        _layout: dict[str, Any],
        result: SliceResult,
    ) -> None:
        """Julgado junto de ``fontColor`` quando os dois existem.

        A entrada precisa existir mesmo assim: sem ela o atributo cairia no ramo
        de "sem tradução" e um tema que declarasse SÓ `selectedFontColor`
        ficaria com a propriedade sem veredito nenhum.
        """
        if "fontColor" in by_name:
            return
        colour = self._single_color(item, result, target="typography.color[focused]")
        if colour is not None:
            typography["color"] = value.when(value.in_state("focused"), colour, "#ffffff")

    def _font(
        self,
        item: SourceDeclaration,
        _by_name: dict[str, SourceDeclaration],
        typography: dict[str, Any],
        _text_layout: dict[str, Any],
        _layout: dict[str, Any],
        result: SliceResult,
    ) -> None:
        family = item.raw_value.strip()
        if family in self._packaged_fonts:
            result.record(item, Verdict.EXACT, target="typography.font_family")
            typography["font_family"] = family
            return
        result.record(
            item,
            Verdict.FALLBACK,
            target="typography.font_family",
            detail=f"fonte {family!r} não está no pacote do tema",
        )
        typography["font_family"] = family
        typography["font_fallback"] = tuple(sorted(self._packaged_fonts))[:1]

    def _font_size(
        self,
        item: SourceDeclaration,
        _by_name: dict[str, SourceDeclaration],
        typography: dict[str, Any],
        _text_layout: dict[str, Any],
        _layout: dict[str, Any],
        result: SliceResult,
    ) -> None:
        try:
            size = float(item.raw_value)
            if not math.isfinite(size) or size <= 0:
                raise ValueError(item.raw_value)
        except ValueError:
            result.record(
                item,
                Verdict.INVALID,
                target="typography.font_size",
                detail=f"tamanho {item.raw_value!r} não é número positivo finito",
            )
            return
        result.record(item, Verdict.EXACT, target="typography.font_size")
        typography["font_size"] = size

    def _alignment(
        self,
        item: SourceDeclaration,
        _by_name: dict[str, SourceDeclaration],
        _typography: dict[str, Any],
        text_layout: dict[str, Any],
        _layout: dict[str, Any],
        result: SliceResult,
    ) -> None:
        member = _ALIGNMENT.get(item.raw_value.strip().lower())
        if member is None:
            result.record(
                item,
                Verdict.INVALID,
                target="text_layout.horizontal_alignment",
                detail=(
                    f"alinhamento {item.raw_value!r} desconhecido; conhecidos: {sorted(_ALIGNMENT)}"
                ),
            )
            return
        result.record(item, Verdict.EXACT, target="text_layout.horizontal_alignment")
        text_layout["horizontal_alignment"] = member

    def _geometry(
        self,
        item: SourceDeclaration,
        _by_name: dict[str, SourceDeclaration],
        _typography: dict[str, Any],
        _text_layout: dict[str, Any],
        layout: dict[str, Any],
        result: SliceResult,
    ) -> None:
        name = item.property_name
        try:
            layout[name] = _dimension(item.raw_value)
        except ValueError as exc:
            # A validação mora no `DimensionValue`. Booleano, NaN, infinito e
            # unidade desconhecida são recusados lá, e a mensagem que chega aqui
            # é a do contrato — não uma segunda regra que possa divergir dele.
            result.record(item, Verdict.INVALID, target=f"layout.{name}", detail=str(exc))
            return
        result.record(item, Verdict.EXACT, target=f"layout.{name}")

    #: Propriedades julgadas no corpo de `_element`, e não por atributo isolado:
    #: o conteúdo do texto depende do elemento inteiro.
    _DEFERRED = frozenset({"value", "type"})

    _HANDLERS: ClassVar[dict[str, Any]] = {}


TextSliceCompiler._HANDLERS = {
    "fontColor": TextSliceCompiler._color,
    "selectedFontColor": TextSliceCompiler._selected_color,
    "font": TextSliceCompiler._font,
    "fontSize": TextSliceCompiler._font_size,
    "alignment": TextSliceCompiler._alignment,
    "x": TextSliceCompiler._geometry,
    "y": TextSliceCompiler._geometry,
    "width": TextSliceCompiler._geometry,
    "height": TextSliceCompiler._geometry,
}
