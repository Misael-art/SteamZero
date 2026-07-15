# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Testes do BIOS store (F-BI-01/03, AC-BI-01/02, CONTENT-POLICY).

Fixtures sintéticas: "BIOS" falsas (bytes aleatórios). Nenhum conteúdo protegido.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path

import jsonschema
import pytest

from steamzero.core import fs, journal, log, state
from steamzero.core.errors import SteamZeroError
from steamzero.domain.bios import BiosDatabase, BiosStore

_FAKE = b"conteudo-sintetico-de-bios-falsa"
_FAKE_SHA = hashlib.sha256(_FAKE).hexdigest()


def _db() -> BiosDatabase:
    return BiosDatabase(
        {
            "schemaVersion": 1,
            "platform": "psx",
            "entries": [
                {
                    "name": "scph5501.bin",
                    "sha256": _FAKE_SHA,
                    "region": "US",
                    "required": True,
                    "usedBy": [{"adapter": "duckstation"}],
                }
            ],
        }
    )


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[state.StateStore]:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    fs.ensure_state_layout()
    s = state.open_state()
    s.save_platform({"id": "psx", "name": "PSX"})
    yield s
    s.close()


def test_db_rejects_content_field() -> None:
    # CONTENT-POLICY: o schema (additionalProperties:false) recusa campo de conteúdo
    with pytest.raises(jsonschema.ValidationError):
        BiosDatabase(
            {
                "schemaVersion": 1,
                "platform": "psx",
                "entries": [{"name": "x.bin", "sha256": _FAKE_SHA, "blob": "AAAA"}],
            }
        )


def test_status_missing_has_no_download_link(store: state.StateStore) -> None:
    statuses = BiosStore(store, _db()).status(adapter="duckstation")
    assert len(statuses) == 1
    st = statuses[0]
    assert st.present is False
    assert st.error is not None and st.error["code"] == "E-CONTENT-BIOS-MISSING"
    # AC-BI-02 / CONTENT-POLICY: ação NUNCA contém link/URL
    blob = (st.error["action"] + st.error["what"]).lower()
    assert "http" not in blob and "download" not in blob and "baixar" not in blob


def test_import_valid_bios(tmp_path: Path, store: state.StateStore) -> None:
    provided = tmp_path / "scph5501.bin"
    fs.write_atomic(provided, _FAKE)
    result = BiosStore(store, _db()).import_bios(provided)
    assert result.status == "imported"
    assert result.name == "scph5501.bin"
    # agora o status é present
    assert BiosStore(store, _db()).status()[0].present is True


def test_import_unknown_bios(tmp_path: Path, store: state.StateStore) -> None:
    provided = tmp_path / "estranho.bin"
    fs.write_atomic(provided, b"conteudo-nao-reconhecido")
    with pytest.raises(SteamZeroError) as ei:
        BiosStore(store, _db()).import_bios(provided)
    assert ei.value.code == "E-CONTENT-FW-INCOMPAT"


def test_ac_bi_01_full_hash_never_logged(tmp_path: Path, store: state.StateStore) -> None:
    logfile = tmp_path / "core.jsonl"
    logger = log.StructuredLogger(logfile, correlation_id="CID")
    provided = tmp_path / "key.bin"
    fs.write_atomic(provided, _FAKE)
    BiosStore(store, _db(), logger=logger).import_bios(provided)
    raw = logfile.read_text()
    # AC-BI-01 / SR-14: hash completo nunca aparece; só truncado
    assert _FAKE_SHA not in raw
    assert _FAKE_SHA[:12] in raw
    assert "conteudo-sintetico" not in raw  # conteúdo nunca logado


@pytest.mark.rt
def test_rt08_broken_link_rolls_back_without_touching_central_bios(
    tmp_path: Path, store: state.StateStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    provided = tmp_path / "provided.bin"
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    fs.write_atomic(provided, _FAKE)
    bios = BiosStore(store, _db())
    bios.import_bios(provided)
    central = tmp_path / "data" / "steamzero" / "bios" / "psx" / "scph5501.bin"
    plan = bios.plan_link(
        "scph5501.bin", consumer_root=consumer, consumer_relpath="firmware/scph5501.bin"
    )
    target = consumer / "firmware" / "scph5501.bin"
    real_symlink = fs.symlink_atomic

    def create_broken_link(_source: Path, destination: Path) -> None:
        real_symlink(tmp_path / "missing.bin", destination)

    monkeypatch.setattr(fs, "symlink_atomic", create_broken_link)
    with pytest.raises(SteamZeroError) as error:
        bios.apply_link(plan.plan_id, plan.confirm_token)
    assert error.value.code == "E-TX-VERIFY-FAILED"
    assert not target.exists() and not target.is_symlink()
    assert central.read_bytes() == _FAKE
    operation = next((tmp_path / "state" / "steamzero" / "journal").glob("*.jsonl")).stem
    assert journal.is_terminal(journal.read_records(operation))


@pytest.mark.rt
def test_rt08_link_apply_and_rollback_are_idempotent(
    tmp_path: Path, store: state.StateStore
) -> None:
    provided = tmp_path / "provided.bin"
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    fs.write_atomic(provided, _FAKE)
    bios = BiosStore(store, _db())
    bios.import_bios(provided)
    plan = bios.plan_link(
        "scph5501.bin", consumer_root=consumer, consumer_relpath="firmware/scph5501.bin"
    )
    result = bios.apply_link(plan.plan_id, plan.confirm_token)
    target = consumer / "firmware" / "scph5501.bin"
    assert target.is_symlink() and target.read_bytes() == _FAKE
    assert bios.rollback_link(result.operation_id).status == "rolled-back"
    assert bios.rollback_link(result.operation_id).status == "rolled-back"
    assert not target.exists() and not target.is_symlink()
