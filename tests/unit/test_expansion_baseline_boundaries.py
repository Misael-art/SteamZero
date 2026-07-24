# SPDX-License-Identifier: GPL-3.0-or-later
"""Boundary tests that restore coverage without contacting host services."""

from __future__ import annotations

import subprocess
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from steamzero.adapters.desktop_dashboard import (
    DesktopDashboard,
    SteamDesktopController,
    _steam_process_running,
)
from steamzero.adapters.registry import AdapterRegistry
from steamzero.adapters.scraping.base import BaseMediaProvider, RateLimiter, TokenBucket
from steamzero.core.errors import SteamZeroError
from steamzero.ports import GameIdentity, MediaCandidate


class _Provider(BaseMediaProvider):
    @property
    def name(self) -> str:
        return "fixture"

    def supported_kinds(self) -> frozenset[str]:
        return frozenset({"boxart"})

    def supported_platforms(self) -> frozenset[str]:
        return frozenset({"switch"})

    def search(
        self,
        identity: GameIdentity,
        media_kinds: list[str],
        region_priority: list[str] | None = None,
    ) -> list[MediaCandidate]:
        del identity, media_kinds, region_priority
        return []


class _Response:
    def __init__(
        self,
        chunks: list[bytes],
        *,
        final_url: str = "https://example.invalid/media",
        declared: str | None = None,
    ) -> None:
        self._chunks = iter(chunks)
        self._url = final_url
        self.headers = {} if declared is None else {"Content-Length": declared}

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, _size: int = -1) -> bytes:
        return next(self._chunks, b"")

    def geturl(self) -> str:
        return self._url


def test_rate_limiter_and_media_provider_success_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError):
        TokenBucket(0, 1)
    with pytest.raises(ValueError):
        TokenBucket(1, 0)

    ticks = iter([10.0, 10.0, 10.5, 10.5, 11.0, 11.0, 11.0, 11.0])
    monkeypatch.setattr("time.monotonic", lambda: next(ticks))
    bucket = TokenBucket(1, 1)
    assert bucket.acquire() == 0
    assert bucket.acquire() == pytest.approx(0.5)

    sleeps: list[float] = []
    monkeypatch.setattr("time.sleep", sleeps.append)
    bucket.wait_if_needed()
    assert sleeps
    limiter = RateLimiter("fixture", requests_per_second=10, burst=2)
    limiter.acquire()

    provider = _Provider(rate_limiter=limiter)
    provider._rate_limit()
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_a, **_k: _Response([b"\x89PNG\r\n\x1a\n", b"fixture"]),
    )
    data = provider._fetch_url("https://example.invalid/media")
    assert data.startswith(b"\x89PNG")
    assert provider._validate_media(data) == ".png"
    assert provider._validate_media(b"\xff\xd8\xffx") == ".jpg"
    assert provider._validate_media(b"RIFFxxxxWEBP") == ".webp"
    assert provider._validate_media(b"x") is None
    assert provider._validate_media(b"xxxx") is None
    assert provider._media_hash(b"fixture")
    assert provider._normalize_platform("switch") == "switch"


def test_media_provider_rejects_unsafe_redirect_size_and_http_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _Provider()
    with pytest.raises(SteamZeroError):
        provider._fetch_url("file:///tmp/media")

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_a, **_k: _Response([], final_url="file:///tmp/redirect"),
    )
    with pytest.raises(SteamZeroError):
        provider._fetch_url("https://example.invalid/media")

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_a, **_k: _Response([], declared="20"),
    )
    with pytest.raises(SteamZeroError):
        provider._fetch_url("https://example.invalid/media", max_bytes=10)

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_a, **_k: _Response([b"12345678901"]),
    )
    with pytest.raises(SteamZeroError):
        provider._fetch_url("https://example.invalid/media", max_bytes=10)

    for status, code in [
        (429, "E-SCRAPE-RATE-LIMITED"),
        (403, "E-SCRAPE-QUOTA-EXCEEDED"),
        (404, "E-SCRAPE-NOT-FOUND"),
        (500, "E-SCRAPE-PROVIDER-UNREACHABLE"),
    ]:
        monkeypatch.setattr(
            "urllib.request.urlopen",
            lambda *_a, _status=status, **_k: (_ for _ in ()).throw(
                urllib.error.HTTPError("https://example.invalid", _status, "fixture", {}, None)
            ),
        )
        with pytest.raises(SteamZeroError) as exc:
            provider._fetch_url("https://example.invalid/media")
        assert exc.value.code == code

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_a, **_k: (_ for _ in ()).throw(urllib.error.URLError("offline")),
    )
    with pytest.raises(SteamZeroError) as exc:
        provider._fetch_url("https://example.invalid/media")
    assert exc.value.code == "E-SCRAPE-PROVIDER-UNREACHABLE"


def test_steam_desktop_rows_and_allowlisted_launches() -> None:
    spawned: list[tuple[str, ...]] = []
    controller = SteamDesktopController(
        which=lambda name: "/usr/bin/steam" if name == "steam" else None,
        running_probe=lambda: True,
        spawn=lambda argv: spawned.append(tuple(argv)),
    )
    rows = controller.rows(
        {"context": {"capabilities": ["steam-keyboard", 1], "conflicts": ["input"]}}
    )
    assert rows[0]["state"] == "running"
    assert rows[2]["state"] == "blocked"
    assert rows[3]["state"] == "available"
    assert controller.open("library")["status"] == "started"
    assert controller.open_controller_config("123")["status"] == "started"
    assert spawned[-1][-1] == "steam://controllerconfig/123"
    with pytest.raises(SteamZeroError):
        controller.open("external")
    with pytest.raises(SteamZeroError):
        controller.open_controller_config("../bad")

    missing = SteamDesktopController(which=lambda _name: None)
    missing_rows = missing.rows({"context": "bad"})
    assert missing_rows[0]["state"] == "missing"
    with pytest.raises(SteamZeroError):
        missing.open("home")
    with pytest.raises(SteamZeroError):
        missing.open_controller_config("123")


def test_dashboard_delegates_all_registered_controller_actions(tmp_path: Path) -> None:
    dashboard = object.__new__(DesktopDashboard)
    emulation = MagicMock()
    gameplay = MagicMock()
    diagnostics = MagicMock()
    steam = MagicMock()
    marker = {"marker": True}
    for mock in (emulation, gameplay, diagnostics, steam):
        for child in mock._mock_children.values():
            child.return_value = marker
    dashboard._emulation = emulation
    dashboard._gameplay = gameplay
    dashboard._diagnostics = diagnostics
    dashboard._steam = steam
    dashboard._doctor_runner = lambda: ({"status": "ok"}, [])

    emulation.plan_emulator.return_value = marker
    emulation.apply_emulator.return_value = marker
    emulation.launch_emulator.return_value = marker
    emulation.stop_emulator.return_value = marker
    emulation.launch_game.return_value = marker
    emulation.launch_cloud.return_value = marker
    emulation.plan_action.return_value = marker
    emulation.apply_action.return_value = marker
    emulation.rollback_action.return_value = marker
    emulation.scan_library.return_value = marker
    emulation.get_job_status.return_value = marker
    emulation.list_jobs.return_value = [marker]
    emulation.cancel_job.return_value = marker
    emulation.retry_job.return_value = marker
    emulation.credential_status.return_value = marker
    emulation.save_credential.return_value = marker
    emulation.test_credential.return_value = marker
    emulation.delete_credential.return_value = marker
    emulation.provider_link.return_value = marker

    assert dashboard.plan_emulation_emulator("emu", "install") == marker
    assert dashboard.apply_emulation_emulator("p", "t") == marker
    assert dashboard.launch_emulation_emulator("emu") == marker
    assert dashboard.stop_emulation_emulator("emu") == marker
    assert dashboard.launch_emulation_game("g") == marker
    assert dashboard.launch_cloud_platform("xbox-cloud-gaming") == marker
    assert dashboard.plan_emulation_action({"action": "x"}) == marker
    assert dashboard.apply_emulation_action("p", "t") == marker
    assert dashboard.rollback_emulation_action("o") == marker
    assert dashboard.scan_emulation_library() == marker
    assert dashboard.get_emulation_job_status("j") == marker
    assert dashboard.list_emulation_jobs() == [marker]
    assert dashboard.cancel_emulation_job("j") == marker
    assert dashboard.retry_emulation_job("j") == marker
    assert dashboard.credential_status() == marker
    assert dashboard.save_credential("p", {"key": "value"}) == marker
    assert dashboard.test_credential("p") == marker
    assert dashboard.delete_credential("p") == marker
    assert dashboard.scraping_provider_link("p", "home") == marker

    diagnostics.operations.return_value = marker
    diagnostics.admin_health.return_value = marker
    diagnostics.apply_export.return_value = SimpleNamespace(status="committed", operation_id="o")
    plan = SimpleNamespace(
        plan_id="p",
        confirm_token="t",
        preview={"actions": []},
        rollback_guarantee="G-FULL",
        requirements={},
    )
    diagnostics.plan_export.return_value = (plan, {"files": []})
    assert dashboard.operations_history(1, 20) == marker
    assert dashboard.plan_diagnostics_export(tmp_path, "state", {})["plan"]["planId"] == "p"
    assert dashboard.apply_diagnostics_export("p", "t")["operationId"] == "o"
    assert dashboard.admin_health() == marker

    delegated_calls = [
        (dashboard.hud_presets, ()),
        (dashboard.plan_steam_gameplay, ({"x": 1}, {})),
        (dashboard.apply_steam_gameplay, ("p", "t", {})),
        (dashboard.rollback_steam_gameplay, ("o",)),
        (dashboard.recover_steam_gameplay, ("g",)),
        (dashboard.plan_steam_launch_options, ("g",)),
        (dashboard.apply_steam_launch_options, ("p", "t", "g")),
        (dashboard.rollback_steam_launch_options, ("o",)),
        (dashboard.plan_steam_maintenance, ("g", ["shader"])),
        (dashboard.apply_steam_maintenance, ("p", "t", "CONFIRM")),
        (dashboard.recover_steam_maintenance, ()),
        (dashboard.plan_steam_media, ("g", "a", tmp_path)),
        (dashboard.apply_steam_media, ("p", "t")),
        (dashboard.rollback_steam_media, ("o",)),
        (dashboard.plan_lsfg_install, ()),
        (dashboard.apply_lsfg_install, ("p", "t")),
        (dashboard.rollback_lsfg_install, ("o",)),
    ]
    for method, args in delegated_calls:
        method(*args)

    steam.open.return_value = marker
    steam.open_controller_config.return_value = marker
    assert dashboard.open_steam("home") == marker
    assert dashboard.open_steam_input("123") == marker
    assert DesktopDashboard._conflicts({"context": {"conflicts": ["a", 1]}}) == ["a"]
    assert DesktopDashboard._conflicts({"context": "bad"}) == []
    assert DesktopDashboard._conflicts({"context": {"conflicts": "bad"}}) == []


def test_spawn_boundary_uses_fixed_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def popen(argv: list[str], **kwargs: object) -> SimpleNamespace:
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return SimpleNamespace(pid=1)

    monkeypatch.setattr(subprocess, "Popen", popen)
    from steamzero.adapters.desktop_dashboard import _spawn_detached

    _spawn_detached(("/usr/bin/steam", "steam://open/main"))
    assert captured["argv"] == ["/usr/bin/steam", "steam://open/main"]
    assert captured["kwargs"]


def test_component_rows_cover_missing_degraded_installed_and_eol_states() -> None:
    dashboard = object.__new__(DesktopDashboard)
    registry = AdapterRegistry.bundled()

    class Executor:
        def __init__(self, status: dict[str, object] | BaseException) -> None:
            self._status = status

        def status(self, _adapter_id: str) -> dict[str, object]:
            if isinstance(self._status, BaseException):
                raise self._status
            return self._status

    dolphin = registry.get("dolphin")
    missing = dashboard._component_row(
        dolphin,
        Executor({"state": "missing", "pinned": True, "endOfLife": False}),  # type: ignore[arg-type]
        conflicts=False,
    )
    assert missing["state"] == "missing"
    assert missing["action"]["enabled"] is True
    blocked = dashboard._component_row(
        dolphin,
        Executor({"state": "degraded", "pinned": True, "endOfLife": False}),  # type: ignore[arg-type]
        conflicts=True,
    )
    assert blocked["state"] == "attention"
    assert blocked["action"]["enabled"] is False
    installed = dashboard._component_row(
        dolphin,
        Executor(
            {
                "state": "installed",
                "pinned": True,
                "endOfLife": False,
                "commit": "a" * 64,
            }
        ),  # type: ignore[arg-type]
        conflicts=False,
    )
    assert installed["state"] == "installed"
    assert installed["action"]["label"] == "Configurar"

    duckstation = registry.get("duckstation")
    eol = dashboard._component_row(
        duckstation,
        Executor({"state": "missing", "pinned": True, "endOfLife": True}),  # type: ignore[arg-type]
        conflicts=False,
    )
    assert eol["state"] == "unsupported"
    degraded = dashboard._component_row(
        dolphin,
        Executor(RuntimeError("fixture")),  # type: ignore[arg-type]
        conflicts=False,
    )
    assert degraded["state"] == "attention"
    assert "fixture" in degraded["detail"]


def test_steam_process_probe_is_read_only_and_total() -> None:
    assert isinstance(_steam_process_running(), bool)
