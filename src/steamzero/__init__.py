# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""SteamZero — núcleo transacional da plataforma de jogos e emulação.

Camadas e fronteiras: ver docs/03-architecture/MODULE-BOUNDARIES.md.
Nenhum módulo depende "para cima"; escrita em disco só via ``steamzero.core.fs``.
"""

__all__ = ["CONTRACT_VERSION", "__version__"]

__version__ = "0.1.0a18"

#: Versão do contrato CLI/API (envelope v2). Ver docs/06-api/CLI-CONTRACT.md.
CONTRACT_VERSION = "2.0"
