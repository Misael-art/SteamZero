# SPDX-License-Identifier: GPL-3.0-or-later
"""Session Manager Game Mode independente e com fallback Desktop."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from steamzero.adapters import steam_session
from steamzero.core.errors import SteamZeroError


def _which(commands: dict[str, str]) -> steam_session.Which:
    return commands.get


def _boot_status() -> dict[str, object]:
    return {"state": "ready", "configured": True, "changesGrub": True}


def test_readiness_reports_independent_runtime() -> None:
    status = steam_session.readiness(
        which=_which(
            {
                "steam": "/usr/bin/steam",
                "gamescope": "/usr/bin/gamescope",
                "startkde-biglinux": "/usr/bin/startkde-biglinux",
            }
        ),
        boot_status=_boot_status,
    )
    assert status["state"] == "ready"
    assert status["independentRuntime"] is True
    # "unknown" cobre execução sem privilégio para inspecionar /etc (ADR-0020).
    assert status["directBoot"]["state"] in {"available", "ready", "unknown"}
    assert status["directBoot"]["changesGrub"] is True


def test_missing_gamescope_falls_back_to_biglinux_desktop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executed: list[str] = []

    def fake_exec(_path: str, argv: list[str]) -> None:
        executed.extend(argv)
        raise RuntimeError("exec intercepted")

    monkeypatch.setattr(steam_session.os, "execv", fake_exec)
    with pytest.raises(RuntimeError, match="intercepted"):
        steam_session.run_session(
            which=_which(
                {
                    "steam": "/usr/bin/steam",
                    "startkde-biglinux": "/usr/bin/startkde-biglinux",
                }
            ),
            environ={},
            boot_status=_boot_status,
        )
    assert executed == ["/usr/bin/startkde-biglinux", "wayland"]


def test_session_refuses_to_replace_an_existing_desktop() -> None:
    with pytest.raises(SteamZeroError) as error:
        steam_session.run_session(
            which=_which(
                {
                    "steam": "/usr/bin/steam",
                    "gamescope": "/usr/bin/gamescope",
                    "startplasma-wayland": "/usr/bin/startplasma-wayland",
                }
            ),
            environ={"WAYLAND_DISPLAY": "wayland-0"},
            boot_status=_boot_status,
        )
    assert error.value.code == "E-SESSION-LAUNCH-FAILED"


def test_session_uses_fixed_gamescope_argv_then_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    executed: list[str] = []

    def runner(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    def fake_exec(_path: str, argv: list[str]) -> None:
        executed.extend(argv)
        raise RuntimeError("exec intercepted")

    monkeypatch.setattr(steam_session.os, "execv", fake_exec)
    with pytest.raises(RuntimeError, match="intercepted"):
        steam_session.run_session(
            which=_which(
                {
                    "steam": "/usr/bin/steam",
                    "gamescope": "/usr/bin/gamescope",
                    "startplasma-wayland": "/usr/bin/startplasma-wayland",
                }
            ),
            runner=runner,
            environ={"PATH": "/usr/bin"},
            boot_started=lambda: {"state": "started"},
            boot_status=_boot_status,
        )
    assert calls == [
        [
            "/usr/bin/gamescope",
            "--steam",
            "--",
            "/usr/bin/steam",
            "-steamos3",
            "-gamepadui",
        ]
    ]
    assert executed == ["/usr/bin/startplasma-wayland"]


def test_session_marker_failure_is_logged_and_does_not_black_screen(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[list[str]] = []

    def runner(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    def fake_exec(_path: str, _argv: list[str]) -> None:
        raise RuntimeError("desktop reached")

    def failed_marker() -> dict[str, object]:
        raise OSError("state read-only")

    monkeypatch.setattr(steam_session.os, "execv", fake_exec)
    with pytest.raises(RuntimeError, match="desktop reached"):
        steam_session.run_session(
            which=_which(
                {
                    "steam": "/usr/bin/steam",
                    "gamescope": "/usr/bin/gamescope",
                    "startplasma-wayland": "/usr/bin/startplasma-wayland",
                }
            ),
            runner=runner,
            environ={"PATH": "/usr/bin"},
            boot_started=failed_marker,
            boot_status=_boot_status,
        )

    assert calls[0][0] == "/usr/bin/gamescope"
    assert "falha ao registrar início" in capsys.readouterr().err


def test_session_target_is_allowlisted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    with pytest.raises(SteamZeroError) as error:
        steam_session.request_target("shell", which=lambda _name: None)
    assert error.value.code == "E-API-SCHEMA"


def test_session_target_requests_shutdown_without_shell(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    calls: list[list[str]] = []

    def runner(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    result = steam_session.request_target(
        "desktop", which=_which({"steam": "/usr/bin/steam"}), runner=runner
    )
    assert result == {"status": "requested", "target": "desktop"}
    assert calls == [["/usr/bin/steam", "-shutdown"]]
    assert (tmp_path / "run" / "steamzero" / "gamemode-target").read_text() == "desktop"


def test_check_and_selector_entrypoints(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        steam_session,
        "readiness",
        lambda: {"state": "ready", "independentRuntime": True},
    )
    assert steam_session.main(["--check"]) == 0
    assert "independentRuntime" in capsys.readouterr().out

    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    monkeypatch.setattr(
        steam_session,
        "request_target",
        lambda target: {"status": "requested", "target": target},
    )
    assert steam_session.select_main(["desktop"]) == 0
    assert '"target": "desktop"' in capsys.readouterr().out
