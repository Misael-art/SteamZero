# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Composição declarativa e abertura segura de plataformas cloud."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol

from steamzero.core import transaction
from steamzero.core.errors import SteamZeroError
from steamzero.domain.platforms import PlatformManifest, PlatformRegistry, platform_placeholder

Which = Callable[[str], str | None]
Spawn = Callable[[Sequence[str]], int | None]


class CloudShortcutPort(Protocol):
    def managed_cloud_platform_ids(self) -> set[str]: ...

    def plan_cloud(self, platforms: Sequence[Mapping[str, Any]]) -> transaction.Plan: ...


class CloudPlatformService:
    """Expõe somente serviços e destinos declarados no registro versionado."""

    def __init__(
        self,
        shortcuts: CloudShortcutPort,
        *,
        registry: PlatformRegistry | None = None,
        which: Which,
        spawn: Spawn,
    ) -> None:
        self._shortcuts = shortcuts
        self._registry = registry or PlatformRegistry.bundled()
        self._which = which
        self._spawn = spawn

    def platforms(self) -> list[dict[str, Any]]:
        published = self._shortcuts.managed_cloud_platform_ids()
        return [
            self._compose(manifest, published=manifest.id in published)
            for manifest in self._cloud_manifests()
        ]

    def launch(self, platform_id: str) -> dict[str, Any]:
        manifest = self._cloud_manifest(platform_id)
        executable = self._which("xdg-open")
        if executable is None:
            raise SteamZeroError(
                "E-DESKTOP-VERIFY",
                detail="xdg-open não está disponível para abrir o serviço cloud",
            )
        cloud = manifest.cloud
        if cloud is None:  # defesa adicional ao schema do registro
            raise SteamZeroError("E-STATE-INTEGRITY", detail="manifesto cloud incompleto")
        url = str(cloud["launchUrl"])
        try:
            pid = self._spawn((executable, url))
        except Exception as exc:
            raise SteamZeroError(
                "E-DESKTOP-VERIFY",
                detail="não foi possível abrir o serviço cloud no navegador",
            ) from exc
        return {
            "status": "started",
            "platformId": manifest.id,
            "url": url,
            "pid": pid,
            "availability": "unverified",
        }

    def plan_shortcuts(self) -> transaction.Plan:
        return self._shortcuts.plan_cloud(
            [{"id": manifest.id, "name": manifest.name} for manifest in self._cloud_manifests()]
        )

    def _cloud_manifests(self) -> list[PlatformManifest]:
        return [manifest for manifest in self._registry.list() if manifest.kind == "cloud"]

    def _cloud_manifest(self, platform_id: str) -> PlatformManifest:
        manifest = self._registry.get(platform_id)
        if manifest.kind != "cloud":
            raise SteamZeroError("E-API-SCHEMA", detail=f"{platform_id} não é uma plataforma cloud")
        return manifest

    def _compose(self, manifest: PlatformManifest, *, published: bool) -> dict[str, Any]:
        platform = platform_placeholder(manifest)
        opener_available = self._which("xdg-open") is not None
        open_detail = (
            "O abridor local está disponível. Conta, assinatura, catálogo, região e "
            "rede não foram verificados."
            if opener_available
            else "xdg-open não está disponível; conta, assinatura, catálogo, região e "
            "rede também não foram verificados."
        )
        platform.update(
            {
                "state": "attention" if opener_available else "unavailable",
                "statusLabel": (
                    "Abertura local disponível"
                    if opener_available
                    else "Abridor local indisponível"
                ),
                "readiness": {
                    "percent": 50 if opener_available else 0,
                    "title": (
                        "Abertura local disponível"
                        if opener_available
                        else "Abridor local indisponível"
                    ),
                    "detail": open_detail,
                    "blockers": [
                        "Disponibilidade do serviço, conta, assinatura, região, catálogo e "
                        "rede permanecem não verificadas."
                    ],
                },
            }
        )
        for capability in platform["capabilities"]:
            if capability["id"] == "cloud-launch":
                capability.update(
                    {
                        "state": "ready" if opener_available else "unavailable",
                        "detail": open_detail,
                    }
                )
        advanced = platform["areaData"]["advanced"]
        launch_action = {
            "id": f"cloud.launch:{manifest.id}",
            "label": f"Abrir {manifest.short_name}",
            "enabled": opener_available,
            "reason": None if opener_available else "xdg-open não está disponível.",
            "requiresConfirmation": False,
        }
        shortcut_action = {
            "id": "cloud.shortcuts.sync",
            "label": "Atualizar atalhos cloud na Steam",
            "enabled": True,
            "reason": None,
            "requiresConfirmation": True,
        }
        advanced["primaryAction"] = launch_action
        advanced["cards"] = [
            {
                "id": "cloud-launch",
                "title": "Serviço oficial",
                "detail": open_detail,
                "state": "ready" if opener_available else "unavailable",
                "statusLabel": (
                    "URL allowlisted pronta" if opener_available else "Abridor local ausente"
                ),
                "action": launch_action,
            },
            {
                "id": "cloud-steam-shortcut",
                "title": "Atalho na Steam",
                "detail": (
                    "Publicado pelo SteamZero; sincronização preserva atalhos externos."
                    if published
                    else "Ainda não publicado; a sincronização preserva atalhos externos."
                ),
                "state": "ready" if published else "attention",
                "statusLabel": "Publicado" if published else "Não publicado",
                "action": shortcut_action,
            },
        ]
        for area in platform["areas"]:
            if area["id"] == "advanced":
                area.update(
                    {
                        "state": "ready" if opener_available else "unavailable",
                        "statusLabel": (
                            "URL allowlisted" if opener_available else "Abridor local ausente"
                        ),
                    }
                )
        cloud = dict(platform["cloud"])
        cloud.update(
            {
                "openerAvailable": opener_available,
                "shortcutPublished": published,
                "serviceAvailability": "unverified",
            }
        )
        platform["cloud"] = cloud
        return platform
