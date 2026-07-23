# SPDX-License-Identifier: GPL-3.0-or-later
"""Contrato declarativo, público e sem segredos dos provedores de mídia.

O catálogo é a única fonte de verdade consumida pela bridge/QML. Valores de
credenciais ficam exclusivamente no :class:`SecretStorePort`; este módulo
nunca recebe nem serializa seus conteúdos.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CredentialType = Literal["text", "password"]


@dataclass(frozen=True)
class CredentialField:
    id: str
    label: str
    type: CredentialType
    required: bool
    secret: bool
    placeholder: str
    help: str
    can_toggle_visibility: bool = False
    can_revoke: bool = True

    def public_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "label": self.label,
            "type": self.type,
            "required": self.required,
            "secret": self.secret,
            "placeholder": self.placeholder,
            "help": self.help,
            "canToggleVisibility": self.can_toggle_visibility,
            "canRevoke": self.can_revoke,
        }


@dataclass(frozen=True)
class ProviderDefinition:
    id: str
    name: str
    description: str
    auth_type: str
    credential_fields: tuple[CredentialField, ...]
    capabilities: tuple[str, ...]
    platforms: tuple[str, ...]
    media_kinds: tuple[str, ...]
    links: dict[str, str]
    credential_test_supported: bool = False
    credential_revoke_supported: bool = True
    enabled: bool = True
    unavailable_reason: str | None = None

    def public_dict(
        self,
        *,
        configured: bool,
        health_status: str = "unknown",
        last_validated_at: str | None = None,
        quota: str | None = None,
        credential_state: str | None = None,
        missing_required_fields: tuple[str, ...] = (),
    ) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "authType": self.auth_type,
            "credentialFields": [field.public_dict() for field in self.credential_fields],
            "capabilities": list(self.capabilities),
            "platforms": list(self.platforms),
            "mediaKinds": list(self.media_kinds),
            "links": dict(self.links),
            "configured": configured,
            "healthStatus": health_status,
            "lastValidatedAt": last_validated_at,
            "quota": quota,
            "credentialState": credential_state or health_status,
            "missingRequiredFields": list(missing_required_fields),
            "canTestCredential": bool(
                self.enabled
                and configured
                and self.credential_fields
                and self.credential_test_supported
            ),
            "credentialTestSupported": self.credential_test_supported,
            "canRevokeCredential": bool(
                self.enabled
                and configured
                and self.credential_fields
                and self.credential_revoke_supported
            ),
            "credentialRevokeSupported": self.credential_revoke_supported,
            "enabled": self.enabled,
            "unavailableReason": self.unavailable_reason,
        }


_STEAMGRIDDB = ProviderDefinition(
    id="steamgriddb",
    name="SteamGridDB",
    description="Grids, heroes, logos e ícones para a publicação local na Steam.",
    auth_type="api-key",
    credential_fields=(
        CredentialField(
            id="api_key",
            label="API key",
            type="password",
            required=True,
            secret=True,
            placeholder="Cole a chave SteamGridDB",
            help="A chave fica somente no cofre do sistema.",
            can_toggle_visibility=True,
        ),
    ),
    capabilities=("search", "grid", "hero", "logo", "icon"),
    platforms=("switch", "pc", "steam"),
    media_kinds=("grid", "hero", "logo", "icon"),
    links={
        "createAccount": "https://www.steamgriddb.com/profile/preferences/api",
        "credentials": "https://www.steamgriddb.com/profile/preferences/api",
        "documentation": "https://www.steamgriddb.com/api/v2",
        "terms": "https://www.steamgriddb.com/terms",
    },
    credential_test_supported=True,
)

_SCREENSCRAPER = ProviderDefinition(
    id="screenscraper",
    name="ScreenScraper",
    description=(
        "Metadados e mídia de catálogo; a integração aguarda credenciais de aplicação aprovadas."
    ),
    auth_type="username-password",
    credential_fields=(
        CredentialField(
            "username", "Usuário", "text", True, False, "Seu usuário", "Conta ScreenScraper."
        ),
        CredentialField(
            "password",
            "Senha",
            "password",
            True,
            True,
            "Sua senha",
            "Nunca é exibida em logs.",
            True,
        ),
    ),
    capabilities=("metadata", "boxart", "screenshot", "manual"),
    platforms=("switch",),
    media_kinds=("boxart", "screenshot", "manual"),
    links={
        "createAccount": "https://main.screenscraper.fr/membreinscription.php",
        "documentation": "https://www.screenscraper.fr/webapi2.php",
        "terms": "https://www.screenscraper.fr/conditions.php",
    },
    enabled=False,
    unavailable_reason="A API atual requer credenciais de aplicação que não pertencem ao usuário.",
)

_IGDB = ProviderDefinition(
    id="igdb",
    name="IGDB / Twitch",
    description=(
        "Metadados de jogos via OAuth de aplicação; o token transitório é renovado no backend."
    ),
    auth_type="oauth-client",
    credential_fields=(
        CredentialField(
            "client_id",
            "Client ID",
            "text",
            True,
            False,
            "Client ID Twitch",
            "Identificador da aplicação.",
        ),
        CredentialField(
            "client_secret",
            "Client Secret",
            "password",
            True,
            True,
            "Client Secret Twitch",
            "Usado apenas para renovar OAuth.",
            True,
        ),
    ),
    capabilities=("metadata",),
    platforms=("switch",),
    media_kinds=("metadata",),
    links={
        "documentation": "https://api-docs.igdb.com/",
        "terms": "https://www.igdb.com/api_terms",
    },
    enabled=False,
    unavailable_reason="Adaptador IGDB ainda não está implementado.",
)

_STEAM_LOCAL = ProviderDefinition(
    id="steam-local",
    name="Integração local com Steam",
    description="Publica atalhos e artes gerenciadas localmente; não usa API key.",
    auth_type="none",
    credential_fields=(),
    capabilities=("publish", "grid", "hero", "logo", "icon"),
    platforms=("switch",),
    media_kinds=("grid", "hero", "logo", "icon"),
    links={},
    credential_revoke_supported=False,
)

_STEAM_WEB = ProviderDefinition(
    id="steam-web-api",
    name="Steam Web API — opcional",
    description="Reservado para recursos que realmente consumam a Steam Web API.",
    auth_type="api-key",
    credential_fields=(
        CredentialField(
            "api_key",
            "API key",
            "password",
            True,
            True,
            "Chave Steam Web API",
            "Não é necessária para publicação local.",
            True,
        ),
    ),
    capabilities=(),
    platforms=("steam",),
    media_kinds=(),
    links={
        "credentials": "https://steamcommunity.com/dev/apikey",
        "documentation": "https://steamcommunity.com/dev",
    },
    credential_revoke_supported=False,
    enabled=False,
    unavailable_reason="Nenhum recurso atual depende da Steam Web API.",
)

PROVIDERS: tuple[ProviderDefinition, ...] = (
    _STEAMGRIDDB,
    _SCREENSCRAPER,
    _IGDB,
    _STEAM_LOCAL,
    _STEAM_WEB,
)


def provider_by_id(provider_id: str) -> ProviderDefinition:
    for provider in PROVIDERS:
        if provider.id == provider_id:
            return provider
    raise ValueError("provedor não permitido")


def allowed_external_url(provider_id: str, link: str) -> str:
    url = provider_by_id(provider_id).links.get(link)
    if (
        url is None
        or not url.startswith("https://")
        or any(character.isspace() for character in url)
    ):
        raise ValueError("link externo não permitido")
    return url
