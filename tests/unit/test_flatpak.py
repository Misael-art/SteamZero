# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contrato argv/parsing da porta Flatpak real, sem mutar o host."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence

import pytest

from steamzero.adapters import flatpak as flatpak_module
from steamzero.adapters.flatpak import CommandResult, FlatpakCLI, FlatpakState
from steamzero.core.errors import SteamZeroError
from steamzero.jobs.manager import JobCancelled

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
    runner = FakeRunner([CommandResult(0, f"{REF}\tflathub\n"), CommandResult(0, f"{COMMIT}\n")])

    assert FlatpakCLI(runner=runner).status(REF) == FlatpakState(True, REF, "flathub", COMMIT)
    assert runner.calls[0][0] == (
        "flatpak",
        "list",
        "--user",
        "--app",
        "--columns=application,origin",
    )
    assert runner.calls[1][0] == ("flatpak", "info", "--user", "--show-commit", REF)


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


def test_real_runner_terminates_flatpak_when_job_cancels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class BlockingProcess:
        pid = 4242
        returncode = -15

        def __init__(self, argv: Sequence[str], **kwargs: object) -> None:
            captured["argv"] = tuple(argv)
            captured["kwargs"] = kwargs
            self.calls = 0
            self.terminated = False
            captured["process"] = self

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired("flatpak", timeout or 0)
            return "", ""

        def terminate(self) -> None:
            self.terminated = True

        def kill(self) -> None:
            raise AssertionError("terminate deveria bastar")

    monkeypatch.setattr(flatpak_module.shutil, "which", lambda _name: "/usr/bin/flatpak")
    monkeypatch.setattr(flatpak_module.subprocess, "Popen", BlockingProcess)

    cancel_checks = 0

    def cancel() -> None:
        nonlocal cancel_checks
        cancel_checks += 1
        if cancel_checks > 2:
            raise JobCancelled

    with (
        flatpak_module.flatpak_operation_observer(
            progress=lambda _stage, _current, _total: None,
            cancel_check=cancel,
        ),
        pytest.raises(JobCancelled),
    ):
        flatpak_module.run_flatpak_command(("flatpak", "install", "--user", REF), 30)

    process = captured["process"]
    assert isinstance(process, BlockingProcess)
    assert process.terminated is True
    assert captured["argv"] == ("/usr/bin/flatpak", "install", "--user", REF)
    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["start_new_session"] is True


def test_remote_failure_maps_to_stable_error() -> None:
    current = "b" * 64
    runner = FakeRunner(
        [CommandResult(1, "", "remote indisponível"), CommandResult(0, f"{current}\n")]
    )

    with pytest.raises(SteamZeroError) as error:
        FlatpakCLI(runner=runner).resolve("flathub", REF, COMMIT)

    assert error.value.code == "E-SUPPLY-REMOTE-FAILED"
    assert current in error.value.detail
    assert runner.calls[1][0] == (
        "flatpak",
        "remote-info",
        "--user",
        "--app",
        "--show-commit",
        "flathub",
        REF,
    )


def test_invalid_ref_never_reaches_runner() -> None:
    runner = FakeRunner([])

    with pytest.raises(SteamZeroError) as error:
        FlatpakCLI(runner=runner).status("--system")

    assert error.value.code == "E-API-SCHEMA"
    assert runner.calls == []


@pytest.mark.parametrize(
    "data",
    [
        {"installed": "false", "ref": REF, "origin": None, "commit": None},
        {"installed": False, "ref": REF, "origin": "flathub", "commit": COMMIT},
        {"installed": True, "ref": REF, "origin": None, "commit": COMMIT},
        {"installed": True, "ref": "--system", "origin": "flathub", "commit": COMMIT},
    ],
)
def test_flatpak_state_rejects_ambiguous_or_inconsistent_snapshots(
    data: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        FlatpakState.from_dict(data)


class _StubSource:
    def __init__(self, version: str) -> None:
        self.version = version
        self.end_of_life = False
        self.ref = "org.DolphinEmu.dolphin-emu"


class _StubManifest:
    kind = "emulator"


def test_degraded_status_explains_which_commits_diverged() -> None:
    """Degradação precisa dizer POR QUÊ, não só que existe.

    Defeito observado no host com a 2.0.0rc1 instalada: dolphin e retroarch
    apareciam como ``degraded`` com ``detail: None``, enquanto duckstation (no
    executor engine) explicava a divergência. Não faltava regra — faltava um
    executor cumprir a que o outro já cumpria, e o usuário ficava sem saber se
    devia atualizar para a fonte fixada ou investigar o commit instalado.
    """
    executor = flatpak_module.FlatpakExecutor.__new__(flatpak_module.FlatpakExecutor)
    executor._flatpak_source = lambda adapter_id, allow_eol=True: (  # type: ignore[method-assign]
        _StubManifest(),
        _StubSource("377c3e63506e" + "0" * 52),
    )
    executor._flatpak = type(  # type: ignore[assignment]
        "_Stub",
        (),
        {
            "status": staticmethod(
                lambda ref: FlatpakState(
                    installed=True, ref=ref, origin="flathub", commit="1b150924d321" + "0" * 52
                )
            )
        },
    )()

    status = executor.status("dolphin")

    assert status["state"] == "degraded"
    assert status["detail"] == ("commit instalado 1b150924d321 difere da fonte fixada 377c3e63506e")
