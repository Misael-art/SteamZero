# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Editor visual de temas: sessão editável, preview, save e export."""

from __future__ import annotations

import io
import json
import re
import zipfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from steamzero.core import fs, ids, paths
from steamzero.core.errors import SteamZeroError
from steamzero.domain.dynamic_palette import extract_dynamic_palette
from steamzero.domain.glass_panels import resolve_glass_panels
from steamzero.domain.media_recipes import (
    MEDIA_RECIPE_SCHEMA_VERSION,
    MediaRole,
    media_recipes_to_dict,
    parse_media_recipes,
)
from steamzero.domain.scene_containers import ContainerBounds, resolve_scene_containers
from steamzero.domain.scene_layout import LayoutBounds, LayoutRecipeBook, resolve_scene_layouts
from steamzero.domain.scene_motion import MotionBook, motion_editor_schema, resolve_scene_motion
from steamzero.domain.scene_surfaces import resolve_scene_surfaces
from steamzero.domain.studio_graph import build_studio_graph
from steamzero.domain.theme_effects import (
    EFFECT_STACK_SCHEMA_VERSION,
    EffectType,
    effect_defaults,
    effect_editor_schema,
    effect_stacks_to_dict,
    parse_effect_stacks,
)
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
            {"title": "Axiom Verge", "state": "Baixando"},
            {"title": "Celeste", "state": ""},
            {"title": "Hades", "state": "Na fila"},
            {"title": "Tunic", "state": ""},
        ]
    }
}
_LAYOUT_PREVIEW_BOUNDS = LayoutBounds(width=640, height=96)
# O preview mostra a interface ociosa para tornar a transparência declarada
# legível; o estado real vem do shell, nunca do pacote.
_MOTION_PREVIEW_INTERACTION = "idle"
_CONTAINER_PREVIEW_BOUNDS = ContainerBounds(width=1280, height=800)
_SURFACE_PREVIEW_READ_MODEL: dict[str, object] = {
    "library": {
        "items": [{"title": "Celeste"}],
        "recent": [{"title": "Celeste"}],
    },
    "saves": {
        "slots": [
            {
                "label": "Auto",
                "timestamp": "2026-08-17T12:00:00Z",
                "playtime": "1h 12m",
                "compatible": True,
                "hasThumbnail": True,
            },
            {
                "label": "Slot 2",
                "timestamp": "",
                "playtime": "",
                "compatible": False,
                "hasThumbnail": False,
            },
        ]
    },
    "osd": {"volume": 0.4, "muted": False, "paused": False},
    "progress": {"download": {"ratio": 0.375, "current": 3, "total": 8}},
    "clock": {"iso": "2026-08-18T21:07:42"},
    "stats": {"totalGames": 128},
}


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
    # Histórico de autoria (V3): snapshots completos, não deltas, porque o
    # documento é pequeno e um snapshot não pode divergir do preview derivado.
    undo_stack: list[dict[str, Any]] = field(default_factory=list)
    redo_stack: list[dict[str, Any]] = field(default_factory=list)


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
) -> tuple[ResolvedTheme, tuple[dict[str, str], ...]]:
    """Resolve o preview da sessão percorrendo a cadeia ``extends``.

    Usa ``ThemeResolver`` (profundidade finita, detecção de ciclo, base ausente).
    Em qualquer falha de cadeia ou de montagem do rascunho, degrada para a
    resolução só com tokens da sessão — o editor nunca trava o preview, mas
    publica diagnóstico quando a cadeia foi recusada.
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
        return (
            ThemeResolver(available).resolve(
                draft.id,
                high_contrast=high_contrast,
                reduced_motion=reduced_motion,
            ),
            (),
        )
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        diagnostic = _editor_chain_diagnostic(exc)
        return (
            _make_resolved_leaf(
                manifest,
                tokens,
                assets,
                high_contrast=high_contrast,
                reduced_motion=reduced_motion,
            ),
            (diagnostic,) if diagnostic is not None else (),
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


def _editor_chain_diagnostic(exc: BaseException) -> dict[str, str] | None:
    message = str(exc)
    if "profundidade de herança excedida" in message:
        return {
            "code": "THEME-EDITOR-EXTENDS-001",
            "reason": "cadeia extends acima do limite; preview usou os tokens da sessão",
        }
    if "ciclo de herança" in message:
        return {
            "code": "THEME-EDITOR-EXTENDS-002",
            "reason": "ciclo na cadeia extends; preview usou os tokens da sessão",
        }
    if "não encontrado" in message:
        return {
            "code": "THEME-EDITOR-EXTENDS-003",
            "reason": "base da cadeia extends ausente; preview usou os tokens da sessão",
        }
    return None


def _declared(manifest: dict[str, object]) -> dict[str, object]:
    """Declaração visual efetiva da cadeia ``extends`` e do rascunho.

    Diferente do preview, nada aqui é negociado por capability, tier ou
    acessibilidade: é o que o tema *declara*, base de edição dos inspetores.
    """
    out: dict[str, object] = {
        "effects": {},
        "sceneMotion": None,
        "sceneLayouts": None,
        "sceneSurfaces": None,
    }
    try:
        draft = ThemeManifest.from_dict(dict(manifest))
        available = _load_manifests_for_resolution()
        available[draft.id] = draft
        chain = ThemeResolver(available)._build_chain(draft.id)
    except (ValueError, TypeError, KeyError, AttributeError):
        return out
    stacks: dict[str, list[dict[str, Any]]] = {}
    for item in chain:
        for name, entries in item.effects.items():
            stacks[name] = [{**effect_defaults(entry.type), **entry.to_dict()} for entry in entries]
        if item.scene_motion is not None:
            out["sceneMotion"] = item.scene_motion.to_dict()
        if item.scene_layouts is not None:
            out["sceneLayouts"] = item.scene_layouts.to_dict()
        if item.scene_surfaces is not None:
            out["sceneSurfaces"] = item.scene_surfaces.to_dict()
    out["effects"] = stacks
    return out


def _document(session: EditorSession) -> dict[str, object]:
    """Documento + declaração que todo resultado de edição devolve à interface."""
    return {
        "manifest": dict(session.manifest),
        "declared": _declared(session.manifest),
        "effectSchema": effect_editor_schema(),
        "motionSchema": motion_editor_schema(),
    }


def _resolved_preview(
    manifest: dict[str, object],
    tokens: dict[str, dict[str, object]],
    assets: dict[str, str],
    *,
    high_contrast: bool = False,
    reduced_motion: bool = False,
    scene_layout_read_model: Mapping[str, Any] | None = None,
) -> dict[str, object]:
    resolved, diagnostics = _make_resolved(
        manifest,
        tokens,
        assets,
        high_contrast=high_contrast,
        reduced_motion=reduced_motion,
    )
    return _to_preview_object(
        resolved,
        diagnostics=diagnostics,
        scene_layout_read_model=scene_layout_read_model,
    )


def _to_preview_object(
    resolved: ResolvedTheme,
    *,
    diagnostics: tuple[dict[str, str], ...] = (),
    scene_layout_read_model: Mapping[str, Any] | None = None,
) -> dict[str, object]:
    """Entrega ao editor um preview já materializado, nunca bindings vivos."""
    preview = resolved.to_theme_qml_object()
    preview["editorDiagnostics"] = [dict(item) for item in diagnostics]
    if resolved.scene_layouts is not None:
        preview["sceneLayoutPreview"] = resolve_scene_layouts(
            resolved.scene_layouts,
            (
                scene_layout_read_model
                if scene_layout_read_model is not None
                else _LAYOUT_PREVIEW_READ_MODEL
            ),
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
    if resolved.scene_motion is not None:
        preview["sceneMotionPreview"] = resolve_scene_motion(
            resolved.scene_motion,
            reduced_motion=resolved.reduced_motion,
            interaction_state=_MOTION_PREVIEW_INTERACTION,
        ).to_qml_object()
    if resolved.scene_containers is not None:
        preview["sceneContainerPreview"] = resolve_scene_containers(
            resolved.scene_containers,
            bounds=_CONTAINER_PREVIEW_BOUNDS,
        ).to_qml_object()
    if resolved.scene_surfaces is not None:
        preview["sceneSurfacePreview"] = resolve_scene_surfaces(
            resolved.scene_surfaces,
            _SURFACE_PREVIEW_READ_MODEL,
        ).to_qml_object()
    preview["studioGraph"] = build_studio_graph(preview).to_qml_object()
    return preview


_HISTORY_LIMIT = 100
#: Metadados públicos que um binding de layout pode ler (spec §13); nada fora disto
#: chega a uma propriedade de template, mesmo que a regex genérica do domínio aceite.
BINDING_FIELDS = (
    "title",
    "year",
    "developer",
    "publisher",
    "genre",
    "description",
    "rating",
    "players",
    "region",
    "language",
    "series",
)
_MEDIA_RECIPE_FIELDS = {"fit", "orientation", "alignH", "alignV", "focalX", "focalY"}


def _capture(session: EditorSession) -> dict[str, Any]:
    return {
        "manifest": deepcopy(session.manifest),
        "tokens": deepcopy(session.tokens),
        "assets": dict(session.assets),
        "pending_assets": dict(session.pending_assets),
        "dirty": session.dirty,
    }


def _restore(session: EditorSession, snapshot: dict[str, Any]) -> None:
    session.manifest = deepcopy(snapshot["manifest"])
    session.tokens = deepcopy(snapshot["tokens"])
    session.assets = dict(snapshot["assets"])
    session.pending_assets = dict(snapshot["pending_assets"])
    session.dirty = bool(snapshot["dirty"])


def _history_state(session: EditorSession) -> dict[str, object]:
    return {
        "canUndo": bool(session.undo_stack),
        "canRedo": bool(session.redo_stack),
        "undoDepth": len(session.undo_stack),
        "redoDepth": len(session.redo_stack),
        "dirty": session.dirty,
    }


@contextmanager
def _mutation(session: EditorSession) -> Iterator[None]:
    """Uma edição = um passo de undo. Falha restaura o documento exatamente."""
    before = _capture(session)
    try:
        yield
    except BaseException:
        _restore(session, before)
        raise
    session.undo_stack.append(before)
    del session.undo_stack[:-_HISTORY_LIMIT]
    session.redo_stack.clear()


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
            "declared": _declared(manifest.to_dict()),
            "preview": _resolved_preview(manifest.to_dict(), tokens, assets),
            "effectSchema": effect_editor_schema(),
            "motionSchema": motion_editor_schema(),
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
            "declared": _declared(manifest.to_dict()),
            "preview": _resolved_preview(manifest.to_dict(), {}, {}),
            "effectSchema": effect_editor_schema(),
            "motionSchema": motion_editor_schema(),
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
        with _mutation(session):
            session.tokens[category] = dict(values)
            session.dirty = True
        return {"preview": self._preview(session), "history": _history_state(session)}

    def set_metadata(self, session_id: str, meta_field: str, value: object) -> dict[str, object]:
        session = self._get_session(session_id)
        allowed = {"name", "author", "license", "description", "homepage", "version", "extends"}
        if meta_field not in allowed:
            raise SteamZeroError("E-API-SCHEMA", detail=f"campo inválido: {meta_field}")
        if value is not None and not isinstance(value, str):
            raise SteamZeroError("E-API-SCHEMA", detail=f"valor de {meta_field} precisa ser string")
        with _mutation(session):
            session.manifest[meta_field] = value
            session.dirty = True
        return {"manifest": dict(session.manifest), "history": _history_state(session)}

    def set_layout(
        self, session_id: str, layout_id: str, field: str, value: object
    ) -> dict[str, object]:
        """Edita uma propriedade declarativa de layout e devolve o preview novo.

        O Studio só pode alterar campos de geometria allowlisted. A receita
        inteira é revalidada antes de tocar na sessão, então um valor inválido
        não deixa um rascunho parcialmente mutado nem alcança o pacote.
        """
        session = self._get_session(session_id)
        raw_book = session.manifest.get("sceneLayouts")
        if not isinstance(raw_book, dict):
            raw_book = _declared(session.manifest)["sceneLayouts"]  # herdado, materializado
        if not isinstance(raw_book, dict):
            raise SteamZeroError("E-API-SCHEMA", detail="tema não possui sceneLayouts editável")
        raw_layouts = raw_book.get("layouts")
        if not isinstance(raw_layouts, dict) or layout_id not in raw_layouts:
            raise SteamZeroError("E-API-SCHEMA", detail=f"layout não encontrado: {layout_id}")
        editable = {"columns", "gap", "maxItems", "selected", "item.width", "item.height"}
        if field not in editable:
            raise SteamZeroError("E-API-SCHEMA", detail=f"campo de layout não editável: {field}")

        candidate = deepcopy(raw_book)
        layout = candidate["layouts"][layout_id]
        if not isinstance(layout, dict):
            raise SteamZeroError("E-API-SCHEMA", detail=f"layout inválido: {layout_id}")
        if field.startswith("item."):
            item = layout.get("item")
            if not isinstance(item, dict):
                raise SteamZeroError("E-API-SCHEMA", detail="layout.item inválido")
            item[field.split(".", 1)[1]] = value
        else:
            layout[field] = value
        try:
            parsed = LayoutRecipeBook.from_dict(candidate)
        except (TypeError, ValueError) as exc:
            raise SteamZeroError("E-API-SCHEMA", detail=str(exc)) from exc
        with _mutation(session):
            session.manifest["sceneLayouts"] = parsed.to_dict()
            session.dirty = True
        return {
            **_document(session),
            "preview": self._preview(session),
            "layout": parsed.layouts[layout_id].to_dict(),
            "history": _history_state(session),
        }

    def edit_layout_binding(
        self,
        session_id: str,
        layout_id: str,
        prop: str,
        *,
        binding: str | None,
        fallback: object = None,
    ) -> dict[str, object]:
        """Liga (ou desliga) uma propriedade do template de layout a um metadado público.

        ``binding=None`` troca o binding pelo valor de ``fallback`` (escalar). O livro
        inteiro é revalidado por ``LayoutRecipeBook`` e a fonte do binding precisa
        estar na allowlist de metadados públicos; nada executável entra no documento.
        """
        session = self._get_session(session_id)
        raw_book = session.manifest.get("sceneLayouts")
        if not isinstance(raw_book, dict):
            raw_book = _declared(session.manifest)["sceneLayouts"]
        if not isinstance(raw_book, dict):
            raise SteamZeroError("E-API-SCHEMA", detail="tema não possui sceneLayouts editável")
        candidate = deepcopy(raw_book)
        layout = candidate.get("layouts", {}).get(layout_id)
        if not isinstance(layout, dict) or not isinstance(layout.get("template"), dict):
            raise SteamZeroError("E-API-SCHEMA", detail=f"layout sem template: {layout_id}")
        properties = layout["template"].setdefault("properties", {})
        if binding is None:
            properties[prop] = fallback
        else:
            if not binding.startswith("item.") or binding[5:] not in BINDING_FIELDS:
                raise SteamZeroError(
                    "E-API-SCHEMA",
                    detail=f"binding fora da allowlist de metadados públicos: {binding}",
                )
            entry: dict[str, object] = {"binding": binding}
            if fallback is not None:
                entry["fallback"] = fallback
            properties[prop] = entry
        try:
            parsed = LayoutRecipeBook.from_dict(candidate)
        except (TypeError, ValueError) as exc:
            raise SteamZeroError("E-API-SCHEMA", detail=str(exc)) from exc
        with _mutation(session):
            session.manifest["sceneLayouts"] = parsed.to_dict()
            session.dirty = True
        return {
            **_document(session),
            "preview": self._preview(session),
            "layout": parsed.layouts[layout_id].to_dict(),
            "history": _history_state(session),
        }

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
        with _mutation(session):
            session.pending_assets[slot] = (stored_name, data)
            session.assets[slot] = f"assets/{stored_name}"
            session.dirty = True
        return {
            "asset": {"slot": slot, "filename": stored_name, "size": len(data)},
            "history": _history_state(session),
        }

    def set_media_recipe(
        self, session_id: str, role: str, recipe_field: str, value: object
    ) -> dict[str, object]:
        """Edita enquadramento de um slot de mídia (fit/orientação/alinhamento/foco).

        A receita herdada é materializada no manifesto na primeira edição e a
        receita inteira é revalidada antes de tocar a sessão. Não há cópia
        pré-transformada da arte: o pacote guarda só esta declaração.
        """
        session = self._get_session(session_id)
        if recipe_field not in _MEDIA_RECIPE_FIELDS:
            raise SteamZeroError(
                "E-API-SCHEMA", detail=f"campo de receita não editável: {recipe_field}"
            )
        try:
            MediaRole(role)
        except ValueError:
            raise SteamZeroError("E-API-SCHEMA", detail=f"slot de mídia inválido: {role}") from None
        current = _resolved_preview(session.manifest, session.tokens, session.assets)
        inherited = current.get("mediaRecipes")
        book: dict[str, dict[str, object]] = {}
        raw_own = session.manifest.get("mediaRecipes")
        if isinstance(raw_own, dict) and isinstance(raw_own.get("recipes"), dict):
            book = deepcopy(raw_own["recipes"])
        if role not in book:
            base = inherited.get(role) if isinstance(inherited, dict) else None
            if not isinstance(base, dict):
                raise SteamZeroError("E-API-SCHEMA", detail=f"slot sem receita para editar: {role}")
            book[role] = deepcopy(base)
        book[role][recipe_field] = value
        candidate = {"schemaVersion": MEDIA_RECIPE_SCHEMA_VERSION, "recipes": book}
        try:
            parsed = parse_media_recipes(candidate)
        except (TypeError, ValueError) as exc:
            raise SteamZeroError("E-API-SCHEMA", detail=str(exc)) from exc
        with _mutation(session):
            session.manifest["mediaRecipes"] = media_recipes_to_dict(parsed)
            session.dirty = True
        return {
            **_document(session),
            "preview": self._preview(session),
            "recipe": parsed[role].to_dict(),
            "history": _history_state(session),
        }

    def edit_effect_stack(
        self,
        session_id: str,
        stack: str,
        op: str,
        *,
        index: int | None = None,
        effect_type: str | None = None,
        param: str | None = None,
        value: object = None,
    ) -> dict[str, object]:
        """Edita uma pilha de efeitos declarativos (add/set/remove/move).

        A pilha herdada é materializada no manifesto na primeira edição e a pilha
        inteira é revalidada por ``EffectSpec`` (allowlist, limites, cores) antes
        de tocar a sessão; falha deixa o documento intacto.
        """
        session = self._get_session(session_id)
        if op not in {"add", "set", "remove", "move"}:
            raise SteamZeroError("E-API-SCHEMA", detail=f"operação de efeito inválida: {op}")
        if not stack:
            raise SteamZeroError("E-API-SCHEMA", detail="stack de efeitos obrigatório")
        raw_own = session.manifest.get("effects")
        stacks: dict[str, list[dict[str, Any]]] = {}
        if isinstance(raw_own, dict) and isinstance(raw_own.get("stacks"), dict):
            stacks = deepcopy(raw_own["stacks"])
        if stack not in stacks:
            declared_stacks = _declared(session.manifest)["effects"]
            seed = declared_stacks.get(stack) if isinstance(declared_stacks, dict) else None
            stacks[stack] = deepcopy(seed) if isinstance(seed, list) else []
        entries = stacks[stack]
        try:
            if op == "add":
                entries.append(
                    {"type": effect_type, **effect_defaults(EffectType(effect_type or ""))}
                )
            else:
                if index is None or not 0 <= index < len(entries):
                    raise ValueError("índice de efeito fora da pilha")
                if op == "remove":
                    del entries[index]
                elif op == "move":
                    target = int(value) if isinstance(value, int | float) else -1
                    if not 0 <= target < len(entries):
                        raise ValueError("destino de efeito fora da pilha")
                    entries.insert(target, entries.pop(index))
                else:
                    if not param:
                        raise ValueError("parâmetro obrigatório")
                    entries[index][param] = value
            parsed = parse_effect_stacks(
                {"schemaVersion": EFFECT_STACK_SCHEMA_VERSION, "stacks": stacks}
            )
        except (TypeError, ValueError) as exc:
            raise SteamZeroError("E-API-SCHEMA", detail=str(exc)) from exc
        with _mutation(session):
            session.manifest["effects"] = effect_stacks_to_dict(parsed)
            session.dirty = True
        return {
            **_document(session),
            "preview": self._preview(session),
            "stack": [item.to_dict() for item in parsed[stack]],
            "history": _history_state(session),
        }

    def edit_motion(
        self,
        session_id: str,
        op: str,
        *,
        timeline: str | None = None,
        index: int | None = None,
        field: str | None = None,
        value: object = None,
    ) -> dict[str, object]:
        """Edita estados (keyframes) e timelines declarativos de ``sceneMotion``.

        ``set_state`` altera um keyframe (opacity/scale/translate) do estado em
        ``timeline``; as demais operações criam/alteram/removem timelines e clips.
        O livro inteiro é revalidado por ``MotionBook`` antes de tocar a sessão.
        """
        session = self._get_session(session_id)
        ops = {
            "set_state",
            "add_timeline",
            "remove_timeline",
            "set_timeline",
            "add_clip",
            "set_clip",
            "remove_clip",
            "move_clip",
        }
        if op not in ops or not timeline:
            raise SteamZeroError("E-API-SCHEMA", detail=f"operação de movimento inválida: {op}")
        raw = session.manifest.get("sceneMotion")
        if not isinstance(raw, dict):
            raw = _declared(session.manifest)["sceneMotion"]  # herdado, nunca descartado
        book: dict[str, Any] = (
            deepcopy(raw)
            if isinstance(raw, dict)
            else {"schemaVersion": 1, "states": {"normal": {}}}
        )
        timelines: dict[str, Any] = book.setdefault("timelines", {})
        try:
            if op == "set_state":
                if not field:
                    raise ValueError("campo de keyframe obrigatório")
                book["states"].setdefault(timeline, {})[field] = value
            elif op == "add_timeline":
                if timeline in timelines:
                    raise ValueError(f"timeline já existe: {timeline}")
                timelines[timeline] = {
                    "kind": str(value or "sequence"),
                    "clips": [{"state": "normal", "duration": 0}],
                }
            else:
                if timeline not in timelines:
                    raise ValueError(f"timeline inexistente: {timeline}")
                entry = timelines[timeline]
                if op == "remove_timeline":
                    del timelines[timeline]
                elif op == "set_timeline":
                    if field not in {"kind", "repeat"}:
                        raise ValueError("campo de timeline não editável")
                    entry[field] = value
                elif op == "add_clip":
                    if not isinstance(value, dict):
                        raise ValueError("clip exige objeto")
                    entry["clips"].append(dict(value))
                else:
                    clips = entry["clips"]
                    if index is None or not 0 <= index < len(clips):
                        raise ValueError("índice de clip fora da timeline")
                    if op == "remove_clip":
                        del clips[index]
                    elif op == "move_clip":
                        if isinstance(value, bool) or not isinstance(value, int):
                            raise ValueError("destino de clip precisa ser inteiro")
                        target = value
                        if not 0 <= target < len(clips):
                            raise ValueError("destino de clip fora da timeline")
                        clips.insert(target, clips.pop(index))
                    else:
                        if field not in {"state", "duration", "transition"}:
                            raise ValueError("campo de clip não editável")
                        clips[index][field] = value
            parsed = MotionBook.from_dict(book)
        except (TypeError, ValueError, KeyError) as exc:
            raise SteamZeroError("E-API-SCHEMA", detail=str(exc)) from exc
        with _mutation(session):
            session.manifest["sceneMotion"] = parsed.to_dict()
            session.dirty = True
        return {
            **_document(session),
            "preview": self._preview(session),
            "motion": parsed.to_dict(),
            "history": _history_state(session),
        }

    def undo(self, session_id: str) -> dict[str, object]:
        return self._step(session_id, undo=True)

    def redo(self, session_id: str) -> dict[str, object]:
        return self._step(session_id, undo=False)

    def _step(self, session_id: str, *, undo: bool) -> dict[str, object]:
        session = self._get_session(session_id)
        source, target = (
            (session.undo_stack, session.redo_stack)
            if undo
            else (session.redo_stack, session.undo_stack)
        )
        if not source:
            raise SteamZeroError(
                "E-API-SCHEMA",
                detail="nada para desfazer" if undo else "nada para refazer",
            )
        target.append(_capture(session))
        _restore(session, source.pop())
        # Manifesto, assets e preview saem da mesma sessão restaurada: não há
        # estado de preview guardado que possa divergir do documento.
        return {
            **_document(session),
            "preview": self._preview(session),
            "history": _history_state(session),
        }

    def history(self, session_id: str) -> dict[str, object]:
        return {"history": _history_state(self._get_session(session_id))}

    def preview(
        self,
        session_id: str,
        *,
        high_contrast: bool = False,
        reduced_motion: bool = False,
        scene_layout_read_model: Mapping[str, Any] | None = None,
    ) -> dict[str, object]:
        session = self._get_session(session_id)
        return {
            "preview": self._preview(
                session,
                high_contrast,
                reduced_motion,
                scene_layout_read_model=scene_layout_read_model,
            )
        }

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
                "E-THEME-ID-EXISTS",
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
        *,
        scene_layout_read_model: Mapping[str, Any] | None = None,
    ) -> dict[str, object]:
        return _resolved_preview(
            session.manifest,
            session.tokens,
            session.assets,
            high_contrast=high_contrast,
            reduced_motion=reduced_motion,
            scene_layout_read_model=scene_layout_read_model,
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
