# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from audit_desktop_bridge import LIFECYCLE_SURFACES, audit  # noqa: E402


def test_lifecycle_inventory_classifies_every_public_method() -> None:
    report = audit()
    assert {item["method"] for item in report["lifecycleDiscoveries"]} == set(
        report["lifecycleMethods"]
    )
    assert set(LIFECYCLE_SURFACES) == set(report["lifecycleMethods"])


def test_audit_reports_only_the_remaining_unpublished_lifecycle_actions() -> None:
    report = audit()
    missing = {item["subject"] for item in report["issues"] if item["kind"] == "missing-contract"}
    assert {"open_config", "rollback", "recover", "stop"} <= missing
    assert not {"status", "status_all", "verify"} & missing
    serialized = str(report)
    assert "/home/" not in serialized
    assert "confirmToken" not in serialized


def test_audit_rejects_contracts_with_open_input_schema() -> None:
    report = audit()
    assert "emulation.action.plan" in {
        item["subject"] for item in report["issues"] if item["kind"] == "open-schema"
    }
