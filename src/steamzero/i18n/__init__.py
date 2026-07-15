# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""i18n: catálogo de mensagens com chaves estáveis (Q7 — pt-BR primário).

Uso: ``t("error.E-TX-STALE-PLAN.title")`` ou com interpolação
``t("error.E-CONTENT-BIOS-MISSING.what", file="scph1001.bin", platform="psx",
emulator="DuckStation")``.

Regras (CONTENT-POLICY §Aplicação técnica): mensagens de conteúdo ausente têm
texto fixo auditado — nunca interpolam sugestões de download; a interpolação
serve apenas para parâmetros operacionais (plataforma, emulador, arquivo).
"""

from __future__ import annotations

from .messages_pt_br import MESSAGES as _PT_BR

DEFAULT_LOCALE = "pt-BR"
AVAILABLE_LOCALES = ("pt-BR",)

_CATALOGS: dict[str, dict[str, str]] = {"pt-BR": _PT_BR}


def has_key(key: str, *, locale: str = DEFAULT_LOCALE) -> bool:
    """True se ``key`` existe no catálogo do idioma dado."""
    return key in _CATALOGS.get(locale, {})


def all_keys(*, locale: str = DEFAULT_LOCALE) -> frozenset[str]:
    """Conjunto de todas as chaves do idioma (para testes de completude)."""
    return frozenset(_CATALOGS.get(locale, {}))


def t(key: str, *, locale: str = DEFAULT_LOCALE, **params: object) -> str:
    """Traduz ``key`` no idioma dado, interpolando ``params`` via str.format.

    Levanta ``KeyError`` se a chave não existir (falha explícita — um código de
    erro sempre deve ter texto; ver teste de completude do catálogo).
    """
    catalog = _CATALOGS.get(locale) or _CATALOGS[DEFAULT_LOCALE]
    template = catalog.get(key)
    if template is None:
        raise KeyError(f"chave i18n ausente ({locale}): {key!r}")
    if params:
        return template.format(**params)
    return template
