# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contrato argv/parsing da porta Flatpak real, sem mutar o host."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from steamzero.adapters.flatpak import CommandResult, FlatpakCLI, FlatpakState
from steamzero.core.errors import SteamZeroError

REF = "org.example.Emulator"
COMMIT = "a" * 64


class FakeRunner:
    def __init__(self, results: list[CommandResult]) -> None:
        self.results = results
        self.calls: list[tuple[tuple[str, ...], float]] = []

    def __call__(self, argv: Sequence[str], timeout: float) -> CommandResult:
        self.calls.append((tuple(argv), timeout))
        return self.results.pop(0)


def test_status_parses_machine_columns() -> None:
    runner = FakeRunner([CommandResult(0, f"{REF}\t{COMMIT}\tflathub\n")])

    assert FlatpakCLI(runner=runner).status(REF) == FlatpakState(True, REF, "flathub", COMMIT)
    assert runner.calls[0][0] == (
        "flatpak",
        "list",
        "--user",
        "--app",
        "--columns=application,active,origin",
    )


def test_mutations_are_user_scoped_noninteractive_and_fixed_argv() -> None:
    runner = FakeRunner([CommandResult(0, ""), CommandResult(0, ""), CommandResult(0, "")])
    cli = FlatpakCLI(runner=runner)

    cli.install("flathub", REF)
    cli.deploy(REF, COMMIT)
    cli.uninstall(REF)

    for argv, _timeout in runner.calls:
        assert argv[0] == "flatpak"
        assert "--user" in argv
        assert "--noninteractive" in argv
        assert "--assumeyes" in argv
    assert f"--commit={COMMIT}" in runner.calls[1][0]
    assert "--delete-data" not in runner.calls[2][0]


def test_remote_failure_maps_to_stable_error() -> None:
    runner = FakeRunner([CommandResult(1, "", "remote indisponível")])

    with pytest.raises(SteamZeroError) as error:
        FlatpakCLI(runner=runner).resolve("flathub", REF, COMMIT)

    assert error.value.code == "E-SUPPLY-REMOTE-FAILED"


def test_invalid_ref_never_reaches_runner() -> None:
    runner = FakeRunner([])

    with pytest.raises(SteamZeroError) as error:
        FlatpakCLI(runner=runner).status("--system")

    assert error.value.code == "E-API-SCHEMA"
    assert runner.calls == []
