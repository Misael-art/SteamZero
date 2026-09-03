# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Da instalação até a cena que o renderizador consegue desenhar.

Fecha o vão entre o que ``scene_esde`` compila e o que a UI mostra. Antes disto
o tema instalado existia como blob e como IR, e não como pixel.

Três coisas acontecem aqui, e nenhuma delas pertence às camadas vizinhas:

1. o grafo de XML é materializado num diretório efêmero — e SÓ o grafo de XML.
   ``resolve_includes`` valida contenção por caminho, e reproduzir essa validação
   sobre um leitor em memória duplicaria a regra que protege contra travessia.
   Os XML somam alguns MB no maior tema medido; a arte, que é o peso, continua
   no store;
2. cada asset do IR vira um caminho de blob, resolvido pelo manifesto. O IR
   carrega caminho relativo ao tema, que não existe no disco: sem esta tradução
   o renderizador pediria arquivo inexistente e desenharia vazio;
3. o que não resolve é REPORTADO, não omitido. Uma cena que esconde o asset
   faltante parece completa e mente sobre a fidelidade.
"""

from __future__ import annotations

import contextlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from steamzero.core import fs, paths
from steamzero.core.errors import SteamZeroError
from steamzero.domain import scene_esde, theme_assets, theme_import_esde_layout

#: Só o grafo de layout é materializado. Arte, fonte, som e vídeo continuam no
#: store e chegam ao renderizador por caminho de blob.
_LAYOUT_SUFFIX = ".xml"

#: Teto de segurança para a materialização. O maior tema medido tem 485 XML.
_MAX_LAYOUT_FILES = 2048


def _manifest_path(themes_root: Path, theme_id: str) -> Path:
    return themes_root / theme_id / "theme.json"


def load_manifest(themes_root: Path, theme_id: str) -> dict[str, Any]:
    """Lê o manifesto do tema instalado, falhando fechado."""
    path = _manifest_path(themes_root, theme_id)
    if not path.is_file():
        raise SteamZeroError("E-THEME-NOT-FOUND", detail=f"tema '{theme_id}' não está instalado")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SteamZeroError(
            "E-THEME-MANIFEST", detail=f"manifesto ilegível de '{theme_id}': {exc}"
        ) from exc
    if not isinstance(manifest, dict) or not isinstance(manifest.get("assets"), dict):
        raise SteamZeroError("E-THEME-MANIFEST", detail=f"manifesto inválido de '{theme_id}'")
    return manifest


def _digest_of(manifest: dict[str, Any], relative: str) -> str | None:
    entry = manifest["assets"].get(relative)
    if isinstance(entry, dict):
        digest = entry.get("digest")
        return digest if isinstance(digest, str) else None
    return None


def materialize_layout(
    manifest: dict[str, Any],
    store: theme_assets.ThemeAssetStore,
    destination: Path,
) -> int:
    """Escreve os XML do tema em ``destination``, preservando a hierarquia.

    A hierarquia importa: ``<include>./_inc/x.xml</include>` é relativo ao
    arquivo que o declara, então achatar os nomes quebraria a resolução.
    """
    fs.ensure_dir(destination)
    written = 0
    for relative in sorted(manifest["assets"]):
        if not relative.endswith(_LAYOUT_SUFFIX):
            continue
        if written >= _MAX_LAYOUT_FILES:
            raise SteamZeroError(
                "E-THEME-UNSAFE",
                detail=f"tema declara mais de {_MAX_LAYOUT_FILES} arquivos de layout",
            )
        digest = _digest_of(manifest, relative)
        if digest is None or not store.has(digest):
            # Blob ausente para um XML é dado faltando, não motivo para abortar:
            # o include correspondente vai aparecer em `missing` com o nome.
            continue
        target = destination / relative
        fs.ensure_dir(target.parent)
        fs.write_atomic(target, store.read(digest))
        written += 1
    return written


def _resolve_assets(
    scene: dict[str, Any],
    manifest: dict[str, Any],
    store: theme_assets.ThemeAssetStore,
    *,
    system_id: str | None,
) -> dict[str, Any]:
    """Troca caminho de tema por caminho de blob, e diz o que não trocou."""
    resolved = 0
    missing: list[str] = []
    pending_template: list[str] = []

    for view in scene.get("views", []):
        for element in view.get("elements", []):
            relative = element.get("asset")
            if relative is None:
                template = element.get("assetTemplate")
                if isinstance(template, dict) and template.get("pattern"):
                    if system_id is None:
                        # Sem sistema em foco o template não tem valor: escolher
                        # um por conta própria daria ao tema a identidade de um
                        # console arbitrário.
                        pending_template.append(str(element.get("id")))
                        continue
                    relative = scene_esde.resolve_asset_template(
                        str(template["pattern"]), system_id
                    )
                else:
                    continue
            digest = _digest_of(manifest, str(relative))
            if digest is None or not store.has(digest):
                missing.append(str(relative))
                continue
            element["source"] = store.blob_path(digest).as_uri()
            resolved += 1

    return {
        "resolved": resolved,
        "missing": sorted(set(missing)),
        "awaitingSystem": sorted(set(pending_template)),
    }


def available_selections_for(
    theme_id: str,
    *,
    themes_root: Path | None = None,
    store: theme_assets.ThemeAssetStore | None = None,
    workspace: Path | None = None,
) -> dict[str, list[str]]:
    """As dimensões que o tema declara, lidas da árvore RESOLVIDA.

    Lê-las só do ``theme.xml`` devolveria uma lista curta e errada: no xmb-menu
    os ``<colorScheme>`` moram em ``colors.xml`` e as proporções em arquivos
    próprios. Oferecer ao usuário uma lista incompleta o faria escolher entre
    opções que não são as do tema — e ficar sem as que carregam a geometria.
    """
    root = themes_root if themes_root is not None else paths.themes_dir()
    assets = store if store is not None else theme_assets.ThemeAssetStore(paths.theme_assets_dir())
    manifest = load_manifest(root, theme_id)
    scratch = workspace if workspace is not None else paths.staging_dir() / f"select-{theme_id}"
    with contextlib.suppress(OSError):
        fs.remove_tree(scratch)
    try:
        materialize_layout(manifest, assets, scratch)
        entry = scratch / "theme.xml"
        if not entry.is_file():
            return {}
        # Sem seleção, todos os blocos são seguidos: é o que torna a lista
        # completa em vez de refletir uma escolha já feita.
        resolved = theme_import_esde_layout.resolve_includes(entry, theme_root=scratch)
        return scene_esde.available_selections(resolved.root)
    finally:
        fs.remove_tree(scratch)


def render_scene(
    theme_id: str,
    *,
    themes_root: Path | None = None,
    store: theme_assets.ThemeAssetStore | None = None,
    system_id: str | None = None,
    selection: scene_esde.Selection | None = None,
    workspace: Path | None = None,
) -> dict[str, Any]:
    """Compila o tema instalado e devolve a cena com os assets já resolvidos."""
    root = themes_root if themes_root is not None else paths.themes_dir()
    assets = store if store is not None else theme_assets.ThemeAssetStore(paths.theme_assets_dir())
    manifest = load_manifest(root, theme_id)

    scratch = workspace if workspace is not None else paths.staging_dir() / f"scene-{theme_id}"
    # Sobra de uma execução interrompida; recriar é o caminho seguro.
    with contextlib.suppress(OSError):
        fs.remove_tree(scratch)
    try:
        materialize_layout(manifest, assets, scratch)
        entry = scratch / "theme.xml"
        if not entry.is_file():
            raise SteamZeroError(
                "E-THEME-MANIFEST", detail=f"tema '{theme_id}' não declara theme.xml"
            )
        includes = theme_import_esde_layout.resolve_includes(
            entry, theme_root=scratch, system_id=system_id, selection=selection
        )
        scene = scene_esde.compile_theme(
            ET.tostring(includes.root, encoding="unicode"),
            theme_id=theme_id,
            name=manifest.get("name"),
            author=manifest.get("author"),
            license_id=manifest.get("license"),
            selection=selection,
        )
    finally:
        fs.remove_tree(scratch)

    assets_report = _resolve_assets(scene, manifest, assets, system_id=system_id)
    fidelity = scene_esde.fidelity_report(scene)
    return {
        "themeId": theme_id,
        "version": manifest.get("version"),
        "systemId": system_id,
        "scene": scene,
        "fidelity": fidelity,
        "assets": assets_report,
        "includes": {
            "included": len(includes.included),
            "missing": sorted(includes.missing),
            "unresolved": sorted(includes.unresolved),
            "refused": sorted(includes.refused),
        },
    }
