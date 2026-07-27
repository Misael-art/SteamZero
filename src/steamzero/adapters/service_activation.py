# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Recarga do daemon em escopo de usuário, após uma release nova ser publicada.

Vive em ``adapters`` porque fala com o systemd do host: a fronteira do projeto
reserva ``subprocess`` para essa camada (BND-PROC em tools/lint_boundaries.py).

Por que aqui e não no instalador: as units vivem em
``/usr/local/lib/systemd/user/`` e valem para TODOS os usuários da máquina. O
instalador roda como root e não sabe qual usuário reiniciar — nem o que fazer se
houver duas sessões abertas. Quem age é o manager de cada usuário, por conta
própria, sem travessia de privilégio.

Estado terminal em caso de falha (decisão C2): **daemon parado com causa
declarada**, nunca "daemon vivo de geração desconhecida". Os dois estados não são
igualmente ruins — daemon morto degrada funcionalidade, daemon vivo da geração
errada corrompe a verdade, e foi o segundo que produziu a a37. Verificado no
código que o boot NÃO depende deste daemon: ``steam_boot`` e ``steam_session``
não têm nenhuma referência a ``steamzero-core``.

A quarentena (decisão C3) é lida pela CLI e pelo doctor, para que a degradação
seja anunciada em vez de descoberta.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from steamzero.core import fs, log, paths
from steamzero.core.identity import runtime_identity

#: Units gerenciadas pelo SteamZero em escopo de usuário. Nenhuma unit de
#: terceiro é tocada (AGENTS.md §5).
MANAGED_UNITS = ("steamzero-core.socket", "steamzero-core.service")

_HANDSHAKE_ATTEMPTS = 10
_HANDSHAKE_INTERVAL = 0.3

Runner = Callable[[Sequence[str]], "CommandOutcome"]


@dataclass(frozen=True)
class CommandOutcome:
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class RefreshResult:
    state: str
    detail: str
    identity: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"state": self.state, "detail": self.detail}
        if self.identity is not None:
            payload["identity"] = self.identity
        return payload


def quarantine_path() -> Path:
    return paths.state_home() / "core-quarantine.json"


def _default_runner(argv: Sequence[str]) -> CommandOutcome:
    executable = shutil.which(argv[0])
    if executable is None:
        return CommandOutcome(127, "", f"comando ausente: {argv[0]}")
    try:
        completed = subprocess.run(  # noqa: S603 - argv fixo, sem shell
            [executable, *argv[1:]],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return CommandOutcome(126, "", f"falha ao executar {argv[0]}: {exc}")
    return CommandOutcome(completed.returncode, completed.stdout, completed.stderr)


def read_quarantine() -> dict[str, Any] | None:
    """Marcador de degradação declarada, ou ``None`` quando saudável."""
    path = quarantine_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # Marcador ilegível ainda é sinal de que algo foi quarentenado.
        return {"reason": "marcador de quarentena ilegível"}
    return data if isinstance(data, dict) else None


def _write_quarantine(reason: str, expected: dict[str, Any]) -> None:
    payload = {
        "schemaVersion": 1,
        "reason": reason,
        "expected": expected,
        "recordedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    try:
        fs.ensure_dir(quarantine_path().parent)
        fs.write_atomic(
            quarantine_path(), json.dumps(payload, ensure_ascii=False, indent=2).encode()
        )
    except OSError:  # pragma: no cover - filesystem degradado
        log.get_logger().warning("activation.quarantine-write-failed")


def clear_quarantine() -> None:
    # Remoção via core.fs: escrita em disco não passa por Path diretamente
    # (fronteira verificada por tools/lint_boundaries.py).
    try:
        fs.remove_file(quarantine_path())
    except OSError:  # pragma: no cover - filesystem degradado
        log.get_logger().warning("activation.quarantine-clear-failed")


def _stop_units(runner: Runner) -> None:
    """Para as units gerenciadas.

    Inclui o socket: sem isto, a ativação por socket ressuscitaria a geração
    anterior no próximo acesso, que é precisamente o estado que se quer evitar.
    """
    for unit in reversed(MANAGED_UNITS):
        runner(("systemctl", "--user", "stop", unit))


def refresh(
    *,
    runner: Runner | None = None,
    verifier: Callable[[], dict[str, Any]] | None = None,
    attempts: int = _HANDSHAKE_ATTEMPTS,
    interval: float = _HANDSHAKE_INTERVAL,
    sleep: Callable[[float], None] = time.sleep,
) -> RefreshResult:
    """Recarrega o manager, reinicia as units gerenciadas e confirma a geração."""
    run = runner or _default_runner
    verify = verifier
    if verify is None:
        from steamzero.service.client import verify_generation

        verify = verify_generation

    expected = runtime_identity().to_dict()

    reload_result = run(("systemctl", "--user", "daemon-reload"))
    if reload_result.returncode != 0:
        detail = (reload_result.stderr or reload_result.stdout).strip()[:400]
        _write_quarantine(f"daemon-reload falhou: {detail}", expected)
        _stop_units(run)
        return RefreshResult(
            "quarantined",
            "Não foi possível recarregar o gerenciador de serviços do usuário; "
            "o serviço foi parado para não responder com a versão anterior.",
        )

    for unit in MANAGED_UNITS:
        outcome = run(("systemctl", "--user", "restart", unit))
        if outcome.returncode != 0:
            detail = (outcome.stderr or outcome.stdout).strip()[:400]
            _write_quarantine(f"restart de {unit} falhou: {detail}", expected)
            _stop_units(run)
            return RefreshResult(
                "quarantined",
                f"Não foi possível reiniciar {unit}; o serviço foi parado para não "
                "responder com a versão anterior.",
            )

    last_error = ""
    for attempt in range(attempts):
        try:
            identity = verify()
        except Exception as exc:
            last_error = str(exc)
            if attempt + 1 < attempts:
                sleep(interval)
            continue
        clear_quarantine()
        return RefreshResult(
            "ready",
            "Serviço reiniciado e confirmado na versão instalada.",
            identity=identity,
        )

    # Chegou aqui: as units subiram mas a geração não confere, ou o handshake
    # nunca respondeu. Parar é a única saída honesta — ver C2 no cabeçalho.
    _write_quarantine(f"handshake não confirmou a geração: {last_error}", expected)
    _stop_units(run)
    return RefreshResult(
        "quarantined",
        "O serviço subiu mas não confirmou a versão instalada; foi parado para não "
        "responder com dados de outra versão.",
    )
