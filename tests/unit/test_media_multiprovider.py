# SPDX-License-Identifier: GPL-3.0-or-later
"""Orquestração remota degradável sem dependência fixa de provider."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from steamzero.adapters.emulation import EmulationController, SessionSecretStore
from steamzero.adapters.state_store_media import StateStoreGameMediaAdapter
from steamzero.core.errors import SteamZeroError, provider_error_category
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
        error_code: str | None = None,
    ) -> None:
        self._name = name
        self._kinds = frozenset(kinds)
        self._calls = calls
        self._failures = failures
        self._error_code = error_code

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
        if self._error_code is not None:
            raise SteamZeroError(self._error_code, detail="secret-in-detail")
        if self._failures > 0:
            self._failures -= 1
            raise SteamZeroError("E-SCRAPE-PROVIDER-UNREACHABLE", detail="secret-in-detail")
        if not media_kinds:
            return []
        kind = next(kind for kind in media_kinds if kind in self._kinds)
        return [
            MediaCandidate(
                url=f"https://media.invalid/{self.name}/{kind}.png",
                media_kind=kind,
                provider=self.name,
                confidence=0.9,
            )
        ]


class EmptyResultProvider(FakeProvider):
    """Provider saudável que nunca encontra candidato (resposta válida vazia)."""

    def search(
        self,
        _identity: GameIdentity,
        _media_kinds: list[str],
        _region_priority: list[str] | None = None,
    ) -> list[MediaCandidate]:
        self._calls.append(self.name)
        return []


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


def _plant_library(controller: EmulationController, tmp_path: Path, count: int) -> None:
    cache = controller._library_cache_path  # type: ignore[attr-defined]
    cache.parent.mkdir(parents=True, exist_ok=True)
    games = []
    for index in range(count):
        rom = tmp_path / f"Game{index}.nsp"
        rom.write_bytes(b"A" * 2048)
        games.append(
            {
                "id": f"game-{index}",
                "name": f"Game {index}",
                "state": "ready",
                "path": str(rom),
                "size": 2048,
                "titleId": f"0100ABCDEF0{index:02d}000",
            }
        )
    cache.write_text(
        json.dumps({"schemaVersion": 1, "games": games, "unidentified": 0}),
        encoding="utf-8",
    )


def _run_global(
    controller: EmulationController,
    *,
    mode: str = "refresh",
    overwrite: bool = False,
):
    job = controller._jobs.create(  # type: ignore[attr-defined]
        "media.global",
        params={"mode": mode, "overwrite": overwrite},
        priority="interactive",
        created_by="qam",
    )
    completed = controller._jobs.run(job.id)
    assert completed.state == "completed"
    assert isinstance(completed.result, dict)
    return completed.result


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
    assert result["provider_errors"] == {"steamgriddb": "E-SCRAPE-PROVIDER-UNREACHABLE"}
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


# =============================================================================
# G28 — resultado terminal do job global, quota e persistência
# =============================================================================


def _with_data_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))


def test_global_job_quota_interrupts_provider_for_remaining_games(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _with_data_home(monkeypatch, tmp_path)
    calls: list[str] = []
    provider = FakeProvider(
        "screenscraper",
        {"boxart"},
        calls,
        error_code="E-SCRAPE-QUOTA-EXCEEDED",
    )
    controller = _controller(tmp_path, [provider])
    _plant_library(controller, tmp_path, 3)

    result = _run_global(controller)

    assert calls == ["screenscraper"]  # quota na 1ª busca; 2ª e 3ª não chamam
    assert result["outcome"] == "degraded"
    assert result["processed"] == 3
    assert result["no_candidates"] == 2  # jogos restantes sem candidato e sem erro novo
    assert result["interrupted_providers"] == ["screenscraper"]
    assert result["provider_errors"] == {"screenscraper": "E-SCRAPE-QUOTA-EXCEEDED"}
    assert result["provider_details"]["screenscraper"]["category"] == "quota"
    assert result["provider_details"]["screenscraper"]["gamesAffected"] == 1


def test_global_job_healthy_provider_continues_after_other_quota(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _with_data_home(monkeypatch, tmp_path)
    calls: list[str] = []
    quota = FakeProvider("steamgriddb", {"grid"}, calls, error_code="E-SCRAPE-QUOTA-EXCEEDED")
    healthy = FakeProvider("screenscraper", {"boxart"}, calls)
    controller = _controller(tmp_path, [quota, healthy])
    _plant_library(controller, tmp_path, 3)

    result = _run_global(controller)

    assert calls == ["steamgriddb", "screenscraper", "screenscraper", "screenscraper"]
    assert result["outcome"] == "degraded"
    assert result["interrupted_providers"] == ["steamgriddb"]
    assert result["provider_errors"] == {"steamgriddb": "E-SCRAPE-QUOTA-EXCEEDED"}


def test_global_job_no_candidates_without_errors_is_partial(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _with_data_home(monkeypatch, tmp_path)
    calls: list[str] = []
    empty = EmptyResultProvider("screenscraper", {"boxart"}, calls)
    controller = _controller(tmp_path, [empty])
    _plant_library(controller, tmp_path, 2)

    result = _run_global(controller)

    assert result["outcome"] == "partial"
    assert result["no_candidates"] == 2
    assert result["provider_errors"] == {}
    assert result["interrupted_providers"] == []
    assert result["provider_details"] == {}


def test_global_job_success_outcome(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _with_data_home(monkeypatch, tmp_path)
    calls: list[str] = []
    provider = FakeProvider("steamgriddb", {"grid"}, calls)
    controller = _controller(tmp_path, [provider])
    _plant_library(controller, tmp_path, 2)

    result = _run_global(controller)

    assert result["outcome"] == "success"
    assert result["no_candidates"] == 0
    assert result["provider_errors"] == {}
    assert result["processed"] == 2


def test_global_job_invalid_mode_rejected_before_any_provider_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _with_data_home(monkeypatch, tmp_path)
    calls: list[str] = []
    provider = FakeProvider("screenscraper", {"boxart"}, calls)
    controller = _controller(tmp_path, [provider])
    _plant_library(controller, tmp_path, 2)

    job = controller._jobs.create(  # type: ignore[attr-defined]
        "media.global",
        params={"mode": "modo-inexistente"},
        priority="interactive",
        created_by="qam",
    )
    completed = controller._jobs.run(job.id)
    assert completed.state == "rolled-back"
    assert completed.error_code == "E-API-SCHEMA"
    assert calls == []


def test_global_job_result_persists_and_rebuilds_workspace_after_restart(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _with_data_home(monkeypatch, tmp_path)
    calls: list[str] = []
    quota = FakeProvider("screenscraper", {"boxart"}, calls, error_code="E-SCRAPE-QUOTA-EXCEEDED")
    controller = _controller(tmp_path, [quota])
    _plant_library(controller, tmp_path, 1)

    result = _run_global(controller)
    assert result["outcome"] == "degraded"

    healthy = FakeProvider("screenscraper", {"boxart"}, calls)
    restarted = _controller(tmp_path, [healthy])

    job_row = restarted._jobs.list_jobs(states=["completed"])  # type: ignore[attr-defined]
    assert len(job_row) == 1
    persisted = job_row[0].result
    assert persisted["outcome"] == "degraded"
    assert persisted["provider_errors"] == {"screenscraper": "E-SCRAPE-QUOTA-EXCEEDED"}

    with restarted._store_factory() as store:  # type: ignore[attr-defined]
        store.migrate()
        media = StateStoreGameMediaAdapter(store.adapter_connection())
        assert media.load("game-0") is not None
        assert media.load("game-0").errors == {"screenscraper": "E-SCRAPE-QUOTA-EXCEEDED"}

    summary = restarted._media_pipeline_summary(  # type: ignore[attr-defined]
        [
            {
                "id": "game-0",
                "titleId": "0100ABCDEF000000",
                "name": "Game 0",
                "mediaSource": "fallback",
                "mediaErrors": {"screenscraper": "E-SCRAPE-QUOTA-EXCEEDED"},
            }
        ]
    )
    assert summary["providerErrors"] == {"screenscraper": 1}
    details = summary["providerDetails"]["screenscraper"]
    assert details["code"] == "E-SCRAPE-QUOTA-EXCEEDED"
    assert details["category"] == "quota"
    assert details["state"] == "active"
    assert details["gamesAffected"] == 1


def test_later_successful_search_clears_persisted_error_and_health(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _with_data_home(monkeypatch, tmp_path)
    calls: list[str] = []
    failing = FakeProvider("screenscraper", {"boxart"}, calls, error_code="E-SCRAPE-QUOTA-EXCEEDED")
    controller = _controller(tmp_path, [failing])
    _plant_library(controller, tmp_path, 1)
    assert _run_global(controller)["outcome"] == "degraded"

    healthy = FakeProvider("screenscraper", {"boxart"}, calls)
    restarted = _controller(tmp_path, [healthy])
    _plant_library(restarted, tmp_path, 1)
    second = _run_global(restarted)
    assert second["outcome"] == "success"

    with restarted._store_factory() as store:  # type: ignore[attr-defined]
        store.migrate()
        media = StateStoreGameMediaAdapter(store.adapter_connection())
        assert media.load("game-0").errors == {}

    summary = restarted._media_pipeline_summary(  # type: ignore[attr-defined]
        [{"id": "game-0", "titleId": "0100ABCDEF000000", "name": "Game 0"}]
    )
    assert summary["providerErrors"] == {}
    assert summary["providerDetails"] == {}


def test_provider_health_persists_code_category_and_no_secrets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _with_data_home(monkeypatch, tmp_path)
    calls: list[str] = []
    failing = FakeProvider("screenscraper", {"boxart"}, calls, error_code="E-SCRAPE-RATE-LIMITED")
    controller = _controller(tmp_path, [failing])
    _plant_library(controller, tmp_path, 1)
    _run_global(controller)

    restarted = _controller(tmp_path, [])
    with restarted._store_factory() as store:  # type: ignore[attr-defined]
        store.migrate()
        from steamzero.adapters.state_store_provider_health import (
            StateStoreProviderHealthAdapter,
        )

        health = StateStoreProviderHealthAdapter(store.adapter_connection()).load("screenscraper")
        assert health is not None
        assert health.last_error_code == "E-SCRAPE-RATE-LIMITED"
        assert health.last_error_category == "rate-limit"
        assert health.error_count == 1
        assert health.total_requests == 1
        assert "secret-in-detail" not in (health.last_error or "")
        assert health.last_error is not None


def test_error_categories_are_stable() -> None:
    assert provider_error_category("E-SCRAPE-QUOTA-EXCEEDED") == "quota"
    assert provider_error_category("E-SCRAPE-RATE-LIMITED") == "rate-limit"
    assert provider_error_category("E-SCRAPE-CREDENTIAL-REJECTED") == "auth"
    assert provider_error_category("E-SCRAPE-CREDENTIAL-MISSING") == "auth"
    assert provider_error_category("E-SCRAPE-PROVIDER-UNREACHABLE") == "unreachable"
    assert provider_error_category("E-NET-HTTP") == "http"
    assert provider_error_category("E-SCRAPE-DOWNLOAD-FAILED") == "download"
    assert provider_error_category("E-CODIGO-DESCONHECIDO") == "generic"
