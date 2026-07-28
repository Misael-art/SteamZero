# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Importação de temas ES-DE para o contrato de tokens do SteamZero.

O plano do framework de temas estabelece "um contrato, duas origens": temas
nativos e externos obedecem ao mesmo esquema. Este módulo honra isso —
**converte** um tema ES-DE em ``steamzero-theme-v1`` em vez de introduzir um
segundo renderizador. O ganho é a identidade visual (paleta e papel de parede); a
perda é o layout, que pertence ao frontend de origem.

Medições que motivaram o desenho (spike de 2026-07-27, tema Canvas):

- o tema inteiro tem 165 MB, dos quais 87% são imagens de sistema;
- ``colors.xml`` tem 27 KB e carrega toda a paleta;
- ``wallpapers/<esquema>.webp`` tem de 5 a 200 KB e é o único asset que mapeia
  para um slot do SteamZero.

Importar paleta e papel de parede custa centenas de KB em vez de centenas de MB,
e é o teto de fidelidade que o contrato de tokens comporta.

**Nada é inventado.** Onde o ES-DE não tem equivalente semântico — sucesso, aviso,
perigo — o token é OMITIDO e herdado do tema base por ``extends``. Derivar um
"vermelho de erro" de uma paleta que não o declara produziria um valor plausível e
errado, que é pior que a herança explícita.
"""

from __future__ import annotations

import colorsys
import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from steamzero.core.errors import SteamZeroError

_HEX = re.compile(r"^[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$")
_SCHEME_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_THEME_ID = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)+$")

#: Tokens do SteamZero alimentados diretamente por tags do ES-DE, em ordem de
#: preferência. Um tema pode declarar só parte delas.
_DIRECT_MAP: dict[str, tuple[str, ...]] = {
    "background": ("backgroundColor",),
    "sidebar": ("systemCarouselTextBackgroundColor", "backgroundColor"),
    "text": ("gamelistSelectedColor", "gridNameColor", "rowSystemColor"),
    "textMuted": ("helpTextColor", "systemColor", "gamelistPrimaryColor"),
    "accent": ("gridSelectorColor", "gamelistSelectorColor"),
    "focus": ("gridSelectorColor", "gamelistSelectorColor"),
}

#: Tokens sem equivalente no ES-DE que são DERIVADOS de outros já extraídos.
#: Derivação só é legítima quando o valor é uma função óbvia da base — uma
#: superfície é o fundo levemente clareado, uma borda fica entre fundo e texto.
_DERIVED = ("surface", "surfaceRaised", "surfaceSelected", "border", "textDisabled", "accentStrong")

#: Semânticos que NÃO são derivados. O ES-DE não os declara e inferi-los daria um
#: valor plausível e errado; herdar do tema base é a resposta honesta.
INHERITED_TOKENS = (
    "success",
    "successSurface",
    "warning",
    "warningSurface",
    "danger",
    "dangerSurface",
)


#: Limites herdados de ``adapters.theme_catalog``: um pacote importado precisa
#: passar na mesma validação de um tema escrito à mão.
MAX_ASSET_BYTES = 16 * 1024 * 1024
ALLOWED_ASSET_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".svg"})

#: Onde temas ES-DE publicam papel de parede por esquema. A variante "Alternate"
#: existe em vários temas e é preferida quando o principal não cobre o esquema.
_WALLPAPER_DIRS = ("wallpapers", "wallpapers/Alternate")


@dataclass(frozen=True)
class AssetPlan:
    """O que buscar da origem e onde gravar dentro do pacote.

    O domínio decide; quem baixa é a camada de adapters. Separar as duas coisas
    é o que permite testar a decisão sem rede.
    """

    slot: str
    source_path: str
    target_path: str
    size: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot": self.slot,
            "sourcePath": self.source_path,
            "targetPath": self.target_path,
            "size": self.size,
        }


def resolve_assets(scheme: str, available: Mapping[str, int]) -> list[AssetPlan]:
    """Decide quais arquivos do tema de origem preenchem os slots do SteamZero.

    ``available`` é o inventário do repositório de origem (caminho -> bytes),
    obtido da árvore do git sem baixar nada.

    Dos três slots do contrato, só ``background`` tem equivalente em temas ES-DE.
    ``logo`` e ``sidebar`` NÃO têm: o que um tema ES-DE chama de logo é arte por
    SISTEMA (um logo do SNES, um do Mega Drive), não a marca do tema. Preencher
    esses slots com arte de sistema colocaria o logo do SNES como marca da
    central inteira — plausível de implementar, errado de exibir.
    """
    if not _SCHEME_NAME.match(scheme):
        raise SteamZeroError("E-THEME-MANIFEST", detail=f"esquema inválido: {scheme!r}")

    for directory in _WALLPAPER_DIRS:
        for suffix in (".webp", ".png", ".jpg", ".jpeg"):
            candidate = f"{directory}/{scheme}{suffix}"
            size = available.get(candidate)
            if size is None:
                continue
            if size <= 0:
                continue
            if size > MAX_ASSET_BYTES:
                # Grande demais para o contrato: seguir sem papel de parede é
                # melhor que produzir um pacote que a validação vai recusar.
                continue
            return [
                AssetPlan(
                    slot="background",
                    source_path=candidate,
                    target_path=f"assets/background{suffix}",
                    size=size,
                )
            ]
    return []


def unsupported_slots() -> dict[str, str]:
    """Slots que ficam vazios, com a razão — para a UI não sugerir que faltou algo."""
    return {
        "logo": (
            "temas ES-DE não declaram marca própria; o que eles chamam de logo é arte por sistema"
        ),
        "sidebar": "temas ES-DE não têm equivalente de barra lateral",
    }


@dataclass(frozen=True)
class ImportedScheme:
    """Um esquema de cor do tema de origem, já convertido."""

    name: str
    color: dict[str, str]
    wallpaper: str | None = None
    assets: tuple[AssetPlan, ...] = field(default_factory=tuple)
    source_tags: int = 0
    derived: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_monochrome(self) -> bool:
        """Sem cor de destaque distinguível.

        Alguns esquemas têm sua identidade na arte, não na paleta; convertê-los
        produz cinza genérico. Saber disso antes de importar evita prometer
        fidelidade que não existe.
        """
        accent = self.color.get("accent")
        return accent is None or _saturation(accent) < 0.08


def _rgb(value: str) -> tuple[float, float, float]:
    raw = value.lstrip("#")
    return tuple(int(raw[i : i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def _hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c * 255))):02x}" for c in rgb)


def _saturation(value: str) -> float:
    return colorsys.rgb_to_hls(*_rgb(value))[2]


def _mix(a: str, b: str, ratio: float) -> str:
    ra, rb = _rgb(a), _rgb(b)
    return _hex(tuple(x + (y - x) * ratio for x, y in zip(ra, rb, strict=True)))  # type: ignore[arg-type]


def parse_color_schemes(colors_xml: str) -> dict[str, dict[str, str]]:
    """Extrai a paleta por esquema de um ``colors.xml`` do ES-DE.

    Um bloco ``<colorScheme name="a,b,c">`` vale para vários esquemas, e o mesmo
    esquema aparece em blocos diferentes — a primeira definição vence, como no
    próprio ES-DE.
    """
    try:
        root = ET.fromstring(colors_xml)  # noqa: S314 - conteúdo já baixado e limitado
    except ET.ParseError as exc:
        raise SteamZeroError("E-THEME-MANIFEST", detail=f"colors.xml inválido: {exc}") from exc

    schemes: dict[str, dict[str, str]] = {}
    for block in root.iter("colorScheme"):
        names = [name.strip() for name in (block.get("name") or "").split(",")]
        for element in block.iter():
            value = (element.text or "").strip()
            if not _HEX.match(value):
                continue
            for name in names:
                if name:
                    schemes.setdefault(name, {}).setdefault(element.tag, f"#{value[:6].lower()}")
    return schemes


def map_to_tokens(source: dict[str, str]) -> tuple[dict[str, str], tuple[str, ...]]:
    """Converte tags do ES-DE nos tokens de cor do SteamZero.

    Devolve os tokens e quais deles foram derivados, para que a origem de cada
    valor seja auditável em vez de indistinguível.
    """
    tokens: dict[str, str] = {}
    for target, candidates in _DIRECT_MAP.items():
        for tag in candidates:
            if tag in source:
                tokens[target] = source[tag]
                break

    background = tokens.get("background")
    text = tokens.get("text")
    accent = tokens.get("accent")
    derived: list[str] = []

    if background and text:
        # Superfícies caminham do fundo em direção ao texto, em passos pequenos:
        # é o que preserva a hierarquia visual sem inventar um tom novo.
        tokens.setdefault("surface", _mix(background, text, 0.06))
        tokens.setdefault("surfaceRaised", _mix(background, text, 0.11))
        tokens.setdefault("surfaceSelected", _mix(background, text, 0.17))
        tokens.setdefault("border", _mix(background, text, 0.24))
        derived += ["surface", "surfaceRaised", "surfaceSelected", "border"]
    if background and tokens.get("textMuted"):
        tokens.setdefault("textDisabled", _mix(tokens["textMuted"], background, 0.45))
        derived.append("textDisabled")
    if accent:
        tokens.setdefault("accentStrong", _mix(accent, "#000000", 0.35))
        derived.append("accentStrong")

    return tokens, tuple(d for d in derived if d in tokens)


def import_scheme(
    scheme: str,
    colors_xml: str,
    *,
    available_assets: Mapping[str, int] | None = None,
) -> ImportedScheme:
    """Converte um esquema nomeado, resolvendo também os assets.

    ``available_assets`` é o inventário do repositório de origem (caminho ->
    bytes). Quando fornecido, o papel de parede do esquema é localizado e entra
    no plano; sem ele, a importação é só de paleta.
    """
    if not _SCHEME_NAME.match(scheme):
        raise SteamZeroError("E-THEME-MANIFEST", detail=f"esquema inválido: {scheme!r}")
    schemes = parse_color_schemes(colors_xml)
    source = schemes.get(scheme)
    if not source:
        raise SteamZeroError(
            "E-THEME-NOT-FOUND", detail=f"esquema '{scheme}' não existe neste tema"
        )
    tokens, derived = map_to_tokens(source)
    if "background" not in tokens:
        raise SteamZeroError(
            "E-THEME-MANIFEST",
            detail=f"esquema '{scheme}' não declara cor de fundo; nada a importar",
        )
    assets = resolve_assets(scheme, available_assets) if available_assets else []
    background = next((a for a in assets if a.slot == "background"), None)
    return ImportedScheme(
        name=scheme,
        color=tokens,
        wallpaper=background.target_path if background else None,
        assets=tuple(assets),
        source_tags=len(source),
        derived=derived,
    )


def build_manifest(
    imported: ImportedScheme,
    *,
    theme_id: str,
    name: str,
    author: str,
    license_id: str,
    version: str = "1.0.0",
    extends: str = "org.steamzero.default",
    homepage: str | None = None,
) -> dict[str, Any]:
    """Emite o ``theme.json`` no contrato nativo.

    ``extends`` não é detalhe: os tokens semânticos que o ES-DE não declara
    chegam por herança, e é isso que permite omiti-los em vez de inventá-los.
    """
    if not _THEME_ID.match(theme_id):
        raise SteamZeroError("E-THEME-MANIFEST", detail=f"id inválido: {theme_id!r}")
    if not license_id.strip():
        raise SteamZeroError(
            "E-THEME-MANIFEST",
            detail="licença é obrigatória: tema importado sem licença confirmada não entra",
        )

    manifest: dict[str, Any] = {
        "schemaVersion": 1,
        "kind": "steamzero-theme-v1",
        "id": theme_id,
        "name": name,
        "version": version,
        "author": author,
        "license": license_id,
        "description": (
            f"Paleta importada do tema ES-DE '{name}' (esquema {imported.name}). "
            "Layout e composição de tela pertencem ao tema original."
        ),
        "compatibility": {"themeApi": 1},
        "extends": extends,
        "tokens": {"color": dict(imported.color)},
        "assets": {},
    }
    if homepage:
        manifest["homepage"] = homepage
    if imported.wallpaper:
        manifest["assets"]["background"] = imported.wallpaper
    return manifest


def import_report(imported: ImportedScheme) -> dict[str, Any]:
    """Relatório do que sobreviveu à conversão, para a UI não prometer demais."""
    return {
        "scheme": imported.name,
        "sourceTags": imported.source_tags,
        "tokens": len(imported.color),
        "derived": list(imported.derived),
        "inherited": list(INHERITED_TOKENS),
        "monochrome": imported.is_monochrome,
        "assets": [a.to_dict() for a in imported.assets],
        "assetBytes": sum(a.size for a in imported.assets),
        "unsupportedSlots": unsupported_slots(),
        "fidelity": "palette+background" if imported.assets else "palette-only",
    }
