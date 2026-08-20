from __future__ import annotations

import re
import zlib
from collections.abc import Callable, Iterator
from pathlib import Path

from steamzero.core import fs
from steamzero.domain.game_identity import (
    GameIdentity,
    identity_from_gc_wii_disc_id,
    identity_from_ps1_ps2_volume_id,
    identity_from_ps2_elf_crc32,
    identity_from_ps3_sfb,
    identity_from_wiiu_meta_xml,
)
from steamzero.ports import RomFormatParser

_NSP_EXTENSIONS = frozenset({".nsp", ".nsz"})
_XCI_EXTENSIONS = frozenset({".xci", ".xcz"})
_NRO_EXTENSION = ".nro"
_ALLOWED_EXTENSIONS = _NSP_EXTENSIONS | _XCI_EXTENSIONS | {_NRO_EXTENSION}
_TITLE_ID_RE = re.compile(r"0100[0-9A-Fa-f]{12}")
_SCENE_BRACKETS = re.compile(r"\s*\([^)]*\)\s*")


class NspParser(RomFormatParser):
    def supports(self, path: Path) -> bool:
        return path.suffix.lower() in _NSP_EXTENSIONS

    def parse_title_id(self, path: Path) -> str | None:
        match = _TITLE_ID_RE.search(path.name)
        if match:
            return match.group(0).upper()
        return _title_id_from_parent(path)

    def parse_content_kind(self, path: Path) -> str:
        stem = _clean_stem(path)
        if "[DLC]" in stem or "[Dlc]" in stem:
            return "dlc"
        if "[UPD]" in stem or "[Upd]" in stem or "update" in stem.lower():
            return "update"
        tid = self.parse_title_id(path)
        if tid and _is_update_tid(tid):
            return "update"
        if tid and _is_dlc_tid(tid):
            return "dlc"
        return "base"

    def parse_version(self, path: Path) -> str | None:
        stem = _clean_stem(path)
        m = re.search(r"v(\d+\.\d+|\d+)", stem)
        return m.group(1) if m else None


class XciParser(RomFormatParser):
    def supports(self, path: Path) -> bool:
        return path.suffix.lower() in _XCI_EXTENSIONS

    def parse_title_id(self, path: Path) -> str | None:
        match = _TITLE_ID_RE.search(path.name)
        if match:
            return match.group(0).upper()
        return _title_id_from_parent(path)

    def parse_content_kind(self, path: Path) -> str:
        stem = _clean_stem(path)
        if "[UPD]" in stem or "[Upd]" in stem or "update" in stem.lower():
            return "update"
        if "[DLC]" in stem or "[Dlc]" in stem:
            return "dlc"
        tid = self.parse_title_id(path)
        if tid and _is_update_tid(tid):
            return "update"
        if tid and _is_dlc_tid(tid):
            return "dlc"
        return "base"

    def parse_version(self, path: Path) -> str | None:
        stem = _clean_stem(path)
        m = re.search(r"v(\d+\.\d+|\d+)", stem)
        return m.group(1) if m else None


class NroParser(RomFormatParser):
    def supports(self, path: Path) -> bool:
        return path.suffix.lower() == _NRO_EXTENSION

    def parse_title_id(self, path: Path) -> str | None:
        return _title_id_from_parent(path)

    def parse_content_kind(self, path: Path) -> str:
        return "base"

    def parse_version(self, path: Path) -> str | None:
        return None


def _clean_stem(path: Path) -> str:
    return _SCENE_BRACKETS.sub("", path.stem).strip()


def _title_id_from_parent(path: Path) -> str | None:
    for parent in path.parents:
        match = _TITLE_ID_RE.search(parent.name)
        if match:
            return match.group(0).upper()
    return None


def _is_update_tid(tid: str) -> bool:
    suffix = int(tid[-2:], 16)
    return 0x800 <= suffix < 0xFFF


def _is_dlc_tid(tid: str) -> bool:
    suffix = int(tid[-4:-2], 16)
    return suffix >= 0x80


def all_parsers() -> list[RomFormatParser]:
    return [NspParser(), XciParser(), NroParser()]


def allowed_extension(path: Path) -> bool:
    return path.suffix.lower() in _ALLOWED_EXTENSIONS


# ===========================================================================
# Identidade de título fora do Switch (Onda 1)
#
# Lê cabeçalhos de ROM por plataforma e produz ``GameIdentity`` ou ``None``
# com diagnóstico estruturado (nunca exceção, nunca falso positivo). Toda
# leitura passa por ``core.fs.read_at`` (AC-LB-01 / boundaries). Formatos
# comprimidos (rvz/chd/wud/wux/zip/7z) e arquivos truncados degradam para
# ``unknown`` com a causa no diagnóstico.
# ===========================================================================

ReadAt = Callable[[int, int], bytes]

ReadResult = tuple[GameIdentity | None, str]

#: Formatos compactados/empacotados fora da faixa de leitura direta de header.
_COMPRESSED_SUFFIXES = frozenset({".rvz", ".chd", ".wud", ".wux", ".zip", ".7z", ".nkit"})


def read_game_identity(
    path: Path,
    *,
    platform: str | None,
    read_at: ReadAt | None = None,
) -> ReadResult:
    """Lê a identidade de título da ROM para a plataforma declarada.

    ``read_at`` é injetável nos testes; default usa ``core.fs.read_at``.
    Qualquer falha de I/O degrada para ``unknown`` com diagnóstico — a
    identidade é oportunista e nunca impede scan nem lançamento.
    """
    if platform is None:
        return None, "no-platform"
    reader = read_at or _make_fs_reader(path)
    try:
        # Wii U: o meta.xml é irmão da ROM (não lê o arquivo de ROM), então
        # vale mesmo para WUD/WUX — o guard de comprimidos é para leitura de
        # header, não para o índice declarativo.
        if platform == "wii-u":
            return _read_wiiu(path)
        if path.suffix.lower() in _COMPRESSED_SUFFIXES:
            return None, "compressed-format"
        if platform in {"playstation", "playstation-2"}:
            return _read_ps1_ps2(path, platform, reader)
        if platform == "nintendo-console":
            return _read_gc_wii(path, reader)
        if platform == "playstation-3":
            return _read_ps3(path, reader)
    except OSError:
        return None, "read-failed"
    return None, "no-reader"


def _make_fs_reader(path: Path) -> ReadAt:
    def read_at(offset: int, length: int) -> bytes:
        return fs.read_at(path, offset, length)

    return read_at


def _read_ps1_ps2(path: Path, platform: str, read_at: ReadAt) -> ReadResult:
    pvd = read_at(_ISO_PVD_OFFSET, _ISO_PVD_LENGTH)
    if len(pvd) < 0x100 or pvd[1:6] != b"CD001":
        return None, "not-iso9660"
    volume_id = pvd[_ISO_VOLUME_ID_OFFSET : _ISO_VOLUME_ID_OFFSET + 32]
    identity = identity_from_ps1_ps2_volume_id(volume_id, platform=platform)
    if identity is not None:
        return identity, "pvd-serial"
    if platform == "playstation-2":
        crc = _ps2_elf_crc32(path, read_at)
        if crc is not None:
            return identity_from_ps2_elf_crc32(crc), "elf-crc32"
    return None, "pvd-no-serial"


# ISO9660: PVD no setor 16; volume identifier (32 bytes) em 0x20.
_ISO_PVD_OFFSET = 0x8000
_ISO_PVD_LENGTH = 2048
_ISO_VOLUME_ID_OFFSET = 0x20

# Limites defensivos de leitura do ISO9660 (conteúdo pode ser de terceiros).
_MAX_DIRECTORY_BYTES = 8 * 1024 * 1024
_MAX_FILE_BYTES = 64 * 1024 * 1024
_MAX_DIR_DEPTH = 3
_MAX_DIR_RECORDS = 8192


def _iso_root_record(pvd: bytes) -> tuple[int, int] | None:
    """Extent e tamanho do diretório raiz (registro em 156 no PVD)."""
    if len(pvd) < 0x9C + 34:
        return None
    record_length = pvd[0x9C]
    if record_length < 34:
        return None
    extent = int.from_bytes(pvd[0x9E:0xA6], "little")
    size = int.from_bytes(pvd[0xA6:0xAE], "little")
    if size > _MAX_DIRECTORY_BYTES:
        return None
    return extent, size


def _iter_directory_records(data: bytes) -> Iterator:
    """Itera registros de diretório ISO9660; retorna (nome, flags, extent, size)."""
    pos = 0
    while pos < len(data):
        record_length = data[pos]
        if record_length == 0:
            # Alinhamento de setor: zeros até a fronteira de 2048.
            pos += 2048 - (pos % 2048)
            continue
        if record_length < 34 or pos + record_length > len(data):
            return
        name_length = data[pos + 32]
        if pos + 33 + name_length > len(data):
            return
        name = data[pos + 33 : pos + 33 + name_length]
        flags = data[pos + 25]
        extent = int.from_bytes(data[pos + 2 : pos + 10], "little")
        size = int.from_bytes(data[pos + 10 : pos + 18], "little")
        yield name, flags, extent, size
        pos += record_length


def _iso_find_files(
    path: Path,
    read_at: ReadAt,
    wanted: frozenset[str],
    *,
    max_bytes: int = _MAX_FILE_BYTES,
) -> dict[str, bytes]:
    """Localiza e lê arquivos por nome no ISO9660 (raiz + profundidade 3).

    Nomes de arquivo são comparados case-insensitive; multi-extent é ignorado
    (primeiro extent vale). Resultado vazio (ou None na leitura) é sempre um
    dict — nunca levanta.
    """
    found: dict[str, bytes] = {}
    try:
        pvd = read_at(_ISO_PVD_OFFSET, _ISO_PVD_LENGTH)
        if len(pvd) < 0x100 or pvd[1:6] != b"CD001":
            return found
        root = _iso_root_record(pvd)
        if root is None:
            return found
        extents = [(root[0], root[1], 0)]
        seen_extents: set[tuple[int, int]] = set()
        while extents and len(found) < len(wanted):
            extent, size, depth = extents.pop(0)
            if not size or (extent, size) in seen_extents or depth > _MAX_DIR_DEPTH:
                continue
            seen_extents.add((extent, size))
            data = read_at(extent * 2048, min(size, _MAX_DIRECTORY_BYTES + 1))
            if len(data) < min(size, _MAX_DIRECTORY_BYTES + 1) and len(data) < size:
                continue
            for name, flags, child_extent, child_size in _iter_directory_records(data):
                if not name or name in {b"\x00", b"\x01"}:
                    continue
                if child_size > _MAX_FILE_BYTES + 1:
                    continue
                base = Path(name.decode("ascii", errors="ignore")).name
                key = base.upper()
                if flags & 0x02:
                    extents.append((child_extent, child_size, depth + 1))
                    continue
                if key in wanted and key not in found:
                    payload = read_at(child_extent * 2048, min(child_size, max_bytes + 1))
                    found[key] = payload
                    if len(payload) > max_bytes:
                        found[key] = payload[:max_bytes]
        return found
    except OSError:
        return found


def _ps2_elf_crc32(path: Path, read_at: ReadAt) -> int | None:
    """CRC32 do ELF bootável do PS2 (SYSTEM.CNF -> BOOT2)."""
    found = _iso_find_files(path, read_at, frozenset({"SYSTEM.CNF"}), max_bytes=16 * 1024)
    cnf = found.get("SYSTEM.CNF")
    if not cnf:
        return None
    match = re.search(rb"BOOT2\s*=\s*(?:cdrom[0-9]:|hd[0-9]:)?([\\/]?[\w./\\-]+\.elf)", cnf, re.I)
    if match is None:
        return None
    # O caminho do CNF usa separadores de estilo Windows mesmo em ISOs.
    elf_token = match.group(1).split(b"\\")[-1].split(b"/")[-1]
    elf_name = Path(elf_token.decode("ascii", errors="ignore")).name.upper()
    if not elf_name:
        return None
    elfs = _iso_find_files(path, read_at, frozenset({elf_name}))
    payload = elfs.get(elf_name)
    if not payload:
        return None
    return zlib.crc32(payload) & 0xFFFFFFFF


#: Magics de disco (mesmos offsets de ``domain.library``); a distinção
#: GC/Wii é feita por eles — sem magic, o esquema conservador é GC.
_GC_MAGIC = (0x1C, b"\xc2\x33\x9f\x3d")
_WII_MAGIC = (0x18, b"\x5d\x1c\x9e\xa3")


def _read_gc_wii(path: Path, read_at: ReadAt) -> ReadResult:
    header = read_at(0, 0x20)
    if len(header) < 6:
        if read_at(0, 6) != header:
            return None, "truncated-header"
        return None, "truncated-header"
    is_wii: bool | None = None
    for offset, magic in (_WII_MAGIC, _GC_MAGIC):
        if read_at(offset, len(magic)) == magic:
            is_wii = offset == _WII_MAGIC[0]
            break
    identity = identity_from_gc_wii_disc_id(header[:6], is_wii=bool(is_wii))
    if identity is None:
        return None, "invalid-disc-id"
    return identity, "disc-header-magic" if is_wii is not None else "disc-header"


def _read_ps3(path: Path, read_at: ReadAt) -> ReadResult:
    found = _iso_find_files(path, read_at, frozenset({"PS3_DISC.SFB"}), max_bytes=0x100)
    sfb = found.get("PS3_DISC.SFB")
    if sfb is None:
        return None, "no-sfb"
    identity = identity_from_ps3_sfb(sfb)
    if identity is None:
        return None, "sfb-invalid"
    return identity, "sfb-title-id"


def _read_wiiu(path: Path) -> ReadResult:
    """Wii U: ``meta.xml`` irmão da ROM (dumps descriptografados comuns).

    WUD/WUX compactados não têm leitura direta de header — o meta.xml irmão é
    a fonte honesta quando presente; senão ``unknown``.
    """
    candidates: list[Path] = []
    base = path if path.is_dir() else path.parent
    if base.is_dir():
        for child in base.iterdir():
            if child.is_file() and child.name.casefold() == "meta.xml":
                candidates.append(child)
    if not candidates:
        return None, "no-meta-xml"
    for candidate in candidates:
        try:
            if candidate.is_symlink():
                continue
            text = candidate.read_text(encoding="utf-8", errors="ignore")[: 64 * 1024]
        except OSError:
            continue
        identity = identity_from_wiiu_meta_xml(text)
        if identity is not None:
            return identity, "meta-xml-product-id"
    return None, "meta-xml-no-product-id"
