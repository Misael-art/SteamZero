from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from steamzero.core import transaction
from steamzero.core.errors import SteamZeroError
from steamzero.domain.media_pipeline import MediaPipeline, _is_managed

RunningProbe = Callable[[], bool]
_KINDS = ("portrait", "landscape", "hero", "logo", "icon")
_EXTENSIONS = (".png", ".jpg", ".webp")
_MAX_ASSET = 16 * 1024 * 1024


def _default_roots() -> tuple[Path, ...]:
    home = Path.home()
    return (
        home / ".local/share/Steam",
        home / ".steam/steam",
        home / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
    )


def _steam_running() -> bool:
    proc = Path("/proc")
    try:
        entries = proc.iterdir()
    except OSError:
        return False
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            name = (entry / "comm").read_text(encoding="utf-8").strip().casefold()
        except OSError:
            continue
        if name in {"steam", "steamwebhelper"}:
            return True
    return False


class SteamMediaManager:
    def __init__(
        self,
        pipeline: MediaPipeline | None = None,
        *,
        roots: Sequence[Path] | None = None,
        running_probe: RunningProbe = _steam_running,
    ) -> None:
        self._pipeline = pipeline
        configured = tuple(roots) if roots is not None else _default_roots()
        self._roots = tuple(root.resolve() for root in configured if root.is_dir())
        self._running_probe = running_probe

    def snapshot(self, game_id: str) -> dict[str, Any]:
        _validate_numeric("gameId", game_id)
        accounts = self._accounts()
        return {
            "gameId": game_id,
            "steamRunning": self._running_probe(),
            "accounts": [
                {
                    "id": account_id,
                    "label": f"Conta Steam •••{account_id[-4:]}",
                    "assets": self._asset_status(grid, game_id),
                }
                for account_id, grid in accounts
            ],
            "packageContract": {
                "required": "ao menos um arquivo",
                "filenames": [f"{kind}.png|jpg|webp" for kind in _KINDS],
                "maxBytesEach": _MAX_ASSET,
                "source": "local-only",
            },
        }

    def plan(self, game_id: str, account_id: str, steam_appid: int) -> dict[str, Any]:
        _validate_numeric("gameId", game_id)
        _validate_numeric("accountId", account_id)
        if self._running_probe():
            raise SteamZeroError("E-TX-LOCKED", detail="feche a Steam antes de trocar a arte")
        if self._pipeline is None:
            raise SteamZeroError(
                "E-INTERNAL-UNEXPECTED",
                detail="pipeline de mídia não configurado",
            )
        plan = self._pipeline.view_steam_plan(game_id, account_id, steam_appid)
        if plan is None:
            raise SteamZeroError(
                "E-CONTENT-INCOMPLETE", detail="nenhuma mídia otimizada disponível"
            )
        data = plan.to_dict()
        data.update(
            {
                "gameId": game_id,
                "accountId": account_id,
                "steamAppId": steam_appid,
            }
        )
        return data

    def plan_package(self, game_id: str, account_id: str, package_dir: Path) -> dict[str, Any]:
        _validate_numeric("gameId", game_id)
        _validate_numeric("accountId", account_id)
        if self._running_probe():
            raise SteamZeroError("E-TX-LOCKED", detail="feche a Steam antes de trocar a arte")
        accounts = dict(self._accounts())
        grid = accounts.get(account_id)
        if grid is None:
            raise SteamZeroError("E-API-SCHEMA", detail="conta Steam não encontrada")
        files = _read_package(package_dir)
        writes: dict[Path, bytes] = {}
        removals: set[Path] = set()
        changed: list[str] = []
        for kind, (extension, content) in files.items():
            target = grid / f"{_target_stem(game_id, kind)}{extension}"
            writes[target] = content
            for old in _variants(grid, game_id, kind):
                if old != target:
                    removals.add(old)
            changed.append(kind)
        plan = transaction.plan_write_files(
            writes,
            removals=removals,
            root=grid,
            kind="steam.media-package",
        )
        data = plan.to_dict()
        data.update(
            {
                "gameId": game_id,
                "accountId": account_id,
                "assets": changed,
                "replacedVariants": len(removals),
                "sourcePolicy": "local-only",
            }
        )
        return data

    def apply(self, plan_id: str, confirm_token: str) -> dict[str, Any]:
        if self._running_probe():
            raise SteamZeroError("E-TX-LOCKED", detail="feche a Steam antes de trocar a arte")
        result = transaction.apply(plan_id, confirm_token)
        return {
            "status": result.status,
            "operationId": result.operation_id,
            "message": "Mídia Steam publicada; reinicie a Steam para atualizar a biblioteca.",
        }

    @staticmethod
    def rollback(operation_id: str) -> dict[str, Any]:
        result = transaction.rollback(operation_id, reason="steam-media-package")
        return {
            "status": result.status,
            "operationId": result.operation_id,
            "restored": result.restored,
        }

    def _accounts(self) -> list[tuple[str, Path]]:
        found: dict[str, Path] = {}
        for root in self._roots:
            userdata = root / "userdata"
            if not userdata.is_dir() or userdata.is_symlink():
                continue
            try:
                entries = tuple(userdata.iterdir())
            except OSError:
                continue
            for account in entries:
                if not account.name.isdigit() or account.is_symlink() or not account.is_dir():
                    continue
                grid = account / "config" / "grid"
                if grid.parent.is_dir() and not grid.parent.is_symlink():
                    found.setdefault(account.name, grid)
        return sorted(found.items())

    def _asset_status(self, grid: Path, game_id: str) -> list[dict[str, Any]]:
        return [
            {"kind": kind, "configured": bool(self._view_exists(grid, game_id, kind))}
            for kind in ("grid", "portrait", "hero", "logo", "icon")
        ]

    @staticmethod
    def _view_exists(grid: Path, game_id: str, kind: str) -> bool:
        suffixes = {"grid": "", "portrait": "p", "hero": "_hero", "logo": "_logo", "icon": "_icon"}
        suffix = suffixes[kind]
        for ext in _EXTENSIONS:
            p = grid / f"{game_id}{suffix}{ext}"
            if p.exists() and _is_managed(p):
                return True
        return False


def _validate_numeric(label: str, value: str) -> None:
    if not value or not value.isdigit() or len(value) > 32:
        raise SteamZeroError("E-API-SCHEMA", detail=f"{label} inválido")


def _target_stem(game_id: str, kind: str) -> str:
    suffixes = {"grid": "", "portrait": "p", "hero": "_hero", "logo": "_logo"}
    return game_id + suffixes[kind]


def _variants(grid: Path, game_id: str, kind: str) -> list[Path]:
    return [
        grid / f"{_target_stem(game_id, kind)}{extension}"
        for extension in _EXTENSIONS
        if (grid / f"{_target_stem(game_id, kind)}{extension}").is_file()
        and not (grid / f"{_target_stem(game_id, kind)}{extension}").is_symlink()
    ]


def _matches_magic(content: bytes, extension: str) -> bool:
    if extension == ".png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if extension == ".jpg":
        return content.startswith(b"\xff\xd8\xff")
    return content.startswith(b"RIFF") and content[8:12] == b"WEBP"


def _read_package(package_dir: Path) -> dict[str, tuple[str, bytes]]:
    if package_dir.is_symlink() or not package_dir.is_dir():
        raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="pacote de mídia inválido")
    result: dict[str, tuple[str, bytes]] = {}
    for kind in _KINDS:
        matches = [
            package_dir / f"{kind}{extension}"
            for extension in _EXTENSIONS
            if (package_dir / f"{kind}{extension}").is_file()
            and not (package_dir / f"{kind}{extension}").is_symlink()
        ]
        if len(matches) > 1:
            raise SteamZeroError("E-CONTENT-POLICY", detail=f"mais de uma variante para {kind}")
        if not matches:
            continue
        source = matches[0]
        if source.stat().st_size <= 0 or source.stat().st_size > _MAX_ASSET:
            raise SteamZeroError("E-CONTENT-POLICY", detail=f"tamanho inválido: {source.name}")
        content = source.read_bytes()
        if not _matches_magic(content, source.suffix):
            raise SteamZeroError("E-CONTENT-POLICY", detail=f"formato inválido: {source.name}")
        result[kind] = (source.suffix, content)
    if not result:
        raise SteamZeroError("E-CONTENT-INCOMPLETE", detail="pacote não contém arte válida")
    return result
