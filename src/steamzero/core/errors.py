# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Catálogo de erros e objeto de erro (P7 — "erro é interface").

Todo erro emitido pelo núcleo tem código estável ``E-<ÁREA>-<NOME>`` registrado
aqui (ERROR-CATALOG.md). ``SteamZeroError`` recusa códigos não registrados —
o teste ``test_error_catalog`` garante que todo código tem textos i18n e que não
há texto órfão. Especificidades dinâmicas vão em ``detail``/``autoAction``, nunca
no texto fixo do catálogo (CONTENT-POLICY).
"""

from __future__ import annotations

from typing import Any

from steamzero import i18n

# Campos i18n obrigatórios por código (convenção error.<CÓDIGO>.<campo>).
REQUIRED_FIELDS = ("title", "what", "impact", "cause", "action")

# Registro autoritativo: código -> área. A área é o segundo segmento do código.
ERROR_CATALOG: dict[str, str] = {
    # TX
    "E-TX-CONFIRM-REQUIRED": "TX",
    "E-TX-STALE-PLAN": "TX",
    "E-TX-VERIFY-FAILED": "TX",
    "E-TX-ROLLBACK-FAILED": "TX",
    "E-TX-LOCKED": "TX",
    # SUPPLY
    "E-SUPPLY-NO-CHECKSUM": "SUPPLY",
    "E-SUPPLY-CHECKSUM": "SUPPLY",
    "E-SUPPLY-OFFLINE": "SUPPLY",
    "E-SUPPLY-UPSTREAM-GONE": "SUPPLY",
    "E-SUPPLY-REMOTE-FAILED": "SUPPLY",
    # STORAGE
    "E-STORAGE-SPACE": "STORAGE",
    "E-STORAGE-MISSING": "STORAGE",
    "E-STORAGE-IO": "STORAGE",
    "E-STORAGE-RO": "STORAGE",
    # CONTENT
    "E-CONTENT-UNSAFE-ARCHIVE": "CONTENT",
    "E-CONTENT-UNSAFE-PATH": "CONTENT",
    "E-CONTENT-INCOMPLETE": "CONTENT",
    "E-CONTENT-BIOS-MISSING": "CONTENT",
    "E-CONTENT-FW-INCOMPAT": "CONTENT",
    "E-CONTENT-FW-MISSING": "CONTENT",
    "E-CONTENT-KEYS-MISSING": "CONTENT",
    "E-CONTENT-KEYS-INCOMPAT": "CONTENT",
    "E-CONTENT-POLICY": "CONTENT",
    "E-CONTENT-LIMIT": "CONTENT",
    "E-CONTENT-UNSUPPORTED": "CONTENT",
    # COMPONENT
    "E-COMPONENT-UPDATE-ROLLEDBACK": "COMPONENT",
    "E-COMPONENT-DEGRADED": "COMPONENT",
    "E-COMPONENT-UNSUPPORTED-DISTRO": "COMPONENT",
    # SAVES
    "E-SAVES-CONFLICT": "SAVES",
    "E-SAVES-FLUSH-TIMEOUT": "SAVES",
    # SESSION / MODE
    "E-SESSION-INTERRUPTED": "SESSION",
    "E-SESSION-LAUNCH-FAILED": "SESSION",
    "E-SESSION-RESUME-DEGRADED": "SESSION",
    "E-MODE-DISPLAY-FALLBACK": "MODE",
    # DESKTOP EXPERIENCE
    "E-DESKTOP-OWNER-CONFLICT": "DESKTOP",
    "E-DESKTOP-CONFLICT-RELEASE": "DESKTOP",
    "E-DESKTOP-VERIFY": "DESKTOP",
    "E-DESKTOP-RECOVERY": "DESKTOP",
    # PRIV
    "E-PRIV-DENIED": "PRIV",
    "E-PRIV-HELPER-MISSING": "PRIV",
    "E-PRIV-PROTO-MISMATCH": "PRIV",
    # API
    "E-API-SCHEMA": "API",
    "E-API-UNKNOWN-ACTION": "API",
    "E-API-CONTRACT": "API",
    "E-API-GENERATION-MISMATCH": "API",
    # CAST
    "E-CAST-UNAVAILABLE": "CAST",
    "E-CAST-UNKNOWN-PROTOCOL": "CAST",
    # JOBS
    "E-JOBS-BLOCKED-GAMEPLAY": "JOBS",
    "E-JOBS-BLOCKED-BATTERY": "JOBS",
    # NET
    "E-NET-INSECURE-URL": "NET",
    "E-NET-HOST-DENIED": "NET",
    "E-NET-REDIRECT-DENIED": "NET",
    "E-NET-TIMEOUT": "NET",
    "E-NET-OFFLINE": "NET",
    "E-NET-HTTP": "NET",
    "E-NET-CONTENT-LIMIT": "NET",
    "E-NET-CANCELLED": "NET",
    # Fase 1 (adições registradas — ver WORKLOG)
    "E-CLI-USAGE": "CLI",
    "E-STATE-MIGRATION": "STATE",
    "E-STATE-INTEGRITY": "STATE",
    "E-INTERNAL-UNEXPECTED": "INTERNAL",
    # Fase 3 (adições registradas — conversões, RT-06/FI-19)
    "E-CONVERT-TIMEOUT": "CONVERT",
    "E-CONVERT-FAILED": "CONVERT",
    # Scraping
    "E-SCRAPE-PROVIDER-UNREACHABLE": "SCRAPE",
    "E-SCRAPE-RATE-LIMITED": "SCRAPE",
    "E-SCRAPE-QUOTA-EXCEEDED": "SCRAPE",
    "E-SCRAPE-NOT-FOUND": "SCRAPE",
    "E-SCRAPE-DOWNLOAD-FAILED": "SCRAPE",
    "E-SCRAPE-CORRUPT-MEDIA": "SCRAPE",
    "E-SCRAPE-CREDENTIAL-MISSING": "SCRAPE",
    "E-SCRAPE-CREDENTIAL-REJECTED": "SCRAPE",
    "E-SCRAPE-VAULT-UNAVAILABLE": "SCRAPE",
    "E-SCRAPE-CACHE-FULL": "SCRAPE",
    "E-SCRAPE-HTTP-ERROR": "SCRAPE",
    "E-SCRAPE-OFFLINE": "SCRAPE",
    # --- Mods (Switch emulators)
    "E-MOD-NOT-FOUND": "MOD",
    "E-MOD-DOWNLOAD-FAILED": "MOD",
    "E-MOD-INSTALL-FAILED": "MOD",
    "E-MOD-SOURCE-UNREACHABLE": "MOD",
    "E-MOD-BUILD-ID-MISSING": "MOD",
    "E-MOD-EMULATOR-NOT-FOUND": "MOD",
    "E-MOD-CATALOG-STALE": "MOD",
    # --- Cheats (Switch emulators)
    "E-CHEAT-NOT-FOUND": "CHEAT",
    "E-CHEAT-DOWNLOAD-FAILED": "CHEAT",
    "E-CHEAT-INSTALL-FAILED": "CHEAT",
    "E-CHEAT-SOURCE-UNREACHABLE": "CHEAT",
    "E-CHEAT-BUILD-ID-MISSING": "CHEAT",
    "E-CHEAT-EMULATOR-NOT-FOUND": "CHEAT",
    "E-CHEAT-CATALOG-STALE": "CHEAT",
    "E-CHEAT-INVALID-CODES": "CHEAT",
    # THEME
    "E-THEME-MANIFEST": "THEME",
    "E-THEME-INCOMPATIBLE": "THEME",
    "E-THEME-UNSAFE": "THEME",
    "E-THEME-LIMIT": "THEME",
    "E-THEME-NOT-FOUND": "THEME",
    "E-THEME-ACTIVE": "THEME",
    "E-THEME-DOWNLOAD-FAILED": "THEME",
    "E-THEME-CATALOG-FAILED": "THEME",
    "E-THEME-MARKETPLACE-DISABLED": "THEME",
    # --- Compartilhamento de tela (ADR-0022)
    "E-CAST-NO-RECEIVER": "CAST",
    "E-CAST-RECEIVER-INCOMPATIBLE": "CAST",
    "E-CAST-ENGINE-MISSING": "CAST",
    "E-CAST-PAIRING-REJECTED": "CAST",
    "E-CAST-CONSENT-REQUIRED": "CAST",
    "E-CAST-PROTECTED-CONTENT": "CAST",
    "E-CAST-LINK-LOST": "CAST",
    "E-CAST-STATE-INVALID": "CAST",
}


def is_registered(code: str) -> bool:
    """True se ``code`` consta no catálogo autoritativo."""
    return code in ERROR_CATALOG


def build_error(
    code: str,
    *,
    detail: str | None = None,
    operation_id: str | None = None,
    auto_action: str | None = None,
    details_ref: str | None = None,
    locale: str = i18n.DEFAULT_LOCALE,
) -> dict[str, Any]:
    """Constrói o objeto de erro (schema error-v1) resolvendo textos do i18n.

    ``detail`` e ``auto_action`` carregam especificidades dinâmicas; o texto do
    catálogo é fixo. Levanta ValueError para código não registrado.
    """
    if code not in ERROR_CATALOG:
        raise ValueError(f"código de erro não registrado no catálogo: {code!r}")
    action = i18n.t(f"error.{code}.action", locale=locale)
    return {
        "code": code,
        "title": i18n.t(f"error.{code}.title", locale=locale),
        "what": i18n.t(f"error.{code}.what", locale=locale),
        "impact": i18n.t(f"error.{code}.impact", locale=locale),
        "probableCause": i18n.t(f"error.{code}.cause", locale=locale),
        "autoAction": auto_action,
        "manualAction": action,
        # aliases de compatibilidade com o envelope v2 (CLI-CONTRACT)
        "action": action,
        "detail": detail,
        "operationId": operation_id,
        "detailsRef": details_ref,
    }


class SteamZeroError(Exception):
    """Erro de domínio com código estável do catálogo.

    Recusa códigos não registrados (falha explícita em desenvolvimento/testes).
    """

    def __init__(
        self,
        code: str,
        *,
        detail: str | None = None,
        operation_id: str | None = None,
        auto_action: str | None = None,
        details_ref: str | None = None,
    ) -> None:
        if code not in ERROR_CATALOG:
            raise ValueError(f"código de erro não registrado no catálogo: {code!r}")
        self.code = code
        self.detail = detail
        self.operation_id = operation_id
        self.auto_action = auto_action
        self.details_ref = details_ref
        super().__init__(f"{code}: {detail}" if detail else code)

    def to_error_object(self, *, locale: str = i18n.DEFAULT_LOCALE) -> dict[str, Any]:
        """Serializa como objeto error-v1."""
        return build_error(
            self.code,
            detail=self.detail,
            operation_id=self.operation_id,
            auto_action=self.auto_action,
            details_ref=self.details_ref,
            locale=locale,
        )
