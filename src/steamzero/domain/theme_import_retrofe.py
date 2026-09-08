# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Importação segura de layouts RetroFE para o IR de cena.

RetroFE não é um ``theme.json`` SteamZero: sua unidade de composição é um
layout XML, enquanto o contrato nativo de tokens é outra capacidade. O
importador, portanto, publica o resultado no IR de cena já usado pelo
renderizador comum. Isso evita criar um segundo frontend e deixa a fidelidade
visível antes de qualquer gravação.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from steamzero.core import fs, paths
from steamzero.core.errors import SteamZeroError
from steamzero.domain import theme_assets
from steamzero.domain.scene_retrofe import compile_layout, fidelity_report

MAX_LAYOUT_BYTES = 8 * 1024 * 1024
MAX_LAYOUTS = 64
SCENE_ID = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$")
LICENSE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+.-]{0,63}$")


@dataclass(frozen=True)
class LayoutSource:
    """Um layout local elegível para inspeção/aplicação."""

    relative_path: str
    path: Path
    layout_id: str

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.layout_id,
            "path": self.relative_path,
            "name": self.path.stem,
        }


def _reject_source_symlink(path: Path, source: str) -> None:
    if path.is_symlink():
        raise SteamZeroError("E-THEME-MANIFEST", detail=f"origem é symlink: {source}")


def _source_root(source: str) -> tuple[Path, Path]:
    if not source or "\x00" in source:
        raise SteamZeroError("E-API-SCHEMA", detail="origem RetroFE inválida")
    path = Path(source).expanduser()
    _reject_source_symlink(path, source)
    if path.is_file():
        return path.parent, path
    if path.is_dir():
        return path, path
    raise SteamZeroError("E-THEME-NOT-FOUND", detail=f"origem não encontrada: {source}")


def _safe_layout_id(relative_path: str) -> str:
    stem = Path(relative_path).with_suffix("").as_posix().casefold()
    value = re.sub(r"[^a-z0-9]+", "-", stem).strip("-")
    return value or "layout"


def discover_layouts(source: str) -> list[LayoutSource]:
    """Descobre XMLs de layout sem seguir links nem atravessar limites."""
    root, target = _source_root(source)
    if target.is_file():
        if target.suffix.casefold() != ".xml":
            raise SteamZeroError("E-THEME-MANIFEST", detail="a origem precisa ser um layout .xml")
        candidates = [target]
    else:
        candidates = []
        for entry in sorted(target.rglob("*.xml"), key=lambda item: item.as_posix().casefold()):
            if entry.is_symlink():
                raise SteamZeroError("E-THEME-UNSAFE", detail=f"symlink no tema: {entry}")
            if entry.is_file():
                candidates.append(entry)
                if len(candidates) > MAX_LAYOUTS:
                    raise SteamZeroError(
                        "E-THEME-LIMIT", detail=f"número de layouts excedido: {MAX_LAYOUTS}"
                    )
    if not candidates:
        raise SteamZeroError("E-THEME-NOT-FOUND", detail="nenhum layout XML encontrado")

    seen: set[str] = set()
    layouts: list[LayoutSource] = []
    for path in candidates:
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError as exc:
            raise SteamZeroError("E-THEME-UNSAFE", detail=f"layout fora da origem: {path}") from exc
        layout_id = _safe_layout_id(relative)
        if layout_id in seen:
            suffix = 2
            while f"{layout_id}-{suffix}" in seen:
                suffix += 1
            layout_id = f"{layout_id}-{suffix}"
        seen.add(layout_id)
        layouts.append(LayoutSource(relative, path, layout_id))
    return layouts


def _read_layout(layout: LayoutSource) -> str:
    try:
        size = layout.path.stat().st_size
        if size > MAX_LAYOUT_BYTES:
            raise SteamZeroError(
                "E-THEME-LIMIT",
                detail=f"layout {layout.relative_path} excede {MAX_LAYOUT_BYTES} bytes",
            )
        raw = layout.path.read_bytes()
    except SteamZeroError:
        raise
    except OSError as exc:
        raise SteamZeroError("E-THEME-MANIFEST", detail=f"layout ilegível: {exc}") from exc
    if len(raw) > MAX_LAYOUT_BYTES:
        raise SteamZeroError("E-THEME-LIMIT", detail=f"layout {layout.relative_path} excede o teto")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SteamZeroError(
            "E-THEME-MANIFEST", detail=f"layout {layout.relative_path} não é UTF-8"
        ) from exc


def _asset_references(scene: dict[str, Any]) -> list[str]:
    """Collect package-relative asset references from a compiled scene."""
    found: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            asset = value.get("asset")
            if isinstance(asset, str):
                found.add(asset)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(scene)
    return sorted(found)


def _asset_path(root: Path, logical_path: str) -> Path:
    """Resolve one asset without following a source-tree symlink."""
    prefix = "assets/"
    if not logical_path.startswith(prefix):
        raise SteamZeroError("E-THEME-UNSAFE", detail=f"asset fora do pacote: {logical_path!r}")
    relative = PurePosixPath(logical_path)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise SteamZeroError(
            "E-THEME-UNSAFE", detail=f"caminho de asset inválido: {logical_path!r}"
        )
    candidate = root.joinpath(*relative.parts)
    if any(part.is_symlink() for part in (root, *candidate.parents, candidate)):
        raise SteamZeroError("E-THEME-UNSAFE", detail=f"asset é symlink: {logical_path!r}")
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise SteamZeroError(
            "E-THEME-UNSAFE", detail=f"asset fora da origem: {logical_path!r}"
        ) from exc
    if not candidate.is_file():
        raise SteamZeroError("E-THEME-NOT-FOUND", detail=f"asset ausente: {logical_path!r}")
    return candidate


def _asset_report(root: Path, scene: dict[str, Any]) -> dict[str, Any]:
    """Inspect asset custody without writing to the managed store."""
    references = _asset_references(scene)
    available: list[str] = []
    missing: list[str] = []
    refused: list[str] = []
    for logical_path in references:
        try:
            _asset_path(root, logical_path)
        except SteamZeroError as exc:
            if exc.code == "E-THEME-NOT-FOUND":
                missing.append(logical_path)
            else:
                refused.append(logical_path)
            continue
        available.append(logical_path)
    return {
        "referenced": references,
        "available": available,
        "missing": missing,
        "refused": refused,
        "ready": not missing and not refused,
    }


def inspect(source: str) -> dict[str, Any]:
    """Compila os layouts e devolve a prévia completa, sem escrever."""
    root, _target = _source_root(source)
    layouts: list[dict[str, Any]] = []
    for layout in discover_layouts(source):
        scene = compile_layout(
            _read_layout(layout), theme_id=layout.layout_id, name=layout.path.stem
        )
        report = fidelity_report(scene)
        layouts.append(
            {
                **layout.to_dict(),
                "report": report,
                "assets": _asset_report(root, scene),
                "degraded": list(scene.get("degraded", [])),
                "scene": scene,
            }
        )
    return {
        "source": str(Path(source).expanduser().absolute()),
        "family": "retrofe",
        "layouts": layouts,
        "layoutCount": len(layouts),
        "totalElements": sum(int(item["report"]["elements"]) for item in layouts),
        "totalDegraded": sum(int(item["report"]["degraded"]) for item in layouts),
        "assets": {
            "referenced": sorted(
                {asset for item in layouts for asset in item["assets"]["referenced"]}
            ),
            "missing": sorted({asset for item in layouts for asset in item["assets"]["missing"]}),
            "refused": sorted({asset for item in layouts for asset in item["assets"]["refused"]}),
        },
    }


def _select_layout(source: str, requested: str) -> LayoutSource:
    layouts = discover_layouts(source)
    selected = next(
        (
            layout
            for layout in layouts
            if requested
            in {layout.layout_id, layout.relative_path, Path(layout.relative_path).stem}
        ),
        None,
    )
    if selected is None:
        raise SteamZeroError(
            "E-THEME-NOT-FOUND",
            detail=f"layout RetroFE não encontrado: {requested}",
        )
    return selected


def apply(
    source: str,
    layout: str,
    *,
    scene_id: str,
    name: str,
    author: str,
    license_id: str,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Publica um IR validado no diretório gerenciado de cenas.

    Não ativa o resultado. A escrita é atômica e a substituição exige
    ``overwrite=true`` explícito; o shell decide quando uma cena pode virar a
    aparência corrente.
    """
    if not SCENE_ID.fullmatch(scene_id):
        raise SteamZeroError("E-THEME-MANIFEST", detail=f"id de cena inválido: {scene_id!r}")
    if not name.strip() or not author.strip() or not license_id.strip():
        raise SteamZeroError("E-THEME-MANIFEST", detail="nome, autor e licença são obrigatórios")
    if not LICENSE_ID.fullmatch(license_id.strip()):
        raise SteamZeroError("E-THEME-MANIFEST", detail=f"licença inválida: {license_id!r}")
    root, _target = _source_root(source)
    selected = _select_layout(source, layout)
    scene = compile_layout(
        _read_layout(selected),
        theme_id=scene_id,
        name=name.strip(),
        author=author.strip(),
        license_id=license_id.strip(),
        view_id=selected.layout_id,
    )
    asset_report = _asset_report(root, scene)
    if not asset_report["ready"]:
        missing = asset_report["missing"] + asset_report["refused"]
        raise SteamZeroError(
            "E-CONTENT-INCOMPLETE",
            detail=f"assets RetroFE indisponíveis ou recusados: {', '.join(missing[:8])}",
        )
    target = paths.scenes_dir() / f"{scene_id}.json"
    if target.exists() and not overwrite:
        raise SteamZeroError(
            "E-THEME-DOWNLOAD-FAILED",
            detail=f"cena '{scene_id}' já existe; confirme overwrite para substituir",
        )
    if target.is_symlink():
        raise SteamZeroError("E-THEME-UNSAFE", detail="destino de cena é symlink")
    asset_manifest = paths.scenes_dir() / f"{scene_id}.assets.json"
    if asset_manifest.is_symlink():
        raise SteamZeroError("E-THEME-UNSAFE", detail="manifesto de assets é symlink")
    store = theme_assets.ThemeAssetStore(paths.theme_assets_dir())
    stored_assets = {}
    for logical_path in asset_report["available"]:
        stored = store.put(logical_path, _asset_path(root, logical_path).read_bytes())
        stored_assets[logical_path] = stored.to_dict()
    fs.write_atomic_text(target, json.dumps(scene, ensure_ascii=False, indent=2) + "\n")
    fs.write_atomic_text(
        asset_manifest,
        json.dumps(
            {
                "schemaVersion": 1,
                "sceneId": scene_id,
                "origin": {
                    "family": "retrofe",
                    "author": author.strip(),
                    "license": license_id.strip(),
                },
                "assets": stored_assets,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )
    return {
        "sceneId": scene_id,
        "path": str(target),
        "layout": selected.relative_path,
        "family": "retrofe",
        "report": fidelity_report(scene),
        "degraded": list(scene.get("degraded", [])),
        "assets": {
            "count": len(stored_assets),
            "manifestPath": str(asset_manifest),
            "files": stored_assets,
        },
        "activated": False,
    }
