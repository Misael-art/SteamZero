# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Registros de tipo: o que cada caminho, token, configuração e asset produz.

Sem registro, o único jeito de saber o tipo de um binding seria olhar o
``fallback`` que o autor escreveu — e um binding SEM fallback ficaria sem
validação nenhuma. Isso deixaria passar o caso mais provável de erro real:

    fontSize = binding("game.title")

que é inválido porque ``game.title`` produz texto, mesmo sem fallback algum
declarado.

Com registro, a validação passa a ser possível em três frentes independentes:

1. o tipo ESPERADO pela propriedade receptora;
2. o tipo PUBLICADO pelo registro para aquele caminho;
3. o tipo do ``fallback``, quando existir.

Divergência entre (1) e (2) é erro de contrato, detectável em compilação.

**Caminho desconhecido nunca é aceito em silêncio.** A política é explícita por
natureza do binding: obrigatório vira ``invalid``, opcional com fallback usa o
fallback, e ``extension.*`` entra em negociação de capability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from steamzero.domain.scene_typing import (
    SourceReference,
    TypeError_,
    ValueType,
    check_type,
    validate_path,
)


class ResolutionPhase(StrEnum):
    """Quando o valor final é conhecido.

    Importa para o cache: o que resolve em ``compileTime`` pode ser assado no
    pacote; ``loadTime`` depende de tema e locale; ``runtime`` muda com o estado
    e precisa de invalidação por dependência.
    """

    COMPILE_TIME = "compileTime"
    LOAD_TIME = "loadTime"
    RUNTIME = "runtime"


#: Namespaces que NENHUM tema alcança, em nenhuma circunstância.
#:
#: Não é lista de "ainda não suportado": é recusa deliberada, e por isso o
#: veredito é ``ignoredByPolicy`` — que não entra na fila de trabalho futuro.
#: Confundir os dois faria alguém tentar implementar acesso ao número de série
#: do host porque o relatório disse "unsupported".
FORBIDDEN_NAMESPACES = ("host.", "process.", "credential.", "network.", "secret.", "internal.")


def forbidden_namespace(path: str) -> str | None:
    """O namespace proibido que este caminho alcança, se algum.

    Mora aqui, e não em cada importador, porque uma segunda lista divergiria da
    primeira — e foi assim que `system.` chegou a estar proibido num módulo
    enquanto `default_registries()` publicava `system.time` como legítimo.
    """
    for namespace in FORBIDDEN_NAMESPACES:
        if path.startswith(namespace):
            return namespace
    return None


class UnknownPathPolicy(StrEnum):
    """O que fazer com um caminho que nenhum registro publica."""

    INVALID = "invalid"
    USE_FALLBACK = "fallback"
    NEGOTIATE_CAPABILITY = "capabilityNegotiation"
    #: Recusa deliberada. Distinta das demais: não vira trabalho futuro.
    FORBIDDEN = "forbidden"


@dataclass(frozen=True)
class DeferredValue:
    """Valor cuja resolução acontece depois, mas cujo CONTRATO é validável agora.

    Carrega os quatro campos exigidos: tipo esperado, fase de resolução, origem
    no arquivo e fallback. É o que permite validar namespace, gramática do
    caminho, autorização e compatibilidade sem conhecer o valor real.
    """

    source_kind: str
    source_path: str
    expected_type: ValueType
    resolution_phase: ResolutionPhase
    fallback: Any = None
    source_reference: SourceReference | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "sourceKind": self.source_kind,
            "sourcePath": self.source_path,
            "expectedType": self.expected_type.value,
            "resolutionPhase": self.resolution_phase.value,
        }
        if self.fallback is not None:
            payload["fallback"] = self.fallback
        if self.source_reference is not None:
            payload["sourceReference"] = self.source_reference.to_dict()
        return payload


@dataclass
class _TypeRegistry:
    """Base dos registros: caminho lógico -> tipo publicado."""

    name: str
    types: dict[str, ValueType] = field(default_factory=dict)

    def declare(self, path: str, value_type: ValueType) -> None:
        self.types[path] = value_type

    def type_of(self, path: str) -> ValueType | None:
        return self.types.get(path)

    def knows(self, path: str) -> bool:
        return path in self.types


class PropertyTypeRegistry(_TypeRegistry):
    """Tipo que cada propriedade de elemento aceita.

    É a fonte de ``fontSize: Value<number>``, e portanto o que permite ao
    resolver exigir que qualquer binding ligado a ``fontSize`` produza número.
    """


class BindingTypeRegistry(_TypeRegistry):
    """Tipo publicado por cada caminho do read model."""


class TokenTypeRegistry(_TypeRegistry):
    """Tipo de cada token de design."""


class ThemeSettingTypeRegistry(_TypeRegistry):
    """Tipo de cada configuração que o tema declara."""


class AssetTypeRegistry(_TypeRegistry):
    """Tipo de cada classe de asset — mídia, fonte, som."""


@dataclass(frozen=True)
class TypeCheck:
    """Resultado da checagem de uma origem diferida contra os registros."""

    ok: bool
    reason: str | None = None
    policy: UnknownPathPolicy | None = None
    declared_type: ValueType | None = None


@dataclass
class Registries:
    """Conjunto de registros usado pelo resolver."""

    properties: PropertyTypeRegistry = field(
        default_factory=lambda: PropertyTypeRegistry("property")
    )
    bindings: BindingTypeRegistry = field(default_factory=lambda: BindingTypeRegistry("binding"))
    tokens: TokenTypeRegistry = field(default_factory=lambda: TokenTypeRegistry("token"))
    settings: ThemeSettingTypeRegistry = field(
        default_factory=lambda: ThemeSettingTypeRegistry("setting")
    )
    assets: AssetTypeRegistry = field(default_factory=lambda: AssetTypeRegistry("asset"))

    def registry_for(self, source_kind: str) -> _TypeRegistry | None:
        return {
            "bind": self.bindings,
            "token": self.tokens,
            "setting": self.settings,
            "asset": self.assets,
        }.get(source_kind)

    def expected_for_property(self, property_name: str) -> ValueType | None:
        return self.properties.type_of(property_name)

    def check_deferred(
        self,
        deferred: DeferredValue,
        *,
        required: bool = True,
        theme_id: str | None = None,
    ) -> TypeCheck:
        """Valida uma origem diferida sem conhecer o valor real.

        A ordem importa. Gramática e namespace vêm primeiro porque um caminho
        malformado não deve nem ser procurado no registro — procurar sugeriria
        que existe a possibilidade de ele ser válido.
        """
        try:
            validate_path(deferred.source_path, theme_id=theme_id)
        except ValueError as exc:
            return TypeCheck(False, reason=str(exc))

        # POLÍTICA ANTES DO REGISTRO. A ordem não é estética: quando a busca no
        # registro vinha primeiro, um caminho proibido que também fosse
        # desconhecido saía como `unsupported` — e `unsupported` vira trabalho
        # futuro. A recusa de política precisa vencer, ou alguém acaba
        # implementando o que foi deliberadamente negado.
        namespace = forbidden_namespace(deferred.source_path)
        if namespace is not None:
            return TypeCheck(
                False,
                reason=f"namespace {namespace!r} é recusa de política, não limitação",
                policy=UnknownPathPolicy.FORBIDDEN,
            )

        registry = self.registry_for(deferred.source_kind)
        if registry is None:
            return TypeCheck(False, reason=f"origem sem registro: {deferred.source_kind!r}")

        declared = registry.type_of(deferred.source_path)
        if declared is None:
            return self._unknown_path(deferred, required=required)

        if declared is not deferred.expected_type:
            # Este é o caso que o fallback sozinho não pegava:
            # fontSize = binding("game.title") sem fallback nenhum.
            return TypeCheck(
                False,
                reason=(
                    f"{deferred.source_path} produz {declared.value}, mas "
                    f"{deferred.expected_type.value} era esperado"
                ),
                declared_type=declared,
            )

        if deferred.fallback is not None:
            try:
                check_type(deferred.fallback, deferred.expected_type, where="fallback")
            except TypeError_ as exc:
                return TypeCheck(False, reason=str(exc), declared_type=declared)

        return TypeCheck(True, declared_type=declared)

    @staticmethod
    def _unknown_path(deferred: DeferredValue, *, required: bool) -> TypeCheck:
        """Caminho que nenhum registro publica. Nunca aceito em silêncio."""
        if deferred.source_path.startswith("extension."):
            return TypeCheck(
                False,
                reason=f"extensão não registrada: {deferred.source_path}",
                policy=UnknownPathPolicy.NEGOTIATE_CAPABILITY,
            )
        if not required and deferred.fallback is not None:
            return TypeCheck(
                False,
                reason=f"caminho desconhecido: {deferred.source_path}; usando fallback",
                policy=UnknownPathPolicy.USE_FALLBACK,
            )
        return TypeCheck(
            False,
            reason=f"caminho desconhecido: {deferred.source_path}",
            policy=UnknownPathPolicy.INVALID,
        )


def default_registries() -> Registries:
    """Registros com o vocabulário mínimo do P0-03 já declarado.

    Os caminhos declarados aqui são os que o corpus RetroFE usa e os tokens de
    cor mínimos da especificação — o bastante para a vertical slice funcionar
    sem depender do read model completo, que ainda não existe.
    """
    registries = Registries()

    for name, value_type in {
        "color": ValueType.COLOR,
        "strokeColor": ValueType.COLOR,
        "background": ValueType.COLOR,
        "fontFamily": ValueType.STRING,
        "fontAsset": ValueType.FONT,
        "fontSize": ValueType.NUMBER,
        "fontWeight": ValueType.NUMBER,
        "lineHeight": ValueType.NUMBER,
        "letterSpacing": ValueType.NUMBER,
        "horizontalAlignment": ValueType.ENUM,
        "verticalAlignment": ValueType.ENUM,
        "opacity": ValueType.NUMBER,
        "visible": ValueType.BOOLEAN,
        "x": ValueType.DIMENSION,
        "y": ValueType.DIMENSION,
        "width": ValueType.DIMENSION,
        "height": ValueType.DIMENSION,
        "rotation": ValueType.NUMBER,
        "scaleX": ValueType.NUMBER,
        "scaleY": ValueType.NUMBER,
        "content": ValueType.STRING,
        "source": ValueType.MEDIA,
    }.items():
        registries.properties.declare(name, value_type)

    for path, value_type in {
        "game.title": ValueType.STRING,
        "game.shortName": ValueType.STRING,
        "game.description": ValueType.STRING,
        "game.year": ValueType.NUMBER,
        "game.rating": ValueType.NUMBER,
        "game.players": ValueType.NUMBER,
        "game.favorite": ValueType.BOOLEAN,
        "game.genre": ValueType.STRING,
        "game.developer": ValueType.STRING,
        "game.publisher": ValueType.STRING,
        "system.time": ValueType.STRING,
        "system.date": ValueType.STRING,
        "system.battery": ValueType.NUMBER,
    }.items():
        registries.bindings.declare(path, value_type)

    for token in (
        "color.background.primary",
        "color.background.secondary",
        "color.surface",
        "color.surface.focused",
        "color.text.primary",
        "color.text.secondary",
        "color.text.disabled",
        "color.accent",
        "color.focusRing",
        "color.success",
        "color.warning",
        "color.error",
        "color.info",
        "color.overlay",
        "color.border",
    ):
        registries.tokens.declare(token, ValueType.COLOR)

    for path in (
        "media.image.packaging.box.front",
        "media.image.identity.clearLogo",
        "media.image.identity.background",
        "media.video.preview.gameplay",
    ):
        registries.assets.declare(path, ValueType.MEDIA)

    return registries
