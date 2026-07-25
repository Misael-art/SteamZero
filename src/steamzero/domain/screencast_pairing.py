# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Política pura de pareamento e registro de receptores confiáveis.

Este módulo não gera aleatoriedade, não faz I/O e não importa adapters.
Ele DECIDE: aceita, recusa, expirou ou excedeu tentativas. O valor do
PIN vem de fora (``secrets``, no adapter).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

PIN_LENGTH = 6
PIN_ALPHABET = "0123456789"
PIN_VALIDITY_SECONDS = 120
PIN_MAX_ATTEMPTS = 5


class PairingDecision(Enum):
    ACCEPTED = "accepted"
    REFUSED = "refused"
    EXPIRED = "expired"
    EXCEEDED_ATTEMPTS = "exceeded-attempts"


@dataclass(frozen=True)
class TrustedReceiver:
    receiver_id: str
    display_name: str
    protocol: str
    transport: str
    paired_at: datetime
    expires_at: datetime | None = None

    def is_expired(self, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        return (now or datetime.now(UTC)) >= self.expires_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "receiverId": self.receiver_id,
            "displayName": self.display_name,
            "protocol": self.protocol,
            "transport": self.transport,
            "pairedAt": self.paired_at.isoformat(),
            "expiresAt": self.expires_at.isoformat() if self.expires_at else None,
        }


@dataclass(frozen=True)
class PairingState:
    receiver_id: str
    generated_at: datetime
    attempts_remaining: int = PIN_MAX_ATTEMPTS

    @property
    def is_expired(self) -> bool:
        age = datetime.now(UTC) - self.generated_at
        return age.total_seconds() > PIN_VALIDITY_SECONDS

    @property
    def is_exhausted(self) -> bool:
        return self.attempts_remaining <= 0


def decide_pairing(
    supplied_pin: str,
    expected_pin: str,
    state: PairingState,
    *,
    constant_time_compare: bool = True,
) -> tuple[PairingDecision, PairingState]:
    """Decide se o pareamento é aceito, recusado, expirou ou excedeu tentativas.

    ``constant_time_compare`` é uma exigência de contrato: a função chamadora
    DEVE usar comparação em tempo constante (``hmac.compare_digest`` ou
    ``secrets.compare_digest``). O domínio registra a exigência na assinatura.
    """
    if state.is_expired:
        return PairingDecision.EXPIRED, state

    if state.is_exhausted:
        return PairingDecision.EXCEEDED_ATTEMPTS, state

    if constant_time_compare and supplied_pin != expected_pin:
        decremented = PairingState(
            receiver_id=state.receiver_id,
            generated_at=state.generated_at,
            attempts_remaining=state.attempts_remaining - 1,
        )
        return PairingDecision.REFUSED, decremented

    if supplied_pin == expected_pin:
        return PairingDecision.ACCEPTED, state

    decremented = PairingState(
        receiver_id=state.receiver_id,
        generated_at=state.generated_at,
        attempts_remaining=state.attempts_remaining - 1,
    )
    return PairingDecision.REFUSED, decremented


def pin_within_validity(generated_at: datetime) -> bool:
    age = datetime.now(UTC) - generated_at
    return age.total_seconds() < PIN_VALIDITY_SECONDS


def format_pin(pin: str) -> str:
    """Agrupa o PIN para exibição amigável (ex.: 123 456)."""
    if len(pin) <= 3:
        return pin
    return f"{pin[:3]} {pin[3:]}"
