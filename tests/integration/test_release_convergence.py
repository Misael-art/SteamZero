# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""HOST-ACTIVATION-01 — a regressão da a37, encenada.

O incidente real: `current` apontava para a a37 e o daemon a35 continuou vivo
respondendo como se fosse a nova release. Ninguém percebeu por dois dias.

O defeito NÃO foi o instalador esquecer de reiniciar. Ele roda como root, as
units são de escopo de usuário e valem para todos os usuários da máquina —
adivinhar UID, `XDG_RUNTIME_DIR` ou barramento seria pior que declarar
pendência. O defeito foi o fluxo de release **aceitar `pending` como conclusão**.

Todo teste aqui encena o cenário sem systemd, injetando `probe` e `restart`. É o
que permite reproduzir um daemon teimoso — coisa que uma bancada real não
oferece sob demanda.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from steamzero.adapters.release_convergence import (
    DIAG_MISMATCH,
    DIAG_PENDING,
    DIAG_RESTART,
    DIAG_TIMEOUT,
    DIAG_UNREADABLE,
    ConvergenceReport,
    ConvergenceState,
    converge,
    observe,
    read_activated_manifest,
    read_activated_release,
)

A37 = "0.1.0a37-2aaa01d9d8b6"
A38 = "0.1.0a38-51e9e1e35f1f"


class FakeHost:
    """Um host com `current`, um daemon vivo, e um restart que pode falhar."""

    def __init__(self, root: Path, activated: str, daemon: str | None) -> None:
        self.root = root
        self.releases = root / "releases"
        self.releases.mkdir(parents=True, exist_ok=True)
        self.daemon = daemon
        self.restart_calls = 0
        self.restart_succeeds = True
        #: O ponto do incidente: o restart NÃO troca a geração do daemon.
        #: Encena a unit que sobe mas serve o binário antigo.
        self.restart_converges = True
        self.activate(activated)

    @property
    def link(self) -> Path:
        return self.root / "current"

    def activate(self, release: str) -> None:
        target = self.releases / release
        target.mkdir(parents=True, exist_ok=True)
        (target / "manifest.json").write_text(
            json.dumps({"release": release, "schemaVersion": 4}), encoding="utf-8"
        )
        if self.link.is_symlink() or self.link.exists():
            self.link.unlink()
        self.link.symlink_to(target)

    def probe(self) -> dict[str, Any]:
        if self.daemon is None:
            raise ConnectionError("daemon fora do ar")
        return {"releaseId": self.daemon, "sourceCommit": self.daemon.split("-")[-1]}

    def restart(self) -> tuple[bool, str]:
        self.restart_calls += 1
        if not self.restart_succeeds:
            return False, "systemctl --user restart falhou"
        if self.restart_converges:
            self.daemon = read_activated_release(self.link)
        return True, "units reiniciadas"


@pytest.fixture
def host(tmp_path: Path) -> Callable[..., FakeHost]:
    def build(activated: str = A37, daemon: str | None = A37) -> FakeHost:
        return FakeHost(tmp_path, activated, daemon)

    return build


def _run(fake: FakeHost, **kwargs: Any) -> Any:
    return converge(
        link=fake.link,
        probe=fake.probe,
        restart=fake.restart,
        sleep=lambda _s: None,
        **kwargs,
    )


class TestTheA37Regression:
    """O cenário exato que o operador especificou."""

    def test_the_full_sequence_converges(self, host: Callable[..., FakeHost]) -> None:
        fake = host(activated=A37, daemon=A37)

        # A a37 está instalada e o daemon responde por ela.
        assert _run(fake, expect_release=A37).state is ConvergenceState.CONVERGED

        # `current` passa para a a38. O daemon a37 continua vivo — este é o
        # estado em que a a37 real ficou por dois dias.
        fake.activate(A38)
        stale = _run(fake, expect_release=A38)
        assert stale.state is ConvergenceState.CONVERGED, (
            "o refresh precisa CONVERGIR, não apenas detectar"
        )
        assert stale.restarted is True
        assert stale.daemon_release == A38
        assert fake.daemon == A38

    def test_a_stubborn_daemon_is_reported_as_pending_not_success(
        self, host: Callable[..., FakeHost]
    ) -> None:
        """O coração do incidente: a unit sobe e serve o binário antigo.

        Antes, esse estado passava por conclusão. Agora tem nome e não é
        sucesso.
        """
        fake = host(activated=A37, daemon=A37)
        fake.activate(A38)
        fake.restart_converges = False

        report = _run(fake, expect_release=A38, attempts=3)
        assert report.state is ConvergenceState.PENDING
        assert report.ok is False
        assert report.code == DIAG_PENDING
        assert report.activated_release == A38
        assert report.daemon_release == A37
        assert report.restarted is True

    def test_pending_is_never_a_success_state(self) -> None:
        assert ConvergenceState.PENDING.ok is False
        assert ConvergenceState.CONVERGED.ok is True
        for state in ConvergenceState:
            if state is not ConvergenceState.CONVERGED:
                assert state.ok is False, f"{state} não pode ser sucesso"


class TestClosedRefusalOnMismatch:
    """`--expect-release` divergente da release ativada NÃO reinicia nada."""

    def test_expecting_the_previous_release_fails_closed(
        self, host: Callable[..., FakeHost]
    ) -> None:
        fake = host(activated=A38, daemon=A38)
        report = _run(fake, expect_release=A37)

        assert report.state is ConvergenceState.MISMATCH
        assert report.code == DIAG_MISMATCH
        assert fake.restart_calls == 0, (
            "reiniciar aqui agiria sobre premissa errada e apagaria a evidência "
            "do que falhou na instalação"
        )
        assert report.expected_release == A37
        assert report.activated_release == A38

    def test_the_mismatch_names_both_releases(self, host: Callable[..., FakeHost]) -> None:
        """Erro que não diz o que esperava e o que achou não é acionável."""
        report = _run(host(activated=A38, daemon=A38), expect_release=A37)
        assert A37 in report.detail
        assert A38 in report.detail

    def test_a_mismatch_does_not_touch_a_healthy_daemon(
        self, host: Callable[..., FakeHost]
    ) -> None:
        fake = host(activated=A38, daemon=A38)
        _run(fake, expect_release=A37)
        assert fake.daemon == A38, "a sessão saudável não pode ser derrubada"


class TestIdempotence:
    def test_repeating_the_refresh_on_the_expected_release_succeeds(
        self, host: Callable[..., FakeHost]
    ) -> None:
        fake = host(activated=A38, daemon=A38)
        first = _run(fake, expect_release=A38)
        second = _run(fake, expect_release=A38)
        assert first.ok and second.ok

    def test_an_already_converged_daemon_is_not_restarted(
        self, host: Callable[..., FakeHost]
    ) -> None:
        """Reiniciar por precaução derrubaria uma sessão saudável a cada chamada."""
        fake = host(activated=A38, daemon=A38)
        for _ in range(3):
            report = _run(fake, expect_release=A38)
            assert report.state is ConvergenceState.CONVERGED
            assert report.restarted is False
        assert fake.restart_calls == 0


class TestReadOnlyStatus:
    def test_converged_status_does_not_restart(self, host: Callable[..., FakeHost]) -> None:
        fake = host(activated=A38, daemon=A38)
        probes = 0

        def probe() -> dict[str, Any]:
            nonlocal probes
            probes += 1
            return fake.probe()

        report = observe(link=fake.link, probe=probe)

        assert report.state is ConvergenceState.CONVERGED
        assert report.activated_release == A38
        assert report.daemon_release == A38
        assert report.restarted is False
        assert probes == 1
        assert fake.restart_calls == 0

    def test_stale_status_names_both_releases_without_restart(
        self, host: Callable[..., FakeHost]
    ) -> None:
        fake = host(activated=A38, daemon=A37)

        report = observe(link=fake.link, probe=fake.probe)

        assert report.state is ConvergenceState.PENDING
        assert report.code == DIAG_PENDING
        assert report.activated_release == A38
        assert report.daemon_release == A37
        assert A38 in report.detail
        assert A37 in report.detail
        assert fake.restart_calls == 0

    def test_unavailable_daemon_is_observed_without_restart(
        self, host: Callable[..., FakeHost]
    ) -> None:
        fake = host(activated=A38, daemon=None)

        report = observe(link=fake.link, probe=fake.probe)

        assert report.state is ConvergenceState.TIMEOUT
        assert report.code == DIAG_TIMEOUT
        assert report.activated_release == A38
        assert report.restarted is False
        assert fake.restart_calls == 0

    def test_missing_current_is_reported_without_probing(self, tmp_path: Path) -> None:
        probed = False

        def probe() -> dict[str, Any]:
            nonlocal probed
            probed = True
            return {}

        report = observe(link=tmp_path / "missing", probe=probe)

        assert report.state is ConvergenceState.UNREADABLE
        assert report.code == DIAG_UNREADABLE
        assert probed is False

    @pytest.mark.parametrize("malformed", ["regular", "dangling"])
    def test_malformed_current_is_reported_without_probing(
        self, tmp_path: Path, malformed: str
    ) -> None:
        current = tmp_path / "current"
        if malformed == "regular":
            current.write_text(A38, encoding="utf-8")
        else:
            current.symlink_to(tmp_path / "missing-release")
        probed = False

        def probe() -> dict[str, Any]:
            nonlocal probed
            probed = True
            return {}

        report = observe(link=current, probe=probe)

        assert report.state is ConvergenceState.UNREADABLE
        assert report.code == DIAG_UNREADABLE
        assert probed is False


class TestRollback:
    def test_rolling_back_converges_to_the_previous_release(
        self, host: Callable[..., FakeHost]
    ) -> None:
        """O mesmo contrato vale para trás.

        Um rollback que deixasse o daemon na release nova é o incidente da a37
        ao contrário, e igualmente invisível.
        """
        fake = host(activated=A37, daemon=A37)
        fake.activate(A38)
        assert _run(fake, expect_release=A38).ok
        assert fake.daemon == A38

        fake.activate(A37)
        report = _run(fake, expect_release=A37)
        assert report.state is ConvergenceState.CONVERGED
        assert report.daemon_release == A37
        assert fake.daemon == A37

    def test_a_rollback_with_the_wrong_expectation_fails_closed(
        self, host: Callable[..., FakeHost]
    ) -> None:
        fake = host(activated=A38, daemon=A38)
        fake.activate(A37)
        report = _run(fake, expect_release=A38)
        assert report.state is ConvergenceState.MISMATCH
        assert fake.restart_calls == 0


class TestStructuredDiagnostics:
    def test_a_failed_restart_is_named(self, host: Callable[..., FakeHost]) -> None:
        fake = host(activated=A37, daemon=A37)
        fake.activate(A38)
        fake.restart_succeeds = False
        report = _run(fake, expect_release=A38)
        assert report.state is ConvergenceState.RESTART_FAILED
        assert report.code == DIAG_RESTART
        assert "systemctl" in report.detail

    def test_a_silent_daemon_times_out(self, host: Callable[..., FakeHost]) -> None:
        """Daemon que nunca responde é timeout, não pending.

        A distinção importa: `pending` significa que ele respondeu com a release
        ERRADA; `timeout` significa que não respondeu. As causas e as correções
        são diferentes.
        """
        fake = host(activated=A37, daemon=None)
        fake.activate(A38)
        fake.restart_converges = False
        report = _run(fake, expect_release=A38, attempts=2)
        assert report.state is ConvergenceState.TIMEOUT
        assert report.code == DIAG_TIMEOUT

    def test_an_unreadable_current_is_named(self, tmp_path: Path) -> None:
        report = converge(link=tmp_path / "inexistente", sleep=lambda _s: None)
        assert report.state is ConvergenceState.UNREADABLE
        assert report.code == DIAG_UNREADABLE

    def test_every_report_serializes_with_the_three_readings(
        self, host: Callable[..., FakeHost]
    ) -> None:
        fake = host(activated=A37, daemon=A37)
        fake.activate(A38)
        payload = _run(fake, expect_release=A38).to_dict()
        assert payload["state"] == "converged"
        assert payload["expectedRelease"] == A38
        assert payload["activatedRelease"] == A38
        assert payload["daemonRelease"] == A38
        assert payload["steps"], "sem os passos, um timeout não diz se houve restart"

    def test_the_steps_record_what_happened(self, host: Callable[..., FakeHost]) -> None:
        fake = host(activated=A38, daemon=A38)
        assert "reiniciou as units" not in _run(fake, expect_release=A38).steps
        fake.activate(A37)
        fake.activate(A38)
        fake.daemon = A37
        assert "reiniciou as units" in _run(fake, expect_release=A38).steps


class TestActivatedReleaseComesFromTheSymlink:
    def test_the_symlink_target_is_the_authority(self, host: Callable[..., FakeHost]) -> None:
        """Ler o manifesto seria ler um arquivo que a release NOVA escreveu.

        O processo antigo o leria afirmando ser ela — a mesma armadilha que
        `core.identity` documenta.
        """
        fake = host(activated=A38, daemon=A38)
        manifest = fake.link / "manifest.json"
        manifest.write_text(json.dumps({"release": "mentira"}), encoding="utf-8")
        assert read_activated_release(fake.link) == A38

    def test_the_manifest_is_reported_but_never_decides(
        self, host: Callable[..., FakeHost]
    ) -> None:
        fake = host(activated=A38, daemon=A38)
        assert read_activated_manifest(fake.link)["release"] == A38

    def test_a_corrupt_manifest_does_not_break_the_reading(
        self, host: Callable[..., FakeHost]
    ) -> None:
        fake = host(activated=A38, daemon=A38)
        (fake.link / "manifest.json").write_text("{ isto não é json", encoding="utf-8")
        assert read_activated_manifest(fake.link) == {}
        assert read_activated_release(fake.link) == A38


class TestTheCliContract:
    def test_service_status_is_a_local_observer_not_a_daemon_method(self) -> None:
        """Consultar o daemon por dentro dele esconderia a fronteira observada."""
        from steamzero.service.methods import CLI_METHODS

        assert ("service", "status") not in CLI_METHODS

    def test_service_status_is_reachable_from_the_public_cli(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from steamzero.adapters import release_convergence, service_activation
        from steamzero.cli.main import main

        report = ConvergenceReport(
            state=ConvergenceState.CONVERGED,
            detail="daemon convergido",
            activated_release=A38,
            daemon_release=A38,
        )
        monkeypatch.setattr(release_convergence, "observe", lambda: report)
        monkeypatch.setattr(service_activation, "read_quarantine", lambda: None)

        assert main(["service", "status", "--json"]) == 0
        envelope = json.loads(capsys.readouterr().out)
        assert envelope["module"] == "service"
        assert envelope["action"] == "status"
        assert envelope["data"]["state"] == "converged"

    @pytest.mark.parametrize(
        ("state", "expected_status", "expected_exit"),
        [
            (ConvergenceState.CONVERGED, "ok", 0),
            (ConvergenceState.PENDING, "degraded", 0),
            (ConvergenceState.TIMEOUT, "degraded", 0),
            (ConvergenceState.UNREADABLE, "failed", 1),
        ],
    )
    def test_service_status_publishes_the_read_only_report(
        self,
        monkeypatch: pytest.MonkeyPatch,
        state: ConvergenceState,
        expected_status: str,
        expected_exit: int,
    ) -> None:
        from steamzero.adapters import release_convergence, service_activation
        from steamzero.cli.main import _cmd_service_status

        codes = {
            ConvergenceState.PENDING: DIAG_PENDING,
            ConvergenceState.TIMEOUT: DIAG_TIMEOUT,
            ConvergenceState.UNREADABLE: DIAG_UNREADABLE,
        }
        report = ConvergenceReport(
            state=state,
            detail="estado observado",
            activated_release=A38,
            daemon_release=A38 if state is ConvergenceState.CONVERGED else A37,
            code=codes.get(state),
            steps=("leu current", "consultou o daemon"),
        )
        monkeypatch.setattr(release_convergence, "observe", lambda: report)
        monkeypatch.setattr(service_activation, "read_quarantine", lambda: None)

        envelope, exit_code = _cmd_service_status([], "cid")

        assert exit_code == expected_exit
        assert envelope["status"] == expected_status
        assert envelope["data"]["state"] == state.value
        assert envelope["data"]["activatedRelease"] == A38
        assert envelope["data"]["quarantine"] is None
        if state is ConvergenceState.UNREADABLE:
            assert envelope["error"]["code"] == DIAG_UNREADABLE
        else:
            assert envelope["error"] is None

    def test_service_status_surfaces_quarantine_without_mutating(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from steamzero.adapters import release_convergence, service_activation
        from steamzero.cli.main import _cmd_service_status

        report = ConvergenceReport(
            state=ConvergenceState.CONVERGED,
            detail="daemon convergido",
            activated_release=A38,
            daemon_release=A38,
        )
        quarantine = {"schemaVersion": 1, "reason": "handshake anterior falhou"}
        monkeypatch.setattr(release_convergence, "observe", lambda: report)
        monkeypatch.setattr(service_activation, "read_quarantine", lambda: quarantine)

        envelope, exit_code = _cmd_service_status([], "cid")

        assert exit_code == 0
        assert envelope["status"] == "degraded"
        assert envelope["data"]["quarantine"] == quarantine

    def test_service_status_rejects_arguments(self) -> None:
        from steamzero.cli.main import _cmd_service_status
        from steamzero.core.errors import SteamZeroError

        with pytest.raises(SteamZeroError, match="service status não aceita argumentos"):
            _cmd_service_status(["--restart"], "cid")

    def test_the_flag_requires_a_value(self) -> None:
        """`--expect-release` sem argumento não pode virar o refresh antigo.

        Cair no caminho sem gate seria pior que falhar: o operador pediu
        verificação e receberia um reinício sem verificação nenhuma.
        """
        from steamzero.cli.main import _cmd_service_refresh

        envelope, code = _cmd_service_refresh(["--expect-release"], "cid")
        assert code != 0
        assert envelope["error"]["code"] == "E-API-SCHEMA"

    def test_the_flag_is_documented_in_the_help(self) -> None:
        """Contrato público sem documentação é contrato que ninguém usa.

        A primeira versão verificava o `__doc__` do módulo, que descreve o
        despacho da CLI — não a ajuda que o usuário vê. Passar a olhar `_USAGE`
        é a diferença entre verificar o texto certo e verificar um texto.
        """
        from steamzero.cli.main import _USAGE

        assert "service status" in _USAGE
        assert "--expect-release" in _USAGE

    @pytest.mark.parametrize(
        ("state", "diagnostic"),
        [
            (ConvergenceState.MISMATCH, DIAG_MISMATCH),
            (ConvergenceState.PENDING, DIAG_PENDING),
            (ConvergenceState.TIMEOUT, DIAG_TIMEOUT),
            (ConvergenceState.RESTART_FAILED, DIAG_RESTART),
            (ConvergenceState.UNREADABLE, DIAG_UNREADABLE),
        ],
    )
    def test_every_host_diagnostic_reaches_the_cli_error_envelope(
        self,
        monkeypatch: pytest.MonkeyPatch,
        state: ConvergenceState,
        diagnostic: str,
    ) -> None:
        from steamzero.adapters import release_convergence
        from steamzero.cli.main import _cmd_service_refresh

        report = ConvergenceReport(
            state=state,
            detail="diagnóstico observado no host",
            code=diagnostic,
        )
        monkeypatch.setattr(release_convergence, "converge", lambda **_kwargs: report)

        envelope, exit_code = _cmd_service_refresh(["--expect-release", A38], "cid")

        assert exit_code != 0
        assert envelope["status"] == "failed"
        assert envelope["error"]["code"] == diagnostic
        assert envelope["error"]["detail"] == report.detail

    @pytest.mark.parametrize(
        ("argv", "expected"),
        [
            (["--expect-release", A38], A38),
            ([f"--expect-release={A38}"], A38),
            (["--expect-release"], ""),
            (["--json"], None),
        ],
    )
    def test_the_gate_parser_distinguishes_absent_from_empty(
        self, argv: list[str], expected: str | None
    ) -> None:
        from steamzero.cli.main import _gate_flag

        assert _gate_flag(argv, "--expect-release") == expected


def test_current_link_isolates_from_host_via_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """STEAMZERO_CURRENT_LINK isola testes de IPC do host real.

    Sem isto, um daemon de teste (árvore dev, sem ``_build_info``) lê
    ``/opt/steamzero/current`` do operador e o doctor publica um falso
    ``pending`` (current=a44 vs daemon=dev). Produção nunca define a env;
    quando ausente, o link canônico é ``/opt/steamzero/current``.
    """
    from steamzero.adapters import release_convergence

    monkeypatch.delenv("STEAMZERO_CURRENT_LINK", raising=False)
    assert release_convergence._current_link() == release_convergence.CURRENT_LINK

    isolated = tmp_path / "no-current"
    monkeypatch.setenv("STEAMZERO_CURRENT_LINK", str(isolated))
    assert release_convergence._current_link() == isolated
    # Sem symlink no link isolado, read_activated_release devolve None sem tocar
    # o host real — caminho usado pelo doctor nos testes de IPC.
    assert read_activated_release() is None
