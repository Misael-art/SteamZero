# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""O recibo de lançamento confirma o que aconteceu com ESTE pedido.

Spawn, código de saída ou foco de janela não confirmam jogo: a resposta JSON
do CLI (aceita com sessionId, ou notStarted com acknowledgment) é o único
sinal. Malformada, ausente ou sem acknowledgment é ``unconfirmed`` — nunca
liberar duplicação com garantia inventada.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from steamzero.adapters import launcher_receipt
from steamzero.adapters.launcher_receipt import spawn_receipt


def _ok_cli(session_id: str, *, hold_gate: Path | None = None) -> tuple[str, ...]:
    """CLI sintético: responde aceito e segue vivo até o gate existir."""
    script = (
        "import json, os, sys, time;"
        "sys.stdout.write(json.dumps({'ok': True, 'data': {"
        "'gameId': sys.argv[1], 'sessionId': sys.argv[2]}}) + '\\n');"
        "sys.stdout.flush();"
    )
    if hold_gate is not None:
        script += (
            f"gate, deadline = {hold_gate.as_posix()!r}, time.time() + 10\n"
            "while not os.path.exists(gate) and time.time() < deadline: time.sleep(0.02)"
        )
    return (sys.executable, "-c", script, "celeste", session_id)


def _raw_cli(stdout: str) -> tuple[str, ...]:
    return (sys.executable, "-c", f"import sys; sys.stdout.write({stdout!r})")


def _not_started_cli() -> tuple[str, ...]:
    return _raw_cli(
        json_envelope(
            {
                "ok": False,
                "status": "failed",
                "error": {
                    "code": "E-COMPONENT-DEGRADED",
                    "what": "emulador ausente",
                    "impact": "nada foi criado",
                    "manualAction": "defina o emulador",
                    "launchAcknowledgment": "notStarted",
                    "secret": "nao-vazar",
                },
            }
        )
    )


def _unacknowledged_failure_cli() -> tuple[str, ...]:
    return _raw_cli(
        json_envelope(
            {
                "ok": False,
                "status": "failed",
                "error": {"code": "E-SESSION-LAUNCH-FAILED"},
            }
        )
    )


def json_envelope(payload: dict) -> str:
    import json

    return json.dumps(payload) + "\n"


def _settled(attempt, state: str, timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if attempt.state == state:
            return True
        time.sleep(0.01)
    return attempt.state == state


def _alive(pid: int) -> bool:
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rpartition(") ")[2].split()
    except FileNotFoundError:
        return False
    return fields[0] not in {"Z", "X"}


def _wait_exit(pid: int) -> None:
    """O jogo sintético sai sozinho pelo gate; o teste só aguarda o fim."""
    deadline = time.monotonic() + 12
    while _alive(pid) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert not _alive(pid)


def test_accepts_envelope_with_matching_game_and_session(tmp_path: Path) -> None:
    gate = tmp_path / "release"
    attempt = spawn_receipt(
        _ok_cli("sess-1", hold_gate=gate),
        request_id="req-1",
        game_id="celeste",
    )
    try:
        assert _settled(attempt, "confirmed")
        assert attempt.pid > 1
        # A resposta chega enquanto o jogo ainda vive: recibo não espera fim.
        assert _alive(attempt.pid)
        outcome = attempt.outcome()
        assert outcome["sessionId"] == "sess-1"
        assert outcome["requestId"] == "req-1"
    finally:
        gate.touch()
        _wait_exit(attempt.pid)


def test_not_started_acknowledgment_projects_allowlisted_error() -> None:
    attempt = spawn_receipt(_not_started_cli(), request_id="req-2", game_id="celeste")
    assert _settled(attempt, "notStarted")
    error = attempt.outcome()["error"]
    assert error["code"] == "E-COMPONENT-DEGRADED"
    assert error["what"] == "emulador ausente"
    assert error["manualAction"] == "defina o emulador"
    assert "secret" not in error, "campo fora da allowlist não atravessa a ponte"


def test_failure_without_acknowledgment_stays_unconfirmed() -> None:
    attempt = spawn_receipt(_unacknowledged_failure_cli(), request_id="req-3", game_id="celeste")
    assert _settled(attempt, "unconfirmed")
    assert attempt.outcome()["reason"] == "unacknowledged-failure"


def test_malformed_reply_is_never_a_confirmation() -> None:
    attempt = spawn_receipt(_raw_cli("not-json\n"), request_id="req-4", game_id="celeste")
    assert _settled(attempt, "unconfirmed")
    assert attempt.outcome()["reason"] == "malformed"


def test_eof_without_reply_is_unconfirmed_not_not_started() -> None:
    attempt = spawn_receipt(_raw_cli(""), request_id="req-5", game_id="celeste")
    assert _settled(attempt, "unconfirmed")
    assert attempt.outcome()["reason"] == "eof"


def test_reply_describing_another_game_is_rejected(tmp_path: Path) -> None:
    gate = tmp_path / "release"
    attempt = spawn_receipt(
        _ok_cli("sess-2", hold_gate=gate),
        request_id="req-6",
        game_id="hollow",
    )
    try:
        assert _settled(attempt, "unconfirmed")
        assert attempt.outcome()["reason"] == "game-mismatch"
    finally:
        gate.touch()
        _wait_exit(attempt.pid)


def test_slow_reply_reports_delay_before_confirming(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(launcher_receipt, "REPLY_TIMEOUT_SECONDS", 0.2)
    script = (
        "import json, sys, time;"
        "time.sleep(0.5);"
        "sys.stdout.write(json.dumps({'ok': True, 'data': {"
        "'gameId': sys.argv[1], 'sessionId': 'sess-3'}}) + '\\n');"
        "sys.stdout.flush()"
    )
    attempt = spawn_receipt(
        (sys.executable, "-c", script, "celeste"),
        request_id="req-7",
        game_id="celeste",
    )
    # Atraso informa lentidão; não fabrica conclusão.
    time.sleep(0.4)
    assert attempt.state in {"pending", "delayed"}
    assert _settled(attempt, "confirmed", timeout=5.0)
    assert attempt.outcome()["sessionId"] == "sess-3"


def test_partial_reply_reports_delay_and_later_confirms(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(launcher_receipt, "REPLY_TIMEOUT_SECONDS", 0.1)
    gate = tmp_path / "finish-reply"
    script = (
        "import os,sys,time\n"
        "sys.stdout.write('{');sys.stdout.flush()\n"
        "deadline=time.monotonic()+5\n"
        "while not os.path.exists(sys.argv[1]) and time.monotonic()<deadline: time.sleep(.01)\n"
        'sys.stdout.write(\'"ok":true,"data":{"gameId":"celeste","sessionId":"partial"}}\\n\')\n'
        "sys.stdout.flush()\n"
    )
    attempt = spawn_receipt(
        (sys.executable, "-c", script, str(gate)), request_id="partial", game_id="celeste"
    )
    try:
        assert _settled(attempt, "delayed", timeout=1.5)
    finally:
        gate.touch()
        _wait_exit(attempt.pid)
    assert _settled(attempt, "confirmed")


def test_non_object_error_is_malformed_without_worker_exception() -> None:
    receipt = launcher_receipt._classify(
        {"ok": False, "status": "failed", "error": "invalid"}, "celeste"
    )
    assert receipt.state == "unconfirmed"
    assert receipt.reason == "malformed"


def test_output_after_reply_is_drained_without_blocking_child(tmp_path: Path) -> None:
    finished = tmp_path / "finished"
    envelope = json_envelope({"ok": True, "data": {"gameId": "celeste", "sessionId": "drain"}})
    script = (
        "import pathlib,sys\n"
        f"sys.stdout.write({envelope!r});sys.stdout.flush()\n"
        "sys.stdout.write('x' * (2 << 20));sys.stdout.flush()\n"
        "pathlib.Path(sys.argv[1]).touch()\n"
    )
    attempt = spawn_receipt(
        (sys.executable, "-c", script, str(finished)), request_id="drain", game_id="celeste"
    )
    assert _settled(attempt, "confirmed")
    _wait_exit(attempt.pid)
    assert finished.exists()


def test_oversized_reply_is_rejected_and_child_can_exit(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(launcher_receipt, "_MAX_REPLY_BYTES", 256)
    attempt = spawn_receipt(
        (sys.executable, "-c", "import sys;sys.stdout.write('x' * (2 << 20));sys.stdout.flush()"),
        request_id="oversized",
        game_id="celeste",
    )
    assert _settled(attempt, "unconfirmed")
    assert attempt.outcome()["reason"] == "oversized"
    _wait_exit(attempt.pid)
