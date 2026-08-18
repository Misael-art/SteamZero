# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Editor visual de temas: sessão editável, preview, save e export."""

from __future__ import annotations

import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from steamzero.core import fs, ids, paths
from steamzero.core.errors import SteamZeroError
from steamzero.domain.dynamic_palette import extract_dynamic_palette
from steamzero.domain.glass_panels import resolve_glass_panels
from steamzero.domain.scene_layout import LayoutBounds, resolve_scene_layouts
from steamzero.domain.themes import (
    ASSET_SLOTS_ALLOWED,
    THEME_DEFAULT_ID,
    ResolvedTheme,
    ThemeAsset,
    ThemeColorTokens,
    ThemeGeometryTokens,
    ThemeManifest,
    ThemeMotionTokens,
    ThemeResolver,
    ThemeTypographyTokens,
)

_TOKEN_CATEGORIES = frozenset({"color", "geometry", "typography", "motion"})
_ASSET_MAX_SIZE = 16 * 1024 * 1024
# Espelha "pattern" de theme-manifest-v1.schema.json (propriedade "id").
THEME_ID_RE = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)+$")


_ASSET_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".svg"}
_THEME_PACKAGE = "steamzero.themes"

_LAYOUT_PREVIEW_READ_MODEL: dict[str, object] = {
    "preview": {
        "items": [
            {"title": "Axiom Verge"},
            {"title": "Celeste"},
            {"title": "Hades"},
            {"title": "Tunic"},
        ]
    }
}
_LAYOUT_PREVIEW_BOUNDS = LayoutBounds(width=640, height=96)


@dataclass
class EditorSession:
    session_id: str
    theme_dir: Path | None
    manifest: dict[str, object]
    tokens: dict[str, dict[str, object]]
    assets: dict[str, str]
    dirty: bool = False
    # Bytes recebidos por ``set_asset`` que ainda não foram gravados em disco.
    # slot -> (nome de arquivo derivado do slot, conteúdo)
    pending_assets: dict[str, tuple[str, bytes]] = field(default_factory=dict)


def _default_session_id() -> str:
    return f"edit-{ids.new_ulid().lower()}"


def _read_manifest_file(path: Path) -> ThemeManifest | None:
    """Lê um theme.json; falha de parse/IO devolve None (preview degrada)."""
    try:
        raw = json.loads(path.read_bytes())
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    try:
        return ThemeManifest.from_dict(raw)
    except (TypeError, ValueError, KeyError):
        return None


def _load_manifests_for_resolution() -> dict[str, ThemeManifest]:
    """Coleta manifests builtin + usuário para resolver a cadeia ``extends``.

    Somente leitura: builtins empacotados e temas em ``themes_dir()``. Não grava
    nem altera arquivos (builtins permanecem imutáveis).
    """
    import importlib.resources as _res

    manifests: dict[str, ThemeManifest] = {}

    try:
        root = _res.files(_THEME_PACKAGE)
        for entry in root.iterdir():
            try:
                if not entry.is_dir():
                    continue
                theme_json = entry.joinpath("theme.json")
                if not theme_json.is_file():
                    continue
                with _res.as_file(theme_json) as path:
                    loaded = _read_manifest_file(path)
                if loaded is not None:
                    manifests[loaded.id] = loaded
            except (OSError, TypeError, AttributeError, ValueError):
                continue
    except (ModuleNotFoundError, FileNotFoundError, TypeError, AttributeError):
        pass

    themes_dir = paths.themes_dir()
    if themes_dir.is_dir():
        try:
            entries = list(themes_dir.iterdir())
        except OSError:
            entries = []
        for entry in entries:
            if not entry.is_dir():
                continue
            loaded = _read_manifest_file(entry / "theme.json")
            if loaded is not None:
                # Usuário sobrescreve homônimo builtin apenas no mapa de resolução
                # da sessão; o pacote builtin no disco/recursos não é tocado.
                manifests[loaded.id] = loaded
    return manifests


def _make_resolved_leaf(
    manifest: dict[str, object],
    tokens: dict[str, dict[str, object]],
    assets: dict[str, str],
    high_contrast: bool = False,
    reduced_motion: bool = False,
) -> ResolvedTheme:
    """Resolve só os tokens da sessão (sem herança) — fallback seguro."""
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


def _make_resolved(
    manifest: dict[str, object],
    tokens: dict[str, dict[str, object]],
    assets: dict[str, str],
    high_contrast: bool = False,
    reduced_motion: bool = False,
) -> ResolvedTheme:
    """Resolve o preview da sessão percorrendo a cadeia ``extends``.

    Usa ``ThemeResolver`` (profundidade finita, detecção de ciclo, base ausente).
    Em qualquer falha de cadeia ou de montagem do rascunho, degrada para a
    resolução só com tokens da sessão — o editor nunca trava o preview.
    """
    draft_tokens = {cat: dict(vals) for cat, vals in tokens.items() if vals}
    draft_assets = {slot: path for slot, path in assets.items() if slot in ASSET_SLOTS_ALLOWED}
    try:
        draft_data = dict(manifest)
        if draft_tokens:
            draft_data["tokens"] = draft_tokens
        else:
            draft_data.pop("tokens", None)
        if draft_assets:
            draft_data["assets"] = draft_assets
        else:
            draft_data.pop("assets", None)
        draft = ThemeManifest.from_dict(draft_data)
        available = _load_manifests_for_resolution()
        # Rascunho da sessão vence o que estiver em disco/builtin para o mesmo id.
        available[draft.id] = draft
        return ThemeResolver(available).resolve(
            draft.id,
            high_contrast=high_contrast,
            reduced_motion=reduced_motion,
        )
    except (ValueError, TypeError, KeyError, AttributeError):
        return _make_resolved_leaf(
            manifest,
            tokens,
            assets,
            high_contrast=high_contrast,
            reduced_motion=reduced_motion,
        )


def _preview_source_bytes(resolved: ResolvedTheme) -> bytes | None:
    if resolved.dynamic_palette is None:
        return None
    slot = resolved.dynamic_palette.source_slot
    asset = resolved.assets.get(slot)
    if asset is None:
        return None
    try:
        import importlib.resources as resources

        ref = resources.files("steamzero.themes").joinpath(resolved.id, asset.path)
        with resources.as_file(ref) as path:
            return path.read_bytes()
    except (OSError, FileNotFoundError, ModuleNotFoundError):
        return None


def _to_preview_object(resolved: ResolvedTheme) -> dict[str, object]:
    """Entrega ao editor um preview já materializado, nunca bindings vivos."""
    preview = resolved.to_theme_qml_object()
    if resolved.scene_layouts is not None:
        preview["sceneLayoutPreview"] = resolve_scene_layouts(
            resolved.scene_layouts,
            _LAYOUT_PREVIEW_READ_MODEL,
            bounds=_LAYOUT_PREVIEW_BOUNDS,
        ).to_qml_object()
    extracted = None
    if resolved.dynamic_palette is not None:
        extracted = extract_dynamic_palette(
            resolved.dynamic_palette,
            source=_preview_source_bytes(resolved),
        )
        preview["dynamicPalette"] = extracted.to_qml_object()
    if resolved.glass is not None:
        palette = extracted.swatches if extracted is not None else {}
        preview["glassPreview"] = resolve_glass_panels(
            resolved.glass,
            palette=palette,
            high_contrast=resolved.high_contrast,
        ).to_qml_object()
    return preview


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
            "preview": _to_preview_object(_make_resolved(manifest.to_dict(), tokens, assets)),
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
            "preview": _to_preview_object(_make_resolved(manifest.to_dict(), {}, {})),
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

    def set_metadata(self, session_id: str, meta_field: str, value: object) -> dict[str, object]:
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
        if not data:
            raise SteamZeroError("E-API-SCHEMA", detail="asset vazio")
        if len(data) > _ASSET_MAX_SIZE:
            raise SteamZeroError("E-THEME-LIMIT", detail="asset excede 16 MiB")
        ext = Path(filename).suffix.lower()
        if ext not in _ASSET_EXTENSIONS:
            raise SteamZeroError("E-API-SCHEMA", detail=f"extensão não permitida: {ext}")
        # O nome gravado é derivado do slot, nunca do nome enviado: o filename
        # externo só contribui com a extensão, já validada acima.
        stored_name = f"{slot}{ext}"
        session.pending_assets[slot] = (stored_name, data)
        session.assets[slot] = f"assets/{stored_name}"
        session.dirty = True
        return {"asset": {"slot": slot, "filename": stored_name, "size": len(data)}}

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

        # O id já foi validado por padrão ancorado, mas o alvo é um caminho que
        # será criado e possivelmente REMOVIDO: reconfirme o confinamento antes
        # de qualquer efeito em disco.
        _assert_within_themes_dir(target)

        if target.exists() and not overwrite:
            raise SteamZeroError(
                "E-THEME-DOWNLOAD-FAILED",
                detail=f"tema '{theme_id}' já existe. Use overwrite=true para substituir.",
            )

        # Assets já em disco no tema de origem, preservados na regravação.
        pending_assets: list[tuple[str, bytes]] = []
        if session.theme_dir and session.theme_dir.is_dir():
            assets_src = session.theme_dir / "assets"
            if assets_src.is_dir():
                for entry in assets_src.iterdir():
                    if entry.is_file():
                        pending_assets.append((entry.name, entry.read_bytes()))
        # Assets enviados nesta sessão vencem os homônimos já existentes.
        uploaded = {name: data for name, data in session.pending_assets.values()}
        pending_assets = [item for item in pending_assets if item[0] not in uploaded]
        pending_assets.extend(uploaded.items())

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
        session.pending_assets.clear()
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
            # Tudo precisa ficar sob {theme_id}/, porque é esse o diretório que
            # ``ThemeInstaller._find_theme_dir`` elege ao reinstalar. Gravar os
            # assets na raiz do zip faz o ciclo export→install perdê-los.
            written: set[str] = set()
            for stored_name, data in session.pending_assets.values():
                arcname = f"{theme_id}/assets/{stored_name}"
                zf.writestr(arcname, data)
                written.add(arcname)
            if session.theme_dir and session.theme_dir.is_dir():
                assets_dir = session.theme_dir / "assets"
                if assets_dir.is_dir():
                    for asset_path in sorted(assets_dir.rglob("*")):
                        if not asset_path.is_file():
                            continue
                        rel = asset_path.relative_to(session.theme_dir)
                        arcname = f"{theme_id}/{rel.as_posix()}"
                        if arcname in written:
                            continue
                        zf.write(asset_path, arcname)
                        written.add(arcname)
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
        return _to_preview_object(
            _make_resolved(
                session.manifest,
                session.tokens,
                session.assets,
                high_contrast=high_contrast,
                reduced_motion=reduced_motion,
            )
        )


def _validate_save(manifest_dict: dict[str, object]) -> str | None:
    for req in ("id", "name", "version", "author", "license"):
        if not manifest_dict.get(req):
            return f"campo obrigatório ausente: {req}"
    mid = str(manifest_dict["id"])
    # Mesmo padrão ancorado de ``theme-manifest-v1.schema.json``. Não troque por
    # heurística: ``str.isalnum()`` é Unicode-aware e aceitaria ids não-ASCII
    # que depois viram caminho de filesystem e alvo de remoção.
    if not THEME_ID_RE.fullmatch(mid):
        return f"ID inválido: {mid}"
    return None


def _assert_within_themes_dir(target: Path) -> None:
    """Garante que o alvo de escrita/remoção não escapa de ``themes_dir()``."""
    root = paths.themes_dir()
    try:
        resolved_root = root.resolve()
        resolved = target.resolve()
    except OSError as exc:  # pragma: no cover - filesystem degradado
        raise SteamZeroError("E-THEME-UNSAFE", detail="alvo inacessível") from exc
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise SteamZeroError(
            "E-THEME-UNSAFE",
            detail="caminho do tema escapa do diretório de temas",
        )
