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

import threading
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any

from steamzero.domain.scene_contract import DimensionUnit, DimensionValue
from steamzero.domain.scene_display import DISPLAY_FIELDS, DisplaySpec
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
    #: Caixa de referência para percentuais. Entra como VALOR, não como
    #: contador: 1920 → 1280 → 1920 precisa devolver o resultado original, e um
    #: contador monotônico faria a terceira medida parecer diferente da
    #: primeira.
    reference_width: float = 1920.0
    reference_height: float = 1080.0
    #: Gerações do display, POR EIXO. Uma janela que muda de 1920x1080 para
    #: 1280x1080 mudou só a largura; invalidar quem depende da altura junto
    #: recomputaria metade da cena por nada. Safe area por lado segue o mesmo
    #: princípio: um entalhe novo num lado não derruba quem só lê o outro.
    display_width: int = 0
    display_height: int = 0
    display_dpr: int = 0
    display_orientation: int = 0
    safe_area_left: int = 0
    safe_area_top: int = 0
    safe_area_right: int = 0
    safe_area_bottom: int = 0

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

    def fingerprint(self, dependencies: frozenset[str]) -> tuple[Any, ...]:
        """Só as gerações que ESTAS dependências usam.

        Uma propriedade sem dependência nenhuma tem impressão vazia: continua
        válida por qualquer mudança de geração, porque nada que mudou a alcança.
        O tema entra sempre — recarregar o tema troca o documento inteiro.
        """
        names: set[str] = {"theme"}
        for dependency in dependencies:
            specific = LAYOUT_DEPENDENCIES.get(dependency)
            if specific is not None:
                names.update(specific)
                continue
            specific = DISPLAY_DEPENDENCIES.get(dependency)
            if specific is not None:
                names.update(specific)
                continue
            kind = dependency.split(":", 1)[0]
            names.update(GENERATION_BY_KIND.get(kind, ()))
        return tuple(sorted((name, getattr(self, name)) for name in names))


#: Qual geração governa cada tipo de dependência.
#:
#: É o que permite a chave de cache olhar SÓ o que a propriedade usa. Sem isto,
#: a chave inclui todas as gerações e um bump em `tokens` torna inalcançável o
#: cache de toda propriedade da cena — inclusive as que só têm literais. Uma
#: mudança de cor recompunha as 65 propriedades da fixture.
GENERATION_BY_KIND: dict[str, tuple[str, ...]] = {
    "token": ("tokens",),
    "bind": ("read_model",),
    "setting": ("theme_settings",),
    "i18n": ("translation_catalog", "locale"),
    "asset": ("asset_registry",),
    "state": ("state_variant",),
    "capability": ("theme",),
    "display": ("display",),
    "a11y": ("accessibility",),
}

#: Dependências de layout, com geração POR EIXO.
#:
#: Separar os eixos não é refinamento: uma janela que muda de 1920x1080 para
#: 1280x1080 mudou só a largura, e invalidar as alturas percentuais junto
#: recomputaria metade da cena por nada. A chave é o caminho completo, não o
#: prefixo, porque `layout:` sozinho não distinguiria os eixos.
LAYOUT_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "layout:referenceWidth": ("reference_width",),
    "layout:referenceHeight": ("reference_height",),
}

#: Dependências do display, com geração POR EIXO e POR CAMPO.
#:
#: O `aspectRatio` depende dos DOIS eixos: mudar a largura ou a altura altera a
#: proporção. Os demais campos têm geração própria — dpr, orientação e cada
#: lado de safe area invalidam SÓ quem os lê. O vocabulário é o mesmo de
#: ``scene_display.DISPLAY_FIELDS``, travado lá e derivado daqui para o registro.
DISPLAY_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "display:width": ("display_width",),
    "display:height": ("display_height",),
    "display:aspectRatio": ("display_width", "display_height"),
    "display:dpr": ("display_dpr",),
    "display:orientation": ("display_orientation",),
    "display:safeArea.left": ("safe_area_left",),
    "display:safeArea.top": ("safe_area_top",),
    "display:safeArea.right": ("safe_area_right",),
    "display:safeArea.bottom": ("safe_area_bottom",),
}


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
    display: DisplaySpec = field(default_factory=DisplaySpec)


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

    def record(self, target: str, dependencies: frozenset[str]) -> int:
        """Atualiza as arestas do alvo. Devolve quantas foram REMOVIDAS.

        Remover as antigas é o que impede aresta órfã. Sem isso, uma propriedade
        que trocou de `token A` para `token B` continuaria sendo invalidada por
        A para sempre — recomputação inútil que cresce a cada mudança de tema.
        """
        previous = self._dependencies.get(target, frozenset())
        removed = previous - dependencies
        for gone in removed:
            dependents = self._dependents.get(gone)
            if dependents is None:
                continue
            dependents.discard(target)
            if not dependents:
                # Chave vazia mantida faria o grafo crescer monotonicamente ao
                # longo de ciclos de carga e descarga.
                del self._dependents[gone]
        for added in dependencies - previous:
            self._dependents.setdefault(added, set()).add(target)
        self._dependencies[target] = dependencies
        return len(removed)

    def forget(self, target: str) -> int:
        """Remove o alvo e todas as arestas que apontam para ele."""
        previous = self._dependencies.pop(target, frozenset())
        for gone in previous:
            dependents = self._dependents.get(gone)
            if dependents is None:
                continue
            dependents.discard(target)
            if not dependents:
                del self._dependents[gone]
        return len(previous)

    @property
    def edge_count(self) -> int:
        return sum(len(targets) for targets in self._dependents.values())

    @property
    def targets(self) -> frozenset[str]:
        return frozenset(self._dependencies)

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

    Há DUAS coleções, e a distinção é o ponto:

    ``entries`` é histórico. Serve ao relatório de importação, e apagar dali
    perderia a informação de que uma fonte esteve ausente durante a conversão.

    ``active`` é o estado AGORA. Quando a fonte é instalada e a propriedade é
    reavaliada com sucesso, o aviso sai daqui. Sem essa separação, ou o painel
    mostra para sempre um problema já corrigido, ou o relatório perde o que
    aconteceu na importação. Os dois são ruins e são o mesmo bug.
    """

    entries: list[Diagnostic] = field(default_factory=list)
    _seen: set[tuple[Any, ...]] = field(default_factory=set, repr=False)
    _active: dict[tuple[str, str], Diagnostic] = field(default_factory=dict, repr=False)

    def emit(self, diagnostic: Diagnostic, generation: tuple[Any, ...]) -> bool:
        self._active[(diagnostic.code, diagnostic.target)] = diagnostic
        key = (diagnostic.code, diagnostic.target, generation)
        if key in self._seen:
            return False
        self._seen.add(key)
        self.entries.append(diagnostic)
        return True

    def resolve_target(self, target: str) -> tuple[Diagnostic, ...]:
        """A propriedade foi reavaliada com sucesso: seus avisos saem do ativo.

        O histórico não é tocado. Um aviso que sobrevive à correção treina quem
        olha o painel a ignorar avisos.
        """
        gone = tuple(item for (_code, key), item in self._active.items() if key == target)
        for code, key in [pair for pair in self._active if pair[1] == target]:
            del self._active[(code, key)]
        return gone

    def clear_active(self) -> None:
        """Descarrega o estado atual, preservando o histórico."""
        self._active.clear()

    @property
    def active(self) -> tuple[Diagnostic, ...]:
        return tuple(self._active.values())

    def to_list(self) -> list[dict[str, Any]]:
        return [entry.to_dict() for entry in self.entries]


@dataclass
class ResolverStats:
    """Contadores para provar que o cache funciona.

    Existem para que o teste possa afirmar o CONJUNTO exato de propriedades
    recomputadas, e não apenas `recomputed > 0`. Um orçamento frouxo passaria
    mesmo se a implementação recomputasse a cena inteira.
    """

    hits: int = 0
    misses: int = 0
    invalidations: int = 0
    resolved: int = 0
    recomputed: int = 0
    removed_dependencies: int = 0
    forgotten_targets: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "cacheHits": self.hits,
            "cacheMisses": self.misses,
            "invalidatedProperties": self.invalidations,
            "resolvedProperties": self.resolved,
            "recomputedProperties": self.recomputed,
            "removedDependencies": self.removed_dependencies,
            "forgottenTargets": self.forgotten_targets,
        }


class Resolver:
    """Resolve valores com cache e invalidação por dependência."""

    #: Política de concorrência, declarada em vez de deixada ambígua.
    #:
    #: O resolver é CONFINADO A UMA THREAD. Não há trava, e o cache, o grafo e
    #: os diagnósticos são mutados sem sincronização. Uma resolução em outra
    #: thread poderia observar metade de uma atualização de gerações — meia cena
    #: nova, meia velha, sem erro nenhum. O shell serializa as chamadas.
    THREAD_POLICY = "single-thread confined"

    def __init__(self, context: ResolutionContext) -> None:
        self._context = context
        self._cache: dict[tuple[Any, ...], Resolved] = {}
        #: Impressão de geração de cada entrada. Guardada ao lado, e não na
        #: chave, porque a chave precisa ser encontrável ANTES de sabermos quais
        #: dependências a entrada tem.
        self._fingerprints: dict[tuple[Any, ...], tuple[Any, ...]] = {}
        #: A EXPRESSÃO que produziu cada entrada. Sem isto, trocar
        #: `title.color` de um token para outro servia o valor antigo: a chave é
        #: (tema, alvo), e o alvo não mudou. Depender de quem chama lembrar de
        #: bumpar a geração é contrato implícito, e contrato implícito é o que
        #: produz tela desatualizada sem ninguém saber por quê.
        self._expressions: dict[tuple[Any, ...], Any] = {}
        self.graph = DependencyGraph()
        self.stats = ResolverStats()
        self.diagnostics = DiagnosticSink()
        self._owner_thread = threading.get_ident()
        self._batch_depth = 0
        self._batched: set[str] = set()

    def _assert_owner_thread(self) -> None:
        """Impede uso acidental em outra thread.

        Documentar a política não basta: o defeito que ela evita — meia
        atualização observada — não levanta exceção, produz uma cena
        parcialmente atualizada que parece certa.
        """
        if threading.get_ident() != self._owner_thread:
            raise RuntimeError(
                f"Resolver é {self.THREAD_POLICY}: criado na thread "
                f"{self._owner_thread}, usado na {threading.get_ident()}"
            )

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
        self._assert_owner_thread()
        # A identidade do tema entra na CHAVE, não só na impressão: dois temas
        # podem declarar o mesmo `gameTitle.color`, e sem isto o segundo serviria
        # o valor do primeiro.
        cache_key = (self._context.theme_id, target)
        cached = self._cache.get(cache_key)
        if cached is not None and self._expressions.get(cache_key) == value:
            expected_fingerprint = self._context.generations.fingerprint(cached.dependencies)
            if self._fingerprints.get(cache_key) == expected_fingerprint:
                self.stats.hits += 1
                return cached
            # A entrada existe mas envelheceu numa geração que ela realmente
            # usa. Recomputar; a que não usa aquela geração continua servindo.
            self.stats.recomputed += 1

        self.stats.misses += 1
        self.stats.resolved += 1
        dependencies: set[str] = set()
        phase = ResolutionPhase.COMPILE_TIME
        resolved_value, used_fallback, phase = self._resolve(
            value, expected, dependencies, (), reference, target
        )
        result = Resolved(resolved_value, frozenset(dependencies), phase, used_fallback)
        if not used_fallback:
            # Resolveu de verdade: o que estava avisado sobre esta propriedade
            # deixa de valer. Sem isto, instalar a fonte faltante corrigiria a
            # tela e o painel continuaria acusando o problema.
            self.diagnostics.resolve_target(target)
        self._cache[cache_key] = result
        self._expressions[cache_key] = value
        self._fingerprints[cache_key] = self._context.generations.fingerprint(result.dependencies)
        self.stats.removed_dependencies += self.graph.record(target, result.dependencies)
        return result

    def invalidate(self, dependency: str) -> frozenset[str]:
        """Descarta o cache dos alvos que dependem de ``dependency``.

        Devolve o conjunto invalidado, para que o chamador possa provar que uma
        mudança localizada não derrubou a cena inteira.
        """
        self._assert_owner_thread()
        affected = self.graph.dependents_of(dependency)
        if not affected:
            return frozenset()
        if self._batch_depth:
            # Em lote, a invalidação é acumulada e aplicada uma vez no commit.
            # Sem isto, mudar token, locale e read model na mesma operação
            # recomputaria a mesma propriedade três vezes, e o usuário veria
            # estados intermediários.
            self._batched |= affected
            return affected
        self._drop(affected)
        return affected

    def _drop(self, targets: frozenset[str]) -> None:
        for key in [key for key in self._cache if key[1] in targets]:
            del self._cache[key]
            self._fingerprints.pop(key, None)
            self._expressions.pop(key, None)
        self.stats.invalidations += len(targets)

    @contextmanager
    def batch(self) -> Iterator[None]:
        """Agrupa invalidações. Cada alvo é descartado no máximo uma vez.

        O ganho não é só desempenho: sem agrupar, uma troca de tema que mexe em
        quatro origens faria a cena passar por estados parcialmente atualizados,
        e alguém veria o texto novo com a cor velha.
        """
        self._assert_owner_thread()
        self._batch_depth += 1
        try:
            yield
        finally:
            self._batch_depth -= 1
            if self._batch_depth == 0 and self._batched:
                self._drop(frozenset(self._batched))
                self._batched.clear()

    def forget(self, target: str) -> None:
        """Esquece uma propriedade: cache, impressão e arestas.

        Elemento removido que continua no grafo é recomputação de algo que não
        existe mais, e o grafo cresce a cada ciclo de carga e descarga.
        """
        self._assert_owner_thread()
        key = (self._context.theme_id, target)
        self._cache.pop(key, None)
        self._fingerprints.pop(key, None)
        self._expressions.pop(key, None)
        self.stats.removed_dependencies += self.graph.forget(target)
        self.stats.forgotten_targets += 1

    def forget_prefix(self, prefix: str) -> frozenset[str]:
        """Esquece um agrupamento inteiro — uma view, por exemplo."""
        self._assert_owner_thread()
        targets = frozenset(item for item in self.graph.targets if item.startswith(prefix))
        for target in targets:
            self.forget(target)
        return targets

    def forget_theme(self) -> None:
        """Descarrega tudo do tema atual.

        Recarregar o mesmo `themeId` com conteúdo diferente NÃO pode reutilizar
        nada por coincidência de chave: a geração `theme` muda, mas a certeza
        vem de esquecer, não de inferir.
        """
        self._assert_owner_thread()
        for target in list(self.graph.targets):
            self.forget(target)
        self._cache.clear()
        self._fingerprints.clear()
        self._expressions.clear()
        self.diagnostics.clear_active()

    def set_reference_box(self, width: float, height: float) -> frozenset[str]:
        """Declara a caixa de referência. Devolve o que foi invalidado.

        Mudar a largura invalida SÓ quem depende da largura. Uma janela que vai
        de 1920x1080 para 1280x1080 mudou um eixo; recomputar as alturas
        percentuais junto seria metade da cena por nada.
        """
        self._assert_owner_thread()
        current = self._context.generations
        if current.reference_width == width and current.reference_height == height:
            return frozenset()
        affected: set[str] = set()
        if current.reference_width != width:
            affected |= self.graph.dependents_of("layout:referenceWidth")
        if current.reference_height != height:
            affected |= self.graph.dependents_of("layout:referenceHeight")
        self._context.generations = replace(current, reference_width=width, reference_height=height)
        if affected and not self._batch_depth:
            self._drop(frozenset(affected))
        elif affected:
            self._batched |= affected
        return frozenset(affected)

    def set_display(self, spec: DisplaySpec) -> frozenset[str]:
        """Troca o display. Devolve o que foi invalidado.

        Campo a campo, como o ``set_reference_box``: rotação muda orientação e
        safe areas; trocar o dpr não muda tamanho; mudar a largura não pode
        derrubar quem só lê a altura. ``aspectRatio`` depende dos dois eixos e
        é invalidado por qualquer mudança de tamanho.
        """
        self._assert_owner_thread()
        current = self._context.generations
        current_spec = self._context.display
        if spec == current_spec:
            return frozenset()

        updates: set[str] = set()
        affected: set[str] = set()

        def _mark(dependency: str, attribute: str) -> None:
            nonlocal affected
            updates.add(attribute)
            affected |= self.graph.dependents_of(dependency)

        if spec.logical_width != current_spec.logical_width:
            _mark("display:width", "display_width")
            affected |= self.graph.dependents_of("display:aspectRatio")
        if spec.logical_height != current_spec.logical_height:
            _mark("display:height", "display_height")
            affected |= self.graph.dependents_of("display:aspectRatio")
        if spec.dpr != current_spec.dpr:
            _mark("display:dpr", "display_dpr")
        if spec.orientation is not current_spec.orientation:
            _mark("display:orientation", "display_orientation")
        for side, attribute, dependency in (
            ("left", "safe_area_left", "display:safeArea.left"),
            ("top", "safe_area_top", "display:safeArea.top"),
            ("right", "safe_area_right", "display:safeArea.right"),
            ("bottom", "safe_area_bottom", "display:safeArea.bottom"),
        ):
            if getattr(spec.safe_area, side) != getattr(current_spec.safe_area, side):
                _mark(dependency, attribute)

        display_marker = (
            f"{spec.logical_width:g}x{spec.logical_height:g}@{spec.dpr:g}/{spec.orientation.value}"
        )
        self._context.generations = Generations(
            theme=current.theme,
            theme_settings=current.theme_settings,
            tokens=current.tokens,
            read_model=current.read_model,
            translation_catalog=current.translation_catalog,
            asset_registry=current.asset_registry,
            locale=current.locale,
            accessibility=current.accessibility,
            display=display_marker,
            state_variant=current.state_variant,
            reference_width=current.reference_width,
            reference_height=current.reference_height,
            display_width=current.display_width + ("display_width" in updates),
            display_height=current.display_height + ("display_height" in updates),
            display_dpr=current.display_dpr + ("display_dpr" in updates),
            display_orientation=current.display_orientation + ("display_orientation" in updates),
            safe_area_left=current.safe_area_left + ("safe_area_left" in updates),
            safe_area_top=current.safe_area_top + ("safe_area_top" in updates),
            safe_area_right=current.safe_area_right + ("safe_area_right" in updates),
            safe_area_bottom=current.safe_area_bottom + ("safe_area_bottom" in updates),
        )
        self._context.display = spec
        if affected and not self._batch_depth:
            self._drop(frozenset(affected))
        elif affected:
            self._batched |= affected
        return frozenset(affected)

    def resolve_dimension(
        self,
        dimension: Any,
        *,
        axis: str,
        target: str,
        default: float = 0.0,
    ) -> Any:
        """Converte uma dimensão para pixel lógico, REGISTRANDO a dependência.

        É a ponte que faltava. A conversão de percentual já consumia a caixa de
        referência, mas fora do grafo — então trocar a resolução deixava o
        layout stale sem que nada invalidasse. A dependência é real porque o
        resultado muda; registrá-la é o que torna a invalidação possível.

        Devolve ``None`` para ``auto``: dimensão implícita não é zero.
        """
        self._assert_owner_thread()
        if axis not in {"width", "height"}:
            raise ValueError(f"eixo desconhecido: {axis!r}")
        marker = "layout:referenceWidth" if axis == "width" else "layout:referenceHeight"
        extent = (
            self._context.generations.reference_width
            if axis == "width"
            else self._context.generations.reference_height
        )

        cache_key = (self._context.theme_id, target)
        cached = self._cache.get(cache_key)
        if (
            cached is not None
            and self._expressions.get(cache_key) == dimension
            and self._fingerprints.get(cache_key)
            == self._context.generations.fingerprint(cached.dependencies)
        ):
            self.stats.hits += 1
            return cached.value

        self.stats.misses += 1
        self.stats.resolved += 1
        dependencies: set[str] = set()
        if dimension is None:
            pixels: Any = default
        elif isinstance(dimension, DimensionValue):
            if dimension.unit is DimensionUnit.AUTO:
                pixels = None
            elif dimension.unit is DimensionUnit.PERCENT:
                # SÓ o percentual depende da caixa. Uma dimensão em pixel lógico
                # não muda com a resolução, e registrar a dependência nela
                # recomputaria a cena inteira a cada troca de display.
                dependencies.add(marker)
                pixels = round(extent * (dimension.value or 0.0) / 100.0, 4)
            else:
                pixels = float(dimension.value or 0.0)
        elif isinstance(dimension, int | float) and not isinstance(dimension, bool):
            pixels = float(dimension)
        else:
            pixels = default

        result = Resolved(pixels, frozenset(dependencies), ResolutionPhase.LOAD_TIME)
        self._cache[cache_key] = result
        self._expressions[cache_key] = dimension
        self._fingerprints[cache_key] = self._context.generations.fingerprint(result.dependencies)
        self.stats.removed_dependencies += self.graph.record(target, result.dependencies)
        return pixels

    @property
    def active_cache_entries(self) -> int:
        return len(self._cache)

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

        if path.startswith("display."):
            return self._resolve_display(
                value, path, expected, dependencies, trail, reference, target
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

    def _resolve_display(
        self,
        value: dict[str, Any],
        path: str,
        expected: ValueType,
        dependencies: set[str],
        trail: tuple[str, ...],
        reference: SourceReference | None,
        target: str,
    ) -> tuple[Any, bool, ResolutionPhase]:
        """Bindings ``display.*``: estado do display, com geração POR CAMPO.

        Não passam pelo read model — descrevem o display, não o jogo — e
        invalidam pela geração do campo (largura, altura, dpr, orientação,
        safe area por lado) em vez de pela geração geral do read model. A
        dependência registrada é ``display:<campo>``, que ``DISPLAY_DEPENDENCIES``
        mapeia para a geração exata.
        """
        field = path.removeprefix("display.")
        spec_field = DISPLAY_FIELDS.get(field)
        if spec_field is None:
            return self._fallback_or_fail(
                value,
                expected,
                dependencies,
                trail,
                reference,
                target,
                DIAG_UNKNOWN_BINDING,
                f"campo de display desconhecido: {field}",
            )
        declared_type, getter = spec_field
        if expected is not declared_type:
            # Segunda linha de defesa: o registro de tipos é a primeira, mas um
            # Registries montado à mão pode não declarar o caminho.
            raise ResolutionError(
                DIAG_TYPE,
                f"display.{field} produz {declared_type.value}, mas {expected.value} era esperado",
                reference=reference,
            )
        dependencies.add(f"display:{field}")
        return getter(self._context.display), False, ResolutionPhase.RUNTIME

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
            # Registrar a dependência é obrigatório. Enquanto a chave de cache
            # continha TODAS as gerações, a ausência daqui era mascarada: trocar
            # de estado invalidava tudo, inclusive isto. Com invalidação
            # seletiva, uma condição de estado sem dependência serviria valor
            # stale — o item continuaria pintado como focado depois de perder o
            # foco.
            name = str(condition["state"])
            dependencies.add(f"state:{name}")
            return _truth(name in self._context.states)
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
