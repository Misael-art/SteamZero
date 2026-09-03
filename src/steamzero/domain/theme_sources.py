# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Catálogo curado de temas ES-DE, fixado por commit.

Isto **não** é o marketplace. ``theme_marketplace`` fala com um catálogo remoto
que o operador registra, e nasce desligado de propósito. Aqui o catálogo é
embutido, versionado junto com o código e revisável em diff — o que é a única
forma honesta de afirmar "estes temas foram conferidos".

**Fixado por commit, não por ramo.** Um ramo move; um commit é o próprio hash do
conteúdo, garantido pelo git. Isso torna a aquisição reprodutível e faz o
conteúdo mudar somente quando alguém atualiza este arquivo — e a mudança aparece
na revisão em vez de acontecer sozinha entre dois downloads.

**Licença é gate, não metadado.** Quatro dos nove temas pedidos em 2026-09-03
ficaram de fora por não declararem licença nenhuma. Distribuir arte de terceiro
sem licença confirmada não é decisão que um catálogo curado pode tomar em
silêncio, e a exclusão fica registrada no próprio arquivo, com o motivo.

CC-BY-NC-SA exige **atribuição**, e três dos cinco temas são obras derivadas com
cadeia de crédito própria. Daí ``credits`` ser uma lista e não um autor só:
publicar apenas o dono do repositório apagaria quem fez o trabalho original.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from steamzero.core.errors import SteamZeroError

#: Forges de onde o catálogo aceita buscar, com o molde de tarball de cada uma.
#: Fechado por construção: um endereço fora daqui não é alcançável nem se
#: aparecer no arquivo, o que mantém a superfície de supply chain enumerável.
_FORGES = {
    "github": "https://codeload.github.com/{repo}/tar.gz/{commit}",
    "gitlab": "https://gitlab.com/{repo}/-/archive/{commit}/{archive}.tar.gz",
}
_FORGE_HOSTS = {"github": "codeload.github.com", "gitlab": "gitlab.com"}

_THEME_ID = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)+$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_REPO = re.compile(r"^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+$")

#: Fora de ``themes/``, que é custódia do SZ-AURA-UI: um catálogo de origens
#: ES-DE não pertence ao tema nativo, e misturá-los faria cada mudança aqui
#: alterar o escopo daquela capacidade (AGENTS §10).
_CATALOG_PATH = Path(__file__).resolve().parent.parent / "catalogs" / "esde-sources-v1.json"


@dataclass(frozen=True)
class ThemeSource:
    """Uma origem curada, pronta para aquisição."""

    id: str
    name: str
    family: str
    author: str
    credits: tuple[str, ...]
    license_id: str
    license_source: str
    homepage: str
    forge: str
    repo: str
    commit: str

    @property
    def archive_url(self) -> str:
        """Endereço do tarball no commit fixado."""
        return _FORGES[self.forge].format(
            repo=self.repo,
            commit=self.commit,
            archive=self.repo.rsplit("/", 1)[-1],
        )

    @property
    def host(self) -> str:
        return _FORGE_HOSTS[self.forge]

    @property
    def root_prefix_components(self) -> int:
        """Quantos componentes de caminho o tarball embrulha (sempre 1 nas duas
        forges: ``<repo>-<commit>/``)."""
        return 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "family": self.family,
            "author": self.author,
            "credits": list(self.credits),
            "license": self.license_id,
            "homepage": self.homepage,
            "forge": self.forge,
            "repo": self.repo,
            "commit": self.commit,
        }


@dataclass(frozen=True)
class ExcludedSource:
    """Tema conhecido e deliberadamente fora, com o motivo.

    Registrar a exclusão evita que alguém reintroduza o mesmo tema meses depois
    sem saber por que ele saiu — e evita que a ausência pareça esquecimento.
    """

    repo: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {"repo": self.repo, "reason": self.reason}


@dataclass(frozen=True)
class SourceCatalog:
    entries: tuple[ThemeSource, ...] = field(default_factory=tuple)
    excluded: tuple[ExcludedSource, ...] = field(default_factory=tuple)

    def get(self, theme_id: str) -> ThemeSource:
        for entry in self.entries:
            if entry.id == theme_id:
                return entry
        raise SteamZeroError(
            "E-THEME-NOT-FOUND",
            detail=f"tema '{theme_id}' não está no catálogo curado",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "entries": [entry.to_dict() for entry in self.entries],
            "excluded": [item.to_dict() for item in self.excluded],
        }


def _require(raw: dict[str, Any], key: str, pattern: re.Pattern[str] | None = None) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SteamZeroError(
            "E-THEME-CATALOG-FAILED",
            detail=f"entrada de catálogo sem '{key}'",
        )
    value = value.strip()
    if pattern is not None and not pattern.match(value):
        raise SteamZeroError(
            "E-THEME-CATALOG-FAILED",
            detail=f"campo '{key}' fora do formato esperado: {value!r}",
        )
    return value


def _source_from_dict(raw: dict[str, Any]) -> ThemeSource:
    source = raw.get("source")
    if not isinstance(source, dict):
        raise SteamZeroError("E-THEME-CATALOG-FAILED", detail="entrada sem bloco 'source'")
    forge = _require(source, "forge")
    if forge not in _FORGES:
        raise SteamZeroError(
            "E-THEME-CATALOG-FAILED",
            detail=f"forge não suportada: {forge!r}; conhecidas: {sorted(_FORGES)}",
        )
    license_id = _require(raw, "license")
    raw_credits = raw.get("credits")
    credits = tuple(str(item) for item in raw_credits) if isinstance(raw_credits, list) else ()
    return ThemeSource(
        id=_require(raw, "id", _THEME_ID),
        name=_require(raw, "name"),
        family=_require(raw, "family"),
        author=_require(raw, "author"),
        # CC-BY-NC-SA exige atribuição; sem crédito o autor vira o único crédito.
        credits=credits or (_require(raw, "author"),),
        license_id=license_id,
        license_source=str(raw.get("licenseSource", "")),
        homepage=str(raw.get("homepage", "")),
        forge=forge,
        repo=_require(source, "repo", _REPO),
        commit=_require(source, "commit", _COMMIT),
    )


@lru_cache(maxsize=1)
def bundled() -> SourceCatalog:
    """Lê o catálogo embutido. Um arquivo inválido é erro, não catálogo vazio.

    Devolver vazio faria a superfície de temas simplesmente sumir, e uma lista
    vazia é indistinguível de "nenhum tema disponível" — o usuário veria ausência
    onde houve defeito.
    """
    try:
        raw = json.loads(_CATALOG_PATH.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise SteamZeroError(
            "E-THEME-CATALOG-FAILED",
            detail=f"catálogo curado ilegível em {_CATALOG_PATH.name}: {exc}",
        ) from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("entries"), list):
        raise SteamZeroError("E-THEME-CATALOG-FAILED", detail="catálogo curado sem lista 'entries'")

    entries = tuple(_source_from_dict(item) for item in raw["entries"] if isinstance(item, dict))
    identifiers = [entry.id for entry in entries]
    duplicates = {value for value in identifiers if identifiers.count(value) > 1}
    if duplicates:
        raise SteamZeroError(
            "E-THEME-CATALOG-FAILED",
            detail=f"identificador repetido no catálogo: {sorted(duplicates)}",
        )
    raw_excluded = raw.get("excluded")
    excluded = tuple(
        ExcludedSource(repo=str(item.get("repo", "")), reason=str(item.get("reason", "")))
        for item in (raw_excluded if isinstance(raw_excluded, list) else [])
        if isinstance(item, dict)
    )
    return SourceCatalog(entries=entries, excluded=excluded)
