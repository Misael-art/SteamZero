# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Importadores de metadados externos para o modelo canônico (frente A1).

Cada adapter traduz um formato de terceiro em ``GameRecord`` e **nunca** vira o
modelo dominante: o SteamZero mantém um modelo interno único, e o formato
externo é entrada, não verdade. Um formato mais pobre não pode apagar
informação mais rica já conhecida — a fusão respeita a proveniência.

Adapters são puros: recebem texto já lido e devolvem registros. Ler disco,
percorrer diretório e escrever é do chamador, para que a tradução seja testável
com fixture sintética e sem tocar biblioteca real.
"""

from __future__ import annotations

from steamzero.domain.metadata_import.esde import (
    EsdeImportResult,
    import_esde_gamelist,
)

__all__ = ["EsdeImportResult", "import_esde_gamelist"]
