# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Leitura segura de tarballs, em fluxo e sem materializar a árvore.

Irmão de ``safezip``, com as mesmas defesas e duas a mais que o formato tar
exige: ele sabe descrever **hardlinks** e **nós de dispositivo**, que o zip não
sabe. Um tar hostil que declare ``/dev/sda`` ou um hardlink para
``/etc/shadow`` precisa ser recusado no cabeçalho, antes de qualquer escrita.

**Por que em fluxo.** Um tema ES-DE tem de 60 a 150 MB e ~92% disso é arte por
sistema. Extrair para uma árvore temporária e só então ingerir gastaria o dobro
do espaço e perderia a deduplicação: dois temas com o mesmo ícone escreveriam o
arquivo duas vezes antes de alguém notar que é o mesmo. Aqui cada membro é
entregue como bytes ao chamador, que decide o destino — e o chamador é o store
endereçado por conteúdo, que grava uma vez só.

Nada é escrito por este módulo. Ele lê, valida e entrega.
"""

from __future__ import annotations

import tarfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from steamzero.core import fs
from steamzero.core.errors import SteamZeroError


@dataclass(frozen=True)
class SafeTarLimits:
    max_entries: int = 20_000
    max_total_bytes: int = 512 * 1024 * 1024
    max_entry_bytes: int = 64 * 1024 * 1024
    max_depth: int = 16


DEFAULT_LIMITS = SafeTarLimits()


@dataclass(frozen=True)
class TarMember:
    """Um arquivo regular já validado, com o caminho relativo à raiz do tema."""

    path: str
    payload: bytes

    @property
    def size(self) -> int:
        return len(self.payload)


def _strip_root(name: str, strip_components: int) -> str | None:
    """Remove os primeiros componentes do caminho.

    Tarballs de forge embrulham tudo em ``<repo>-<commit>/``. Sem remover, todo
    caminho lógico carregaria o commit e o mesmo arquivo em duas versões do
    tema pareceria dois arquivos diferentes — o que anularia a deduplicação
    justamente entre as versões que mais se repetem.
    """
    parts = PurePosixPath(name).parts
    if len(parts) <= strip_components:
        return None
    return str(PurePosixPath(*parts[strip_components:]))


def iter_members(
    tar_path: Path,
    *,
    limits: SafeTarLimits = DEFAULT_LIMITS,
    strip_components: int = 0,
    allowed_suffixes: frozenset[str] | None = None,
) -> Iterator[TarMember]:
    """Percorre os arquivos regulares do tar, recusando tudo que não seja um.

    ``allowed_suffixes`` filtra por extensão ANTES de ler o conteúdo: num tema de
    150 MB, a maior parte do que não interessa nem chega a ser lida.

    Um membro fora do conjunto permitido é **pulado**, não fatal — um tema traz
    README, licença e captura de tela, e recusar o pacote inteiro por causa deles
    seria inútil. O que é fatal é o que denuncia hostilidade: travessia, caminho
    absoluto, link e nó de dispositivo.
    """
    # O try cobre a abertura E a iteração: um tar que corrompe no meio da leitura
    # falha do mesmo jeito que um que nem abre, e o chamador não deveria precisar
    # distinguir dois erros para a mesma causa.
    try:
        with tarfile.open(tar_path, mode="r:*") as archive:
            yield from _iter_validated(archive, limits, strip_components, allowed_suffixes)
    except tarfile.TarError as exc:
        raise SteamZeroError("E-CONTENT-UNSAFE-ARCHIVE", detail=f"tarball ilegível: {exc}") from exc


def _iter_validated(
    archive: tarfile.TarFile,
    limits: SafeTarLimits,
    strip_components: int,
    allowed_suffixes: frozenset[str] | None,
) -> Iterator[TarMember]:
    seen = 0
    total = 0
    for info in archive:
        seen += 1
        if seen > limits.max_entries:
            raise SteamZeroError(
                "E-CONTENT-UNSAFE-ARCHIVE",
                detail=f"contagem de entradas > {limits.max_entries}",
            )
        # Link e nó de dispositivo são recusados pelo CABEÇALHO: o tar os
        # descreve sem carregar conteúdo, então esperar pela leitura seria
        # esperar por algo que nunca chega.
        if info.issym() or info.islnk():
            raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail=f"link em archive: {info.name!r}")
        if info.ischr() or info.isblk() or info.isfifo() or info.isdev():
            raise SteamZeroError(
                "E-CONTENT-UNSAFE-PATH",
                detail=f"nó de dispositivo em archive: {info.name!r}",
            )
        if info.isdir():
            continue
        if not info.isfile():
            raise SteamZeroError(
                "E-CONTENT-UNSAFE-PATH",
                detail=f"entrada que não é arquivo regular: {info.name!r}",
            )

        stripped = _strip_root(info.name, strip_components)
        if stripped is None:
            continue
        # Travessia, absoluto e NUL: a mesma porta usada pelo safezip.
        relative = fs.validate_relative_entry(stripped)
        if len(relative.parts) > limits.max_depth:
            raise SteamZeroError(
                "E-CONTENT-UNSAFE-ARCHIVE", detail=f"profundidade > {limits.max_depth}"
            )
        if allowed_suffixes is not None and relative.suffix.casefold() not in allowed_suffixes:
            continue
        if info.size > limits.max_entry_bytes:
            raise SteamZeroError(
                "E-CONTENT-UNSAFE-ARCHIVE",
                detail=f"{relative} declara {info.size} bytes; teto é {limits.max_entry_bytes}",
            )

        handle = archive.extractfile(info)
        if handle is None:
            continue
        payload = handle.read(limits.max_entry_bytes + 1)
        # O tamanho REAL manda: o cabeçalho pode mentir, e é contando bytes
        # lidos que uma bomba é pega.
        if len(payload) > limits.max_entry_bytes:
            raise SteamZeroError(
                "E-CONTENT-UNSAFE-ARCHIVE",
                detail=f"{relative} excede {limits.max_entry_bytes} bytes na leitura",
            )
        total += len(payload)
        if total > limits.max_total_bytes:
            raise SteamZeroError(
                "E-CONTENT-UNSAFE-ARCHIVE",
                detail=f"total extraído > {limits.max_total_bytes} bytes",
            )
        yield TarMember(path=str(relative), payload=payload)
