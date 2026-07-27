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
from collections.abc import Sequence
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


@dataclass(frozen=True)
class LaunchProfile:
    """Como esta plataforma é lançada neste emulador."""

    platform_id: str
    adapter_id: str
    game_args: tuple[str, ...]
    open_args: tuple[str, ...] = ()
    core: str | None = None
    requires_bios: tuple[str, ...] = field(default_factory=tuple)

    @property
    def requires_core(self) -> bool:
        return self.core is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "platformId": self.platform_id,
            "adapterId": self.adapter_id,
            "core": self.core,
            "openArgs": list(self.open_args),
            "gameArgs": list(self.game_args),
            "requiresBios": list(self.requires_bios),
        }


def parse_launch(platform_id: str, adapter_id: str, raw: Any) -> LaunchProfile | None:
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

    for argument in (*game_args, *open_args):
        for placeholder in _PLACEHOLDER_RE.findall(argument):
            if placeholder not in ALLOWED_PLACEHOLDERS:
                raise SteamZeroError(
                    "E-API-SCHEMA",
                    detail=(
                        f"placeholder não permitido em {platform_id}/{adapter_id}: {placeholder}"
                    ),
                )
    if CORE_PLACEHOLDER in " ".join(game_args) and core is None:
        raise SteamZeroError(
            "E-API-SCHEMA",
            detail=f"{platform_id}/{adapter_id} usa {{core}} sem declarar core",
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
            detail=f"plataforma {profile.platform_id} exige o core {profile.core}",
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
                    detail=f"core {profile.core} não encontrado no host",
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
