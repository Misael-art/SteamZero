# SPDX-License-Identifier: GPL-3.0-or-later
"""M11 — canais de frontend (SRM manifests + ES-DE custom systems) via CLI.

Fluxo ponta a ponta: plan -> apply -> verify (convergido) -> plan noop ->
rollback, com envio de envelopes JSON e estado isolado em XDG dirs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from steamzero.cli import main as cli

GAMES = [
    {"id": "zelda-botw", "title": "The Legend of Zelda: Breath of the Wild"},
    {"id": "mario-odyssey", "title": "Super Mario Odyssey"},
]


@pytest.fixture
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, Path, Path]:
    state = tmp_path / "state"
    config = tmp_path / "config"
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config))
    monkeypatch.setenv("STEAMZERO_NO_DAEMON", "1")
    return tmp_path, state, config


def _spec_path(tmp_path: Path, *, only: str | None = None) -> Path:
    spec: dict[str, object] = {"srm": {}, "esde": {}}
    if only in (None, "srm"):
        spec["srm"] = {
            "collections": [
                {"slug": "switch", "games": GAMES},
            ]
        }
    if only in (None, "esde"):
        spec["esde"] = {
            "systems": [
                {
                    "name": "steamzero-switch",
                    "label": "Nintendo Switch",
                    "path": "/media/games/switch",
                    "extensions": [".nsp", ".xci"],
                    "platform": "switch",
                    "theme": "switch",
                }
            ]
        }
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec), encoding="utf-8")
    return path


def _run(capsys: pytest.CaptureFixture[str], args: list[str]) -> tuple[int, dict]:
    code = cli.main(args)
    out = capsys.readouterr().out
    return code, json.loads(out)


def test_frontends_plan_then_apply_then_verify_then_rollback(
    capsys: pytest.CaptureFixture[str], isolated: tuple[Path, Path, Path]
) -> None:
    tmp_path, _state, config = isolated
    spec = _spec_path(tmp_path)
    srm_dir = config / "steam-rom-manager" / "userData" / "manifests"
    esde_file = config / "ES-DE" / "custom_systems" / "es_systems.xml"

    code, env = _run(capsys, ["frontends", "status", "--json"])
    assert code == 0
    assert env["module"] == "frontends" and env["action"] == "status"
    assert env["data"]["srm"]["status"] == "missing"
    assert env["data"]["esde"]["status"] == "missing"

    code, env = _run(capsys, ["frontends", "plan", "--spec", str(spec), "--json"])
    assert code == 0
    plan = env["data"]
    assert plan["srm"]["actions"] != [] and plan["esde"]["actions"] != []
    srm_plan_id = plan["srm"]["planId"]
    srm_token = plan["srm"]["confirmToken"]
    esde_plan_id = plan["esde"]["planId"]
    esde_token = plan["esde"]["confirmToken"]

    code, env = _run(
        capsys,
        [
            "frontends",
            "apply",
            "--target",
            "srm",
            "--plan-id",
            srm_plan_id,
            "--confirm",
            srm_token,
            "--json",
        ],
    )
    assert code == 0
    assert env["data"]["status"] == "ok"
    assert env["data"]["target"] == "srm"
    srm_operation = env["data"]["operationId"]

    code, env = _run(
        capsys,
        [
            "frontends",
            "apply",
            "--target",
            "esde",
            "--plan-id",
            esde_plan_id,
            "--confirm",
            esde_token,
            "--json",
        ],
    )
    assert code == 0
    esde_operation = env["data"]["operationId"]

    assert (srm_dir / "steamzero-manifest-switch.json").is_file()
    assert "steamzero-switch" in esde_file.read_text(encoding="utf-8")

    code, env = _run(capsys, ["frontends", "verify", "--spec", str(spec), "--json"])
    assert code == 0
    assert env["data"]["srm"]["converged"] is True
    assert env["data"]["esde"]["converged"] is True

    code, env = _run(capsys, ["frontends", "plan", "--spec", str(spec), "--json"])
    assert code == 0
    assert env["data"]["srm"]["actions"] == []
    assert env["data"]["esde"]["actions"] == []

    code, env = _run(
        capsys,
        [
            "frontends",
            "rollback",
            "--target",
            "srm",
            "--operation-id",
            srm_operation,
            "--json",
        ],
    )
    assert code == 0
    assert env["data"]["status"] == "rolled-back"
    assert not (srm_dir / "steamzero-manifest-switch.json").exists()
    assert "steamzero-switch" in esde_file.read_text(encoding="utf-8")

    code, env = _run(
        capsys,
        [
            "frontends",
            "rollback",
            "--target",
            "esde",
            "--operation-id",
            esde_operation,
            "--json",
        ],
    )
    assert code == 0
    assert env["data"]["status"] == "rolled-back"
    assert not esde_file.exists() or "steamzero-switch" not in esde_file.read_text(
        encoding="utf-8"
    )


def test_frontends_rejects_bad_spec_and_wrong_confirm(
    capsys: pytest.CaptureFixture[str], isolated: tuple[Path, Path, Path]
) -> None:
    tmp_path, _state, _config = isolated

    bad = tmp_path / "bad.json"
    bad.write_text("[not an object]", encoding="utf-8")
    code, env = _run(capsys, ["frontends", "plan", "--spec", str(bad), "--json"])
    assert code != 0
    assert env["status"] == "failed"
    assert env["error"]["code"] == "E-API-SCHEMA"

    spec = _spec_path(tmp_path)
    code, env = _run(capsys, ["frontends", "plan", "--spec", str(spec), "--json"])
    assert code == 0
    srm = env["data"]["srm"]
    code, env = _run(
        capsys,
        [
            "frontends",
            "apply",
            "--target",
            "srm",
            "--plan-id",
            srm["planId"],
            "--confirm",
            "token-errado",
            "--json",
        ],
    )
    assert code != 0
    assert env["status"] == "blocked"
    assert env["error"]["code"] == "E-TX-CONFIRM-REQUIRED"

    code, env = _run(capsys, ["frontends", "plan", "--json"])
    assert code != 0
    assert env["error"]["code"] == "E-API-SCHEMA"

    code, env = _run(
        capsys,
        [
            "frontends",
            "apply",
            "--target",
            "nintnintw",
            "--plan-id",
            "x",
            "--confirm",
            "y",
            "--json",
        ],
    )
    assert code != 0
    assert env["error"]["code"] == "E-API-SCHEMA"


def test_frontends_status_tracks_managed_after_apply(
    capsys: pytest.CaptureFixture[str], isolated: tuple[Path, Path, Path]
) -> None:
    tmp_path, _state, _config = isolated
    spec = _spec_path(tmp_path)
    code, env = _run(capsys, ["frontends", "plan", "--spec", str(spec), "--json"])
    assert code == 0
    for target, plan in (("srm", env["data"]["srm"]), ("esde", env["data"]["esde"])):
        code, env_apply = _run(
            capsys,
            [
                "frontends",
                "apply",
                "--target",
                target,
                "--plan-id",
                plan["planId"],
                "--confirm",
                plan["confirmToken"],
                "--json",
            ],
        )
        assert code == 0, env_apply

    code, env = _run(capsys, ["frontends", "status", "--json"])
    assert code == 0
    assert env["data"]["srm"]["status"] == "configured"
    assert env["data"]["srm"]["collections"] == ["switch"]
    assert env["data"]["esde"]["status"] == "configured"
    assert env["data"]["esde"]["systems"] == ["steamzero-switch"]
