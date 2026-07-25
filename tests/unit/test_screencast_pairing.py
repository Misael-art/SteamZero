# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from steamzero.domain.screencast_pairing import (
    PIN_ALPHABET,
    PIN_LENGTH,
    PIN_MAX_ATTEMPTS,
    PIN_VALIDITY_SECONDS,
    PairingDecision,
    PairingState,
    TrustedReceiver,
    decide_pairing,
    format_pin,
    pin_within_validity,
)


class TestPinPolicy:
    def test_pin_has_correct_length(self) -> None:
        assert PIN_LENGTH == 6

    def test_pin_alphabet_is_numeric(self) -> None:
        assert all(c in "0123456789" for c in PIN_ALPHABET)

    def test_pin_validity_window_is_reasonable(self) -> None:
        assert 60 <= PIN_VALIDITY_SECONDS <= 300

    def test_pin_max_attempts_is_positive(self) -> None:
        assert 3 <= PIN_MAX_ATTEMPTS <= 10

    def test_format_pin_six_digits(self) -> None:
        assert format_pin("123456") == "123 456"

    def test_format_pin_short(self) -> None:
        assert format_pin("123") == "123"

    def test_format_pin_empty(self) -> None:
        assert format_pin("") == ""


class TestPairingState:
    def test_fresh_state_not_expired(self) -> None:
        state = PairingState(receiver_id="tv-1", generated_at=datetime.now(UTC))
        assert not state.is_expired

    def test_state_expired_after_validity_window(self) -> None:
        old = datetime.now(UTC) - timedelta(seconds=PIN_VALIDITY_SECONDS + 1)
        state = PairingState(receiver_id="tv-1", generated_at=old)
        assert state.is_expired

    def test_not_exhausted_initially(self) -> None:
        state = PairingState(receiver_id="tv-1", generated_at=datetime.now(UTC))
        assert not state.is_exhausted

    def test_exhausted_when_no_attempts_left(self) -> None:
        state = PairingState(
            receiver_id="tv-1",
            generated_at=datetime.now(UTC),
            attempts_remaining=0,
        )
        assert state.is_exhausted


class TestDecidePairing:
    def test_accepts_correct_pin(self) -> None:
        state = PairingState(receiver_id="tv-1", generated_at=datetime.now(UTC))
        decision, new_state = decide_pairing("123456", "123456", state)
        assert decision == PairingDecision.ACCEPTED
        assert new_state is state

    def test_refuses_wrong_pin(self) -> None:
        state = PairingState(receiver_id="tv-1", generated_at=datetime.now(UTC))
        decision, new_state = decide_pairing("000000", "123456", state)
        assert decision == PairingDecision.REFUSED
        assert new_state.attempts_remaining == PIN_MAX_ATTEMPTS - 1

    def test_expired_pin(self) -> None:
        old = datetime.now(UTC) - timedelta(seconds=PIN_VALIDITY_SECONDS + 1)
        state = PairingState(receiver_id="tv-1", generated_at=old)
        decision, new_state = decide_pairing("123456", "123456", state)
        assert decision == PairingDecision.EXPIRED
        assert new_state is state

    def test_exhausted_attempts(self) -> None:
        state = PairingState(
            receiver_id="tv-1",
            generated_at=datetime.now(UTC),
            attempts_remaining=0,
        )
        decision, new_state = decide_pairing("123456", "123456", state)
        assert decision == PairingDecision.EXCEEDED_ATTEMPTS
        assert new_state is state

    def test_exhausted_after_multiple_refusals(self) -> None:
        state = PairingState(receiver_id="tv-1", generated_at=datetime.now(UTC))
        for i in range(PIN_MAX_ATTEMPTS + 1):
            decision, state = decide_pairing("000000", "123456", state)
            if i < PIN_MAX_ATTEMPTS:
                assert decision == PairingDecision.REFUSED, f"i={i}"
            else:
                assert decision == PairingDecision.EXCEEDED_ATTEMPTS

    def test_exhausted_when_decremented_to_zero(self) -> None:
        state = PairingState(
            receiver_id="tv-1",
            generated_at=datetime.now(UTC),
            attempts_remaining=1,
        )
        decision, state = decide_pairing("000000", "123456", state)
        assert decision == PairingDecision.REFUSED
        assert state.attempts_remaining == 0
        decision, state = decide_pairing("000000", "123456", state)
        assert decision == PairingDecision.EXCEEDED_ATTEMPTS

    def test_accepts_correct_pin_at_last_attempt(self) -> None:
        state = PairingState(
            receiver_id="tv-1",
            generated_at=datetime.now(UTC),
            attempts_remaining=1,
        )
        decision, new_state = decide_pairing("123456", "123456", state)
        assert decision == PairingDecision.ACCEPTED
        assert new_state is state


class TestPinWithinValidity:
    def test_recent_pin_is_valid(self) -> None:
        generated = datetime.now(UTC)
        assert pin_within_validity(generated)

    def test_old_pin_is_invalid(self) -> None:
        old = datetime.now(UTC) - timedelta(seconds=PIN_VALIDITY_SECONDS + 10)
        assert not pin_within_validity(old)

    def test_boundary_pin_is_valid(self) -> None:
        boundary = datetime.now(UTC) - timedelta(seconds=PIN_VALIDITY_SECONDS - 1)
        assert pin_within_validity(boundary)


class TestTrustedReceiver:
    def test_not_expired_when_no_expiry(self) -> None:
        r = TrustedReceiver(
            receiver_id="tv-1",
            display_name="TV Sala",
            protocol="web-receiver",
            transport="lan",
            paired_at=datetime.now(UTC),
        )
        assert not r.is_expired()

    def test_expired_when_past_expiry(self) -> None:
        r = TrustedReceiver(
            receiver_id="tv-1",
            display_name="TV Sala",
            protocol="web-receiver",
            transport="lan",
            paired_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        assert r.is_expired()

    def test_not_expired_before_expiry(self) -> None:
        r = TrustedReceiver(
            receiver_id="tv-1",
            display_name="TV Sala",
            protocol="web-receiver",
            transport="lan",
            paired_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
        assert not r.is_expired()

    def test_to_dict_includes_all_fields(self) -> None:
        now = datetime.now(UTC)
        r = TrustedReceiver(
            receiver_id="tv-1",
            display_name="TV Sala",
            protocol="web-receiver",
            transport="lan",
            paired_at=now,
            expires_at=now + timedelta(days=30),
        )
        d = r.to_dict()
        assert d["receiverId"] == "tv-1"
        assert d["displayName"] == "TV Sala"
        assert d["protocol"] == "web-receiver"
        assert "pairedAt" in d
