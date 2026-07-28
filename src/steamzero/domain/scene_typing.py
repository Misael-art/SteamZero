# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Gates de fechamento do modelo de valor: tipagem, contabilidade e diagnóstico.

O modelo de valor permite que qualquer propriedade receba qualquer origem. Isso
sozinho seria permissivo demais: nada impediria ``fontSize = asset("bg.png")``
ou um condicional cujo ramo verdadeiro é cor e o falso é imagem.

Este módulo fecha os seis gates exigidos antes de considerar o modelo pronto:

1. **Tipagem** — cada propriedade declara o tipo que aceita, e o valor precisa
   ser compatível independentemente da origem;
2. **Contabilidade** — toda propriedade da origem produz exatamente UM veredito;
   ``unaccounted`` é sempre zero ou a compilação falhou em contar algo;
3. **Fallback determinístico** — ordem fixa e detecção de ciclo;
4. **Namespaces** — caminho é chave lógica autorizada, nunca caminho físico;
5. **Compat legada** — ``boundText``/``boundImage`` normalizados na entrada;
6. **Diagnóstico com origem** — arquivo, linha, elemento e código estável.

O princípio que atravessa tudo: **uma propriedade que some sem veredito é pior
que uma propriedade recusada**, porque a segunda aparece no relatório e a
primeira não.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$")
_VENDOR = re.compile(r"^[a-z][a-zA-Z0-9]*(\.[a-zA-Z0-9]+)+$")


class ValueType(StrEnum):
    """Tipo que uma propriedade aceita.

    Existe para que a validação seja possível ANTES de renderizar: um tema com
    ``visible = translation(...)`` precisa falhar na compilação, não desenhar
    errado em silêncio.
    """

    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    COLOR = "color"
    DIMENSION = "dimension"
    MEDIA = "mediaReference"
    FONT = "fontReference"
    DURATION = "duration"
    ENUM = "enum"


class Category(StrEnum):
    """Categoria de propriedade, para fidelidade ser reportada por área.

    Uma fidelidade agregada de 89% esconde que a tipografia está em 0%. Separar
    é o que torna a métrica acionável.
    """

    LAYOUT = "layout"
    TYPOGRAPHY = "typography"
    COLOR = "color"
    MEDIA = "media"
    ANIMATION = "animation"
    AUDIO = "audio"
    NAVIGATION = "navigation"
    ACCESSIBILITY = "accessibility"
    EFFECTS = "effects"
    INTERACTION = "interaction"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SourceReference:
    """De onde a propriedade veio. Sem isto, um veredito é inauditável."""

    file: str
    line: int | None = None
    column: int | None = None
    element: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"file": self.file}
        if self.line is not None:
            payload["line"] = self.line
        if self.column is not None:
            payload["column"] = self.column
        if self.element:
            payload["element"] = self.element
        return payload

    def __str__(self) -> str:
        location = self.file
        if self.line is not None:
            location += f":{self.line}"
            if self.column is not None:
                location += f":{self.column}"
        return location


class TypeError_(ValueError):
    """Incompatibilidade entre o tipo da propriedade e o valor declarado."""


def _origin_of(value: Any) -> str:
    """Qual forma do modelo de valor este objeto é."""
    if not isinstance(value, dict):
        return "literal"
    for key in ("token", "bind", "asset", "text", "setting", "when"):
        if key in value:
            return {"text": "localized", "when": "conditional"}.get(key, key)
    return "unknown"


#: Origens cujo tipo só é conhecido em runtime. Não dá para checar estaticamente
#: um binding sem um registro de tipos do read model, então a checagem recai
#: sobre o ``fallback``, que o autor controla.
_DEFERRED = frozenset({"token", "bind", "setting"})


def check_type(value: Any, expected: ValueType, *, where: str = "valor") -> None:
    """Recusa valor incompatível com o tipo da propriedade.

    Origens diferidas (token, binding, configuração) são resolvidas pelo shell e
    não podem ser checadas aqui — mas o ``fallback`` declarado pelo autor pode, e
    é justamente ele que revela a intenção: quem escreve
    ``fontSize = bind("game.title", fallback="grande")`` está enganado sobre o
    tipo, e o fallback denuncia.
    """
    origin = _origin_of(value)

    if origin == "conditional":
        # Os dois ramos precisam ser do MESMO tipo. Um condicional que devolve
        # cor ou imagem conforme o estado é impossível de renderizar.
        check_type(value["then"], expected, where=f"{where}.then")
        if value.get("otherwise") is not None:
            check_type(value["otherwise"], expected, where=f"{where}.otherwise")
        return

    if origin in _DEFERRED:
        if isinstance(value, dict) and value.get("fallback") is not None:
            check_type(value["fallback"], expected, where=f"{where}.fallback")
        return

    if origin == "asset":
        if expected not in {ValueType.MEDIA, ValueType.FONT, ValueType.STRING}:
            raise TypeError_(f"{where}: asset não é compatível com {expected.value}")
        return

    if origin == "localized":
        if expected is not ValueType.STRING:
            raise TypeError_(f"{where}: tradução só produz texto, não {expected.value}")
        return

    _check_literal(value, expected, where)


def _check_literal(value: Any, expected: ValueType, where: str) -> None:
    if value is None:
        return
    if expected is ValueType.STRING:
        if not isinstance(value, str):
            raise TypeError_(f"{where}: esperado texto, veio {type(value).__name__}")
    elif expected in {ValueType.NUMBER, ValueType.DURATION}:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise TypeError_(f"{where}: esperado número, veio {type(value).__name__}")
    elif expected is ValueType.BOOLEAN:
        if not isinstance(value, bool):
            raise TypeError_(f"{where}: esperado booleano, veio {type(value).__name__}")
    elif expected is ValueType.COLOR:
        if not isinstance(value, str) or not _HEX_COLOR.match(value):
            raise TypeError_(f"{where}: cor precisa ser #RRGGBB ou #RRGGBBAA, veio {value!r}")
    elif expected is ValueType.DIMENSION:
        _check_dimension(value, where)
    elif expected in {ValueType.MEDIA, ValueType.FONT}:
        raise TypeError_(f"{where}: {expected.value} exige asset ou binding, não literal")


#: Palavras-chave de dimensão. Fórmula e expressão são deliberadamente ausentes:
#: dimensão calculada viraria linguagem executável.
_DIMENSION_KEYWORDS = frozenset({"auto", "center", "left", "right", "top", "bottom", "stretch"})


def _check_dimension(value: Any, where: str) -> None:
    if isinstance(value, bool):
        raise TypeError_(f"{where}: booleano não é dimensão")
    if isinstance(value, int | float):
        return
    if isinstance(value, str):
        if value in _DIMENSION_KEYWORDS:
            return
        if value.endswith("%"):
            try:
                float(value[:-1])
            except ValueError:
                raise TypeError_(f"{where}: percentual inválido: {value!r}") from None
            return
        raise TypeError_(f"{where}: dimensão desconhecida: {value!r}")
    raise TypeError_(f"{where}: dimensão precisa ser número, percentual ou palavra-chave")


#: Namespaces autorizados. `media.*` é reservado ao produto; extensões e recursos
#: privados de tema vivem em prefixos próprios, para que um tema não possa
#: reivindicar um caminho do sistema.
RESERVED_NAMESPACE = "media"
EXTENSION_PREFIX = "extension"
THEME_PREFIX = "theme"


def validate_path(path: str, *, theme_id: str | None = None) -> None:
    """Confere que um caminho é chave lógica autorizada, não caminho físico."""
    if not _VENDOR.match(path):
        raise ValueError(f"caminho inválido: {path!r}")
    if ".." in path or "/" in path or "\\" in path:
        raise ValueError(f"caminho não pode conter separador de arquivo: {path!r}")
    head = path.split(".", 1)[0]
    if head == EXTENSION_PREFIX:
        vendor = path.split(".")[1:2]
        if not vendor:
            raise ValueError(f"extensão sem vendor: {path!r}")
        return
    if head == THEME_PREFIX:
        declared = path.split(".")[1:2]
        if not declared:
            raise ValueError(f"recurso de tema sem identificador: {path!r}")
        if theme_id is not None and declared[0] != theme_id:
            # Um tema não lê o namespace privado de outro.
            raise ValueError(f"tema '{theme_id}' não pode acessar recurso de '{declared[0]}'")
        return


#: Ordem fixa de resolução. Determinismo importa: dois runs do mesmo tema
#: precisam escolher a mesma origem, senão bug de tema vira intermitente.
FALLBACK_ORDER = (
    "principal",
    "fallback declarado",
    "token padrão da propriedade",
    "valor padrão do componente",
    "valor seguro do shell",
)

MAX_FALLBACK_DEPTH = 8


def resolve_chain(value: Any, *, depth: int = 0, seen: frozenset[str] = frozenset()) -> list[str]:
    """Percorre a cadeia de fallback devolvendo os passos, detectando ciclo.

    Um token cujo fallback é ele mesmo, ou dois tokens que se referenciam,
    travariam a resolução em runtime. Detectar na compilação transforma um
    congelamento em erro de contrato.
    """
    if depth > MAX_FALLBACK_DEPTH:
        raise ValueError(f"cadeia de fallback excede {MAX_FALLBACK_DEPTH} níveis")
    if not isinstance(value, dict):
        return ["literal"]

    origin = _origin_of(value)
    marker = ""
    for key in ("token", "bind", "setting", "asset", "text"):
        if isinstance(value.get(key), str):
            marker = f"{key}:{value[key]}"
            break
    if marker and marker in seen:
        raise ValueError(f"ciclo de fallback em {marker}")

    steps = [origin]
    nested = value.get("fallback")
    if nested is not None:
        steps += resolve_chain(
            nested, depth=depth + 1, seen=seen | ({marker} if marker else frozenset())
        )
    return steps


@dataclass
class Accounting:
    """Contabilidade de propriedades: encontradas contra julgadas.

    O gate é ``unaccounted == 0``. Uma propriedade que a origem declarou e que
    não recebeu veredito não aparece em lugar nenhum — foi assim que 238
    ``fontColor`` sumiram sem ninguém notar.
    """

    found: int = 0
    judged: int = 0
    duplicates: list[str] = field(default_factory=list)
    _seen: set[str] = field(default_factory=set, repr=False)

    def observe(self, key: str) -> None:
        """Registra que a origem declarou esta propriedade."""
        self.found += 1

    def judge(self, key: str) -> None:
        """Registra que esta propriedade recebeu veredito.

        Veredito duplicado é defeito tão sério quanto ausente: significa que
        dois caminhos do compilador julgaram a mesma coisa e o relatório passa a
        somar mais que o total.
        """
        if key in self._seen:
            self.duplicates.append(key)
            return
        self._seen.add(key)
        self.judged += 1

    @property
    def unaccounted(self) -> int:
        return max(0, self.found - self.judged)

    @property
    def coverage(self) -> float:
        return 1.0 if self.found == 0 else round(self.judged / self.found, 4)

    @property
    def complete(self) -> bool:
        return self.unaccounted == 0 and not self.duplicates

    def to_dict(self) -> dict[str, Any]:
        return {
            "sourcePropertyCount": self.found,
            "translationVerdictCount": self.judged,
            "unaccounted": self.unaccounted,
            "duplicateVerdicts": list(self.duplicates),
            "accountingCoverage": self.coverage,
        }


#: Normalização dos tipos legados. Eles sobrevivem apenas no parser de entrada e
#: nunca chegam ao runtime como tipos independentes.
LEGACY_KINDS = {
    "boundText": ("text", True),
    "boundImage": ("image", True),
}


def normalize_legacy_kind(kind: str) -> tuple[str, bool]:
    """Converte tipo legado em (tipo canônico, tem binding)."""
    return LEGACY_KINDS.get(kind, (kind, False))
