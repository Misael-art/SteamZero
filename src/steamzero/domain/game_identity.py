# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Identidade de título tipada por plataforma (Onda 1).

Cobre os esquemas de ID usados pelos emuladores do catálogo: Title ID do
Switch, serial de PS1/PS2 (PVD do ISO9660), Game ID de GC/Wii, TITLE_ID de
PS3 (PS3_DISC.SFB), product_id de Wii U (meta.xml) e CRC32 do ELF de PS2.

O valor é um tipo do domínio com plataforma, esquema e valor validado — nunca
uma string solta. A leitura de bytes fica no adapter; aqui só há validação
pura e normalização, testável com fixtures sintéticas.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

_MAX_VALUE_LENGTH = 64


class IdentityScheme(Enum):
    SWITCH_TITLE_ID = "switch-title-id"
    PSX_SERIAL = "psx-serial"
    PS2_SERIAL = "ps2-serial"
    GC_GAME_ID = "gc-game-id"
    WII_GAME_ID = "wii-game-id"
    PS3_TITLE_ID = "ps3-title-id"
    WIIU_PRODUCT_ID = "wiiu-product-id"
    PS2_ELF_CRC32 = "ps2-elf-crc32"
    UNKNOWN = "unknown"

    @classmethod
    def _missing_(cls, value: object) -> IdentityScheme:
        if isinstance(value, str):
            for member in cls:
                if member.value == value:
                    return member
        return cls.UNKNOWN


#: Regex de validação por esquema. ``UNKNOWN`` não valida nada.
_SCHEME_PATTERNS: dict[IdentityScheme, re.Pattern[str]] = {
    IdentityScheme.SWITCH_TITLE_ID: re.compile(r"^[0-9A-Fa-f]{16}$"),
    IdentityScheme.PSX_SERIAL: re.compile(r"^[A-Za-z]{2,4}[_-]\d{3,5}(\.\d{2})?$"),
    IdentityScheme.PS2_SERIAL: re.compile(r"^[A-Za-z]{2,4}[_-]\d{3,5}(\.\d{2})?$"),
    IdentityScheme.GC_GAME_ID: re.compile(r"^[A-Za-z0-9]{4}[A-Za-z0-9]{2}$"),
    IdentityScheme.WII_GAME_ID: re.compile(r"^[A-Za-z0-9]{4}[A-Za-z0-9]{2}$"),
    IdentityScheme.PS3_TITLE_ID: re.compile(r"^[A-Za-z0-9]{4,9}$"),
    IdentityScheme.WIIU_PRODUCT_ID: re.compile(r"^[A-Za-z0-9]{4,9}$"),
    IdentityScheme.PS2_ELF_CRC32: re.compile(r"^[0-9A-Fa-f]{8}$"),
    IdentityScheme.UNKNOWN: re.compile(r"^.*$", re.DOTALL),
}

#: Plataformas do catálogo (slugs de platform_manifests) compatíveis com cada
#: esquema. A mesma plataforma pode usar mais de um esquema (ex.: PS2 tem
#: serial e CRC32 do ELF).
_SCHEME_PLATFORMS: dict[IdentityScheme, frozenset[str]] = {
    IdentityScheme.SWITCH_TITLE_ID: frozenset({"switch"}),
    IdentityScheme.PSX_SERIAL: frozenset({"playstation"}),
    IdentityScheme.PS2_SERIAL: frozenset({"playstation-2"}),
    IdentityScheme.GC_GAME_ID: frozenset({"nintendo-console"}),
    IdentityScheme.WII_GAME_ID: frozenset({"nintendo-console"}),
    IdentityScheme.PS3_TITLE_ID: frozenset({"playstation-3"}),
    IdentityScheme.WIIU_PRODUCT_ID: frozenset({"wii-u"}),
    IdentityScheme.PS2_ELF_CRC32: frozenset({"playstation-2"}),
    IdentityScheme.UNKNOWN: frozenset(),
}


def scheme_for_platform(platform: str) -> tuple[IdentityScheme, ...]:
    """Esquemas relevantes para uma plataforma, em ordem de preferência."""
    return tuple(scheme for scheme, platforms in _SCHEME_PLATFORMS.items() if platform in platforms)


def validate_identity_value(scheme: IdentityScheme, value: str) -> bool:
    """Valida um valor contra o esquema; ``UNKNOWN`` sempre falha."""
    if scheme is IdentityScheme.UNKNOWN:
        return False
    if not isinstance(value, str) or not 1 <= len(value) <= _MAX_VALUE_LENGTH:
        return False
    pattern = _SCHEME_PATTERNS.get(scheme)
    return pattern is not None and pattern.fullmatch(value) is not None


@dataclass(frozen=True)
class GameIdentity:
    """Identidade de título: plataforma + esquema + valor validado.

    É este tipo que substitui o regex de 16 hex do schema
    ``known-good-profile-v1``: o catálogo indexa por ``GameIdentity`` e o
    Switch continua sendo um esquema entre os demais.
    """

    platform: str
    scheme: IdentityScheme
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.platform, str) or not self.platform:
            raise ValueError("platform precisa ser um slug não vazio")
        if not isinstance(self.scheme, IdentityScheme):
            raise ValueError("scheme precisa ser IdentityScheme")
        if not isinstance(self.value, str) or not 1 <= len(self.value) <= _MAX_VALUE_LENGTH:
            raise ValueError("value precisa ser string de 1..64 chars")
        if self.scheme is not IdentityScheme.UNKNOWN and not validate_identity_value(
            self.scheme, self.value
        ):
            raise ValueError(f"valor {self.value!r} não é válido para {self.scheme.value}")

    @classmethod
    def switch(cls, title_id: str) -> GameIdentity:
        """Identidade de título do Switch a partir do Title ID legado."""
        return GameIdentity("switch", IdentityScheme.SWITCH_TITLE_ID, title_id)

    @classmethod
    def unknown(cls, platform: str, value: str = "") -> GameIdentity:
        """Identidade não identificada; a plataforma permanece informativa."""
        return cls(platform, IdentityScheme.UNKNOWN, value or platform)

    @property
    def is_known(self) -> bool:
        return self.scheme is not IdentityScheme.UNKNOWN

    def lookup_key(self) -> str:
        """Chave de indexação canônica (case normalized conforme o esquema)."""
        if self.scheme in {
            IdentityScheme.SWITCH_TITLE_ID,
            IdentityScheme.PS3_TITLE_ID,
            IdentityScheme.WIIU_PRODUCT_ID,
            IdentityScheme.PS2_ELF_CRC32,
        }:
            return self.value.upper()
        if self.scheme in {IdentityScheme.GC_GAME_ID, IdentityScheme.WII_GAME_ID}:
            return self.value.upper()
        return self.value.upper()

    def matches(self, other: GameIdentity) -> bool:
        """Compara duas identidades da mesma plataforma pelo valor canônico."""
        return self.platform == other.platform and self.lookup_key() == other.lookup_key()

    def to_dict(self) -> dict[str, str | None]:
        return {
            "platform": self.platform,
            "scheme": self.scheme.value if self.scheme is not IdentityScheme.UNKNOWN else None,
            "value": self.value if self.scheme is not IdentityScheme.UNKNOWN else None,
        }


# --- Extração pura por plataforma (bytes -> identidade) -----------------------
#
# Estas funções recebem bytes já lidos e devolvem a identidade validada ou
# ``None``. Nenhuma faz I/O: o adapter lê os bytes (via core.fs) e as chama.
# Arquivo truncado, comprimido ou com offset inesperado nunca levanta —
# devolvem ``None`` e o chamador produz o diagnóstico.


def _serial_from_volume_id(data: bytes) -> str | None:
    """Serial de PS1/PS2 a partir do volume identifier do PVD ISO9660.

    O campo tem 32 bytes no PVD (offset 0x20). Seriais reais são
    tipo ``SLUS_005.55``; títulos longos ocupam o campo inteiro. A regra:
    remover padding/versão de arquivo (``;1``) e tentar o token inicial.
    """
    raw = data.split(b"\x00")[0].rstrip()
    if b";" in raw:
        raw = raw.split(b";")[0]
    token = raw.strip().decode("ascii", errors="ignore")
    if validate_identity_value(IdentityScheme.PS2_SERIAL, token):
        return token.upper()
    first = token.split()[0] if token.split() else ""
    if validate_identity_value(IdentityScheme.PS2_SERIAL, first):
        return first.upper()
    return None


def identity_from_ps1_ps2_volume_id(data: bytes, *, platform: str) -> GameIdentity | None:
    """Identidade PS1/PS2 pelo volume identifier (32 bytes do PVD)."""
    serial = _serial_from_volume_id(data)
    if serial is None:
        return None
    scheme = IdentityScheme.PS2_SERIAL if platform == "playstation-2" else IdentityScheme.PSX_SERIAL
    return GameIdentity(platform, scheme, serial)


def identity_from_gc_wii_disc_id(data: bytes, *, is_wii: bool) -> GameIdentity | None:
    """Identidade GC/Wii pelos 6 bytes iniciais do header do disco.

    Layout: 4 chars de gamecode + 2 chars de região/país (ex.: ``GM8E01``).
    A distinção GC/Wii vem do magic do disco, decidida pelo chamador.
    """
    if len(data) < 6:
        return None
    disc_id = data[:6].decode("ascii", errors="ignore").upper()
    scheme = IdentityScheme.WII_GAME_ID if is_wii else IdentityScheme.GC_GAME_ID
    if not validate_identity_value(scheme, disc_id):
        return None
    platform = "nintendo-console"
    return GameIdentity(platform, scheme, disc_id)


_PS3_SFB_MAGIC = b"..S"


def identity_from_ps3_sfb(data: bytes) -> GameIdentity | None:
    """Identity PS3 a partir do arquivo ``PS3_DISC.SFB`` da raiz do ISO.

    Formato: magic ``..S`` em 0x00 e ``TITLE_ID`` (16 bytes ASCII) em 0x10.
    A validação exige o magic — um arquivo qualquer no ISO não vira identity.
    """
    if len(data) < 0x20 or not data.startswith(_PS3_SFB_MAGIC):
        return None
    region = data[0x10 : 0x10 + 16]
    candidate = region.split(b"\x00")[0].decode("ascii", errors="ignore").strip().upper()
    if validate_identity_value(IdentityScheme.PS3_TITLE_ID, candidate):
        return GameIdentity("playstation-3", IdentityScheme.PS3_TITLE_ID, candidate)
    fallback = re.search(rb"[A-Z0-9]{4,9}", data[:0x60])
    if fallback is not None:
        candidate = fallback.group(0).decode("ascii").upper()
        if validate_identity_value(IdentityScheme.PS3_TITLE_ID, candidate):
            return GameIdentity("playstation-3", IdentityScheme.PS3_TITLE_ID, candidate)
    return None


_WIIU_PRODUCT_ID_RE = re.compile(r"<product_id>([^<]+)</product_id>", re.IGNORECASE)


def identity_from_wiiu_meta_xml(text: str) -> GameIdentity | None:
    """Identidade Wii U pelo ``product_id`` do ``meta.xml``.

    Regex em vez de parser XML de propósito: o arquivo pode ser de terceiros e
    um parser XML abriria superfície de ataque (entidades, XXE) sem benefício.
    """
    match = _WIIU_PRODUCT_ID_RE.search(text)
    if match is None:
        return None
    candidate = match.group(1).strip().upper()
    if validate_identity_value(IdentityScheme.WIIU_PRODUCT_ID, candidate):
        return GameIdentity("wii-u", IdentityScheme.WIIU_PRODUCT_ID, candidate)
    return None


def identity_from_ps2_elf_crc32(crc: int) -> GameIdentity:
    """Identidade PS2 pelo CRC32 do ELF bootável (formato usado pelo PCSX2)."""
    value = format(crc & 0xFFFFFFFF, "08X")
    if not validate_identity_value(IdentityScheme.PS2_ELF_CRC32, value):
        raise ValueError(f"CRC32 ELF inválido: {value!r}")
    return GameIdentity("playstation-2", IdentityScheme.PS2_ELF_CRC32, value)
