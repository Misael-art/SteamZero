# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""O processo do Launcher não deixa a cena QML órfã ao morrer.

O defeito real: `steamzero-launcher` terminava e o `qml6` que renderiza
`LauncherMain.qml` sobrevivia, mantendo uma janela Wayland com o mesmo título
("SteamZero") e a mesma classe ("org.qt-project.qml") da sessão viva. A ponte
HTTP morre com o wrapper, então a janela órfã parece funcional e não é.

Isso já produziu dois diagnósticos errados registrados em
`docs/status/items/aura-launcher.json`: duas janelas coexistindo em 2026-08-27
("identidade de janela não é identidade de release") e, em 2026-09-04, injeções
de teclado entregues à janela órfã.

O teste sobe o caminho real de `launch_launcher_ui` com um `qml6` de mentira no
PATH — de mentira só no binário; a construção do argv, o grupo de processos e a
supervisão são os de produção. Depois mata o wrapper e exige que o filho tenha
ido junto.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

_WRAPPER = textwrap.dedent(
    """
    import sys
    from pathlib import Path

    from steamzero.adapters.launcher_ui import LauncherBridge, launch_launcher_ui
    from steamzero.launcher.navigation import HomeSection

    bridge = LauncherBridge(
        sections=(HomeSection(id="library", title="Biblioteca", items=("celeste",)),),
        context_path=Path(sys.argv[1]),
        on_launch=lambda *_: None,
    )
    raise SystemExit(launch_launcher_ui(bridge))
    """
)

# O `qml6` de mentira só publica o próprio PID e espera. O wrapper do teste
# nasce em sessão própria, então nenhum sinal do processo de teste o alcança por
# tabela: quem matar o filho terá sido o código de produção.
_FAKE_QML = textwrap.dedent(
    """
    #!/usr/bin/env python3
    import os, pathlib, time
    pathlib.Path(os.environ["STEAMZERO_TEST_PIDFILE"]).write_text(
        str(os.getpid()), encoding="utf-8"
    )
    time.sleep(300)
    """
)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # pragma: no cover - o processo existe
        return True
    return True


def _wait_until(predicate, *, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


@pytest.mark.parametrize("stop_signal", [signal.SIGTERM, signal.SIGINT])
def test_the_qml_child_dies_with_the_launcher_wrapper(
    tmp_path: Path, stop_signal: signal.Signals
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_qml = fake_bin / "qml6"
    # O shebang precisa ser o primeiro byte do arquivo; `dedent` preserva a
    # quebra inicial do literal.
    fake_qml.write_text(_FAKE_QML.lstrip(), encoding="utf-8")
    fake_qml.chmod(0o755)

    pidfile = tmp_path / "qml.pid"
    wrapper_script = tmp_path / "wrapper.py"
    wrapper_script.write_text(_WRAPPER, encoding="utf-8")

    environment = {
        **os.environ,
        "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
        "STEAMZERO_TEST_PIDFILE": str(pidfile),
    }
    wrapper = subprocess.Popen(  # argv fixo: interpretador do teste + script gerado aqui
        [sys.executable, str(wrapper_script), str(tmp_path / "return.json")],
        env=environment,
        start_new_session=True,
        stdin=subprocess.DEVNULL,
    )
    child_pid = -1
    try:
        assert _wait_until(lambda: pidfile.is_file() and pidfile.read_text().strip(), timeout=30), (
            "a cena QML de mentira não chegou a subir"
        )
        child_pid = int(pidfile.read_text(encoding="utf-8").strip())
        assert _alive(child_pid)

        wrapper.send_signal(stop_signal)
        wrapper.wait(timeout=30)

        assert _wait_until(lambda: not _alive(child_pid), timeout=15), (
            f"o processo qml6 {child_pid} sobreviveu ao wrapper: janela órfã com a mesma "
            "identidade da sessão viva"
        )
    finally:
        if wrapper.poll() is None:  # pragma: no cover - só em falha
            wrapper.kill()
            wrapper.wait(timeout=10)
        if child_pid > 0 and _alive(child_pid):  # pragma: no cover - só em falha
            os.kill(child_pid, signal.SIGKILL)
