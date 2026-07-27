# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Editor visual de temas: sessão editável, preview, save e export."""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from steamzero.core import fs, ids, paths
from steamzero.core.errors import SteamZeroError
from steamzero.domain.themes import (
    ASSET_SLOTS_ALLOWED,
    THEME_DEFAULT_ID,
    ResolvedTheme,
    ThemeAsset,
    ThemeColorTokens,
    ThemeGeometryTokens,
    ThemeManifest,
    ThemeMotionTokens,
    ThemeTypographyTokens,
)

_TOKEN_CATEGORIES = frozenset({"color", "geometry", "typography", "motion"})
_ASSET_MAX_SIZE = 16 * 1024 * 1024


@dataclass
class EditorSession:
    session_id: str
    theme_dir: Path | None
    manifest: dict[str, object]
    tokens: dict[str, dict[str, object]]
    assets: dict[str, str]
    dirty: bool = False


def _default_session_id() -> str:
    return f"edit-{ids.new_ulid().lower()}"


def _make_resolved(
    manifest: dict[str, object],
    tokens: dict[str, dict[str, object]],
    assets: dict[str, str],
    high_contrast: bool = False,
    reduced_motion: bool = False,
) -> ResolvedTheme:
    color_data: dict[str, Any] = tokens.get("color", {})
    geometry_data: dict[str, Any] = tokens.get("geometry", {})
    typo_data: dict[str, Any] = tokens.get("typography", {})
    motion_data: dict[str, Any] = tokens.get("motion", {})

    color = ThemeColorTokens.from_dict(color_data) if color_data else ThemeColorTokens()
    geo = ThemeGeometryTokens.from_dict(geometry_data) if geometry_data else ThemeGeometryTokens()
    typo = ThemeTypographyTokens.from_dict(typo_data) if typo_data else ThemeTypographyTokens()
    motion = ThemeMotionTokens.from_dict(motion_data) if motion_data else ThemeMotionTokens()
    resolved_assets = {
        slot: ThemeAsset(slot=slot, path=path)
        for slot, path in assets.items()
        if slot in ASSET_SLOTS_ALLOWED
    }

    mid = str(manifest.get("id", THEME_DEFAULT_ID))
    return ResolvedTheme(
        id=mid,
        name=str(manifest.get("name", mid)),
        version=str(manifest.get("version", "1.0.0")),
        author=str(manifest.get("author", "")),
        license=str(manifest.get("license", "")),
        description=str(manifest.get("description", "")),
        color=color,
        geometry=geo,
        typography=typo,
        motion=motion,
        assets=resolved_assets,
    ).apply_accessibility(high_contrast, reduced_motion)


class ThemeEditorManager:
    def __init__(self) -> None:
        self._sessions: dict[str, EditorSession] = {}

    def load(self, theme_id: str) -> dict[str, object]:
        import importlib.resources as _res

        theme_dir = paths.themes_dir() / theme_id
        manifest_path = theme_dir / "theme.json"
        read_only = False
        if not manifest_path.is_file():
            try:
                ref = _res.files("steamzero.themes").joinpath(theme_id, "theme.json")
                with _res.as_file(ref) as builtin_path:
                    raw = json.loads(builtin_path.read_bytes())
                theme_dir = builtin_path.parent
                read_only = True
            except (FileNotFoundError, ModuleNotFoundError, TypeError):
                raise SteamZeroError(
                    "E-THEME-NOT-FOUND",
                    detail=f"tema '{theme_id}' não encontrado",
                ) from None
        else:
            raw = json.loads(manifest_path.read_bytes())
        manifest = ThemeManifest.from_dict(raw)
        tokens: dict[str, dict[str, object]] = {}
        raw_tokens = dict(manifest.tokens or {})
        for cat in _TOKEN_CATEGORIES:
            cat_data = raw_tokens.get(cat, {})
            if isinstance(cat_data, dict):
                tokens[cat] = dict(cat_data)
            else:
                tokens[cat] = {}
        assets = dict(manifest.assets or {})

        sid = _default_session_id()
        self._sessions[sid] = EditorSession(
            session_id=sid,
            theme_dir=theme_dir,
            manifest=manifest.to_dict(),
            tokens=tokens,
            assets=assets,
            dirty=False,
        )
        return {
            "sessionId": sid,
            "readOnly": read_only,
            "manifest": manifest.to_dict(),
            "preview": _make_resolved(manifest.to_dict(), tokens, assets).to_theme_qml_object(),
        }

    def create(
        self,
        name: str,
        extends: str = THEME_DEFAULT_ID,
    ) -> dict[str, object]:
        sid = _default_session_id()
        new_id = f"org.steamzero.{ids.new_ulid().casefold()[:8]}"
        manifest = ThemeManifest(
            id=new_id,
            name=name,
            version="1.0.0",
            author="Usuário",
            license="MIT",
            extends=extends,
        )
        self._sessions[sid] = EditorSession(
            session_id=sid,
            theme_dir=None,
            manifest=manifest.to_dict(),
            tokens={},
            assets={},
            dirty=True,
        )
        return {
            "sessionId": sid,
            "manifest": manifest.to_dict(),
            "preview": _make_resolved(manifest.to_dict(), {}, {}).to_theme_qml_object(),
        }

    def set_tokens(
        self,
        session_id: str,
        category: str,
        values: dict[str, object],
    ) -> dict[str, object]:
        session = self._get_session(session_id)
        if category not in _TOKEN_CATEGORIES:
            raise SteamZeroError("E-API-SCHEMA", detail=f"categoria inválida: {category}")
        session.tokens[category] = dict(values)
        session.dirty = True
        return {"preview": self._preview(session)}

    def set_metadata(
        self, session_id: str, meta_field: str, value: object
    ) -> dict[str, object]:
        session = self._get_session(session_id)
        allowed = {"name", "author", "license", "description", "homepage", "version", "extends"}
        if meta_field not in allowed:
            raise SteamZeroError("E-API-SCHEMA", detail=f"campo inválido: {meta_field}")
        if value is not None and not isinstance(value, str):
            raise SteamZeroError("E-API-SCHEMA", detail=f"valor de {meta_field} precisa ser string")
        session.manifest[meta_field] = value
        session.dirty = True
        return {"manifest": dict(session.manifest)}

    def set_asset(
        self, session_id: str, slot: str, data: bytes, filename: str
    ) -> dict[str, object]:
        session = self._get_session(session_id)
        if slot not in ASSET_SLOTS_ALLOWED:
            raise SteamZeroError("E-API-SCHEMA", detail=f"slot inválido: {slot}")
        if len(data) > _ASSET_MAX_SIZE:
            raise SteamZeroError("E-THEME-LIMIT", detail="asset excede 16 MiB")
        ext = Path(filename).suffix.lower()
        if ext not in {".png", ".jpg", ".jpeg", ".webp", ".svg"}:
            raise SteamZeroError("E-API-SCHEMA", detail=f"extensão não permitida: {ext}")
        session.dirty = True
        return {"asset": {"slot": slot, "filename": filename, "size": len(data)}}

    def preview(
        self,
        session_id: str,
        *,
        high_contrast: bool = False,
        reduced_motion: bool = False,
    ) -> dict[str, object]:
        session = self._get_session(session_id)
        return {"preview": self._preview(session, high_contrast, reduced_motion)}

    def save(self, session_id: str, *, overwrite: bool = False) -> dict[str, str]:
        session = self._get_session(session_id)
        manifest = ThemeManifest.from_dict(session.manifest)
        theme_id = manifest.id
        target = paths.themes_dir() / theme_id

        tokens = {}
        for cat in _TOKEN_CATEGORIES:
            cat_data = session.tokens.get(cat)
            if cat_data:
                tokens[cat] = dict(cat_data)
        manifest_dict = manifest.to_dict()
        if tokens:
            manifest_dict["tokens"] = tokens
        else:
            manifest_dict.pop("tokens", None)
        if session.assets:
            manifest_dict["assets"] = dict(session.assets)
        else:
            manifest_dict.pop("assets", None)

        validation = _validate_save(manifest_dict)
        if validation:
            raise SteamZeroError("E-THEME-MANIFEST", detail=validation)

        if target.exists() and not overwrite:
            raise SteamZeroError(
                "E-THEME-DOWNLOAD-FAILED",
                detail=f"tema '{theme_id}' já existe. Use overwrite=true para substituir.",
            )

        pending_assets: list[tuple[str, bytes]] = []
        if session.theme_dir and session.theme_dir.is_dir():
            assets_src = session.theme_dir / "assets"
            if assets_src.is_dir():
                for entry in assets_src.iterdir():
                    if entry.is_file():
                        pending_assets.append((entry.name, entry.read_bytes()))

        if target.exists():
            fs.remove_tree(target)

        fs.ensure_dir(target)
        fs.write_atomic(target / "theme.json", json.dumps(manifest_dict, indent=2).encode())

        if pending_assets:
            assets_dst = target / "assets"
            fs.ensure_dir(assets_dst)
            for name, data in pending_assets:
                fs.write_atomic(assets_dst / name, data)

        session.theme_dir = target
        session.dirty = False
        return {"themeId": theme_id, "path": str(target)}

    def export_zip(self, session_id: str) -> bytes:
        session = self._get_session(session_id)
        manifest = ThemeManifest.from_dict(session.manifest)
        theme_id = manifest.id
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            tokens = {}
            for cat in _TOKEN_CATEGORIES:
                cat_data = session.tokens.get(cat)
                if cat_data:
                    tokens[cat] = dict(cat_data)
            manifest_dict = manifest.to_dict()
            if tokens:
                manifest_dict["tokens"] = tokens
            else:
                manifest_dict.pop("tokens", None)
            if session.assets:
                manifest_dict["assets"] = dict(session.assets)
            else:
                manifest_dict.pop("assets", None)
            zf.writestr(f"{theme_id}/theme.json", json.dumps(manifest_dict, indent=2))
            if session.theme_dir and session.theme_dir.is_dir():
                assets_dir = session.theme_dir / "assets"
                if assets_dir.is_dir():
                    for asset_path in assets_dir.rglob("*"):
                        if asset_path.is_file():
                            rel = asset_path.relative_to(session.theme_dir)
                            zf.write(asset_path, str(rel))
        return buf.getvalue()

    def cancel(self, session_id: str) -> dict[str, str]:
        sid_lower = session_id.lower()
        for key in list(self._sessions):
            if key.lower() == sid_lower:
                del self._sessions[key]
                return {"status": "cancelled", "sessionId": session_id}
        raise SteamZeroError("E-API-SCHEMA", detail=f"sessão não encontrada: {session_id}")

    def _get_session(self, session_id: str) -> EditorSession:
        sid_lower = session_id.lower()
        for key, session in self._sessions.items():
            if key.lower() == sid_lower:
                return session
        raise SteamZeroError("E-API-SCHEMA", detail=f"sessão não encontrada: {session_id}")

    def _preview(
        self,
        session: EditorSession,
        high_contrast: bool = False,
        reduced_motion: bool = False,
    ) -> dict[str, object]:
        return _make_resolved(
            session.manifest,
            session.tokens,
            session.assets,
            high_contrast=high_contrast,
            reduced_motion=reduced_motion,
        ).to_theme_qml_object()


def _validate_save(manifest_dict: dict[str, object]) -> str | None:
    for req in ("id", "name", "version", "author", "license"):
        if not manifest_dict.get(req):
            return f"campo obrigatório ausente: {req}"
    mid = str(manifest_dict["id"])
    if not mid.replace(".", "").replace("-", "").isalnum():
        return f"ID inválido: {mid}"
    return None
