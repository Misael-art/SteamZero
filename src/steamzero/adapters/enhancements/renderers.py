# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Renderers de arquivos de melhoria por jogo, puros (sem I/O).

Cada formato conhece sua sintaxe e produz bytes válidos para o emulador
consumir. Nenhum renderer abre arquivo: a escrita pertence ao fluxo de
transação (plan_write_files/apply), e o instalador consome
``manageability_check`` antes de tocar qualquer arquivo existente.

Marcador de ownership (AGENTS.md seção 5): todo arquivo publicado carrega
``# SteamZero-Boot-Managed: true`` na primeira linha; arquivo sem o marcador
nunca é substituído.

Formatos (Onda 3):
- rpcs3-yaml: arquivo YAML de patches do RPCS3 (categoria técnica);
- cemu-rules: rules.txt do Cemu (cheats, secoes [Definition] + cheats);
- pcsx2-pnach: cheats .pnach do PCSX2/DuckStation (linhas com dois quads
  hexadecimais);
- dolphin-gameini: seção [Gecko] com códigos Gecko do Dolphin;
- duckstation-ini: gamesettings.ini do DuckStation (overrides por jogo,
  categoria técnica).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from steamzero.core.errors import SteamZeroError
from steamzero.domain.game_enhancements import (
    GAMEPLAY_BLACKLIST,
    EnhancementKind,
)

ENHANCEMENT_MARKER = "# SteamZero-Boot-Managed: true"
_MARKER_LINE = (ENHANCEMENT_MARKER + "\n").encode("ascii")


def _is_code_line(line: str) -> bool:
    """Linha de código: dois grupos hexadecimais de oito digitos separados
    por espaços (prefixo 0x opcional no primeiro para Gecko)."""
    import re

    stripped = line.strip()
    if not stripped or stripped.startswith("#") or stripped.startswith("//"):
        return False
    return bool(re.match(r"^(?:0x)?[0-9A-Fa-f]{8}\s+(?:0x)?[0-9A-Fa-f]{8}(?:\s+.*)?$", stripped))


class EnhancementFileFormat(StrEnum):
    RPCS3_YAML = "rpcs3-yaml"
    CEMU_RULES = "cemu-rules"
    PCSX2_PNACH = "pcsx2-pnach"
    DOLPHIN_GAMEINI = "dolphin-gameini"
    DUCKSTATION_INI = "duckstation-ini"


_TECHNICAL_ONLY = frozenset(
    {EnhancementFileFormat.RPCS3_YAML, EnhancementFileFormat.DUCKSTATION_INI}
)


@dataclass(frozen=True)
class EnhancementRecipe:
    """Conteúdo já aprovado pela política (assert_allowed já passou)."""

    kind: EnhancementKind
    category: str
    title: str
    source: str
    codes: tuple[str, ...] = ()
    version: str | None = None
    author: str = "SteamZero"


@dataclass(frozen=True)
class RenderedEnhancementFile:
    relative_path: str
    data: bytes
    format: EnhancementFileFormat


def manageability_check(existing: bytes | None) -> tuple[bool, str]:
    """Pode criar (None) ou substituir (marcador presente) o arquivo.

    Arquivo existente SEM o marcador é de terceiros: nunca tocar.
    """
    if existing is None:
        return True, "criável"
    head = existing[:512]
    if ENHANCEMENT_MARKER.encode("ascii") in head:
        return True, "marcado pelo SteamZero"
    return False, "arquivo sem marcador de ownership (terceiro)"


def _guard_technical_only(recipe: EnhancementRecipe, fmt: EnhancementFileFormat) -> None:
    if fmt in _TECHNICAL_ONLY and recipe.category in GAMEPLAY_BLACKLIST:
        raise SteamZeroError(
            "E-ENHANCEMENT-DENIED",
            detail=(f"formato {fmt.value} só aceita categoria técnica; recebeu {recipe.category}"),
        )


def _codes_to_lines(codes: tuple[str, ...]) -> list[str]:
    invalid = [line for line in codes if not _is_code_line(line)]
    if invalid:
        raise SteamZeroError(
            "E-ENHANCEMENT-DENIED",
            detail=f"códigos inválidos para o formato: {invalid[0]!r}",
        )
    return [line.strip() for line in codes]


def render_rpcs3_yaml(recipe: EnhancementRecipe) -> RenderedEnhancementFile:
    """Patch YAML do RPCS3 (categoria técnica; opcode be32 por linha)."""
    _guard_technical_only(recipe, EnhancementFileFormat.RPCS3_YAML)
    name = recipe.title.replace('"', "'")
    lines = [
        ENHANCEMENT_MARKER,
        "Version: 1.0",
        "Metadata:",
        f'  Name: "{name}"',
        f'  Author: "{recipe.author}"',
        f'  Category: "{recipe.category}"',
        "  VersionNotes:",
        f'    - "{recipe.source}"',
        "Patches:",
        f'  - Name: "{name}"',
        f'    Author: "{recipe.author}"',
        f'    Notes: "gerenciado pelo SteamZero ({recipe.source})"',
        "    Patch:",
    ]
    for line in _codes_to_lines(recipe.codes):
        parts = line.split()
        offset = int(parts[0].replace("0x", ""), 16)
        value = int(parts[1].replace("0x", ""), 16)
        lines.append(f"      - [be32, 0x{offset:08X}, 0x{value:08X}, 0x00000000]")
    data = ("\n".join(lines) + "\n").encode("utf-8")
    return RenderedEnhancementFile("patch.yml", data, EnhancementFileFormat.RPCS3_YAML)


def render_cemu_rules(
    recipe: EnhancementRecipe, title_ids: tuple[str, ...]
) -> RenderedEnhancementFile:
    """rules.txt do Cemu: [Definition] + seção por cheat."""
    if not isinstance(title_ids, tuple) or not title_ids:
        raise SteamZeroError("E-ENHANCEMENT-DENIED", detail="cemu-rules exige ao menos um titleId")
    lines = [
        ENHANCEMENT_MARKER,
        "[Definition]",
        "titleIds = " + ", ".join(title_ids),
        f'name = "{recipe.title}"',
        'path = "game profiles"',
        "",
    ]
    lines.append(f"[{recipe.title[:40]}]")
    lines.extend(_codes_to_lines(recipe.codes))
    data = ("\n".join(lines) + "\n").encode("utf-8")
    return RenderedEnhancementFile("rules.txt", data, EnhancementFileFormat.CEMU_RULES)


def render_pcsx2_pnach(recipe: EnhancementRecipe, serial: str) -> RenderedEnhancementFile:
    """Cheat .pnach do PCSX2/DuckStation: gametitle + pares hexadecimais."""
    if not serial or not serial.replace("-", "").isalnum():
        raise SteamZeroError(
            "E-ENHANCEMENT-DENIED", detail=f"serial inválido para pnach: {serial!r}"
        )
    lines = [
        ENHANCEMENT_MARKER,
        f"gametitle={recipe.title}",
        f"author={recipe.author}",
        f"// fonte: {recipe.source}",
        "",
        f"// {recipe.title}",
    ]
    lines.extend(_codes_to_lines(recipe.codes))
    data = ("\n".join(lines) + "\n").encode("ascii")
    return RenderedEnhancementFile(f"{serial}.pnach", data, EnhancementFileFormat.PCSX2_PNACH)


def render_dolphin_gameini(recipe: EnhancementRecipe) -> RenderedEnhancementFile:
    """GameINI do Dolphin: seção [Gecko] com códigos Gecko."""
    lines = [
        ENHANCEMENT_MARKER,
        f"# {recipe.title} (SteamZero, {recipe.source})",
        "",
        "[Gecko]",
        f"$SteamZero-{recipe.title[:32]}",
    ]
    lines.extend(_codes_to_lines(recipe.codes))
    data = ("\n".join(lines) + "\n").encode("ascii")
    return RenderedEnhancementFile("game.ini", data, EnhancementFileFormat.DOLPHIN_GAMEINI)


def render_duckstation_ini(
    recipe: EnhancementRecipe, settings: tuple[str, ...]
) -> RenderedEnhancementFile:
    """gamesettings.ini do DuckStation (overrides por jogo; técnico)."""
    _guard_technical_only(recipe, EnhancementFileFormat.DUCKSTATION_INI)
    if not settings:
        raise SteamZeroError(
            "E-ENHANCEMENT-DENIED", detail="duckstation-ini exige ao menos uma chave"
        )
    section = {
        "quality-of-life": "Display",
        "display-only": "Display",
        "performance": "GPU",
        "graphics": "GPU",
    }.get(recipe.category, "Display")
    lines = [
        ENHANCEMENT_MARKER,
        f"[{section}]",
        f"# via SteamZero ({recipe.source})",
    ]
    lines.extend(settings)
    data = ("\n".join(lines) + "\n").encode("ascii")
    return RenderedEnhancementFile("gamesettings.ini", data, EnhancementFileFormat.DUCKSTATION_INI)


_RENDERERS: dict[str, Callable[..., RenderedEnhancementFile]] = {
    "rpcs3-yaml": render_rpcs3_yaml,
    "cemu-rules": render_cemu_rules,
    "pcsx2-pnach": render_pcsx2_pnach,
    "dolphin-gameini": render_dolphin_gameini,
    "duckstation-ini": render_duckstation_ini,
}


def render_file(
    fmt: EnhancementFileFormat | str,
    recipe: EnhancementRecipe,
    *,
    serial: str | None = None,
    title_ids: tuple[str, ...] = (),
    settings: tuple[str, ...] = (),
) -> RenderedEnhancementFile:
    """Dispatcher puro de formatos da Onda 3."""
    key = fmt.value if isinstance(fmt, EnhancementFileFormat) else fmt
    renderer = _RENDERERS.get(key)
    if renderer is None:
        raise SteamZeroError("E-ENHANCEMENT-DENIED", detail=f"formato desconhecido: {key}")
    if key == "pcsx2-pnach":
        if not serial:
            raise SteamZeroError("E-ENHANCEMENT-DENIED", detail="pcsx2-pnach exige serial")
        return renderer(recipe, serial)
    if key == "cemu-rules":
        return renderer(recipe, title_ids)
    if key == "duckstation-ini":
        return renderer(recipe, settings)
    return renderer(recipe)
