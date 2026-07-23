# SPDX-License-Identifier: GPL-3.0-or-later
"""Orquestração remota degradável sem dependência fixa de provider."""

from __future__ import annotations

from pathlib import Path

import pytest

from steamzero.adapters.emulation import EmulationController, SessionSecretStore
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore
from steamzero.ports import GameIdentity, MediaCandidate


class FakeProvider:
    def __init__(
        self,
        name: str,
        kinds: set[str],
        calls: list[str],
        *,
        failures: int = 0,
    ) -> None:
        self._name = name
        self._kinds = frozenset(kinds)
        self._calls = calls
        self._failures = failures

    @property
    def name(self) -> str:
        return self._name

    def supported_kinds(self) -> frozenset[str]:
        return self._kinds

    def supported_platforms(self) -> frozenset[str]:
        return frozenset({"switch"})

    def search(
        self,
        _identity: GameIdentity,
        media_kinds: list[str],
        _region_priority: list[str] | None = None,
    ) -> list[MediaCandidate]:
        self._calls.append(self.name)
        if self._failures > 0:
            self._failures -= 1
            raise SteamZeroError("E-SCRAPE-PROVIDER-UNREACHABLE", detail="secret-in-detail")
        kind = next(kind for kind in media_kinds if kind in self._kinds)
        return [
            MediaCandidate(
                url=f"https://media.invalid/{self.name}/{kind}.png",
                media_kind=kind,
                provider=self.name,
                confidence=0.9,
            )
        ]


def _controller(
    tmp_path: Path,
    providers: list[FakeProvider],
    *,
    delays: list[float] | None = None,
) -> EmulationController:
    return EmulationController(
        store_factory=lambda: StateStore(tmp_path / "state.db"),
        which=lambda _command: None,
        spawn=lambda _argv: None,
        secret_store=SessionSecretStore(),
        media_providers=providers,
        media_retry_delay=(delays.append if delays is not None else lambda _delay: None),
    )


def _run_search(
    controller: EmulationController, media_kinds: list[str] | None = None
) -> dict[str, object]:
    job = controller._jobs.create(
        "media.search",
        params={
            "game_id": "game-1",
            "title_id": "0100ABCDEF123000",
            "title": "Game",
            "media_kinds": media_kinds,
            "local_media_source": "emulator-cache",
        },
        priority="interactive",
        created_by="qam",
    )
    completed = controller._jobs.run(job.id)
    assert completed.state == "completed"
    assert isinstance(completed.result, dict)
    return completed.result


@pytest.mark.parametrize(
    ("provider_names", "media_kinds", "expected_calls", "candidate_count"),
    [
        (["steamgriddb"], ["grid"], ["steamgriddb"], 1),
        (["screenscraper"], ["boxart"], ["screenscraper"], 1),
        (
            ["steamgriddb", "screenscraper"],
            None,
            ["steamgriddb", "screenscraper"],
            2,
        ),
        ([], None, [], 0),
    ],
)
def test_search_with_each_provider_combination(
    tmp_path: Path,
    provider_names: list[str],
    media_kinds: list[str] | None,
    expected_calls: list[str],
    candidate_count: int,
) -> None:
    calls: list[str] = []
    providers = [
        FakeProvider(
            name,
            {"grid", "hero", "logo", "icon"}
            if name == "steamgriddb"
            else {"boxart", "screenshot", "manual"},
            calls,
        )
        for name in provider_names
    ]
    result = _run_search(_controller(tmp_path, providers), media_kinds)
    assert calls == expected_calls
    assert result["candidate_count"] == candidate_count
    assert result["provider_errors"] == {}
    if not providers:
        assert result["remote_state"] == "degraded"
        assert result["fallback_source"] == "emulator-cache"


def test_provider_failure_does_not_cancel_next_provider_or_leak_detail(
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    steamgriddb = FakeProvider(
        "steamgriddb",
        {"grid"},
        calls,
        failures=3,
    )
    screenscraper = FakeProvider("screenscraper", {"boxart"}, calls)
    result = _run_search(
        _controller(tmp_path, [steamgriddb, screenscraper]),
        ["grid", "boxart"],
    )
    assert calls == ["steamgriddb", "steamgriddb", "steamgriddb", "screenscraper"]
    assert result["candidate_count"] == 1
    assert result["provider_errors"] == {
        "steamgriddb": "E-SCRAPE-PROVIDER-UNREACHABLE"
    }
    assert "secret-in-detail" not in str(result)


def test_retry_uses_bounded_exponential_backoff_then_succeeds(tmp_path: Path) -> None:
    calls: list[str] = []
    delays: list[float] = []
    provider = FakeProvider("screenscraper", {"boxart"}, calls, failures=2)
    result = _run_search(
        _controller(tmp_path, [provider], delays=delays),
        ["boxart"],
    )
    assert result["candidate_count"] == 1
    assert result["provider_errors"] == {}
    assert calls == ["screenscraper", "screenscraper", "screenscraper"]
    assert delays == [0.25, 0.5]
