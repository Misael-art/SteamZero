# SPDX-License-Identifier: GPL-3.0-or-later
"""Preflight observável do runtime necessário para lançamentos PS5."""

from __future__ import annotations

import platform
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

_SUPPORTED_ARCHITECTURES = frozenset({"x86_64", "amd64"})
_VULKAN_MARKERS = ("Vulkan Instance Version", "Devices:")


@dataclass(frozen=True)
class Ps5RuntimeReadiness:
    """Resultado estável e sem dados sensíveis do preflight PS5."""

    ready: bool
    architecture: str
    vulkan: bool
    reason: str = ""


def check_ps5_runtime(
    *,
    machine: Callable[[], str] = platform.machine,
    which: Callable[[str], str | None] = shutil.which,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> Ps5RuntimeReadiness:
    """Confere arquitetura e uma resposta real do ``vulkaninfo``.

    O probe é somente leitura, não carrega o emulador e não interpreta dumps.
    Dependências externas são injetáveis para que ausência, timeout e saída
    inválida sejam estados testáveis e publicados como falha controlada.
    """
    architecture = machine().strip().casefold()
    if architecture not in _SUPPORTED_ARCHITECTURES:
        return Ps5RuntimeReadiness(
            ready=False,
            architecture=architecture,
            vulkan=False,
            reason="ps5-architecture-unsupported",
        )

    vulkaninfo = which("vulkaninfo")
    if not vulkaninfo:
        return Ps5RuntimeReadiness(
            ready=False,
            architecture=architecture,
            vulkan=False,
            reason="ps5-vulkan-tool-missing",
        )

    try:
        result = run(
            [vulkaninfo, "--summary"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return Ps5RuntimeReadiness(
            ready=False,
            architecture=architecture,
            vulkan=False,
            reason="ps5-vulkan-probe-failed",
        )

    output = result.stdout or ""
    if result.returncode != 0 or any(marker not in output for marker in _VULKAN_MARKERS):
        return Ps5RuntimeReadiness(
            ready=False,
            architecture=architecture,
            vulkan=False,
            reason="ps5-vulkan-probe-failed",
        )
    return Ps5RuntimeReadiness(
        ready=True,
        architecture=architecture,
        vulkan=True,
    )
