# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Compilação de temas ES-DE para o IR de cena.

Segundo emissor do IR, depois de ``scene_retrofe``. A escolha de compilar em vez
de interpretar é a mesma: um tema de terceiros não executa código, e traduzir
para nós allowlisted é o que permite fidelidade de layout sem abrir a fronteira
de confiança.

**ES-DE não é RetroFE, e a diferença dita o desenho.** Medições em 130 arquivos
XML de cinco temas licenciados (modern-es-de, playstation-x, xmb-menu, nso-menu,
iconic), colhidas em 2026-09-03:

- **0 arquivos malformados.** Temas ES-DE são XML conforme. Toda a maquinaria de
  reparo de ``scene_retrofe._sanitize`` — comentários ilegais, fechamento
  anônimo, tags trocadas — não tem análogo aqui e seria complexidade sem causa.
- **Propriedades são elementos filhos, não atributos.** ``<image><pos>0 0</pos>``
  onde o RetroFE escreveria ``<image x="0" y="0">``. Daí ``_PROPERTIES`` mapear
  tag filha, e não atributo.
- **Coordenadas são pares normalizados.** ``<pos>0.5 0.5</pos>`` é uma fração da
  tela, não pixels. Isso torna o resultado independente de resolução — e é o que
  permite compilar um tema 16:9 e exibi-lo no painel do Deck sem reescala.
- **Variáveis com interpolação.** ``${systemDescriptionFontSize}`` aparece 1359
  vezes. Sem resolvê-las, metade das propriedades numéricas viraria lixo textual.

Princípio herdado, e inegociável: **o que não é compreendido degrada e é
registrado, nunca inventado nem silenciado.** Cada elemento ou propriedade
recusada entra em ``degraded`` com a razão, e é isso que permite declarar
fidelidade em vez de prometê-la.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

from steamzero.core.errors import SteamZeroError

#: Elementos de view que sabemos traduzir, com a contagem observada nos 130
#: arquivos medidos. O IR reusa os mesmos ``kind`` do emissor RetroFE onde a
#: semântica coincide — dois nomes para o mesmo conceito obrigariam o
#: renderizador a conhecer a origem, que é exatamente o que o IR evita.
_ELEMENT_KINDS = {
    "text": "text",  # 623
    "image": "image",  # 425
    "datetime": "boundText",  # 129
    "helpsystem": "helpSystem",  # 94
    "rating": "rating",  # 92
    "badges": "badges",  # 70
    "video": "video",  # 63
    "carousel": "carousel",  # 56
    "systemstatus": "systemStatus",  # 44
    "textlist": "textList",  # 30
    "clock": "boundText",  # 28
    "sound": "sound",  # 14
    "grid": "grid",  # 10
    "gamelistinfo": "gameListInfo",  # 1
    "gameselector": "gameSelector",  # 1
}

#: Elementos que o ES-DE resolve por conta própria, sem asset nem texto do tema.
#: ``clock`` e ``datetime`` são relógio e data do sistema; declarar o vínculo aqui
#: evita que virem texto vazio no IR.
_IMPLICIT_BINDINGS = {
    "clock": {"source": "system", "field": "time"},
    "datetime": {"source": "metadata", "field": "releasedate"},
}

#: Propriedades de par ``x y`` — posição, tamanho e origem normalizados.
_PAIR_PROPERTIES = {
    "pos": ("x", "y"),
    "size": ("width", "height"),
    "maxSize": ("maxWidth", "maxHeight"),
    "minSize": ("minWidth", "minHeight"),
    "cropSize": ("cropWidth", "cropHeight"),
    "origin": ("xOrigin", "yOrigin"),
    "itemSize": ("itemWidth", "itemHeight"),
    "itemScale": ("itemScaleX", "itemScaleY"),
    # Medidos como pares nos temas reais, apesar do nome no singular sugerir
    # escalar: ``<itemMargin>0.006 0.01</itemMargin>``.
    "itemMargin": ("itemMarginX", "itemMarginY"),
    "itemSpacing": ("itemSpacingX", "itemSpacingY"),
    "selectedItemMargins": ("selectedItemMarginX", "selectedItemMarginY"),
    # Variante "dimmed" do helpsystem, exibida quando um menu cobre a view.
    "posDimmed": ("xDimmed", "yDimmed"),
    "originDimmed": ("xOriginDimmed", "yOriginDimmed"),
    "controllerPos": ("controllerX", "controllerY"),
    "controllerSize": ("controllerWidth", "controllerHeight"),
    "folderLinkPos": ("folderLinkX", "folderLinkY"),
    "folderLinkSize": ("folderLinkWidth", "folderLinkHeight"),
}

#: Propriedades escalares, com faixa válida. Fora da faixa degrada em vez de
#: entrar: um ``fontSize`` de 40 (fração de tela) deformaria a cena inteira.
_SCALAR_PROPERTIES: dict[str, tuple[float, float]] = {
    "fontSize": (0.0, 1.0),
    "lineSpacing": (0.0, 8.0),
    "opacity": (0.0, 1.0),
    "saturation": (0.0, 1.0),
    "brightness": (-1.0, 1.0),
    "rotation": (-360.0, 360.0),
    "maxItemCount": (0.0, 64.0),
    "itemsBeforeCenter": (0.0, 64.0),
    "itemsAfterCenter": (0.0, 64.0),
    "horizontalOffset": (-8.0, 8.0),
    "verticalOffset": (-8.0, 8.0),
    "imageCornerRadius": (0.0, 1.0),
    "textRelativeScale": (0.0, 8.0),
    "unfocusedItemOpacity": (0.0, 1.0),
    "selectorWidth": (0.0, 1.0),
    "selectorHeight": (0.0, 1.0),
    "selectorHorizontalOffset": (-1.0, 1.0),
    "entrySpacing": (0.0, 1.0),
    "iconTextSpacing": (0.0, 1.0),
    "itemMargin": (0.0, 1.0),
    "containerScrollSpeed": (0.0, 16.0),
    "entryRelativeScale": (0.0, 8.0),
    "lines": (1.0, 16.0),
    "itemsPerLine": (1.0, 32.0),
    "textBackgroundCornerRadius": (0.0, 1.0),
    "horizontalMargin": (0.0, 1.0),
    "unfocusedItemDimming": (0.0, 1.0),
    "unfocusedItemSaturation": (0.0, 1.0),
    "fractionalRows": (0.0, 32.0),
    "delay": (0.0, 60.0),
    "pillarboxThreshold": (0.0, 4.0),
    "scrollFadeIn": (0.0, 16.0),
}

#: Cores. O ES-DE escreve RRGGBB ou RRGGBBAA sem ``#``.
_COLOR_PROPERTIES = frozenset(
    {
        "color",
        "backgroundColor",
        "textColor",
        "textBackgroundColor",
        "selectorColor",
        "selectedColor",
        "primaryColor",
        "secondaryColor",
        "iconColor",
        "textColorDimmed",
        "iconColorDimmed",
    }
)

#: Enumerações textuais aceitas, por propriedade. Valor fora do conjunto degrada:
#: repassar string arbitrária ao renderizador seria confiar em dado de terceiro.
_ENUM_PROPERTIES: dict[str, frozenset[str]] = {
    "horizontalAlignment": frozenset({"left", "center", "right"}),
    "verticalAlignment": frozenset({"top", "center", "bottom"}),
    "letterCase": frozenset({"none", "uppercase", "lowercase", "capitalize"}),
    "containerType": frozenset({"horizontal", "vertical"}),
    "imageFit": frozenset({"contain", "fill", "cover"}),
    "interpolation": frozenset({"nearest", "linear"}),
    "direction": frozenset({"row", "column", "horizontal", "vertical"}),
    # ``none`` aparece nos temas reais e significa "sem helpsystem nesta view".
    "scope": frozenset({"menu", "view", "global", "none"}),
    # Medido como enum, não booleano: o único valor observado é ``withinView``.
    "stationary": frozenset({"never", "always", "withinview", "withinviewandmenu"}),
}

#: Propriedades booleanas.
_BOOL_PROPERTIES = frozenset(
    {"visible", "tile", "selectable", "container", "fastScrolling", "scaleInwards", "pillarboxes"}
)

#: Slots de mídia do ES-DE (``imageType``/``metadata``) → campo do IR. Os nomes
#: coincidem em grande parte com os do RetroFE porque descrevem a mesma arte.
_MEDIA_FIELDS = {
    "image": "image",
    "cover": "boxFront",
    "backcover": "boxBack",
    "box3d": "box3d",
    "marquee": "marquee",
    "screenshot": "screenshot",
    "titlescreen": "titlescreen",
    "fanart": "fanart",
    "miximage": "miximage",
    "physicalmedia": "cartridge",
    "video": "video",
}

#: Campos de metadado do jogo referenciados por ``<metadata>``.
_METADATA_FIELDS = {
    "name": "title",
    "description": "description",
    "developer": "developer",
    "publisher": "publisher",
    "genre": "genre",
    "players": "players",
    "releasedate": "releasedate",
    "rating": "rating",
    "playcount": "playCount",
    "lastplayed": "lastPlayed",
    "systemName": "platform",
    "systemFullname": "platform",
    "sourceSystemName": "platform",
    "sourceSystemFullname": "platform",
    # Tempo acumulado de jogo. Medido em uso real (`game-playtime` no xmb-menu).
    "playtime": "playTime",
}

#: Marcadores que o ES-DE resolve em TEMPO DE EXECUÇÃO, conforme o sistema em
#: foco — não são variáveis de tema e não têm valor durante a compilação.
#: Medidos no xmb-menu: ``${system.fullName}`` (18 usos) e ``${system.theme}``
#: (3 usos), e é por ``system.theme`` que passa toda a arte por sistema.
_RUNTIME_PLACEHOLDERS = {
    "system.theme": "system",
    "system.fullName": "systemFullName",
}

#: ``<view name="all">`` é o curinga do ES-DE: vale para todas as views.
_VIEW_WILDCARD = "all"
_VIEW_NAMES = frozenset({"system", "gamelist", "menu"})
_ID_SAFE = re.compile(r"[^a-zA-Z0-9_-]")
_HEX_COLOR = re.compile(r"^[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$")
#: Variável de tema. O ponto NÃO entra: ``${system.theme}`` é marcador de tempo
#: de execução e é tratado à parte, senão viraria "variável não declarada".
_VARIABLE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_RUNTIME_VARIABLE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+)\}")
#: Um identificador de sistema aceitável como substituição do template. Validado
#: contra os 214 nomes reais de ``_inc/systems/_metadata-global/`` do xmb-menu:
#: todos casam, nenhuma exceção. É o que impede ``{system}`` de virar travessia.
SYSTEM_ID = re.compile(r"^[a-z0-9_][a-z0-9_-]*$")
#: Caminhos de asset dentro do tema. Travessia, caminho absoluto e esquema são
#: recusados à parte; aqui limitamos a forma e a extensão.
_ASSET_SAFE = re.compile(
    r"^[a-zA-Z0-9_. /()'&+-]+\.(png|jpg|jpeg|webp|svg|gif|mp4|mkv|webm|wav|ogg|mp3)$",
    re.IGNORECASE,
)

#: Tetos. Um tema hostil não pode virar consumo ilimitado de memória.
MAX_ELEMENTS_PER_VIEW = 256
MAX_VIEWS = 32
MAX_VARIABLE_DEPTH = 8


@dataclass
class _Degraded:
    entries: list[dict[str, str]] = field(default_factory=list)

    def add(self, element: str, reason: str) -> None:
        if len(self.entries) < 256:
            self.entries.append({"element": element[:64], "reason": reason[:256]})


@dataclass(frozen=True)
class Selection:
    """Escolhas do ES-DE que decidem QUAIS variáveis valem.

    ES-DE não tem um tema só: tem um tema por combinação de variante, esquema de
    cor, tamanho de fonte, proporção e idioma. Medido nos 130 arquivos, as
    variáveis moram majoritariamente nesses blocos — 3406 em ``<language>``, 1433
    em ``<fontSize>``, 273 em ``<colorScheme>``. Compilar sem escolher deixaria
    169 referências ``${...}`` sem valor, que foi exatamente o que a primeira
    medição mostrou.

    Herdar de todos os blocos NÃO é alternativa: misturaria a descrição em árabe
    com a em português e o corpo "small" com o "large", e o último a ser lido
    venceria por acidente de ordem de arquivo.
    """

    variant: str = ""
    color_scheme: str = ""
    font_size: str = ""
    language: str = ""
    #: A proporção é a dimensão que carrega a GEOMETRIA. Os temas medidos põem
    #: ``<pos>``/``<size>`` dentro de ``<aspectRatio>``, um bloco por formato de
    #: tela. Compilar sem escolher uma produzia cena com cobertura alta e dois
    #: elementos posicionados: os demais existiam no IR sem nada que os
    #: colocasse na tela, e nenhum renderizador consegue desenhar isso.
    aspect_ratio: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            key: value
            for key, value in (
                ("variant", self.variant),
                ("colorScheme", self.color_scheme),
                ("fontSize", self.font_size),
                ("language", self.language),
                ("aspectRatio", self.aspect_ratio),
            )
            if value
        }


#: Blocos de seleção → atributo da ``Selection`` que os escolhe.
_SELECTION_BLOCKS = (
    ("aspectRatio", "aspect_ratio"),
    ("colorScheme", "color_scheme"),
    ("fontSize", "font_size"),
    ("language", "language"),
    ("variant", "variant"),
)


def _merge_variables(block: ET.Element, into: dict[str, str]) -> None:
    for holder in block.findall("variables"):
        for node in holder:
            text = (node.text or "").strip()
            if text:
                into[node.tag] = text[:1024]


def available_selections(root: ET.Element) -> dict[str, list[str]]:
    """Enumera as variantes/esquemas/corpos/idiomas que o tema declara.

    É o que permite a UI oferecer as opções reais do tema em vez de um campo
    livre onde qualquer erro de digitação vira silenciosamente o default.
    """
    out: dict[str, list[str]] = {}
    for tag, _ in _SELECTION_BLOCKS:
        names: list[str] = []
        for block in root.iter(tag):
            name = (block.get("name") or "").strip()
            for part in name.split(","):
                candidate = part.strip()
                if candidate and candidate not in names:
                    names.append(candidate)
        if names:
            out[tag] = names
    return out


def collect_variables(root: ET.Element, selection: Selection | None = None) -> dict[str, str]:
    """Junta os ``<variables>`` do escopo global e os da seleção pedida.

    A precedência é a do ES-DE: o bloco global é a base, e cada bloco de seleção
    escolhido sobrescreve. Um bloco cujo ``name`` não casa com a seleção é
    ignorado por inteiro — é o que impede vazamento entre variantes.
    """
    chosen = selection or Selection()
    variables: dict[str, str] = {}
    _merge_variables(root, variables)

    for tag, attribute in _SELECTION_BLOCKS:
        wanted = getattr(chosen, attribute)
        if not wanted:
            continue
        for block in root.iter(tag):
            names = {part.strip() for part in (block.get("name") or "").split(",")}
            if wanted in names:
                _merge_variables(block, variables)
    return variables


def interpolate(value: str, variables: dict[str, str]) -> tuple[str, list[str]]:
    """Resolve ``${nome}`` recursivamente, devolvendo também o que não resolveu.

    Variáveis podem referenciar variáveis. O teto de profundidade existe para que
    um ciclo (``a`` → ``b`` → ``a``) termine em vez de girar; ciclo é dado de
    terceiro, não pode derrubar a compilação.
    """
    unresolved: list[str] = []
    current = value
    for _ in range(MAX_VARIABLE_DEPTH):
        if "${" not in current:
            break
        # Os nomes ausentes são colhidos ANTES da substituição, em vez de por
        # efeito colateral dentro do callback: uma closure sobre variável de
        # laço é fonte clássica de captura tardia.
        pending = [name for name in _VARIABLE.findall(current) if name not in variables]
        current = _VARIABLE.sub(
            lambda match: variables.get(match.group(1), match.group(0)), current
        )
        if pending:
            unresolved.extend(pending)
            break
    else:
        # Esgotou a profundidade com referências de pé: é ciclo. Reportar é o que
        # mantém a promessa do módulo — silenciar devolveria "${a}" como se fosse
        # um valor literal, e a propriedade viraria lixo textual sem registro.
        if "${" in current:
            unresolved.extend(_VARIABLE.findall(current))
    return current, sorted(set(unresolved))


def _numbers(raw: str) -> list[float] | None:
    parts = raw.replace(",", " ").split()
    try:
        return [float(part) for part in parts]
    except ValueError:
        return None


def _pair(raw: str, names: tuple[str, str], degraded: _Degraded, where: str) -> dict[str, float]:
    numbers = _numbers(raw)
    if numbers is None or len(numbers) != 2:
        degraded.add(where, f"par numérico inválido: {raw!r}")
        return {}
    out: dict[str, float] = {}
    for name, number in zip(names, numbers, strict=True):
        if not -16.0 <= number <= 16.0:
            degraded.add(where, f"{name} fora de faixa: {number}")
            continue
        out[name] = number
    return out


def _color(raw: str, degraded: _Degraded, where: str) -> str | None:
    value = raw.strip().lstrip("#")
    if not _HEX_COLOR.match(value):
        degraded.add(where, f"cor inválida: {raw!r}")
        return None
    return f"#{value.lower()}"


def _reject_escaping(value: str) -> bool:
    """Travessia, caminho absoluto e esquema de URL — as três formas de sair."""
    return ".." in value or value.startswith("/") or "://" in value or "\\" in value


def _asset(raw: str, degraded: _Degraded, where: str) -> str | None:
    """Aceita um caminho de asset relativo ao tema, recusando tudo que escapa.

    O caminho vem de um tema de terceiros. Travessia, caminho absoluto e esquema
    de URL são as três formas de transformar "carregue esta imagem" em "leia este
    arquivo do sistema" ou "busque isto na rede" — as três são recusadas antes de
    qualquer verificação de forma.
    """
    value = raw.strip()
    if not value:
        return None
    if _reject_escaping(value):
        degraded.add(where, f"caminho de asset recusado: {value!r}")
        return None
    value = value.removeprefix("./")
    if not _ASSET_SAFE.match(value):
        degraded.add(where, f"caminho de asset recusado: {value!r}")
        return None
    return value


def asset_template(raw: str, degraded: _Degraded, where: str) -> dict[str, str] | None:
    """Reconhece um caminho de arte POR SISTEMA e o publica como template.

    ``${systemContentImagePath}/${system.theme}.png`` resolve, depois das
    variáveis do tema, para ``_inc/systems/physical-media/${system.theme}.png``.
    O ``${system.theme}`` só tem valor em tempo de execução, quando se sabe qual
    sistema está em foco — e é por esse caminho que passa a arte por sistema, que
    um tema publica para as centenas de consoles que conhece (223 nomes
    distintos no xmb-menu).

    Tratar isso como caminho literal descartaria a arte por sistema inteira, que
    foi o que a primeira versão fez. Emitir o template preserva a intenção e
    mantém a fronteira: o renderizador só pode substituir por um identificador
    que casa com ``SYSTEM_ID``, nunca por texto arbitrário.
    """
    value = raw.strip()
    if not value:
        return None
    placeholders = _RUNTIME_VARIABLE.findall(value)
    if not placeholders:
        return None
    unknown = [name for name in placeholders if name not in _RUNTIME_PLACEHOLDERS]
    if unknown:
        degraded.add(where, f"marcador de tempo de execução desconhecido: {sorted(set(unknown))}")
        return None

    pattern = _RUNTIME_VARIABLE.sub(
        lambda match: "{" + _RUNTIME_PLACEHOLDERS[match.group(1)] + "}", value
    )
    if _reject_escaping(pattern):
        degraded.add(where, f"caminho de asset recusado: {value!r}")
        return None
    pattern = pattern.removeprefix("./")
    # A forma é validada com o marcador já substituído por um nome plausível:
    # o que precisa ser seguro é o caminho FINAL, não o template.
    probe = pattern.format(**dict.fromkeys(_RUNTIME_PLACEHOLDERS.values(), "sistema"))
    if _reject_escaping(probe) or not _ASSET_SAFE.match(probe):
        degraded.add(where, f"caminho de asset recusado: {value!r}")
        return None
    return {"pattern": pattern, "parameter": "system"}


def resolve_asset_template(pattern: str, system_id: str) -> str:
    """Substitui o marcador por um sistema concreto, recusando o que não casa.

    Este é o ponto onde um identificador vindo de fora vira caminho. Validar
    contra ``SYSTEM_ID`` aqui — e não confiar em quem chamou — é o que impede que
    o template vire travessia.
    """
    if not SYSTEM_ID.match(system_id):
        raise SteamZeroError(
            "E-THEME-UNSAFE",
            detail=f"identificador de sistema inválido: {system_id!r}",
        )
    return pattern.format(**dict.fromkeys(_RUNTIME_PLACEHOLDERS.values(), system_id))


def _property(  # um ramo por família de propriedade; achatar esconderia o mapa
    tag: str,
    raw: str,
    degraded: _Degraded,
    where: str,
) -> dict[str, Any]:
    if tag in _PAIR_PROPERTIES:
        return _pair(raw, _PAIR_PROPERTIES[tag], degraded, where)
    if tag in _SCALAR_PROPERTIES:
        low, high = _SCALAR_PROPERTIES[tag]
        numbers = _numbers(raw)
        if numbers is None or len(numbers) != 1:
            degraded.add(where, f"{tag} não numérico: {raw!r}")
            return {}
        if not low <= numbers[0] <= high:
            degraded.add(where, f"{tag} fora de faixa [{low}, {high}]: {numbers[0]}")
            return {}
        return {tag: numbers[0]}
    if tag in _COLOR_PROPERTIES:
        color = _color(raw, degraded, where)
        return {tag: color} if color else {}
    if tag in _BOOL_PROPERTIES:
        lowered = raw.strip().casefold()
        if lowered in {"true", "false"}:
            return {tag: lowered == "true"}
        degraded.add(where, f"{tag} não booleano: {raw!r}")
        return {}
    if tag in _ENUM_PROPERTIES:
        lowered = raw.strip().casefold()
        if lowered in _ENUM_PROPERTIES[tag]:
            return {tag: lowered}
        degraded.add(where, f"{tag} com valor não suportado: {raw!r}")
        return {}
    if tag == "zIndex":
        numbers = _numbers(raw)
        if numbers is None or len(numbers) != 1:
            degraded.add(where, f"zIndex não numérico: {raw!r}")
            return {}
        return {"layer": max(0, min(1024, int(numbers[0])))}
    return {}


def _binding(node: ET.Element, tag: str, degraded: _Degraded, where: str) -> dict[str, str] | None:
    """Resolve o vínculo de dado do elemento, quando ele tiver um.

    Três origens, nesta ordem: ``<metadata>`` explícito, ``<imageType>`` para
    arte, e o vínculo implícito de ``clock``/``datetime``. Elemento sem nenhuma
    delas simplesmente não tem vínculo — o que é normal para arte estática.
    """
    declared = (node.findtext("metadata") or "").strip()
    if declared:
        target = _METADATA_FIELDS.get(declared)
        if target is None:
            degraded.add(where, f"campo de metadado não suportado: {declared!r}")
            return None
        return {"source": "metadata", "field": target}

    image_type = (node.findtext("imageType") or "").strip()
    if image_type.casefold() == "none":
        # Declaração explícita de "sem mídia aqui" — ausência pedida, não falha.
        return None
    if image_type:
        # ES-DE aceita lista de fallback: "cover,screenshot,miximage". O IR
        # guarda o primeiro que soubermos traduzir, que é a intenção primária.
        for candidate in image_type.split(","):
            target = _MEDIA_FIELDS.get(candidate.strip())
            if target is not None:
                return {"source": "media", "field": target}
        degraded.add(where, f"slot de mídia não suportado: {image_type!r}")
        return None

    implicit = _IMPLICIT_BINDINGS.get(tag)
    return dict(implicit) if implicit else None


def _element(
    node: ET.Element,
    index: int,
    variables: dict[str, str],
    degraded: _Degraded,
) -> dict[str, Any] | None:
    kind = _ELEMENT_KINDS.get(node.tag)
    name = (node.get("name") or "").strip()
    where = f"{node.tag}[{name or index}]"
    if kind is None:
        degraded.add(node.tag, "elemento sem equivalente no IR")
        return None

    element: dict[str, Any] = {
        "id": _ID_SAFE.sub("_", f"{node.tag}-{name or index}")[:64],
        "kind": kind,
    }
    if name:
        element["name"] = name[:64]

    layout: dict[str, Any] = {}
    appearance: dict[str, Any] = {}
    for child in node:
        raw = (child.text or "").strip()
        if not raw:
            continue
        resolved, unresolved = interpolate(raw, variables)
        if unresolved:
            # Variável não declarada é dado faltando, não valor: registrar e
            # descartar a propriedade preserva o resto do elemento.
            degraded.add(f"{where}/{child.tag}", f"variável não resolvida: {unresolved}")
            continue
        parsed = _property(child.tag, resolved, degraded, f"{where}/{child.tag}")
        for key, value in parsed.items():
            if key in {"visible", "opacity", "layer"} or key in _COLOR_PROPERTIES:
                appearance[key] = value
            else:
                layout[key] = value

    if layout:
        element["layout"] = layout
    if appearance:
        element["appearance"] = appearance

    if kind in {"image", "video", "sound"}:
        raw_path = (node.findtext("path") or node.findtext("staticImage") or "").strip()
        if raw_path:
            resolved, unresolved = interpolate(raw_path, variables)
            if not unresolved:
                # Template ANTES de caminho literal: `${system.theme}` sobrevive à
                # interpolação de variáveis e só aqui ganha significado. Testar
                # literal primeiro o recusaria como caminho inseguro, que foi o
                # que descartou a arte por sistema na primeira versão.
                template = asset_template(resolved, degraded, f"{where}/path")
                if template is not None:
                    element["assetTemplate"] = template
                else:
                    asset = _asset(resolved, degraded, f"{where}/path")
                    if asset:
                        element["asset"] = asset

    binding = _binding(node, node.tag, degraded, where)
    if binding:
        element["binding"] = binding

    if kind == "text" and "binding" not in element:
        raw_text = (node.findtext("text") or "").strip()
        if raw_text:
            resolved, unresolved = interpolate(raw_text, variables)
            if not unresolved:
                element["text"] = resolved[:512]

    # Um elemento sem asset, sem vínculo, sem texto e sem layout não descreve
    # nada renderizável. Emiti-lo encheria a cena de nós vazios e inflaria a
    # cobertura declarada com elementos que não desenham um pixel.
    if not any(
        key in element
        for key in ("layout", "asset", "assetTemplate", "binding", "text", "appearance")
    ):
        degraded.add(where, "elemento sem propriedade compreendida")
        return None
    return element


def _view_nodes(root: ET.Element, selection: Selection) -> list[ET.Element]:
    """Views do escopo global mais as da variante escolhida, nessa ordem.

    ``<variant>`` carrega views próprias (148 nos arquivos medidos). Ignorá-las
    descartaria a diferença entre "detailed" e "simple", que é justamente o que a
    variante existe para expressar.
    """
    nodes = list(root.findall("view"))
    for tag, attribute in (("variant", "variant"), ("aspectRatio", "aspect_ratio")):
        chosen = getattr(selection, attribute)
        if not chosen:
            continue
        for block in root.iter(tag):
            names = {part.strip() for part in (block.get("name") or "").split(",")}
            # ``all`` é o curinga do ES-DE: vale para qualquer escolha.
            if chosen in names or "all" in names:
                nodes.extend(block.findall("view"))
                # ``<aspectRatio>`` aninha ``<variant>`` nos temas medidos, e é
                # nesse nível que a geometria específica de cada combinação mora.
                for nested in block.iter("variant"):
                    nested_names = {part.strip() for part in (nested.get("name") or "").split(",")}
                    if not selection.variant or selection.variant in nested_names:
                        nodes.extend(nested.findall("view"))
    return nodes


def _views(
    view_nodes: list[ET.Element], variables: dict[str, str], degraded: _Degraded
) -> list[dict[str, Any]]:
    """Compila os ``<view>``, expandindo os nomes agrupados por vírgula.

    ``<view name="system,gamelist">`` declara o MESMO conteúdo para duas views —
    é como temas reais publicam os elementos comuns. Expandir aqui, e mesclar com
    os blocos específicos que vierem depois, reproduz a ordem de precedência do
    ES-DE: o que vem depois complementa o que veio antes.
    """
    collected: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for view_node in view_nodes:
        names = [part.strip() for part in (view_node.get("name") or "").split(",")]
        if _VIEW_WILDCARD in names:
            # `<view name="all">` vale para todas as views do contrato.
            targets = sorted(_VIEW_NAMES)
        else:
            targets = [name for name in names if name in _VIEW_NAMES]
            for unknown in (name for name in names if name and name not in _VIEW_NAMES):
                degraded.add(f"view[{unknown}]", "view desconhecida no contrato ES-DE")
        if not targets:
            continue
        elements: list[dict[str, Any]] = []
        for index, node in enumerate(list(view_node)):
            compiled = _element(node, index, variables, degraded)
            if compiled is not None:
                elements.append(compiled)
        for target in targets:
            if target not in collected:
                collected[target] = []
                order.append(target)
            bucket = collected[target]
            for compiled in elements:
                existing = _find_element(bucket, compiled["id"])
                if existing is not None:
                    _merge_element(existing, compiled)
                    continue
                if len(bucket) >= MAX_ELEMENTS_PER_VIEW:
                    degraded.add(f"view[{target}]", f"limite de {MAX_ELEMENTS_PER_VIEW} elementos")
                    break
                bucket.append(compiled)

    return [{"id": name, "elements": collected[name]} for name in order[:MAX_VIEWS]]


def _find_element(bucket: list[dict[str, Any]], element_id: str) -> dict[str, Any] | None:
    for candidate in bucket:
        if candidate["id"] == element_id:
            return candidate
    return None


def _merge_element(into: dict[str, Any], extra: dict[str, Any]) -> None:
    """Funde duas declarações do MESMO elemento, a posterior vencendo empate.

    Um tema ES-DE parte o elemento entre arquivos: ``theme.xml`` diz qual arte
    ele usa e ``aspect-ratio-16-10.xml`` diz onde ele fica. São o mesmo
    ``<image name="system-content">``, e o ES-DE os funde por nome dentro da
    view. Empilhá-los como dois elementos produzia exatamente o que a medição
    mostrou: um com arte e sem posição, outro com posição e sem arte, e nenhum
    dos dois desenhável.
    """
    for key, value in extra.items():
        if key in {"layout", "appearance"} and isinstance(value, dict):
            merged = dict(into.get(key) or {})
            merged.update(value)
            into[key] = merged
        elif key not in {"id", "kind"}:
            into[key] = value


def compile_theme(
    theme_xml: str,
    *,
    theme_id: str,
    name: str | None = None,
    author: str | None = None,
    license_id: str | None = None,
    aspect_ratio: str | None = None,
    selection: Selection | None = None,
) -> dict[str, Any]:
    """Compila um XML de tema ES-DE no IR de cena.

    Nunca levanta por elemento desconhecido: o não traduzido vai para
    ``degraded`` e a cena continua renderizável. Só XML malformado é fatal,
    porque aí não há o que compilar.
    """
    try:
        root = ET.fromstring(theme_xml)  # noqa: S314 - conteúdo local, já limitado
    except ET.ParseError as exc:
        raise SteamZeroError("E-THEME-MANIFEST", detail=f"tema ES-DE inválido: {exc}") from exc
    if root.tag != "theme":
        raise SteamZeroError(
            "E-THEME-MANIFEST",
            detail=f"raiz esperada <theme>, encontrada <{root.tag}>",
        )

    degraded = _Degraded()
    chosen = selection or Selection()
    variables = collect_variables(root, chosen)
    views = _views(_view_nodes(root, chosen), variables, degraded)

    for include in root.findall("include"):
        # ``<include>`` é resolvido pela camada que conhece o disco, não aqui.
        # Registrar mantém visível que a cena está incompleta em relação à
        # origem, em vez de deixar parecer que o tema simplesmente tem menos.
        target = (include.text or "").strip()
        if target:
            degraded.add("include", f"arquivo incluído não resolvido nesta compilação: {target}")

    scene: dict[str, Any] = {
        "schemaVersion": 1,
        "id": theme_id,
        "views": views,
        "shortcuts": ["accept", "cancel", "details", "nextPage", "prevPage"],
    }
    if name:
        scene["name"] = name
    origin: dict[str, Any] = {"family": "esde"}
    if author:
        origin["author"] = author
    if license_id:
        origin["license"] = license_id
    scene["origin"] = origin
    if aspect_ratio:
        scene["aspectRatio"] = aspect_ratio
    if chosen.to_dict():
        scene["selection"] = chosen.to_dict()
    if variables:
        scene["variables"] = variables
    if degraded.entries:
        scene["degraded"] = degraded.entries
    return scene


def fidelity_report(scene: dict[str, Any]) -> dict[str, Any]:
    """Quanto da cena foi compreendido — para declarar fidelidade, não prometer."""
    views = scene.get("views", [])
    elements = sum(len(view.get("elements", [])) for view in views)
    degraded = len(scene.get("degraded", []))
    total = elements + degraded
    return {
        "elements": elements,
        "degraded": degraded,
        "views": [view["id"] for view in views],
        "coverage": round(elements / total, 4) if total else 0.0,
        "assets": sorted(
            {
                str(element["asset"])
                for view in views
                for element in view.get("elements", [])
                if element.get("asset")
            }
        ),
        "reasons": sorted({entry["reason"].split(":")[0] for entry in scene.get("degraded", [])}),
    }
