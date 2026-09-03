# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Store de assets de tema endereçado por conteúdo, com posse derivada.

Temas ES-DE reais pesam de 43 a 463 MB (medido nos cinco temas licenciados em
2026-09-03) e repetem arte entre si: os mesmos ícones de controle, as mesmas
capas de sistema, os mesmos gradientes. Guardar cada tema como uma árvore própria
multiplicaria esse custo por tema instalado.

O store guarda cada arquivo UMA vez, sob o seu próprio SHA-256, e cada tema
guarda apenas o mapa ``caminho lógico -> digest``. Dois temas que compartilham um
ícone compartilham o blob.

**Não existe contador de referências, por decisão.** Um contador é uma segunda
fonte de verdade derivada dos temas instalados; quando desvia — e ele desvia, por
queda no meio de uma escrita, por remoção manual de diretório, por restauração de
backup — o resultado é apagar um blob ainda em uso ou vazar espaço para sempre.
Nenhum dos dois é detectável no momento em que acontece.

Aqui a posse é **derivada**: o conjunto de digests vivos é o que os manifestos
dos temas instalados referenciam, calculado na hora. O store é um cache
reconstruível. Isso dá três propriedades que o contador não dá:

- desinstalar um tema NUNCA quebra outro, porque nada é apagado por remoção;
- rollback não precisa restaurar blob nenhum: o blob nunca saiu;
- o espaço é recuperado por ``collect_garbage``, que é explícito, auditável e
  seguro de rodar a qualquer momento.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from steamzero.core import fs
from steamzero.core.errors import SteamZeroError

#: Um digest hexadecimal de SHA-256, e nada além disso. O nome do blob vem de
#: manifesto de terceiro; validar a forma é o que impede que ``../../etc/passwd``
#: vire caminho de blob.
_DIGEST = re.compile(r"^[0-9a-f]{64}$")

#: Prefixo de fragmentação. Um diretório com dezenas de milhares de entradas
#: degrada em qualquer sistema de arquivos; dois caracteres dão 256 baldes.
_SHARD = 2

#: Teto por arquivo. Arte de tema é imagem e vídeo curto; um arquivo maior que
#: isto não é asset de tema e não entra sem revisão.
MAX_ASSET_BYTES = 64 * 1024 * 1024

#: Extensões aceitas. Um tema não traz executável, biblioteca nem script: a
#: fronteira de confiança da AGENTS §10 é exatamente esta lista.
ALLOWED_SUFFIXES = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".svg",
        ".gif",
        ".mp4",
        ".mkv",
        ".webm",
        ".wav",
        ".ogg",
        ".mp3",
        ".ttf",
        ".otf",
        ".xml",
    }
)


def digest_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class StoredAsset:
    """Um asset já no store, com o caminho lógico que o tema usa para achá-lo."""

    logical_path: str
    digest: str
    size: int

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.logical_path, "digest": self.digest, "size": self.size}


class ThemeAssetStore:
    """Store endereçado por conteúdo sob um diretório raiz.

    A raiz é injetada em vez de lida de ``paths`` para que o teste use um
    diretório temporário sem tocar no estado do usuário — o mesmo padrão do
    resto do domínio.
    """

    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    def root(self) -> Path:
        return self._root

    def blob_path(self, digest: str) -> Path:
        if not _DIGEST.match(digest):
            raise SteamZeroError("E-THEME-UNSAFE", detail=f"digest inválido: {digest!r}")
        return self._root / "blobs" / digest[:_SHARD] / digest

    def has(self, digest: str) -> bool:
        return self.blob_path(digest).is_file()

    def put(self, logical_path: str, payload: bytes) -> StoredAsset:
        """Grava um asset, devolvendo o registro para o manifesto do tema.

        Idempotente por construção: se o blob já existe, o conteúdo é
        necessariamente igual — é o mesmo SHA-256 — e regravar seria desperdício.
        """
        if len(payload) > MAX_ASSET_BYTES:
            raise SteamZeroError(
                "E-THEME-LIMIT",
                detail=f"asset {logical_path!r} tem {len(payload)} bytes; teto é {MAX_ASSET_BYTES}",
            )
        suffix = Path(logical_path).suffix.casefold()
        if suffix not in ALLOWED_SUFFIXES:
            raise SteamZeroError(
                "E-THEME-UNSAFE",
                detail=f"extensão não permitida em asset de tema: {logical_path!r}",
            )
        digest = digest_bytes(payload)
        target = self.blob_path(digest)
        if not target.is_file():
            fs.write_atomic(target, payload)
        return StoredAsset(logical_path=logical_path, digest=digest, size=len(payload))

    def read(self, digest: str) -> bytes:
        path = self.blob_path(digest)
        if not path.is_file():
            raise SteamZeroError("E-THEME-NOT-FOUND", detail=f"blob ausente: {digest}")
        return path.read_bytes()

    def iter_blobs(self) -> Iterator[tuple[str, int]]:
        """Enumera os blobs presentes, com tamanho. Ignora nomes fora do padrão."""
        blobs = self._root / "blobs"
        if not blobs.is_dir():
            return
        for shard in sorted(blobs.iterdir()):
            if not shard.is_dir():
                continue
            for entry in sorted(shard.iterdir()):
                if entry.is_file() and _DIGEST.match(entry.name):
                    yield entry.name, entry.stat().st_size

    def usage(self) -> dict[str, Any]:
        blobs = list(self.iter_blobs())
        return {
            "blobs": len(blobs),
            "bytes": sum(size for _, size in blobs),
        }

    def collect_garbage(
        self, live_digests: Iterable[str], *, dry_run: bool = True
    ) -> dict[str, Any]:
        """Remove blobs que nenhum tema instalado referencia.

        ``live_digests`` é calculado dos manifestos — a única fonte de verdade.
        O padrão é ``dry_run``: apagar dado do usuário é o tipo de ação que deve
        ser pedida, não presumida, e o relatório permite conferir antes.
        """
        live = {digest for digest in live_digests if _DIGEST.match(digest)}
        removed: list[str] = []
        reclaimed = 0
        for digest, size in self.iter_blobs():
            if digest in live:
                continue
            removed.append(digest)
            reclaimed += size
            if not dry_run:
                fs.remove_file(self.blob_path(digest))
        return {
            "dryRun": dry_run,
            "liveDigests": len(live),
            "orphans": len(removed),
            "reclaimedBytes": reclaimed,
            "removed": removed[:64],
        }

    def verify(self, live_digests: Iterable[str]) -> dict[str, Any]:
        """Confere que todo digest referenciado existe e confere o conteúdo.

        Detecta as duas falhas que quebram um tema em silêncio: blob ausente
        (referência pendurada) e blob corrompido (conteúdo não bate com o nome).
        """
        missing: list[str] = []
        corrupt: list[str] = []
        for digest in {d for d in live_digests if _DIGEST.match(d)}:
            path = self.blob_path(digest)
            if not path.is_file():
                missing.append(digest)
                continue
            if digest_bytes(path.read_bytes()) != digest:
                corrupt.append(digest)
        return {
            "ok": not missing and not corrupt,
            "missing": sorted(missing),
            "corrupt": sorted(corrupt),
        }


def live_digests(manifests: Iterable[Mapping[str, Any]]) -> set[str]:
    """Digests vivos: a união do que os temas instalados referenciam.

    Esta função é a definição de "em uso" no sistema. Se um dia houver um segundo
    lugar que responda a mesma pergunta, o store volta a ter duas fontes de
    verdade — que é precisamente o que o desenho evita.
    """
    out: set[str] = set()
    for manifest in manifests:
        assets = manifest.get("assets")
        if not isinstance(assets, dict):
            continue
        for entry in assets.values():
            digest = entry.get("digest") if isinstance(entry, dict) else entry
            if isinstance(digest, str) and _DIGEST.match(digest):
                out.add(digest)
    return out


def load_installed_manifests(themes_root: Path) -> list[dict[str, Any]]:
    """Lê os manifestos dos temas instalados, tolerando um diretório corrompido.

    Um manifesto ilegível NÃO pode fazer o conjunto vivo encolher em silêncio:
    isso transformaria um arquivo corrompido em coleta de lixo dos blobs de um
    tema saudável. O erro sobe.
    """
    if not themes_root.is_dir():
        return []
    manifests: list[dict[str, Any]] = []
    for entry in sorted(themes_root.iterdir()):
        manifest_path = entry / "theme.json"
        if not entry.is_dir() or not manifest_path.is_file():
            continue
        try:
            raw = json.loads(manifest_path.read_bytes())
        except (OSError, json.JSONDecodeError) as exc:
            raise SteamZeroError(
                "E-THEME-MANIFEST",
                detail=f"manifesto ilegível em {entry.name}; recusando calcular assets vivos",
            ) from exc
        if isinstance(raw, dict):
            manifests.append(raw)
    return manifests
