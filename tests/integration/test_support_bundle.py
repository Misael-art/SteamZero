# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Support bundle: preview revisável, confirmação por digest e anonimização (SZ-OP-07)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from steamzero.api import contracts
from steamzero.cli import main as cli
from steamzero.core import paths
from steamzero.diagnostics import support_bundle


@pytest.fixture(autouse=True)
def state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("STEAMZERO_NO_DAEMON", "1")
    return tmp_path


def test_anonymize_replaces_state_home_and_user_recursively() -> None:
    reps = [("/home/alice/.local/state/steamzero", "$STATE"), ("/home/alice", "$HOME")]
    value = {"a": ["/home/alice/.local/state/steamzero/db", "/home/alice/x"], "n": 3}
    assert support_bundle.anonymize(value, reps) == {"a": ["$STATE/db", "$HOME/x"], "n": 3}


def test_preview_is_anonymized_and_stable(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(["support", "bundle", "--preview", "--json"])
    env = json.loads(capsys.readouterr().out)
    contracts.validate(env, "envelope-v2.schema.json")
    assert code == cli.EXIT_OK
    data = env["data"]
    assert data["bundle"]["schema"] == support_bundle.BUNDLE_SCHEMA
    assert str(paths.state_home()) not in json.dumps(data["bundle"])
    assert data["bundle"]["doctor"]["data"]["stateHome"] == "$STATE"
    assert support_bundle.preview()["confirmToken"] == data["confirmToken"]


def test_write_requires_matching_token(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    out_file = tmp_path / "bundle.json"
    code = cli.main(["support", "bundle", "--out", str(out_file), "--confirm", "bad", "--json"])
    env = json.loads(capsys.readouterr().out)
    assert code == cli.EXIT_BLOCKED
    assert env["error"]["code"] == "E-TX-CONFIRM-REQUIRED"
    assert not out_file.exists()


def test_write_saves_exactly_the_previewed_bundle(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    preview = support_bundle.preview()
    out_file = tmp_path / "bundle.json"
    argv = ["support", "bundle", "--out", str(out_file), "--confirm", preview["confirmToken"]]
    code = cli.main([*argv, "--json"])
    env = json.loads(capsys.readouterr().out)
    assert code == cli.EXIT_OK
    assert env["data"]["sha256"] == preview["sha256"]
    assert json.loads(out_file.read_text()) == preview["bundle"]


def test_write_without_confirm_is_rejected(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    code = cli.main(["support", "bundle", "--out", str(tmp_path / "b.json"), "--json"])
    assert code == cli.EXIT_FAILURE
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "E-API-SCHEMA"
