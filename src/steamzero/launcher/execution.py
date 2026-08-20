# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Como o Launcher decide o que executar para cada jogo.

O projeto atende dezenas de sistemas e cada um tem emulador, core, argumentos e
precedência próprios. Um comando fixo serviria a uma plataforma e quebraria o
resto — por isso a decisão vem inteira do manifesto da plataforma, através de
``domain.launch_profile``, que já monta o argv por substituição posicional com a
ROM como argumento atômico.

Nada aqui inventa alternativa. Sem emulador instalado, ou com core ausente, o
plano é recusado **com motivo**: oferecer "Jogar" e falhar depois é a ação que
termina em stub.
"""

from __future__ import annotations

from collections.abc import Iterable, Set
from dataclasses import dataclass
from pathlib import Path

from steamzero.core.errors import SteamZeroError
from steamzero.domain.launch_profile import build_argv, find_core, parse_launch
from steamzero.domain.platforms import PlatformRegistry
from steamzero.launcher.library import LibraryGame

DIAG_NO_EMULATOR = "LAUNCHER-EXEC-NO-EMULATOR-001"
DIAG_UNKNOWN_PLATFORM = "LAUNCHER-EXEC-PLATFORM-002"
DIAG_CORE_MISSING = "LAUNCHER-EXEC-CORE-003"


@dataclass(frozen=True)
class ExecutionPlan:
    game: LibraryGame
    emulator_id: str
    argv: tuple[str, ...]
    core: str | None = None


@dataclass(frozen=True)
class ExecutionRefusal:
    code: str
    reason: str
    fallback: str = "acao-bloqueada"


def _platform_for(system: str, registry: PlatformRegistry) -> object | None:
    """Acha a família da plataforma pelo id ou pelo sistema que ela agrega.

    Uma família cobre vários sistemas — ``nintendo-handheld`` atende gb, gbc e
    gba —, então o jogo pode chegar identificado por qualquer um dos dois.
    """
    for manifest in registry.list():
        if manifest.id == system or system in tuple(getattr(manifest, "systems", ()) or ()):
            return manifest
    return None


def _emulator_entries(manifest: object) -> Iterable[dict[str, object]]:
    entries = getattr(manifest, "emulators", None) or []
    candidates = [dict(entry) for entry in entries if isinstance(entry, dict)]
    # Precedência é do manifesto: primary antes de fallback, e o operador não
    # deve receber um emulador secundário só porque ele apareceu antes na lista.
    return sorted(candidates, key=lambda item: int(item.get("precedence", 99)))


def resolve_execution(
    game: LibraryGame,
    *,
    available: Set[str],
    registry: PlatformRegistry | None = None,
    core_search: Path | None = None,
) -> ExecutionPlan | ExecutionRefusal:
    """Escolhe emulador e monta o argv para este jogo, ou recusa com motivo."""
    catalogue = registry or PlatformRegistry.bundled()
    manifest = _platform_for(game.system, catalogue)
    if manifest is None:
        return ExecutionRefusal(
            code=DIAG_UNKNOWN_PLATFORM,
            reason=f"plataforma '{game.system}' não está no catálogo",
        )

    platform_id = str(getattr(manifest, "id", game.system))
    tried: list[str] = []
    for entry in _emulator_entries(manifest):
        emulator_id = str(entry.get("adapterId") or entry.get("id") or "")
        if not emulator_id:
            continue
        tried.append(emulator_id)
        if emulator_id not in available:
            continue
        profile = parse_launch(platform_id, emulator_id, entry.get("launch"))
        if profile is None:
            continue
        core_path: Path | None = None
        if profile.requires_core and profile.core:
            core_path = find_core(
                profile.core, search_paths=(core_search,) if core_search else None
            )
            if core_path is None:
                # Core ausente é recusa legítima: o emulador abriria e não
                # rodaria o jogo, o que é pior do que dizer que falta o core.
                return ExecutionRefusal(
                    code=DIAG_CORE_MISSING,
                    reason=(
                        f"plataforma '{platform_id}' exige o core {profile.core}, "
                        "que não está instalado"
                    ),
                )
        try:
            argv = build_argv(profile, emulator_id, rom=game.path, core_path=core_path)
        except SteamZeroError as exc:
            return ExecutionRefusal(code=DIAG_CORE_MISSING, reason=str(exc))
        return ExecutionPlan(
            game=game,
            emulator_id=emulator_id,
            argv=tuple(argv),
            core=profile.core,
        )

    listed = ", ".join(tried) if tried else "nenhum declarado"
    return ExecutionRefusal(
        code=DIAG_NO_EMULATOR,
        reason=f"nenhum emulador de '{platform_id}' está instalado (declarados: {listed})",
    )
