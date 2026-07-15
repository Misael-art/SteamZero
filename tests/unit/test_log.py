# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Testes de core.log: JSONL, correlação, mascaramento de segredos, rotação."""

from __future__ import annotations

import json
import stat
from pathlib import Path

from steamzero.core import ids, log
from steamzero.core.secret import Secret


def _read_lines(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_emits_valid_jsonl_with_required_fields(tmp_path: Path) -> None:
    p = tmp_path / "core.jsonl"
    logger = log.StructuredLogger(p, correlation_id="CID1")
    logger.info("started", phase=1)
    (record,) = _read_lines(p)
    assert record["event"] == "started"
    assert record["level"] == "info"
    assert record["correlationId"] == "CID1"
    assert record["phase"] == 1
    assert "ts" in record


def test_file_mode_0600(tmp_path: Path) -> None:
    p = tmp_path / "core.jsonl"
    log.StructuredLogger(p, correlation_id="CID").info("x")
    assert stat.S_IMODE(p.stat().st_mode) == 0o600


def test_secret_is_masked_canary(tmp_path: Path) -> None:
    p = tmp_path / "core.jsonl"
    logger = log.StructuredLogger(p, correlation_id="CID")
    logger.info("auth", token=Secret("hunter2-super-secret"), nested={"key": Secret("k3y")})
    raw = p.read_text(encoding="utf-8")
    assert "hunter2-super-secret" not in raw
    assert "k3y" not in raw
    (rec,) = _read_lines(p)
    assert rec["token"] == "***"
    assert rec["nested"] == {"key": "***"}


def test_bind_propagates_operation_id(tmp_path: Path) -> None:
    p = tmp_path / "core.jsonl"
    base = log.StructuredLogger(p, correlation_id="CID")
    child = base.bind(operationId="OP1", jobId="JOB1")
    child.info("apply")
    (rec,) = _read_lines(p)
    assert rec["operationId"] == "OP1"
    assert rec["jobId"] == "JOB1"
    assert rec["correlationId"] == "CID"


def test_min_level_filters(tmp_path: Path) -> None:
    p = tmp_path / "core.jsonl"
    logger = log.StructuredLogger(p, correlation_id="CID", min_level="warning")
    logger.info("ignored")
    logger.debug("ignored2")
    logger.warning("kept")
    lines = _read_lines(p)
    assert [r["event"] for r in lines] == ["kept"]


def test_rotation_by_size(tmp_path: Path) -> None:
    p = tmp_path / "core.jsonl"
    logger = log.StructuredLogger(p, correlation_id="CID", max_bytes=200)
    for i in range(50):
        logger.info("fill", i=i, pad="x" * 20)
    assert p.exists()
    assert (tmp_path / "core.jsonl.1").exists()  # rotacionou ao menos uma vez


def test_new_correlation_id_is_ulid() -> None:
    assert ids.is_ulid(log.new_correlation_id())
