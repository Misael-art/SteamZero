from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from steamzero.adapters.desktop_contracts import handheld_ui_contracts
from steamzero.adapters.diagnostics import DiagnosticsService, sanitize_payload
from steamzero.core import fs, transaction
from steamzero.core.errors import SteamZeroError
from steamzero.core.secret import Secret
from steamzero.core.state import StateStore


def _service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[DiagnosticsService, Path]:
    home = tmp_path / "home" / "private-user"
    home.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda _class: home))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    database = tmp_path / "state.db"
    return DiagnosticsService(lambda: StateStore(database)), home


def _doctor(home: Path) -> dict[str, object]:
    return {
        "checks": [
            {
                "name": "rom",
                "status": "warn",
                "message": str(home / "Games" / "Private Game.nsp"),
            }
        ],
        "apiToken": "must-not-leak",
        "owner": "person@example.com",
        "secret": Secret("also-must-not-leak"),
    }


def test_sanitizer_removes_secret_email_home_and_rom_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _service(tmp_path, monkeypatch)
    raw = {
        "token": "abc",
        "nested": {
            "email": "person@example.com",
            "path": str(Path.home() / "Games" / "Private.nsp"),
        },
        "title": "Private Game",
    }
    serialized = json.dumps(sanitize_payload(raw), sort_keys=True)
    assert "abc" not in serialized
    assert "person@example.com" not in serialized
    assert str(Path.home()) not in serialized
    assert "Private.nsp" not in serialized
    assert "Private Game" not in serialized


def test_operations_are_paginated_and_targets_are_hashed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, home = _service(tmp_path, monkeypatch)
    target = home / "Games" / "Private Game.nsp"
    fs.write_atomic(target, b"rom")
    plan = transaction.plan_write_files({target: b"updated"}, root=home, kind="test.private")
    transaction.apply(plan.plan_id, plan.confirm_token)

    history = service.operations(page=1, page_size=1)
    assert history["total"] == 1
    assert history["items"][0]["operation"] == "test.private"
    assert history["items"][0]["state"] == "committed"
    assert history["items"][0]["rollbackAvailable"] is True
    assert str(home) not in json.dumps(history)
    assert "Private Game.nsp" not in json.dumps(history)


def test_state_and_support_exports_require_preview_and_are_sanitized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, home = _service(tmp_path, monkeypatch)
    doctor = _doctor(home)
    desktop = {
        "context": {
            "sessionType": "wayland",
            "deviceKind": "deck-oled",
            "physicalDock": False,
        }
    }
    with StateStore(tmp_path / "state.db") as store:
        store.migrate()
        connection = store.adapter_connection()
        connection.execute(
            "INSERT INTO platform (id, name) VALUES (?, ?)",
            ("switch", "Nintendo Switch"),
        )
        connection.execute(
            "INSERT INTO game (id, platform_id, title, state) VALUES (?, ?, ?, ?)",
            ("private-game", "switch", "Private Game", "ready"),
        )
        connection.execute(
            "INSERT INTO scraping_credential (provider, key_name, value_encrypted) "
            "VALUES (?, ?, ?)",
            ("provider", "api", "encrypted-must-not-leak"),
        )
        connection.execute(
            "INSERT INTO event_log (ts, kind, payload_json) VALUES (?, ?, ?)",
            (
                "2026-07-22T00:00:00+00:00",
                "private",
                json.dumps(
                    {
                        "token": "nested-must-not-leak",
                        "path": str(home / "Games" / "Private Game.nsp"),
                    }
                ),
            ),
        )
    state_target = tmp_path / "chosen" / "state.json"
    state_target.parent.mkdir()
    plan, preview = service.plan_export(
        state_target, kind="state", doctor=doctor, desktop_status=desktop
    )
    assert preview["files"] == ["state.json"]
    preview_text = json.dumps(preview, sort_keys=True, default=str)
    for forbidden in (
        "must-not-leak",
        "also-must-not-leak",
        "person@example.com",
        str(home),
        "Private Game.nsp",
    ):
        assert forbidden not in preview_text
    result = service.apply_export(plan.plan_id, plan.confirm_token)
    assert result.status == "ok"
    state_text = state_target.read_text(encoding="utf-8")
    assert "counts" in state_text
    assert '"tables"' in state_text
    assert '"title": "[REDACTED]"' in state_text
    assert "must-not-leak" not in state_text
    assert "nested-must-not-leak" not in state_text

    support_target = tmp_path / "chosen" / "support.zip"
    support_plan, support_preview = service.plan_export(
        support_target, kind="support", doctor=doctor, desktop_status=desktop
    )
    assert support_preview["files"] == [
        "diagnostics.json",
        "manifest.json",
        "operations.json",
    ]
    service.apply_export(support_plan.plan_id, support_plan.confirm_token)
    with zipfile.ZipFile(support_target) as archive:
        names = sorted(archive.namelist())
        bundle = b"".join(archive.read(name) for name in names)
    assert names == support_preview["files"]
    assert b'"tables"' not in bundle
    for forbidden in (
        b"must-not-leak",
        b"also-must-not-leak",
        b"person@example.com",
        str(home).encode(),
        b"Private Game.nsp",
    ):
        assert forbidden not in bundle


def test_export_rejects_symlink_destination_and_contracts_expose_no_shell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _home = _service(tmp_path, monkeypatch)
    real = tmp_path / "real.json"
    real.write_text("existing", encoding="utf-8")
    link = tmp_path / "export.json"
    link.symlink_to(real)
    with pytest.raises(SteamZeroError) as error:
        service.plan_export(link, kind="state", doctor={}, desktop_status={})
    assert error.value.code == "E-CONTENT-UNSAFE-PATH"

    contracts = handheld_ui_contracts()["byId"]
    assert contracts["admin.health"]["endpoint"] == "/system/admin/health"
    assert contracts["admin.health"]["inputSchema"]["additionalProperties"] is False
    assert contracts["session.recovery"]["enabled"] is False
    assert all(
        "command" not in action["inputSchema"]["properties"] for action in contracts.values()
    )
