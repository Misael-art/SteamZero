from __future__ import annotations

import contextlib
import importlib.resources
import json
from pathlib import Path
from typing import Any

import jsonschema

from steamzero.core.errors import SteamZeroError
from steamzero.domain.asset_recipes import validate_asset_source
from steamzero.domain.theme_effects import PerformanceTier
from steamzero.domain.themes import (
    THEME_API_VERSION,
    THEME_DEFAULT_ID,
    ResolvedTheme,
    ThemeManifest,
    ThemeResolver,
)

_THEME_PACKAGE = "steamzero.themes"
_MAX_MANIFEST_BYTES = 256 * 1024
_MAX_FILES = 128
_MAX_TOTAL_BYTES = 64 * 1024 * 1024
_MAX_ASSET_BYTES = 16 * 1024 * 1024
_MAX_ASSET_DIMENSION = 8192
_MAX_DIR_DEPTH = 4
_MAX_THEMES = 100
_ALLOWED_RASTER = frozenset({".png", ".jpg", ".jpeg", ".webp"})
_ALLOWED_SVG_EXT = ".svg"
_PROHIBITED_FILES = frozenset(
    {
        ".qml",
        ".js",
        ".py",
        ".so",
        ".wasm",
        ".wasm64",
        ".html",
        ".htm",
        ".sh",
        ".bash",
        ".zsh",
        ".fish",
    }
)


def _load_manifest_schema() -> dict[str, Any]:
    schemas = importlib.resources.files("steamzero.schemas")
    ref = schemas.joinpath("theme-manifest-v1.schema.json")
    with importlib.resources.as_file(ref) as path:
        loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    # ``jsonschema.validate`` não recebe o registry multi-arquivo usado pela API.
    # Injetar o schema empacotado preserva a mesma validação sem buscar a rede.
    asset_ref = schemas.joinpath("asset-recipe-v1.schema.json")
    with importlib.resources.as_file(asset_ref) as path:
        loaded["properties"]["assetRecipes"] = json.loads(path.read_text(encoding="utf-8"))
    layout_ref = schemas.joinpath("scene-layout-v1.schema.json")
    with importlib.resources.as_file(layout_ref) as path:
        loaded["properties"]["sceneLayouts"] = json.loads(path.read_text(encoding="utf-8"))
    palette_ref = schemas.joinpath("dynamic-palette-v1.schema.json")
    with importlib.resources.as_file(palette_ref) as path:
        loaded["properties"]["dynamicPalette"] = json.loads(path.read_text(encoding="utf-8"))
    glass_ref = schemas.joinpath("glass-panel-v1.schema.json")
    with importlib.resources.as_file(glass_ref) as path:
        loaded["properties"]["glass"] = json.loads(path.read_text(encoding="utf-8"))
    motion_ref = schemas.joinpath("scene-motion-v1.schema.json")
    with importlib.resources.as_file(motion_ref) as path:
        loaded["properties"]["sceneMotion"] = json.loads(path.read_text(encoding="utf-8"))
    surface_ref = schemas.joinpath("scene-surfaces-v1.schema.json")
    with importlib.resources.as_file(surface_ref) as path:
        loaded["properties"]["sceneSurfaces"] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


_MANIFEST_SCHEMA = _load_manifest_schema()


def list_builtin_theme_ids() -> list[str]:
    """Lista IDs de temas builtin empacotados via importlib.resources."""
    ref: object = importlib.resources.files(_THEME_PACKAGE)
    ids: list[str] = []
    if not _is_resource_dir(ref):
        return ids
    for entry in _iter_resource(ref):
        if _is_resource_dir(entry) and _resource_has(entry, "theme.json"):
            ids.append(_resource_name(entry))
    return sorted(ids)


def _is_resource_dir(ref: object) -> bool:
    try:
        if hasattr(ref, "is_dir") and callable(ref.is_dir):
            return bool(ref.is_dir())
        return False
    except Exception:
        return False


def _iter_resource(ref: object) -> list[object]:
    with contextlib.suppress(Exception):
        if hasattr(ref, "iterdir") and callable(ref.iterdir):
            return list(ref.iterdir())
    return []


def _resource_has(ref: object, name: str) -> bool:
    with contextlib.suppress(Exception):
        if hasattr(ref, "joinpath") and callable(ref.joinpath):
            child = ref.joinpath(name)
            if hasattr(child, "exists") and callable(child.exists):
                return bool(child.exists())
    return False


def _resource_name(ref: object) -> str:
    with contextlib.suppress(Exception):
        if hasattr(ref, "name"):
            return str(ref.name)
    return ""


def read_builtin_manifest(theme_id: str) -> ThemeManifest:
    """Lê e valida o manifesto de um tema builtin."""
    ref = importlib.resources.files(_THEME_PACKAGE).joinpath(theme_id, "theme.json")
    try:
        with importlib.resources.as_file(ref) as path:
            raw = json.loads(path.read_bytes())
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise SteamZeroError("E-THEME-MANIFEST", detail=str(exc)) from exc
    _validate_manifest(raw)
    return ThemeManifest.from_dict(raw)


def validate_source_path(source_path: str) -> Path:
    """Valida que source_path é um diretório local acessível."""
    path = Path(source_path).resolve()
    if not path.is_dir():
        raise SteamZeroError("E-THEME-MANIFEST", detail=f"origem não encontrada: {source_path}")
    return path


def read_user_manifest_from(source_path: Path) -> ThemeManifest:
    """Lê e valida o manifesto de um pacote de tema do usuário."""
    manifest_path = source_path / "theme.json"
    if not manifest_path.is_file():
        raise SteamZeroError("E-THEME-MANIFEST", detail="theme.json ausente no pacote")
    try:
        raw = json.loads(manifest_path.read_bytes())
    except json.JSONDecodeError as exc:
        raise SteamZeroError("E-THEME-MANIFEST", detail=str(exc)) from exc
    _validate_manifest(raw)
    return ThemeManifest.from_dict(raw)


def _validate_manifest(raw: dict[str, Any]) -> None:
    try:
        jsonschema.validate(raw, _MANIFEST_SCHEMA)
    except jsonschema.ValidationError as exc:
        raise SteamZeroError("E-THEME-MANIFEST", detail=str(exc)) from exc
    api = raw.get("compatibility", {}).get("themeApi", 0)
    if api != THEME_API_VERSION:
        raise SteamZeroError(
            "E-THEME-INCOMPATIBLE", detail=f"tema requer themeApi={api}, atual={THEME_API_VERSION}"
        )


def _check_path_safety(directory: Path) -> None:
    resolved_root = directory.resolve()
    depth = 0
    for entry in sorted(directory.rglob("*"), key=lambda p: str(p)):
        if not entry.exists():
            continue
        depth = len(entry.relative_to(directory).parts)
        if depth > _MAX_DIR_DEPTH:
            raise SteamZeroError(
                "E-THEME-LIMIT", detail=f"profundidade excedida: {depth} > {_MAX_DIR_DEPTH}"
            )
        try:
            resolved = entry.resolve()
        except OSError as exc:
            raise SteamZeroError("E-THEME-UNSAFE", detail=str(exc)) from exc
        if resolved_root not in resolved.parents and resolved != resolved_root:
            raise SteamZeroError("E-THEME-UNSAFE", detail=f"caminho fora da raiz: {entry}")
        if entry.is_symlink():
            raise SteamZeroError("E-THEME-UNSAFE", detail=f"symlink não permitido: {entry}")
        if entry.is_socket() or entry.is_fifo():
            raise SteamZeroError(
                "E-THEME-UNSAFE", detail=f"arquivo especial não permitido: {entry}"
            )
        if entry.is_block_device() or entry.is_char_device():
            raise SteamZeroError(
                "E-THEME-UNSAFE", detail=f"arquivo especial não permitido: {entry}"
            )


def _check_file_limits(directory: Path) -> tuple[int, int]:
    total_bytes = 0
    file_count = 0
    for entry in sorted(directory.rglob("*"), key=lambda p: str(p)):
        if not entry.is_file():
            continue
        file_count += 1
        if file_count > _MAX_FILES:
            raise SteamZeroError(
                "E-THEME-LIMIT", detail=f"número de arquivos excedido: {file_count}"
            )
        size = entry.stat().st_size
        total_bytes += size
        if total_bytes > _MAX_TOTAL_BYTES:
            raise SteamZeroError("E-THEME-LIMIT", detail=f"tamanho total excedido: {total_bytes}")
        ext = entry.suffix.lower()
        if ext in _PROHIBITED_FILES:
            raise SteamZeroError("E-THEME-UNSAFE", detail=f"tipo de arquivo proibido: {ext}")
        if ext in _ALLOWED_RASTER | {_ALLOWED_SVG_EXT} and size > _MAX_ASSET_BYTES:
            raise SteamZeroError(
                "E-THEME-LIMIT", detail=f"asset muito grande: {entry.name} ({size} bytes)"
            )
        if ext == _ALLOWED_SVG_EXT:
            try:
                validate_asset_source(entry.read_bytes())
            except (OSError, ValueError) as exc:
                raise SteamZeroError("E-THEME-UNSAFE", detail=f"{entry.name}: {exc}") from exc
    return file_count, total_bytes


def _check_manifest_limits(raw: dict[str, Any]) -> None:
    serialized = json.dumps(raw)
    if len(serialized.encode()) > _MAX_MANIFEST_BYTES:
        raise SteamZeroError("E-THEME-LIMIT", detail="manifesto excede 256 KiB")
    extends = raw.get("extends")
    if extends is not None and not isinstance(extends, str):
        raise SteamZeroError("E-THEME-MANIFEST", detail="extends precisa ser string")


def validate_theme_directory(directory: Path) -> ThemeManifest:
    """Valida um diretório de tema. Levanta SteamZeroError se inválido."""
    _check_path_safety(directory)
    manifest = read_user_manifest_from(directory)
    _check_manifest_limits(manifest.to_dict())
    _check_file_limits(directory)
    theme_id = manifest.id
    if directory.name != theme_id:
        raise SteamZeroError(
            "E-THEME-MANIFEST",
            detail=f"nome do diretório ({directory.name}) difere do id ({theme_id})",
        )
    return manifest


class ThemeCatalog:
    """Catálogo que descobre temas builtin e do usuário."""

    def __init__(self, user_themes_dir: Path | None = None) -> None:
        from steamzero.core import paths

        self._user_themes_dir = user_themes_dir or paths.themes_dir()

    def list_catalog(self) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        seen: set[str] = set()
        for tid in list_builtin_theme_ids():
            try:
                manifest = read_builtin_manifest(tid)
                seen.add(tid)
                entries.append(
                    {
                        "id": tid,
                        "name": manifest.name,
                        "version": manifest.version,
                        "author": manifest.author,
                        "license": manifest.license,
                        "state": "available",
                        "origin": "builtin",
                        "compatible": True,
                    }
                )
            except SteamZeroError as exc:
                entries.append(
                    {
                        "id": tid,
                        "name": tid,
                        "version": "",
                        "author": "",
                        "license": "",
                        "state": "invalid",
                        "origin": "builtin",
                        "compatible": False,
                        "error": exc.detail,
                    }
                )
        if self._user_themes_dir is not None and self._user_themes_dir.is_dir():
            for entry in sorted(self._user_themes_dir.iterdir(), key=str):
                if not entry.is_dir():
                    continue
                tid = entry.name
                if tid in seen:
                    continue
                try:
                    manifest = validate_theme_directory(entry)
                    seen.add(tid)
                    api = manifest.compatibility.get("themeApi", 0)
                    compatible = api == THEME_API_VERSION
                    entries.append(
                        {
                            "id": tid,
                            "name": manifest.name,
                            "version": manifest.version,
                            "author": manifest.author,
                            "license": manifest.license,
                            "state": "available" if compatible else "incompatible",
                            "origin": "user",
                            "compatible": compatible,
                        }
                    )
                except SteamZeroError as exc:
                    entries.append(
                        {
                            "id": tid,
                            "name": tid,
                            "version": "",
                            "author": "",
                            "license": "",
                            "state": "invalid",
                            "origin": "user",
                            "compatible": False,
                            "error": exc.detail,
                        }
                    )
        return entries

    def resolve(
        self,
        theme_id: str,
        *,
        effect_capabilities: frozenset[str] | None = None,
        performance_tier: PerformanceTier | None = None,
        high_contrast: bool = False,
        reduced_motion: bool = False,
    ) -> ResolvedTheme:
        manifests: dict[str, ThemeManifest] = {}
        for tid in list_builtin_theme_ids():
            with contextlib.suppress(SteamZeroError):
                manifests[tid] = read_builtin_manifest(tid)
        if self._user_themes_dir is not None and self._user_themes_dir.is_dir():
            for entry in self._user_themes_dir.iterdir():
                if not entry.is_dir():
                    continue
                tid = entry.name
                with contextlib.suppress(SteamZeroError):
                    manifests[tid] = validate_theme_directory(entry)
        resolver = ThemeResolver(manifests)
        try:
            return resolver.resolve(
                theme_id,
                effect_capabilities=effect_capabilities,
                performance_tier=performance_tier,
                high_contrast=high_contrast,
                reduced_motion=reduced_motion,
            )
        except ValueError:
            if theme_id == THEME_DEFAULT_ID:
                raise
            # Pacote inválido, incompatível ou ausente não derruba a central:
            # o builtin seguro permanece o único consumidor visível.
            return resolver.resolve(
                THEME_DEFAULT_ID,
                effect_capabilities=effect_capabilities,
                performance_tier=performance_tier,
                high_contrast=high_contrast,
                reduced_motion=reduced_motion,
            )
