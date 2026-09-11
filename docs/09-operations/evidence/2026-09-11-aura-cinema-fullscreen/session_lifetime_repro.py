"""Isolated diagnostic: real CLI/controller lifetime, synthetic game process."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[4] / 'src'
sys.path.insert(0, str(SOURCE))


def worker(database: Path) -> None:
    from steamzero.adapters import emulation
    from steamzero.cli.main import _cmd_emulation_launch
    from steamzero.core.state import StateStore

    controller = emulation.EmulationController.__new__(emulation.EmulationController)
    controller._store_factory = lambda: StateStore(database)
    controller._monotonic = time.monotonic
    controller._read_start_ticks = emulation._read_proc_start_ticks
    controller._process_waiter = emulation._wait_pid
    controller._spawn = emulation._spawn_detached
    controller._running_pids = {}
    controller._provided_job_manager = None
    controller._job_context = threading.local()
    # Only ROM/platform preflight and argv compilation are injected. The CLI,
    # canonical session creation, process spawn and watcher are production code.
    controller._launch_preflight = lambda _: {
        'game': {'id': 'aura-lifetime-probe', 'name': 'Synthetic lifetime probe'},
        'game_settings': {}, 'emulator_id': 'diagnostic', 'platform_id': 'diagnostic',
        'rom': database.parent / 'unused.rom', 'profile': None,
        'source_type': 'diagnostic', 'flatpak_ref': None, 'payload': None,
        'core_path': None,
    }
    controller._apply_launch_enhancements = lambda *_: {
        'applied': 0, 'tried': 0, 'skipped': [],
    }
    controller._build_exec_argv = lambda *_, **__: (
        sys.executable, '-c', 'import time; time.sleep(2)',
    )
    with patch.object(emulation, 'EmulationController', return_value=controller):
        envelope, code = _cmd_emulation_launch(
            ['--game-id', 'aura-lifetime-probe'], '00000000000000000000000000',
        )
    print(json.dumps({'exitCode': code, 'data': envelope['data']}), flush=True)


def parent() -> None:
    from steamzero.core.state import StateStore
    from steamzero.adapters.launcher_session import observe_game_session

    with tempfile.TemporaryDirectory(prefix='aura-lifetime-repro-') as directory:
        root = Path(directory)
        env = dict(os.environ)
        env['HOME'] = str(root / 'home')
        for key in ('STATE', 'DATA', 'CONFIG', 'CACHE', 'RUNTIME'):
            target = root / key.lower()
            target.mkdir(mode=0o700)
            env['XDG_' + key + '_HOME' if key != 'RUNTIME' else 'XDG_RUNTIME_DIR'] = str(target)
        database = root / 'state.db'
        started = time.monotonic()
        completed = subprocess.run(
            [sys.executable, __file__, '--worker', str(database)],
            env=env, capture_output=True, text=True, check=True, timeout=10,
        )
        elapsed = time.monotonic() - started
        launch = json.loads(completed.stdout)
        child_pid = launch['data']['pid']
        deadline = time.monotonic() + 6
        alive = True
        while time.monotonic() < deadline:
            try:
                fields = Path(f'/proc/{child_pid}/stat').read_text().rpartition(') ')[2].split()
                alive = fields[0] not in ('Z', 'X')
            except FileNotFoundError:
                alive = False
            if not alive:
                break
            time.sleep(0.02)
        with StateStore(database) as store:
            row = store.latest_game_session('aura-lifetime-probe')
        observation = observe_game_session(database, 'aura-lifetime-probe')
        result = {
            'diagnosticOnly': True, 'hostGameLaunched': False,
            'cliExitCode': completed.returncode, 'cliElapsedSeconds': round(elapsed, 3),
            'syntheticGameAliveAfterWait': alive,
            'canonicalStateAfterGameExit': row['state'],
            'launcherObservation': observation['state'],
            'defectReproduced': not alive and row['state'] == 'running'
                and observation['state'] == 'unknown',
        }
        print(json.dumps(result, indent=2))
        if not result['defectReproduced']:
            raise SystemExit('Expected defect was not reproduced; investigate result')


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--worker':
        worker(Path(sys.argv[2]))
    else:
        parent()
