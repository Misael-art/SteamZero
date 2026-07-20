# SPDX-License-Identifier: GPL-3.0-or-later
"""Session Manager Game Mode independente e com fallback Desktop."""

from __future__ import annotations

import json
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
                "gamescope-session-plus": "/usr/bin/gamescope-session-plus",
                "startkde-biglinux": "/usr/bin/startkde-biglinux",
            }
        ),
        boot_status=_boot_status,
    )
    assert status["state"] == "ready"
    assert status["independentRuntime"] is True
    assert status["gamescopeSession"] is True
    # "unknown" cobre execução sem privilégio para inspecionar /etc (ADR-0020).
    assert status["directBoot"]["state"] in {"available", "ready", "unknown"}
    assert status["directBoot"]["changesGrub"] is True


def test_missing_gamescope_falls_back_to_biglinux_desktop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executed: list[str] = []
    executed_environment: dict[str, str] = {}

    def fake_exec(_path: str, argv: list[str], environment: dict[str, str]) -> None:
        executed.extend(argv)
        executed_environment.update(environment)
        raise RuntimeError("exec intercepted")

    monkeypatch.setattr(steam_session.os, "execve", fake_exec)
    with pytest.raises(RuntimeError, match="intercepted"):
        steam_session.run_session(
            which=_which(
                {
                    "steam": "/usr/bin/steam",
                    "startkde-biglinux": "/usr/bin/startkde-biglinux",
                }
            ),
            environ={"DESKTOP_SESSION": "steamzero-gamemode", "GAMESCOPE_FOO": "1"},
            boot_status=_boot_status,
        )
    assert executed == ["/usr/bin/startkde-biglinux", "wayland"]
    assert executed_environment["DESKTOP_SESSION"] == "plasma"
    assert executed_environment["XDG_CURRENT_DESKTOP"] == "KDE"
    assert executed_environment["XDG_SESSION_TYPE"] == "wayland"
    assert "GAMESCOPE_FOO" not in executed_environment


def test_missing_gamescope_session_wrapper_falls_back_to_desktop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executed: list[str] = []

    def fake_exec(_path: str, argv: list[str], _environment: dict[str, str]) -> None:
        executed.extend(argv)
        raise RuntimeError("exec intercepted")

    monkeypatch.setattr(steam_session.os, "execve", fake_exec)
    with pytest.raises(RuntimeError, match="intercepted"):
        steam_session.run_session(
            which=_which(
                {
                    "steam": "/usr/bin/steam",
                    "gamescope": "/usr/bin/gamescope",
                    "startplasma-wayland": "/usr/bin/startplasma-wayland",
                }
            ),
            environ={},
            boot_status=_boot_status,
        )

    assert executed == ["/usr/bin/startplasma-wayland"]


def test_desktop_environment_matches_a_direct_kde_login() -> None:
    direct = {
        "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus",
        "DESKTOP_SESSION": "plasma",
        "KDE_FULL_SESSION": "true",
        "PATH": "/usr/bin",
        "XDG_CURRENT_DESKTOP": "KDE",
        "XDG_SESSION_DESKTOP": "KDE",
        "XDG_SESSION_TYPE": "wayland",
    }

    handoff = steam_session._desktop_environment(("/usr/bin/startplasma-wayland",), direct)

    assert handoff == direct


def test_session_refuses_to_replace_an_existing_desktop() -> None:
    with pytest.raises(SteamZeroError) as error:
        steam_session.run_session(
            which=_which(
                {
                    "steam": "/usr/bin/steam",
                    "gamescope": "/usr/bin/gamescope",
                    "gamescope-session-plus": "/usr/bin/gamescope-session-plus",
                    "startplasma-wayland": "/usr/bin/startplasma-wayland",
                }
            ),
            environ={"WAYLAND_DISPLAY": "wayland-0"},
            boot_status=_boot_status,
        )
    assert error.value.code == "E-SESSION-LAUNCH-FAILED"


def test_missing_gamescope_does_not_start_nested_desktop() -> None:
    with pytest.raises(SteamZeroError) as error:
        steam_session.run_session(
            which=_which(
                {
                    "steam": "/usr/bin/steam",
                    "startplasma-wayland": "/usr/bin/startplasma-wayland",
                }
            ),
            environ={"WAYLAND_DISPLAY": "wayland-0"},
            boot_status=_boot_status,
        )
    assert error.value.code == "E-SESSION-LAUNCH-FAILED"


def test_session_uses_distro_gamescope_wrapper_then_falls_back(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[list[str]] = []
    executed: list[str] = []
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    def runner(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    def fake_exec(_path: str, argv: list[str], _environment: dict[str, str]) -> None:
        executed.extend(argv)
        raise RuntimeError("exec intercepted")

    monkeypatch.setattr(steam_session.os, "execve", fake_exec)
    with pytest.raises(RuntimeError, match="intercepted"):
        steam_session.run_session(
            which=_which(
                {
                    "steam": "/usr/bin/steam",
                    "gamescope": "/usr/bin/gamescope",
                    "gamescope-session-plus": "/usr/bin/gamescope-session-plus",
                    "startplasma-wayland": "/usr/bin/startplasma-wayland",
                }
            ),
            runner=runner,
            environ={"PATH": "/usr/bin"},
            boot_started=lambda: {"state": "started"},
            boot_status=_boot_status,
            retry_delay=lambda _seconds: None,
        )
    assert calls == [["/usr/bin/gamescope-session-plus", "steam"]] * 3
    assert executed == ["/usr/bin/startplasma-wayland"]
    state = json.loads((tmp_path / "state" / "steamzero" / "gamemode-session.json").read_text())
    assert state["state"] == "fallback"
    assert state["attempt"] == 3


def test_steam_updater_exit_is_retried_before_explicit_desktop(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []
    executed: list[str] = []
    delays: list[float] = []
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    def runner(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        if len(calls) == 2:
            steam_session.request_target("desktop", which=lambda _name: None)
        return subprocess.CompletedProcess(argv, 0, "", "")

    def fake_exec(_path: str, argv: list[str], _environment: dict[str, str]) -> None:
        executed.extend(argv)
        raise RuntimeError("desktop reached")

    monkeypatch.setattr(steam_session.os, "execve", fake_exec)
    with pytest.raises(RuntimeError, match="desktop reached"):
        steam_session.run_session(
            which=_which(
                {
                    "steam": "/usr/bin/steam",
                    "gamescope": "/usr/bin/gamescope",
                    "gamescope-session-plus": "/usr/bin/gamescope-session-plus",
                    "startplasma-wayland": "/usr/bin/startplasma-wayland",
                }
            ),
            runner=runner,
            environ={"PATH": "/usr/bin"},
            boot_started=lambda: {"state": "started"},
            boot_status=_boot_status,
            retry_delay=delays.append,
        )

    assert calls == [["/usr/bin/gamescope-session-plus", "steam"]] * 2
    assert delays == [1.0]
    assert executed == ["/usr/bin/startplasma-wayland"]
    state = json.loads((tmp_path / "state" / "steamzero" / "gamemode-session.json").read_text())
    assert state["state"] == "desktop-requested"
    assert state["target"] == "desktop"


def test_native_big_picture_desktop_request_reaches_desktop(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []
    executed: list[str] = []
    executed_environment: dict[str, str] = {}
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))

    def runner(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        steam_session.request_target("plasma", which=lambda _name: None)
        return subprocess.CompletedProcess(argv, 0, "", "")

    def fake_exec(_path: str, argv: list[str], environment: dict[str, str]) -> None:
        executed.extend(argv)
        executed_environment.update(environment)
        raise RuntimeError("desktop reached")

    monkeypatch.setattr(steam_session.os, "execve", fake_exec)
    with pytest.raises(RuntimeError, match="desktop reached"):
        steam_session.run_session(
            which=_which(
                {
                    "steam": "/usr/bin/steam",
                    "gamescope": "/usr/bin/gamescope",
                    "gamescope-session-plus": "/usr/bin/gamescope-session-plus",
                    "startplasma-wayland": "/usr/bin/startplasma-wayland",
                }
            ),
            runner=runner,
            environ={
                "DESKTOP_SESSION": "steamzero-gamemode",
                "GAMESCOPE_WAYLAND_DISPLAY": "gamescope-0",
                "PATH": "/usr/bin",
                "STEAM_GAMEPADUI": "1",
                "STEAMZERO_GAMEMODE_SESSION": "1",
                "XDG_CURRENT_DESKTOP": "gamescope",
            },
            boot_started=lambda: {"state": "started"},
            boot_status=_boot_status,
        )

    assert calls == [["/usr/bin/gamescope-session-plus", "steam"]]
    assert executed == ["/usr/bin/startplasma-wayland"]
    assert executed_environment["DESKTOP_SESSION"] == "plasma"
    assert executed_environment["KDE_FULL_SESSION"] == "true"
    assert executed_environment["XDG_CURRENT_DESKTOP"] == "KDE"
    assert executed_environment["XDG_SESSION_DESKTOP"] == "KDE"
    assert executed_environment["XDG_SESSION_TYPE"] == "wayland"
    assert "GAMESCOPE_WAYLAND_DISPLAY" not in executed_environment
    assert "STEAM_GAMEPADUI" not in executed_environment
    assert "STEAMZERO_GAMEMODE_SESSION" not in executed_environment
    assert not (tmp_path / "run" / "steamzero" / "gamemode-target").exists()


def test_session_marker_failure_is_logged_and_does_not_black_screen(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    def runner(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    def fake_exec(_path: str, _argv: list[str], _environment: dict[str, str]) -> None:
        raise RuntimeError("desktop reached")

    def failed_marker() -> dict[str, object]:
        raise OSError("state read-only")

    monkeypatch.setattr(steam_session.os, "execve", fake_exec)
    with pytest.raises(RuntimeError, match="desktop reached"):
        steam_session.run_session(
            which=_which(
                {
                    "steam": "/usr/bin/steam",
                    "gamescope": "/usr/bin/gamescope",
                    "gamescope-session-plus": "/usr/bin/gamescope-session-plus",
                    "startplasma-wayland": "/usr/bin/startplasma-wayland",
                }
            ),
            runner=runner,
            environ={"PATH": "/usr/bin"},
            boot_started=failed_marker,
            boot_status=_boot_status,
            retry_delay=lambda _seconds: None,
        )

    assert calls[0][0] == "/usr/bin/gamescope-session-plus"
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
