# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Compilação de layouts RetroFE para o IR de cena.

RetroFE é declarativo: o tema é uma máquina de estados de animação disparada por
eventos de navegação, sem código. Medido no layout Aeon Nox (1121 linhas): 648
``<animate>``, 629 ``<set>``, e pares ``on*Enter``/``on*Exit`` para menu, jogo,
destaque, playlist e salto de menu.

Isso torna RetroFE o primeiro emissor certo do IR: cobre hierarquia de menu,
bindings de metadado, relógio e eventos **sem exigir execução de código de
terceiros**, que o ``PLUGIN-MODEL`` proíbe hoje.

Princípio que atravessa o módulo: **o que não é compreendido degrada e é
registrado, nunca inventado nem silenciado.** Cada elemento ou atributo recusado
entra em ``degraded`` com a razão, e é isso que permite declarar fidelidade em vez
de prometê-la.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

from steamzero.core.errors import SteamZeroError

#: Elementos do RetroFE que sabemos traduzir.
_ELEMENT_KINDS = {
    "image": "image",
    "text": "text",
    "reloadableText": "boundText",
    # Texto que rola quando não cabe. O IR trata como texto vinculado; a rolagem
    # é decisão do renderizador, não do tema.
    "reloadableScrollingText": "boundText",
    "reloadableImage": "boundImage",
    "reloadableVideo": "video",
    "video": "video",
    "menu": "menu",
    "container": "container",
    # Som de navegação. Temas RetroFE reais usam bastante: 92 elementos <sound>
    # nos 29 layouts locais. Ignorá-los descartaria a camada sonora inteira.
    "sound": "sound",
    "reloadableAudio": "sound",
}

#: Eventos do RetroFE que viram eventos do IR. Nome idêntico, sem tradução.
_EVENTS = {
    "onEnter": "enter",
    "onExit": "exit",
    "onMenuEnter": "menuEnter",
    "onMenuExit": "menuExit",
    "onGameEnter": "gameEnter",
    "onGameExit": "gameExit",
    "onHighlightEnter": "highlightEnter",
    "onHighlightExit": "highlightExit",
    "onPlaylistEnter": "playlistEnter",
    "onPlaylistExit": "playlistExit",
    "onMenuJumpEnter": "menuJumpEnter",
    "onMenuJumpExit": "menuJumpExit",
}

#: Propriedades animáveis. Fechado: no Aeon Nox, alpha responde por 615 das 648
#: animações, seguida de y (23) e x (2). "nop" existe no RetroFE como espera.
_ANIMATABLE = {
    "alpha",
    "x",
    "y",
    "width",
    "height",
    "maxWidth",
    "maxHeight",
    "angle",
    "nop",
    # Observadas na varredura dos 29 layouts: volume domina (70), seguida de
    # backgroundAlpha (11) e das propriedades de container.
    "volume",
    "backgroundAlpha",
    "xOrigin",
    "yOrigin",
    "xOffset",
    "yOffset",
    "containerX",
    "containerY",
    "containerWidth",
    "containerHeight",
    "fontSize",
}

#: ``type`` de ``reloadableText`` → campo de metadado do IR. O prefixo ``lb_`` é
#: do LaunchBox e mapeia para o mesmo campo semântico.
_METADATA_FIELDS = {
    "title": "title",
    "year": "year",
    "genre": "genre",
    "manufacturer": "manufacturer",
    "developer": "developer",
    "publisher": "publisher",
    "players": "players",
    "numberPlayers": "players",
    "rating": "rating",
    "description": "description",
    "platform": "platform",
    "region": "region",
    "collection": "collection",
    # Posição dentro da coleção: é o que permite "3 de 47" e navegação alfabética.
    "collectionSize": "collectionSize",
    "collectionIndex": "collectionIndex",
    "collectionIndexSize": "collectionIndexSize",
    "cpu": "cpu",
    # Campos que temas RetroFE reais usam e o vocabulário inicial não previa.
    "story": "story",
    "type": "type",
    "generation": "generation",
    "media": "media",
}

#: ``type`` que na verdade é valor de sistema, não metadado do jogo.
_SYSTEM_FIELDS = {
    "time": "time",
    "date": "date",
    "gameCount": "gameCount",
    "collectionName": "collectionName",
}

#: ``type`` de ``reloadableImage`` → slot de mídia.
_MEDIA_FIELDS = {
    "logo": "logo",
    "boxFront": "boxFront",
    "boxBack": "boxBack",
    "marquee": "marquee",
    "screenshot": "screenshot",
    "titlescreen": "titlescreen",
    "background": "background",
    "fanart": "fanart",
    "banner": "banner",
    "poster": "poster",
    "cartridge": "cartridge",
    "video": "video",
    "device": "device",
    # Slots observados na varredura. firstLetter alimenta navegação alfabética.
    "firstLetter": "firstLetter",
    "settingshot": "settingshot",
    "score": "score",
    "playlist": "playlist",
    "genre": "genre",
    "manufacturer": "manufacturer",
    "isfavorite": "isFavorite",
    "numberplayers": "players",
}

_ORIGINS = {"left", "center", "right", "top", "bottom"}
_KEYWORDS = {"center", "left", "right", "top", "bottom", "stretch"}
_ID_SAFE = re.compile(r"[^a-zA-Z0-9_-]")
#: Espaço, parênteses e apóstrofo são caracteres legítimos em nome de arquivo —
#: 36 assets dos layouts locais os usam. O que precisa ser recusado é travessia,
#: caminho absoluto e esquema, verificados à parte.
_ASSET_SAFE = re.compile(
    r"^[a-zA-Z0-9_. /()'&-]+\.(png|jpg|jpeg|webp|svg|wav|ogg|mp3)$", re.IGNORECASE
)


_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_TAG = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9_.-]*)([^>]*?)(/?)>", re.DOTALL)
#: Fechamento anônimo ``</>``, encontrado no layout "Aura - Collection". Um
#: parser tolerante fecha o elemento corrente; a stdlib recusa.
_ANON_CLOSE = re.compile(r"</\s*>")
_ATTR = re.compile(r'([a-zA-Z][a-zA-Z0-9_.:-]*)\s*=\s*"([^"]*)"')


def _normalize_attributes(attributes: str) -> tuple[str, int, bool]:
    """Reescreve os atributos de uma tag em forma canônica.

    Defeitos observados em layouts RetroFE reais, todos aceitos pelo parser
    tolerante do RetroFE e recusados pelo da stdlib:

    - ``type="x"to ="-5"`` — sem espaço entre atributos e com espaço antes do
      ``=`` (14 dos 29 layouts locais falhavam só por isto);
    - ``alpha="0.5" alpha="1"`` — atributo duplicado.

    A reescrita só acontece quando é **comprovadamente sem perda**: se remover
    tudo que casou deixar qualquer resto não-branco, devolvemos o original
    intocado. Reescrever às cegas poderia descartar um atributo que a expressão
    não reconheceu, trocando um erro de parse por dado perdido em silêncio.
    """
    matches = list(_ATTR.finditer(attributes))
    if not matches:
        return attributes, 0, False
    residue = _ATTR.sub("", attributes)
    if residue.strip():
        return attributes, 0, False

    seen: set[str] = set()
    kept: list[str] = []
    dropped = 0
    for match in matches:
        name = match.group(1)
        if name in seen:
            dropped += 1
            continue
        seen.add(name)
        kept.append(f'{name}="{match.group(2)}"')
    rendered = (" " + " ".join(kept)) if kept else ""
    return rendered, dropped, rendered != attributes


def _sanitize(layout_xml: str) -> tuple[str, list[str]]:
    """Torna parseável um layout RetroFE do mundo real.

    Layouts reais NÃO são XML bem formado, e as duas causas observadas no Aeon
    Nox são independentes:

    1. separadores de seção como ``<!------------->`` — a especificação proíbe
       ``--`` dentro de comentário;
    2. **tags de fechamento trocadas** — ``<onMenuJumpEnter>`` fechando com
       ``</onMenuEnter>``, resultado de copiar e colar. O parser do RetroFE
       tolera; o da stdlib não.

    Reparar é o que permite compilar temas que existem em vez de só os
    teoricamente corretos. Cada reparo é DEVOLVIDO para virar registro — corrigir
    em silêncio esconderia que o arquivo de origem foi tocado.
    """
    cleaned = _COMMENT.sub("", layout_xml)
    notes: list[str] = []
    if cleaned != layout_xml:
        notes.append("comentários removidos antes do parse (XML não conforme)")

    anonymous = len(_ANON_CLOSE.findall(cleaned))
    if anonymous:
        # Marcador que o tokenizador reconhece; o nome real é resolvido pela
        # pilha logo abaixo, que é o que um parser tolerante faz.
        cleaned = _ANON_CLOSE.sub("</anonclose>", cleaned)
        notes.append(f"{anonymous} fechamento(s) anônimo(s) '</>' resolvidos pela pilha")

    stack: list[str] = []
    out: list[str] = []
    cursor = 0
    repairs = 0
    duplicates = 0
    normalized = 0
    for match in _TAG.finditer(cleaned):
        out.append(cleaned[cursor : match.start()])
        cursor = match.end()
        closing, name, attributes, self_closing = match.groups()
        if self_closing:
            fixed, dropped, changed = _normalize_attributes(attributes)
            duplicates += dropped
            normalized += 1 if changed and not dropped else 0
            out.append(f"<{name}{fixed}/>" if changed else match.group(0))
            continue
        if not closing:
            stack.append(name)
            fixed, dropped, changed = _normalize_attributes(attributes)
            duplicates += dropped
            normalized += 1 if changed and not dropped else 0
            out.append(f"<{name}{fixed}>" if changed else match.group(0))
            continue
        if stack and stack[-1] != name:
            # Fechamento não bate com a abertura corrente: confiar no
            # ANINHAMENTO, que é o que o RetroFE faz, e reescrever o nome.
            expected = stack.pop()
            out.append(f"</{expected}>")
            repairs += 1
            continue
        if stack:
            stack.pop()
        out.append(match.group(0))
    out.append(cleaned[cursor:])
    if repairs:
        notes.append(f"{repairs} tag(s) de fechamento reparadas por aninhamento")
    if duplicates:
        notes.append(f"{duplicates} atributo(s) duplicado(s) descartado(s)")
    if normalized:
        notes.append(f"{normalized} tag(s) com atributos normalizados (espaçamento não conforme)")
    return "".join(out), notes


@dataclass
class _Degraded:
    entries: list[dict[str, str]] = field(default_factory=list)

    def add(self, element: str, reason: str) -> None:
        # Limite alto o bastante para diagnosticar, baixo o bastante para não
        # transformar um layout hostil em consumo de memória.
        if len(self.entries) < 256:
            self.entries.append({"element": element[:64], "reason": reason[:256]})


def _coordinate(raw: str | None, degraded: _Degraded, where: str) -> Any:
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        # Atributo vazio é ausência declarada, não erro: não vale registro.
        return None
    lowered = value.casefold()
    if lowered == "stretched":
        lowered = "stretch"
    if lowered in _KEYWORDS:
        return lowered
    if value.endswith("%"):
        try:
            float(value[:-1])
        except ValueError:
            degraded.add(where, f"percentual inválido: {value!r}")
            return None
        return value
    try:
        number = float(value)
    except ValueError:
        degraded.add(where, f"coordenada não numérica: {value!r}")
        return None
    if not -8192 <= number <= 8192:
        degraded.add(where, f"coordenada fora de faixa: {number}")
        return None
    return number


def _layout(node: ET.Element, degraded: _Degraded, where: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for attribute in ("x", "y", "width", "height", "maxWidth", "maxHeight"):
        value = _coordinate(node.get(attribute), degraded, where)
        if value is not None:
            out[attribute] = value
    for attribute in ("xOffset", "yOffset"):
        value = _coordinate(node.get(attribute), degraded, where)
        if isinstance(value, int | float):
            out[attribute] = float(value)
        elif value is not None:
            # Offset por palavra-chave existe no RetroFE; o IR guarda no eixo
            # correspondente, que é onde o renderizador sabe interpretá-lo.
            # Offset por palavra-chave vira posição no mesmo eixo: "yOffset=center"
            # significa centralizado em y, e é assim que o renderizador o lê.
            out[attribute.replace("Offset", "")] = value
    for attribute in ("xOrigin", "yOrigin"):
        raw = node.get(attribute)
        if raw is None:
            continue
        if raw in _ORIGINS:
            out[attribute] = raw
        else:
            try:
                number = float(raw)
            except ValueError:
                degraded.add(where, f"{attribute} desconhecido: {raw!r}")
                continue
            if 0.0 <= number <= 1.0:
                out[attribute] = number
            else:
                # RetroFE também aceita origem absoluta em pixels. Normalizar
                # exigiria conhecer a caixa do pai, que só o renderizador tem;
                # guardamos como offset para não descartar a intenção.
                out[attribute.replace("Origin", "Offset")] = number
    for attribute, lo, hi in (
        ("alpha", 0.0, 1.0),
        ("angle", -360.0, 360.0),
        ("fontSize", 1.0, 512.0),
    ):
        raw = node.get(attribute)
        if raw is None:
            continue
        try:
            number = float(raw)
        except ValueError:
            degraded.add(where, f"{attribute} não numérico: {raw!r}")
            continue
        if lo <= number <= hi:
            out[attribute] = number
        else:
            degraded.add(where, f"{attribute} fora de faixa: {number}")
    raw_layer = node.get("layer")
    if raw_layer is not None:
        try:
            layer = int(float(raw_layer))
        except ValueError:
            degraded.add(where, f"layer não numérico: {raw_layer!r}")
        else:
            out["layer"] = max(0, min(32, layer))
    return out


def _binding(node: ET.Element, kind: str, degraded: _Degraded, where: str) -> dict[str, Any] | None:
    declared = (node.get("type") or "").strip()
    if not declared:
        degraded.add(where, "elemento vinculado sem 'type'")
        return None
    # O RetroFE prefixa campos importados do LaunchBox; o campo semântico é o mesmo.
    field_name = declared[3:] if declared.startswith("lb_") else declared

    if kind == "boundImage":
        # RetroFE permite nomear arte específica do tema como "fanart - Nome do
        # Tema". O slot semântico é o prefixo; o sufixo é decoração do autor.
        # Convenções de nome que temas usam sobre o mesmo slot semântico:
        # "fanart - Nome do Tema", "firstLetter vertical", "playlist2".
        base = field_name.split(" - ", 1)[0].split(" ", 1)[0].strip()
        base = base.rstrip("0123456789") or base
        target = (
            _MEDIA_FIELDS.get(field_name)
            or _MEDIA_FIELDS.get(base)
            or _MEDIA_FIELDS.get(base.casefold())
        )
        if target is None:
            degraded.add(where, f"slot de mídia não suportado: {declared!r}")
            return None
        return {"source": "media", "field": target}

    if field_name in _SYSTEM_FIELDS:
        return {"source": "system", "field": _SYSTEM_FIELDS[field_name]}
    target = _METADATA_FIELDS.get(field_name)
    if target is None:
        degraded.add(where, f"campo de metadado não suportado: {declared!r}")
        return None
    return {"source": "metadata", "field": target}


def _timeline(node: ET.Element, degraded: _Degraded, where: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for block in node.findall("set"):
        raw_duration = block.get("duration", "0")
        try:
            duration = max(0.0, min(60.0, float(raw_duration)))
        except ValueError:
            degraded.add(where, f"duração não numérica: {raw_duration!r}")
            continue
        animations: list[dict[str, Any]] = []
        for item in block.findall("animate"):
            prop = (item.get("type") or "").strip()
            if prop not in _ANIMATABLE:
                degraded.add(where, f"propriedade não animável: {prop!r}")
                continue
            # Destino pode ser número OU palavra-chave: o RetroFE anima para
            # posição relativa ("center"), e recusar isso descartaria animações
            # perfeitamente válidas do tema.
            to_value = _coordinate(item.get("to"), degraded, where)
            if to_value is None:
                degraded.add(where, f"animação de {prop} sem destino utilizável")
                continue
            animation: dict[str, Any] = {"property": prop, "to": to_value}
            if item.get("from") is not None:
                from_value = _coordinate(item.get("from"), degraded, where)
                if from_value is not None:
                    animation["from"] = from_value
            animations.append(animation)
        if animations:
            blocks.append({"duration": duration, "animations": animations[:16]})
    return blocks[:32]


def _menu(node: ET.Element, degraded: _Degraded, where: str) -> dict[str, Any]:
    orientation = (node.get("orientation") or "horizontal").strip()
    if orientation not in {"horizontal", "vertical", "wheel", "grid"}:
        degraded.add(where, f"orientação desconhecida: {orientation!r}")
        orientation = "horizontal"
    out: dict[str, Any] = {"orientation": orientation}
    for attribute, key in (
        ("scrollTime", "scrollTime"),
        ("scrollAcceleration", "scrollAcceleration"),
    ):
        raw = node.get(attribute)
        if raw is None:
            continue
        try:
            out[key] = max(0.0, min(5.0, float(raw)))
        except ValueError:
            degraded.add(where, f"{attribute} não numérico: {raw!r}")
    defaults = node.find("itemDefaults")
    if defaults is not None:
        out["itemDefaults"] = _layout(defaults, degraded, f"{where}/itemDefaults")
    items = [_layout(item, degraded, f"{where}/item") for item in node.findall("item")]
    if items:
        out["items"] = items[:64]
        out["visibleItems"] = min(64, len(items))
    return out


def _element(node: ET.Element, degraded: _Degraded, index: int) -> dict[str, Any] | None:
    kind = _ELEMENT_KINDS.get(node.tag)
    where = f"{node.tag}[{index}]"
    if kind is None:
        degraded.add(node.tag, "elemento sem equivalente no IR")
        return None

    element: dict[str, Any] = {
        "id": _ID_SAFE.sub("_", f"{node.tag}-{index}")[:64],
        "kind": kind,
    }
    layout = _layout(node, degraded, where)
    if layout:
        element["layout"] = layout

    if kind in {"boundText", "boundImage"}:
        binding = _binding(node, kind, degraded, where)
        if binding is None:
            return None
        element["binding"] = binding
    elif kind in {"image", "sound"}:
        source = (node.get("src") or "").strip()
        if not source:
            degraded.add(where, f"{node.tag} sem 'src'")
            return None
        if not _ASSET_SAFE.match(source) or ".." in source:
            # Caminho vindo de tema é dado não confiável: recusar é a única
            # resposta segura, e recusar declarando é o que permite auditoria.
            degraded.add(where, f"caminho de asset recusado: {source!r}")
            return None
        element["asset"] = f"assets/{source.lstrip('./')}"
    elif kind == "text":
        element["text"] = (node.get("value") or node.text or "").strip()[:512]
    elif kind == "menu":
        element["menu"] = _menu(node, degraded, where)

    events: dict[str, Any] = {}
    for tag, name in _EVENTS.items():
        for holder in node.findall(tag):
            timeline = _timeline(holder, degraded, f"{where}/{tag}")
            if timeline:
                events.setdefault(name, []).extend(timeline)
    if events:
        element["on"] = {name: blocks[:32] for name, blocks in events.items()}
    return element


def compile_layout(
    layout_xml: str,
    *,
    theme_id: str,
    name: str | None = None,
    author: str | None = None,
    license_id: str | None = None,
    view_id: str = "main",
    aspect_ratio: str | None = None,
) -> dict[str, Any]:
    """Compila um ``layout.xml`` do RetroFE no IR de cena.

    Nunca levanta por elemento desconhecido: o não traduzido vai para
    ``degraded`` e a cena continua renderizável. Só XML malformado é fatal,
    porque aí não há o que compilar.
    """
    cleaned, repairs = _sanitize(layout_xml)
    try:
        root = ET.fromstring(cleaned)  # noqa: S314 - conteúdo local, já limitado
    except ET.ParseError as exc:
        raise SteamZeroError("E-THEME-MANIFEST", detail=f"layout RetroFE inválido: {exc}") from exc

    degraded = _Degraded()
    for note in repairs:
        # Registrado, não silenciado: quem auditar precisa saber que o arquivo
        # de origem foi tocado antes de ser parseado.
        degraded.add("source", note)
    elements: list[dict[str, Any]] = []
    for index, node in enumerate(list(root)):
        compiled = _element(node, degraded, index)
        if compiled is not None:
            elements.append(compiled)
        if len(elements) >= 512:
            degraded.add("layout", "limite de 512 elementos atingido")
            break

    view: dict[str, Any] = {"id": view_id, "elements": elements}
    if aspect_ratio:
        view["aspectRatio"] = aspect_ratio

    scene: dict[str, Any] = {
        "schemaVersion": 1,
        "id": theme_id,
        "views": [view],
        "shortcuts": ["accept", "cancel", "details", "nextPage", "prevPage"],
    }
    if name:
        scene["name"] = name
    origin: dict[str, Any] = {"family": "retrofe"}
    if author:
        origin["author"] = author
    if license_id:
        origin["license"] = license_id
    scene["origin"] = origin
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
        "coverage": round(elements / total, 4) if total else 0.0,
        "reasons": sorted({entry["reason"].split(":")[0] for entry in scene.get("degraded", [])}),
    }
