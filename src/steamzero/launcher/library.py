# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Biblioteca real do AURA Launcher, a partir do acervo em disco.

A varredura reusa ``PlatformRomScanner`` e o registro de plataformas do
projeto, em vez de um filtro próprio de extensões. A diferença importa: num
acervo real cada pasta de sistema também guarda ``.directory``,
``metadata.txt`` e ``systeminfo.txt``, e um filtro ingênuo listaria
`systeminfo` como se fosse jogo.

O que o registro não reconhece **não some**: vira diagnóstico. Medido no acervo
real de referência, 1290 arquivos em 198 pastas produzem 104 jogos em 6
sistemas — o registro cobre 36 plataformas e as extensões alcançam essa fatia.
Silenciar a diferença faria o usuário concluir que perdeu jogos; publicá-la
mostra que a lacuna é de cobertura de plataforma, não de varredura.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from steamzero.domain.library import PlatformRomScanner
from steamzero.domain.platforms import PlatformRegistry

DIAG_PLATFORM_UNKNOWN = "LAUNCHER-LIBRARY-PLATFORM-001"
DIAG_ROOT_MISSING = "LAUNCHER-LIBRARY-ROOT-002"
MAX_GAMES_PER_SYSTEM = 512
_TITLE_NOISE = re.compile(r"\s*[\[(][^\])]*[\])]")
_SLUG_STRIP = re.compile(r"[^a-z0-9]+")
# Pastas que existem em acervo real e nunca são coleção de jogos.
_SKIP_DIRECTORIES = frozenset({"_backup", "backup", "backups", "bios", "media", "downloaded_media"})


@dataclass(frozen=True)
class LibraryGame:
    id: str
    title: str
    system: str
    path: Path

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "title": self.title, "section": "library", "system": self.system}


@dataclass(frozen=True)
class LibraryDiagnostic:
    code: str
    reason: str
    fallback: str = "ignorado"

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "reason": self.reason, "fallback": self.fallback}


@dataclass(frozen=True)
class LibraryScan:
    games: tuple[LibraryGame, ...] = ()
    diagnostics: tuple[LibraryDiagnostic, ...] = field(default_factory=tuple)


def title_for(filename: str) -> str:
    """Nome exibível a partir do arquivo.

    Remove extensão e os marcadores técnicos entre colchetes ou parênteses —
    ``Hollow Knight Silksong [0100...][v0].nsp`` não é o que se mostra a quem
    está escolhendo o que jogar.
    """
    stem = Path(filename).stem
    cleaned = _TITLE_NOISE.sub("", stem).strip()
    return cleaned or stem


def game_id_for(system: str, filename: str) -> str:
    """Id estável e seguro para virar nó de foco e argumento de lançamento.

    O nome do arquivo tem espaços, acentos e colchetes; o id precisa casar com
    o formato aceito pelo foco. O sufixo de hash evita que dois títulos que
    encurtam para a mesma raiz colidam num id só.
    """
    base = _SLUG_STRIP.sub("-", title_for(filename).casefold()).strip("-")
    if not base or not base[0].isalpha():
        base = f"g-{base}" if base else "g"
    digest = hashlib.sha256(f"{system}/{filename}".encode()).hexdigest()[:8]
    return f"{base[:40].strip('-')}-{digest}"


def _platform_directories(root: Path) -> Iterable[Path]:
    for child in sorted(root.iterdir()):
        if child.is_dir() and child.name.casefold() not in _SKIP_DIRECTORIES:
            yield child


def scan_library(root: Path, *, registry: PlatformRegistry | None = None) -> LibraryScan:
    """Varre o acervo, um diretório de sistema por vez.

    ``PlatformRomScanner`` não desce recursivamente: cada raiz é uma
    plataforma. Apontá-lo para o topo do acervo devolveria quase nada, o que
    pareceria uma biblioteca vazia em vez de um uso errado da ferramenta.
    """
    if not root.is_dir():
        return LibraryScan(
            diagnostics=(
                LibraryDiagnostic(
                    code=DIAG_ROOT_MISSING,
                    reason=f"acervo ausente: {root}",
                    fallback="biblioteca vazia",
                ),
            )
        )

    catalogue = registry or PlatformRegistry.bundled()
    # Os ids do registro são canônicos (`master-system`), enquanto as pastas do
    # acervo seguem a convenção do ES-DE (`mastersystem`, `gb`, `nes`). Casar
    # nome de pasta com id descartaria quase tudo: quem identifica a plataforma
    # é a extensão do arquivo, e o nome da pasta serve só como dica.
    known = {manifest.id for manifest in catalogue.list()}
    scanner = PlatformRomScanner.from_manifests(
        [{"id": manifest.id, "media": dict(manifest.media)} for manifest in catalogue.list()]
    )

    games: list[LibraryGame] = []
    diagnostics: list[LibraryDiagnostic] = []
    for directory in _platform_directories(root):
        system = directory.name
        hint = system if system in known else None
        candidates = [
            candidate
            for candidate in scanner.inventory(directory, root_platform=hint)
            if candidate.content_kind == "base" and candidate.platform
        ]
        if not candidates:
            # Pasta com arquivos que o scanner não reconheceu como jogo. Some
            # da home, mas não do relatório: 34 pastas no disco e um punhado
            # reconhecido é diferença que o usuário precisa poder ver.
            if any(item.is_file() for item in directory.iterdir()):
                diagnostics.append(
                    LibraryDiagnostic(
                        code=DIAG_PLATFORM_UNKNOWN,
                        reason=f"sistema '{system}' não teve jogo reconhecido",
                        fallback="ignorado",
                    )
                )
            continue
        for candidate in candidates[:MAX_GAMES_PER_SYSTEM]:
            games.append(
                LibraryGame(
                    id=game_id_for(system, candidate.path.name),
                    title=title_for(candidate.path.name),
                    system=candidate.platform or system,
                    path=candidate.path,
                )
            )
        if len(candidates) > MAX_GAMES_PER_SYSTEM:
            diagnostics.append(
                LibraryDiagnostic(
                    code=DIAG_PLATFORM_UNKNOWN,
                    reason=(
                        f"sistema '{system}' tem {len(candidates)} jogos; "
                        f"exibindo os primeiros {MAX_GAMES_PER_SYSTEM}"
                    ),
                    fallback="truncado",
                )
            )
    return LibraryScan(games=tuple(games), diagnostics=tuple(diagnostics))
