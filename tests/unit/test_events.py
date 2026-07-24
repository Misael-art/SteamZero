# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contrato event-v1 paginado e follow reconectável."""

from __future__ import annotations

from pathlib import Path

import pytest

from steamzero.api import contracts
from steamzero.api.events import (
    JOB_EVENT_KINDS,
    JOB_TERMINAL_STATES,
    SYSTEM_CORRELATION_ID,
    event_page,
    follow_events,
    parse_event_cursor,
)
from steamzero.core import state
from steamzero.core.errors import build_error


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    value = state.open_state()
    yield value
    value.close()


def test_event_page_serializes_live_job_units_and_correlation(store) -> None:  # type: ignore[no-untyped-def]
    store.save_job(
        {
            "id": "J1",
            "type": "catalog.search",
            "priority": "interactive",
            "state": "running",
            "correlation_id": "01J000000000000000000000AA",
        }
    )
    store.append_event(
        "job.progress",
        entity="job:J1",
        payload={
            "stage": "download",
            "current": 1,
            "total": 4,
            "unit": "catalogs",
        },
    )

    page = event_page(store, cursor="0", kinds=JOB_EVENT_KINDS)

    assert page.cursor == str(page.events[0]["seq"])
    assert page.events[0]["jobId"] == "J1"
    assert page.events[0]["correlationId"] == "01J000000000000000000000AA"
    assert page.events[0]["progress"]["unit"] == "catalogs"
    contracts.validate(page.events[0], "event-v1.schema.json")
    assert page.to_dict()["count"] == 1


def test_follow_drains_pages_and_resumes_without_duplicates(store) -> None:  # type: ignore[no-untyped-def]
    for current in range(5):
        store.append_event(
            "job.progress",
            entity="job:J1",
            payload={
                "stage": "scan",
                "current": current,
                "total": 5,
                "unit": "items",
            },
        )

    first = list(
        follow_events(
            store,
            cursor="0",
            kinds=JOB_EVENT_KINDS,
            limit=2,
            poll_interval=0,
            idle_timeout=0,
        )
    )
    assert [event["seq"] for event in first] == sorted(
        event["seq"] for event in first
    )
    assert len(first) == 5

    resumed = list(
        follow_events(
            store,
            cursor=str(first[2]["seq"]),
            kinds=JOB_EVENT_KINDS,
            limit=2,
            poll_interval=0,
            idle_timeout=0,
        )
    )
    assert [event["seq"] for event in resumed] == [
        first[3]["seq"],
        first[4]["seq"],
    ]


def test_operation_event_uses_system_correlation_and_schema(store) -> None:  # type: ignore[no-untyped-def]
    store.save_operation("01J000000000000000000000AB", state="committed")

    page = event_page(store, cursor="0", kinds=("operation.state",))

    event = page.events[0]
    assert event["operationId"] == "01J000000000000000000000AB"
    assert event["state"] == "committed"
    assert event["correlationId"] == SYSTEM_CORRELATION_ID
    contracts.validate(event, "event-v1.schema.json")


def test_public_event_projection_covers_system_session_and_alert_payloads(store) -> None:  # type: ignore[no-untyped-def]
    store.append_event(
        "session.state",
        entity="session:S1",
        payload={
            "state": "running",
            "gameId": "10",
            "correlationId": "01J000000000000000000000AC",
        },
    )
    store.append_event(
        "session.environment",
        entity="session-environment:current",
        payload={"digest": "a" * 64, "changes": ["display", "power"]},
    )
    store.append_event(
        "session.resume",
        entity="system-session:current",
        payload={"suspendedSeconds": 12.5},
    )
    store.append_event(
        "alert",
        entity=None,
        payload={"error": build_error("E-INTERNAL-UNEXPECTED")},
    )
    store.append_event("entity.changed", entity=None, payload=None)

    page = event_page(store, cursor=None)

    by_kind = {event["kind"]: event for event in page.events}
    assert by_kind["session.state"]["sessionId"] == "S1"
    assert by_kind["session.state"]["gameId"] == "10"
    assert (
        by_kind["session.state"]["correlationId"]
        == "01J000000000000000000000AC"
    )
    assert by_kind["session.environment"]["changes"] == ["display", "power"]
    assert by_kind["session.resume"]["suspendedSeconds"] == 12.5
    assert by_kind["alert"]["error"]["code"] == "E-INTERNAL-UNEXPECTED"
    for event in page.events:
        contracts.validate(event, "event-v1.schema.json")


def test_event_projection_degrades_malformed_private_payloads(store) -> None:  # type: ignore[no-untyped-def]
    store._conn.execute(  # type: ignore[attr-defined]
        "INSERT INTO event_log (ts,kind,entity,payload_json) VALUES (?,?,?,?)",
        ("2026-07-23T00:00:00+00:00", "job.state", "job:missing", "{"),
    )
    store._conn.execute(  # type: ignore[attr-defined]
        "INSERT INTO event_log (ts,kind,entity,payload_json) VALUES (?,?,?,?)",
        ("2026-07-23T00:00:01+00:00", "entity.changed", None, "[]"),
    )
    store.append_event("job.state", entity=None, payload={"state": "queued"})
    store.append_event(
        "job.state", entity="Jlegacy", payload={"state": "running"}
    )

    page = event_page(store, cursor="0")

    assert page.events[0]["correlationId"] == SYSTEM_CORRELATION_ID
    assert "state" not in page.events[0]
    assert page.events[1]["correlationId"] == SYSTEM_CORRELATION_ID
    assert "jobId" not in page.events[2]
    assert page.events[3]["jobId"] == "Jlegacy"


def test_follow_validates_polling_and_stops_on_terminal_state(store) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError, match="poll_interval"):
        list(follow_events(store, cursor="0", kinds=JOB_EVENT_KINDS, poll_interval=-1))
    with pytest.raises(ValueError, match="idle_timeout"):
        list(
            follow_events(
                store,
                cursor="0",
                kinds=JOB_EVENT_KINDS,
                idle_timeout=-1,
            )
        )

    store.append_event(
        "job.state", entity="job:J1", payload={"state": "completed"}
    )
    store.append_event(
        "job.state", entity="job:J1", payload={"state": "queued"}
    )
    followed = list(
        follow_events(
            store,
            cursor="0",
            kinds=JOB_EVENT_KINDS,
            poll_interval=0,
            idle_timeout=0,
            terminal_states=JOB_TERMINAL_STATES,
        )
    )
    assert [event["state"] for event in followed] == ["completed"]


def test_follow_waits_until_idle_timeout_when_no_event_arrives(store) -> None:  # type: ignore[no-untyped-def]
    assert (
        list(
            follow_events(
                store,
                cursor=None,
                kinds=JOB_EVENT_KINDS,
                poll_interval=0.001,
                idle_timeout=0.002,
            )
        )
        == []
    )


@pytest.mark.parametrize(
    "cursor",
    ["-1", "+1", "1.0", "x", "9" * 20, "9223372036854775808"],
)
def test_event_cursor_rejects_ambiguous_or_out_of_range_values(cursor: str) -> None:
    with pytest.raises(ValueError, match="cursor"):
        parse_event_cursor(cursor)
