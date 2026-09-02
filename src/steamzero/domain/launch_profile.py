# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Perfis de lançamento declarados por plataforma e emulador.

O contrato é fechado de propósito. Não existe comando livre, template textual nem
shell: o manifesto declara uma lista de argumentos com placeholders allowlisted, e
o argv é montado por substituição posicional. A ROM entra como argumento
**atômico** — nunca concatenada em string —, então nome com espaço, aspas ou
qualquer outro caractere é apenas um argumento, não uma oportunidade de injeção.

Sobre o RetroArch em particular: uma única instalação atende dezenas de
plataformas, cada uma com um core libretro diferente. O core é, portanto,
propriedade da PLATAFORMA e não do emulador. E core ausente é motivo legítimo
para recusar "Jogar" — oferecer o botão e falhar depois é a ação que termina em
stub, proibida pelo ``AGENTS.md``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from steamzero.core.errors import SteamZeroError

#: Únicos placeholders aceitos. Qualquer outro no manifesto é erro de contrato,
#: não algo a ignorar em silêncio: ignorar produziria argv silenciosamente errado.
ROM_PLACEHOLDER = "{rom}"
CORE_PLACEHOLDER = "{core}"
ALLOWED_PLACEHOLDERS = frozenset({ROM_PLACEHOLDER, CORE_PLACEHOLDER})

_PLACEHOLDER_RE = re.compile(r"\{[a-z_]+\}")
_CORE_RE = re.compile(r"^[a-z0-9][a-z0-9_]*$")

#: Cores libretro sancionados por plataforma — fonte de verdade da validação
#: de core. RetroArch é multi-plataforma; o core é propriedade da PLATAFORMA.
#: O manifesto que declara um core fora deste registro é contrato quebrado:
#: aceitar produziria um "Jogar" com core de outra plataforma (ou inexistente).
#: A entrada da plataforma é exigida sempre que um core é declarado, para que
#: este registro não envelheça silenciosamente quando um core novo chegar.
PLATFORM_CORES: dict[str, frozenset[str]] = {
    "nintendo-handheld": frozenset({"mgba"}),
    "nes-famicom": frozenset({"mesen"}),
    "snes": frozenset({"snes9x"}),
    "mega-drive": frozenset({"genesis_plus_gx"}),
    "arcade": frozenset({"fbneo"}),
    "playstation": frozenset({"swanstation"}),
    "nintendo-console": frozenset({"dolphin"}),
    "master-system": frozenset({"genesis_plus_gx"}),
    "game-gear": frozenset({"genesis_plus_gx"}),
    "pc-engine-turbografx": frozenset({"mednafen_pce"}),
    "atari-classics": frozenset({"stella", "atari800", "prosystem", "handy", "virtualjaguar"}),
    "neo-geo-pocket": frozenset({"mednafen_ngp"}),
    "wonderswan": frozenset({"mednafen_wswan"}),
    "msx": frozenset({"bluemsx"}),
    "zx-spectrum": frozenset({"fuse"}),
    "commodore-64": frozenset({"vice_x64"}),
    "amiga": frozenset({"puae"}),
    "colecovision": frozenset({"bluemsx"}),
    "intellivision": frozenset({"freeintv"}),
    "virtual-boy": frozenset({"mednafen_vb"}),
    "three-do": frozenset({"opera"}),
    "sega-cd-32x": frozenset({"genesis_plus_gx", "picodrive"}),
    "nintendo-64": frozenset({"mupen64plus_next"}),
    "playstation-2": frozenset({"pcsx2"}),
    "playstation-portable": frozenset({"ppsspp"}),
    "nintendo-ds": frozenset({"melonds"}),
    "dreamcast": frozenset({"flycast"}),
    # Lote 1 da cobertura dos 110 diretorios sem manifesto
    # (SZ-LIBRARY-CANONICAL, 2026-08-28). Sancao = contrato da plataforma
    # (o core libretro upstream existe); instalabilidade pelo lock e camada
    # separada e segue com recusa honesta de "Jogar" enquanto o core nao
    # estiver no lock.
    "sega-saturn": frozenset({"mednafen_saturn"}),
    "sg-1000": frozenset({"genesis_plus_gx"}),
    "neo-geo-cd": frozenset({"neocd"}),
    "vectrex": frozenset({"vecx"}),
    "odyssey2": frozenset({"o2em"}),
    "channelf": frozenset({"freechaf"}),
    "pc-engine-supergrafx": frozenset({"beetle_sgx"}),
    "atari-st": frozenset({"hatari"}),
    "apple2": frozenset({"applewin"}),
    "bbc-micro": frozenset({"beebem"}),
    "coco": frozenset({"xroar"}),
    "ti99": frozenset({"ti99"}),
    "zx81": frozenset({"81"}),
    "thomson": frozenset({"theodore"}),
    "x68000": frozenset({"px68k"}),
    "pc88": frozenset({"quasi88"}),
    "pc98": frozenset({"np2kai"}),
    "gameandwatch": frozenset({"gw"}),
    "supervision": frozenset({"potator"}),
    "megaduck": frozenset({"sameduck"}),
    "doom": frozenset({"prboom"}),
    "quake": frozenset({"tyrquake"}),
    "pico8": frozenset({"fake08"}),
    "tic80": frozenset({"tic80"}),
    "wasm4": frozenset({"wasm4"}),
}


@dataclass(frozen=True)
class LaunchProfile:
    """Como esta plataforma é lançada neste emulador."""

    platform_id: str
    adapter_id: str
    game_args: tuple[str, ...]
    open_args: tuple[str, ...] = ()
    core: str | None = None
    system_cores: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    requires_bios: tuple[str, ...] = field(default_factory=tuple)

    @property
    def requires_core(self) -> bool:
        return self.core is not None or bool(self.system_cores)

    @property
    def required_cores(self) -> tuple[str, ...]:
        """Cores possíveis deste perfil, em ordem estável e sem duplicatas."""
        return tuple(
            dict.fromkeys(core for _system, core in (*self.system_cores, ("", self.core)) if core)
        )

    def core_for_system(self, system_id: str | None) -> str | None:
        """Resolve o core do sistema, com fallback só quando declarado."""
        if system_id:
            for declared_system, core in self.system_cores:
                if declared_system == system_id:
                    return core
        return self.core

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "platformId": self.platform_id,
            "adapterId": self.adapter_id,
            "core": self.core,
            "openArgs": list(self.open_args),
            "gameArgs": list(self.game_args),
            "requiresBios": list(self.requires_bios),
        }
        if self.system_cores:
            result["systemCores"] = dict(self.system_cores)
        return result


def parse_launch(
    platform_id: str,
    adapter_id: str,
    raw: Any,
    *,
    systems: Sequence[str] | None = None,
) -> LaunchProfile | None:
    """Lê o bloco ``launch`` de um emulador declarado numa plataforma.

    Ausência devolve ``None`` — plataforma sem perfil simplesmente não é
    lançável, e isso precisa ser visível. Presença malformada levanta: aceitar
    contrato quebrado produziria argv errado em tempo de execução, longe da causa.
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise SteamZeroError(
            "E-API-SCHEMA", detail=f"launch de {platform_id}/{adapter_id} não é objeto"
        )

    game_args = _string_list(raw.get("gameArgs"), platform_id, adapter_id, "gameArgs")
    if not game_args:
        raise SteamZeroError(
            "E-API-SCHEMA", detail=f"launch de {platform_id}/{adapter_id} sem gameArgs"
        )
    open_args = _string_list(raw.get("openArgs") or [], platform_id, adapter_id, "openArgs")

    core = raw.get("core")
    if core is not None and (not isinstance(core, str) or not _CORE_RE.fullmatch(core)):
        raise SteamZeroError(
            "E-API-SCHEMA", detail=f"core inválido em {platform_id}/{adapter_id}: {core!r}"
        )
    if core is not None:
        sanctioned = PLATFORM_CORES.get(platform_id)
        if sanctioned is None or core not in sanctioned:
            raise SteamZeroError(
                "E-API-SCHEMA",
                detail=(
                    f"core {core!r} não é sancionado para a plataforma {platform_id} "
                    f"(sancionados: {sorted(sanctioned) if sanctioned else 'nenhum'})"
                ),
            )

    system_cores = _string_map(raw.get("systemCores") or {}, platform_id, adapter_id, "systemCores")
    if system_cores:
        if systems is None:
            raise SteamZeroError(
                "E-API-SCHEMA",
                detail=(
                    f"{platform_id}/{adapter_id} precisa declarar systems para validar systemCores"
                ),
            )
        unknown_systems = set(system_cores) - set(systems)
        if unknown_systems:
            raise SteamZeroError(
                "E-API-SCHEMA",
                detail=(
                    f"systemCores de {platform_id}/{adapter_id} referencia systems ausentes: "
                    f"{sorted(unknown_systems)}"
                ),
            )
        sanctioned = PLATFORM_CORES.get(platform_id)
        if sanctioned is None or any(value not in sanctioned for value in system_cores.values()):
            raise SteamZeroError(
                "E-API-SCHEMA",
                detail=(
                    f"systemCores de {platform_id}/{adapter_id} possui core não sancionado "
                    f"(sancionados: {sorted(sanctioned) if sanctioned else 'nenhum'})"
                ),
            )
    if CORE_PLACEHOLDER in " ".join(game_args) and core is None and not system_cores:
        raise SteamZeroError(
            "E-API-SCHEMA",
            detail=f"{platform_id}/{adapter_id} usa {{core}} sem declarar core",
        )

    for argument in (*game_args, *open_args):
        for placeholder in _PLACEHOLDER_RE.findall(argument):
            if placeholder not in ALLOWED_PLACEHOLDERS:
                raise SteamZeroError(
                    "E-API-SCHEMA",
                    detail=(
                        f"placeholder não permitido em {platform_id}/{adapter_id}: {placeholder}"
                    ),
                )
    if ROM_PLACEHOLDER not in game_args:
        # Exigir o placeholder SOZINHO num argumento garante que a ROM seja
        # atômica. "--rom={rom}" passaria numa checagem de substring e abriria
        # espaço para o caminho ser interpretado junto com a flag.
        raise SteamZeroError(
            "E-API-SCHEMA",
            detail=(
                f"{platform_id}/{adapter_id} precisa conter {ROM_PLACEHOLDER} como "
                "argumento próprio"
            ),
        )

    bios = _string_list(raw.get("requiresBios") or [], platform_id, adapter_id, "requiresBios")
    return LaunchProfile(
        platform_id=platform_id,
        adapter_id=adapter_id,
        game_args=game_args,
        open_args=open_args,
        core=core,
        system_cores=tuple(system_cores.items()),
        requires_bios=bios,
    )


def _string_list(value: Any, platform_id: str, adapter_id: str, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise SteamZeroError(
            "E-API-SCHEMA",
            detail=f"{field_name} de {platform_id}/{adapter_id} precisa ser lista de strings",
        )
    for item in value:
        if "\x00" in item:
            raise SteamZeroError("E-API-SCHEMA", detail=f"{field_name} de {platform_id} contém NUL")
    return tuple(value)


def _string_map(value: Any, platform_id: str, adapter_id: str, field_name: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or any(
        not isinstance(key, str) or not isinstance(item, str) for key, item in value.items()
    ):
        raise SteamZeroError(
            "E-API-SCHEMA",
            detail=f"{field_name} de {platform_id}/{adapter_id} precisa ser objeto de strings",
        )
    result: dict[str, str] = {}
    for key, item in value.items():
        if not re.fullmatch(r"^[a-z0-9][a-z0-9-]{0,62}$", key):
            raise SteamZeroError(
                "E-API-SCHEMA", detail=f"sistema inválido em {field_name}: {key!r}"
            )
        if not _CORE_RE.fullmatch(item):
            raise SteamZeroError("E-API-SCHEMA", detail=f"core inválido em {field_name}: {item!r}")
        result[key] = item
    return result


def build_argv(
    profile: LaunchProfile,
    executable: str,
    *,
    rom: Path | None = None,
    core_path: Path | None = None,
) -> list[str]:
    """Monta o argv por substituição posicional.

    Cada placeholder ocupa um argumento inteiro e é trocado pelo valor, sem
    formatação de string. Um caminho com espaço, aspas ou ponto e vírgula
    permanece um argumento único.
    """
    template = profile.game_args if rom is not None else profile.open_args
    if rom is not None and not template:
        raise SteamZeroError("E-API-SCHEMA", detail=f"{profile.platform_id} não declara gameArgs")
    if profile.requires_core and core_path is None and rom is not None:
        raise SteamZeroError(
            "E-CONTENT-UNSUPPORTED",
            detail=(
                f"plataforma {profile.platform_id} exige o core "
                f"{profile.core or 'específico do sistema'}"
            ),
        )

    argv = [executable]
    for argument in template:
        if argument == ROM_PLACEHOLDER:
            if rom is None:
                raise SteamZeroError("E-API-SCHEMA", detail="argumento de ROM usado sem ROM")
            argv.append(str(rom))
        elif argument == CORE_PLACEHOLDER:
            if core_path is None:
                raise SteamZeroError(
                    "E-CONTENT-UNSUPPORTED",
                    detail=(
                        f"core {profile.core or 'específico do sistema'} não encontrado no host"
                    ),
                )
            argv.append(str(core_path))
        else:
            argv.append(argument)
    return argv


#: Diretórios onde cores libretro costumam ser publicados. A busca é por nome
#: exato de core declarado, nunca por padrão vindo de fora.
_CORE_DIRS = (
    "~/.var/app/org.libretro.RetroArch/config/retroarch/cores",
    "~/.config/retroarch/cores",
    "~/.local/share/retroarch/cores",
    "/usr/lib/libretro",
    "/usr/lib64/libretro",
)


def find_core(
    core: str, *, search_paths: Sequence[Path] | None = None, home: Path | None = None
) -> Path | None:
    """Localiza o ``.so`` de um core libretro, ou ``None`` quando ausente.

    Ausência não é erro: é o estado que precisa chegar à UI como "instale o core"
    em vez de virar um botão Jogar que falha depois.
    """
    if not _CORE_RE.fullmatch(core):
        raise SteamZeroError("E-API-SCHEMA", detail=f"nome de core inválido: {core!r}")
    base = home or Path.home()
    roots = (
        list(search_paths)
        if search_paths is not None
        else [Path(str(d).replace("~", str(base), 1)) for d in _CORE_DIRS]
    )
    filename = f"{core}_libretro.so"
    for root in roots:
        candidate = root / filename
        if candidate.is_file():
            return candidate
    return None
