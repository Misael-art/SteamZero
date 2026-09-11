# SPDX-License-Identifier: GPL-3.0-or-later
"""The CLI must retain the canonical observer until its detached game exits."""

from __future__ import annotations

import json
import os
import selectors
import subprocess
import sys
import time
from pathlib import Path

import pytest

import steamzero
from steamzero.adapters.launcher_session import observe_game_session
from steamzero.core.state import StateStore

# Inject only platform preflight and the synthetic game's argv. The CLI,
# session store, detached spawn and watcher run unchanged in another process.
_WORKER = r"""
import json
from pathlib import Path
import sys
import threading
import time
from unittest.mock import patch
from steamzero.adapters import emulation
from steamzero.cli.main import _cmd_emulation_launch
from steamzero.core.state import StateStore

database = Path(sys.argv[1])
exit_code = int(sys.argv[2])
controller = emulation.EmulationController.__new__(emulation.EmulationController)
controller._store_factory = lambda: StateStore(database)
controller._monotonic = time.monotonic
controller._read_start_ticks = emulation._read_proc_start_ticks
controller._process_waiter = emulation._wait_pid
controller._spawn = emulation._spawn_detached
controller._running_pids = {}
controller._provided_job_manager = None
controller._job_context = threading.local()
controller._launch_preflight = lambda _: {
    'game': {'id': 'lifetime-probe', 'name': 'Synthetic process'},
    'game_settings': {}, 'emulator_id': 'diagnostic', 'platform_id': 'diagnostic',
    'rom': database.parent / 'unused.rom', 'profile': None,
    'source_type': 'diagnostic', 'flatpak_ref': None, 'payload': None, 'core_path': None,
}
controller._apply_launch_enhancements = lambda *_: {'applied': 0, 'tried': 0, 'skipped': []}
controller._build_exec_argv = lambda *_, **__: (
    sys.executable, '-c', f'import time; time.sleep(0.5); raise SystemExit({exit_code})',
)
if len(sys.argv) > 3:
    controller._build_exec_argv = lambda *_, **__: (
        sys.executable, '-c',
        'from pathlib import Path; import sys,time; '
        'gate=Path(sys.argv[1]); deadline=time.monotonic()+10\n'
        'while not gate.exists() and time.monotonic()<deadline: time.sleep(0.01)',
        sys.argv[3],
    )
with patch.object(emulation, 'EmulationController', return_value=controller):
    envelope, code = _cmd_emulation_launch(['--game-id', 'lifetime-probe'], 'correlation')
print(json.dumps({'code': code, 'data': envelope['data']}), flush=True)
"""


def _alive(pid: int) -> bool:
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rpartition(") ")[2].split()
    except FileNotFoundError:
        return False
    return fields[0] not in {"Z", "X"}


@pytest.mark.parametrize("game_exit_code", [0, 7])
def test_cli_records_game_exit_before_observer_process_exits(
    tmp_path: Path, game_exit_code: int
) -> None:
    database = tmp_path / "state.db"
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(Path(steamzero.__file__).resolve().parent.parent)
    completed = subprocess.run(
        [sys.executable, "-c", _WORKER, str(database), str(game_exit_code)],
        env=environment,
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )
    launched = json.loads(completed.stdout)
    pid = launched["data"]["pid"]
    # Even the uncorrected implementation must not leave a synthetic process
    # behind when the assertion fails. The child exits itself; no host signals.
    deadline = time.monotonic() + 5
    while _alive(pid) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert not _alive(pid)
    assert launched["code"] == 0
    with StateStore(database) as store:
        row = store.latest_game_session("lifetime-probe")
    assert row is not None
    assert row["state"] == "closed"
    assert row["exit_code"] == game_exit_code
    assert row["duration_source"] == "observed-monotonic"
    assert observe_game_session(database, "lifetime-probe")["state"] == "closed"


def test_cli_publishes_launch_reply_while_game_and_observer_are_alive(tmp_path: Path) -> None:
    database = tmp_path / "state.db"
    release = tmp_path / "release-game"
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(Path(steamzero.__file__).resolve().parent.parent)
    with subprocess.Popen(
        [sys.executable, "-c", _WORKER, str(database), "0", str(release)],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as process:
        try:
            assert process.stdout is not None
            with selectors.DefaultSelector() as ready:
                ready.register(process.stdout, selectors.EVENT_READ)
                assert ready.select(timeout=10), "CLI must reply before the game is released"
            launched = json.loads(process.stdout.readline())
            assert launched["code"] == 0
            assert _alive(launched["data"]["pid"])
            assert process.poll() is None
            assert observe_game_session(database, "lifetime-probe")["state"] == "running"
        finally:
            release.touch()
            process.communicate(timeout=15)
    assert process.returncode == 0
    assert observe_game_session(database, "lifetime-probe")["state"] == "closed"
