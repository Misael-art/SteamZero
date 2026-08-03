# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""VS-05 — o tema vai e volta do disco sem perder o que significa.

O critério NÃO é igualdade de bytes. Dois documentos podem diferir em ordem de
chave, em `1` contra `1.0`, em maiúsculas de cor, e continuarem dizendo
exatamente a mesma coisa. Exigir igualdade textual como gate principal
transformaria qualquer mudança de formatação em falso positivo, e o time
aprenderia a ignorar o teste.

O gate é semântico: ``normalize(parse(serialize(normalize(parse(x)))))``
preserva elemento, propriedade, tipo, valor, dimensão, cor, tipografia,
alinhamento, binding, token, tradução, condicional, fallback, origem e status de
degradação.

A determinismo textual é gate SECUNDÁRIO, e existe por outra razão: duas
execuções sobre a mesma entrada normalizada precisam produzir o mesmo texto, ou
o versionamento enche de diffs que não significam nada.

**O que NÃO pode acontecer aqui:** um token virar a cor que ele resolvia no
momento da serialização. ``token("color.accent")`` voltando como ``"#ffd166"``
congelaria o tema no estado de uma execução — trocar o esquema de cores deixaria
de funcionar, e o defeito só apareceria para quem trocasse.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from steamzero.domain.scene_contract import (
    Alignment,
    DimensionValue,
    ElementContract,
    LayoutSpec,
    TextLayoutSpec,
    TypographySpec,
)
from steamzero.domain.scene_tree import validate_tree
from steamzero.domain.scene_typing import SourceReference
from steamzero.domain.scene_value import is_pending_value

#: Versão do documento serializado. Um documento sem versão, ou com versão que
#: este código não conhece, é recusado: adivinhar o formato produziria um tema
#: parcialmente lido que renderiza errado sem reclamar.
#:
#: v2 acrescenta ``children``: a cena deixou de ser plana. Documentos v1 (planos)
#: continuam sendo lidos — o campo é opcional na leitura; o que NÃO é aceito é a
#: direção contrária, um leitor v1 encontrando ``children`` e os descartando em
#: silêncio.
SCHEMA_VERSION = 2

#: Versões que este código sabe ler. v1 era o documento plano da vertical slice.
READABLE_SCHEMA_VERSIONS = frozenset({1, SCHEMA_VERSION})


class SerializationError(ValueError):
    """Documento que não pode ser lido com segurança."""


def _canonical(node: Any) -> Any:
    """Forma canônica de um valor, para comparação semântica.

    Três normalizações, cada uma por um motivo concreto:

    - chaves ordenadas, porque a ordem não carrega significado e um dicionário
      reordenado não é um tema diferente;
    - inteiro que é float vira float, porque ``1`` e ``1.0`` são a mesma
      dimensão e JSON não distingue de forma confiável;
    - cor em minúsculas, porque ``#F2F6FB`` e ``#f2f6fb`` são a mesma cor.

    O que NÃO é normalizado: valor pendente. Um token continua token.
    """
    if isinstance(node, dict):
        return {key: _canonical(node[key]) for key in sorted(node)}
    if isinstance(node, list | tuple):
        return [_canonical(item) for item in node]
    if isinstance(node, bool):
        return node
    if isinstance(node, int):
        return float(node)
    if isinstance(node, str) and node.startswith("#") and len(node) in {7, 9}:
        return node.lower()
    return node


def canonical_json(payload: Mapping[str, Any]) -> str:
    """Texto determinístico para a mesma entrada normalizada.

    ``sort_keys`` é o que garante que duas execuções não produzam diffs
    irrelevantes. ``ensure_ascii=False`` mantém acento legível no diff, que é
    metade do valor de versionar o documento.
    """
    return json.dumps(
        _canonical(dict(payload)),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def semantic_equal(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return bool(_canonical(dict(left)) == _canonical(dict(right)))


def semantic_diff(left: Mapping[str, Any], right: Mapping[str, Any]) -> list[str]:
    """Onde os dois documentos divergem, em caminhos legíveis.

    Existe para que a falha diga "typography.color mudou" em vez de despejar
    dois JSON de mil linhas lado a lado.
    """
    differences: list[str] = []

    def walk(a: Any, b: Any, where: str) -> None:
        if isinstance(a, dict) and isinstance(b, dict):
            for key in sorted(set(a) | set(b)):
                if key not in a:
                    differences.append(f"{where}.{key}: ausente antes, {b[key]!r} depois")
                elif key not in b:
                    differences.append(f"{where}.{key}: {a[key]!r} antes, ausente depois")
                else:
                    walk(a[key], b[key], f"{where}.{key}")
            return
        if isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b):
                differences.append(f"{where}: {len(a)} itens antes, {len(b)} depois")
                return
            for index, (first, second) in enumerate(zip(a, b, strict=True)):
                walk(first, second, f"{where}[{index}]")
            return
        if a != b:
            differences.append(f"{where}: {a!r} → {b!r}")

    walk(_canonical(dict(left)), _canonical(dict(right)), "$")
    return differences


def _dimension(payload: Any) -> Any:
    if isinstance(payload, dict) and "kind" in payload:
        return DimensionValue.from_dict(payload)
    return payload


def _reference(payload: Any) -> SourceReference | None:
    if not isinstance(payload, dict):
        return None
    return SourceReference(
        file=str(payload["file"]),
        line=payload.get("line"),
        column=payload.get("column"),
        element=payload.get("element"),
    )


#: Cor canônica no documento. A mesma gramática do adapter, e não uma segunda
#: regra: duas validações de cor divergiriam, e a divergência apareceria como
#: um tema que salva e não abre.
_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


def _colour(payload: Any, where: str) -> Any:
    """Valida cor literal na leitura.

    Sem isto, um documento com ``"color": "vermelho"`` era aceito e só falhava
    lá no adapter, longe da causa — ou pior, num caminho que não passasse pelo
    adapter, sem falhar nunca. Valor pendente atravessa: token e condicional
    resolvem depois, e validá-los aqui exigiria resolver na leitura.
    """
    if payload is None or is_pending_value(payload):
        return payload
    if isinstance(payload, str) and _COLOR.match(payload):
        return payload
    raise SerializationError(f"cor inválida em {where}: {payload!r}")


def _alignment(payload: Any) -> Any:
    if payload is None:
        return None
    try:
        return Alignment(payload)
    except ValueError:
        raise SerializationError(
            f"alinhamento fora do contrato: {payload!r}; "
            f"conhecidos: {[member.value for member in Alignment]}"
        ) from None


_LAYOUT_DIMENSIONS = ("x", "y", "width", "height", "minWidth", "minHeight", "maxWidth", "maxHeight")

_SNAKE = {
    "minWidth": "min_width",
    "minHeight": "min_height",
    "maxWidth": "max_width",
    "maxHeight": "max_height",
    "horizontalAlignment": "horizontal_alignment",
    "verticalAlignment": "vertical_alignment",
    "fontFamily": "font_family",
    "fontAsset": "font_asset",
    "fontFallback": "font_fallback",
    "fontSize": "font_size",
    "fontWeight": "font_weight",
    "fontStyle": "font_style",
    "lineHeight": "line_height",
    "letterSpacing": "letter_spacing",
    "strokeColor": "stroke_color",
    "strokeWidth": "stroke_width",
    "maxLines": "max_lines",
    "textTransform": "text_transform",
    "autoFit": "auto_fit",
}


def _spec_kwargs(payload: Mapping[str, Any], allowed: frozenset[str]) -> dict[str, Any]:
    """Converte o payload para argumentos do dataclass, recusando o que sobra.

    Campo desconhecido não é ignorado em silêncio: um documento de versão futura
    lido por este código produziria um tema com propriedades faltando, e o
    sintoma seria uma tela quase certa.
    """
    kwargs: dict[str, Any] = {}
    for key, item in payload.items():
        name = _SNAKE.get(key, key)
        if name not in allowed:
            raise SerializationError(f"campo desconhecido na desserialização: {key!r}")
        kwargs[name] = item
    return kwargs


def element_from_dict(payload: Mapping[str, Any]) -> ElementContract:
    """Reconstrói o contrato. Recusa o que não sabe ler.

    Cada recusa aqui evita um tema silenciosamente incompleto — que é pior que
    um erro, porque renderiza.
    """
    for required in ("id", "type"):
        if required not in payload:
            raise SerializationError(f"campo obrigatório ausente: {required!r}")

    layout_payload = dict(payload.get("layout", {}))
    for name in _LAYOUT_DIMENSIONS:
        if name in layout_payload:
            layout_payload[name] = _dimension(layout_payload[name])
    for name in ("horizontalAlignment", "verticalAlignment"):
        if name in layout_payload:
            layout_payload[name] = _alignment(layout_payload[name])
    layout = LayoutSpec(**_spec_kwargs(layout_payload, frozenset(LayoutSpec.__dataclass_fields__)))

    typography = None
    if "typography" in payload:
        raw = dict(payload["typography"])
        if "fontFallback" in raw:
            raw["fontFallback"] = tuple(raw["fontFallback"])
        for name in ("color", "strokeColor"):
            if name in raw:
                raw[name] = _colour(raw[name], f"typography.{name}")
        typography = TypographySpec(
            **_spec_kwargs(raw, frozenset(TypographySpec.__dataclass_fields__))
        )

    text_layout = None
    if "textLayout" in payload:
        raw = dict(payload["textLayout"])
        for name in ("horizontalAlignment", "verticalAlignment"):
            if name in raw:
                raw[name] = _alignment(raw[name])
        text_layout = TextLayoutSpec(
            **_spec_kwargs(raw, frozenset(TextLayoutSpec.__dataclass_fields__))
        )

    children: tuple[ElementContract, ...] = ()
    if "children" in payload:
        raw_children = payload["children"]
        if not isinstance(raw_children, list):
            raise SerializationError("'children' precisa ser lista")
        children = tuple(element_from_dict(item) for item in raw_children)

    return ElementContract(
        id=str(payload["id"]),
        type=str(payload["type"]),
        role=payload.get("role"),
        tags=tuple(payload.get("tags", ())),
        z_index=payload.get("zIndex"),
        source_reference=_reference(payload.get("sourceReference")),
        debug_label=payload.get("debugLabel"),
        extension_data=dict(payload.get("extensionData", {})),
        visible=payload.get("visible"),
        enabled=payload.get("enabled"),
        opacity=payload.get("opacity"),
        clip=payload.get("clip"),
        overflow=payload.get("overflow"),
        text_content=payload.get("textContent"),
        layout=layout,
        typography=typography,
        text_layout=text_layout,
        children=children,
    )


def document(elements: list[ElementContract], **extra: Any) -> dict[str, Any]:
    """Documento canônico do tema. É ISTO que se versiona.

    ``ResolvedTextNode`` e ``QmlTextRenderModel`` NÃO entram: eles são produtos
    derivados de uma execução específica, com o binding já resolvido e o token
    já virado cor. Guardá-los como documento congelaria o tema no estado daquela
    execução.
    """
    payload: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "elements": [element.to_dict() for element in elements],
    }
    payload.update(extra)
    return payload


def parse_document(payload: Mapping[str, Any]) -> list[ElementContract]:
    version = payload.get("schemaVersion")
    if version not in READABLE_SCHEMA_VERSIONS:
        raise SerializationError(
            f"schemaVersion {version!r} incompatível; este código lê {SCHEMA_VERSION}"
        )
    elements = payload.get("elements")
    if not isinstance(elements, list):
        raise SerializationError("campo obrigatório ausente: 'elements'")
    parsed = [element_from_dict(item) for item in elements]
    for element in parsed:
        try:
            validate_tree(element)
        except ValueError as exc:
            raise SerializationError(f"árvore de cena inválida: {exc}") from None
    return parsed


def assert_no_frozen_dynamics(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[str]:
    """Encontra valores dinâmicos que viraram literais no round-trip.

    É a verificação mais importante do VS-05. Um token que volta como a cor que
    ele resolvia congelaria o tema no estado da execução que serializou: trocar
    o esquema de cores deixaria de funcionar, e o defeito só apareceria para
    quem trocasse — muito depois, sem ligação com a causa.
    """
    frozen: list[str] = []

    def walk(a: Any, b: Any, where: str) -> None:
        if is_pending_value(a) and not is_pending_value(b):
            frozen.append(f"{where}: {a!r} congelou em {b!r}")
            return
        if isinstance(a, dict) and isinstance(b, dict):
            for key in a:
                if key in b:
                    walk(a[key], b[key], f"{where}.{key}")
            return
        if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
            for index, (first, second) in enumerate(zip(a, b, strict=True)):
                walk(first, second, f"{where}[{index}]")

    walk(dict(before), dict(after), "$")
    return frozen
