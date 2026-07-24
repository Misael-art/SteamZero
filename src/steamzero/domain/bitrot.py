# SPDX-License-Identifier: GPL-3.0-or-later
"""Amostragem anti-bitrot limitada e estritamente somente leitura."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from steamzero.api import contracts
from steamzero.core import fs, paths
from steamzero.core.errors import SteamZeroError

_SCHEMA = "feat-bitrot-v1.schema.json"
_MAX_STATE_BYTES = 2 * 1024 * 1024
_MAX_ITEMS = 10_000
_CHUNK = 1024 * 1024


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class BitrotTarget:
    asset_id: str
    title: str
    platform_id: str
    path: Path
    size: int

    def __post_init__(self) -> None:
        if (
            not self.asset_id
            or len(self.asset_id) > 160
            or "\x00" in self.asset_id
            or not self.title
            or len(self.title) > 240
            or not self.platform_id
            or len(self.platform_id) > 96
            or self.size < 0
        ):
            raise ValueError("alvo anti-bitrot inválido")


class _BudgetReached(Exception):
    pass


class BitrotManager:
    """Mantém baselines locais sem persistir caminhos absolutos."""

    def __init__(
        self,
        path: Path | None = None,
        *,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._path = path or paths.bitrot_state_path()
        self._monotonic = monotonic

    def status(
        self,
        targets: Sequence[BitrotTarget] = (),
        *,
        active_jobs: Sequence[dict[str, Any]] = (),
    ) -> dict[str, Any]:
        document = self._load()
        current = {target.asset_id: target for target in targets}
        items = []
        for asset_id, record in sorted(document["items"].items()):
            target = current.get(asset_id)
            state = str(record["state"])
            if target is None and state != "suspect":
                state = "unavailable"
            items.append(
                {
                    "assetId": asset_id,
                    "title": target.title if target is not None else str(record["title"]),
                    "platformId": (
                        target.platform_id if target is not None else str(record["platformId"])
                    ),
                    "state": state,
                    "size": target.size if target is not None else int(record["size"]),
                    "checkedAt": record["checkedAt"],
                    "reason": str(record["reason"]),
                }
            )
        counts = {
            state: sum(item["state"] == state for item in items)
            for state in ("verified", "suspect", "missing", "error", "unavailable")
        }
        known = set(document["items"])
        counts["unchecked"] = sum(target.asset_id not in known for target in targets)
        overall = (
            "suspect"
            if counts["suspect"] or counts["missing"] or counts["error"]
            else "unchecked"
            if counts["unchecked"] or not items
            else "healthy"
        )
        payload = {
            "schemaVersion": 1,
            "generatedAt": _now(),
            "state": overall,
            "lastRun": document["lastRun"],
            "counts": counts,
            "items": items[:200],
            "activeJobs": list(active_jobs)[:16],
            "limits": dict(document["lastLimits"]),
        }
        contracts.validate(payload, _SCHEMA)
        return payload

    def verify_sample(
        self,
        targets: Sequence[BitrotTarget],
        *,
        max_files: int = 8,
        max_bytes: int = 2 * 1024**3,
        max_seconds: float = 20.0,
        safepoint: Callable[[], None] | None = None,
        progress: Callable[[int, int, str], None] | None = None,
    ) -> dict[str, Any]:
        if not 1 <= max_files <= 64:
            raise SteamZeroError("E-API-SCHEMA", detail="maxFiles deve estar entre 1 e 64")
        if not 1024 <= max_bytes <= 16 * 1024**3:
            raise SteamZeroError("E-API-SCHEMA", detail="maxBytes fora do limite")
        if not 0.1 <= max_seconds <= 120:
            raise SteamZeroError("E-API-SCHEMA", detail="maxSeconds fora do limite")
        document = self._load()
        started_at = _now()
        started = self._monotonic()
        candidates = self._candidates(targets, cast(dict[str, Any], document["items"]))
        selected: list[BitrotTarget] = []
        selected_bytes = 0
        for target in candidates:
            if len(selected) >= max_files:
                break
            if target.size > max_bytes - selected_bytes:
                continue
            selected.append(target)
            selected_bytes += target.size

        checked = 0
        bytes_read = 0
        suspect = 0
        for target in selected:
            if safepoint is not None:
                safepoint()
            if self._monotonic() - started >= max_seconds:
                break
            if progress is not None:
                progress(checked, len(selected), target.title)
            record, consumed = self._verify_one(
                target,
                document["items"].get(target.asset_id),
                deadline=started + max_seconds,
                safepoint=safepoint,
            )
            if record is None:
                break
            document["items"][target.asset_id] = record
            checked += 1
            bytes_read += consumed
            suspect += record["state"] in {"suspect", "missing", "error"}

        finished_at = _now()
        document["revision"] += 1
        document["lastRun"] = {
            "startedAt": started_at,
            "finishedAt": finished_at,
            "checked": checked,
            "bytesRead": bytes_read,
            "suspect": suspect,
            "limited": checked < len(candidates),
        }
        document["lastLimits"] = {
            "maxFiles": max_files,
            "maxBytes": max_bytes,
            "maxSeconds": max_seconds,
        }
        self._save(document)
        if progress is not None:
            progress(checked, len(selected), "")
        return {
            "checked": checked,
            "bytesRead": bytes_read,
            "suspect": suspect,
            "limited": checked < len(candidates),
            "finishedAt": finished_at,
        }

    @staticmethod
    def _candidates(targets: Sequence[BitrotTarget], records: dict[str, Any]) -> list[BitrotTarget]:
        unique = {target.asset_id: target for target in targets}

        def key(target: BitrotTarget) -> tuple[int, str, str]:
            record = records.get(target.asset_id, {})
            state = record.get("state", "unchecked")
            priority = 0 if state in {"suspect", "missing", "error"} else 1
            return priority, str(record.get("checkedAt") or ""), target.asset_id

        return sorted(unique.values(), key=key)

    def _verify_one(
        self,
        target: BitrotTarget,
        previous: Any,
        *,
        deadline: float,
        safepoint: Callable[[], None] | None,
    ) -> tuple[dict[str, Any] | None, int]:
        checked_at = _now()
        try:
            digest, consumed = self._hash_limited(
                target.path, deadline=deadline, safepoint=safepoint
            )
        except _BudgetReached:
            return None, 0
        except FileNotFoundError:
            return self._record(target, previous, "missing", None, checked_at), 0
        except (OSError, SteamZeroError):
            return self._record(target, previous, "error", None, checked_at), 0
        expected = previous.get("expectedSha256") if isinstance(previous, dict) else None
        state = "verified" if expected in {None, digest} else "suspect"
        return self._record(target, previous, state, digest, checked_at), consumed

    @staticmethod
    def _record(
        target: BitrotTarget,
        previous: Any,
        state: str,
        observed: str | None,
        checked_at: str,
    ) -> dict[str, Any]:
        expected = previous.get("expectedSha256") if isinstance(previous, dict) else None
        if expected is None and observed is not None:
            expected = observed
        reason = {
            "verified": "Hash confere com a baseline local.",
            "suspect": "Hash diverge da baseline; o arquivo não foi alterado.",
            "missing": "Arquivo não está disponível no caminho catalogado.",
            "error": "Não foi possível ler o arquivo com segurança.",
        }[state]
        return {
            "expectedSha256": expected,
            "observedSha256": observed,
            "state": state,
            "checkedAt": checked_at,
            "size": target.size,
            "title": target.title,
            "platformId": target.platform_id,
            "pathFingerprint": hashlib.sha256(str(target.path).encode()).hexdigest(),
            "reason": reason,
        }

    def _hash_limited(
        self,
        path: Path,
        *,
        deadline: float,
        safepoint: Callable[[], None] | None,
    ) -> tuple[str, int]:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        consumed = 0
        digest = hashlib.sha256()
        try:
            metadata = os.fstat(fd)
            if not stat.S_ISREG(metadata.st_mode):
                raise SteamZeroError(
                    "E-CONTENT-UNSAFE-PATH", detail="anti-bitrot exige arquivo regular"
                )
            while chunk := os.read(fd, _CHUNK):
                if safepoint is not None:
                    safepoint()
                if self._monotonic() >= deadline:
                    raise _BudgetReached
                digest.update(chunk)
                consumed += len(chunk)
        finally:
            os.close(fd)
        return digest.hexdigest(), consumed

    def _load(self) -> dict[str, Any]:
        empty = {
            "schemaVersion": 1,
            "revision": 0,
            "lastRun": None,
            "lastLimits": {"maxFiles": 8, "maxBytes": 2 * 1024**3, "maxSeconds": 20.0},
            "items": {},
        }
        if not self._path.exists():
            return empty
        if self._path.is_symlink() or not self._path.is_file():
            raise SteamZeroError("E-STATE-INTEGRITY", detail="estado anti-bitrot inseguro")
        try:
            if self._path.stat().st_size > _MAX_STATE_BYTES:
                raise SteamZeroError("E-CONTENT-LIMIT", detail="estado anti-bitrot excede 2 MiB")
            value = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise SteamZeroError(
                "E-STATE-INTEGRITY", detail="estado anti-bitrot corrompido"
            ) from exc
        self._validate_document(value)
        return cast(dict[str, Any], value)

    def _save(self, document: dict[str, Any]) -> None:
        self._validate_document(document)
        content = (
            json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        ).encode()
        if len(content) > _MAX_STATE_BYTES:
            raise SteamZeroError("E-CONTENT-LIMIT", detail="estado anti-bitrot excede 2 MiB")
        if self._path.exists() and self._path.is_symlink():
            raise SteamZeroError("E-STATE-INTEGRITY", detail="estado anti-bitrot inseguro")
        fs.write_atomic(self._path, content)

    @staticmethod
    def _validate_document(value: Any) -> None:
        if not isinstance(value, dict) or set(value) != {
            "schemaVersion",
            "revision",
            "lastRun",
            "lastLimits",
            "items",
        }:
            raise SteamZeroError("E-STATE-INTEGRITY", detail="documento anti-bitrot inválido")
        limits = value.get("lastLimits")
        last_run = value.get("lastRun")
        if (
            value["schemaVersion"] != 1
            or not isinstance(value["revision"], int)
            or value["revision"] < 0
            or not isinstance(limits, dict)
            or set(limits) != {"maxFiles", "maxBytes", "maxSeconds"}
            or not isinstance(limits["maxFiles"], int)
            or not isinstance(limits["maxBytes"], int)
            or not isinstance(limits["maxSeconds"], int | float)
            or not isinstance(value["items"], dict)
            or len(value["items"]) > _MAX_ITEMS
        ):
            raise SteamZeroError("E-STATE-INTEGRITY", detail="estado anti-bitrot inválido")
        if last_run is not None and (
            not isinstance(last_run, dict)
            or set(last_run)
            != {"startedAt", "finishedAt", "checked", "bytesRead", "suspect", "limited"}
            or not isinstance(last_run["startedAt"], str)
            or not isinstance(last_run["finishedAt"], str)
            or not isinstance(last_run["checked"], int)
            or not isinstance(last_run["bytesRead"], int)
            or not isinstance(last_run["suspect"], int)
            or not isinstance(last_run["limited"], bool)
        ):
            raise SteamZeroError("E-STATE-INTEGRITY", detail="execução anti-bitrot inválida")
        for asset_id, record in value["items"].items():
            if (
                not isinstance(asset_id, str)
                or not asset_id
                or len(asset_id) > 160
                or not isinstance(record, dict)
                or set(record)
                != {
                    "expectedSha256",
                    "observedSha256",
                    "state",
                    "checkedAt",
                    "size",
                    "title",
                    "platformId",
                    "pathFingerprint",
                    "reason",
                }
                or record.get("state") not in {"verified", "suspect", "missing", "error"}
                or not isinstance(record.get("title"), str)
                or not isinstance(record.get("platformId"), str)
                or not isinstance(record.get("size"), int)
                or not isinstance(record.get("checkedAt"), str)
                or not isinstance(record.get("reason"), str)
                or not isinstance(record.get("pathFingerprint"), str)
                or len(record["pathFingerprint"]) != 64
                or (
                    record.get("expectedSha256") is not None
                    and (
                        not isinstance(record["expectedSha256"], str)
                        or len(record["expectedSha256"]) != 64
                    )
                )
                or (
                    record.get("observedSha256") is not None
                    and (
                        not isinstance(record["observedSha256"], str)
                        or len(record["observedSha256"]) != 64
                    )
                )
            ):
                raise SteamZeroError("E-STATE-INTEGRITY", detail="item anti-bitrot inválido")
