# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Núcleo: fs, ids, errors, log, lock, journal, state, transaction.

Camada mais baixa do grafo de dependências (MODULE-BOUNDARIES): não importa de
``domain``, ``jobs``, ``api`` nem ``adapters``.
"""
