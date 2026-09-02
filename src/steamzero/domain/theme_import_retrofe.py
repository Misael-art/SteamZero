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
from pathlib import Path
from typing import Any

from steamzero.core import fs, paths
from steamzero.core.errors import SteamZeroError
from steamzero.domain.scene_retrofe import compile_layout, fidelity_report

MAX_LAYOUT_BYTES = 8 * 1024 * 1024
MAX_LAYOUTS = 64
SCENE_ID = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$")


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


def inspect(source: str) -> dict[str, Any]:
    """Compila os layouts e devolve a prévia completa, sem escrever."""
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
    selected = _select_layout(source, layout)
    scene = compile_layout(
        _read_layout(selected),
        theme_id=scene_id,
        name=name.strip(),
        author=author.strip(),
        license_id=license_id.strip(),
        view_id=selected.layout_id,
    )
    target = paths.scenes_dir() / f"{scene_id}.json"
    if target.exists() and not overwrite:
        raise SteamZeroError(
            "E-THEME-DOWNLOAD-FAILED",
            detail=f"cena '{scene_id}' já existe; confirme overwrite para substituir",
        )
    if target.is_symlink():
        raise SteamZeroError("E-THEME-UNSAFE", detail="destino de cena é symlink")
    fs.write_atomic_text(target, json.dumps(scene, ensure_ascii=False, indent=2) + "\n")
    return {
        "sceneId": scene_id,
        "path": str(target),
        "layout": selected.relative_path,
        "family": "retrofe",
        "report": fidelity_report(scene),
        "degraded": list(scene.get("degraded", [])),
        "activated": False,
    }
