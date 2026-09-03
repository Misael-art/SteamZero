# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Resolução de ``<include>`` de temas ES-DE, com contenção de caminho.

``scene_esde`` compila um XML já completo; quem monta esse XML é este módulo,
porque juntar arquivos é trabalho de disco e o compilador é puro. A separação é
a mesma de ``theme_import_retrofe`` sobre ``scene_retrofe``.

**Por que isto existe.** Medido no xmb-menu em 2026-09-03: compilar só o
``theme.xml`` deixava 311 referências ``${...}`` sem valor e 35 pares numéricos
inválidos — todos consequência de variáveis declaradas em arquivos incluídos.
Com a cadeia resolvida, a cobertura do ponto de entrada real vai a 84%.

**Duas formas de include, e a segunda é a que carrega o tema.**

1. estático — ``<include>./colors.xml</include>``;
2. por sistema — ``<include>./_inc/systems/_metadata-global/${system.theme}.xml</include>``.

A segunda explica a forma dos temas ES-DE: dos 231 XML do xmb-menu, 214 são
metadados por sistema (nome, descrição, cor, tipo de hardware). Ignorá-la
deixaria todo tema sem identidade de sistema.

Contenção: nenhum include escapa da raiz do tema, nenhum symlink é seguido e a
profundidade é limitada. Um tema é dado de terceiro; ``<include>/etc/passwd</include>``
precisa cair antes de ser aberto, não depois.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from steamzero.core.errors import SteamZeroError
from steamzero.domain.scene_esde import SYSTEM_ID, Selection, collect_variables, interpolate

#: Tetos. Um tema hostil não pode virar recursão infinita nem leitura ilimitada.
MAX_INCLUDE_DEPTH = 12
MAX_INCLUDE_FILES = 512
MAX_FILE_BYTES = 8 * 1024 * 1024

#: O marcador de sistema, como aparece no XML de origem.
_SYSTEM_TOKEN = "${system.theme}"  # noqa: S105 - marcador de template, não credencial


@dataclass
class IncludeResult:
    """A árvore montada, com o registro do que foi lido e do que não abriu."""

    root: ET.Element
    included: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    refused: list[str] = field(default_factory=list)
    system_includes: list[str] = field(default_factory=list)
    #: Includes cujo caminho depende de uma variável que a seleção corrente não
    #: define. NÃO é o mesmo que "arquivo ausente", e confundir os dois faz o
    #: relatório culpar um arquivo inexistente em vez da seleção que falta.
    unresolved: list[str] = field(default_factory=list)

    def report(self) -> dict[str, Any]:
        return {
            "included": list(self.included),
            "includedCount": len(self.included),
            "missing": list(self.missing),
            "refused": list(self.refused),
            "systemIncludes": list(self.system_includes),
            "unresolved": list(self.unresolved),
        }


def _contained(candidate: Path, root: Path) -> bool:
    """O caminho resolvido continua dentro da raiz do tema?

    ``resolve()`` colapsa ``..`` e resolve symlink, então esta é a checagem que
    vale — comparar as strings antes de resolver seria burlável por link.
    """
    try:
        candidate.resolve().relative_to(root.resolve())
    except (ValueError, OSError):
        return False
    return True


def _read(path: Path) -> str:
    size = path.stat().st_size
    if size > MAX_FILE_BYTES:
        raise SteamZeroError(
            "E-THEME-LIMIT",
            detail=f"{path.name} tem {size} bytes; teto de include é {MAX_FILE_BYTES}",
        )
    return path.read_text(encoding="utf-8")


def resolve_includes(
    entry: Path,
    *,
    theme_root: Path | None = None,
    system_id: str | None = None,
    selection: Selection | None = None,
) -> IncludeResult:
    """Monta uma árvore ``<theme>`` única a partir do ponto de entrada.

    ``system_id`` escolhe qual arquivo os includes por sistema abrem. Sem ele, o
    include templado é REGISTRADO e não seguido: escolher um sistema por conta
    própria daria ao tema a identidade de um console arbitrário.

    O caminho de um include pode ser ele mesmo uma variável de tema —
    ``<include>${customizationPath}</include>`` no xmb-menu. As variáveis são
    acumuladas conforme os arquivos são lidos, na ordem em que o ES-DE as lê, e
    um alvo que não resolve é classificado como tal em vez de virar "arquivo
    ausente": são problemas diferentes e o segundo culparia o alvo errado.
    """
    root = (theme_root or entry.parent).resolve()
    if system_id is not None and not SYSTEM_ID.match(system_id):
        raise SteamZeroError(
            "E-THEME-UNSAFE", detail=f"identificador de sistema inválido: {system_id!r}"
        )

    result = IncludeResult(root=ET.Element("theme"))
    seen: set[Path] = set()
    variables: dict[str, str] = {}

    def walk(path: Path, depth: int) -> list[ET.Element]:
        if depth > MAX_INCLUDE_DEPTH:
            result.refused.append(f"{path.name}: profundidade máxima de include atingida")
            return []
        if len(result.included) >= MAX_INCLUDE_FILES:
            result.refused.append("limite de arquivos incluídos atingido")
            return []
        resolved = path.resolve()
        if resolved in seen:
            # Ciclo ou inclusão repetida: o ES-DE também lê uma vez só.
            return []
        if path.is_symlink() or not _contained(path, root):
            result.refused.append(f"{path.name}: fora da raiz do tema ou symlink")
            return []
        if not path.is_file():
            relative = str(path.relative_to(root)) if _contained(path, root) else path.name
            result.missing.append(relative)
            return []

        seen.add(resolved)
        try:
            parsed = ET.fromstring(_read(path))  # noqa: S314 - contido e limitado acima
        except ET.ParseError as exc:
            result.refused.append(f"{path.name}: XML inválido ({exc})")
            return []
        except (OSError, UnicodeDecodeError) as exc:
            result.refused.append(f"{path.name}: ilegível ({exc})")
            return []
        if parsed.tag != "theme":
            # `capabilities.xml` e afins têm outra raiz e não são layout.
            result.refused.append(f"{path.name}: raiz <{parsed.tag}>, não <theme>")
            return []

        result.included.append(str(resolved.relative_to(root)))
        # As variáveis deste arquivo passam a valer para os includes seguintes,
        # que é a ordem em que o ES-DE as lê.
        variables.update(collect_variables(parsed, selection))

        collected: list[ET.Element] = []
        for child in parsed:
            if child.tag != "include":
                collected.append(child)
                continue
            raw_target = (child.text or "").strip()
            if not raw_target:
                continue
            target = raw_target
            if _SYSTEM_TOKEN in target:
                result.system_includes.append(target)
                if system_id is None:
                    continue
                target = target.replace(_SYSTEM_TOKEN, system_id)
            target, unresolved = interpolate(target, variables)
            if unresolved:
                result.unresolved.append(f"{raw_target} (variável não definida: {unresolved})")
                continue
            collected.extend(walk((path.parent / target), depth + 1))
        return collected

    result.root.extend(walk(entry, 0))
    return result


def available_systems(theme_root: Path) -> list[str]:
    """Sistemas para os quais o tema traz metadado próprio.

    Derivado dos arquivos que os includes templados endereçam, em vez de uma
    lista fixa: um tema que ganhar um console novo passa a oferecê-lo sem que
    este módulo mude. Nomes que não casam com ``SYSTEM_ID`` ficam de fora — é a
    mesma fronteira que impede o template de virar travessia.
    """
    root = theme_root.resolve()
    found: set[str] = set()
    for directory in sorted(root.rglob("_metadata-global")):
        if not directory.is_dir() or not _contained(directory, root):
            continue
        for entry in directory.glob("*.xml"):
            if entry.is_symlink() or not entry.is_file():
                continue
            name = entry.stem
            if SYSTEM_ID.match(name) and not name.startswith("_"):
                found.add(name)
    return sorted(found)
