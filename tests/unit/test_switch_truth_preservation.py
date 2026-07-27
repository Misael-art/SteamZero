# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""A verdade do Switch sobrevive a falhas e a trocas de geração.

O sintoma relatado na a37 foi "as keys e o firmware deixaram de aparecer". Os
dados NUNCA foram apagados: uma exceção no adapter de emulação era engolida e o
dashboard recompunha a central com o builder sem argumentos, que produz
keys/firmware ``unverified`` e biblioteca vazia. Para quem olha a tela, isso é
indistinguível de perda de dados.

Todas as fixtures aqui são sintéticas. Nenhum teste lê keys, firmware ou ROMs
reais (AGENTS.md).
"""

from __future__ import annotations

from typing import Any

import pytest

from steamzero.domain.emulation_workspace import build_switch_workspace


def _requirement(kind: str, installed: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "status": "ok",
        "required": installed,
        "installed": installed,
        "detail": f"{kind} catalogado.",
        "blocksPlay": False,
    }


def _games(count: int) -> list[dict[str, Any]]:
    return [
        {
            "id": f"jogo-{i}",
            "name": f"Jogo {i}",
            "titleId": f"0100{i:012X}",
            "state": "ready",
            "statusLabel": "Pronto",
        }
        for i in range(count)
    ]


def _healthy_workspace() -> dict[str, Any]:
    """Equivalente sintético do host descrito no diagnóstico: keys rev21,
    firmware 22.5.0, 15 jogos e os três emuladores instalados."""
    return build_switch_workspace(
        probe=lambda _emulator_id: True,
        keys=_requirement("keys", "rev21"),
        firmware=_requirement("firmware", "22.5.0"),
        games=_games(15),
    )


def _switch(payload: dict[str, Any]) -> dict[str, Any]:
    return next(p for p in payload["platforms"] if p["id"] == "switch")


class TestHealthySnapshotIsComplete:
    def test_keys_and_firmware_are_reported_as_installed(self) -> None:
        switch = _switch(_healthy_workspace())
        assert switch["requirements"]["keys"]["installed"] == "rev21"
        assert switch["requirements"]["firmware"]["installed"] == "22.5.0"

    def test_library_is_present(self) -> None:
        assert len(_switch(_healthy_workspace())["games"]) == 15

    def test_the_three_emulators_are_installed(self) -> None:
        emulators = _switch(_healthy_workspace())["emulators"]
        by_id = {row["id"]: row for row in emulators}
        for emulator_id in ("eden", "citron", "ryubing"):
            assert by_id[emulator_id]["installState"] == "installed"

    def test_emulator_icons_come_from_the_adapter_contract(self) -> None:
        """O builder de domínio não publica ícone: quem o faz é o adapter, via
        _EMULATOR_PRESENTATION. Registrado aqui para que a divergência de camada
        seja explícita — test_packaged_assets.py garante que esses ícones estão
        empacotados e allowlistados."""
        from steamzero.adapters.emulation import _EMULATOR_PRESENTATION

        rows = {row["id"] for row in _switch(_healthy_workspace())["emulators"]}
        assert {"eden", "citron", "ryubing"} <= rows
        for emulator_id in rows & set(_EMULATOR_PRESENTATION):
            assert _EMULATOR_PRESENTATION[emulator_id][1], f"{emulator_id} sem ícone declarado"

    def test_switch_declares_fallback_artwork(self) -> None:
        assert _switch(_healthy_workspace())["fallbackArtworkAsset"]

    def test_readiness_is_ready_when_everything_checks_out(self) -> None:
        assert _healthy_workspace()["truthState"] == "ready"


class TestSimplifiedBuilderIsNotTheTruth:
    """O builder sem argumentos NÃO pode ser usado para substituir um snapshot real."""

    def test_bare_builder_erases_installed_versions(self) -> None:
        """Isto documenta o mecanismo do sintoma, não um comportamento desejado."""
        bare = _switch(build_switch_workspace())
        assert bare["requirements"]["keys"]["installed"] is None
        assert bare["requirements"]["keys"]["status"] == "unverified"
        assert bare["games"] == []

    def test_healthy_and_bare_differ_exactly_where_it_hurts(self) -> None:
        healthy = _switch(_healthy_workspace())
        bare = _switch(build_switch_workspace())
        assert healthy["requirements"]["keys"]["status"] == "ok"
        assert bare["requirements"]["keys"]["status"] == "unverified"


class TestDashboardPreservesTruthOnFailure:
    """Uma exceção no adapter não pode reescrever keys, firmware nem biblioteca."""

    def _dashboard(self, builder):  # type: ignore[no-untyped-def]
        from steamzero.adapters.desktop_dashboard import DesktopDashboard

        return DesktopDashboard(emulation_builder=builder)

    def test_failure_after_success_keeps_the_last_real_snapshot(self) -> None:
        calls = {"n": 0}

        def builder(**_kw: Any) -> dict[str, Any]:
            calls["n"] += 1
            if calls["n"] == 1:
                return _healthy_workspace()
            raise RuntimeError("provider quebrou")

        dashboard = self._dashboard(builder)
        first = _switch(dashboard.snapshot({})["emulation"])
        assert first["requirements"]["keys"]["installed"] == "rev21"

        second = _switch(dashboard.snapshot({})["emulation"])
        assert second["requirements"]["keys"]["installed"] == "rev21", (
            "keys verificadas não podem virar unverified por causa de uma exceção"
        )
        assert second["requirements"]["firmware"]["installed"] == "22.5.0"
        assert len(second["games"]) == 15

    def test_first_failure_says_reading_failed_not_import_needed(self) -> None:
        """Sem snapshot anterior não há verdade a preservar — mas o texto precisa
        dizer que a leitura falhou, não que falta importar."""

        def builder(**_kw: Any) -> dict[str, Any]:
            raise RuntimeError("provider quebrou na primeira composição")

        switch = _switch(self._dashboard(builder).snapshot({})["emulation"])
        detail = switch["requirements"]["keys"]["detail"]
        assert "consultar" in detail
        assert "Nenhum dado foi alterado" in detail

    def test_failure_is_logged_not_swallowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """AGENTS.md §8: degradar é permitido, degradar em silêncio não."""
        recorded: list[str] = []

        class _Logger:
            def warning(self, event: str, **_kw: Any) -> None:
                recorded.append(event)

            def __getattr__(self, _name: str):  # type: ignore[no-untyped-def]
                return lambda *_a, **_k: None

        monkeypatch.setattr(
            "steamzero.adapters.desktop_dashboard.log.get_logger", lambda: _Logger()
        )

        def builder(**_kw: Any) -> dict[str, Any]:
            raise RuntimeError("provider quebrou")

        self._dashboard(builder).snapshot({})
        assert any("emulation-snapshot-failed" in event for event in recorded)

    def test_recovery_restores_the_fresh_snapshot(self) -> None:
        """Quando o provider volta, a verdade nova prevalece sobre o cache."""
        calls = {"n": 0}

        def builder(**_kw: Any) -> dict[str, Any]:
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("falha transitória")
            return build_switch_workspace(
                probe=lambda _e: True,
                keys=_requirement("keys", "rev21"),
                firmware=_requirement("firmware", "22.5.0"),
                games=_games(calls["n"]),
            )

        dashboard = self._dashboard(builder)
        assert len(_switch(dashboard.snapshot({})["emulation"])["games"]) == 1
        assert len(_switch(dashboard.snapshot({})["emulation"])["games"]) == 1  # cache
        assert len(_switch(dashboard.snapshot({})["emulation"])["games"]) == 3  # recomposto


class TestNoImportIsRequestedWhileProjectionsHold:
    def test_ready_environment_has_no_import_blocker(self) -> None:
        readiness = _switch(_healthy_workspace())["readiness"]
        assert readiness["blockers"] == []
        joined = " ".join([readiness["title"], readiness["detail"]]).casefold()
        assert "importe" not in joined

    def test_missing_requirement_offers_repair_without_erasing(self) -> None:
        """Ausência REAL pede importação — e é isso que a distingue de falha."""
        payload = build_switch_workspace(
            probe=lambda _e: True,
            keys={
                "kind": "keys",
                "status": "missing",
                "required": "rev21",
                "installed": None,
                "detail": "Keys ausentes.",
                "blocksPlay": True,
            },
            firmware=_requirement("firmware", "22.5.0"),
            games=_games(15),
        )
        readiness = _switch(payload)["readiness"]
        assert any("mporte" in blocker for blocker in readiness["blockers"])
        assert len(_switch(payload)["games"]) == 15, "a biblioteca não some por falta de keys"
