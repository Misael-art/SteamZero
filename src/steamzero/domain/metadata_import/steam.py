# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Adapter de importação Steam (``appmanifest_*.acf`` e atalhos não-Steam).

Duas fontes distintas, com garantias distintas:

- ``appmanifest_*.acf`` é VDF **texto**, escrito pelo próprio cliente Steam.
  Descreve um jogo nativo instalado: appid, nome e diretório. Confiança alta
  (0,9) porque a fonte é o dono do dado.
- **Atalhos não-Steam** vivem em ``shortcuts.vdf``, que é VDF **binário**. Este
  módulo **não** o decodifica: ``steamzero.adapters.steam_shortcuts`` já tem um
  decodificador em produção, e ``domain`` não importa ``adapters``. O chamador
  decodifica e passa as linhas; aqui só há tradução. Reimplementar o parser
  criaria uma segunda leitura do mesmo formato binário, que divergiria.
  Confiança baixa (0,3): atalho é o que o usuário digitou, sem curadoria.

Jogo nativo da Steam não é ROM: ``path`` aponta o diretório de instalação, e
não há ``core`` nem requisito de BIOS. Forçá-lo no molde de emulação produziria
um registro que mente sobre como o jogo roda.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from steamzero.domain.game_record import GameRecord, GameRecordError
from steamzero.domain.metadata_import._common import (
    MAX_ENTRIES,
    ImportResult,
    PathRefused,
    build_provenance,
    require_absolute_root,
    resolve_path,
)

#: Origens distintas; a proveniência precisa distingui-las na fusão.
SOURCE_MANIFEST = "steam"
SOURCE_SHORTCUT = "steam-shortcut"

#: O cliente Steam é dono do dado do manifesto.
CONFIDENCE_MANIFEST = 0.9

#: Atalho é o que o usuário digitou, sem curadoria.
CONFIDENCE_SHORTCUT = 0.3

_KEY_VALUE = re.compile(r'^\s*"((?:[^"\\]|\\.)*)"\s+"((?:[^"\\]|\\.)*)"\s*$')
_UNESCAPE = {"\\\\": "\\", '\\"': '"', "\\n": "\n", "\\t": "\t"}
_ID_SAFE = re.compile(r"[^a-z0-9._-]+")


def _unescape(value: str) -> str:
    out = value
    for escaped, plain in _UNESCAPE.items():
        out = out.replace(escaped, plain)
    return out


def parse_acf(text: str) -> dict[str, str]:
    """Extrai os pares escalares de um ``.acf``, ignorando o aninhamento.

    O manifesto tem blocos aninhados (``InstalledDepots``, ``UserConfig``) cujas
    chaves repetem entre si. Achatar tudo faria uma chave de bloco sobrescrever
    a do topo; por isso só o nível raiz de ``AppState`` é considerado.
    """
    values: dict[str, str] = {}
    depth = 0
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("//"):
            continue
        if line == "{":
            depth += 1
            continue
        if line == "}":
            depth = max(0, depth - 1)
            continue
        # Chave que abre bloco na próxima linha; a "{" incrementa depth.
        match = _KEY_VALUE.match(raw_line)
        if match is None:
            continue
        if depth == 1:
            values[_unescape(match.group(1)).lower()] = _unescape(match.group(2))
    return values


def import_steam_appmanifest(
    text: str,
    *,
    library_root: str,
    retrieved_at: str,
    platform_id: str = "steam",
) -> ImportResult:
    """Traduz um ``appmanifest_*.acf`` em um registro canônico.

    ``library_root`` é a raiz ``steamapps`` da biblioteca; ``installdir`` é
    relativo a ``common/`` dentro dela.
    """
    try:
        require_absolute_root(library_root)
    except ValueError as exc:
        raise GameRecordError(str(exc)) from exc

    values = parse_acf(text)
    appid = (values.get("appid") or "").strip()
    name = (values.get("name") or "").strip()
    installdir = (values.get("installdir") or "").strip()

    if not appid or not appid.isdigit():
        return ImportResult(skipped=((name or "<sem nome>", "steam-appid-ausente-ou-invalido"),))
    if not installdir:
        return ImportResult(skipped=((name or appid, "steam-sem-installdir"),))

    try:
        path = resolve_path(f"common/{installdir}", library_root)
    except PathRefused as exc:
        return ImportResult(skipped=((name or appid, f"steam-path-recusado: {exc}"),))

    payload: dict[str, Any] = {
        "schemaVersion": 1,
        "id": f"steam-{appid}",
        "title": name or installdir,
        "platformId": platform_id,
        "path": path,
        # Jogo nativo: o diretório é o alvo, não um arquivo de ROM.
        "container": "directory",
        "availability": "unknown",
        "updatedAt": retrieved_at,
    }

    size = (values.get("sizeondisk") or "").strip()
    if size.isdigit():
        payload["size"] = int(size)

    payload["provenance"] = build_provenance(
        payload,
        source=SOURCE_MANIFEST,
        retrieved_at=retrieved_at,
        confidence=CONFIDENCE_MANIFEST,
    )

    try:
        return ImportResult(records=(GameRecord.from_mapping(payload),))
    except GameRecordError as exc:
        return ImportResult(skipped=((name or appid, f"steam-registro-invalido: {exc}"),))


def import_steam_shortcuts(
    rows: Sequence[object],
    *,
    retrieved_at: str,
    platform_id: str = "steam-shortcut",
) -> ImportResult:
    """Traduz atalhos não-Steam **já decodificados** em registros canônicos.

    Recebe as linhas prontas de propósito: o decodificador binário vive em
    ``adapters.steam_shortcuts``, ``domain`` não importa ``adapters``, e uma
    segunda leitura do mesmo formato binário acabaria divergindo da primeira.

    O tipo é ``Sequence[object]`` porque a entrada vem de decodificação de
    arquivo de terceiro: prometer ``Mapping`` na assinatura tornaria a checagem
    de forma um código morto para o verificador e uma mentira em runtime.
    """
    records: list[GameRecord] = []
    skipped: list[tuple[str, str]] = []
    seen: set[str] = set()

    for index, row in enumerate(rows):
        if index >= MAX_ENTRIES:
            skipped.append(("<limite>", "steam-shortcuts-excede-limite"))
            break
        if not isinstance(row, Mapping):
            skipped.append((f"<atalho {index}>", "steam-atalho-nao-e-objeto"))
            continue

        name = str(row.get("AppName") or row.get("appname") or "").strip()
        exe = str(row.get("Exe") or row.get("exe") or "").strip()
        label = name or exe or f"<atalho {index}>"
        if not exe:
            skipped.append((label, "steam-atalho-sem-exe"))
            continue

        # A Steam grava o executável entre aspas quando há espaço no caminho.
        target = exe.strip('"').strip()
        if not target:
            skipped.append((label, "steam-atalho-sem-exe"))
            continue

        slug = _ID_SAFE.sub("-", (name or target).lower()).strip("-._")
        if not slug or not slug[0].isalnum():
            slug = f"a{slug}" if slug else f"atalho-{index}"
        record_id = f"steam-shortcut-{slug}"[:128]
        if record_id in seen:
            skipped.append((label, "steam-atalho-duplicado"))
            continue
        seen.add(record_id)

        payload: dict[str, Any] = {
            "schemaVersion": 1,
            "id": record_id,
            "title": name or target.rsplit("/", 1)[-1],
            "platformId": platform_id,
            "path": target,
            "availability": "unknown",
            "updatedAt": retrieved_at,
        }
        payload["provenance"] = build_provenance(
            payload,
            source=SOURCE_SHORTCUT,
            retrieved_at=retrieved_at,
            confidence=CONFIDENCE_SHORTCUT,
        )

        try:
            records.append(GameRecord.from_mapping(payload))
        except GameRecordError as exc:
            skipped.append((label, f"steam-atalho-invalido: {exc}"))

    return ImportResult(records=tuple(records), skipped=tuple(skipped))
