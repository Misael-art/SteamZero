# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contrato de nome apresentado do tema.

Tres conceitos estavam misturados: o ID tecnico (org.steamzero.aura), o nome
apresentado (AURA) e o estado operacional. O backend usava o ID como fallback
de ``activeName``, entao um tema sem entrada valida no catalogo aparecia na
interface como "org.steamzero.algo". Estes testes fixam a separacao.
"""

from __future__ import annotations

from typing import Any

import pytest

from steamzero.adapters.desktop_dashboard import DesktopDashboard


class _FakeCatalog:
    def __init__(self, entries: list[dict[str, Any]]) -> None:
        self._entries = entries

    def list_catalog(self) -> list[dict[str, Any]]:
        return self._entries

    def resolve(self, *_args: object, **_kwargs: object) -> Any:
        raise RuntimeError("resolucao nao importa para o contrato de nome")


class _FakePrefs:
    def __init__(self, theme_id: str | None) -> None:
        self._theme_id = theme_id

    def _read_preference(self) -> dict[str, Any] | None:
        return {"themeId": self._theme_id} if self._theme_id else None


def _entry(theme_id: str, name: str, state: str = "available") -> dict[str, Any]:
    return {
        "id": theme_id,
        "name": name,
        "version": "1.0.0",
        "author": "SteamZero",
        "origin": "builtin",
        "state": state,
        "compatible": True,
    }


def _state(dashboard: DesktopDashboard) -> dict[str, Any]:
    return dashboard._theme_state()  # type: ignore[attr-defined]


@pytest.fixture
def dashboard() -> DesktopDashboard:
    return DesktopDashboard.__new__(DesktopDashboard)


def _wire(
    dashboard: DesktopDashboard, entries: list[dict[str, Any]], active: str | None
) -> DesktopDashboard:
    dashboard._theme_catalog = _FakeCatalog(entries)  # type: ignore[attr-defined]
    dashboard._theme_prefs = _FakePrefs(active)  # type: ignore[attr-defined]
    dashboard._high_contrast_probe = lambda: False  # type: ignore[attr-defined]
    dashboard._reduced_motion_probe = lambda: False  # type: ignore[attr-defined]
    return dashboard


def test_active_name_is_the_display_name(dashboard: DesktopDashboard) -> None:
    _wire(dashboard, [_entry("org.steamzero.aura", "AURA")], "org.steamzero.aura")
    result = _state(dashboard)
    assert result["activeName"] == "AURA"
    assert result["activeKnown"] is True
    assert result["activeId"] == "org.steamzero.aura"


def test_unknown_active_theme_does_not_leak_the_technical_id(
    dashboard: DesktopDashboard,
) -> None:
    """O defeito original: o ID virava o nome exibido."""
    _wire(dashboard, [_entry("org.steamzero.outro", "Outro")], "org.steamzero.sumiu")
    result = _state(dashboard)
    assert result["activeName"] == ""
    assert result["activeKnown"] is False
    assert "org.steamzero.sumiu" not in result["activeName"]


def test_installed_but_unavailable_theme_is_not_reported_as_named(
    dashboard: DesktopDashboard,
) -> None:
    """Instalado e ativo sao estados diferentes; state != available nao nomeia."""
    _wire(
        dashboard,
        [_entry("org.steamzero.aura", "AURA", state="incompatible")],
        "org.steamzero.aura",
    )
    result = _state(dashboard)
    assert result["activeKnown"] is False
    assert result["activeName"] == ""


def test_every_entry_exposes_display_name_and_active_flag(
    dashboard: DesktopDashboard,
) -> None:
    _wire(
        dashboard,
        [_entry("org.steamzero.aura", "AURA"), _entry("org.esde.nso", "NSO Menu")],
        "org.steamzero.aura",
    )
    available = _state(dashboard)["available"]
    assert [e["displayName"] for e in available] == ["AURA", "NSO Menu"]
    assert [e["active"] for e in available] == [True, False]
