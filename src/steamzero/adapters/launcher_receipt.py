# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Recibo de lançamento: captura a resposta do CLI que iniciou o jogo.

O spawn desacoplado mantém o jogo vivo independentemente do Launcher, e a
resposta JSON do CLI (aceita ou ``notStarted``) é o único sinal que confirma
o que aconteceu com ESTE pedido. PID vivo, código de saída ou foco de janela
não confirmam jogo: podem pertencer a outra tentativa.

O worker nunca mata o processo lançado e nunca prende a thread que atende
HTTP: lê uma linha limitada de stdout, classifica e segue acompanhando o
encerramento em segundo plano. O CLI vive até o fim do jogo (dono do ciclo
de vida canônico); encerrá-lo aqui destruiria a observação da sessão.
"""

from __future__ import annotations

import json
import selectors
import subprocess
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

#: Uma linha de envelope basta; mais que isso é resposta malformada, não
#: motivo para retenção de saída arbitrária.
_MAX_REPLY_BYTES = 1 << 20

#: Tempo de espera pela primeira linha antes de declarar atraso. O worker
#: continua esperando depois disso — atraso não é conclusão.
REPLY_TIMEOUT_SECONDS = 15.0

_PENDING = "pending"
_CONFIRMED = "confirmed"
_NOT_STARTED = "notStarted"
_UNCONFIRMED = "unconfirmed"
_DELAYED = "delayed"

_FINAL_STATES = frozenset({_CONFIRMED, _NOT_STARTED, _UNCONFIRMED})

#: Campos do objeto error-v1 que podem cruzar a ponte; texto cru do stderr e
#: caminhos locais não atravessam (projeção allowlisted).
_ERROR_FIELDS = (
    "code",
    "title",
    "what",
    "impact",
    "probableCause",
    "manualAction",
    "action",
    "detail",
)


@dataclass(frozen=True)
class Receipt:
    """Resultado final da leitura do recibo de uma tentativa."""

    state: str
    session_id: str | None = None
    game_id: str | None = None
    error: Mapping[str, Any] | None = None
    reason: str | None = None


def _project_error(error: Any) -> dict[str, Any] | None:
    if not isinstance(error, Mapping):
        return None
    return {key: error.get(key) for key in _ERROR_FIELDS if error.get(key) is not None}


def _classify(payload: Any, expected_game_id: str) -> Receipt:
    """Classifica o envelope do CLI sem inventar garantia."""
    if not isinstance(payload, Mapping):
        return Receipt(state=_UNCONFIRMED, reason="malformed")
    if payload.get("ok") is True:
        data = payload.get("data")
        if not isinstance(data, Mapping):
            return Receipt(state=_UNCONFIRMED, reason="malformed")
        session_id = data.get("sessionId")
        game_id = data.get("gameId")
        if not isinstance(session_id, str) or not session_id:
            return Receipt(state=_UNCONFIRMED, reason="malformed")
        if game_id != expected_game_id:
            # A resposta descreve outro jogo: nunca confirmar esta tentativa.
            return Receipt(state=_UNCONFIRMED, reason="game-mismatch")
        return Receipt(state=_CONFIRMED, session_id=session_id, game_id=expected_game_id)
    if payload.get("status") == "failed" and payload.get("ok") is False:
        acknowledgment = (payload.get("error") or {}).get("launchAcknowledgment")
        if acknowledgment == "notStarted":
            error = _project_error(payload.get("error"))
            return Receipt(state=_NOT_STARTED, game_id=expected_game_id, error=error)
        # Falha sem prova de pré-spawn: pode existir jogo; não liberar.
        return Receipt(state=_UNCONFIRMED, reason="unacknowledged-failure")
    return Receipt(state=_UNCONFIRMED, reason="malformed")


class LaunchAttempt:
    """Tentativa de lançamento com resposta capturada em segundo plano."""

    def __init__(self, *, request_id: str, game_id: str) -> None:
        self.request_id = request_id
        self.game_id = game_id
        self.pid = -1
        self._lock = threading.Lock()
        self._state = _PENDING
        self._receipt: Receipt | None = None

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @property
    def receipt(self) -> Receipt | None:
        with self._lock:
            return self._receipt

    def _settle(self, receipt: Receipt) -> None:
        with self._lock:
            if self._state in _FINAL_STATES:
                return
            self._receipt = receipt
            self._state = receipt.state

    def _delay(self) -> None:
        with self._lock:
            if self._state == _PENDING:
                self._state = _DELAYED

    def outcome(self) -> dict[str, Any]:
        """Projeção allowlisted do estado atual para a ponte/UI."""
        with self._lock:
            state = self._state
            receipt = self._receipt
        outcome: dict[str, Any] = {"requestId": self.request_id, "state": state}
        if receipt is not None:
            if receipt.session_id is not None:
                outcome["sessionId"] = receipt.session_id
            if receipt.reason is not None:
                outcome["reason"] = receipt.reason
            if receipt.error is not None:
                outcome["error"] = dict(receipt.error)
        return outcome


#: Assinatura de quem cria a tentativa; o argv chega validado por LaunchPlan.
ReceiptSpawner = Callable[..., LaunchAttempt]


def _watch(attempt: LaunchAttempt, process: subprocess.Popen[bytes]) -> None:
    """Lê a resposta e acompanha o encerramento sem prender ninguém."""
    stdout = process.stdout
    try:
        if stdout is not None:
            with selectors.DefaultSelector() as selector:
                selector.register(stdout, selectors.EVENT_READ)
                deadline_hit = False
                while attempt.state not in _FINAL_STATES:
                    events = selector.select(timeout=REPLY_TIMEOUT_SECONDS)
                    if not events:
                        if not deadline_hit:
                            deadline_hit = True
                            attempt._delay()
                        continue
                    line = stdout.readline(_MAX_REPLY_BYTES)
                    if not line:
                        attempt._settle(Receipt(state=_UNCONFIRMED, reason="eof"))
                        break
                    try:
                        payload = json.loads(line.decode("utf-8"))
                    except (ValueError, UnicodeDecodeError):
                        attempt._settle(Receipt(state=_UNCONFIRMED, reason="malformed"))
                        break
                    attempt._settle(_classify(payload, attempt.game_id))
                    break
        # O CLI vive até o fim do jogo (dono do ciclo canônico). Esperar sem
        # matar: o reap evita zumbi e o fechamento da nossa ponta de stdout
        # não afeta um filho que só escreveu o envelope e nunca mais volta.
        process.wait()
    finally:
        if stdout is not None:
            stdout.close()
        if process.stdin is not None:
            process.stdin.close()
        if process.stderr is not None:
            process.stderr.close()
        if attempt.state not in _FINAL_STATES:
            attempt._settle(Receipt(state=_UNCONFIRMED, reason="eof"))


def spawn_receipt(argv: tuple[str, ...], *, request_id: str, game_id: str) -> LaunchAttempt:
    """Lança o CLI em sessão própria e captura a resposta JSON dele.

    `start_new_session` mantém o jogo fora do grupo do Launcher (item 5 da
    Definition of Done). stdin é fechado e stderr vai para DEVNULL para que
    nenhum filho bloqueie por pipe cheio; stdout é a única ponta de resposta.
    """
    attempt = LaunchAttempt(request_id=request_id, game_id=game_id)
    process = subprocess.Popen(  # noqa: S603 - argv validado em LaunchPlan
        list(argv),
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    attempt.pid = process.pid
    worker = threading.Thread(
        target=_watch,
        args=(attempt, process),
        name=f"steamzero-receipt-{request_id[-8:]}",
        daemon=True,
    )
    worker.start()
    return attempt
