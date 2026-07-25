# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from steamzero.api.envelope import build_envelope, status_from_checks


def test_status_from_checks_ok_when_no_issues() -> None:
    assert status_from_checks([]) == "ok"


def test_status_from_checks_ok_when_all_good() -> None:
    checks = [{"status": "ok"}, {"status": "ok"}]
    assert status_from_checks(checks) == "ok"


def test_status_from_checks_failed_on_fail() -> None:
    checks = [{"status": "ok"}, {"status": "fail"}, {"status": "warn"}]
    assert status_from_checks(checks) == "failed"


def test_status_from_checks_degraded_on_warn() -> None:
    checks = [{"status": "ok"}, {"status": "warn"}]
    assert status_from_checks(checks) == "degraded"


def test_build_envelope_ok_derives_ok() -> None:
    env = build_envelope("test", "test", status="ok")
    assert env["ok"] is True
    assert env["status"] == "ok"


def test_build_envelope_explicit_ok_passed_through() -> None:
    env = build_envelope("test", "test", status="failed", ok=False)
    assert env["ok"] is False
