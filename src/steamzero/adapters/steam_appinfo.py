# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Tipo declarado de cada app Steam, lido do ``appinfo.vdf``.

Existe porque o ``appmanifest_*.acf`` **não** carrega o tipo do app: um
``Steam Linux Runtime`` e um jogo têm exatamente os mesmos campos ali. Sem esta
leitura, o acervo Steam publicado ao usuário mistura Proton, runtimes e
redistribuíveis com os jogos — foi o que apareceu no host em 2026-09-04, onde
dos 15 apps instalados apenas 7 eram jogos, e é a razão de a central publicar
"1134 títulos" contando ferramentas.

O formato é VDF binário. A partir da v29 as CHAVES não são strings inline: são
índices para uma tabela no fim do arquivo. Por isso procurar ``type`` no binário
não acha nada, e foi o que fez a primeira tentativa concluir, errado, que o tipo
não estava lá.

Nada aqui é escrito: o arquivo é do cliente Steam e este módulo só lê.
"""

from __future__ import annotations

import struct
from pathlib import Path

#: `VDF)` little-endian. Só a v29 traz a tabela de strings; as anteriores usam
#: chaves inline e não são lidas aqui — devolver "não sei" é melhor que decodificar
#: um layout adivinhado.
_MAGIC_V29 = 0x07564429

#: magic(4) + universe(4) + offset da tabela de strings(8).
_HEADER_SIZE = 16

#: Por entrada, antes do corpo VDF: infoState(4), lastUpdated(4), picsToken(8),
#: sha1(20), changeNumber(4), binaryVdfSha1(20).
_ENTRY_METADATA_SIZE = 60

_NESTED, _STRING, _INT32, _UINT64, _END = 0x00, 0x01, 0x02, 0x07, 0x08

#: O que conta como jogável para o usuário. ``demo`` entra: é conteúdo que ele
#: instalou e joga. ``tool`` (Proton, Steam Linux Runtime, redistribuíveis) e
#: ``application`` ficam fora. Vive aqui, junto do classificador, para que a
#: central e o Launcher não voltem a divergir por aplicarem regras diferentes.
PLAYABLE_APP_TYPES = frozenset({"game", "demo"})


def app_types(path: Path | None = None) -> dict[str, str]:
    """``{appid: tipo}`` em minúsculas (``game``, ``tool``, ``demo``…).

    Devolve ``{}`` quando o arquivo falta, está em versão não suportada ou é
    ilegível. Quem chama decide o que fazer sem classificação — este módulo não
    inventa um tipo para preencher a lacuna.
    """
    source = path if path is not None else default_appinfo_path()
    try:
        blob = source.read_bytes()
    except OSError:
        return {}
    try:
        return _parse(blob)
    except (struct.error, ValueError, IndexError):
        # Arquivo truncado ou layout inesperado. O cliente Steam reescreve este
        # cache sozinho; recusar a leitura é melhor que publicar tipos errados.
        return {}


def default_appinfo_path() -> Path:
    return Path.home() / ".local/share/Steam/appcache/appinfo.vdf"


def _parse(blob: bytes) -> dict[str, str]:
    magic = struct.unpack_from("<I", blob, 0)[0]
    if magic != _MAGIC_V29:
        return {}
    table_offset = struct.unpack_from("<q", blob, 8)[0]
    if not 0 < table_offset <= len(blob) - 4:
        return {}
    keys = _string_table(blob, table_offset)

    types: dict[str, str] = {}
    cursor = _HEADER_SIZE
    while cursor + 8 <= table_offset:
        app_id, size = struct.unpack_from("<II", blob, cursor)
        if app_id == 0:
            break
        entry_end = cursor + 8 + size
        if not cursor < entry_end <= table_offset:
            break
        declared = _entry_type(blob, cursor + 8 + _ENTRY_METADATA_SIZE, entry_end, keys)
        if declared:
            types[str(app_id)] = declared
        cursor = entry_end
    return types


def _string_table(blob: bytes, offset: int) -> list[str]:
    count = struct.unpack_from("<I", blob, offset)[0]
    keys: list[str] = []
    cursor = offset + 4
    for _ in range(count):
        end = blob.index(b"\x00", cursor)
        keys.append(blob[cursor:end].decode("utf-8", "replace"))
        cursor = end + 1
    return keys


def _entry_type(blob: bytes, cursor: int, end: int, keys: list[str]) -> str:
    """Percorre o VDF binário de uma entrada até achar ``common/type``.

    Só interessa esse campo, então a travessia não constrói a árvore inteira:
    guarda apenas o caminho, para não confundir o ``type`` de ``common`` com
    algum ``type`` aninhado noutro bloco.
    """
    path: list[str] = []
    while cursor < end:
        marker = blob[cursor]
        cursor += 1
        if marker == _END:
            if not path:
                break
            path.pop()
            continue
        if cursor + 4 > end:
            break
        key_index = struct.unpack_from("<I", blob, cursor)[0]
        cursor += 4
        key = keys[key_index] if key_index < len(keys) else ""
        if marker == _NESTED:
            path.append(key)
        elif marker == _STRING:
            terminator = blob.index(b"\x00", cursor)
            value = blob[cursor:terminator].decode("utf-8", "replace")
            cursor = terminator + 1
            # O acervo real traz "Game" e "game" na mesma leitura; comparar com
            # sensibilidade a caixa deixaria jogos de fora.
            if key == "type" and path[-1:] == ["common"]:
                return value.strip().lower()
        elif marker == _INT32:
            cursor += 4
        elif marker == _UINT64:
            cursor += 8
        else:
            break
    return ""
