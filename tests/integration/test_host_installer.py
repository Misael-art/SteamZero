# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contrato do instalador host versionado sem tocar em caminhos do sistema."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import tempfile
import threading
from collections.abc import Sequence
from pathlib import Path

import pytest

import install_host


def _layout(tmp_path: Path) -> install_host.Layout:
    return install_host.Layout(
        root=tmp_path / "opt" / "steamzero",
        command=tmp_path / "usr" / "local" / "bin" / "steamzero",
        manager=tmp_path / "usr" / "local" / "sbin" / "steamzero-host",
        desktop=tmp_path
        / "usr"
        / "local"
        / "share"
        / "applications"
        / "org.steamzero.SteamZero.desktop",
        user_service=tmp_path
        / "usr"
        / "local"
        / "lib"
        / "systemd"
        / "user"
        / "steamzero-core.service",
        user_socket=tmp_path
        / "usr"
        / "local"
        / "lib"
        / "systemd"
        / "user"
        / "steamzero-core.socket",
        gamemode_session=tmp_path
        / "usr"
        / "share"
        / "wayland-sessions"
        / "steamzero-gamemode.desktop",
        legacy_gamemode_session=tmp_path
        / "usr"
        / "local"
        / "share"
        / "wayland-sessions"
        / "steamzero-gamemode.desktop",
        gamemode_boot_unit=tmp_path
        / "usr"
        / "local"
        / "lib"
        / "systemd"
        / "system"
        / "steamzero-gamemode-boot.service",
        gamemode_command=tmp_path / "usr" / "local" / "bin" / "steamzero-gamemode-session",
        session_selector_command=tmp_path / "usr" / "local" / "bin" / "steamos-session-select",
        gamemode_boot_command=tmp_path / "usr" / "local" / "libexec" / "steamzero-gamemode-boot",
        host_prepare_command=tmp_path / "usr" / "local" / "libexec" / "steamzero-host-prepare",
        admin_command=tmp_path / "usr" / "local" / "libexec" / "steamzero-admin",
        polkit_policy=tmp_path
        / "usr"
        / "share"
        / "polkit-1"
        / "actions"
        / "io.github.misael-art.steamzero.admin.policy",
    )


def _release(layout: install_host.Layout, name: str) -> Path:
    release = layout.releases / name
    executable = release / "venv" / "bin" / "steamzero"
    artifacts = release / "artifacts"
    executable.parent.mkdir(parents=True)
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "print('0.1.0') if '--version' in sys.argv else "
        "print(json.dumps({'status': 'ok'}))\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    artifacts.mkdir()
    wheel = artifacts / "steamzero-test.whl"
    requirements = artifacts / "requirements-runtime.lock"
    installer = artifacts / "install_host.py"
    wheel.write_text("wheel", encoding="utf-8")
    requirements.write_text("lock", encoding="utf-8")
    installer.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    installer.chmod(0o755)
    (release / "manifest.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "release": name,
                "wheelFile": wheel.name,
                "wheelSha256": install_host._sha256(wheel),
                "requirementsSha256": install_host._sha256(requirements),
                "installerSha256": install_host._sha256(installer),
            }
        ),
        encoding="utf-8",
    )
    return release


def _identified_release(
    layout: install_host.Layout,
    version: str,
    commit: str,
) -> tuple[str, Path]:
    release_id = install_host._canonical_release(version, commit)
    release = _release(layout, release_id)
    executable = release / "venv" / "bin" / "steamzero"
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        f"print({version!r}) if '--version' in sys.argv else "
        "print(json.dumps({'status': 'ok'}))\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    manifest_path = release / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        {
            "schemaVersion": 2,
            "packageVersion": version,
            "sourceCommit": commit,
            "sourceTreeState": "clean",
        }
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return release_id, release


class _HostRunner:
    def __init__(self, on_restart=None, failures: dict[str, int] | None = None) -> None:  # type: ignore[no-untyped-def]
        self.calls: list[tuple[str, ...]] = []
        self.on_restart = on_restart
        self.failures = failures or {}

    def __call__(self, argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
        call = tuple(argv)
        self.calls.append(call)
        joined = " ".join(call)
        for fragment, returncode in self.failures.items():
            if fragment in joined:
                return subprocess.CompletedProcess(call, returncode, "", f"falha em {fragment}")
        if self.on_restart is not None and call[-2:] == ("restart", "steamzero-core.service"):
            self.on_restart()
        return subprocess.CompletedProcess(call, 0, "", "")


def test_release_id_rejects_traversal() -> None:
    for invalid in ("../escape", "/absolute", "", "release with spaces"):
        with pytest.raises(ValueError):
            install_host._release_id(invalid)


def test_release_identity_is_canonical_version_plus_exact_commit() -> None:
    commit = "a" * 40
    assert install_host._canonical_release("0.1.0a1", commit) == f"0.1.0a1-{commit[:12]}"
    with pytest.raises(ValueError, match="SHA-1 completo"):
        install_host._canonical_release("0.1.0a1", "a" * 12)


def test_v2_manifest_requires_matching_release_provenance(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    release = _release(layout, "release-a")
    manifest_path = release / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        {
            "schemaVersion": 2,
            "packageVersion": "0.1.0a1",
            "sourceCommit": "b" * 40,
            "sourceTreeState": "clean",
        }
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(RuntimeError, match="versão e ao commit"):
        install_host._verify_release(release)


def test_release_verification_uses_disk_backed_tmp_for_the_smoke(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Um TMPDIR cheio da sessão não pode impedir a certificação da release."""
    layout = _layout(tmp_path)
    release = _release(layout, "release-a")
    captured: dict[str, object] = {}

    class SmokeDirectory:
        def __init__(self, *args: object, **kwargs: object) -> None:
            captured["args"] = args
            captured["dir"] = kwargs.get("dir")
            self.path = tmp_path / "smoke"

        def __enter__(self) -> str:
            self.path.mkdir()
            return str(self.path)

        def __exit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(install_host.tempfile, "TemporaryDirectory", SmokeDirectory)

    install_host._verify_release(release)

    assert captured["dir"] == install_host._SMOKE_TMPDIR


def test_verify_release_smoke_accepts_live_daemon_still_on_previous_generation(
    tmp_path: Path,
) -> None:
    """O smoke isola XDG, mas doctor ainda observa o daemon da sessão.

    Se a geração ao vivo ainda não convergiu, isso não pode impedir o
    instalador de verificar o binário novo — senão o converge nunca chega a
    reiniciar o serviço.
    """
    layout = _layout(tmp_path)
    release = _release(layout, "release-a")
    executable = release / "venv" / "bin" / "steamzero"
    # O doctor real sai com EXIT_FAILURE quando `status` é `failed`
    # (`_cmd_doctor` em cli/main.py). Um fake que saísse com 0 esconderia
    # justamente o defeito: o instalador nunca chegaria a inspecionar o payload.
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "if '--version' in sys.argv:\n"
        "    print('0.1.0')\n"
        "    sys.exit(0)\n"
        "print(json.dumps({\n"
        "    'status': 'failed',\n"
        "    'ok': False,\n"
        "    'checks': [\n"
        "        {'name': 'runtime.python', 'status': 'pass', 'message': 'ok'},\n"
        "        {'name': 'runtime.provenance', 'status': 'pass', 'message': 'release-a'},\n"
        "        {'name': 'service.generation', 'status': 'fail',\n"
        "         'message': 'E-HOST-DAEMON-PENDING: current=release-a daemon=release-old'},\n"
        "    ],\n"
        "}))\n"
        "sys.exit(1)\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)

    install_host._verify_release(release)


def test_verify_release_smoke_still_fails_on_unrelated_doctor_errors(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    release = _release(layout, "release-a")
    executable = release / "venv" / "bin" / "steamzero"
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "if '--version' in sys.argv:\n"
        "    print('0.1.0')\n"
        "    sys.exit(0)\n"
        "print(json.dumps({\n"
        "    'status': 'failed',\n"
        "    'ok': False,\n"
        "    'checks': [\n"
        "        {'name': 'state.db.integrity', 'status': 'fail', 'message': 'corrupt'},\n"
        "    ],\n"
        "}))\n"
        "sys.exit(1)\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)

    with pytest.raises(RuntimeError, match="smoke da release"):
        install_host._verify_release(release)


def test_verify_release_smoke_fails_when_doctor_produces_no_json(tmp_path: Path) -> None:
    """Doctor que morre sem payload não pode ser confundido com pendência benigna."""
    layout = _layout(tmp_path)
    release = _release(layout, "release-a")
    executable = release / "venv" / "bin" / "steamzero"
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "if '--version' in sys.argv:\n"
        "    print('0.1.0')\n"
        "    sys.exit(0)\n"
        "sys.stderr.write('Traceback: ImportError\\n')\n"
        "sys.exit(2)\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)

    with pytest.raises(RuntimeError, match="não devolveu JSON"):
        install_host._verify_release(release)


def test_activation_and_rollback_switch_current_atomically(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    _release(layout, "release-a")
    _release(layout, "release-b")

    install_host._activate(layout, "release-a")
    assert layout.current.readlink() == Path("releases/release-a")
    assert layout.command.readlink() == layout.current / "venv" / "bin" / "steamzero"
    assert "X-SteamZero-Managed=true" in layout.desktop.read_text(encoding="utf-8")

    result = install_host.rollback(layout, "release-b")
    assert result["release"] == "release-b"
    assert layout.current.readlink() == Path("releases/release-b")
    assert install_host.status(layout)["release"] == "release-b"


def test_stable_host_gate_accepts_legacy_daemon_by_version_and_process_path(
    tmp_path: Path,
) -> None:
    layout = _layout(tmp_path)
    release_id, release = _identified_release(layout, "0.1.0a37", "a" * 40)
    layout.current.parent.mkdir(parents=True, exist_ok=True)
    layout.current.symlink_to(Path("releases") / release_id)
    runner = _HostRunner()

    report = install_host.converge_host(
        layout,
        release_id,
        runner=runner,
        probe=lambda: {"daemonVersion": "0.1.0a37", "pid": 37},
        process_executable=lambda _pid: release / "venv" / "bin" / "python3",
    )

    assert report["state"] == "converged"
    assert report["restarted"] is False
    assert runner.calls == []


def test_stable_host_gate_accepts_modern_daemon_by_release_commit_and_process_path(
    tmp_path: Path,
) -> None:
    layout = _layout(tmp_path)
    commit = "b" * 40
    release_id, release = _identified_release(layout, "0.1.0a38", commit)
    layout.current.parent.mkdir(parents=True, exist_ok=True)
    layout.current.symlink_to(Path("releases") / release_id)
    runner = _HostRunner()

    report = install_host.converge_host(
        layout,
        release_id,
        runner=runner,
        probe=lambda: {
            "daemonVersion": "0.1.0a38",
            "pid": 38,
            "identity": {"releaseId": release_id, "sourceCommit": commit},
        },
        process_executable=lambda _pid: release / "venv" / "bin" / "python3",
    )

    assert report["state"] == "converged"
    assert report["restarted"] is False
    assert runner.calls == []


def test_stable_host_gate_converges_a38_to_legacy_a37_without_a37_cli(
    tmp_path: Path,
) -> None:
    layout = _layout(tmp_path)
    a37, release_a37 = _identified_release(layout, "0.1.0a37", "a" * 40)
    a38, release_a38 = _identified_release(layout, "0.1.0a38", "b" * 40)
    layout.current.parent.mkdir(parents=True, exist_ok=True)
    layout.current.symlink_to(Path("releases") / a37)
    daemon = {"release": a38, "version": "0.1.0a38", "pid": 38}

    def complete_restart() -> None:
        daemon.update(release=a37, version="0.1.0a37", pid=37)

    runner = _HostRunner(on_restart=complete_restart)

    def probe() -> dict[str, object]:
        if daemon["release"] == a37:
            return {"daemonVersion": daemon["version"], "pid": daemon["pid"]}
        return {
            "daemonVersion": daemon["version"],
            "pid": daemon["pid"],
            "identity": {"releaseId": a38, "sourceCommit": "b" * 40},
        }

    def process_executable(pid: int) -> Path:
        release = release_a37 if pid == 37 else release_a38
        return release / "venv" / "bin" / "python3"

    report = install_host.converge_host(
        layout,
        a37,
        runner=runner,
        probe=probe,
        process_executable=process_executable,
        sleep=lambda _seconds: None,
    )

    assert report["state"] == "converged"
    assert report["restarted"] is True
    assert ("/usr/bin/systemctl", "--user", "daemon-reload") in runner.calls
    assert (
        "/usr/bin/systemctl",
        "--user",
        "restart",
        "steamzero-core.service",
    ) in runner.calls


def test_stable_host_gate_fails_closed_before_restart_on_release_mismatch(
    tmp_path: Path,
) -> None:
    layout = _layout(tmp_path)
    a37, _release_a37 = _identified_release(layout, "0.1.0a37", "a" * 40)
    a38, _release_a38 = _identified_release(layout, "0.1.0a38", "b" * 40)
    layout.current.parent.mkdir(parents=True, exist_ok=True)
    layout.current.symlink_to(Path("releases") / a37)
    runner = _HostRunner()

    report = install_host.converge_host(layout, a38, runner=runner)

    assert report["state"] == "mismatch"
    assert report["code"] == "E-HOST-RELEASE-MISMATCH"
    assert runner.calls == []


def test_stable_host_gate_stops_units_when_wrong_daemon_survives_restart(
    tmp_path: Path,
) -> None:
    layout = _layout(tmp_path)
    a37, release_a37 = _identified_release(layout, "0.1.0a37", "a" * 40)
    _a38, release_a38 = _identified_release(layout, "0.1.0a38", "b" * 40)
    layout.current.parent.mkdir(parents=True, exist_ok=True)
    layout.current.symlink_to(Path("releases") / a37)
    runner = _HostRunner()

    report = install_host.converge_host(
        layout,
        a37,
        runner=runner,
        probe=lambda: {
            "daemonVersion": "0.1.0a38",
            "pid": 38,
            "identity": {
                "releaseId": "0.1.0a38-" + "b" * 12,
                "sourceCommit": "b" * 40,
            },
        },
        process_executable=lambda _pid: release_a38 / "venv" / "bin" / "python3",
        attempts=2,
        sleep=lambda _seconds: None,
    )

    assert release_a37 != release_a38
    assert report["state"] == "pending"
    assert report["code"] == "E-HOST-DAEMON-PENDING"
    assert (
        "/usr/bin/systemctl",
        "--user",
        "stop",
        "steamzero-core.service",
    ) in runner.calls
    assert (
        "/usr/bin/systemctl",
        "--user",
        "stop",
        "steamzero-core.socket",
    ) in runner.calls


def test_stable_host_gate_reports_timeout_and_stops_units_when_probe_never_answers(
    tmp_path: Path,
) -> None:
    layout = _layout(tmp_path)
    a37, _release_a37 = _identified_release(layout, "0.1.0a37", "a" * 40)
    layout.current.parent.mkdir(parents=True, exist_ok=True)
    layout.current.symlink_to(Path("releases") / a37)
    runner = _HostRunner()

    def unavailable() -> dict[str, object]:
        raise ConnectionError("daemon fora do ar")

    report = install_host.converge_host(
        layout,
        a37,
        runner=runner,
        probe=unavailable,
        attempts=2,
        sleep=lambda _seconds: None,
    )

    assert report["state"] == "timeout"
    assert report["code"] == "E-HOST-CONVERGENCE-TIMEOUT"
    assert (
        "/usr/bin/systemctl",
        "--user",
        "stop",
        "steamzero-core.service",
    ) in runner.calls


def test_stable_host_gate_reports_restart_failure_and_stops_units(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    a37, _release_a37 = _identified_release(layout, "0.1.0a37", "a" * 40)
    layout.current.parent.mkdir(parents=True, exist_ok=True)
    layout.current.symlink_to(Path("releases") / a37)
    runner = _HostRunner(failures={"daemon-reload": 1})

    report = install_host.converge_host(
        layout,
        a37,
        runner=runner,
        probe=lambda: (_ for _ in ()).throw(ConnectionError("stale")),
    )

    assert report["state"] == "restartFailed"
    assert report["code"] == "E-HOST-RESTART-FAILED"
    assert (
        "/usr/bin/systemctl",
        "--user",
        "stop",
        "steamzero-core.service",
    ) in runner.calls


def test_stable_host_gate_reports_unreadable_current_without_systemd(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    runner = _HostRunner()

    report = install_host.converge_host(layout, "release-a", runner=runner)

    assert report["state"] == "unreadable"
    assert report["code"] == "E-HOST-CURRENT-UNREADABLE"
    assert runner.calls == []


def test_stable_host_gate_reports_unverifiable_release_without_systemd(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    release_id, release = _identified_release(layout, "0.1.0a38", "b" * 40)
    layout.current.parent.mkdir(parents=True, exist_ok=True)
    layout.current.symlink_to(Path("releases") / release_id)
    (release / "manifest.json").write_text("{invalid", encoding="utf-8")
    runner = _HostRunner()

    report = install_host.converge_host(layout, release_id, runner=runner)

    assert report["state"] == "unreadable"
    assert report["code"] == "E-HOST-CURRENT-UNREADABLE"
    assert "não pôde ser verificada" in report["detail"]
    assert runner.calls == []


def test_stable_host_gate_rejects_modern_daemon_with_wrong_source_commit(
    tmp_path: Path,
) -> None:
    layout = _layout(tmp_path)
    release_id, release = _identified_release(layout, "0.1.0a38", "b" * 40)
    layout.current.parent.mkdir(parents=True, exist_ok=True)
    layout.current.symlink_to(Path("releases") / release_id)
    runner = _HostRunner()

    report = install_host.converge_host(
        layout,
        release_id,
        runner=runner,
        probe=lambda: {
            "daemonVersion": "0.1.0a38",
            "pid": 38,
            "identity": {"releaseId": release_id, "sourceCommit": "c" * 40},
        },
        process_executable=lambda _pid: release / "venv" / "bin" / "python3",
        attempts=1,
        sleep=lambda _seconds: None,
    )

    assert report["state"] == "pending"
    assert report["code"] == "E-HOST-DAEMON-PENDING"
    assert "commit declarado" in report["detail"]
    assert (
        "/usr/bin/systemctl",
        "--user",
        "stop",
        "steamzero-core.service",
    ) in runner.calls


def test_stable_host_probe_reads_legacy_system_hello_without_importing_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    short_runtime = tempfile.TemporaryDirectory(prefix="sz-g18-", dir="/tmp")
    runtime = Path(short_runtime.name)
    socket_dir = runtime / "steamzero"
    socket_dir.mkdir(parents=True, mode=0o700)
    runtime.chmod(0o700)
    socket_path = socket_dir / "core.sock"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(socket_path))
    os.chmod(socket_path, 0o600)
    server.listen(1)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))

    def serve_once() -> None:
        connection, _address = server.accept()
        try:
            request = connection.recv(4096)
            assert b'"method":"system.hello"' in request
            connection.sendall(
                b'{"jsonrpc":"2.0","id":1,"result":{"daemonVersion":"0.1.0a37","pid":37}}\n'
            )
        finally:
            connection.close()
            server.close()

    thread = threading.Thread(target=serve_once)
    thread.start()
    try:
        response = install_host._probe_host_daemon()
    finally:
        thread.join(timeout=2)
        short_runtime.cleanup()

    assert response == {"daemonVersion": "0.1.0a37", "pid": 37}


def test_converge_command_runs_as_session_user_without_root(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(install_host.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(
        install_host,
        "converge_host",
        lambda _layout, expected: {
            "state": "converged",
            "expectedRelease": expected,
            "restarted": False,
        },
    )

    exit_code = install_host.main(["converge", "--expect-release", "release-a"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["data"]["expectedRelease"] == "release-a"


def test_converge_command_refuses_bigsudo_root(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(install_host.os, "geteuid", lambda: 0)

    exit_code = install_host.main(["converge", "--expect-release", "release-a"])

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().err)
    assert payload["ok"] is False
    assert "sem bigsudo" in payload["error"]


def test_activation_refuses_unmanaged_command_without_switching(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    _release(layout, "release-a")
    _release(layout, "release-b")
    install_host._activate(layout, "release-a")
    layout.command.unlink()
    layout.command.write_text("do not replace", encoding="utf-8")

    with pytest.raises(RuntimeError, match="não gerenciado"):
        install_host._activate(layout, "release-b")

    assert layout.current.readlink() == Path("releases/release-a")


def test_activation_publishes_session_in_effective_sddm_location(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    release = _release(layout, "release-a")
    for name in (
        "steamzero-gamemode-session",
        "steamos-session-select",
        "steamzero-gamemode-boot",
    ):
        executable = release / "venv" / "bin" / name
        executable.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        executable.chmod(0o755)
    layout.legacy_gamemode_session.parent.mkdir(parents=True)
    layout.legacy_gamemode_session.write_text(
        "[Desktop Entry]\nX-SteamZero-Managed=true\n", encoding="utf-8"
    )

    install_host._activate(layout, "release-a")

    assert layout.gamemode_session.is_file()
    assert not layout.legacy_gamemode_session.exists()
    assert layout.session_selector_command.readlink() == (
        layout.current / "venv" / "bin" / "steamos-session-select"
    )


def test_activation_refuses_unmanaged_session_selector_without_switching(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    _release(layout, "release-a")
    layout.session_selector_command.parent.mkdir(parents=True)
    layout.session_selector_command.write_text("do not replace", encoding="utf-8")

    with pytest.raises(RuntimeError, match="seletor de sessão não gerenciado"):
        install_host._activate(layout, "release-a")

    assert not layout.current.exists()
    assert layout.session_selector_command.read_text(encoding="utf-8") == "do not replace"


def _add_venv_binary(layout: install_host.Layout, name: str, release: str) -> None:
    binary = layout.releases / release / "venv" / "bin" / name
    binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    binary.chmod(0o755)


def test_activation_refuses_release_without_boot_chain_when_direct_boot_active(
    tmp_path: Path,
) -> None:
    """Incidente 2026-07-19: release sem entry points de Game Mode foi ativada
    com o boot direto instalado e derrubou autologin, sessão e oneshot."""
    layout = _layout(tmp_path)
    _release(layout, "release-a")
    layout.gamemode_boot_unit.parent.mkdir(parents=True)
    layout.gamemode_boot_unit.write_text(
        "# SteamZero-Boot-Managed: true\n[Unit]\n", encoding="utf-8"
    )

    with pytest.raises(RuntimeError, match="boot direto ativo"):
        install_host._activate(layout, "release-a")

    assert not layout.current.exists()
    assert not layout.command.exists()


def test_activation_with_boot_chain_proceeds_when_direct_boot_active(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    _release(layout, "release-a")
    for name in ("steamzero-gamemode-boot", "steamzero-gamemode-session", "steamos-session-select"):
        _add_venv_binary(layout, name, "release-a")
    layout.gamemode_boot_unit.parent.mkdir(parents=True)
    layout.gamemode_boot_unit.write_text(
        "# SteamZero-Boot-Managed: true\n[Unit]\n", encoding="utf-8"
    )

    install_host._activate(layout, "release-a")

    assert layout.current.is_symlink()
    assert install_host._readlink(layout.current) == "releases/release-a"


def test_activation_refuses_broken_session_symlink_without_switching(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    _release(layout, "release-a")
    layout.gamemode_session.parent.mkdir(parents=True)
    layout.gamemode_session.symlink_to(tmp_path / "missing-session")

    with pytest.raises(RuntimeError, match="sessão não gerenciada"):
        install_host._activate(layout, "release-a")

    assert not layout.current.exists()
    assert layout.gamemode_session.is_symlink()


def test_verify_rejects_manifest_directory_mismatch(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    release = _release(layout, "release-a")
    manifest = json.loads((release / "manifest.json").read_text(encoding="utf-8"))
    manifest["release"] = "other"
    (release / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(RuntimeError, match="não corresponde"):
        install_host._verify_release(release)


def test_verify_rejects_tampered_release_artifact(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    release = _release(layout, "release-a")
    (release / "artifacts" / "steamzero-test.whl").write_text("tampered", encoding="utf-8")

    with pytest.raises(RuntimeError, match="integridade inválida: wheel"):
        install_host._verify_release(release)


def test_manager_is_stable_across_release_rollback(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    _release(layout, "release-a")
    _release(layout, "release-b")
    legacy_target = str(layout.current / "artifacts" / "install_host.py")
    layout.manager.parent.mkdir(parents=True)
    layout.manager.symlink_to(legacy_target)

    install_host._publish_manager(layout)
    published = layout.manager.read_bytes()
    assert layout.manager.is_file() and not layout.manager.is_symlink()

    install_host._activate(layout, "release-a")
    install_host.rollback(layout, "release-b")

    assert layout.manager.read_bytes() == published
    assert layout.current.readlink() == Path("releases/release-b")


def test_manager_refuses_unmanaged_regular_file(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    layout.manager.parent.mkdir(parents=True)
    layout.manager.write_text("do not replace", encoding="utf-8")

    with pytest.raises(RuntimeError, match="gerenciador não gerenciado"):
        install_host._publish_manager(layout)


def test_activation_publishes_and_removes_user_units_by_release_capability(
    tmp_path: Path,
) -> None:
    layout = _layout(tmp_path)
    modern = _release(layout, "release-modern")
    core = modern / "venv" / "bin" / "steamzero-core"
    core.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    core.chmod(0o755)
    session = modern / "venv" / "bin" / "steamzero-gamemode-session"
    session.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    session.chmod(0o755)
    admin = modern / "venv" / "bin" / "steamzero-admin"
    admin.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    admin.chmod(0o755)
    _release(layout, "release-legacy")

    install_host._activate(layout, "release-modern")
    assert "ListenStream=%t/steamzero/core.sock" in layout.user_socket.read_text()
    assert str(layout.current / "venv" / "bin" / "steamzero-core") in (
        layout.user_service.read_text()
    )
    assert "Name=SteamZero Game Mode" in layout.gamemode_session.read_text()
    assert "phasezero" not in layout.gamemode_session.read_text().casefold()
    assert layout.gamemode_command.readlink() == (
        layout.current / "venv" / "bin" / "steamzero-gamemode-session"
    )
    assert layout.admin_command.readlink() == (layout.current / "venv" / "bin" / "steamzero-admin")
    policy = layout.polkit_policy.read_text(encoding="utf-8")
    assert "io.github.misael-art.steamzero.admin" in policy
    assert str(layout.admin_command) in policy

    install_host._activate(layout, "release-legacy")
    assert not layout.user_service.exists()
    assert not layout.user_socket.exists()
    assert not layout.gamemode_session.exists()
    assert not layout.gamemode_command.exists()
    assert not layout.admin_command.exists()
    assert not layout.polkit_policy.exists()


def test_activation_refuses_unmanaged_gamemode_command(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    modern = _release(layout, "release-modern")
    session = modern / "venv" / "bin" / "steamzero-gamemode-session"
    session.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    session.chmod(0o755)
    layout.gamemode_command.parent.mkdir(parents=True)
    layout.gamemode_command.write_text("do not replace", encoding="utf-8")

    with pytest.raises(RuntimeError, match="comando não gerenciado"):
        install_host._activate(layout, "release-modern")

    assert not layout.current.exists()


def test_daemon_unit_allows_egress_because_installs_run_in_the_daemon(tmp_path: Path) -> None:
    """O daemon precisa de AF_INET/AF_INET6 para cumprir o que os adapters declaram.

    ``component apply`` delega a mutação ao daemon (provado no host por
    ``E-API-GENERATION-MISMATCH``), e os adapters declaram fontes de rede —
    remoto Flatpak, URL de AppImage. Com apenas ``AF_UNIX``, todo install que
    precise baixar falhava com "[6] Could not resolve hostname": o executor era
    proibido de alcançar as fontes que ele mesmo declara.

    O restante do endurecimento é exigido aqui para que afrouxar a rede não vire
    porta de entrada para afrouxar o resto.
    """
    unit = install_host._service_unit(_layout(tmp_path))
    families = [ln for ln in unit.splitlines() if ln.startswith("RestrictAddressFamilies=")]
    assert families == ["RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6"]
    for directive in (
        "NoNewPrivileges=true",
        "ProtectSystem=strict",
        "MemoryDenyWriteExecute=true",
        "ProtectKernelModules=true",
        "LockPersonality=true",
    ):
        assert directive in unit, f"endurecimento perdido: {directive}"
