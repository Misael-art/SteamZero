# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Histórico operacional limitado e rollback contextual confirmado."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from steamzero.api import contracts
from steamzero.core import fs, ids, journal, paths, transaction
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore

StoreFactory = Callable[[], StateStore]
ComponentRollback = Callable[[str], Any]

_SCHEMA = "feat-operation-history-v1.schema.json"
_MAX_JOURNAL_BYTES = 4 * 1024 * 1024
_MAX_RECORDS = 4096
_MAX_LEGACY_INDEX = 1000
_PLAN_TTL = 3600
_GENERIC_ROUTE = "transaction"
_COMPONENT_ROUTE = "component-flatpak"

_TITLES = {
    "bios.link": "Vínculos de BIOS",
    "component.lsfg.install": "Instalação do LSFG-VK",
    "emulator.config": "Configuração de emulador",
    "keys.link": "Vínculos de keys",
    "library.convert": "Conversão de jogo",
    "library.organize": "Organização da biblioteca",
    "media.reconcile": "Organização de mídia",
    "steam.media-package": "Arte da biblioteca Steam",
    "steam.cloud-shortcuts.sync": "Atalhos cloud na Steam",
    "steam.shortcuts.sync": "Atalhos não-Steam",
    "switch-library.quarantine": "Quarentena da biblioteca Switch",
    "switch-library.rename": "Organização da biblioteca Switch",
}


def _now() -> datetime:
    return datetime.now(UTC)


def _title(kind: str) -> str:
    if kind in _TITLES:
        return _TITLES[kind]
    prefixes = (
        ("component.", "Componente"),
        ("collections.", "Coleções e favoritos"),
        ("bitrot.", "Saúde da coleção"),
        ("diagnostics.export.", "Exportação de diagnóstico"),
        ("emulation.game-delete:", "Exclusão de jogo"),
        ("emulation.", "Emulação"),
        ("input-profile.activate:", "Perfil de controle"),
        ("input-profile.clear:", "Perfil de controle"),
        ("media.", "Mídia"),
        ("preservation.", "Restauração de preservação"),
        ("saves.restore", "Restauração de save"),
        ("steam.launch-options.configure:", "Opções de lançamento Steam"),
        ("steam.gameplay-profile:", "Perfil de gameplay Steam"),
        ("switch-content.", "Conteúdo Switch"),
    )
    return next((label for prefix, label in prefixes if kind.startswith(prefix)), "Operação")


def _target(records: list[dict[str, Any]]) -> str:
    intent = next((item for item in records if item.get("type") == "action.intent"), None)
    undo = intent.get("undo") if isinstance(intent, dict) else None
    raw = undo.get("target") if isinstance(undo, dict) else None
    if not isinstance(raw, str) or not raw:
        return "nenhum alvo externo"
    return "arquivo:" + hashlib.sha256(raw.encode()).hexdigest()[:12]


def _fingerprint(path: Path, state: str) -> str:
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise SteamZeroError(
            "E-STATE-INTEGRITY", detail="evidência da operação indisponível"
        ) from exc
    return hashlib.sha256(state.encode() + b"\0" + content).hexdigest()


def _safe_file(path: Path, expected: Path, *, maximum: int) -> None:
    if path != expected or path.is_symlink() or not path.is_file():
        raise SteamZeroError("E-STATE-INTEGRITY", detail="evidência operacional insegura")
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise SteamZeroError("E-STATE-INTEGRITY", detail="evidência operacional ilegível") from exc
    if size > maximum:
        raise SteamZeroError("E-CONTENT-LIMIT", detail="evidência operacional excede o limite")


def _read_journal(operation_id: str, path: Path) -> list[dict[str, Any]]:
    _safe_file(path, paths.journal_path(operation_id), maximum=_MAX_JOURNAL_BYTES)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > _MAX_RECORDS:
            raise SteamZeroError("E-CONTENT-LIMIT", detail="journal excede o limite de registros")
        records = [json.loads(line) for line in lines if line.strip()]
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SteamZeroError("E-STATE-INTEGRITY", detail="journal operacional corrompido") from exc
    if not all(isinstance(item, dict) for item in records):
        raise SteamZeroError("E-STATE-INTEGRITY", detail="journal operacional inválido")
    for index, record in enumerate(records):
        if record.get("seq") != index or record.get("operationId") != operation_id:
            raise SteamZeroError("E-STATE-INTEGRITY", detail="sequência do journal inválida")
    return records


def _transaction_context(
    operation_id: str, path: Path, state: str
) -> tuple[str, str | None, str, list[dict[str, Any]]]:
    records = _read_journal(operation_id, path)
    begins = [item for item in records if item.get("type") == "operation.begin"]
    if len(begins) != 1:
        raise SteamZeroError("E-STATE-INTEGRITY", detail="início da operação inválido")
    begin = begins[0]
    kind = begin.get("kind")
    plan_id = begin.get("planId")
    if not isinstance(kind, str) or not kind or not isinstance(plan_id, str):
        raise SteamZeroError("E-STATE-INTEGRITY", detail="contexto da operação inválido")
    actual = (
        "rolled-back"
        if journal.has_type(records, journal.ROLLBACK)
        else "committed"
        if journal.has_type(records, journal.COMMIT)
        else "active"
    )
    if state in {"committed", "rolled-back"} and actual != state:
        raise SteamZeroError("E-STATE-INTEGRITY", detail="StateStore e journal divergem")
    timestamp = begin.get("ts")
    return kind, timestamp if isinstance(timestamp, str) else None, actual, records


def _validate_transaction_plan(
    operation_id: str, kind: str, records: list[dict[str, Any]]
) -> transaction.Plan:
    begin = next(item for item in records if item.get("type") == "operation.begin")
    plan_id = str(begin["planId"])
    if not ids.is_ulid(plan_id):
        raise SteamZeroError("E-STATE-INTEGRITY", detail="planId do journal inválido")
    plan_path = paths.plan_path(plan_id)
    _safe_file(plan_path, paths.plan_path(plan_id), maximum=_MAX_JOURNAL_BYTES)
    try:
        plan = transaction.load_plan(plan_id)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SteamZeroError("E-STATE-INTEGRITY", detail="plano original corrompido") from exc
    if plan.kind != kind or plan.status != "applied":
        raise SteamZeroError("E-TX-STALE-PLAN", detail="plano original não confirma a operação")
    actions = {item.action_id: item for item in plan.actions}
    intents = [item for item in records if item.get("type") == "action.intent"]
    if len(intents) > len(actions):
        raise SteamZeroError("E-STATE-INTEGRITY", detail="journal contém ações excedentes")
    seen: set[str] = set()
    for intent in intents:
        action_id = intent.get("actionId")
        undo = intent.get("undo")
        if (
            not isinstance(action_id, str)
            or action_id in seen
            or action_id not in actions
            or not isinstance(undo, dict)
        ):
            raise SteamZeroError("E-STATE-INTEGRITY", detail="intent de rollback inválido")
        seen.add(action_id)
        action = actions[action_id]
        if undo.get("target") != action.target:
            raise SteamZeroError("E-STATE-INTEGRITY", detail="alvo do rollback diverge do plano")
        if action.kind == "move":
            if undo.get("op") != "move-restore" or undo.get("source") != action.source:
                raise SteamZeroError("E-STATE-INTEGRITY", detail="movimento do rollback inválido")
        elif undo.get("op") not in {"restore", "restore-symlink", "delete"}:
            raise SteamZeroError("E-STATE-INTEGRITY", detail="ação de rollback inválida")
        backup_rel = undo.get("backupRel")
        if backup_rel not in {None, action_id}:
            raise SteamZeroError("E-STATE-INTEGRITY", detail="backup do rollback inválido")
    return plan


def _validate_current_transaction_state(plan: transaction.Plan) -> None:
    """Confirma que nenhum alvo mudou depois do commit que será desfeito."""
    for action in plan.actions:
        target = Path(action.target)
        if action.kind == "delete":
            valid = not target.exists() and not target.is_symlink()
        elif action.kind == "symlink":
            valid = (
                action.source is not None
                and target.is_symlink()
                and Path(os.path.realpath(target)) == Path(os.path.realpath(action.source))
                and Path(action.source).is_file()
                and fs.hash_file(Path(action.source)) == action.new_hash
            )
        else:
            valid = (
                target.is_file()
                and not target.is_symlink()
                and fs.hash_file(target) == action.new_hash
            )
        if action.kind == "move" and action.source is not None:
            valid = valid and not Path(action.source).exists()
        if not valid:
            raise SteamZeroError(
                "E-TX-STALE-PLAN",
                detail="alvo mudou depois da operação; rollback recusado",
            )


class OperationHistory:
    """Projeta operações persistidas e executa apenas rollback previamente revisado."""

    def __init__(
        self,
        store_factory: StoreFactory = StateStore,
        *,
        component_rollback: ComponentRollback | None = None,
    ) -> None:
        self._store_factory = store_factory
        self._component_rollback = component_rollback

    def list(self, *, limit: int = 20, cursor: str | None = None) -> dict[str, Any]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise SteamZeroError("E-API-SCHEMA", detail="limit deve estar entre 1 e 100")
        if cursor is not None and not ids.is_ulid(cursor):
            raise SteamZeroError("E-API-SCHEMA", detail="cursor de operações inválido")
        self._reconcile_if_empty()
        with self._store_factory() as store:
            store.migrate()
            rows, has_more = store.list_operations_page(limit=limit, before_id=cursor)
        items = [self._item(row) for row in rows]
        payload = {
            "schemaVersion": 1,
            "generatedAt": _now().isoformat(),
            "items": items,
            "page": {
                "limit": limit,
                "hasMore": has_more,
                "nextCursor": items[-1]["operationId"] if has_more and items else None,
            },
        }
        contracts.validate(payload, _SCHEMA)
        return payload

    def _reconcile_if_empty(self) -> None:
        """Indexa journals legados uma única vez quando o store ainda está vazio."""
        with self._store_factory() as store:
            store.migrate()
            if store.count_operations():
                return
            directory = paths.journal_dir()
            try:
                entries = os.scandir(directory)
            except FileNotFoundError:
                return
            with entries:
                for index, entry in enumerate(entries):
                    if index >= _MAX_LEGACY_INDEX:
                        break
                    if (
                        not entry.name.endswith(".jsonl")
                        or entry.is_symlink()
                        or not entry.is_file(follow_symlinks=False)
                    ):
                        continue
                    operation_id = entry.name.removesuffix(".jsonl")
                    if not ids.is_ulid(operation_id):
                        continue
                    path = directory / entry.name
                    try:
                        _kind, _timestamp, state, _records = _transaction_context(
                            operation_id, path, "legacy"
                        )
                    except SteamZeroError:
                        continue
                    store.save_operation(
                        operation_id,
                        journal_path=str(path),
                        state=state,
                        backup_path=str(paths.backup_for(operation_id)),
                    )

    def page(self, *, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        if page < 1 or page > 100 or not 1 <= page_size <= 100:
            raise SteamZeroError("E-API-SCHEMA", detail="paginação inválida")
        cursor: str | None = None
        result: dict[str, Any] = {}
        for index in range(page):
            result = self.list(limit=page_size, cursor=cursor)
            next_cursor = result["page"]["nextCursor"]
            if index == page - 1:
                break
            if next_cursor is None:
                result = {
                    **result,
                    "items": [],
                    "page": {
                        "limit": page_size,
                        "hasMore": False,
                        "nextCursor": None,
                    },
                }
                break
            cursor = next_cursor
        with self._store_factory() as store:
            store.migrate()
            total = store.count_operations()
        return {
            "schemaVersion": 1,
            "generatedAt": result["generatedAt"],
            "page": page,
            "pageSize": page_size,
            "total": total,
            "hasMore": result["page"]["hasMore"],
            "nextCursor": result["page"]["nextCursor"],
            "items": result["items"],
        }

    def get(self, operation_id: str) -> dict[str, Any]:
        row = self._row(operation_id)
        payload = {
            "schemaVersion": 1,
            "generatedAt": _now().isoformat(),
            "operation": self._item(row),
        }
        contracts.validate(payload, _SCHEMA)
        return payload

    def plan_rollback(self, operation_id: str) -> dict[str, Any]:
        row = self._row(operation_id)
        item = self._item(row)
        rollback = item["rollback"]
        if not rollback["available"]:
            raise SteamZeroError("E-TX-STALE-PLAN", detail=str(rollback["reason"]))
        evidence_path = Path(str(row["journal_path"]))
        if rollback["route"] == _GENERIC_ROUTE:
            original_plan = _validate_transaction_plan(
                operation_id,
                str(item["kind"]),
                _read_journal(operation_id, evidence_path),
            )
            _validate_current_transaction_state(original_plan)
        plan_id = ids.new_ulid()
        created = _now()
        stored = {
            "schemaVersion": 1,
            "type": "operation-rollback",
            "planId": plan_id,
            "confirmToken": secrets.token_urlsafe(24),
            "operationId": operation_id,
            "operationKind": item["kind"],
            "route": rollback["route"],
            "evidenceFingerprint": _fingerprint(evidence_path, str(row["state"])),
            "createdAt": created.isoformat(),
            "expiresAt": (created + timedelta(seconds=_PLAN_TTL)).isoformat(),
            "status": "pending",
        }
        fs.ensure_dir(paths.plans_dir())
        fs.write_atomic_text(
            paths.plan_path(plan_id),
            json.dumps(stored, sort_keys=True, ensure_ascii=False),
        )
        payload = {
            "schemaVersion": 1,
            "generatedAt": created.isoformat(),
            "plan": {
                "planId": plan_id,
                "confirmToken": stored["confirmToken"],
                "operationId": operation_id,
                "kind": item["kind"],
                "title": item["title"],
                "target": item["target"],
                "changeCount": item["changeCount"],
                "rollbackGuarantee": rollback["guarantee"],
                "expiresAt": stored["expiresAt"],
            },
        }
        contracts.validate(payload, _SCHEMA)
        return payload

    def apply_rollback(self, plan_id: str, confirm_token: str) -> dict[str, Any]:
        plan = self._load_rollback_plan(plan_id)
        if plan["status"] != "pending":
            raise SteamZeroError("E-TX-STALE-PLAN", detail="plano de rollback já consumido")
        if not secrets.compare_digest(str(plan["confirmToken"]), confirm_token):
            raise SteamZeroError(
                "E-TX-CONFIRM-REQUIRED", detail="confirmToken ausente ou incorreto"
            )
        if _now() > datetime.fromisoformat(str(plan["expiresAt"])):
            raise SteamZeroError("E-TX-CONFIRM-REQUIRED", detail="confirmToken expirado")
        operation_id = str(plan["operationId"])
        row = self._row(operation_id)
        if row["state"] != "committed":
            raise SteamZeroError("E-TX-STALE-PLAN", detail="operação não está mais commitada")
        evidence_path = Path(str(row["journal_path"]))
        if not secrets.compare_digest(
            str(plan["evidenceFingerprint"]),
            _fingerprint(evidence_path, str(row["state"])),
        ):
            raise SteamZeroError("E-TX-STALE-PLAN", detail="evidência mudou após a revisão")
        route = str(plan["route"])
        if route == _GENERIC_ROUTE:
            records = _read_journal(operation_id, evidence_path)
            original_plan = _validate_transaction_plan(
                operation_id, str(plan["operationKind"]), records
            )
            _validate_current_transaction_state(original_plan)
            result = transaction.rollback(operation_id, reason="operation-history-confirmed")
            status = result.status
            restored = len(result.restored)
        elif route == _COMPONENT_ROUTE and self._component_rollback is not None:
            result = self._component_rollback(operation_id)
            status = str(getattr(result, "status", None) or result.get("status"))
            restored = 1
        else:
            raise SteamZeroError("E-TX-STALE-PLAN", detail="rota de rollback indisponível")
        with self._store_factory() as store:
            store.migrate()
            final = store.get_operation(operation_id)
        if final is None or final["state"] != "rolled-back":
            raise SteamZeroError(
                "E-TX-ROLLBACK-FAILED",
                operation_id=operation_id,
                detail="estado final do rollback não foi confirmado",
            )
        plan["status"] = "applied"
        fs.write_atomic_text(
            paths.plan_path(plan_id),
            json.dumps(plan, sort_keys=True, ensure_ascii=False),
        )
        payload = {
            "schemaVersion": 1,
            "generatedAt": _now().isoformat(),
            "result": {
                "operationId": operation_id,
                "status": status,
                "restoredCount": restored,
                "verified": True,
            },
        }
        contracts.validate(payload, _SCHEMA)
        return payload

    def _row(self, operation_id: str) -> dict[str, Any]:
        if not ids.is_ulid(operation_id):
            raise SteamZeroError("E-API-SCHEMA", detail="operationId inválido")
        with self._store_factory() as store:
            store.migrate()
            row = store.get_operation(operation_id)
        if row is None:
            raise SteamZeroError("E-API-SCHEMA", detail="operação inexistente")
        return row

    def _item(self, row: dict[str, Any]) -> dict[str, Any]:
        operation_id = str(row["id"])
        state = str(row["state"])
        path = Path(str(row.get("journal_path") or ""))
        try:
            if path.suffix == ".jsonl":
                kind, timestamp, actual, records = _transaction_context(operation_id, path, state)
                change_count = sum(item.get("type") == "action.intent" for item in records)
                route = _GENERIC_ROUTE
                target = _target(records)
                effective_state = actual
            elif path.suffix == ".json":
                _safe_file(
                    path,
                    paths.component_operation_path(operation_id),
                    maximum=_MAX_JOURNAL_BYTES,
                )
                raw = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(raw, dict) or raw.get("operationId") != operation_id:
                    raise SteamZeroError("E-STATE-INTEGRITY", detail="operação Flatpak inválida")
                kind = f"component.flatpak:{raw.get('adapterId', 'unknown')}"
                timestamp = raw.get("startedAt") if isinstance(raw.get("startedAt"), str) else None
                change_count = 1
                route = _COMPONENT_ROUTE
                target = (
                    "deployment:"
                    + hashlib.sha256(str(raw.get("ref", "")).encode()).hexdigest()[:12]
                )
                effective_state = str(raw.get("status", state))
                if effective_state != state:
                    raise SteamZeroError(
                        "E-STATE-INTEGRITY", detail="StateStore e operação Flatpak divergem"
                    )
            else:
                raise SteamZeroError(
                    "E-STATE-INTEGRITY", detail="formato de evidência desconhecido"
                )
            available = effective_state == "committed" and (
                route == _GENERIC_ROUTE or self._component_rollback is not None
            )
            reason = (
                ""
                if available
                else "A operação já foi desfeita."
                if effective_state == "rolled-back"
                else "Rollback indisponível neste contexto."
            )
        except (OSError, UnicodeError, json.JSONDecodeError, SteamZeroError) as exc:
            kind = "unknown"
            timestamp = None
            change_count = 0
            route = "unavailable"
            target = "alvo indisponível"
            effective_state = "invalid"
            available = False
            reason = f"Evidência inválida: {getattr(exc, 'code', 'E-STATE-INTEGRITY')}"
        return {
            "operationId": operation_id,
            "kind": kind,
            "title": _title(kind),
            "state": effective_state,
            "timestamp": timestamp,
            "target": target,
            "changeCount": change_count,
            "rollback": {
                "available": available,
                "guarantee": "G-DEPLOYMENT" if route == _COMPONENT_ROUTE else "G-FULL",
                "route": route,
                "reason": reason,
            },
        }

    @staticmethod
    def _load_rollback_plan(plan_id: str) -> dict[str, Any]:
        if not ids.is_ulid(plan_id):
            raise SteamZeroError("E-TX-STALE-PLAN", detail="planId inválido")
        path = paths.plan_path(plan_id)
        _safe_file(path, paths.plan_path(plan_id), maximum=64 * 1024)
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise SteamZeroError(
                "E-STATE-INTEGRITY", detail="plano de rollback corrompido"
            ) from exc
        required = {
            "schemaVersion",
            "type",
            "planId",
            "confirmToken",
            "operationId",
            "operationKind",
            "route",
            "evidenceFingerprint",
            "createdAt",
            "expiresAt",
            "status",
        }
        if (
            not isinstance(value, dict)
            or set(value) != required
            or value.get("schemaVersion") != 1
            or value.get("type") != "operation-rollback"
            or value.get("planId") != plan_id
            or value.get("route") not in {_GENERIC_ROUTE, _COMPONENT_ROUTE}
            or value.get("status") not in {"pending", "applied"}
        ):
            raise SteamZeroError("E-STATE-INTEGRITY", detail="plano de rollback inválido")
        return value
