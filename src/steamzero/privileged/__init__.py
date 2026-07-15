# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Fronteira privilegiada (ADR-0009, PRIVILEGE-BOUNDARIES).

`steamzero-admin` (helper) e `privileged.client`. Allowlist enum fechada; nenhuma
string de shell, path arbitrário ou conteúdo de arquivo cruza a fronteira. Menor
privilégio: uma ação por vez, parâmetros schemados, audit log próprio.
"""
