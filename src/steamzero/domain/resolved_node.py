# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""``ResolvedTextNode`` — a fronteira entre o IR e qualquer renderizador.

O DTO carrega SOMENTE valores finais. Nenhum token, binding, condição ou
configuração pendente atravessa esta linha, e nenhum tipo do Qt entra nela.

A razão não é purismo. Se o QML pudesse consultar o ``TokenRegistry`` ou o read
model, ele acabaria implementando suas próprias regras de fallback — e um dia
elas divergiriam das do resolver. Aí o mesmo tema renderizaria diferente conforme
o backend, e o diagnóstico apontaria para a regra errada. Manter a resolução de
um lado só é o que garante que ``visual-software`` e um futuro ``visual-rhi``
desenhem a mesma coisa.

O caminho é unidirecional: ``ResolvedTextNode → QML``. O QML não resolve, não
corrige e não completa o contrato — se um valor chegou errado, o defeito está
antes dele.

Fonte é ``FontAssetHandle``, nunca caminho do host. Um tema referencia
``theme.neonGrid.font.heading``; o shell valida e emite o handle. O renderizador
recebe o handle, não ``/home/user/fonts/x.ttf``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from steamzero.domain.scene_typing import SourceReference

#: Gramática FECHADA do handle de asset. Allowlist, não blacklist: procurar por
#: "/home/" ou ".ttf" pega os casos que imaginamos, e deixa passar os que não.
#: Só esta forma é aceita, e ela não tem como expressar um caminho do host.
ASSET_HANDLE = re.compile(r"^asset://[a-z][a-z0-9]*/[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class TextAlignment(StrEnum):
    """Alinhamento canônico. O adapter converte para o enum do backend.

    Próprio de propósito: ``Qt.AlignHCenter`` no DTO acoplaria o contrato a um
    renderizador, e o valor serializado deixaria de ser legível fora do Qt.
    """

    START = "start"
    CENTER = "center"
    END = "end"
    JUSTIFY = "justify"


class TextVerticalAlignment(StrEnum):
    TOP = "top"
    MIDDLE = "middle"
    BOTTOM = "bottom"


class FontWeight(StrEnum):
    """Pesos nomeados. Números crus dependeriam da convenção do backend."""

    THIN = "thin"
    EXTRA_LIGHT = "extraLight"
    LIGHT = "light"
    NORMAL = "normal"
    MEDIUM = "medium"
    SEMI_BOLD = "semiBold"
    BOLD = "bold"
    EXTRA_BOLD = "extraBold"
    BLACK = "black"


#: Peso numérico correspondente, na escala CSS. O adapter mapeia daqui para a
#: escala do backend; guardar o nome mantém o DTO legível e estável.
FONT_WEIGHT_SCALE: dict[FontWeight, int] = {
    FontWeight.THIN: 100,
    FontWeight.EXTRA_LIGHT: 200,
    FontWeight.LIGHT: 300,
    FontWeight.NORMAL: 400,
    FontWeight.MEDIUM: 500,
    FontWeight.SEMI_BOLD: 600,
    FontWeight.BOLD: 700,
    FontWeight.EXTRA_BOLD: 800,
    FontWeight.BLACK: 900,
}


class FontStyle(StrEnum):
    NORMAL = "normal"
    ITALIC = "italic"
    OBLIQUE = "oblique"


class FontOrigin(StrEnum):
    """De onde veio a fonte efetivamente usada.

    Distinguir importa: ``FALLBACK_SYSTEM`` significa que o tema pediu algo que
    o pacote não tinha, e o teste precisa poder afirmar que a família RENDERIZADA
    não é a solicitada — em vez de aceitar a escolha automática do sistema como
    se fosse o desejado.
    """

    PACKAGED = "packaged"
    FALLBACK_DECLARED = "fallbackDeclared"
    FALLBACK_SYSTEM = "fallbackSystem"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class FontAssetHandle:
    """Referência segura a uma fonte, emitida pelo shell.

    ``key`` é a chave lógica que o tema declarou. ``handle`` é o identificador
    opaco que o shell emitiu depois de validar. Caminho do host NÃO aparece aqui
    — nem no DTO, nem no que chega ao renderizador.
    """

    key: str
    handle: str | None = None
    origin: FontOrigin = FontOrigin.UNAVAILABLE
    requested_family: str | None = None
    resolved_family: str | None = None
    fallback_reason: str | None = None
    file_hash: str | None = None

    def __post_init__(self) -> None:
        if self.handle is not None and not ASSET_HANDLE.match(self.handle):
            raise ValueError(
                f"handle de asset fora da gramática asset://<namespace>/<id>: {self.handle!r}"
            )

    @property
    def available(self) -> bool:
        return self.origin is not FontOrigin.UNAVAILABLE and self.handle is not None

    @property
    def fallback_applied(self) -> bool:
        return self.origin in {FontOrigin.FALLBACK_DECLARED, FontOrigin.FALLBACK_SYSTEM}

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"key": self.key, "origin": self.origin.value}
        for name, item in (
            ("handle", self.handle),
            ("requestedFamily", self.requested_family),
            ("resolvedFamily", self.resolved_family),
            ("fallbackReason", self.fallback_reason),
            ("fileHash", self.file_hash),
        ):
            if item is not None:
                payload[name] = item
        return payload


@dataclass(frozen=True)
class ResolvedGeometry:
    """Posição e tamanho já em pixels lógicos.

    Percentual e ``auto`` foram resolvidos antes: o renderizador não conhece a
    caixa do pai nem o canvas, e não deveria.
    """

    x: float = 0.0
    y: float = 0.0
    width: float | None = None
    height: float | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"x": self.x, "y": self.y}
        if self.width is not None:
            payload["width"] = self.width
        if self.height is not None:
            payload["height"] = self.height
        return payload


@dataclass(frozen=True)
class ResolvedTextNode:
    """Tudo que um renderizador precisa para desenhar um texto — e nada além."""

    id: str
    text: str = ""
    geometry: ResolvedGeometry = field(default_factory=ResolvedGeometry)
    visible: bool = True
    opacity: float = 1.0

    color: str = "#000000"
    font_family: str | None = None
    font_asset: FontAssetHandle | None = None
    font_size: float = 16.0
    font_weight: FontWeight = FontWeight.NORMAL
    font_style: FontStyle = FontStyle.NORMAL

    horizontal_alignment: TextAlignment = TextAlignment.START
    vertical_alignment: TextVerticalAlignment = TextVerticalAlignment.TOP

    source_reference: SourceReference | None = None
    #: Diagnósticos já materializados como dados. Não há referência viva a
    #: registry aqui: o DTO precisa sobreviver à serialização e ser comparável
    #: sem depender de nada que esteja em memória.
    resolution_diagnostics: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Serialização determinística.

        A ordem das chaves é fixa e os valores são escalares ou dicionários
        simples — dois nós iguais produzem exatamente o mesmo JSON, que é o que
        torna round-trip e comparação de golden confiáveis.
        """
        payload: dict[str, Any] = {
            "id": self.id,
            "text": self.text,
            "geometry": self.geometry.to_dict(),
            "visible": self.visible,
            "opacity": self.opacity,
            "color": self.color,
            "fontSize": self.font_size,
            "fontWeight": self.font_weight.value,
            "fontStyle": self.font_style.value,
            "horizontalAlignment": self.horizontal_alignment.value,
            "verticalAlignment": self.vertical_alignment.value,
        }
        if self.font_family is not None:
            payload["fontFamily"] = self.font_family
        if self.font_asset is not None:
            payload["fontAssetHandle"] = self.font_asset.to_dict()
        if self.source_reference is not None:
            payload["sourceReference"] = self.source_reference.to_dict()
        if self.resolution_diagnostics:
            payload["resolutionDiagnostics"] = list(self.resolution_diagnostics)
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ResolvedTextNode:
        """Reconstrói a partir da forma serializada, para o round-trip."""
        geometry = payload.get("geometry", {})
        font_asset = payload.get("fontAssetHandle")
        reference = payload.get("sourceReference")
        return cls(
            id=str(payload["id"]),
            text=str(payload.get("text", "")),
            geometry=ResolvedGeometry(
                x=float(geometry.get("x", 0.0)),
                y=float(geometry.get("y", 0.0)),
                width=geometry.get("width"),
                height=geometry.get("height"),
            ),
            visible=bool(payload.get("visible", True)),
            opacity=float(payload.get("opacity", 1.0)),
            color=str(payload.get("color", "#000000")),
            font_family=payload.get("fontFamily"),
            font_asset=(
                FontAssetHandle(
                    key=str(font_asset["key"]),
                    handle=font_asset.get("handle"),
                    origin=FontOrigin(font_asset.get("origin", "unavailable")),
                    requested_family=font_asset.get("requestedFamily"),
                    resolved_family=font_asset.get("resolvedFamily"),
                    fallback_reason=font_asset.get("fallbackReason"),
                    file_hash=font_asset.get("fileHash"),
                )
                if font_asset
                else None
            ),
            font_size=float(payload.get("fontSize", 16.0)),
            font_weight=FontWeight(payload.get("fontWeight", "normal")),
            font_style=FontStyle(payload.get("fontStyle", "normal")),
            horizontal_alignment=TextAlignment(payload.get("horizontalAlignment", "start")),
            vertical_alignment=TextVerticalAlignment(payload.get("verticalAlignment", "top")),
            source_reference=(
                SourceReference(
                    file=str(reference["file"]),
                    line=reference.get("line"),
                    column=reference.get("column"),
                    element=reference.get("element"),
                )
                if reference
                else None
            ),
            resolution_diagnostics=tuple(payload.get("resolutionDiagnostics", ())),
        )
