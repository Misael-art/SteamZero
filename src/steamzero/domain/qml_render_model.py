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
- **Não escolhe default para o que não sabe traduzir.** Enum desconhecido não
  vira ``AlignLeft``, cor inválida não vira transparente. Um default produziria
  uma tela plausível e errada, e ninguém investiga o que parece certo. O
  resultado é ``failed``, e ``failed`` não carrega modelo NENHUM — não há
  payload parcial para um consumidor distraído entregar ao QML.

Determinismo é requisito: a mesma entrada produz exatamente a mesma saída, sem
consulta a relógio, ambiente ou estado global. É o que permite comparar goldens.

Independente da escolha futura entre PySide6 e Qt nativo: aqui não se importa
nada do Qt. Os números e strings emitidos são os que a linguagem QML aceita, mas
quem os entrega ao runtime é o shell, não este módulo.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Generic, TypeVar

from steamzero.domain.resolved_node import (
    ASSET_HANDLE,
    FONT_WEIGHT_SCALE,
    FontAssetHandle,
    FontOrigin,
    FontStyle,
    ImageFillMode,
    ResolvedImageNode,
    ResolvedTextNode,
    TextAlignment,
    TextVerticalAlignment,
)
from steamzero.domain.scene_typing import SourceReference
from steamzero.domain.scene_value import is_pending_value

#: Diagnósticos que o adapter pode emitir. Numeração própria: são defeitos de
#: TRADUÇÃO, e confundi-los com defeitos de resolução mandaria quem investiga
#: para o módulo errado.
DIAG_UNKNOWN_ENUM = "QML-ADAPTER-UNKNOWN-ENUM-001"
DIAG_INVALID_HANDLE = "QML-ADAPTER-INVALID-ASSET-HANDLE-002"
DIAG_INVALID_COLOR = "QML-ADAPTER-INVALID-COLOR-003"
DIAG_OUT_OF_RANGE = "QML-ADAPTER-VALUE-OUT-OF-RANGE-004"
DIAG_FONT_UNAVAILABLE = "QML-ADAPTER-FONT-UNAVAILABLE-005"
DIAG_FONT_FALLBACK = "QML-ADAPTER-FONT-FALLBACK-006"
DIAG_APPROXIMATED = "QML-ADAPTER-APPROXIMATED-007"
DIAG_PENDING_VALUE = "QML-ADAPTER-PENDING-VALUE-008"
DIAG_INVALID_MEDIA = "QML-ADAPTER-INVALID-MEDIA-009"

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

#: Caminho de mídia relativo ao PACOTE do tema. Mesma gramática fechada do
#: construtor de asset do IR (`scene_value.asset`): permitir qualquer string
#: aqui abriria a porta a um caminho do host atravessando o adapter — e o DTO
#: é a fronteira que o proíbe.
_MEDIA = re.compile(r"^assets/[a-zA-Z0-9_. /()'&-]+\.[a-zA-Z0-9]+$")

#: Nomes que o QML aceita em `Image[model.fillMode]`. `crop` é o comportamento
#: de capa: a imagem preenche a caixa e o excesso é cortado, sem deformar.
_FILL_MODE = {
    ImageFillMode.CROP: "PreserveAspectCrop",
    ImageFillMode.STRETCH: "Stretch",
    ImageFillMode.FIT: "PreserveAspectFit",
    ImageFillMode.ORIGINAL: "Original",
}

#: Namespace autorizado para fonte, dentro da gramática do handle.
_FONT_NAMESPACE = "font"


class FallbackKind(StrEnum):
    """Como o valor entregue difere do declarado.

    Sem isto, "degradado" diria só que algo mudou. Saber que foi ``clamp`` e não
    ``substitution`` é o que separa "o autor escreveu 1.5 e recebeu 1.0" de "a
    fonte pedida não existe no pacote" — dois problemas com correções
    diferentes.
    """

    CLAMP = "clamp"
    SUBSTITUTION = "substitution"
    APPROXIMATION = "approximation"


class Severity(StrEnum):
    """Quanto o defeito custa.

    ``FATAL`` derruba o modelo inteiro. ``DEGRADED`` deixa passar um valor que
    não é o pedido, mas é uma substituição explícita e registrada — como
    ``oblique`` virando itálico sintético, que o QML não sabe distinguir.
    """

    FATAL = "fatal"
    DEGRADED = "degraded"


class AdaptationStatus(StrEnum):
    """Resultado da tradução, do ponto de vista de quem vai renderizar."""

    SUCCESS = "success"
    DEGRADED = "degraded"
    FAILED = "failed"


@dataclass(frozen=True)
class AdapterDiagnostic:
    """Defeito de tradução, com o suficiente para agir sobre ele."""

    code: str
    target: str
    detail: str
    severity: Severity = Severity.FATAL
    #: O que o autor DECLAROU. Registrar só que houve degradação não basta:
    #: sem o valor original, quem lê o relatório não sabe o que corrigir no
    #: tema, e sem o resolvido não sabe o que a tela mostrou.
    original_value: Any = None
    resolved_value: Any = None
    fallback_kind: FallbackKind | None = None
    source_reference: SourceReference | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "target": self.target,
            "severity": self.severity.value,
            # Serializa como `reason`: `detail` era o mesmo texto com outro
            # nome, e dois nomes para um campo viram duas leituras divergentes.
            "reason": self.detail,
        }
        if self.fallback_kind is not None:
            payload["fallbackKind"] = self.fallback_kind.value
            # Só nos degradados os dois valores fazem sentido juntos: em falha
            # não há valor resolvido, porque não há modelo.
            payload["originalValue"] = self.original_value
            payload["resolvedValue"] = self.resolved_value
        if self.source_reference is not None:
            payload["sourceReference"] = self.source_reference.to_dict()
        return payload


#: O projeto tem alvo 3.11; `class AdaptationResult[T]` só existe a partir do 3.12.
_ModelT = TypeVar("_ModelT")


class AdaptationError(RuntimeError):
    """Levantado por ``require_model()`` quando não há modelo válido."""


@dataclass(frozen=True)
class AdaptationResult(Generic[_ModelT]):
    """Modelo mais o veredito sobre ele — e o veredito não é opcional.

    O adapter devolve isto, e não o modelo, porque `ok` ao lado de um payload
    pronto é fácil demais de não ler. Aqui o consumidor precisa desempacotar, e
    em ``failed`` não há o que desempacotar: o modelo é ``None``.

    ``degraded`` existe para separar "não é o que o tema pediu, mas é uma
    substituição declarada" de "não sei traduzir isto". Colapsar os dois faria
    ou fallback legítimo derrubar a tela, ou defeito real passar por fallback.
    """

    status: AdaptationStatus
    model: _ModelT | None
    diagnostics: tuple[AdapterDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        # Os estados são inconfundíveis por construção. Um `failed` com modelo,
        # ou um `success` com diagnóstico, seria um convite a interpretar o
        # status errado — e quem interpreta errado renderiza errado.
        if self.status is AdaptationStatus.FAILED:
            if self.model is not None:
                raise ValueError("failed não carrega modelo")
            if not self.diagnostics:
                raise ValueError("failed exige diagnóstico")
            return
        if self.model is None:
            raise ValueError(f"{self.status.value} exige modelo")
        if self.status is AdaptationStatus.SUCCESS and self.diagnostics:
            raise ValueError("success não carrega diagnóstico")
        if self.status is AdaptationStatus.DEGRADED and not self.diagnostics:
            raise ValueError("degraded exige diagnóstico")

    @property
    def failed(self) -> bool:
        return self.status is AdaptationStatus.FAILED

    def require_model(self) -> _ModelT:
        """Devolve o modelo, ou recusa.

        É o caminho curto para quem não tem política de apresentação própria. O
        shell do VS-04 pode decidir outra coisa para ``failed`` — mostrar o
        elemento anterior, esconder o nó, pintar um marcador de defeito —, mas
        precisa decidir explicitamente. Ignorar não é uma opção disponível.
        """
        if self.model is None:
            detail = "; ".join(
                f"{item.code} em {item.target}: {item.detail}" for item in self.diagnostics
            )
            raise AdaptationError(f"tradução falhou — {detail}")
        return self.model

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"status": self.status.value}
        if self.model is not None:
            payload["model"] = self.model.to_dict()  # type: ignore[attr-defined]
        if self.diagnostics:
            payload["diagnostics"] = [item.to_dict() for item in self.diagnostics]
        return payload


@dataclass(frozen=True)
class QmlTextRenderModel:
    """Exatamente o que ``SceneText.qml`` atribui às suas propriedades.

    Só existe quando a tradução deu certo o bastante para existir. Diagnóstico
    não mora aqui: mora no ``AdaptationResult``, porque um modelo carregando o
    próprio defeito é um modelo que alguém vai renderizar mesmo assim.

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
    #: Referência interna autorizada. Vazia quando o tema não declarou fonte —
    #: nunca quando declarou e a tradução falhou, porque aí não há modelo.
    font_source: str = ""

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
        return payload


@dataclass(frozen=True)
class QmlImageRenderModel:
    """Exatamente o que ``SceneImage.qml`` atribui às suas propriedades.

    ``width``/``height`` em ``None`` significam "dimensione pelo conteúdo" —
    para imagem, pelo tamanho natural do arquivo — e é diferente de ``0.0``.
    O QML distingue os dois deixando a propriedade sem atribuir.

    ``source`` é o caminho de asset do pacote. O shell mapeia para o arquivo
    real na fronteira do QML (o mesmo papel que a referência interna autorizada
    de fonte); o modelo nunca carrega caminho do host.
    """

    id: str
    source: str
    x: float
    y: float
    width: float | None
    height: float | None
    visible: bool
    opacity: float
    fill_mode: str

    def to_dict(self) -> dict[str, Any]:
        """Forma determinística, para golden e para a ponte com o QML."""
        payload: dict[str, Any] = {
            "id": self.id,
            "source": self.source,
            "x": self.x,
            "y": self.y,
            "visible": self.visible,
            "opacity": self.opacity,
            "fillMode": self.fill_mode,
        }
        if self.width is not None:
            payload["width"] = self.width
        if self.height is not None:
            payload["height"] = self.height
        return payload


class _Collector:
    """Acumula diagnósticos sem interromper a tradução.

    Parar no primeiro defeito esconderia os demais, e quem investiga acabaria
    corrigindo um por vez. Traduz-se tudo que dá, e reporta-se tudo que não deu —
    mas se algo foi FATAL, o modelo não chega a ser construído.
    """

    def __init__(self, target: str, reference: SourceReference | None = None) -> None:
        self._target = target
        self._reference = reference
        self.entries: list[AdapterDiagnostic] = []

    def fatal(self, code: str, detail: str, *, field_name: str, original: Any = None) -> None:
        self.entries.append(
            AdapterDiagnostic(
                code=code,
                target=f"{self._target}.{field_name}",
                detail=detail,
                severity=Severity.FATAL,
                original_value=original,
                source_reference=self._reference,
            )
        )

    def degraded(
        self,
        code: str,
        detail: str,
        *,
        field_name: str,
        kind: FallbackKind,
        original: Any,
        resolved: Any,
    ) -> None:
        """Degradação exige a história completa.

        `kind`, `original` e `resolved` são obrigatórios de propósito: um
        registro de degradação sem eles diz que algo mudou sem dizer o quê, e
        quem lê o relatório não consegue nem corrigir o tema nem confirmar o que
        a tela mostrou.
        """
        self.entries.append(
            AdapterDiagnostic(
                code=code,
                target=f"{self._target}.{field_name}",
                detail=detail,
                severity=Severity.DEGRADED,
                original_value=original,
                resolved_value=resolved,
                fallback_kind=kind,
                source_reference=self._reference,
            )
        )

    @property
    def has_fatal(self) -> bool:
        return any(item.severity is Severity.FATAL for item in self.entries)


#: Sentinela para valor que não pôde ser traduzido. Nunca chega a um modelo:
#: quando aparece, houve FATAL e o modelo não é construído.
_UNSET = object()


def _map_enum(
    member: Any, table: dict[Any, Any], *, field_name: str, diagnostics: _Collector
) -> Any:
    """Traduz enum pela tabela, ou recusa.

    Não há parâmetro `default` de propósito. Escolher um produziria uma tela
    plausível e errada, e o dia em que o DTO ganhasse um membro novo, a tela
    apareceria alinhada à esquerda sem ninguém ligar o sintoma à causa.
    """
    try:
        return table[member]
    except (KeyError, TypeError):
        diagnostics.fatal(
            DIAG_UNKNOWN_ENUM,
            f"valor {member!r} não tem correspondente no QML; "
            f"conhecidos: {sorted(str(key) for key in table)}",
            field_name=field_name,
            original=member,
        )
        return _UNSET


def _font_source(handle: FontAssetHandle | None, diagnostics: _Collector) -> Any:
    """Handle seguro para referência interna autorizada.

    A gramática é revalidada aqui, e não assumida do DTO: o adapter pode receber
    um nó desserializado de disco, e um handle que não passe pela gramática não
    vira referência — vira defeito.
    """
    if handle is None:
        # Tema sem fonte declarada usa a do sistema. Isso é legítimo.
        return ""
    if handle.origin is FontOrigin.UNAVAILABLE:
        # O shell tentou e não conseguiu. Renderizar com a fonte errada em
        # silêncio esconderia que o pacote do tema está incompleto.
        diagnostics.fatal(
            DIAG_FONT_UNAVAILABLE,
            handle.fallback_reason or f"fonte {handle.key!r} indisponível",
            field_name="fontSource",
        )
        return _UNSET
    if handle.handle is None:
        diagnostics.fatal(
            DIAG_INVALID_HANDLE,
            f"origem {handle.origin.value} sem handle",
            field_name="fontSource",
        )
        return _UNSET
    if not ASSET_HANDLE.match(handle.handle):
        diagnostics.fatal(
            DIAG_INVALID_HANDLE,
            f"handle {handle.handle!r} fora da gramática asset://<namespace>/<id>",
            field_name="fontSource",
            original=handle.handle,
        )
        return _UNSET
    namespace = handle.handle.removeprefix("asset://").split("/", 1)[0]
    if namespace != _FONT_NAMESPACE:
        diagnostics.fatal(
            DIAG_INVALID_HANDLE,
            f"handle de fonte no namespace {namespace!r}, esperado {_FONT_NAMESPACE!r}",
            field_name="fontSource",
        )
        return _UNSET
    if handle.fallback_applied:
        # Substituição explícita, decidida pelo shell e registrada por ele. O
        # tema não recebeu o que pediu, e quem olhar o resultado precisa saber.
        diagnostics.degraded(
            DIAG_FONT_FALLBACK,
            handle.fallback_reason
            or f"fonte {handle.requested_family or handle.key!r} substituída por "
            f"{handle.resolved_family!r}",
            field_name="fontFamily",
            kind=FallbackKind.SUBSTITUTION,
            original=handle.requested_family or handle.key,
            resolved=handle.resolved_family,
        )
    return handle.handle


def _color(raw: Any, diagnostics: _Collector) -> Any:
    """Cor normalizada para hexadecimal que o QML aceita.

    Cor inválida não vira transparente. Transparente é um valor legítimo que um
    tema pode ter pedido de propósito, e usá-lo como marca de erro tornaria os
    dois casos indistinguíveis no resultado.
    """
    if isinstance(raw, str):
        text = raw.strip()
        if _COLOR.match(text):
            return text.lower()
    diagnostics.fatal(
        DIAG_INVALID_COLOR,
        f"cor {raw!r} não é #RRGGBB nem #AARRGGBB",
        field_name="color",
        original=raw,
    )
    return _UNSET


def _media_source(raw: Any, diagnostics: _Collector) -> Any:
    """Origem de imagem: caminho de asset do pacote, nunca caminho do host.

    A gramática é revalidada aqui, e não assumida do DTO: o adapter pode
    receber um nó desserializado de disco. Um caminho que não seja asset do
    pacote é defeito de tradução, não consulta de arquivo.
    """
    if isinstance(raw, str) and _MEDIA.match(raw) and ".." not in raw:
        return raw
    diagnostics.fatal(
        DIAG_INVALID_MEDIA,
        f"origem de imagem {raw!r} não é asset do pacote (assets/...)",
        field_name="source",
        original=raw,
    )
    return _UNSET


def _opacity(raw: Any, diagnostics: _Collector) -> Any:
    if isinstance(raw, bool) or not isinstance(raw, int | float) or not math.isfinite(raw):
        diagnostics.fatal(
            DIAG_OUT_OF_RANGE, f"opacidade não é número finito: {raw!r}", field_name="opacity"
        )
        return _UNSET
    if 0.0 <= raw <= 1.0:
        return float(raw)
    # Fora da faixa a intenção é inequívoca — 1.5 é opaco, -0.5 é invisível —,
    # então limitar é substituição declarada, não adivinhação.
    clamped = min(1.0, max(0.0, float(raw)))
    diagnostics.degraded(
        DIAG_OUT_OF_RANGE,
        f"opacidade fora da faixa permitida [0, 1], limitada a {clamped}",
        field_name="opacity",
        kind=FallbackKind.CLAMP,
        original=raw,
        resolved=clamped,
    )
    return clamped


def _number(raw: Any, *, field_name: str, diagnostics: _Collector) -> Any:
    if isinstance(raw, bool) or not isinstance(raw, int | float) or not math.isfinite(raw):
        diagnostics.fatal(
            DIAG_OUT_OF_RANGE, f"{field_name} não é número finito: {raw!r}", field_name=field_name
        )
        return _UNSET
    return float(raw)


def _dimension(raw: Any, *, field_name: str, diagnostics: _Collector) -> Any:
    """``None`` atravessa intacto: é dimensão implícita, não ausência de valor."""
    if raw is None:
        return None
    number = _number(raw, field_name=field_name, diagnostics=diagnostics)
    if number is _UNSET:
        return _UNSET
    if number < 0.0:
        # Zerar produziria um elemento invisível que parece intencional. Largura
        # negativa é defeito de quem produziu o nó, e é lá que precisa aparecer.
        diagnostics.fatal(
            DIAG_OUT_OF_RANGE, f"dimensão negativa: {raw}", field_name=field_name, original=raw
        )
        return _UNSET
    return number


def _reject_pending(node: object, diagnostics: _Collector) -> None:
    """Última barreira: valor não resolvido não atravessa o adapter.

    O DTO é tipado, então isto não acontece por engano — acontece quando um
    construtor novo esquece de resolver um campo, e aí o QML receberia um
    dicionário onde espera um escalar e renderizaria vazio sem reclamar.
    Aceita qualquer DTO de nó (texto ou imagem): a varredura é a mesma.
    """
    for name, item in vars(node).items():
        if is_pending_value(item):
            diagnostics.fatal(
                DIAG_PENDING_VALUE,
                f"valor não resolvido chegou ao adapter: {item!r}",
                field_name=name,
            )


def to_render_model(node: ResolvedTextNode) -> AdaptationResult[QmlTextRenderModel]:
    """Traduz um nó resolvido para o modelo que o QML consome.

    Função pura: mesma entrada, mesma saída, sem estado e sem efeito. O nó de
    entrada não é modificado.
    """
    diagnostics = _Collector(node.id, node.source_reference)

    _reject_pending(node, diagnostics)

    fields: dict[str, Any] = {
        "id": node.id,
        "text": node.text,
        "x": _number(node.geometry.x, field_name="x", diagnostics=diagnostics),
        "y": _number(node.geometry.y, field_name="y", diagnostics=diagnostics),
        "width": _dimension(node.geometry.width, field_name="width", diagnostics=diagnostics),
        "height": _dimension(node.geometry.height, field_name="height", diagnostics=diagnostics),
        "visible": bool(node.visible),
        "opacity": _opacity(node.opacity, diagnostics),
        "color": _color(node.color, diagnostics),
        # A família RENDERIZADA é a que o shell resolveu, não a que o tema pediu.
        # Usar a solicitada faria o QML tentar uma fonte que não está no pacote e
        # cair no fallback do sistema — decisão que pertence ao shell, não ao Qt.
        "font_family": node.font_family or "",
        "font_pixel_size": _number(
            node.font_size, field_name="fontPixelSize", diagnostics=diagnostics
        ),
        "font_weight": _map_enum(
            node.font_weight, FONT_WEIGHT_SCALE, field_name="fontWeight", diagnostics=diagnostics
        ),
        "font_italic": _map_enum(
            node.font_style, _ITALIC, field_name="fontItalic", diagnostics=diagnostics
        ),
        "horizontal_alignment": _map_enum(
            node.horizontal_alignment,
            _H_ALIGN,
            field_name="horizontalAlignment",
            diagnostics=diagnostics,
        ),
        "vertical_alignment": _map_enum(
            node.vertical_alignment,
            _V_ALIGN,
            field_name="verticalAlignment",
            diagnostics=diagnostics,
        ),
        "font_source": _font_source(node.font_asset, diagnostics),
    }

    if node.font_style is FontStyle.OBLIQUE:
        # `font.italic` é booleano no QML e não distingue itálico de oblíquo.
        # Itálico sintético é mais próximo do pedido do que texto reto, mas não é
        # o pedido.
        diagnostics.degraded(
            DIAG_APPROXIMATED,
            "oblique renderizado como itálico: font.italic é booleano no QML",
            field_name="fontStyle",
            kind=FallbackKind.APPROXIMATION,
            original=FontStyle.OBLIQUE.value,
            resolved=FontStyle.ITALIC.value,
        )

    if diagnostics.has_fatal:
        # Nenhum modelo parcial sai daqui. Não há payload para um consumidor
        # distraído entregar ao QML.
        return AdaptationResult(
            status=AdaptationStatus.FAILED, model=None, diagnostics=tuple(diagnostics.entries)
        )

    model = QmlTextRenderModel(**fields)
    if diagnostics.entries:
        return AdaptationResult(
            status=AdaptationStatus.DEGRADED, model=model, diagnostics=tuple(diagnostics.entries)
        )
    return AdaptationResult(status=AdaptationStatus.SUCCESS, model=model)


def to_image_render_model(node: ResolvedImageNode) -> AdaptationResult[QmlImageRenderModel]:
    """Traduz um nó de imagem resolvido para o modelo que o QML consome.

    Função pura, na mesma disciplina de ``to_render_model``: o nó de entrada
    não é modificado e nada é escolhido aqui para o que não se sabe traduzir.
    """
    diagnostics = _Collector(node.id, node.source_reference)

    _reject_pending(node, diagnostics)

    fields: dict[str, Any] = {
        "id": node.id,
        "source": _media_source(node.source, diagnostics),
        "x": _number(node.geometry.x, field_name="x", diagnostics=diagnostics),
        "y": _number(node.geometry.y, field_name="y", diagnostics=diagnostics),
        "width": _dimension(node.geometry.width, field_name="width", diagnostics=diagnostics),
        "height": _dimension(node.geometry.height, field_name="height", diagnostics=diagnostics),
        "visible": bool(node.visible),
        "opacity": _opacity(node.opacity, diagnostics),
        "fill_mode": _map_enum(
            node.fill_mode, _FILL_MODE, field_name="fillMode", diagnostics=diagnostics
        ),
    }

    if diagnostics.has_fatal:
        return AdaptationResult(
            status=AdaptationStatus.FAILED, model=None, diagnostics=tuple(diagnostics.entries)
        )

    model = QmlImageRenderModel(**fields)
    if diagnostics.entries:
        return AdaptationResult(
            status=AdaptationStatus.DEGRADED, model=model, diagnostics=tuple(diagnostics.entries)
        )
    return AdaptationResult(status=AdaptationStatus.SUCCESS, model=model)
