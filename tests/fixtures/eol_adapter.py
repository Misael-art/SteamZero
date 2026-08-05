# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Adapter com fonte Flatpak em fim de vida, sintético de propósito.

O comportamento EOL — status honesto, `installable=False` com motivo dizível,
launch de deployment já instalado, stop recusado, componente publicado como
`unsupported` no dashboard — é contrato permanente do lifecycle.

Antes, esse contrato era exercitado sobre o DuckStation, único adapter EOL
empacotado. Quando a fonte dele migrou do Flatpak descontinuado para o AppImage
oficial, nove testes caíram de uma vez **sem que o contrato tivesse mudado**:
eles não testavam o DuckStation, testavam o EOL, e tinham se amarrado ao
exemplar em vez do comportamento.

Um fixture próprio mantém a cobertura estável qualquer que seja o estado dos
manifests reais. Que nenhum emulador empacotado seja EOL é asserção separada,
em `test_component_lifecycle.py`.
"""

from __future__ import annotations

from typing import Any

from steamzero.adapters.registry import AdapterManifest, AdapterRegistry, load_manifest

EOL_ID = "eol-fixture"
EOL_REF = "org.example.EolFixture"
EOL_REMOTE = "flathub"
EOL_COMMIT = "a" * 64

_MANIFEST: dict[str, Any] = {
    "schemaVersion": 1,
    "id": EOL_ID,
    "kind": "emulator",
    "presentation": {"displayName": "EOL Fixture", "iconAsset": "../assets/steam.svg"},
    "platforms": ["psx"],
    "capabilities": ["detect", "status", "install", "update", "verify"],
    "sources": [
        {
            "type": "flatpak",
            "ref": EOL_REF,
            "remote": EOL_REMOTE,
            "version": EOL_COMMIT,
            "priority": 1,
            "endOfLife": True,
        }
    ],
    "configFormat": "ini",
    "verify": {"smokeTest": ["--version"]},
    "license": "GPL-3.0-only",
    "upstream": "https://example.invalid/eol",
}


def eol_manifest() -> AdapterManifest:
    """Manifesto EOL isolado; `dict()` evita que um teste mute o template."""
    return load_manifest(dict(_MANIFEST))


def eol_registry() -> AdapterRegistry:
    return AdapterRegistry([eol_manifest()])
