# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Importadores de metadados externos para o modelo canônico (frente A1).

Cada adapter traduz um formato de terceiro em ``GameRecord`` e **nunca** vira o
modelo dominante: o SteamZero mantém um modelo interno único, e o formato
externo é entrada, não verdade. Um formato mais pobre não pode apagar
informação mais rica já conhecida — a fusão respeita a proveniência, e cada
adapter declara uma confiança condizente com o que a fonte realmente garante.

Adapters são puros: recebem texto já lido e devolvem registros. Ler disco,
percorrer diretório e escrever é do chamador, para que a tradução seja testável
com fixture sintética e sem tocar biblioteca real.

Suportados neste ciclo: ES-DE, RetroArch, Pegasus e LaunchBox. Playnite, Steam
e RetroFE seguem por fazer — ver ``SZ-AURA-METADATA``.
"""

from __future__ import annotations

from steamzero.domain.metadata_import._common import ImportResult, PathRefused
from steamzero.domain.metadata_import.esde import EsdeImportResult, import_esde_gamelist
from steamzero.domain.metadata_import.launchbox import import_launchbox_xml
from steamzero.domain.metadata_import.pegasus import import_pegasus_metadata
from steamzero.domain.metadata_import.retroarch import import_retroarch_playlist

__all__ = [
    "EsdeImportResult",
    "ImportResult",
    "PathRefused",
    "import_esde_gamelist",
    "import_launchbox_xml",
    "import_pegasus_metadata",
    "import_retroarch_playlist",
]
