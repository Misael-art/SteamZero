# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Exportação para ``gamelist.xml`` do ES-DE (frente A1).

Um `gamelist.xml` costuma ter curadoria manual acumulada — descrições
reescritas, favoritos, jogos marcados para criança. Exportar por cima disso
sem cuidado apaga trabalho que não é nosso. Três recusas dão a forma do módulo:

1. **Não apagamos jogo que não conhecemos.** Entrada existente sem registro
   correspondente é mantida intacta. Exportar 10 jogos para um arquivo com 500
   não pode devolver um arquivo com 10.
2. **Não apagamos campo que não modelamos.** ``<favorite>``, ``<kidgame>``,
   ``<playcount>`` e qualquer outra tag desconhecida sobrevivem à atualização;
   só as tags que o ``GameRecord`` representa são reescritas.
3. **Não sobrescrevemos o que não entendemos.** XML alvo malformado ou com DTD
   é recusado, não substituído: o parser pode estar diante de um arquivo válido
   que ele não sabe ler, e sobrescrever destruiria a curadoria.

A escala do ``rating`` é invertida aqui: o contrato usa 0..100 e o ES-DE usa
fração 0..1. É o espelho exato do bug que passou pelo schema na importação, e
por isso tem teste com valor calculado à mão.

Domínio puro: nada é lido nem escrito em disco. O chamador entrega o XML atual
(ou ``None``) e recebe um plano.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Sequence

from steamzero.domain.game_record import GameRecord, MediaRole
from steamzero.domain.metadata_export._plan import ExportPlan, decide, refusal
from steamzero.domain.metadata_import._common import PathRefused, resolve_path

_DOCTYPE = re.compile(r"<!(DOCTYPE|ENTITY)", re.IGNORECASE)

#: Tags que o ``GameRecord`` representa e que a exportação reescreve. Toda tag
#: fora desta lista é preservada como está — é curadoria do usuário.
OWNED_TAGS = (
    "path",
    "name",
    "desc",
    "developer",
    "publisher",
    "genre",
    "players",
    "rating",
    "releasedate",
    "image",
)


def _relative(path: str, system_root: str) -> str | None:
    """Caminho no formato do ES-DE (``./arquivo``), ou ``None`` se escapar."""
    try:
        absolute = resolve_path(path, system_root)
    except PathRefused:
        return None
    root = system_root.rstrip("/")
    if absolute == root:
        return None
    if not absolute.startswith(root + "/"):
        return None
    return "./" + absolute[len(root) + 1 :]


def _owned_values(record: GameRecord, system_root: str) -> dict[str, str] | None:
    """Valores das tags que exportamos, ou ``None`` se o registro não serve."""
    payload = record.to_mapping()
    relative = _relative(str(payload.get("path") or ""), system_root)
    if relative is None:
        return None

    values: dict[str, str] = {"path": relative, "name": record.title}

    for field, tag in (
        ("description", "desc"),
        ("developer", "developer"),
        ("publisher", "publisher"),
    ):
        value = payload.get(field)
        if isinstance(value, str) and value:
            values[tag] = value

    genres = payload.get("genres")
    if isinstance(genres, list) and genres:
        values["genre"] = str(genres[0])

    players = payload.get("players")
    if isinstance(players, int):
        values["players"] = str(players)

    rating = payload.get("rating")
    if isinstance(rating, int | float):
        # Contrato 0..100 -> fração 0..1 do ES-DE. Espelho do bug de escala que
        # o schema não pegou na importação.
        values["rating"] = f"{rating / 100:.6f}".rstrip("0").rstrip(".") or "0"

    release = payload.get("releaseDate")
    if isinstance(release, str) and len(release) == 10:
        values["releasedate"] = release.replace("-", "") + "T000000"

    cover = record.media(MediaRole.COVER)
    if cover:
        relative_cover = _relative(str(cover.get("path") or ""), system_root)
        if relative_cover:
            values["image"] = relative_cover

    return values


def _indent(element: ET.Element, level: int = 0) -> None:
    """Indentação estável — saída determinística é o que torna o plano idempotente."""
    pad = "\n" + "  " * level
    if len(element):
        if not (element.text or "").strip():
            element.text = pad + "  "
        for child in element:
            _indent(child, level + 1)
            if not (child.tail or "").strip():
                child.tail = pad + "  "
        if not (element[-1].tail or "").strip():
            element[-1].tail = pad
    if level and not (element.tail or "").strip():
        element.tail = pad


def plan_esde_export(
    records: Sequence[GameRecord],
    *,
    system_root: str,
    target: str,
    current_xml: str | None = None,
) -> ExportPlan:
    """Planeja a exportação sem escrever nada.

    ``current_xml`` é o conteúdo atual do alvo, ou ``None`` se ele não existe.
    """
    skipped: list[tuple[str, str]] = []
    preserved: set[str] = set()

    if current_xml is not None:
        if _DOCTYPE.search(current_xml):
            return refusal(target, current_xml, "gamelist alvo contém DTD ou entidade")
        try:
            root = ET.fromstring(current_xml)  # noqa: S314 - DTD recusado acima
        except ET.ParseError as exc:
            # Sobrescrever aqui destruiria curadoria que talvez esteja íntegra.
            return refusal(target, current_xml, f"gamelist alvo malformado: {exc}")
        if root.tag != "gameList":
            return refusal(target, current_xml, f"raiz inesperada no alvo: <{root.tag}>")
    else:
        root = ET.Element("gameList")

    existing: dict[str, ET.Element] = {}
    for node in root.findall("game"):
        node_path = node.find("path")
        if node_path is not None and node_path.text:
            existing[node_path.text.strip()] = node

    for record in records:
        values = _owned_values(record, system_root)
        if values is None:
            skipped.append((record.id, "caminho fora da raiz do sistema"))
            continue

        found = existing.get(values["path"])
        if found is None:
            node = ET.SubElement(root, "game")
            existing[values["path"]] = node
        else:
            node = found
            # Preserva toda tag que não é nossa: é curadoria do usuário.
            for child in list(node):
                if child.tag in OWNED_TAGS:
                    node.remove(child)
                else:
                    preserved.add(child.tag)

        for tag in OWNED_TAGS:
            if tag in values:
                ET.SubElement(node, tag).text = values[tag]

    _indent(root)
    body = ET.tostring(root, encoding="unicode")
    proposed = '<?xml version="1.0"?>\n' + body.rstrip() + "\n"

    action, current_digest, proposed_digest = decide(target, current_xml, proposed)
    return ExportPlan(
        action=action,
        target=target,
        preview=proposed,
        current_digest=current_digest,
        proposed_digest=proposed_digest,
        preserved=tuple(sorted(preserved)),
        skipped=tuple(skipped),
    )


__all__ = ["OWNED_TAGS", "plan_esde_export"]
