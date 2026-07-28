# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Resolver de valores: literal, token, asset, binding, tradução, configuração.

Resolve o modelo de valor até um resultado concreto, registrando o caminho
percorrido. Três propriedades importam mais que a resolução em si:

**Grafo de dependências.** Cada valor resolvido declara de quais tokens,
configurações e caminhos do read model ele dependeu. Quando um token muda,
apenas os dependentes daquele token são invalidados — não a cena inteira. Sem
isso, mudar uma cor recomputaria 866 elementos.

**Detecção de ciclo entre origens diferentes.** O ciclo perigoso não é
``token → token``; é ``token → configuração → token``, que atravessa sistemas e
por isso escapa de uma checagem local. O diagnóstico mostra o caminho completo,
porque saber que existe ciclo sem saber onde não ajuda ninguém.

**Chave de cache composta.** Um valor resolvido depende de tema, geração de
tokens, geração do read model, locale, perfil de acessibilidade e variante de
estado. Ignorar qualquer um deles produz cache que devolve a resposta certa para
a pergunta errada — pior que não ter cache.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from steamzero.domain.scene_registry import Registries, ResolutionPhase
from steamzero.domain.scene_typing import (
    MAX_FALLBACK_DEPTH,
    SourceReference,
    TypeError_,
    ValueType,
    check_type,
    validate_path,
)

#: Códigos estáveis de diagnóstico. Estáveis porque entram em relatório e em
#: documentação de autor — renomear quebraria referência externa.
DIAG_CYCLE = "THEME-RESOLUTION-CYCLE-001"
DIAG_DEPTH = "THEME-RESOLUTION-DEPTH-002"
# "TOKEN" aqui é token de DESIGN, não credencial — falso positivo do S105.
DIAG_UNKNOWN_TOKEN = "THEME-RESOLUTION-TOKEN-003"  # noqa: S105
DIAG_UNKNOWN_BINDING = "THEME-RESOLUTION-BINDING-004"
DIAG_UNKNOWN_SETTING = "THEME-RESOLUTION-SETTING-005"
DIAG_TYPE = "THEME-RESOLUTION-TYPE-006"
DIAG_NAMESPACE = "THEME-RESOLUTION-NAMESPACE-007"
DIAG_CAPABILITY = "THEME-RESOLUTION-CAPABILITY-008"
DIAG_MISSING_TRANSLATION = "THEME-RESOLUTION-I18N-009"
DIAG_MISSING_ASSET = "THEME-RESOLUTION-ASSET-010"
DIAG_CONDITION_TYPE = "THEME-CONDITION-TYPE-MISMATCH-001"


class Absence(StrEnum):
    """Por que um valor não está aqui.

    Usar ``None`` para tudo confunde quatro situações distintas: propriedade que
    a origem nunca declarou, binding que ainda não resolveu, provider que
    falhou, e valor que é legitimamente nulo. Elas exigem respostas diferentes —
    ``exists`` precisa distinguir ausência de nulo explícito, e um provider que
    falhou pode voltar, enquanto uma propriedade ausente não.
    """

    MISSING = "missing"
    UNRESOLVED = "unresolved"
    EXPLICIT_NULL = "explicitNull"


#: Sentinelas. Comparação por identidade, nunca por igualdade — ``==`` com um
#: valor de tema poderia ser sobrecarregado.
MISSING = Absence.MISSING
UNRESOLVED = Absence.UNRESOLVED
EXPLICIT_NULL = Absence.EXPLICIT_NULL


def is_absent(value: Any) -> bool:
    """Se o valor representa alguma forma de ausência."""
    return isinstance(value, Absence)


class Truth(StrEnum):
    """Resultado de uma condição.

    ``INDETERMINATE`` existe porque tratar incompatibilidade como ``false``
    selecionaria o ramo ``otherwise`` e produziria uma interface de aparência
    válida e semanticamente ERRADA — pior que uma que falha visivelmente.
    """

    TRUE = "true"
    FALSE = "false"
    INDETERMINATE = "indeterminate"


class ResolutionError(ValueError):
    """Falha de resolução com código estável e caminho percorrido."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        path: tuple[str, ...] = (),
        reference: SourceReference | None = None,
    ) -> None:
        self.code = code
        self.path = path
        self.reference = reference
        location = f" em {reference}" if reference else ""
        trail = "\n  " + "\n→ ".join(path) if path else ""
        super().__init__(f"{code}: {message}{location}{trail}")

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": str(self)}
        if self.path:
            payload["cyclePath"] = list(self.path)
        if self.reference is not None:
            payload["sourceReference"] = self.reference.to_dict()
        return payload


@dataclass(frozen=True)
class Generations:
    """Versões das fontes que alimentam o resolver.

    Cada uma incrementa quando sua fonte muda. A chave de cache as inclui, então
    um valor resolvido sob uma geração antiga nunca é servido depois.
    """

    theme: int = 0
    #: Separada de ``theme`` de propósito: uma configuração pode mudar sem que o
    #: tema seja reinstalado ou recarregado.
    theme_settings: int = 0
    tokens: int = 0
    read_model: int = 0
    #: Catálogo de tradução e registro de assets mudam em desenvolvimento sem
    #: que locale ou versão do tema mudem.
    translation_catalog: int = 0
    asset_registry: int = 0
    locale: str = "pt-BR"
    accessibility: str = "default"
    display: str = "default"
    state_variant: str = "default"

    def key(self) -> tuple[Any, ...]:
        return (
            self.theme,
            self.theme_settings,
            self.tokens,
            self.read_model,
            self.translation_catalog,
            self.asset_registry,
            self.locale,
            self.accessibility,
            self.display,
            self.state_variant,
        )


@dataclass
class ResolutionContext:
    """Tudo que o resolver consulta. Somente leitura do ponto de vista do tema."""

    registries: Registries
    tokens: Mapping[str, Any] = field(default_factory=dict)
    settings: Mapping[str, Any] = field(default_factory=dict)
    read_model: Mapping[str, Any] = field(default_factory=dict)
    translations: Mapping[str, str] = field(default_factory=dict)
    assets: frozenset[str] = frozenset()
    capabilities: frozenset[str] = frozenset()
    states: frozenset[str] = frozenset()
    generations: Generations = field(default_factory=Generations)
    theme_id: str | None = None


@dataclass(frozen=True)
class Resolved:
    """Valor concreto mais as dependências que o produziram."""

    value: Any
    dependencies: frozenset[str] = frozenset()
    phase: ResolutionPhase = ResolutionPhase.COMPILE_TIME
    used_fallback: bool = False
    #: Identidade da origem preservada mesmo quando token e configuração
    #: compartilham o algoritmo — importa para diagnóstico, permissão,
    #: precedência e invalidação.
    source_kind: str | None = None
    source_namespace: str | None = None
    source_path: str | None = None
    source_reference: SourceReference | None = None
    generation: tuple[Any, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "value": self.value,
            "dependencies": sorted(self.dependencies),
            "phase": self.phase.value,
            "usedFallback": self.used_fallback,
        }
        for key, item in (
            ("sourceKind", self.source_kind),
            ("sourceNamespace", self.source_namespace),
            ("sourcePath", self.source_path),
        ):
            if item is not None:
                payload[key] = item
        if self.source_reference is not None:
            payload["sourceReference"] = self.source_reference.to_dict()
        if self.diagnostics:
            payload["diagnostics"] = [item.to_dict() for item in self.diagnostics]
        return payload


@dataclass
class DependencyGraph:
    """Quem depende de quê. Permite invalidar por ramo em vez de tudo."""

    _dependents: dict[str, set[str]] = field(default_factory=dict)
    _dependencies: dict[str, frozenset[str]] = field(default_factory=dict)

    def record(self, target: str, dependencies: frozenset[str]) -> None:
        previous = self._dependencies.get(target, frozenset())
        for gone in previous - dependencies:
            self._dependents.get(gone, set()).discard(target)
        for added in dependencies - previous:
            self._dependents.setdefault(added, set()).add(target)
        self._dependencies[target] = dependencies

    def dependents_of(self, dependency: str) -> frozenset[str]:
        """Alvos afetados, transitivamente.

        Transitivo importa: um token que alimenta outro token que alimenta a cor
        de um elemento precisa invalidar o elemento, não só o token do meio.
        """
        seen: set[str] = set()
        queue = [dependency]
        while queue:
            current = queue.pop()
            for target in self._dependents.get(current, set()):
                if target not in seen:
                    seen.add(target)
                    queue.append(target)
        return frozenset(seen)

    def dependencies_of(self, target: str) -> frozenset[str]:
        return self._dependencies.get(target, frozenset())


@dataclass(frozen=True)
class Diagnostic:
    """Aviso não fatal emitido durante a resolução."""

    code: str
    message: str
    target: str
    reference: SourceReference | None = None
    resolution: str = "fallback"

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "property": self.target,
            "resolution": self.resolution,
        }
        if self.reference is not None:
            payload["sourceReference"] = self.reference.to_dict()
        return payload


@dataclass
class DiagnosticSink:
    """Coleta diagnósticos deduplicados por propriedade e geração.

    Sem deduplicação, uma condição incompatível numa lista de 500 itens emitiria
    500 avisos por frame — o log deixaria de ser legível justamente quando é mais
    necessário.
    """

    entries: list[Diagnostic] = field(default_factory=list)
    _seen: set[tuple[Any, ...]] = field(default_factory=set, repr=False)

    def emit(self, diagnostic: Diagnostic, generation: tuple[Any, ...]) -> bool:
        key = (diagnostic.code, diagnostic.target, generation)
        if key in self._seen:
            return False
        self._seen.add(key)
        self.entries.append(diagnostic)
        return True

    def to_list(self) -> list[dict[str, Any]]:
        return [entry.to_dict() for entry in self.entries]


@dataclass
class ResolverStats:
    """Contadores para provar que o cache funciona."""

    hits: int = 0
    misses: int = 0
    invalidations: int = 0

    def to_dict(self) -> dict[str, int]:
        return {"hits": self.hits, "misses": self.misses, "invalidations": self.invalidations}


class Resolver:
    """Resolve valores com cache e invalidação por dependência."""

    def __init__(self, context: ResolutionContext) -> None:
        self._context = context
        self._cache: dict[tuple[Any, ...], Resolved] = {}
        self.graph = DependencyGraph()
        self.stats = ResolverStats()
        self.diagnostics = DiagnosticSink()

    @property
    def context(self) -> ResolutionContext:
        return self._context

    def resolve(
        self,
        value: Any,
        expected: ValueType,
        *,
        target: str,
        reference: SourceReference | None = None,
    ) -> Resolved:
        """Resolve ``value`` para a propriedade ``target``.

        ``target`` identifica a propriedade no grafo — algo como
        ``gameTitle.typography.color``. É a chave pela qual a invalidação
        encontra o que recomputar.
        """
        cache_key = (target, *self._context.generations.key())
        cached = self._cache.get(cache_key)
        if cached is not None:
            self.stats.hits += 1
            return cached

        self.stats.misses += 1
        dependencies: set[str] = set()
        phase = ResolutionPhase.COMPILE_TIME
        resolved_value, used_fallback, phase = self._resolve(
            value, expected, dependencies, (), reference, target
        )
        result = Resolved(resolved_value, frozenset(dependencies), phase, used_fallback)
        self._cache[cache_key] = result
        self.graph.record(target, result.dependencies)
        return result

    def invalidate(self, dependency: str) -> frozenset[str]:
        """Descarta o cache dos alvos que dependem de ``dependency``.

        Devolve o conjunto invalidado, para que o chamador possa provar que uma
        mudança localizada não derrubou a cena inteira.
        """
        affected = self.graph.dependents_of(dependency)
        if not affected:
            return frozenset()
        for key in [key for key in self._cache if key[0] in affected]:
            del self._cache[key]
        self.stats.invalidations += len(affected)
        return affected

    def _resolve(
        self,
        value: Any,
        expected: ValueType,
        dependencies: set[str],
        trail: tuple[str, ...],
        reference: SourceReference | None,
        target: str,
    ) -> tuple[Any, bool, ResolutionPhase]:
        if len(trail) > MAX_FALLBACK_DEPTH:
            raise ResolutionError(
                DIAG_DEPTH,
                f"resolução excedeu {MAX_FALLBACK_DEPTH} níveis",
                path=trail,
                reference=reference,
            )

        if not isinstance(value, dict):
            self._check(value, expected, reference)
            return value, False, ResolutionPhase.COMPILE_TIME

        if "when" in value:
            return self._resolve_conditional(
                value, expected, dependencies, trail, reference, target
            )
        if "token" in value:
            return self._resolve_indirect(
                value, "token", expected, dependencies, trail, reference, target
            )
        if "setting" in value:
            return self._resolve_indirect(
                value, "setting", expected, dependencies, trail, reference, target
            )
        if "bind" in value:
            return self._resolve_binding(value, expected, dependencies, trail, reference, target)
        if "asset" in value:
            return self._resolve_asset(value, expected, dependencies, trail, reference, target)
        if "text" in value:
            return self._resolve_translation(
                value, expected, dependencies, trail, reference, target
            )

        raise ResolutionError(
            DIAG_TYPE, f"forma de valor desconhecida: {sorted(value)}", reference=reference
        )

    def _resolve_indirect(
        self,
        value: dict[str, Any],
        kind: str,
        expected: ValueType,
        dependencies: set[str],
        trail: tuple[str, ...],
        reference: SourceReference | None,
        target: str,
    ) -> tuple[Any, bool, ResolutionPhase]:
        """Token e configuração: mesma mecânica, tabelas diferentes.

        São tratados juntos porque o ciclo perigoso atravessa os dois —
        ``token → setting → token`` — e separar o código separaria a detecção.
        """
        name = str(value[kind])
        marker = f"{kind}:{name}"
        if marker in trail:
            raise ResolutionError(
                DIAG_CYCLE,
                "ciclo de resolução",
                path=(*trail, marker),
                reference=reference,
            )
        dependencies.add(marker)

        table = self._context.tokens if kind == "token" else self._context.settings
        if name in table:
            nested = table[name]
            resolved, used_fallback, _ = self._resolve(
                nested, expected, dependencies, (*trail, marker), reference, target
            )
            phase = ResolutionPhase.LOAD_TIME if kind == "token" else ResolutionPhase.RUNTIME
            return resolved, used_fallback, phase

        code = DIAG_UNKNOWN_TOKEN if kind == "token" else DIAG_UNKNOWN_SETTING
        return self._fallback_or_fail(
            value,
            expected,
            dependencies,
            trail,
            reference,
            target,
            code,
            f"{kind} não declarado: {name}",
        )

    def _resolve_binding(
        self,
        value: dict[str, Any],
        expected: ValueType,
        dependencies: set[str],
        trail: tuple[str, ...],
        reference: SourceReference | None,
        target: str,
    ) -> tuple[Any, bool, ResolutionPhase]:
        path = str(value["bind"])
        try:
            validate_path(path, theme_id=self._context.theme_id)
        except ValueError as exc:
            raise ResolutionError(DIAG_NAMESPACE, str(exc), reference=reference) from exc

        declared = self._context.registries.bindings.type_of(path)
        if declared is not None and declared is not expected:
            raise ResolutionError(
                DIAG_TYPE,
                f"{path} produz {declared.value}, mas {expected.value} era esperado",
                reference=reference,
            )

        dependencies.add(f"bind:{path}")
        if path in self._context.read_model:
            resolved = self._context.read_model[path]
            self._check(resolved, expected, reference)
            return resolved, False, ResolutionPhase.RUNTIME

        return self._fallback_or_fail(
            value,
            expected,
            dependencies,
            trail,
            reference,
            target,
            DIAG_UNKNOWN_BINDING,
            f"caminho não disponível: {path}",
        )

    def _resolve_asset(
        self,
        value: dict[str, Any],
        expected: ValueType,
        dependencies: set[str],
        trail: tuple[str, ...],
        reference: SourceReference | None,
        target: str,
    ) -> tuple[Any, bool, ResolutionPhase]:
        path = str(value["asset"])
        dependencies.add(f"asset:{path}")
        if not self._context.assets or path in self._context.assets:
            return path, False, ResolutionPhase.LOAD_TIME
        return self._fallback_or_fail(
            value,
            expected,
            dependencies,
            trail,
            reference,
            target,
            DIAG_MISSING_ASSET,
            f"asset ausente no pacote: {path}",
        )

    def _resolve_translation(
        self,
        value: dict[str, Any],
        expected: ValueType,
        dependencies: set[str],
        trail: tuple[str, ...],
        reference: SourceReference | None,
        target: str,
    ) -> tuple[Any, bool, ResolutionPhase]:
        key = str(value["text"])
        dependencies.add(f"i18n:{key}")
        if key in self._context.translations:
            return self._context.translations[key], False, ResolutionPhase.LOAD_TIME
        declared = value.get("fallback")
        if declared is not None:
            # Degradação prevista, não erro — o autor escreveu o texto de origem
            # justamente para este caso. Mas PRECISA ser contabilizada como
            # fallback, e o aviso sai uma vez por chave e locale, nunca por
            # frame: uma lista de 500 itens emitiria 500 avisos idênticos.
            self.diagnostics.emit(
                Diagnostic(
                    DIAG_MISSING_TRANSLATION,
                    f"tradução ausente para {key!r} em {self._context.generations.locale}",
                    target=target,
                    reference=reference,
                    resolution="fallback",
                ),
                (self._context.generations.locale, self._context.generations.translation_catalog),
            )
            return declared, True, ResolutionPhase.LOAD_TIME
        raise ResolutionError(
            DIAG_MISSING_TRANSLATION, f"tradução ausente: {key}", reference=reference
        )

    def _resolve_conditional(
        self,
        value: dict[str, Any],
        expected: ValueType,
        dependencies: set[str],
        trail: tuple[str, ...],
        reference: SourceReference | None,
        target: str,
    ) -> tuple[Any, bool, ResolutionPhase]:
        outcome = self._evaluate(value["when"], dependencies, reference, target)

        if outcome is Truth.INDETERMINATE:
            # Nem then nem otherwise: escolher um ramo sem base produziria uma
            # tela plausível e errada. Vai para o fallback declarado, e se não
            # houver, para o valor seguro do contrato.
            declared = value.get("fallback")
            if declared is not None:
                resolved, _, _ = self._resolve(
                    declared, expected, dependencies, trail, reference, target
                )
                return resolved, True, ResolutionPhase.RUNTIME
            return SAFE_DEFAULTS.get(expected), True, ResolutionPhase.RUNTIME

        branch = value["then"] if outcome is Truth.TRUE else value.get("otherwise")
        if branch is None:
            return None, False, ResolutionPhase.RUNTIME
        resolved, used_fallback, _ = self._resolve(
            branch, expected, dependencies, trail, reference, target
        )
        # Condicional é sempre runtime: o ramo escolhido muda com o estado.
        return resolved, used_fallback, ResolutionPhase.RUNTIME

    def _fallback_or_fail(
        self,
        value: dict[str, Any],
        expected: ValueType,
        dependencies: set[str],
        trail: tuple[str, ...],
        reference: SourceReference | None,
        target: str,
        code: str,
        message: str,
    ) -> tuple[Any, bool, ResolutionPhase]:
        declared = value.get("fallback")
        if declared is None:
            raise ResolutionError(code, message, path=trail, reference=reference)
        resolved, _, phase = self._resolve(
            declared, expected, dependencies, trail, reference, target
        )
        return resolved, True, phase

    def _evaluate(
        self,
        condition: Any,
        dependencies: set[str],
        reference: SourceReference | None,
        target: str,
    ) -> Truth:
        """Avalia uma condição em lógica ternária.

        ``INDETERMINATE`` propaga: uma conjunção com um operando indeterminado
        só é falsa se outro operando for comprovadamente falso. Colapsar para
        ``false`` cedo escolheria o ramo ``otherwise`` sem base.
        """
        if not isinstance(condition, dict):
            return Truth.TRUE if condition else Truth.FALSE
        op = condition.get("op")

        if op == "state":
            return _truth(str(condition["state"]) in self._context.states)
        if op == "capability":
            name = str(condition["name"])
            dependencies.add(f"capability:{name}")
            return _truth(name in self._context.capabilities)
        if op in {"and", "or"}:
            results = [
                self._evaluate(item, dependencies, reference, target)
                for item in condition.get("operands", [])
            ]
            return _conjunction(results) if op == "and" else _disjunction(results)
        if op == "not":
            return _negate(
                self._evaluate(condition.get("operand"), dependencies, reference, target)
            )

        left = self._operand(condition.get("left"), dependencies)
        right = self._operand(condition.get("right"), dependencies)
        result = _compare(op, left, right)
        if result is Truth.INDETERMINATE:
            self.diagnostics.emit(
                Diagnostic(
                    DIAG_CONDITION_TYPE,
                    (f"operador {op!r} recebeu {type(left).__name__} e {type(right).__name__}"),
                    target=target,
                    reference=reference,
                    resolution="fallback",
                ),
                self._context.generations.key(),
            )
        return result

    def _operand(self, value: Any, dependencies: set[str]) -> Any:
        """Lê um operando sem exigir tipo — comparação não conhece o tipo alvo."""
        if not isinstance(value, dict):
            return value
        if "bind" in value:
            path = str(value["bind"])
            dependencies.add(f"bind:{path}")
            return self._context.read_model.get(path, value.get("fallback"))
        if "token" in value:
            name = str(value["token"])
            dependencies.add(f"token:{name}")
            return self._context.tokens.get(name, value.get("fallback"))
        if "setting" in value:
            name = str(value["setting"])
            dependencies.add(f"setting:{name}")
            return self._context.settings.get(name, value.get("fallback"))
        return value

    def _check(self, value: Any, expected: ValueType, reference: SourceReference | None) -> None:
        try:
            check_type(value, expected)
        except TypeError_ as exc:
            raise ResolutionError(DIAG_TYPE, str(exc), reference=reference) from exc


_COMPARATORS: dict[str, Callable[[Any, Any], bool]] = {
    "equals": lambda a, b: bool(a == b),
    "notEquals": lambda a, b: bool(a != b),
    "greaterThan": lambda a, b: bool(a > b),
    "lessThan": lambda a, b: bool(a < b),
    "greaterOrEqual": lambda a, b: bool(a >= b),
    "lessOrEqual": lambda a, b: bool(a <= b),
    "contains": lambda a, b: bool(b in a),
    "in": lambda a, b: bool(a in b),
}

#: Valor seguro por tipo, usado quando uma condição fica indeterminada e o autor
#: não declarou fallback. Escolhidos para não desenhar nada visualmente errado:
#: transparente, vazio, invisível.
SAFE_DEFAULTS: dict[ValueType, Any] = {
    ValueType.COLOR: "#00000000",
    ValueType.STRING: "",
    ValueType.NUMBER: 0,
    ValueType.DURATION: 0,
    ValueType.BOOLEAN: False,
    ValueType.DIMENSION: 0,
}


def _truth(condition: bool) -> Truth:
    return Truth.TRUE if condition else Truth.FALSE


def _conjunction(results: list[Truth]) -> Truth:
    """``and`` ternário.

    Curto-circuita SOMENTE quando o resultado já está logicamente determinado:
    um ``false`` decide sozinho. Mas ``true AND indeterminate`` continua
    indeterminado — colapsar para verdadeiro escolheria o ramo ``then`` sem base.
    """
    if Truth.FALSE in results:
        return Truth.FALSE
    if Truth.INDETERMINATE in results:
        return Truth.INDETERMINATE
    return Truth.TRUE


def _disjunction(results: list[Truth]) -> Truth:
    """``or`` ternário. Um ``true`` decide sozinho; o resto propaga."""
    if Truth.TRUE in results:
        return Truth.TRUE
    if Truth.INDETERMINATE in results:
        return Truth.INDETERMINATE
    return Truth.FALSE


def _negate(inner: Truth) -> Truth:
    if inner is Truth.INDETERMINATE:
        return Truth.INDETERMINATE
    return Truth.FALSE if inner is Truth.TRUE else Truth.TRUE


def _compare(op: Any, left: Any, right: Any) -> Truth:
    """Compara em lógica ternária.

    Tipos incompatíveis devolvem ``INDETERMINATE``, nunca ``FALSE``: um
    ``greaterThan`` entre texto e número não é "não maior", é uma pergunta sem
    resposta, e responder ``false`` escolheria o ramo ``otherwise``.
    """
    # exists e missing EXISTEM para testar presença: precisam devolver booleano
    # determinístico mesmo diante de ausência, senão não serviriam ao seu
    # propósito. Nulo explícito conta como presente — o autor o declarou.
    if op == "exists":
        return _truth(left is not EXPLICIT_NULL and not is_absent(left) and left is not None)
    if op == "missing":
        return _truth((is_absent(left) and left is not EXPLICIT_NULL) or left is None)

    comparator = _COMPARATORS.get(str(op))
    if comparator is None:
        raise ResolutionError(DIAG_TYPE, f"operador desconhecido: {op!r}")
    # Comparação comum diante de ausência não inventa resultado.
    if is_absent(left) or is_absent(right) or left is None or right is None:
        return Truth.INDETERMINATE
    try:
        return _truth(comparator(left, right))
    except TypeError:
        return Truth.INDETERMINATE
