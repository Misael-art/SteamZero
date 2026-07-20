# SPDX-License-Identifier: GPL-3.0-or-later
"""Launcher Steam M11: composição allowlisted, verdade e lifecycle."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from steamzero.adapters import steam_launcher as launcher_module
from steamzero.adapters.steam_launcher import SteamGameLauncher
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore


class FakeChild:
    def __init__(self, exit_code: int = 0) -> None:
        self.pid = 4242
        self.exit_code = exit_code
        self.signals: list[int] = []

    def wait(self) -> int:
        return self.exit_code

    def send_signal(self, sig: int) -> None:
        self.signals.append(sig)


class FakeProcesses:
    def __init__(self, child: FakeChild | None = None) -> None:
        self.child = child or FakeChild()
        self.calls: list[tuple[tuple[str, ...], dict[str, str]]] = []

    def start(self, argv: object, env: dict[str, str]) -> FakeChild:
        self.calls.append((tuple(argv), dict(env)))  # type: ignore[arg-type]
        return self.child


class BrokenProcesses:
    def start(self, argv: object, env: dict[str, str]) -> FakeChild:
        raise OSError("spawn failed")


class SignallingChild(FakeChild):
    def wait(self) -> int:
        signal.raise_signal(signal.SIGTERM)
        return 0


def _save_profile(path: Path, **overrides: object) -> dict[str, object]:
    profile: dict[str, object] = {
        "gameId": "10",
        "scope": "game",
        "profile": "balanced",
        "fps": 40,
        "tdp": 10,
        "gpuMode": "auto",
        "gpuClock": None,
        "gamescope": True,
        "gameMode": True,
        "mangoHud": "basic",
        "upscaling": "gamescope-fsr",
        "frameGeneration": "off",
    }
    profile.update(overrides)
    with StateStore(path) as store:
        store.migrate()
        store.save_profile(
            {
                "id": "steam-gameplay:game:10",
                "scope": "game",
                "kind": "performance",
                "payload_json": json.dumps(profile),
                "profile_owner": "steamzero",
            }
        )
    return profile


def _launcher(tmp_path: Path, processes: FakeProcesses | None = None) -> SteamGameLauncher:
    available = {"gamescope", "gamemoderun", "mangohud", "mangoapp"}
    return SteamGameLauncher(
        roots=(tmp_path / "Steam",),
        which=lambda name: f"/usr/bin/{name}" if name in available else None,
        store_factory=lambda: StateStore(tmp_path / "state.db"),
        processes=processes,
        alive_probe=lambda pid: pid == 9999,
        environ=lambda: {"HOME": "/home/deck"},
        lsfg_manifests=(tmp_path / "VkLayer_LS_frame_generation.json",),
    )


def test_compile_composes_gamescope_mangoapp_gamemode_without_shell(tmp_path: Path) -> None:
    _save_profile(tmp_path / "state.db")
    launcher = _launcher(tmp_path)

    spec = launcher.compile("10", ("/games/My Game/game", "arg;shutdown", "$(touch nope)"))

    assert spec.argv == (
        "/usr/bin/gamescope",
        "-r",
        "40",
        "-F",
        "fsr",
        "--mangoapp",
        "--",
        "/usr/bin/gamemoderun",
        "/games/My Game/game",
        "arg;shutdown",
        "$(touch nope)",
    )
    assert spec.environment["MANGOHUD_CONFIG"].startswith("fps,frametime")
    assert "Gamescope 40 FPS" in spec.applied_effects
    assert "TDP aguarda transporte privilegiado validado em hardware" in spec.deferred_effects


def test_compile_mangohud_without_gamescope_and_public_summary(tmp_path: Path) -> None:
    _save_profile(
        tmp_path / "state.db",
        gamescope=False,
        gameMode=False,
        mangoHud="detailed",
        upscaling="fsr2-balanced",
        gpuMode="manual",
        gpuClock=800,
    )
    spec = _launcher(tmp_path).compile("10", ("game",))
    assert spec.argv == ("/usr/bin/mangohud", "game")
    assert len(spec.deferred_effects) == 3
    assert spec.public() == {
        "gameId": "10",
        "appliedEffects": ["MangoHud detailed"],
        "deferredEffects": list(spec.deferred_effects),
        "profileDigest": spec.profile_digest,
    }


def test_run_records_canonical_session_and_returns_child_code(tmp_path: Path) -> None:
    _save_profile(
        tmp_path / "state.db",
        gamescope=False,
        gameMode=False,
        mangoHud="off",
        upscaling="native",
        tdp=None,
    )
    processes = FakeProcesses(FakeChild(exit_code=17))
    launcher = _launcher(tmp_path, processes)

    assert launcher.run("10", ("/usr/bin/game",)) == 17
    assert processes.calls[0][0] == ("/usr/bin/game",)
    status = launcher.status("10")
    assert status["state"] == "desired"
    assert status["runtime"]["state"] == "closed"
    assert status["runtime"]["exitCode"] == 17
    assert status["runtime"]["sessionId"]
    with StateStore(tmp_path / "state.db") as store:
        assert [json.loads(event["payload_json"])["state"] for event in store.events_since(0)][
            -3:
        ] == ["launching", "running", "closed"]


def test_run_forwards_termination_signal_to_child(tmp_path: Path) -> None:
    _save_profile(
        tmp_path / "state.db",
        gamescope=False,
        gameMode=False,
        mangoHud="off",
        upscaling="native",
        tdp=None,
    )
    child = SignallingChild()
    launcher = _launcher(tmp_path, FakeProcesses(child))
    assert launcher.run("10", ("game",)) == 0
    assert child.signals == [signal.SIGTERM]
    with StateStore(tmp_path / "state.db") as store:
        session = store.latest_game_session("10")
    assert session is not None
    assert session["state"] == "closed"


def test_lsfg_environment_uses_owned_dll_and_pinned_layer(tmp_path: Path) -> None:
    _save_profile(
        tmp_path / "state.db",
        gamescope=False,
        gameMode=False,
        mangoHud="off",
        upscaling="native",
        tdp=None,
        frameGeneration="lsfg-3x",
    )
    manifest = tmp_path / "VkLayer_LS_frame_generation.json"
    manifest.write_text("{}", encoding="utf-8")
    steamapps = tmp_path / "Steam/steamapps"
    steamapps.mkdir(parents=True)
    (steamapps / "appmanifest_993090.acf").write_text(
        '"AppState"\n{\n "installdir" "Lossless Scaling"\n}\n', encoding="utf-8"
    )
    dll = steamapps / "common/Lossless Scaling/Lossless.dll"
    dll.parent.mkdir(parents=True)
    dll.write_bytes(b"owned")

    spec = _launcher(tmp_path).compile("10", ("game",))

    assert spec.environment["LSFG_LEGACY"] == "1"
    assert spec.environment["LSFG_MULTIPLIER"] == "3"
    assert spec.environment["LSFG_DLL_PATH"] == str(dll.resolve())


def test_missing_mangoapp_blocks_before_process_start(tmp_path: Path) -> None:
    _save_profile(tmp_path / "state.db")
    processes = FakeProcesses()
    launcher = SteamGameLauncher(
        store_factory=lambda: StateStore(tmp_path / "state.db"),
        which=lambda name: f"/usr/bin/{name}" if name != "mangoapp" else None,
        processes=processes,
    )

    with pytest.raises(SteamZeroError, match="mangoapp"):
        launcher.run("10", ("game",))
    assert processes.calls == []


def test_spawn_failure_is_recorded_without_exposing_command(tmp_path: Path) -> None:
    _save_profile(
        tmp_path / "state.db",
        gamescope=False,
        gameMode=False,
        mangoHud="off",
        upscaling="native",
        tdp=None,
    )
    launcher = SteamGameLauncher(
        store_factory=lambda: StateStore(tmp_path / "state.db"),
        processes=BrokenProcesses(),
    )
    with pytest.raises(OSError, match="spawn failed"):
        launcher.run("10", ("secret-game-argument",))
    runtime = launcher.status("10")["runtime"]
    assert runtime["state"] == "failed"
    assert runtime["error"] == "E-SESSION-LAUNCH-FAILED"
    assert "secret-game-argument" not in json.dumps(runtime)


def test_second_managed_session_is_blocked_atomically(tmp_path: Path) -> None:
    _save_profile(
        tmp_path / "state.db",
        gamescope=False,
        gameMode=False,
        mangoHud="off",
        upscaling="native",
        tdp=None,
    )
    with StateStore(tmp_path / "state.db") as store:
        store.create_game_session(
            {
                "id": "active-session",
                "game_id": "20",
                "state": "running",
                "pid": 9999,
                "owner": "steamzero-game-session",
            }
        )
    processes = FakeProcesses()
    with pytest.raises(SteamZeroError) as error:
        _launcher(tmp_path, processes).run("10", ("game",))
    assert error.value.code == "E-TX-LOCKED"
    assert processes.calls == []


def test_persisted_interrupted_session_requires_and_accepts_recovery(tmp_path: Path) -> None:
    _save_profile(tmp_path / "state.db")
    with StateStore(tmp_path / "state.db") as store:
        store.create_game_session(
            {
                "id": "interrupted-session",
                "game_id": "10",
                "state": "launching",
                "owner": "steamzero-launcher",
            }
        )
    launcher = _launcher(tmp_path)
    assert launcher.status("10")["recoveryRequired"] is True
    assert launcher.recover("10") == {"status": "recovered", "gameId": "10"}
    recovered = launcher.status("10")
    assert recovered["state"] == "desired"
    assert recovered["runtime"]["state"] == "failed"
    assert recovered["runtime"]["error"] == "E-SESSION-INTERRUPTED"


def test_stale_active_session_requires_explicit_recovery(tmp_path: Path) -> None:
    _save_profile(tmp_path / "state.db")
    with StateStore(tmp_path / "state.db") as store:
        store.save_profile(
            {
                "id": "steam-runtime:game:10",
                "scope": "game",
                "kind": "performance-runtime",
                "payload_json": '{"state":"active","pid":42}',
                "profile_owner": "steamzero-launcher",
            }
        )
    launcher = _launcher(tmp_path)

    assert launcher.status("10")["state"] == "stale"
    assert launcher.recover("10")["status"] == "recovered"
    assert launcher.status("10")["state"] == "desired"


def test_empty_status_and_clean_recovery_do_not_write(tmp_path: Path) -> None:
    launcher = _launcher(tmp_path)
    assert launcher.status("")["state"] == "unconfigured"
    assert launcher.recover("10") == {"status": "clean", "gameId": "10"}


def test_active_session_requires_process_identity_and_current_digest(tmp_path: Path) -> None:
    _save_profile(tmp_path / "state.db")
    compiler = _launcher(tmp_path)
    digest = compiler.compile("10", ("game",)).profile_digest
    with StateStore(tmp_path / "state.db") as store:
        store.save_profile(
            {
                "id": "steam-runtime:game:10",
                "scope": "game",
                "kind": "performance-runtime",
                "payload_json": json.dumps(
                    {"state": "active", "pid": 9999, "profileDigest": digest}
                ),
                "profile_owner": "steamzero-launcher",
            }
        )
    launcher = SteamGameLauncher(
        store_factory=lambda: StateStore(tmp_path / "state.db"),
        alive_probe=lambda pid: pid == 9999,
        observation_probe=lambda pid, app_id, seen: (
            pid == 9999 and app_id == "10" and seen == digest
        ),
        context_probe=lambda: None,
    )
    assert launcher.status("10")["state"] == "observed"

    _save_profile(tmp_path / "state.db", fps=60)
    changed = launcher.status("10")
    assert changed["state"] == "stale"
    assert changed["recoveryRequired"] is False


@pytest.mark.parametrize(
    "state", ["launching", "running", "suspending", "suspended", "resuming", "closing"]
)
def test_reused_live_pid_requires_recovery_without_signalling_process(
    tmp_path: Path, state: str
) -> None:
    _save_profile(tmp_path / "state.db")
    compiler = _launcher(tmp_path)
    digest = compiler.compile("10", ("game",)).profile_digest
    with StateStore(tmp_path / "state.db") as store:
        store.create_game_session(
            {
                "id": "reused-pid-session",
                "game_id": "10",
                "state": "launching",
                "pid": 4242,
                "profile_digest": digest,
                "owner": "steamzero-game-session",
            }
        )
        if state != "launching":
            store.transition_game_session("reused-pid-session", "running", pid=4242)
        if state in {"suspending", "suspended", "resuming"}:
            store.transition_game_session("reused-pid-session", "suspending")
        if state in {"suspended", "resuming"}:
            store.transition_game_session("reused-pid-session", "suspended")
        if state == "resuming":
            store.transition_game_session("reused-pid-session", "resuming")
        if state == "closing":
            store.transition_game_session("reused-pid-session", "closing")

    observed_calls: list[tuple[int, str, str]] = []
    launcher = SteamGameLauncher(
        store_factory=lambda: StateStore(tmp_path / "state.db"),
        alive_probe=lambda pid: pid == 4242,
        observation_probe=lambda pid, app_id, seen: (
            observed_calls.append((pid, app_id, seen)) or False
        ),
        wrapper_probe=lambda pid, app_id: False,
        context_probe=lambda: None,
    )

    status = launcher.status("10")
    assert status["state"] == "stale"
    assert status["recoveryRequired"] is True
    assert observed_calls == ([] if state == "launching" else [(4242, "10", digest)])
    assert launcher.recover("10") == {"status": "recovered", "gameId": "10"}
    assert launcher.status("10")["runtime"]["error"] == "E-SESSION-INTERRUPTED"


@pytest.mark.parametrize(
    ("runtime_state", "expected"),
    [
        ("suspending", "suspending"),
        ("suspended", "suspended"),
        ("resuming", "resuming"),
        ("closing", "closing"),
    ],
)
def test_lifecycle_intermediate_states_require_observed_identity(
    tmp_path: Path, runtime_state: str, expected: str
) -> None:
    _save_profile(tmp_path / "state.db")
    compiler = _launcher(tmp_path)
    digest = compiler.compile("10", ("game",)).profile_digest
    with StateStore(tmp_path / "state.db") as store:
        store.create_game_session(
            {
                "id": "lifecycle-session",
                "game_id": "10",
                "state": "launching",
                "pid": 4242,
                "profile_digest": digest,
                "owner": "steamzero-game-session",
            }
        )
        store.transition_game_session("lifecycle-session", "running", pid=4242)
        if runtime_state in {"suspending", "suspended", "resuming"}:
            store.transition_game_session("lifecycle-session", "suspending")
        if runtime_state in {"suspended", "resuming"}:
            store.transition_game_session("lifecycle-session", "suspended")
        if runtime_state == "resuming":
            store.transition_game_session("lifecycle-session", "resuming")
        if runtime_state == "closing":
            store.transition_game_session("lifecycle-session", "closing")

    launcher = SteamGameLauncher(
        store_factory=lambda: StateStore(tmp_path / "state.db"),
        alive_probe=lambda pid: pid == 4242,
        observation_probe=lambda pid, app_id, seen: True,
        context_probe=lambda: None,
    )
    status = launcher.status("10")
    assert status["state"] == expected
    assert status["recoveryRequired"] is False


def test_launching_requires_wrapper_identity(tmp_path: Path) -> None:
    _save_profile(tmp_path / "state.db")
    with StateStore(tmp_path / "state.db") as store:
        store.create_game_session(
            {
                "id": "launching-session",
                "game_id": "10",
                "state": "launching",
                "pid": 4242,
                "owner": "steamzero-game-session",
            }
        )
    launcher = SteamGameLauncher(
        store_factory=lambda: StateStore(tmp_path / "state.db"),
        alive_probe=lambda pid: pid == 4242,
        wrapper_probe=lambda pid, app_id: pid == 4242 and app_id == "10",
        context_probe=lambda: None,
    )
    status = launcher.status("10")
    assert status["state"] == "launching"
    assert status["recoveryRequired"] is False


def test_launcher_rejects_invalid_appid_and_missing_profile(tmp_path: Path) -> None:
    launcher = _launcher(tmp_path)
    with pytest.raises(SteamZeroError) as invalid:
        launcher.compile("10;shutdown", ("game",))
    assert invalid.value.code == "E-API-SCHEMA"
    with pytest.raises(SteamZeroError, match="nenhum perfil"):
        launcher.compile("10", ("game",))


@pytest.mark.parametrize(
    ("overrides", "detail"),
    [
        ({"fps": 45}, "FPS"),
        ({"tdp": True}, "TDP"),
        ({"gpuMode": "unsafe"}, "modo de GPU"),
        ({"gpuMode": "manual", "gpuClock": 9000}, "clock de GPU"),
        ({"mangoHud": "verbose"}, "MangoHud"),
        ({"upscaling": "shell"}, "renderização"),
    ],
)
def test_tampered_persisted_profile_is_rejected(
    tmp_path: Path, overrides: dict[str, object], detail: str
) -> None:
    _save_profile(tmp_path / "state.db", **overrides)
    with pytest.raises(SteamZeroError, match=detail) as error:
        _launcher(tmp_path).compile("10", ("game",))
    assert error.value.code == "E-STATE-INTEGRITY"


def test_lsfg_requires_layer_and_owned_dll_at_launch_time(tmp_path: Path) -> None:
    _save_profile(
        tmp_path / "state.db",
        gamescope=False,
        gameMode=False,
        mangoHud="off",
        upscaling="native",
        tdp=None,
        frameGeneration="lsfg-2x",
    )
    launcher = _launcher(tmp_path)
    with pytest.raises(SteamZeroError, match="camada LSFG"):
        launcher.compile("10", ("game",))
    (tmp_path / "VkLayer_LS_frame_generation.json").write_text("{}", encoding="utf-8")
    with pytest.raises(SteamZeroError, match=r"Lossless\.dll"):
        launcher.compile("10", ("game",))


def test_cli_entrypoint_has_stable_usage_and_exit_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert launcher_module.main([]) == 2
    assert launcher_module.main(["--appid", "10"]) == 2

    monkeypatch.setattr(SteamGameLauncher, "run", lambda self, app_id, command: 7)
    assert launcher_module.main(["--appid", "10", "--", "game"]) == 7

    def fail(self: SteamGameLauncher, app_id: str, command: object) -> int:
        raise OSError("private path")

    monkeypatch.setattr(SteamGameLauncher, "run", fail)
    assert launcher_module.main(["--appid", "10", "--", "game"]) == 71

    def domain_fail(self: SteamGameLauncher, app_id: str, command: object) -> int:
        raise SteamZeroError("E-COMPONENT-DEGRADED", detail="fixture")

    monkeypatch.setattr(SteamGameLauncher, "run", domain_fail)
    assert launcher_module.main(["--appid", "10", "--", "game"]) == 70


def test_low_level_process_and_display_observation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert launcher_module._is_alive(-1) is False
    assert launcher_module._is_alive(os.getpid()) is True
    assert launcher_module._is_observed_process(-1, "10", "digest") is False
    with monkeypatch.context() as patch:
        patch.setattr(
            Path,
            "read_bytes",
            lambda _path: (
                b"/opt/steamzero/venv/bin/python\0/usr/local/bin/steamzero-launch\0"
                b"--appid\0"
                b"10\0--\0game\0"
            ),
        )
        assert launcher_module._is_launcher_process(42, "10") is True
        assert launcher_module._is_launcher_process(42, "20") is False

    env = dict(os.environ)
    env.update({"STEAMZERO_GAME_ID": "10", "STEAMZERO_PROFILE_DIGEST": "digest"})
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(2)"], env=env)
    try:
        deadline = time.monotonic() + 1
        while (
            not launcher_module._is_observed_process(process.pid, "10", "digest")
            and time.monotonic() < deadline
        ):
            time.sleep(0.01)
        assert launcher_module._is_observed_process(process.pid, "10", "digest") is True
    finally:
        process.terminate()
        process.wait(timeout=3)

    internal = tmp_path / "card0-eDP-1/status"
    external = tmp_path / "card0-DP-1/status"
    internal.parent.mkdir(parents=True)
    external.parent.mkdir(parents=True)
    internal.write_text("connected\n", encoding="utf-8")
    external.write_text("disconnected\n", encoding="utf-8")
    monkeypatch.setattr(Path, "glob", lambda self, pattern: iter((internal, external)))
    assert launcher_module._display_context() == "portable"
    external.write_text("connected\n", encoding="utf-8")
    assert launcher_module._display_context() == "dock"

    child = launcher_module.SubprocessPort().start(("/usr/bin/true",), dict(os.environ))
    assert child.wait() == 0


def test_corrupt_profile_and_runtime_rows_degrade_safely(tmp_path: Path) -> None:
    _save_profile(tmp_path / "state.db")
    with StateStore(tmp_path / "state.db") as store:
        store._conn.execute("UPDATE profile SET payload_json='{' WHERE id='steam-gameplay:game:10'")
        store.save_profile(
            {
                "id": "steam-runtime:game:10",
                "scope": "game",
                "kind": "performance-runtime",
                "payload_json": "{",
                "profile_owner": "steamzero-launcher",
            }
        )
    launcher = _launcher(tmp_path)
    assert launcher.desired_profile("10") is None
    assert launcher.status("10")["runtime"] is None


def test_command_and_profile_integrity_guards(tmp_path: Path) -> None:
    _save_profile(tmp_path / "state.db")
    launcher = _launcher(tmp_path)
    with pytest.raises(SteamZeroError, match="comando Steam"):
        launcher.compile("10", ())
    with pytest.raises(SteamZeroError, match="argumento Steam"):
        launcher.compile("10", ("game", "bad\x00arg"))
    with StateStore(tmp_path / "state.db") as store:
        row = store.get_profile("steam-gameplay:game:10")
        payload = json.loads(str(row["payload_json"]))
        payload.pop("fps")
        store.save_profile({**row, "payload_json": json.dumps(payload)})
    with pytest.raises(SteamZeroError, match="incompleto"):
        launcher.compile("10", ("game",))


def test_profile_resolution_prefers_game_then_context_then_global(tmp_path: Path) -> None:
    state_path = tmp_path / "state.db"
    base = _save_profile(state_path)
    with StateStore(state_path) as store:
        for scope, fps in (("global", 30), ("dock", 60)):
            payload = {**base, "scope": scope, "fps": fps}
            store.save_profile(
                {
                    "id": f"steam-gameplay:{scope}:default",
                    "scope": scope,
                    "kind": "performance",
                    "payload_json": json.dumps(payload),
                    "profile_owner": "steamzero",
                }
            )
    launcher = SteamGameLauncher(
        store_factory=lambda: StateStore(state_path),
        context_probe=lambda: "dock",
    )
    assert launcher.desired_profile("10")["fps"] == 40  # type: ignore[index]

    with StateStore(state_path) as store:
        store._conn.execute("DELETE FROM profile WHERE id='steam-gameplay:game:10'")
    assert launcher.desired_profile("10")["fps"] == 60  # type: ignore[index]

    portable = SteamGameLauncher(
        store_factory=lambda: StateStore(state_path),
        context_probe=lambda: "portable",
    )
    assert portable.desired_profile("10")["fps"] == 30  # type: ignore[index]
