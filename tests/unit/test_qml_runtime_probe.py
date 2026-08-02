# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Regressões G31 — probe do runtime QML que nunca aceita processo abortado.

Cobre os estados distintos do gate visual: timeout, morte por sinal, código
de saída diferente de zero e stderr sanitizado; o guard de baseline/delta de
coredumps (falha apenas por eventos novos atribuíveis à execução); e a
verificação de que o QML validado é o do pacote instalado/unpacked, não só a
árvore fonte. Nenhum teste exige Qt real: subprocess e leitores de coredump
são injetados.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from qml_capture_runner import (  # noqa: E402
    DIAG_CRASH,
    DIAG_ENVIRONMENT,
    DIAG_QT_EXIT,
    DIAG_QT_RUNTIME,
    DIAG_QT_SIGNAL,
    DIAG_QT_STDERR,
    DIAG_QT_TIMEOUT,
    DIAG_QT_VERSION,
    CaptureError,
    CrashSnapshot,
    PackagedQmlStatus,
    assert_no_new_crashes,
    capture,
    check_runtime_version,
    crash_fingerprint,
    probe_runtime,
    sanitize_stderr,
    verify_packaged_qml,
)


class _Done:
    def __init__(
        self,
        *,
        returncode: int = 0,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class _Timeout:
    stderr = b"stderr do timeout"


def _fake_run(monkeypatch: pytest.MonkeyPatch, result: object) -> None:
    """Probe de versão roda sob ``subprocess.run``: injeta o resultado.

    Aceita um ``subprocess.TimeoutExpired`` (lança), um ``OSError`` (lança) ou
    um ``_Done`` (retorna).
    """
    import qml_capture_runner as runner

    def fake_run(*_args: object, **_kwargs: object) -> object:
        if isinstance(result, BaseException):
            raise result
        return result

    monkeypatch.setattr(runner.subprocess, "run", fake_run)


class _FakePopen:
    """Substituto de ``subprocess.Popen`` para o harness em ``capture()``.

    O harness agora usa ``Popen`` + ``communicate`` (para expor o PID ao guard
    de crash). Este fake reproduz a interface mínima que ``capture()`` toca:
    ``pid``, ``communicate(timeout=)``, ``kill()``, ``returncode`` e o fechamento
    dos pipes no ``finally``.
    """

    _next_pid = 10_000

    def __init__(
        self,
        *,
        returncode: int = 0,
        stdout: str = "",
        stderr: str = "",
        on_start: object = None,
    ) -> None:
        type(self)._next_pid += 1
        self.pid = type(self)._next_pid
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr
        self._on_start = on_start
        self.stdout = None
        self.stderr = None

    def communicate(self, timeout: float | None = None) -> tuple[str, str]:
        # Hook para o teste PNG-residual escrever a imagem durante a execução
        # do harness — reproduz o cenário declarado (PNG só existe se o
        # harness produziu algo antes de abortar).
        if self._on_start is not None:
            self._on_start()
        return self._stdout, self._stderr

    def kill(self) -> None:
        pass


def _fake_popen(monkeypatch: pytest.MonkeyPatch, popen: _FakePopen) -> None:
    import qml_capture_runner as runner

    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **k: popen)


class TestProbeStates:
    def test_timeout_is_a_distinct_state(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _fake_run(monkeypatch, subprocess.TimeoutExpired("probe", 30))
        probe = probe_runtime(Path("/usr/bin/qml6"), timeout=30)
        assert probe.ok is False
        assert probe.timed_out is True
        assert probe.signal_number is None
        assert probe.exit_code is None
        # G31: stderr None no timeout não vira o literal "None" no diagnóstico.
        assert probe.stderr_sanitized == ""
        with pytest.raises(CaptureError) as raised:
            check_runtime_version(Path("/usr/bin/qml6"))
        assert raised.value.code == DIAG_QT_TIMEOUT

    def test_oserror_is_a_distinct_state_not_exit_code_none(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Binário ausente/inexecutável: OSError no probe é estado de ambiente,
        # distinto de "terminou com código de erro". Não pode virar a mensagem
        # enganosa "saiu com código None".
        _fake_run(monkeypatch, OSError("[Errno 2] No such file or directory: '/usr/bin/qml6'"))
        probe = probe_runtime(Path("/usr/bin/qml6"))
        assert probe.ok is False
        assert probe.exit_code is None
        assert probe.signal_number is None
        assert probe.timed_out is False
        with pytest.raises(CaptureError) as raised:
            check_runtime_version(Path("/usr/bin/qml6"))
        assert raised.value.code == DIAG_QT_RUNTIME
        assert "código None" not in raised.value.detail

    def test_killed_by_signal_is_a_distinct_state_and_refused(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _fake_run(monkeypatch, _Done(returncode=-6))
        probe = probe_runtime(Path("/usr/bin/qml6"))
        assert probe.ok is False
        assert probe.signal_number == 6
        assert probe.signal_name == "SIGABRT"
        assert probe.timed_out is False
        with pytest.raises(CaptureError) as raised:
            check_runtime_version(Path("/usr/bin/qml6"))
        assert raised.value.code == DIAG_QT_SIGNAL
        assert "SIGABRT" in raised.value.detail
        assert "nunca prova renderização" in raised.value.detail

    def test_nonzero_exit_is_a_distinct_state_and_refused(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _fake_run(monkeypatch, _Done(returncode=3, stdout="Qt 6.11.1"))
        probe = probe_runtime(Path("/usr/bin/qml6"))
        assert probe.ok is False
        assert probe.exit_code == 3
        assert probe.signal_number is None
        with pytest.raises(CaptureError) as raised:
            check_runtime_version(Path("/usr/bin/qml6"))
        assert raised.value.code == DIAG_QT_EXIT

    def test_success_requires_zero_exit_even_when_version_printed(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _fake_run(monkeypatch, _Done(returncode=-11, stdout="Qt 6.11.1"))
        with pytest.raises(CaptureError) as raised:
            check_runtime_version(Path("/usr/bin/qml6"))
        assert raised.value.code == DIAG_QT_SIGNAL
        assert "SIGSEGV" in raised.value.detail

    def test_ok_returns_parsed_version(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _fake_run(monkeypatch, _Done(returncode=0, stdout="Qt 6.11.1"))
        probe = probe_runtime(Path("/usr/bin/qml6"))
        assert probe.ok is True
        assert probe.version[:2] == (6, 11)
        assert check_runtime_version(Path("/usr/bin/qml6")) == (6, 11, 1)

    def test_old_qt_is_still_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _fake_run(monkeypatch, _Done(returncode=0, stdout="Qt 6.2.0"))
        with pytest.raises(CaptureError) as raised:
            check_runtime_version(Path("/usr/bin/qml6"))
        assert raised.value.code == DIAG_QT_VERSION

    def test_unrecognized_output_is_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _fake_run(monkeypatch, _Done(returncode=0, stdout="binário misterioso"))
        with pytest.raises(CaptureError) as raised:
            check_runtime_version(Path("/usr/bin/qml6"))
        assert raised.value.code == DIAG_QT_VERSION

    def test_critical_stderr_is_a_distinct_state_even_on_success(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _fake_run(
            monkeypatch,
            _Done(
                returncode=0,
                stdout="Qt 6.11.1",
                stderr="critical|qt.qpa.plugin: camada quebrada",
            ),
        )
        probe = probe_runtime(Path("/usr/bin/qml6"))
        assert probe.ok is True
        assert "critical|" in probe.stderr_sanitized
        with pytest.raises(CaptureError) as raised:
            check_runtime_version(Path("/usr/bin/qml6"))
        assert raised.value.code == DIAG_QT_STDERR


class TestSanitizedStderr:
    def test_stderr_is_bounded_not_raw(self) -> None:
        blob = "x" * 10_000
        assert len(sanitize_stderr(blob)) <= 4096 + 40
        assert "truncado pelo gate" in sanitize_stderr(blob)

    def test_empty_stderr_stays_empty(self) -> None:
        assert sanitize_stderr("  \n ") == ""


class TestCaptureAbortNeverProvesRendering:
    def test_harness_killed_by_signal_fails_before_image_check(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        import qml_capture_runner as runner

        # Probe de versão sob subprocess.run: termina com sucesso para não
        # mascarar o caminho do abort do harness.
        monkeypatch.setattr(
            runner.subprocess,
            "run",
            lambda *a, **k: _Done(returncode=0, stdout="Qt 6.11.1"),
        )
        monkeypatch.setattr(runner, "find_runtime", lambda: Path("/usr/bin/qml6"))
        monkeypatch.setattr(
            runner,
            "verify_packaged_qml",
            lambda: PackagedQmlStatus(resolved=True, reason=None, size_bytes=1),
        )
        # A fronteira de payload já é testada à parte; aqui só o caminho do
        # abort do harness importa.
        monkeypatch.setattr(runner, "_reject_pending_payload", lambda model: None)

        # O PNG precisa existir QUANDO o check de signal roda — ou seja, só
        # pode ser escrito durante a execução do harness, não antes (capture()
        # apaga o arquivo antes de lançar o processo). O hook on_start do fake
        # reproduz o cenário declarado: um PNG sobreviveu de um processo que
        # abortou; o gate reprova pelo signal ANTES de olhar a imagem.
        def write_residual_png() -> None:
            (tmp_path / "actual.png").write_bytes(b"png")

        popen = _FakePopen(returncode=-6, on_start=write_residual_png)
        _fake_popen(monkeypatch, popen)

        with pytest.raises(CaptureError) as raised:
            capture({"text": "x"}, output=tmp_path)
        assert raised.value.code == DIAG_QT_SIGNAL
        assert "abortado por SIGABRT" in raised.value.detail

    def test_successful_capture_runs_crash_guard_with_harness_pid(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # G31 fechamento: o guard baseline/delta tem que rodar numa captura que
        # chegou ao sucesso aparente (verde que esconde coredump). Este teste
        # prova o wiring — antes desta mudança capture() nunca chamava o guard.
        import qml_capture_runner as runner

        original_collect = runner.CrashSnapshot.collect
        calls: list[tuple] = []

        def fake_collect(reader=None):
            calls.append("collect")
            return original_collect(reader)

        def fake_assert(before, after, *, spawned_pids):
            calls.append(("assert", tuple(spawned_pids)))

        monkeypatch.setattr(
            runner.subprocess,
            "run",
            lambda *a, **k: _Done(returncode=0, stdout="Qt 6.11.1"),
        )
        monkeypatch.setattr(runner, "find_runtime", lambda: Path("/usr/bin/qml6"))
        monkeypatch.setattr(
            runner,
            "verify_packaged_qml",
            lambda: PackagedQmlStatus(resolved=True, reason=None, size_bytes=1),
        )
        monkeypatch.setattr(runner, "_reject_pending_payload", lambda model: None)
        monkeypatch.setattr(runner.CrashSnapshot, "collect", staticmethod(fake_collect))
        monkeypatch.setattr(runner, "assert_no_new_crashes", fake_assert)

        def write_png_and_geometry() -> None:
            (tmp_path / "actual.png").write_bytes(b"png")

        popen = _FakePopen(
            returncode=0,
            stdout="",
            stderr="HARNESS-GEOMETRY {}",
            on_start=write_png_and_geometry,
        )
        _fake_popen(monkeypatch, popen)

        capture({"text": "x"}, output=tmp_path)

        # O guard foi chamado: duas coletas (baseline + delta) e a asserção
        # recebeu o PID do harness que capture() lançou.
        assert calls.count("collect") == 2
        assert_calls = [c for c in calls if isinstance(c, tuple) and c[0] == "assert"]
        assert len(assert_calls) == 1
        assert assert_calls[0][1] == (popen.pid,)


class TestCrashGuard:
    def _snapshot(self, records: list[dict[str, object]]) -> CrashSnapshot:
        return CrashSnapshot.collect(lambda: records)

    def test_old_history_is_never_a_new_failure(self) -> None:
        before = self._snapshot([{"pid": 111, "comm": "qml6", "signal": 6}])
        after = self._snapshot([{"pid": 111, "comm": "qml6", "signal": 6}])
        assert_no_new_crashes(before, after, spawned_pids=[999])

    def test_new_abort_of_the_runtime_is_attributable(self) -> None:
        before = self._snapshot([{"pid": 111, "comm": "qml6", "signal": 6}])
        after = self._snapshot(
            [
                {"pid": 111, "comm": "qml6", "signal": 6},
                {"pid": 222, "comm": "qml6", "signal": 6},
            ]
        )
        with pytest.raises(CaptureError) as raised:
            assert_no_new_crashes(before, after, spawned_pids=[999])
        assert raised.value.code == DIAG_CRASH

    def test_spawned_pid_crash_is_attributable_even_without_qml_comm(self) -> None:
        before = self._snapshot([])
        after = self._snapshot([{"pid": 777, "comm": "other", "signal": 11}])
        with pytest.raises(CaptureError) as raised:
            assert_no_new_crashes(before, after, spawned_pids=[777])
        assert raised.value.code == DIAG_CRASH

    def test_unrelated_new_coredump_is_not_attributable(self) -> None:
        before = self._snapshot([])
        after = self._snapshot([{"pid": 888, "comm": "browser", "signal": 6}])
        assert_no_new_crashes(before, after, spawned_pids=[777])

    def test_fingerprint_is_neutral_and_stable(self) -> None:
        one = crash_fingerprint({"pid": 5, "comm": "qml6", "signal": 6, "exe": "/usr/bin/qml6"})
        two = crash_fingerprint({"signal": 6, "comm": "qml6", "pid": 5, "exe": "/other/path"})
        assert one == two
        assert "/" not in one
        assert "usr" not in one

    def test_collect_degrades_to_empty_when_reader_raises(self) -> None:
        # Um coredumpctl quebrado (ex.: permissão negada, JSON inválido) nunca
        # derruba o gate: collect() engole a exceção e devolve snapshot vazio.
        def broken_reader() -> list[dict[str, Any]]:
            raise RuntimeError("coredumpctl failed")

        snapshot = CrashSnapshot.collect(broken_reader)
        assert snapshot.records == ()
        assert snapshot.fingerprints == frozenset()


class TestPackagedQml:
    def test_product_main_qml_resolves_in_the_package(self) -> None:
        result = verify_packaged_qml()
        assert result.resolved is True
        assert result.size_bytes > 0
        assert result.reason is None

    def test_capture_refuses_when_packaged_qml_is_missing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        import qml_capture_runner as runner

        monkeypatch.setattr(
            runner,
            "verify_packaged_qml",
            lambda: PackagedQmlStatus(
                resolved=False,
                reason="Main.qml ausente no pacote instalado/unpacked",
                size_bytes=0,
            ),
        )
        monkeypatch.setattr(runner, "find_runtime", lambda: Path("/usr/bin/qml6"))
        monkeypatch.setattr(
            runner.subprocess,
            "run",
            lambda *a, **k: _Done(returncode=0, stdout="Qt 6.11.1"),
        )
        monkeypatch.setattr(runner, "_reject_pending_payload", lambda model: None)
        with pytest.raises(CaptureError) as raised:
            capture({"text": "x"}, output=tmp_path)
        assert raised.value.code == DIAG_ENVIRONMENT
        assert "árvore fonte" in raised.value.detail
