# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""WI-1: keys/firmware store — import auditado, cruzamento e SR-14.

Fixtures sintéticas: bytes falsos. Nenhum conteúdo protegido, key ou firmware
real. Verifica que hash completo/nome de key jamais vazam (só hash truncado).
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from steamzero.core import fs, state
from steamzero.core.errors import SteamZeroError
from steamzero.domain.keys_firmware import (
    FirmwareDatabase,
    KeysDatabase,
    KeysFirmwareStore,
    parse_firmware_version,
)

_KEYS_16 = b"synthetic-prod-keys-generation-16"
_KEYS_18 = b"synthetic-prod-keys-generation-18"
_FW_16 = b"synthetic-firmware-16.1.0"
_FW_18 = b"synthetic-firmware-18.0.0"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _keys_db() -> KeysDatabase:
    return KeysDatabase(
        {
            "schemaVersion": 1,
            "platform": "switch",
            "keyset": "prod",
            "entries": [
                {"sha256": _sha(_KEYS_16), "keyRevision": 16, "label": "syn-16"},
                {"sha256": _sha(_KEYS_18), "keyRevision": 18, "label": "syn-18"},
            ],
        }
    )


def _firmware_db() -> FirmwareDatabase:
    return FirmwareDatabase(
        {
            "schemaVersion": 1,
            "platform": "switch",
            "entries": [
                {"version": "16.1.0", "sha256": _sha(_FW_16), "label": "syn-16"},
                {"version": "18.0.0", "sha256": _sha(_FW_18), "label": "syn-18"},
            ],
        }
    )


class _RecordingLogger:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict[str, Any]]] = []

    def info(self, event: str, **fields: Any) -> None:
        self.events.append(("info", event, fields))

    def warning(self, event: str, **fields: Any) -> None:
        self.events.append(("warning", event, fields))

    def error(self, event: str, **fields: Any) -> None:
        self.events.append(("error", event, fields))

    def all_field_values(self) -> list[Any]:
        return [v for _, _, fields in self.events for v in fields.values()]


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[state.StateStore]:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    fs.ensure_state_layout()
    opened = state.open_state()
    opened.save_platform({"id": "switch", "name": "Nintendo Switch"})
    yield opened
    opened.close()


def _write(tmp_path: Path, name: str, data: bytes) -> Path:
    p = tmp_path / name
    p.write_bytes(data)
    return p


# -- importação ------------------------------------------------------------


def test_import_keys_matches_hash_and_derives_revision(
    store: state.StateStore, tmp_path: Path
) -> None:
    ks = KeysFirmwareStore(store, keys_db=_keys_db(), firmware_db=_firmware_db())
    result = ks.import_keys(_write(tmp_path, "prod.keys", _KEYS_18))
    assert result.kind == "key"
    assert result.status == "imported"
    assert result.revision == 18
    assert ks.installed_key_revision("switch") == 18
    items = store.list_firmware_key_items("switch", kind="key")
    assert len(items) == 1 and items[0]["state"] == "present"


def test_import_firmware_matches_hash_and_derives_version(
    store: state.StateStore, tmp_path: Path
) -> None:
    ks = KeysFirmwareStore(store, keys_db=_keys_db(), firmware_db=_firmware_db())
    result = ks.import_firmware(_write(tmp_path, "fw.bin", _FW_18))
    assert result.version == "18.0.0"
    assert ks.installed_firmware_version("switch") == "18.0.0"


def test_reimport_is_idempotent_and_keeps_audit_events(
    store: state.StateStore, tmp_path: Path
) -> None:
    ks = KeysFirmwareStore(store, keys_db=_keys_db(), firmware_db=_firmware_db())
    provided = _write(tmp_path, "prod.keys", _KEYS_18)

    first = ks.import_keys(provided)
    second = ks.import_keys(provided)

    assert first.status == "imported"
    assert second.status == "revalidated"
    assert len(store.list_firmware_key_items("switch", kind="key")) == 1
    import_events = [
        event for event in store.events_since(0) if event["kind"].startswith("key.import")
    ]
    assert [event["kind"] for event in import_events] == [
        "key.import.imported",
        "key.import.revalidated",
    ]


def test_import_unknown_keys_rejected_without_persistence(
    store: state.StateStore, tmp_path: Path
) -> None:
    ks = KeysFirmwareStore(store, keys_db=_keys_db(), firmware_db=_firmware_db())
    with pytest.raises(SteamZeroError) as exc:
        ks.import_keys(_write(tmp_path, "unknown.keys", b"not-a-known-keyset"))
    assert exc.value.code == "E-CONTENT-KEYS-INCOMPAT"
    assert store.list_firmware_key_items("switch", kind="key") == []


def test_import_unknown_firmware_rejected(store: state.StateStore, tmp_path: Path) -> None:
    ks = KeysFirmwareStore(store, keys_db=_keys_db(), firmware_db=_firmware_db())
    with pytest.raises(SteamZeroError) as exc:
        ks.import_firmware(_write(tmp_path, "x.bin", b"unknown-fw"))
    assert exc.value.code == "E-CONTENT-FW-INCOMPAT"


def test_import_degrades_when_db_absent(store: state.StateStore, tmp_path: Path) -> None:
    ks = KeysFirmwareStore(store)  # sem bancos
    with pytest.raises(SteamZeroError) as exc:
        ks.import_keys(_write(tmp_path, "prod.keys", _KEYS_18))
    assert exc.value.code == "E-COMPONENT-DEGRADED"


# -- SR-14: segredo nunca vaza --------------------------------------------


def test_import_never_leaks_full_hash_or_key_name(store: state.StateStore, tmp_path: Path) -> None:
    logger = _RecordingLogger()
    ks = KeysFirmwareStore(store, keys_db=_keys_db(), firmware_db=_firmware_db(), logger=logger)  # type: ignore[arg-type]
    full = _sha(_KEYS_18)
    ks.import_keys(_write(tmp_path, "prod.keys", _KEYS_18))
    # nenhum campo de log carrega o hash completo
    for value in logger.all_field_values():
        assert value != full
        if isinstance(value, str):
            assert full not in value
    # o state guarda só hash truncado (12), nunca o hash completo
    item = store.list_firmware_key_items("switch", kind="key")[0]
    assert len(item["hash_truncated"]) == 12
    assert full.startswith(item["hash_truncated"])
    assert "hash" not in item or item.get("hash") is None


# -- estado instalado (máximos) -------------------------------------------


def test_installed_revision_is_maximum(store: state.StateStore, tmp_path: Path) -> None:
    ks = KeysFirmwareStore(store, keys_db=_keys_db(), firmware_db=_firmware_db())
    ks.import_keys(_write(tmp_path, "k16.keys", _KEYS_16))
    ks.import_keys(_write(tmp_path, "k18.keys", _KEYS_18))
    assert ks.installed_key_revision("switch") == 18


def test_installed_firmware_is_maximum_version(store: state.StateStore, tmp_path: Path) -> None:
    ks = KeysFirmwareStore(store, keys_db=_keys_db(), firmware_db=_firmware_db())
    ks.import_firmware(_write(tmp_path, "f16", _FW_16))
    ks.import_firmware(_write(tmp_path, "f18", _FW_18))
    assert ks.installed_firmware_version("switch") == "18.0.0"


# -- cruzamento pré-execução ----------------------------------------------


def test_check_keys_missing_outdated_ok(store: state.StateStore, tmp_path: Path) -> None:
    ks = KeysFirmwareStore(store, keys_db=_keys_db(), firmware_db=_firmware_db())
    missing = ks.check_key_requirement("switch", minimum_revision=18)
    assert missing.status == "missing" and missing.blocks_play

    ks.import_keys(_write(tmp_path, "k16.keys", _KEYS_16))
    outdated = ks.check_key_requirement("switch", minimum_revision=18)
    assert outdated.status == "outdated" and not outdated.blocks_play
    assert "abaixo do mínimo" in outdated.detail

    ks.import_keys(_write(tmp_path, "k18.keys", _KEYS_18))
    ok = ks.check_key_requirement("switch", minimum_revision=18)
    assert ok.status == "ok"


def test_check_firmware_missing_outdated_ok(store: state.StateStore, tmp_path: Path) -> None:
    ks = KeysFirmwareStore(store, keys_db=_keys_db(), firmware_db=_firmware_db())
    assert ks.check_firmware_requirement("switch", minimum_version="18.0.0").status == "missing"
    ks.import_firmware(_write(tmp_path, "f16", _FW_16))
    outdated = ks.check_firmware_requirement("switch", minimum_version="18.0.0")
    assert outdated.status == "outdated"
    ks.import_firmware(_write(tmp_path, "f18", _FW_18))
    assert ks.check_firmware_requirement("switch", minimum_version="18.0.0").status == "ok"


def test_check_requirement_to_dict_is_deterministic(store: state.StateStore) -> None:
    ks = KeysFirmwareStore(store, keys_db=_keys_db(), firmware_db=_firmware_db())
    payload = ks.check_key_requirement("switch", minimum_revision=None).to_dict()
    assert set(payload) == {"status", "kind", "required", "installed", "detail", "blocksPlay"}


def test_absent_minimum_requirement_is_not_required(store: state.StateStore) -> None:
    ks = KeysFirmwareStore(store, keys_db=_keys_db(), firmware_db=_firmware_db())

    keys = ks.check_key_requirement("switch", minimum_revision=None)
    firmware = ks.check_firmware_requirement("switch", minimum_version=None)

    assert keys.status == "not-required" and not keys.blocks_play
    assert firmware.status == "not-required" and not firmware.blocks_play


def test_parse_firmware_version_rejects_bad_input() -> None:
    assert parse_firmware_version("17.0.1") == (17, 0, 1)
    with pytest.raises(SteamZeroError):
        parse_firmware_version("dev")


# -- linking / path traversal ---------------------------------------------


def test_plan_link_keys_rejects_path_traversal(store: state.StateStore, tmp_path: Path) -> None:
    ks = KeysFirmwareStore(store, keys_db=_keys_db(), firmware_db=_firmware_db())
    ks.import_keys(_write(tmp_path, "prod.keys", _KEYS_18))
    with pytest.raises((SteamZeroError, ValueError)):
        ks.plan_link_keys(
            "switch", consumer_root=tmp_path / "emu", consumer_relpath="../../escape.keys"
        )


def test_plan_link_keys_missing_source_is_reported(store: state.StateStore, tmp_path: Path) -> None:
    ks = KeysFirmwareStore(store, keys_db=_keys_db(), firmware_db=_firmware_db())
    with pytest.raises(SteamZeroError) as exc:
        ks.plan_link_keys("switch", consumer_root=tmp_path / "emu", consumer_relpath="prod.keys")
    assert exc.value.code == "E-CONTENT-KEYS-MISSING"


def test_link_keys_plan_apply_rollback(store: state.StateStore, tmp_path: Path) -> None:
    ks = KeysFirmwareStore(store, keys_db=_keys_db(), firmware_db=_firmware_db())
    ks.import_keys(_write(tmp_path, "prod.keys", _KEYS_18))
    consumer = tmp_path / "emu"
    consumer.mkdir()
    plan = ks.plan_link_keys("switch", consumer_root=consumer, consumer_relpath="prod.keys")
    applied = ks.apply_link(plan.plan_id, plan.confirm_token)
    assert (consumer / "prod.keys").exists()
    ks.rollback_link(applied.operation_id)
    assert not (consumer / "prod.keys").exists()
