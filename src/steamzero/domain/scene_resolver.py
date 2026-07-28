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
    tokens: int = 0
    read_model: int = 0
    locale: str = "pt-BR"
    accessibility: str = "default"
    display: str = "default"

    def key(self) -> tuple[Any, ...]:
        return (
            self.theme,
            self.tokens,
            self.read_model,
            self.locale,
            self.accessibility,
            self.display,
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "dependencies": sorted(self.dependencies),
            "phase": self.phase.value,
            "usedFallback": self.used_fallback,
        }


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
            # Tradução ausente com fallback é degradação prevista, não erro: o
            # autor escreveu o texto de origem justamente para este caso.
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
        chosen = self._evaluate(value["when"], dependencies, reference)
        branch = value["then"] if chosen else value.get("otherwise")
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
    ) -> bool:
        if not isinstance(condition, dict):
            return bool(condition)
        op = condition.get("op")

        if op == "state":
            return str(condition["state"]) in self._context.states
        if op == "capability":
            name = str(condition["name"])
            dependencies.add(f"capability:{name}")
            return name in self._context.capabilities
        if op == "and":
            return all(
                self._evaluate(item, dependencies, reference)
                for item in condition.get("operands", [])
            )
        if op == "or":
            return any(
                self._evaluate(item, dependencies, reference)
                for item in condition.get("operands", [])
            )
        if op == "not":
            return not self._evaluate(condition.get("operand"), dependencies, reference)

        left = self._operand(condition.get("left"), dependencies)
        right = self._operand(condition.get("right"), dependencies)
        return _compare(op, left, right)

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
    "greaterThan": lambda a, b: bool(a is not None and b is not None and a > b),
    "lessThan": lambda a, b: bool(a is not None and b is not None and a < b),
    "greaterOrEqual": lambda a, b: bool(a is not None and b is not None and a >= b),
    "lessOrEqual": lambda a, b: bool(a is not None and b is not None and a <= b),
    "contains": lambda a, b: bool(a is not None and b in a),
    "in": lambda a, b: bool(b is not None and a in b),
}


def _compare(op: Any, left: Any, right: Any) -> bool:
    if op == "exists":
        return left is not None
    if op == "missing":
        return left is None
    comparator = _COMPARATORS.get(str(op))
    if comparator is None:
        raise ResolutionError(DIAG_TYPE, f"operador desconhecido: {op!r}")
    try:
        return comparator(left, right)
    except TypeError:
        # Comparar tipos incompatíveis devolve falso em vez de explodir: a
        # condição não é o lugar de descobrir erro de tipo, e derrubar a cena
        # por causa de uma comparação seria degradação pior que a informação.
        return False
