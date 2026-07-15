# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Camada de domínio (MODULE-BOUNDARIES).

Depende de ``core.*`` e de **portas de capacidade** (Protocols) declaradas aqui;
NUNCA importa ``adapters.*`` (a composição injeta implementações concretas).
Verificado por tools/lint_boundaries.py (BND-DOMAIN-ADAPTER).
"""
