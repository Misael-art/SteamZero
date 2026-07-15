# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Testes da CLL `steamzero` — envelope v2, doctor, exit codes (M2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from steamzero import CONTRACT_VERSION
from steamzero.api import contracts
from steamzero.cli import main as cli


@pytest.fixture(autouse=True)
def state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    return tmp_path


def test_doctor_json_validates_envelope(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(["doctor", "--json"])
    out = capsys.readouterr().out
    # stdout PURO: exatamente um objeto JSON
    env = json.loads(out)
    contracts.validate(env, "envelope-v2.schema.json")
    assert env["module"] == "doctor"
    assert env["contract"] == CONTRACT_VERSION
    assert {c["name"] for c in env["checks"]} >= {"runtime.python", "state.db.integrity"}
    assert code == cli.EXIT_OK


def test_doctor_human_output_has_no_json_envelope(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(["doctor"])
    out = capsys.readouterr().out
    assert "doctor run:" in out
    assert "[pass]" in out or "[warn]" in out or "[fail]" in out
    assert code == cli.EXIT_OK
    with pytest.raises(json.JSONDecodeError):
        json.loads(out)  # saída humana não é JSON


def test_contract_version(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(["--contract-version"])
    assert capsys.readouterr().out.strip() == CONTRACT_VERSION
    assert code == cli.EXIT_OK


def test_jobs_list_empty(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(["jobs", "list", "--json"])
    env = json.loads(capsys.readouterr().out)
    contracts.validate(env, "envelope-v2.schema.json")
    assert env["status"] == "noop"
    assert env["data"]["count"] == 0
    assert code == cli.EXIT_OK


def test_state_export_json(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(["state", "export", "--json"])
    env = json.loads(capsys.readouterr().out)
    contracts.validate(env, "envelope-v2.schema.json")
    assert "job" in env["data"]["tables"]
    assert code == cli.EXIT_OK


def test_state_export_to_file(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    out_file = tmp_path / "export.json"
    code = cli.main(["state", "export", "--out", str(out_file), "--json"])
    env = json.loads(capsys.readouterr().out)
    assert env["data"]["written"] == str(out_file)
    assert code == cli.EXIT_OK
    loaded = json.loads(out_file.read_text())
    assert "tables" in loaded


def test_unknown_action_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(["frobnicate", "now", "--json"])
    env = json.loads(capsys.readouterr().out)
    assert env["error"]["code"] == "E-CLI-USAGE"
    assert code == cli.EXIT_USAGE


def test_no_args_usage(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main([])
    assert code == cli.EXIT_USAGE
    assert "steamzero" in capsys.readouterr().err


def test_help(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(["--help"])
    assert code == cli.EXIT_OK
    assert "Domínios" in capsys.readouterr().out
