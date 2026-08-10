# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Testes do driver de certificação M10 (DEBT-A7).

O driver é puro: recebe um ``ComponentClient`` injetável. Estes testes usam um
``FakeComponentClient`` em memória que espelha o contrato da CLI
(``component plan/apply/rollback/status``). A VM real (virt-install/cloud-init)
roda fora da suíte, sob autorização do operador.
"""

from __future__ import annotations

import json
import secrets
import subprocess
from pathlib import Path
from typing import Any

import pytest

import vm_harness.provision as provision_module
from vm_harness.driver import (
    CYCLE_STEPS,
    certify_emulator,
    certify_emulator_minimal,
    certify_m10,
    m10_pinned_commits,
    render_evidence_report,
)
from vm_harness.provision import (
    CommandResult,
    GuestComponentClient,
    VmConfig,
    _seed_argv,
    build_virt_install_argv,
    render_cloud_init,
)
from vm_harness.provision import (
    main as provision_main,
)


class FakeComponentClient:
    """Cliente de componente determinístico para o driver.

    Mantém estado em memória (installed/missing) e gera planId/confirmToken/
    operationId opacos como a CLI real. ``plan(action='update')`` devolve noop
    porque a fonte Flatpak já está pinada no commit do manifesto.
    """

    def __init__(self) -> None:
        self._state: dict[str, str] = {}  # adapter_id -> "installed" | "missing"
        self._plans: dict[str, dict[str, Any]] = {}  # planId -> plan envelope
        self._counter = 0
        self._pins = m10_pinned_commits()

    def status(self, adapter_id: str) -> dict[str, Any]:
        state = self._state.get(adapter_id, "missing")
        return {
            "id": adapter_id,
            "state": state,
            "version": self._pins[adapter_id] if state == "installed" else None,
        }

    def plan(self, adapter_id: str, action: str = "install") -> dict[str, Any]:
        current = self._state.get(adapter_id, "missing")
        if action == "install" and current == "installed":
            return {"planId": None, "confirmToken": None, "action": "noop"}
        if action == "update":
            # Fonte Flatpak pinada: update é noop (mesmo commit do manifesto).
            return {"planId": None, "confirmToken": None, "action": "noop"}
        self._counter += 1
        plan_id = f"plan-{adapter_id}-{self._counter}"
        confirm = secrets.token_urlsafe(16)
        envelope = {"planId": plan_id, "confirmToken": confirm, "action": action}
        self._plans[plan_id] = envelope
        return envelope

    def apply(self, plan_id: str, confirm_token: str) -> dict[str, Any]:
        plan = self._plans[plan_id]
        assert plan["confirmToken"] == confirm_token  # token de confirmação casado
        adapter_id = plan_id.split("-")[1]
        action = plan["action"]
        if action == "install":
            self._state[adapter_id] = "installed"
        elif action == "uninstall":
            self._state[adapter_id] = "missing"
        op_id = f"op-{plan_id}"
        return {"operationId": op_id, "status": "committed"}

    def rollback(self, operation_id: str) -> dict[str, Any]:
        # operation_id = "op-plan-<adapter>-<n>"; adapter é o segundo token.
        adapter_id = operation_id.split("-")[2]
        self._state[adapter_id] = "missing"
        return {"operationId": operation_id, "status": "rolled-back"}

    def verify(self, adapter_id: str) -> dict[str, Any]:
        status = self.status(adapter_id)
        return {"verified": status["state"] == "installed", **status}


def test_certify_emulator_happy_path() -> None:
    # Ciclo completo install->update(noop)->rollback->roll-forward fica verde.
    client = FakeComponentClient()
    result = certify_emulator("pcsx2", client, expected_commit=m10_pinned_commits()["pcsx2"])
    assert result.ok is True
    assert result.failure is None
    steps = [s["step"] for s in result.steps]
    assert steps[0] == "baseline"
    for expected in CYCLE_STEPS:
        assert expected in steps
    # Estado final: installed (roll-forward).
    assert client.status("pcsx2")["state"] == "installed"


def test_certify_emulator_records_evidence_via_sink() -> None:
    # O EvidenceSink recebe cada checkpoint na ordem, com o emulador certo.
    client = FakeComponentClient()
    seen: list[tuple[str, str]] = []
    certify_emulator(
        "ppsspp",
        client,
        expected_commit=m10_pinned_commits()["ppsspp"],
        evidence=lambda emu, step, _payload: seen.append((emu, step)),
    )
    assert seen[0] == ("ppsspp", "baseline")
    assert ("ppsspp", "install") in seen
    assert ("ppsspp", "rollback") in seen
    assert ("ppsspp", "roll-forward") in seen
    assert all(emu == "ppsspp" for emu, _ in seen)


def test_certify_emulator_fails_when_not_absent_at_baseline() -> None:
    # Emulador já installed no baseline: divergência, ciclo interrompe, sem falso.
    client = FakeComponentClient()
    client._state["retroarch"] = "installed"  # simula estado sujo antes do ciclo
    result = certify_emulator(
        "retroarch", client, expected_commit=m10_pinned_commits()["retroarch"]
    )
    assert result.ok is False
    assert result.failure is not None
    assert "baseline" in result.failure


def test_certify_emulator_fails_when_install_does_not_reach_installed() -> None:
    # Apply que não leva a installed: divergência registrada, ciclo para.
    client = FakeComponentClient()

    def _broken_apply(plan_id: str, confirm_token: str) -> dict[str, Any]:
        return {"operationId": "op-x", "status": "committed"}  # não muda estado

    client.apply = _broken_apply  # type: ignore[method-assign]
    result = certify_emulator("pcsx2", client, expected_commit=m10_pinned_commits()["pcsx2"])
    assert result.ok is False
    assert "install" in (result.failure or "")


def test_certify_emulator_fails_when_rollback_does_not_restore_absent() -> None:
    # Rollback que não restaura o baseline ausente: divergência registrada.
    client = FakeComponentClient()

    original_rollback = client.rollback

    def _noop_rollback(operation_id: str) -> dict[str, Any]:
        return {"operationId": operation_id, "status": "rolled-back"}  # não restaura

    client.rollback = _noop_rollback  # type: ignore[method-assign]
    result = certify_emulator("ppsspp", client, expected_commit=m10_pinned_commits()["ppsspp"])
    assert result.ok is False
    assert "rollback" in (result.failure or "")
    # restore para não vazar estado entre asserções
    client.rollback = original_rollback  # type: ignore[method-assign]


def test_certify_emulator_minimal_stops_after_verified_rollback() -> None:
    client = FakeComponentClient()
    result = certify_emulator_minimal(
        "retroarch", client, expected_commit=m10_pinned_commits()["retroarch"]
    )
    assert result.ok is True
    assert [step["step"] for step in result.steps] == [
        "baseline",
        "install",
        "verify",
        "rollback",
    ]
    assert client.status("retroarch")["state"] == "missing"


def test_certify_m10_aggregates_all_emulators() -> None:
    # certify_m10 roda cada emulador e agrega o veredito geral.
    client = FakeComponentClient()
    report = certify_m10(client)
    assert report["ok"] is True
    assert set(report["summary"]) == {"retroarch", "pcsx2", "ppsspp"}
    assert all(v == "ok" for v in report["summary"].values())
    assert len(report["emulators"]) == 3


def test_certify_m10_reports_failure_when_one_emulator_breaks() -> None:
    # Um emulador quebrado reprova o geral, mas os outros ainda correm.
    client = FakeComponentClient()
    result = certify_emulator(
        "pcsx2", client, expected_commit=m10_pinned_commits()["pcsx2"]
    )  # pré-instala para sujar baseline
    assert result.ok  # sanity: o ciclo happy-path deixa installed
    # Agora pcsx2 está installed; novo certify deve falhar no baseline.
    report = certify_m10(client)
    assert report["ok"] is False
    assert report["summary"]["retroarch"] == "ok"  # os limpos ainda passam
    assert report["summary"]["pcsx2"] == "fail"


def test_render_evidence_report_includes_commit_and_verdict(tmp_path: Path) -> None:
    # O relatório renderizado vincula commit + data + veredito por etapa.
    client = FakeComponentClient()
    report = certify_m10(client)
    md = render_evidence_report(report, source_commit="abc123def456", date="2026-08-06")
    assert "abc123def456" in md
    assert "2026-08-06" in md
    assert "APROVADO" in md
    for emu in ("retroarch", "pcsx2", "ppsspp"):
        assert emu in md
    # Tabela de resultado por emulador presente.
    assert "| emulador | veredito" in md


def test_certify_emulator_rejects_deployed_commit_different_from_manifest() -> None:
    client = FakeComponentClient()
    expected = m10_pinned_commits()["retroarch"]
    original_status = client.status

    def _drifted_status(adapter_id: str) -> dict[str, Any]:
        status = original_status(adapter_id)
        if status["state"] == "installed":
            status["version"] = "0" * 64
        return status

    client.status = _drifted_status  # type: ignore[method-assign]
    result = certify_emulator("retroarch", client, expected_commit=expected)
    assert result.ok is False
    assert "commit Flatpak diverge" in (result.failure or "")


def test_provision_plan_is_non_mutating_and_does_not_require_kvm(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # --plan não chama preflight, não procura imagem/chave e não cria o stub antigo.
    result = provision_main(["--source-commit", "a" * 40, "--plan"])
    captured = capsys.readouterr()
    assert result == 0
    assert "Plano de provisionamento" in captured.out
    assert captured.err == ""


def test_provision_rejects_execution_without_its_confirmation(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = provision_main(["--source-commit", "a" * 40])
    captured = capsys.readouterr()
    assert result == 1
    assert "recusa mutar" in captured.err


def test_process_runner_only_passes_input_when_copying_archive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    class Completed:
        returncode = 0
        stdout = b"out"
        stderr = b"err"

    def run(_argv: list[str], **kwargs: Any) -> Completed:
        calls.append(kwargs)
        return Completed()

    monkeypatch.setattr(provision_module.subprocess, "run", run)
    assert provision_module._run(("ssh", "guest"), None, 10.0).stdout == b"out"
    assert "input" not in calls[0]
    assert calls[0]["stdin"] is provision_module.subprocess.DEVNULL
    provision_module._run(("ssh", "guest"), b"archive", 10.0)
    assert calls[1]["input"] == b"archive"
    assert "stdin" not in calls[1]


def test_required_uses_stdout_when_a_process_has_no_stderr() -> None:
    with pytest.raises(RuntimeError, match="diagnóstico do guest"):
        provision_module._required(
            CommandResult(1, stdout="diagnóstico do guest".encode()), "component status"
        )


def test_vm_config_rejects_execution_without_operator_inputs(tmp_path: Path) -> None:
    config = VmConfig(
        source_commit="a" * 40,
        vm_name="steamzero-m10",
        base_image=tmp_path / "missing.qcow2",
        ssh_public_key=tmp_path / "missing.pub",
        work_dir=tmp_path / "work",
    )
    with pytest.raises(ValueError, match="base-image"):
        config.validate(executing=True)


def test_vm_config_requires_the_private_identity_for_execution(tmp_path: Path) -> None:
    config = VmConfig(
        source_commit="a" * 40,
        vm_name="steamzero-m10",
        base_image=tmp_path / "arch.qcow2",
        ssh_public_key=tmp_path / "operator.pub",
        work_dir=tmp_path / "work",
    )
    config.base_image.write_bytes(b"qcow2")
    config.ssh_public_key.write_text(
        "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI test\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="ssh-private-key"):
        config.validate(executing=True)


def test_cloud_init_and_virt_install_are_pinned_to_disposable_overlay(tmp_path: Path) -> None:
    config = VmConfig(
        source_commit="a" * 40,
        vm_name="steamzero-m10",
        base_image=tmp_path / "arch.qcow2",
        ssh_public_key=tmp_path / "operator.pub",
        work_dir=tmp_path / "work",
    )
    user_data, meta_data = render_cloud_init(config, "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI test")
    assert "python-jsonschema" in user_data
    assert "noto-fonts" in user_data
    assert "package_update: false" in user_data
    assert "timeout --kill-after=15s" in user_data
    assert "300s " in user_data
    assert "pacman -Sy --noconfirm --needed" in user_data
    assert "pacman bootstrap attempt $attempt failed" in user_data
    assert "systemctl enable --now sshd.service || true" in user_data
    assert "flatpak remote-add" not in user_data
    assert "steamzero-m10" in meta_data
    argv = build_virt_install_argv(config, tmp_path / "overlay.qcow2", tmp_path / "seed.iso")
    assert argv[:5] == ["virt-install", "--connect", "qemu:///system", "--name", "steamzero-m10"]
    assert "network=default,model=virtio" in argv
    assert "--noautoconsole" in argv


def test_seed_iso_uses_xorriso_when_cloud_localds_is_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def which(name: str) -> str | None:
        return "/usr/bin/xorriso" if name == "xorriso" else None

    monkeypatch.setattr(provision_module.shutil, "which", which)
    argv = _seed_argv(tmp_path / "seed.iso", tmp_path / "user-data", tmp_path / "meta-data")
    assert argv[:5] == ("xorriso", "-as", "mkisofs", "-output", str(tmp_path / "seed.iso"))
    assert "cidata" in argv


def test_guest_component_client_unwraps_the_cli_envelope(tmp_path: Path) -> None:
    calls: list[tuple[str, ...]] = []

    def runner(argv: tuple[str, ...], _input: bytes | None, _timeout: float) -> CommandResult:
        calls.append(argv)
        remote = argv[-1]
        if "'plan'" in remote:
            data: dict[str, Any] = {
                "plan": {"planId": "p1", "confirmToken": "token", "action": "install"}
            }
        else:
            data = {"state": "missing"}
        return CommandResult(0, json.dumps({"ok": True, "data": data}).encode())

    identity = tmp_path / "steamzero-vm-key"
    client = GuestComponentClient("192.0.2.5", identity_file=identity, runner=runner)
    assert client.status("retroarch") == {"state": "missing"}
    assert client.plan("retroarch") == {
        "planId": "p1",
        "confirmToken": "token",
        "action": "install",
    }
    assert all(call[0] == "ssh" for call in calls)
    assert all("-i" in call and str(identity) in call for call in calls)
    assert all("IdentitiesOnly=yes" in call for call in calls)
    assert all("UserKnownHostsFile=/dev/null" in call for call in calls)
    assert all("GlobalKnownHostsFile=/dev/null" in call for call in calls)


def test_guest_component_client_preserves_failed_lifecycle_data() -> None:
    def runner(_argv: tuple[str, ...], _input: bytes | None, _timeout: float) -> CommandResult:
        return CommandResult(
            0,
            json.dumps({"ok": False, "error": None, "data": {"status": "failed"}}).encode(),
        )

    with pytest.raises(provision_module.GuestComponentError, match='"status": "failed"') as exc:
        GuestComponentClient("192.0.2.5", runner=runner).rollback("op-1")
    assert exc.value.envelope == {"ok": False, "error": None, "data": {"status": "failed"}}


def test_write_evidence_keeps_complete_failed_component_payload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(provision_module, "ROOT", tmp_path)
    failure = provision_module._failure_payload(
        "certificação retroarch (minimal)",
        provision_module.GuestComponentError(
            "rollback", {"ok": False, "error": {"code": "E-ROLLBACK"}, "data": {"id": "op-1"}}
        ),
    )
    evidence = provision_module._write_evidence(
        "a" * 40,
        {"ok": False, "emulators": [], "summary": {}, "protocol": "minimal"},
        baseline_restored=False,
        failure=failure,
    )
    content = evidence.read_text(encoding="utf-8")
    assert "Falha da execução" in content
    assert "certificação retroarch (minimal)" in content
    assert '"code": "E-ROLLBACK"' in content
    assert '"action": "rollback"' in content


def test_write_evidence_preserves_an_existing_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(provision_module, "ROOT", tmp_path)
    diagnostics = tmp_path / "docs" / "diagnostics"
    diagnostics.mkdir(parents=True)
    original = diagnostics / f"{provision_module.dt.date.today().isoformat()}-m10-vm-evidence.md"
    original.write_text("evidência anterior", encoding="utf-8")

    evidence = provision_module._write_evidence(
        "a" * 40,
        {"ok": False, "emulators": [], "summary": {}, "protocol": "minimal"},
        baseline_restored=False,
    )

    assert original.read_text(encoding="utf-8") == "evidência anterior"
    assert evidence != original
    assert evidence.name.startswith(original.stem + "-")


def test_snapshot_is_bootable_and_records_its_subvolume_id(tmp_path: Path) -> None:
    calls: list[tuple[str, ...]] = []

    def runner(argv: tuple[str, ...], _input: bytes | None, _timeout: float) -> CommandResult:
        calls.append(argv)
        stdout = b"Subvolume ID: 271\n" if "'show'" in argv[-1] else b""
        return CommandResult(0, stdout)

    snapshot_id = provision_module._snapshot_before(
        "192.0.2.5", identity_file=tmp_path / "steamzero-vm-key", runner=runner
    )
    assert snapshot_id == 271
    snapshot = calls[1][-1]
    assert "'snapshot'" in snapshot
    assert "'-r'" not in snapshot, "o baseline precisa ser bootável para a prova pós-reboot"


def test_destroy_vm_preserves_failure_artifacts_but_removes_named_domain(tmp_path: Path) -> None:
    config = VmConfig(
        source_commit="a" * 40,
        vm_name="steamzero-m10",
        base_image=tmp_path / "arch.qcow2",
        ssh_public_key=tmp_path / "operator.pub",
        work_dir=tmp_path / "work",
    )
    config.run_dir.mkdir(parents=True)
    (config.run_dir / ".steamzero-m10-managed").write_text(config.source_commit, encoding="utf-8")
    calls: list[tuple[str, ...]] = []

    def runner(argv: tuple[str, ...], _input: bytes | None, _timeout: float) -> CommandResult:
        calls.append(argv)
        return CommandResult(0)

    provision_module._destroy_vm(config, runner=runner, remove_run_dir=False)
    assert config.run_dir.is_dir()
    assert calls == [
        ("virsh", "--connect", "qemu:///system", "destroy", "steamzero-m10"),
        ("virsh", "--connect", "qemu:///system", "undefine", "steamzero-m10", "--nvram"),
    ]


def test_wait_for_guest_retries_a_timed_out_lease_query(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = VmConfig(
        source_commit="a" * 40,
        vm_name="steamzero-m10",
        base_image=tmp_path / "arch.qcow2",
        ssh_public_key=tmp_path / "operator.pub",
        work_dir=tmp_path / "work",
    )
    calls: list[tuple[str, ...]] = []

    def runner(argv: tuple[str, ...], _input: bytes | None, _timeout: float) -> CommandResult:
        calls.append(argv)
        raise subprocess.TimeoutExpired(list(argv), 20.0)

    monkeypatch.setattr(provision_module.time, "sleep", lambda _seconds: None)
    with pytest.raises(RuntimeError, match="não obteve IPv4/SSH"):
        provision_module._wait_for_guest(config, runner=runner, retries=1)
    assert calls == [
        (
            "virsh",
            "--connect",
            "qemu:///system",
            "domifaddr",
            "steamzero-m10",
            "--source",
            "lease",
        )
    ]


def test_wait_for_guest_retries_a_timed_out_ssh_probe(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = VmConfig(
        source_commit="a" * 40,
        vm_name="steamzero-m10",
        base_image=tmp_path / "arch.qcow2",
        ssh_public_key=tmp_path / "operator.pub",
        work_dir=tmp_path / "work",
        ssh_private_key=tmp_path / "operator.key",
    )
    lease = b"vnet0 52:54:00:00:00:01 ipv4 192.0.2.5/24\n"
    calls: list[tuple[str, ...]] = []

    def runner(argv: tuple[str, ...], _input: bytes | None, _timeout: float) -> CommandResult:
        calls.append(argv)
        if "domifaddr" in argv:
            return CommandResult(0, lease)
        raise subprocess.TimeoutExpired(list(argv), 15.0)

    monkeypatch.setattr(provision_module.time, "sleep", lambda _seconds: None)
    with pytest.raises(RuntimeError, match="não obteve IPv4/SSH"):
        provision_module._wait_for_guest(config, runner=runner, retries=1)
    assert len(calls) == 2
    assert calls[1][0] == "ssh"


def test_wait_for_guest_preserves_the_last_cloud_init_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = VmConfig(
        source_commit="a" * 40,
        vm_name="steamzero-m10",
        base_image=tmp_path / "arch.qcow2",
        ssh_public_key=tmp_path / "operator.pub",
        work_dir=tmp_path / "work",
        ssh_private_key=tmp_path / "operator.key",
    )
    lease = b"vnet0 52:54:00:00:00:01 ipv4 192.0.2.5/24\n"

    def runner(argv: tuple[str, ...], _input: bytes | None, _timeout: float) -> CommandResult:
        if "domifaddr" in argv:
            return CommandResult(0, lease)
        if "'cloud-init'" in argv[-1]:
            if "'--long'" in argv[-1]:
                return CommandResult(0, stdout=b"detailed cloud-init failure")
            return CommandResult(1, stderr=b"cloud-init ainda instalando pacotes")
        return CommandResult(0)

    monkeypatch.setattr(provision_module.time, "sleep", lambda _seconds: None)
    with pytest.raises(provision_module.GuestReadinessError) as exc:
        provision_module._wait_for_guest(config, runner=runner, retries=1)
    assert exc.value.last_issue["phase"] == "cloud-init"
    assert exc.value.last_issue["address"] == "192.0.2.5"
    assert exc.value.last_issue["command"] == {
        "label": "SSH guest (cloud-init)",
        "returncode": 1,
        "stdout": "",
        "stderr": "cloud-init ainda instalando pacotes",
    }
    assert exc.value.last_issue["cloudInitStatusLong"] == {
        "returncode": 0,
        "stdout": "detailed cloud-init failure",
        "stderr": "",
    }
    assert exc.value.last_issue["cloudInitOutputLog"] == {
        "returncode": 0,
        "stdout": "",
        "stderr": "",
    }


def test_configure_flathub_retries_only_dns_failures(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = 0

    def runner(_argv: tuple[str, ...], _input: bytes | None, _timeout: float) -> CommandResult:
        nonlocal calls
        calls += 1
        if calls < 3:
            return CommandResult(1, stderr=b"Could not resolve hostname")
        return CommandResult(0)

    sleeps: list[float] = []
    monkeypatch.setattr(provision_module.time, "sleep", sleeps.append)
    provision_module._configure_flathub(
        "192.0.2.5", identity_file=tmp_path / "steamzero-vm-key", runner=runner
    )
    assert calls == 3
    assert sleeps == [5.0, 10.0]


def test_configure_flathub_keeps_all_failed_payloads(tmp_path: Path) -> None:
    def runner(_argv: tuple[str, ...], _input: bytes | None, _timeout: float) -> CommandResult:
        return CommandResult(1, stderr=b"TLS certificate rejected")

    with pytest.raises(provision_module.FlathubSetupError) as exc:
        provision_module._configure_flathub(
            "192.0.2.5", identity_file=tmp_path / "steamzero-vm-key", runner=runner
        )
    assert exc.value.attempts == [
        {"attempt": 1, "returncode": 1, "stdout": "", "stderr": "TLS certificate rejected"}
    ]


def test_provision_orchestrates_only_disposable_resources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source_commit = "a" * 40
    config = VmConfig(
        source_commit=source_commit,
        vm_name="steamzero-m10",
        base_image=tmp_path / "arch.qcow2",
        ssh_public_key=tmp_path / "operator.pub",
        work_dir=tmp_path / "work",
        ssh_private_key=tmp_path / "operator.key",
    )
    config.base_image.write_bytes(b"qcow2")
    config.ssh_public_key.write_text(
        "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI test\n", encoding="utf-8"
    )
    config.ssh_private_key.write_text("private", encoding="utf-8")
    calls: list[tuple[str, ...]] = []
    events: list[object] = []

    def runner(argv: tuple[str, ...], _input: bytes | None, _timeout: float) -> CommandResult:
        calls.append(argv)
        if argv[:2] == ("git", "rev-parse"):
            return CommandResult(0, f"{source_commit}\n".encode())
        return CommandResult(0)

    class FakeGuest:
        def __init__(
            self, _address: str, *, identity_file: Path | None = None, runner: object
        ) -> None:
            self.identity_file = identity_file
            self.runner = runner

        def status(self, _adapter_id: str) -> dict[str, str]:
            return {"state": "missing"}

    monkeypatch.setattr(provision_module, "_preflight", lambda: events.append("preflight"))
    monkeypatch.setattr(provision_module, "_wait_for_guest", lambda *_a, **_k: "192.0.2.5")
    monkeypatch.setattr(
        provision_module,
        "_copy_source",
        lambda *_a, **_k: events.append("copy-source"),
    )
    monkeypatch.setattr(
        provision_module,
        "_configure_flathub",
        lambda *_a, **_k: events.append("flathub"),
    )
    monkeypatch.setattr(
        provision_module,
        "_snapshot_before",
        lambda *_a, **_k: 271,
    )
    monkeypatch.setattr(
        provision_module,
        "_restore_snapshot",
        lambda *_a, **_k: events.append("restore"),
    )
    monkeypatch.setattr(provision_module, "GuestComponentClient", FakeGuest)
    monkeypatch.setattr(
        provision_module,
        "_selected_certification",
        lambda _client, **_kwargs: {"ok": True, "emulators": [], "summary": {}, "pins": {}},
    )
    evidence = tmp_path / "evidence.md"
    monkeypatch.setattr(
        provision_module,
        "_write_evidence",
        lambda *_a, **_k: evidence,
    )
    monkeypatch.setattr(
        provision_module,
        "_destroy_vm",
        lambda *_a, **_k: events.append("destroy"),
    )

    assert (
        provision_module.provision(
            config, runner=runner, adapter_id="retroarch", protocol="minimal"
        )
        == evidence
    )
    assert events == ["preflight", "flathub", "copy-source", "restore", "destroy"]
    qemu_img = next(command for command in calls if command[0] == "qemu-img")
    assert str(config.base_image.resolve()) in qemu_img
    assert any(command[0] in {"cloud-localds", "xorriso", "genisoimage"} for command in calls)
    assert any(command[0] == "virt-install" for command in calls)
    assert any(command[0] == "virsh" and "ttyconsole" in command for command in calls)


def test_provision_writes_failed_component_payload_before_cleanup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source_commit = "a" * 40
    config = VmConfig(
        source_commit=source_commit,
        vm_name="steamzero-m10",
        base_image=tmp_path / "arch.qcow2",
        ssh_public_key=tmp_path / "operator.pub",
        ssh_private_key=tmp_path / "operator.key",
        work_dir=tmp_path / "work",
    )
    config.base_image.write_bytes(b"qcow2")
    config.ssh_public_key.write_text(
        "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI test\n", encoding="utf-8"
    )
    config.ssh_private_key.write_text("private", encoding="utf-8")
    events: list[str] = []
    seen_failure: dict[str, Any] | None = None

    def runner(argv: tuple[str, ...], _input: bytes | None, _timeout: float) -> CommandResult:
        if argv[:2] == ("git", "rev-parse"):
            return CommandResult(0, f"{source_commit}\n".encode())
        return CommandResult(0)

    monkeypatch.setattr(provision_module, "_preflight", lambda: None)
    monkeypatch.setattr(provision_module, "_wait_for_guest", lambda *_a, **_k: "192.0.2.5")
    monkeypatch.setattr(provision_module, "_copy_source", lambda *_a, **_k: None)
    monkeypatch.setattr(provision_module, "_configure_flathub", lambda *_a, **_k: None)
    monkeypatch.setattr(provision_module, "_snapshot_before", lambda *_a, **_k: 271)
    monkeypatch.setattr(provision_module, "GuestComponentClient", lambda *_a, **_k: object())
    component_error = provision_module.GuestComponentError(
        "rollback", {"ok": False, "error": {"code": "E-ROLLBACK"}, "data": {"id": "op-1"}}
    )
    monkeypatch.setattr(
        provision_module,
        "_selected_certification",
        lambda *_a, **_k: (_ for _ in ()).throw(component_error),
    )

    def write_evidence(*_args: Any, **kwargs: Any) -> Path:
        nonlocal seen_failure
        events.append("evidence")
        seen_failure = kwargs["failure"]
        return tmp_path / "evidence.md"

    monkeypatch.setattr(provision_module, "_write_evidence", write_evidence)
    monkeypatch.setattr(
        provision_module,
        "_destroy_vm",
        lambda *_a, **_k: events.append("destroy"),
    )

    with pytest.raises(provision_module.GuestComponentError):
        provision_module.provision(
            config, runner=runner, adapter_id="retroarch", protocol="minimal"
        )
    assert events == ["evidence", "destroy"]
    assert seen_failure == {
        "stage": "certificação retroarch (minimal)",
        "exception": {
            "type": "GuestComponentError",
            "message": 'component rollback falhou: {"code": "E-ROLLBACK"}',
        },
        "component": {
            "action": "rollback",
            "envelope": {"ok": False, "error": {"code": "E-ROLLBACK"}, "data": {"id": "op-1"}},
        },
        "expectedPins": provision_module.m10_pinned_commits(),
    }
