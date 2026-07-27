# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Identidade de runtime — quem este processo é, carregado, nunca consultado.

A regressão da a37 aconteceu porque o daemon da geração anterior sobreviveu à
troca de release e passou a responder como se fosse a nova. Nenhum lado sabia
declarar a própria origem.

A regra que este módulo implementa: **identidade se carrega, não se consulta.**
O commit de origem é gravado dentro do pacote em tempo de build; ele viaja com
o código. Ler o commit de um arquivo externo (por exemplo o ``manifest.json``
ao lado de ``current``) seria pior que não ter identidade: o processo antigo
leria o manifesto da release NOVA e afirmaria ser ela — a verificação passaria e
a regressão continuaria invisível.

Sem ``.git`` e sem injeção de build, o commit vale ``"unknown"``. O preflight de
promoção (``tools/release_preflight.py``) trata ausência como reprovação, então
o fallback não é uma brecha: é um estado declarado.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any

from steamzero import __version__

#: Valor usado quando a origem não pôde ser determinada no build.
UNKNOWN_COMMIT = "unknown"


def _build_info() -> tuple[str, bool]:
    """Lê o módulo gravado pelo hook de build, se existir.

    Em árvore de desenvolvimento sem build o módulo não existe, e a identidade
    degrada para ``unknown`` em vez de falhar — o núcleo continua utilizável.
    """
    # Import por nome: o módulo é gerado em tempo de build e não existe na
    # árvore, então não pode ser resolvido estaticamente.
    try:
        info = importlib.import_module("steamzero._build_info")
    except ImportError:
        return UNKNOWN_COMMIT, False
    commit = str(getattr(info, "SOURCE_COMMIT", "") or UNKNOWN_COMMIT)
    dirty = bool(getattr(info, "SOURCE_DIRTY", False))
    return commit, dirty


@dataclass(frozen=True)
class RuntimeIdentity:
    """Quem é o código que está executando agora."""

    package_version: str
    source_commit: str
    source_dirty: bool
    release_id: str

    @property
    def known(self) -> bool:
        """Identidade utilizável para comparar gerações."""
        return self.source_commit != UNKNOWN_COMMIT and bool(self.source_commit)

    def to_dict(self) -> dict[str, Any]:
        return {
            "packageVersion": self.package_version,
            "sourceCommit": self.source_commit,
            "sourceDirty": self.source_dirty,
            "releaseId": self.release_id,
        }

    def matches(self, other: RuntimeIdentity) -> bool:
        """Duas identidades descrevem a MESMA geração.

        Identidade desconhecida nunca casa, nem consigo mesma: não sabemos o que
        estamos comparando, e assumir compatibilidade é o erro que a a37 cometeu.
        """
        if not self.known or not other.known:
            return False
        return (
            self.package_version == other.package_version
            and self.source_commit == other.source_commit
            and self.release_id == other.release_id
        )


def _derive_release_id(version: str, commit: str) -> str:
    """Mesma regra de ``tools/install_host.py::_canonical_release``."""
    if commit == UNKNOWN_COMMIT or len(commit) < 12:
        return ""
    return f"{version}-{commit[:12]}"


def runtime_identity() -> RuntimeIdentity:
    commit, dirty = _build_info()
    return RuntimeIdentity(
        package_version=__version__,
        source_commit=commit,
        source_dirty=dirty,
        release_id=_derive_release_id(__version__, commit),
    )
