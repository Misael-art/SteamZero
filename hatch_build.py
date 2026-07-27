# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Hook de build que grava a origem do código dentro do pacote.

Grava ``src/steamzero/_build_info.py`` com o commit de origem e um marcador de
árvore suja, para que o runtime possa declarar de onde veio (ver
``steamzero.core.identity``).

Reprodutibilidade: injetamos EXCLUSIVAMENTE o hash e o flag ``dirty``. Nenhum
timestamp, caminho de build, hostname ou usuário — qualquer um deles faria dois
builds do mesmo commit divergirem byte a byte, e a conferência de builds
idênticos é parte do fluxo de release do operador.

Sem ``git`` disponível (build a partir de sdist, por exemplo), o commit vale
``"unknown"``. O preflight de promoção trata isso como reprovação.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

# hatchling só existe no ambiente de build. As funções puras abaixo precisam ser
# importáveis e testáveis sem ele — o ambiente de testes instala apenas o
# requirements-dev.lock, onde o backend de build não entra.
try:
    from hatchling.builders.hooks.plugin.interface import BuildHookInterface
except ImportError:  # pragma: no cover - exercitado apenas fora do build
    BuildHookInterface = object  # type: ignore[assignment,misc]

_TARGET = Path("src") / "steamzero" / "_build_info.py"
_UNKNOWN = "unknown"

_TEMPLATE = '''\
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Origem do código, gravada em tempo de build. NÃO EDITE À MÃO.

Gerado por ``hatch_build.py``. Consumido por ``steamzero.core.identity``.
"""

from __future__ import annotations

SOURCE_COMMIT = "{commit}"
SOURCE_DIRTY = {dirty}
'''


def _git(args: list[str], root: Path) -> str | None:
    executable = shutil.which("git")
    if executable is None:
        return None
    try:
        result = subprocess.run(  # noqa: S603 - argv fixo, sem shell
            [executable, *args],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip()


def resolve_source(root: Path) -> tuple[str, bool]:
    """Commit completo e se a árvore tinha alterações não commitadas."""
    commit = _git(["rev-parse", "HEAD"], root)
    if not commit:
        return _UNKNOWN, False
    status = _git(["status", "--porcelain"], root)
    # status None significa que não conseguimos saber: trate como suja, porque
    # afirmar "limpa" sem prova é o tipo de otimismo que produz release errada.
    dirty = True if status is None else bool(status)
    return commit, dirty


def render(commit: str, dirty: bool) -> str:
    return _TEMPLATE.format(commit=commit, dirty=dirty)


def write_build_info(root: Path) -> Path:
    commit, dirty = resolve_source(root)
    target = root / _TARGET
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(commit, dirty), encoding="utf-8")
    return target


class SourceProvenanceHook(BuildHookInterface):  # type: ignore[type-arg]
    PLUGIN_NAME = "source-provenance"

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        write_build_info(Path(self.root))
