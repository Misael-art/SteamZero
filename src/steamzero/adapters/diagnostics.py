# SPDX-License-Identifier: GPL-3.0-or-later
"""Read model e exportações sanitizadas para a área Sistema handheld."""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from steamzero.core import journal, paths, transaction
from steamzero.core.errors import SteamZeroError
from steamzero.core.secret import Secret
from steamzero.core.state import StateStore
from steamzero.privileged.client import AdminClient

_SENSITIVE_KEY = re.compile(
    r"(?:token|secret|password|credential|api.?key|email|encrypted|cipher|cookie)", re.I
)
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_ROM_PATH = re.compile(r"(?:^|[/\\])[^\n]*(?:\.nsp|\.xci|\.nsz|\.xcz)\b", re.I)
_TOKEN_IN_TEXT = re.compile(r"(?i)(token|secret|password|api[_-]?key)(\s*[=:]\s*)[^&\s,;]+")
_PERSONAL_KEYS = {
    "author",
    "attribution",
    "dmi_fingerprint",
    "label",
    "owner",
    "profile_owner",
    "steam_user_id",
    "title",
    "gametitle",
}


class DiagnosticsService:
    def __init__(self, store_factory: type[StateStore] | Any = StateStore) -> None:
        self._store_factory = store_factory

    def snapshot(
        self,
        *,
        doctor: dict[str, Any],
        desktop_status: dict[str, Any],
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        operations = self.operations(page=page, page_size=page_size)
        session = _session_state(desktop_status)
        admin = AdminClient.host()
        return {
            "operations": operations,
            "adminHealth": {
                "available": admin.available(),
                "mode": "health-only",
                "detail": (
                    "Helper e transporte Polkit detectados; somente health é allowlisted."
                    if admin.available()
                    else "Helper administrativo não instalado; nenhum comando arbitrário é exposto."
                ),
            },
            "session": session,
            "sessionRecovery": {
                "available": False,
                "reason": "O daemon não publica contrato Desktop seguro para recovery de sessão.",
            },
            "exports": {
                "state": True,
                "supportBundle": True,
                "previewRequired": True,
                "destinationRequired": True,
            },
            "doctor": sanitize_payload(doctor),
        }

    def operations(self, *, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        if page < 1 or not 1 <= page_size <= 100:
            raise SteamZeroError("E-API-SCHEMA", detail="paginação inválida")
        rows: list[dict[str, Any]] = []
        for path in sorted(
            paths.journal_dir().glob("*.jsonl"),
            key=lambda item: item.stat().st_mtime_ns,
            reverse=True,
        ):
            operation_id = path.stem
            try:
                records = journal.read_records(operation_id, path=path)
            except (OSError, json.JSONDecodeError):
                continue
            begin = next(
                (record for record in records if record.get("type") == "operation.begin"), {}
            )
            rolled_back = journal.has_type(records, journal.ROLLBACK)
            committed = journal.has_type(records, journal.COMMIT)
            rows.append(
                {
                    "operationId": operation_id,
                    "operation": str(begin.get("kind") or "unknown"),
                    "state": (
                        "rolled-back" if rolled_back else "committed" if committed else "active"
                    ),
                    "timestamp": begin.get("ts"),
                    "target": _operation_target(records),
                    "rollbackAvailable": committed and not rolled_back,
                }
            )
        start = (page - 1) * page_size
        return {
            "page": page,
            "pageSize": page_size,
            "total": len(rows),
            "items": rows[start : start + page_size],
        }

    @staticmethod
    def admin_health() -> dict[str, Any]:
        client = AdminClient.host()
        if not client.available():
            return {
                "available": False,
                "state": "unavailable",
                "detail": "steamzero-admin/pkexec não estão disponíveis.",
            }
        response = client.request("health", {})
        if response.ok:
            return {"available": True, "state": "healthy", "result": response.result}
        return {"available": True, "state": "failed", "error": response.error}

    def plan_export(
        self,
        destination: Path,
        *,
        kind: str,
        doctor: dict[str, Any],
        desktop_status: dict[str, Any],
    ) -> tuple[transaction.Plan, dict[str, Any]]:
        if kind not in {"state", "support"}:
            raise SteamZeroError("E-API-SCHEMA", detail="tipo de exportação inválido")
        expected_suffix = ".json" if kind == "state" else ".zip"
        if destination.suffix.casefold() != expected_suffix:
            raise SteamZeroError(
                "E-API-SCHEMA", detail=f"destino precisa terminar em {expected_suffix}"
            )
        if destination.is_symlink() or not destination.parent.is_dir():
            raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="destino de exportação inválido")
        payload = self._export_payload(
            doctor=doctor,
            desktop_status=desktop_status,
            include_state_tables=kind == "state",
        )
        _assert_sanitized(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode())
        if kind == "state":
            content = json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2).encode()
            preview = {"files": [destination.name], "content": payload}
        else:
            content, file_preview = _support_zip(payload)
            preview = {"files": file_preview, "content": payload}
        _assert_sanitized(content)
        plan = transaction.plan_write_files(
            {destination: content},
            root=destination.parent,
            kind=f"diagnostics.export.{kind}",
        )
        return plan, preview

    @staticmethod
    def apply_export(plan_id: str, confirm_token: str) -> transaction.ApplyResult:
        plan = transaction.load_plan(plan_id)
        if not plan.kind.startswith("diagnostics.export."):
            raise SteamZeroError("E-TX-STALE-PLAN", detail="plano não exporta diagnóstico")
        return transaction.apply(plan_id, confirm_token)

    def _export_payload(
        self,
        *,
        doctor: dict[str, Any],
        desktop_status: dict[str, Any],
        include_state_tables: bool,
    ) -> dict[str, Any]:
        with self._store_factory() as store:
            store.migrate()
            exported = store.export_json()
        table_counts = {
            name: len(rows)
            for name, rows in exported.get("tables", {}).items()
            if isinstance(name, str) and isinstance(rows, list)
        }
        state: dict[str, Any] = {
            "schemaVersion": exported.get("schemaVersion"),
            "counts": table_counts,
        }
        if include_state_tables:
            state["tables"] = _sanitize_state_tables(exported.get("tables", {}))
        payload = {
            "schemaVersion": 1,
            "generatedAt": datetime.now(UTC).isoformat(),
            "state": state,
            "operations": self.operations(page=1, page_size=100),
            "doctor": sanitize_payload(doctor),
            "session": _session_state(desktop_status),
        }
        sanitized = sanitize_payload(payload)
        if not isinstance(sanitized, dict):
            raise SteamZeroError("E-CONTENT-POLICY", detail="sanitização inválida")
        return sanitized


def sanitize_payload(value: Any) -> Any:
    if isinstance(value, Secret):
        return "[REDACTED]"
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, child in value.items():
            name = str(key)
            normalized = name.casefold()
            if (
                _SENSITIVE_KEY.search(name)
                or normalized in _PERSONAL_KEYS
                or normalized
                in {
                    "rompath",
                    "canonicalpath",
                    "relpath",
                }
            ):
                result[name] = "[REDACTED]"
            elif normalized.endswith("_path") or normalized.endswith("path"):
                result[name] = _redacted_path(child)
            elif normalized.endswith("_json") and isinstance(child, str):
                result[name] = _sanitize_json_text(child)
            else:
                result[name] = sanitize_payload(child)
        return result
    if isinstance(value, (list, tuple)):
        return [sanitize_payload(item) for item in value]
    if isinstance(value, str):
        text = _EMAIL.sub("[REDACTED-EMAIL]", value)
        text = _TOKEN_IN_TEXT.sub(r"\1\2[REDACTED]", text)
        home = str(Path.home())
        if home and home in text:
            text = text.replace(home, "{HOME}")
        username = Path.home().name
        if username and text == username:
            return "[REDACTED-USER]"
        if Path(text).is_absolute() or _ROM_PATH.search(text):
            return "{PATH}/" + hashlib.sha256(text.encode()).hexdigest()[:12]
        return text
    return value


def _sanitize_state_tables(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    sanitized = sanitize_payload(value)
    return sanitized if isinstance(sanitized, dict) else {}


def _sanitize_json_text(value: str) -> str:
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        sanitized = sanitize_payload(value)
        return sanitized if isinstance(sanitized, str) else "[REDACTED]"
    return json.dumps(
        sanitize_payload(decoded),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _redacted_path(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    return "{PATH}/" + hashlib.sha256(text.encode()).hexdigest()[:12]


def _session_state(desktop_status: dict[str, Any]) -> dict[str, Any]:
    context = desktop_status.get("context")
    if not isinstance(context, dict):
        return {"state": "unknown", "type": None, "recoveryRequired": False}
    return {
        "state": "active" if context.get("sessionType") else "unknown",
        "type": context.get("sessionType") or context.get("type"),
        "deviceKind": context.get("deviceKind"),
        "physicalDock": bool(context.get("physicalDock")),
        "recoveryRequired": bool(desktop_status.get("recoveryRequired")),
    }


def _operation_target(records: list[dict[str, Any]]) -> str:
    intent = next((record for record in records if record.get("type") == "action.intent"), None)
    if not isinstance(intent, dict):
        return "nenhum alvo externo"
    undo = intent.get("undo")
    if not isinstance(undo, dict):
        return "alvo sanitizado"
    target = str(undo.get("target") or "")
    if not target:
        return "alvo sanitizado"
    return "arquivo:" + hashlib.sha256(target.encode()).hexdigest()[:12]


def _support_zip(payload: dict[str, Any]) -> tuple[bytes, list[str]]:
    files = {
        "diagnostics.json": json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2),
        "operations.json": json.dumps(
            payload["operations"], sort_keys=True, ensure_ascii=False, indent=2
        ),
    }
    manifest = {
        "schemaVersion": 1,
        "files": [
            {"path": name, "sha256": hashlib.sha256(content.encode()).hexdigest()}
            for name, content in sorted(files.items())
        ],
    }
    files["manifest.json"] = json.dumps(manifest, sort_keys=True, ensure_ascii=False, indent=2)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            archive.writestr(name, content)
    return output.getvalue(), sorted(files)


def _assert_sanitized(content: bytes) -> None:
    if len(content) > 16 * 1024 * 1024:
        raise SteamZeroError("E-CONTENT-LIMIT", detail="exportação excede 16 MiB")
    probes = [str(Path.home()).encode(), Path.home().name.encode()]
    if any(probe and probe in content for probe in probes):
        raise SteamZeroError("E-CONTENT-POLICY", detail="exportação contém dado pessoal")
    lowered = content.lower()
    if b".nsp" in lowered or b".xci" in lowered or b".nsz" in lowered:
        raise SteamZeroError("E-CONTENT-POLICY", detail="exportação contém caminho de ROM")
