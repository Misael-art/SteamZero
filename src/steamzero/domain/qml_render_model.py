# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""``ResolvedTextNode`` → ``QmlTextRenderModel``: tradução, não decisão.

O adapter converte enums canônicos para os valores que o QML aceita, normaliza
cor, opacidade, dimensão e alinhamento, e transforma o handle seguro de fonte em
referência interna autorizada. Só isso.

O que ele deliberadamente NÃO faz — e a razão de cada recusa:

- **Não resolve** binding, token, tradução, condição ou fallback. Se resolvesse,
  existiriam duas implementações das mesmas regras, uma por backend, e um dia
  elas divergiriam. O diagnóstico então apontaria para a regra errada.
- **Não acessa registries.** Ele recebe um DTO e devolve outro; não tem como
  consultar estado, e portanto não tem como depender de ordem de execução.
- **Não altera o nó.** O ``ResolvedTextNode`` que entra sai intacto — o adapter
  não é lugar de corrigir defeito produzido antes dele.
- **Não escolhe default em silêncio para enum desconhecido.** Um enum que o
  adapter não conhece significa que o DTO e o adapter estão em versões
  diferentes; escolher ``start`` produziria uma tela plausível e errada, que é
  pior que uma tela com defeito visível. Vira diagnóstico e valor recusado.

Determinismo é requisito: a mesma entrada produz exatamente a mesma saída, sem
consulta a relógio, ambiente ou estado global. É o que permite comparar goldens.

Independente da escolha futura entre PySide6 e Qt nativo: aqui não se importa
nada do Qt. Os números e strings emitidos são os que a linguagem QML aceita, mas
quem os entrega ao runtime é o shell, não este módulo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from steamzero.domain.resolved_node import (
    ASSET_HANDLE,
    FONT_WEIGHT_SCALE,
    FontAssetHandle,
    FontOrigin,
    FontStyle,
    ResolvedTextNode,
    TextAlignment,
    TextVerticalAlignment,
)

#: Diagnósticos que o adapter pode emitir. Numeração própria: são defeitos de
#: TRADUÇÃO, e confundi-los com defeitos de resolução mandaria quem investiga
#: para o módulo errado.
DIAG_UNKNOWN_ENUM = "QML-ADAPTER-UNKNOWN-ENUM-001"
DIAG_INVALID_HANDLE = "QML-ADAPTER-INVALID-ASSET-HANDLE-002"
DIAG_INVALID_COLOR = "QML-ADAPTER-INVALID-COLOR-003"
DIAG_OUT_OF_RANGE = "QML-ADAPTER-VALUE-OUT-OF-RANGE-004"
DIAG_FONT_UNAVAILABLE = "QML-ADAPTER-FONT-UNAVAILABLE-005"

#: Nomes do QML para alinhamento horizontal. `justify` sobrevive porque o Qt o
#: implementa; se um backend futuro não implementar, é ele que degrada — não o
#: adapter, que não sabe o que o backend suporta.
_H_ALIGN = {
    TextAlignment.START: "AlignLeft",
    TextAlignment.CENTER: "AlignHCenter",
    TextAlignment.END: "AlignRight",
    TextAlignment.JUSTIFY: "AlignJustify",
}

_V_ALIGN = {
    TextVerticalAlignment.TOP: "AlignTop",
    TextVerticalAlignment.MIDDLE: "AlignVCenter",
    TextVerticalAlignment.BOTTOM: "AlignBottom",
}

#: `font.italic` é booleano no QML e não distingue itálico de oblíquo. A
#: aproximação é registrada, não escondida: o tema pediu `oblique` e recebeu o
#: itálico sintético do backend.
_ITALIC = {FontStyle.NORMAL: False, FontStyle.ITALIC: True, FontStyle.OBLIQUE: True}

#: Cor no formato que o QML aceita. `rgba()` foi recusado no passado por
#: "Invalid property assignment"; hexadecimal com alfa é o que funciona.
_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")

#: Namespace autorizado para fonte, dentro da gramática do handle.
_FONT_NAMESPACE = "font"

#: Peso usado quando o nome não tem correspondente. Sempre com diagnóstico junto.
FONT_WEIGHT_SCALE_DEFAULT = 400


@dataclass(frozen=True)
class AdapterDiagnostic:
    """Defeito de tradução, com o suficiente para agir sobre ele."""

    code: str
    target: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "target": self.target, "detail": self.detail}


@dataclass(frozen=True)
class QmlTextRenderModel:
    """Exatamente o que ``SceneText.qml`` atribui às suas propriedades.

    Cada campo corresponde a uma propriedade do QML, e nada aqui exige
    interpretação do outro lado: o QML atribui e pronto.

    ``width``/``height`` em ``None`` significam "dimensione pelo conteúdo" — e é
    diferente de ``0.0``, que significa caixa explicitamente sem tamanho. O QML
    distingue os dois deixando a propriedade sem atribuir no primeiro caso, o que
    devolve o ``implicitWidth`` do ``Text``.
    """

    id: str
    text: str
    x: float
    y: float
    width: float | None
    height: float | None
    visible: bool
    opacity: float
    color: str
    font_family: str
    font_pixel_size: float
    font_weight: int
    font_italic: bool
    horizontal_alignment: str
    vertical_alignment: str
    #: Referência interna autorizada. Vazia quando a fonte não pôde ser usada —
    #: nesse caso `font_family` já carrega a família efetivamente aplicada.
    font_source: str = ""
    diagnostics: tuple[AdapterDiagnostic, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return not self.diagnostics

    def to_dict(self) -> dict[str, Any]:
        """Forma determinística, para golden e para a ponte com o QML."""
        payload: dict[str, Any] = {
            "id": self.id,
            "text": self.text,
            "x": self.x,
            "y": self.y,
            "visible": self.visible,
            "opacity": self.opacity,
            "color": self.color,
            "fontFamily": self.font_family,
            "fontPixelSize": self.font_pixel_size,
            "fontWeight": self.font_weight,
            "fontItalic": self.font_italic,
            "horizontalAlignment": self.horizontal_alignment,
            "verticalAlignment": self.vertical_alignment,
        }
        if self.width is not None:
            payload["width"] = self.width
        if self.height is not None:
            payload["height"] = self.height
        if self.font_source:
            payload["fontSource"] = self.font_source
        if self.diagnostics:
            payload["diagnostics"] = [item.to_dict() for item in self.diagnostics]
        return payload


class _Collector:
    """Acumula diagnósticos sem interromper a tradução.

    Parar no primeiro defeito esconderia os demais, e quem investiga acabaria
    corrigindo um por vez. Traduz-se tudo que dá, e reporta-se tudo que não deu.
    """

    def __init__(self, target: str) -> None:
        self._target = target
        self.entries: list[AdapterDiagnostic] = []

    def add(self, code: str, detail: str, *, field_name: str) -> None:
        self.entries.append(
            AdapterDiagnostic(code=code, target=f"{self._target}.{field_name}", detail=detail)
        )


def _map_enum(
    member: Any,
    table: dict[Any, Any],
    *,
    field_name: str,
    default: Any,
    diagnostics: _Collector,
) -> Any:
    """Traduz enum pela tabela, ou recusa.

    Escolher `default` em silêncio produziria uma tela plausível e errada. O
    default é usado só para manter a tradução seguindo — e vem acompanhado do
    diagnóstico que impede a saída de ser considerada válida.
    """
    try:
        return table[member]
    except KeyError:
        diagnostics.add(
            DIAG_UNKNOWN_ENUM,
            f"valor {member!r} não tem correspondente no QML; "
            f"conhecidos: {sorted(str(key) for key in table)}",
            field_name=field_name,
        )
        return default


def _font_source(handle: FontAssetHandle | None, diagnostics: _Collector) -> str:
    """Handle seguro para referência interna autorizada.

    A gramática é revalidada aqui, e não assumida do DTO: o adapter pode receber
    um nó desserializado de disco, e um handle que não passe pela gramática não
    vira referência — vira diagnóstico.
    """
    if handle is None or handle.handle is None:
        return ""
    if not ASSET_HANDLE.match(handle.handle):
        diagnostics.add(
            DIAG_INVALID_HANDLE,
            f"handle {handle.handle!r} fora da gramática asset://<namespace>/<id>",
            field_name="fontSource",
        )
        return ""
    namespace = handle.handle.removeprefix("asset://").split("/", 1)[0]
    if namespace != _FONT_NAMESPACE:
        diagnostics.add(
            DIAG_INVALID_HANDLE,
            f"handle de fonte no namespace {namespace!r}, esperado {_FONT_NAMESPACE!r}",
            field_name="fontSource",
        )
        return ""
    if handle.origin is FontOrigin.UNAVAILABLE:
        # Não é erro de tradução: o shell já registrou que a fonte não existe.
        # O adapter apenas não inventa uma referência para ela.
        diagnostics.add(
            DIAG_FONT_UNAVAILABLE,
            handle.fallback_reason or f"fonte {handle.key!r} indisponível",
            field_name="fontSource",
        )
        return ""
    return handle.handle


def _color(raw: str, diagnostics: _Collector) -> str:
    """Cor normalizada para hexadecimal que o QML aceita.

    Recusar é melhor que substituir por preto: preto é uma cor plausível, e a
    tela pareceria correta enquanto estivesse errada. Preto TRANSPARENTE, não —
    o elemento some, e quem olha percebe.
    """
    text = raw.strip()
    if _COLOR.match(text):
        return text.lower()
    diagnostics.add(
        DIAG_INVALID_COLOR,
        f"cor {raw!r} não é #RRGGBB nem #AARRGGBB",
        field_name="color",
    )
    return "#00000000"


def _clamp_opacity(raw: float, diagnostics: _Collector) -> float:
    if 0.0 <= raw <= 1.0:
        return float(raw)
    diagnostics.add(
        DIAG_OUT_OF_RANGE,
        f"opacidade {raw} fora de [0, 1]",
        field_name="opacity",
    )
    return min(1.0, max(0.0, float(raw)))


def _dimension(raw: float | None, *, field_name: str, diagnostics: _Collector) -> float | None:
    """``None`` atravessa intacto: é dimensão implícita, não ausência de valor."""
    if raw is None:
        return None
    if raw < 0.0:
        diagnostics.add(
            DIAG_OUT_OF_RANGE,
            f"dimensão negativa: {raw}",
            field_name=field_name,
        )
        return 0.0
    return float(raw)


def to_render_model(node: ResolvedTextNode) -> QmlTextRenderModel:
    """Traduz um nó resolvido para o modelo que o QML consome.

    Função pura: mesma entrada, mesma saída, sem estado e sem efeito. O nó de
    entrada não é modificado.
    """
    diagnostics = _Collector(node.id)

    font_source = _font_source(node.font_asset, diagnostics)
    # A família RENDERIZADA é a que o shell resolveu, não a que o tema pediu.
    # Usar a solicitada faria o QML tentar uma fonte que não está no pacote e
    # cair no fallback do sistema — decisão que pertence ao shell, não ao Qt.
    family = node.font_family or ""

    return QmlTextRenderModel(
        id=node.id,
        text=node.text,
        x=float(node.geometry.x),
        y=float(node.geometry.y),
        width=_dimension(node.geometry.width, field_name="width", diagnostics=diagnostics),
        height=_dimension(node.geometry.height, field_name="height", diagnostics=diagnostics),
        visible=bool(node.visible),
        opacity=_clamp_opacity(node.opacity, diagnostics),
        color=_color(node.color, diagnostics),
        font_family=family,
        font_pixel_size=float(node.font_size),
        font_weight=_map_enum(
            node.font_weight,
            FONT_WEIGHT_SCALE,
            field_name="fontWeight",
            default=FONT_WEIGHT_SCALE_DEFAULT,
            diagnostics=diagnostics,
        ),
        font_italic=_map_enum(
            node.font_style,
            _ITALIC,
            field_name="fontItalic",
            default=False,
            diagnostics=diagnostics,
        ),
        horizontal_alignment=_map_enum(
            node.horizontal_alignment,
            _H_ALIGN,
            field_name="horizontalAlignment",
            default="AlignLeft",
            diagnostics=diagnostics,
        ),
        vertical_alignment=_map_enum(
            node.vertical_alignment,
            _V_ALIGN,
            field_name="verticalAlignment",
            default="AlignTop",
            diagnostics=diagnostics,
        ),
        font_source=font_source,
        diagnostics=tuple(diagnostics.entries),
    )
