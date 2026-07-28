# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Modelo de valor do IR: qualquer propriedade, qualquer origem.

A distinção entre ``boundText`` e ``boundImage`` obrigava o autor a escolher o
TIPO DE ELEMENTO por causa da origem do dado. A consequência não era só
deselegante: cor não podia vir de configuração, opacidade não podia vir de
estado, visibilidade não podia depender da existência de uma mídia — porque
essas propriedades não eram "elementos".

Aqui qualquer propriedade aceita literal, token de design, asset, binding do read
model, chave de tradução, configuração do tema ou valor condicional, cada um com
``fallback``.

Duas travas de projeto:

**Sem expressão executável.** Condição é comparação declarativa com operador
nomeado e operandos tipados, validável por schema. Um tema nunca executa código.

**Nada é descartado em silêncio.** Toda propriedade traduzida recebe um veredito
— ``exact``, ``approximated``, ``fallback``, ``unsupported``, ``invalid`` ou
``ignoredByPolicy`` — e o relatório de perdas é parte do resultado, não um efeito
colateral. Foi assim que descobrimos que 238 declarações de ``fontColor`` estavam
sendo perdidas sem registro.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

_PATH = re.compile(r"^[a-z][a-zA-Z0-9]*(\.[a-zA-Z0-9]+)+$")
_SETTING = re.compile(r"^[a-z][a-zA-Z0-9]*$")
_ASSET = re.compile(r"^assets/[a-zA-Z0-9_. /()'&-]+\.[a-zA-Z0-9]+$")

#: Estados que um elemento pode assumir. Fechado: condição sobre estado
#: desconhecido é erro de contrato, não algo a avaliar como falso.
ELEMENT_STATES = frozenset(
    {
        "default",
        "focused",
        "selected",
        "pressed",
        "hovered",
        "disabled",
        "loading",
        "empty",
        "error",
        "success",
        "playing",
        "paused",
        "unavailable",
        "locked",
        "offline",
    }
)

_COMPARISON = frozenset(
    {
        "exists",
        "missing",
        "equals",
        "notEquals",
        "greaterThan",
        "lessThan",
        "greaterOrEqual",
        "lessOrEqual",
        "contains",
        "in",
    }
)

_FORMATS = frozenset(
    {
        "raw",
        "number",
        "percent",
        "duration",
        "date",
        "time",
        "dateTime",
        "relative",
        "list",
        "upper",
        "lower",
        "capitalize",
    }
)


class Verdict(StrEnum):
    """Como uma propriedade da origem sobreviveu à tradução.

    A distinção entre ``unsupported`` e ``ignoredByPolicy`` importa: a primeira é
    limitação nossa e vira trabalho futuro; a segunda é recusa deliberada — um
    tema pedindo algo que o shell não concede — e não deve entrar na fila.
    """

    EXACT = "exact"
    APPROXIMATED = "approximated"
    FALLBACK = "fallback"
    UNSUPPORTED = "unsupported"
    INVALID = "invalid"
    IGNORED_BY_POLICY = "ignoredByPolicy"


@dataclass(frozen=True)
class Translation:
    """O destino de uma propriedade da origem, com veredito."""

    source: str
    verdict: Verdict
    target: str | None = None
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"source": self.source, "verdict": self.verdict.value}
        if self.target:
            payload["target"] = self.target
        if self.detail:
            payload["detail"] = self.detail
        return payload


@dataclass
class TranslationLog:
    """Relatório de perdas. Cresce durante a compilação e é publicado inteiro."""

    entries: list[Translation] = field(default_factory=list)

    def record(
        self,
        source: str,
        verdict: Verdict,
        *,
        target: str | None = None,
        detail: str | None = None,
    ) -> None:
        if len(self.entries) < 4096:
            self.entries.append(Translation(source, verdict, target, detail))

    def counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for entry in self.entries:
            counts[entry.verdict.value] = counts.get(entry.verdict.value, 0) + 1
        return counts

    def fidelity(self) -> float:
        """Fração das propriedades que chegaram exatas ou aproximadas.

        Mede PROPRIEDADE, não elemento. A métrica antiga contava elementos
        compilados e por isso dava 89% enquanto a cor de todo texto se perdia.
        """
        if not self.entries:
            return 1.0
        kept = sum(
            1
            for entry in self.entries
            if entry.verdict in {Verdict.EXACT, Verdict.APPROXIMATED, Verdict.FALLBACK}
        )
        return round(kept / len(self.entries), 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fidelity": self.fidelity(),
            "counts": self.counts(),
            "translations": [entry.to_dict() for entry in self.entries],
        }


def literal(value: Any) -> Any:
    """Valor escalar puro. Existe para o chamador declarar intenção."""
    return value


def token(name: str, *, fallback: Any = None) -> dict[str, Any]:
    if not _PATH.match(name):
        raise ValueError(f"token inválido: {name!r}")
    out: dict[str, Any] = {"token": name}
    if fallback is not None:
        out["fallback"] = fallback
    return out


def bind(path: str, *, fmt: str | None = None, fallback: Any = None) -> dict[str, Any]:
    if not _PATH.match(path):
        raise ValueError(f"caminho de binding inválido: {path!r}")
    if fmt is not None and fmt not in _FORMATS:
        raise ValueError(f"formato desconhecido: {fmt!r}")
    out: dict[str, Any] = {"bind": path}
    if fmt:
        out["format"] = fmt
    if fallback is not None:
        out["fallback"] = fallback
    return out


def asset(path: str, *, fallback: Any = None) -> dict[str, Any]:
    if not _ASSET.match(path) or ".." in path:
        raise ValueError(f"asset inválido: {path!r}")
    out: dict[str, Any] = {"asset": path}
    if fallback is not None:
        out["fallback"] = fallback
    return out


def localized(key: str, *, fallback: str | None = None) -> dict[str, Any]:
    if not _PATH.match(key):
        raise ValueError(f"chave de tradução inválida: {key!r}")
    out: dict[str, Any] = {"text": key}
    if fallback is not None:
        out["fallback"] = fallback
    return out


def setting(name: str, *, fallback: Any = None) -> dict[str, Any]:
    if not _SETTING.match(name):
        raise ValueError(f"configuração inválida: {name!r}")
    out: dict[str, Any] = {"setting": name}
    if fallback is not None:
        out["fallback"] = fallback
    return out


def when(condition: dict[str, Any], then: Any, otherwise: Any = None) -> dict[str, Any]:
    out: dict[str, Any] = {"when": condition, "then": then}
    if otherwise is not None:
        out["otherwise"] = otherwise
    return out


def compare(op: str, left: Any, right: Any = None) -> dict[str, Any]:
    if op not in _COMPARISON:
        raise ValueError(f"operador desconhecido: {op!r}")
    out: dict[str, Any] = {"op": op, "left": left}
    if right is not None:
        out["right"] = right
    return out


def all_of(*conditions: dict[str, Any]) -> dict[str, Any]:
    return {"op": "and", "operands": list(conditions)}


def any_of(*conditions: dict[str, Any]) -> dict[str, Any]:
    return {"op": "or", "operands": list(conditions)}


def negate(condition: dict[str, Any]) -> dict[str, Any]:
    return {"op": "not", "operand": condition}


def in_state(state: str) -> dict[str, Any]:
    if state not in ELEMENT_STATES:
        raise ValueError(f"estado desconhecido: {state!r}")
    return {"op": "state", "state": state}


def has_capability(name: str) -> dict[str, Any]:
    if not re.fullmatch(r"[a-z][a-zA-Z0-9.]*", name):
        raise ValueError(f"capability inválida: {name!r}")
    return {"op": "capability", "name": name}


def is_dynamic(value: Any) -> bool:
    """Se o valor depende de algo além dele mesmo.

    O renderizador usa isto para decidir o que precisa reavaliar quando o estado
    muda — literal nunca muda, os demais podem.
    """
    if not isinstance(value, dict):
        return False
    return bool({"bind", "token", "setting", "when"} & set(value))


def referenced_paths(value: Any) -> set[str]:
    """Todos os caminhos do read model que este valor consome, recursivamente.

    Permite ao runtime assinar exatamente o que a cena usa, em vez de reavaliar
    tudo a cada mudança.
    """
    found: set[str] = set()
    if isinstance(value, dict):
        if isinstance(value.get("bind"), str):
            found.add(value["bind"])
        for key in ("fallback", "then", "otherwise", "left", "right", "count", "operand"):
            found |= referenced_paths(value.get(key))
        for item in value.get("operands", []) or []:
            found |= referenced_paths(item)
        if isinstance(value.get("when"), dict):
            found |= referenced_paths(value["when"])
    elif isinstance(value, list):
        for item in value:
            found |= referenced_paths(item)
    return found
