# SPDX-License-Identifier: GPL-3.0-or-later
"""Limpeza explícita de caches Steam com remoção crash-resilient.

Compatdata/Proton, saves, jogos instalados, workshop e downloads em andamento
nunca entram no inventário. Esta capacidade remove somente shader cache
regenerável e crash dumps, após confirmação destrutiva digitada e com a Steam
fechada. O rename atômico para um tombstone torna recovery determinístico.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from steamzero.core import fs, ids, paths
from steamzero.core.errors import SteamZeroError

RunningProbe = Callable[[], bool]
_CATEGORIES = frozenset({"shader-cache", "crash-dumps"})
_CONFIRM_PHRASE = "LIBERAR ESPACO"
_TTL = timedelta(minutes=15)
_MAX_ENTRIES = 250_000


def _now() -> datetime:
    return datetime.now(UTC)


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


@dataclass(frozen=True)
class CleanupCandidate:
    path: str
    category: str
    game_id: str | None
    size: int
    entries: int
    fingerprint: str

    def to_dict(self, *, expose_path: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "category": self.category,
            "gameId": self.game_id,
            "sizeBytes": self.size,
            "entries": self.entries,
            "fingerprint": self.fingerprint,
        }
        if expose_path:
            data["path"] = self.path
        return data


class SteamMaintenance:
    def __init__(
        self,
        *,
        roots: Sequence[Path] | None = None,
        running_probe: RunningProbe = _steam_running,
    ) -> None:
        configured = tuple(roots) if roots is not None else _default_roots()
        self._roots = tuple(root.resolve() for root in configured if root.is_dir())
        self._running_probe = running_probe

    def snapshot(self, game_id: str = "") -> dict[str, Any]:
        _validate_game_id(game_id)
        candidates = self._scan(game_id)
        totals = {
            category: sum(item.size for item in candidates if item.category == category)
            for category in sorted(_CATEGORIES)
        }
        return {
            "steamRunning": self._running_probe(),
            "gameId": game_id,
            "totalBytes": sum(item.size for item in candidates),
            "categories": [
                {
                    "id": category,
                    "sizeBytes": totals[category],
                    "items": sum(item.category == category for item in candidates),
                    "safeScope": "cache-regeneravel"
                    if category == "shader-cache"
                    else "diagnostico-antigo",
                }
                for category in sorted(_CATEGORIES)
            ],
            "excluded": ["compatdata", "saves", "workshop", "downloads", "game-content"],
            "recoveryRequired": bool(self._recoverable_operations()),
        }

    def plan(self, categories: Sequence[str], game_id: str = "") -> dict[str, Any]:
        _validate_game_id(game_id)
        chosen = frozenset(categories)
        if not chosen or not chosen <= _CATEGORIES:
            raise SteamZeroError("E-API-SCHEMA", detail="categorias de limpeza inválidas")
        if self._running_probe():
            raise SteamZeroError("E-TX-LOCKED", detail="feche a Steam antes de planejar limpeza")
        candidates = [item for item in self._scan(game_id) if item.category in chosen]
        plan_id = ids.new_ulid()
        created = _now()
        payload = {
            "schemaVersion": 1,
            "planId": plan_id,
            "confirmToken": secrets.token_urlsafe(24),
            "confirmPhrase": _CONFIRM_PHRASE,
            "createdAt": created.isoformat(),
            "expiresAt": (created + _TTL).isoformat(),
            "status": "pending",
            "gameId": game_id,
            "categories": sorted(chosen),
            "totalBytes": sum(item.size for item in candidates),
            "candidateCount": len(candidates),
            "candidates": [item.to_dict(expose_path=True) for item in candidates],
            "rollbackGuarantee": "G-NONE após confirmação destrutiva; cache regenerável",
            "excluded": ["compatdata", "saves", "workshop", "downloads", "game-content"],
        }
        fs.write_atomic_text(
            paths.steam_maintenance_plan_path(plan_id),
            json.dumps(payload, sort_keys=True, ensure_ascii=False),
        )
        return _public_plan(payload)

    def apply(self, plan_id: str, confirm_token: str, confirm_phrase: str) -> dict[str, Any]:
        plan = self._load_plan(plan_id)
        if plan.get("status") != "pending" or not secrets.compare_digest(
            str(plan.get("confirmToken", "")), confirm_token
        ):
            raise SteamZeroError("E-TX-CONFIRM-REQUIRED", detail="plano de limpeza inválido")
        if confirm_phrase != _CONFIRM_PHRASE:
            raise SteamZeroError("E-TX-CONFIRM-REQUIRED", detail="frase destrutiva incorreta")
        expires = datetime.fromisoformat(str(plan["expiresAt"]))
        if _now() > expires:
            raise SteamZeroError("E-TX-CONFIRM-REQUIRED", detail="plano de limpeza expirado")
        if self._running_probe():
            raise SteamZeroError("E-TX-LOCKED", detail="feche a Steam antes de limpar caches")
        candidates = _candidates_from_plan(plan)
        self._validate_candidates(candidates)
        operation_id = ids.new_ulid()
        operation = {
            "schemaVersion": 1,
            "operationId": operation_id,
            "planId": plan_id,
            "state": "applying",
            "candidates": [
                {
                    **item.to_dict(expose_path=True),
                    "state": "pending",
                    "tombstone": str(_tombstone(Path(item.path), operation_id)),
                }
                for item in candidates
            ],
            "freedBytes": 0,
        }
        self._save_operation(operation)
        self._finish_operation(operation)
        plan["status"] = "applied"
        fs.write_atomic_text(
            paths.steam_maintenance_plan_path(plan_id),
            json.dumps(plan, sort_keys=True, ensure_ascii=False),
        )
        return _public_operation(operation)

    def recover(self) -> dict[str, Any]:
        recovered: list[dict[str, Any]] = []
        for operation in self._recoverable_operations():
            self._finish_operation(operation)
            recovered.append(_public_operation(operation))
        return {"status": "recovered" if recovered else "noop", "operations": recovered}

    def _scan(self, game_id: str) -> list[CleanupCandidate]:
        candidates: list[CleanupCandidate] = []
        seen: set[str] = set()
        for root in self._roots:
            shader_root = root / "steamapps" / "shadercache"
            if shader_root.is_dir() and not shader_root.is_symlink():
                entries = (shader_root / game_id,) if game_id else tuple(shader_root.iterdir())
                for entry in entries:
                    if entry.name.isdigit() and entry.exists() and not entry.is_symlink():
                        candidate = _candidate(entry, "shader-cache", entry.name)
                        if candidate.path not in seen:
                            candidates.append(candidate)
                            seen.add(candidate.path)
            if not game_id:
                dumps = root / "dumps"
                if dumps.is_dir() and not dumps.is_symlink():
                    for entry in dumps.iterdir():
                        if entry.is_file() and not entry.is_symlink():
                            candidate = _candidate(entry, "crash-dumps", None)
                            if candidate.path not in seen:
                                candidates.append(candidate)
                                seen.add(candidate.path)
        return sorted(candidates, key=lambda item: item.path)

    def _validate_candidates(self, candidates: Sequence[CleanupCandidate]) -> None:
        for candidate in candidates:
            source = Path(candidate.path)
            if not any(fs.is_within(root, source) for root in self._roots):
                raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="cache fora da Steam")
            current = _candidate(source, candidate.category, candidate.game_id)
            if current.fingerprint != candidate.fingerprint:
                raise SteamZeroError("E-TX-STALE-PLAN", detail=f"cache mudou: {source.name}")

    def _finish_operation(self, operation: dict[str, Any]) -> None:
        freed = int(operation.get("freedBytes", 0))
        raw_candidates = operation.get("candidates", [])
        if not isinstance(raw_candidates, list):
            raise SteamZeroError("E-STATE-INTEGRITY", detail="operação de limpeza inválida")
        for row in raw_candidates:
            if not isinstance(row, dict) or row.get("state") == "removed":
                continue
            source = Path(str(row["path"]))
            tombstone = Path(str(row["tombstone"]))
            if source.exists() and not tombstone.exists():
                expected = str(row["fingerprint"])
                raw_game_id = row.get("gameId")
                candidate_game_id = str(raw_game_id) if raw_game_id is not None else None
                current = _candidate(source, str(row["category"]), candidate_game_id)
                if current.fingerprint != expected:
                    operation["state"] = "degraded"
                    self._save_operation(operation)
                    raise SteamZeroError(
                        "E-TX-STALE-PLAN", detail=f"cache mudou durante recovery: {source.name}"
                    )
                fs.move_path_atomic(source, tombstone)
                row["state"] = "detached"
                self._save_operation(operation)
            if tombstone.exists() or tombstone.is_symlink():
                fs.remove_path(tombstone)
            row["state"] = "removed"
            freed += int(row["sizeBytes"])
            operation["freedBytes"] = freed
            self._save_operation(operation)
        operation["state"] = "completed"
        self._save_operation(operation)

    @staticmethod
    def _load_plan(plan_id: str) -> dict[str, Any]:
        if not ids.is_ulid(plan_id):
            raise SteamZeroError("E-API-SCHEMA", detail="planId de limpeza inválido")
        path = paths.steam_maintenance_plan_path(plan_id)
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SteamZeroError("E-TX-STALE-PLAN", detail="plano de limpeza ausente") from exc
        if not isinstance(value, dict) or value.get("planId") != plan_id:
            raise SteamZeroError("E-STATE-INTEGRITY", detail="plano de limpeza corrompido")
        return value

    @staticmethod
    def _save_operation(operation: dict[str, Any]) -> None:
        operation_id = str(operation["operationId"])
        fs.write_atomic_text(
            paths.steam_maintenance_operation_path(operation_id),
            json.dumps(operation, sort_keys=True, ensure_ascii=False),
        )

    @staticmethod
    def _recoverable_operations() -> list[dict[str, Any]]:
        directory = paths.steam_maintenance_operations_dir()
        if not directory.is_dir():
            return []
        operations: list[dict[str, Any]] = []
        for path in sorted(directory.glob("*.json")):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(value, dict) and value.get("state") in {"applying", "degraded"}:
                operations.append(value)
        return operations


def _validate_game_id(game_id: str) -> None:
    if game_id and (not game_id.isdigit() or len(game_id) > 32):
        raise SteamZeroError("E-API-SCHEMA", detail="gameId inválido")


def _candidate(path: Path, category: str, game_id: str | None) -> CleanupCandidate:
    if category not in _CATEGORIES or path.is_symlink() or not path.exists():
        raise SteamZeroError("E-TX-STALE-PLAN", detail=f"candidato inválido: {path}")
    digest = hashlib.sha256()
    size = 0
    count = 0
    entries = (path,) if path.is_file() else sorted(path.rglob("*"))
    for entry in entries:
        if entry.is_symlink():
            raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="symlink dentro do cache")
        if not entry.is_file():
            continue
        if count >= _MAX_ENTRIES:
            raise SteamZeroError("E-STORAGE-IO", detail="cache excede limite de entradas")
        metadata = entry.stat()
        relative = entry.name if path.is_file() else str(entry.relative_to(path))
        digest.update(relative.encode("utf-8", errors="surrogateescape"))
        digest.update(f"\0{metadata.st_size}\0{metadata.st_mtime_ns}\n".encode())
        size += metadata.st_size
        count += 1
    return CleanupCandidate(str(path.resolve()), category, game_id, size, count, digest.hexdigest())


def _tombstone(source: Path, operation_id: str) -> Path:
    return source.with_name(f".{source.name}.steamzero-delete-{operation_id}")


def _candidates_from_plan(plan: dict[str, Any]) -> list[CleanupCandidate]:
    raw = plan.get("candidates")
    if not isinstance(raw, list):
        raise SteamZeroError("E-STATE-INTEGRITY", detail="candidatos de limpeza inválidos")
    result: list[CleanupCandidate] = []
    for row in raw:
        if not isinstance(row, dict):
            raise SteamZeroError("E-STATE-INTEGRITY", detail="candidato de limpeza inválido")
        result.append(
            CleanupCandidate(
                path=str(row["path"]),
                category=str(row["category"]),
                game_id=str(row["gameId"]) if row.get("gameId") is not None else None,
                size=int(row["sizeBytes"]),
                entries=int(row["entries"]),
                fingerprint=str(row["fingerprint"]),
            )
        )
    return result


def _public_plan(plan: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in plan.items() if key != "candidates"}


def _public_operation(operation: dict[str, Any]) -> dict[str, Any]:
    return {
        "operationId": operation["operationId"],
        "planId": operation["planId"],
        "status": operation["state"],
        "freedBytes": operation["freedBytes"],
    }
