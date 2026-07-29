# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Recarga do daemon em escopo de usuário e estado terminal de falha.

Nenhum teste aqui executa systemctl de verdade nem toca o host: o runner é
injetado. O que se prova é a DECISÃO — que a falha termina em "daemon parado com
causa declarada", nunca em "daemon vivo de geração desconhecida".
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pytest

from steamzero.adapters import service_activation as activation
from steamzero.adapters.service_activation import MANAGED_UNITS, CommandOutcome


@pytest.fixture(autouse=True)
def state_home(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))


class _Recorder:
    def __init__(self, failures: dict[str, int] | None = None) -> None:
        self.calls: list[tuple[str, ...]] = []
        self._failures = failures or {}

    def __call__(self, argv: Sequence[str]) -> CommandOutcome:
        self.calls.append(tuple(argv))
        key = " ".join(argv)
        for pattern, code in self._failures.items():
            if pattern in key:
                return CommandOutcome(code, "", f"falha simulada em {pattern}")
        return CommandOutcome(0)

    def ran(self, *fragment: str) -> bool:
        return any(all(f in " ".join(call) for f in fragment) for call in self.calls)


def _ok_identity() -> dict[str, Any]:
    return {"packageVersion": "0.1.0a37", "sourceCommit": "a" * 40, "releaseId": "0.1.0a37-aaa"}


class TestSuccessfulRefresh:
    def test_reloads_restarts_and_confirms(self) -> None:
        runner = _Recorder()
        result = activation.refresh(runner=runner, verifier=_ok_identity)

        assert result.state == "ready"
        assert runner.ran("daemon-reload")
        for unit in MANAGED_UNITS:
            assert runner.ran("restart", unit)
        assert result.identity == _ok_identity()

    def test_socket_is_restarted_before_service(self) -> None:
        """A ordem importa: o socket precisa apontar para a geração nova antes
        de o serviço subir por ativação."""
        runner = _Recorder()
        activation.refresh(runner=runner, verifier=_ok_identity)
        restarts = [c for c in runner.calls if "restart" in c]
        assert restarts[0][-1] == "steamzero-core.socket"
        assert restarts[1][-1] == "steamzero-core.service"

    def test_success_clears_previous_quarantine(self) -> None:
        activation._write_quarantine("falha anterior", _ok_identity())
        assert activation.read_quarantine() is not None

        activation.refresh(runner=_Recorder(), verifier=_ok_identity)
        assert activation.read_quarantine() is None


class TestFailureIsQuarantinedNotSilent:
    """C2: terminar em daemon parado com causa declarada."""

    def test_reload_failure_stops_units(self) -> None:
        runner = _Recorder({"daemon-reload": 1})
        result = activation.refresh(runner=runner, verifier=_ok_identity)

        assert result.state == "quarantined"
        for unit in MANAGED_UNITS:
            assert runner.ran("stop", unit), f"{unit} precisa ser parada"

    def test_restart_failure_stops_units(self) -> None:
        runner = _Recorder({"restart steamzero-core.service": 1})
        result = activation.refresh(runner=runner, verifier=_ok_identity)

        assert result.state == "quarantined"
        assert runner.ran("stop", "steamzero-core.service")
        assert runner.ran("stop", "steamzero-core.socket")

    def test_socket_is_stopped_so_activation_cannot_resurrect(self) -> None:
        """Sem parar o socket, o próximo acesso ressuscitaria a geração anterior."""
        runner = _Recorder({"daemon-reload": 1})
        activation.refresh(runner=runner, verifier=_ok_identity)
        assert runner.ran("stop", "steamzero-core.socket")

    def test_handshake_never_confirming_is_quarantined(self) -> None:
        """Units sobem, mas a geração não confere: o caso literal da a37."""
        from steamzero.service.client import CoreGenerationMismatch

        def _mismatch() -> dict[str, Any]:
            raise CoreGenerationMismatch(
                {"releaseId": "0.1.0a37-novo"}, {"releaseId": "0.1.0a35-velho"}
            )

        runner = _Recorder()
        result = activation.refresh(
            runner=runner, verifier=_mismatch, attempts=2, interval=0, sleep=lambda _s: None
        )

        assert result.state == "quarantined"
        assert runner.ran("stop", "steamzero-core.service")

    def test_quarantine_records_reason_and_expected_identity(self) -> None:
        runner = _Recorder({"daemon-reload": 1})
        activation.refresh(runner=runner, verifier=_ok_identity)

        marker = activation.read_quarantine()
        assert marker is not None
        assert "daemon-reload" in marker["reason"]
        assert "expected" in marker, "o marcador precisa dizer qual geração era esperada"

    def test_detail_explains_why_the_service_is_down(self) -> None:
        runner = _Recorder({"restart steamzero-core.socket": 1})
        result = activation.refresh(runner=runner, verifier=_ok_identity)
        assert "parado" in result.detail


class TestHandshakeRetry:
    def test_transient_failure_is_retried(self) -> None:
        """O daemon leva um instante para aceitar conexão após o restart."""
        attempts: list[int] = []

        def _flaky() -> dict[str, Any]:
            attempts.append(1)
            if len(attempts) < 3:
                raise ConnectionError("ainda subindo")
            return _ok_identity()

        result = activation.refresh(
            runner=_Recorder(), verifier=_flaky, attempts=5, interval=0, sleep=lambda _s: None
        )
        assert result.state == "ready"
        assert len(attempts) == 3


class TestQuarantineMarker:
    """C3: a degradação é anunciada, não descoberta."""

    def test_absent_marker_means_healthy(self) -> None:
        assert activation.read_quarantine() is None

    def test_unreadable_marker_still_signals_quarantine(self) -> None:
        path = activation.quarantine_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{isto nao e json", encoding="utf-8")
        marker = activation.read_quarantine()
        assert marker is not None
        assert "ilegível" in marker["reason"]

    def test_clear_is_idempotent(self) -> None:
        activation.clear_quarantine()
        activation.clear_quarantine()
        assert activation.read_quarantine() is None


class TestOnlyManagedUnitsAreTouched:
    def test_no_third_party_unit_is_named(self) -> None:
        """AGENTS.md §5: nenhuma unit de terceiro é tocada."""
        runner = _Recorder({"daemon-reload": 1})
        activation.refresh(runner=runner, verifier=_ok_identity)

        for call in runner.calls:
            named = [a for a in call if a.endswith((".service", ".socket"))]
            for unit in named:
                assert unit in MANAGED_UNITS, f"unit não gerenciada tocada: {unit}"

    def test_every_call_is_user_scoped(self) -> None:
        """Escopo de usuário: nada aqui exige nem usa privilégio."""
        runner = _Recorder()
        activation.refresh(runner=runner, verifier=_ok_identity)
        for call in runner.calls:
            assert call[0] == "systemctl"
            assert "--user" in call
            assert "sudo" not in call and "bigsudo" not in call


class TestInstallerDeclaresPendingRefresh:
    """O instalador não reinicia — mas precisa DIZER que não reiniciou.

    Foi o silêncio que produziu a a37: `current` passou a apontar para a release
    nova e o daemon seguiu na anterior, sem nada avisar.
    """

    def _installer(self):  # type: ignore[no-untyped-def]
        import sys
        from pathlib import Path as _Path

        sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / "tools"))
        import install_host

        return install_host

    def test_notice_marks_refresh_as_pending(self) -> None:
        installer = self._installer()
        result = installer._activation_notice(
            {"release": "release-a", "packageVersion": "0.1.0a37"},
            installer.Layout(),
        )
        assert result["daemonRefresh"]["state"] == "pending"

    def test_notice_names_the_command_to_run(self) -> None:
        installer = self._installer()
        result = installer._activation_notice({"release": "release-a"}, installer.Layout())
        assert result["daemonRefresh"]["command"] == (
            "/usr/local/sbin/steamzero-host converge --expect-release release-a"
        )

    def test_notice_preserves_the_manifest(self) -> None:
        installer = self._installer()
        manifest = {
            "release": "release-a",
            "packageVersion": "0.1.0a37",
            "sourceCommit": "a" * 40,
        }
        result = installer._activation_notice(manifest, installer.Layout())
        for key, value in manifest.items():
            assert result[key] == value

    def test_detail_explains_the_consequence(self) -> None:
        installer = self._installer()
        detail = installer._activation_notice({"release": "release-a"}, installer.Layout())[
            "daemonRefresh"
        ]["detail"]
        assert "geração anterior" in detail
