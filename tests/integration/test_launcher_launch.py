# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Lançamento real e retorno do AURA Launcher.

Estes testes criam processos de verdade. É o único jeito de provar o item 5 da
Definition of Done — reiniciar o launcher sem derrubar o jogo — porque um mock
sempre diria que sobreviveu.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from steamzero.launcher.launch import (
    DIAG_CONTEXT_LOST,
    LaunchPlan,
    consume_context,
    launch_detached,
)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    return True


def test_the_game_survives_the_launcher_process_dying(tmp_path: Path) -> None:
    """Item 5 da DoD: reiniciar o launcher não pode derrubar o jogo."""
    context_path = tmp_path / "return.json"
    parent = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import sys, time;"
                "sys.path.insert(0, 'src');"
                "from steamzero.launcher.launch import LaunchPlan, launch_detached;"
                "from steamzero.adapters.launcher_process import spawn_detached;"
                "plan = LaunchPlan(game_id='celeste', argv=('sleep', '30'),"
                f" focus_id='library:celeste', context_path=r'{context_path}');"
                "handle = launch_detached(plan, spawn=spawn_detached);"
                "print(handle.pid, flush=True);"
                "time.sleep(30)"
            ),
        ],
        stdout=subprocess.PIPE,
        text=True,
        cwd=Path.cwd(),
        # O launcher de teste precisa do próprio grupo: sem isso o killpg
        # abaixo alcançaria o pytest que roda esta suíte.
        start_new_session=True,
    )
    assert parent.stdout is not None
    child_pid = int(parent.stdout.readline().strip())
    try:
        assert _alive(child_pid)
        # Derruba o GRUPO do launcher, não apenas o processo.
        #
        # Matar só o pai não provaria nada: no Linux o filho é reparentado ao
        # init e sobreviveria de qualquer forma, com ou sem sessão própria. O
        # que a sessão própria protege é o sinal de grupo — Ctrl+C no terminal
        # ou o systemd encerrando o escopo do launcher.
        os.killpg(os.getpgid(parent.pid), signal.SIGKILL)
        parent.wait(timeout=10)
        time.sleep(0.5)
        assert _alive(child_pid), "o jogo morreu junto com o grupo do launcher"
        # E o contexto de retorno sobreviveu ao processo que o escreveu.
        restored = consume_context(context_path)
        assert restored is not None
        assert restored["focusId"] == "library:celeste"
    finally:
        # Limpa o jogo pelo grupo dele; deixar `sleep` órfão poluiria a máquina
        # de quem roda a suíte.
        try:
            os.killpg(os.getpgid(child_pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            with contextlib.suppress(ProcessLookupError):
                os.kill(child_pid, signal.SIGKILL)


def test_context_is_written_before_the_process_starts(tmp_path: Path) -> None:
    """Se o contexto fosse gravado depois, um crash no meio perderia o lugar."""
    context_path = tmp_path / "return.json"
    order: list[str] = []

    def runner(argv: tuple[str, ...]) -> int:
        order.append("spawn")
        assert context_path.exists(), "o contexto precisa existir antes do spawn"
        return 4321

    plan = LaunchPlan(
        game_id="celeste",
        argv=("sleep", "1"),
        focus_id="library:celeste",
        context_path=context_path,
    )
    handle = launch_detached(plan, spawn=runner)
    assert handle.pid == 4321
    assert order == ["spawn"]


def test_context_is_consumed_once(tmp_path: Path) -> None:
    context_path = tmp_path / "return.json"
    plan = LaunchPlan(
        game_id="celeste",
        argv=("sleep", "1"),
        focus_id="library:celeste",
        context_path=context_path,
    )
    launch_detached(plan, spawn=lambda argv: 1)
    assert consume_context(context_path) is not None
    # Segunda leitura não pode ressuscitar um retorno já usado.
    assert consume_context(context_path) is None


def test_a_truncated_context_is_reported_not_guessed(tmp_path: Path) -> None:
    context_path = tmp_path / "return.json"
    context_path.write_text("{ isso não é json", encoding="utf-8")
    restored, diagnostics = consume_context(context_path, with_diagnostics=True)
    assert restored is None
    assert any(item["code"] == DIAG_CONTEXT_LOST for item in diagnostics)


@pytest.mark.parametrize(
    "argv",
    [
        "sleep 30",
        ("sleep; rm -rf /",),
        (),
        ("../../bin/sh",),
    ],
)
def test_the_plan_refuses_argv_it_cannot_trust(argv: object, tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        LaunchPlan(
            game_id="celeste",
            argv=argv,  # type: ignore[arg-type]
            focus_id="library:celeste",
            context_path=tmp_path / "c.json",
        )
