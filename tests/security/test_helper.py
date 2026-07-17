# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Testes de segurança do helper privilegiado (ST-01, AC-PR-01/02)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from steamzero.core.errors import SteamZeroError
from steamzero.privileged import protocol
from steamzero.privileged.client import AdminClient, PkexecHealthTransport, ProcessResult
from steamzero.privileged.helper import AdminHelper, DryEffector, HostEffector, main
from steamzero.privileged.protocol import PROTOCOL_VERSION, Request


def _helper(audit: Path | None = None) -> tuple[AdminHelper, DryEffector]:
    eff = DryEffector()
    return AdminHelper(eff, audit_path=audit), eff


@pytest.mark.security
def test_valid_set_tdp_executes() -> None:
    helper, eff = _helper()
    resp = helper.handle(Request("set-tdp", {"watts": 12}))
    assert resp.ok
    assert eff.calls == [("set-tdp", {"watts": 12})]


@pytest.mark.security
@pytest.mark.parametrize("watts", [2, 31, 9999, -5, 0, True, "12", 12.5, None])
def test_fuzz_set_tdp_out_of_range_denied_no_execution(watts: object) -> None:
    helper, eff = _helper()
    resp = helper.handle(Request("set-tdp", {"watts": watts}))
    assert not resp.ok
    assert resp.error is not None and resp.error["code"] == "E-PRIV-DENIED"
    assert eff.calls == []  # fuzzing nunca chega ao efetor


@pytest.mark.security
def test_extra_param_key_denied() -> None:
    helper, eff = _helper()
    resp = helper.handle(Request("set-tdp", {"watts": 10, "cmd": "rm -rf /"}))
    assert not resp.ok
    assert resp.error["code"] == "E-PRIV-DENIED"
    assert eff.calls == []


@pytest.mark.security
def test_unknown_action_denied() -> None:
    helper, eff = _helper()
    resp = helper.handle(Request("run-shell", {"cmd": "id"}))
    assert not resp.ok
    assert resp.error["code"] == "E-PRIV-DENIED"
    assert eff.calls == []


@pytest.mark.security
def test_protocol_mismatch_refused() -> None:
    helper, _ = _helper()
    resp = helper.handle(Request("set-tdp", {"watts": 10}, protocol_version=PROTOCOL_VERSION + 1))
    assert not resp.ok
    assert resp.error["code"] == "E-PRIV-PROTO-MISMATCH"


@pytest.mark.security
@pytest.mark.parametrize(
    "uuid",
    ["../../etc/passwd", "/dev/sda1", "1234-ABCD/../x", "; reboot", "", "not a uuid", "AAAA_BBBB"],
)
def test_mount_removable_rejects_bad_uuid(uuid: str) -> None:
    helper, eff = _helper()
    resp = helper.handle(Request("mount-removable", {"uuid": uuid, "mode": "ro"}))
    assert not resp.ok
    assert resp.error["code"] == "E-PRIV-DENIED"
    assert eff.calls == []


@pytest.mark.security
def test_mount_removable_valid_uuid() -> None:
    helper, eff = _helper()
    assert helper.handle(Request("mount-removable", {"uuid": "1234-ABCD", "mode": "rw"})).ok
    assert helper.handle(
        Request("mount-removable", {"uuid": "12345678-9abc-def0-1234-56789abcdef0", "mode": "ro"})
    ).ok
    assert len(eff.calls) == 2


@pytest.mark.security
def test_write_sysctl_allowlist() -> None:
    helper, eff = _helper()
    # key fora da allowlist (perigosa)
    assert not helper.handle(Request("write-sysctl", {"key": "kernel.core_pattern", "value": 1})).ok
    # key permitida, valor fora da faixa
    assert not helper.handle(Request("write-sysctl", {"key": "vm.swappiness", "value": 9999})).ok
    # válido
    assert helper.handle(Request("write-sysctl", {"key": "vm.swappiness", "value": 10})).ok
    assert eff.calls == [("write-sysctl", {"key": "vm.swappiness", "value": 10})]


@pytest.mark.security
def test_udev_and_unit_enum_only() -> None:
    helper, _eff = _helper()
    assert not helper.handle(Request("install-udev-rule", {"ruleId": "arbitrary"})).ok
    # o chamador não pode injetar conteúdo (chave 'content' extra é rejeitada)
    assert not helper.handle(
        Request("install-udev-rule", {"ruleId": "steam-controller", "content": "KERNEL==*"})
    ).ok
    assert helper.handle(Request("install-udev-rule", {"ruleId": "steam-controller"})).ok
    assert not helper.handle(Request("enable-system-unit", {"unitId": "sshd.service"})).ok


@pytest.mark.security
def test_authorizer_denies() -> None:
    helper = AdminHelper(DryEffector(), authorizer=lambda _a, _c: False)
    resp = helper.handle(Request("set-tdp", {"watts": 10}))
    assert not resp.ok
    assert resp.error["code"] == "E-PRIV-DENIED"


@pytest.mark.security
def test_audit_log_written(tmp_path: Path) -> None:
    audit = tmp_path / "admin-audit.jsonl"
    helper, _ = _helper(audit)
    helper.handle(Request("set-tdp", {"watts": 10}))
    helper.handle(Request("set-tdp", {"watts": 9999}))
    lines = [json.loads(x) for x in audit.read_text().splitlines()]
    assert [rec["outcome"] for rec in lines] == ["allowed", "denied"]
    assert all(rec["action"] == "set-tdp" for rec in lines)


@pytest.mark.security
def test_client_forwards_to_helper() -> None:
    helper, eff = _helper()
    client = AdminClient(helper)
    assert client.available() is True
    resp = client.request("set-tdp", {"watts": 11})
    assert resp.ok
    assert eff.calls == [("set-tdp", {"watts": 11})]
    # o client injeta o protocolo correto -> ação inválida ainda é negada pelo helper
    assert not client.request("run-shell", {"x": 1}).ok


@pytest.mark.security
def test_client_helper_missing() -> None:
    client = AdminClient(None)
    assert client.available() is False
    with pytest.raises(SteamZeroError) as ei:
        client.request("set-tdp", {"watts": 10})
    assert ei.value.code == "E-PRIV-HELPER-MISSING"


@pytest.mark.security
def test_pkexec_transport_uses_fixed_argv_and_parses_health(tmp_path: Path) -> None:
    pkexec = tmp_path / "pkexec"
    helper = tmp_path / "steamzero-admin"
    for path in (pkexec, helper):
        path.write_text("fixture", encoding="utf-8")
        path.chmod(0o755)
    calls: list[tuple[tuple[str, ...], float]] = []

    def run(argv: tuple[str, ...], timeout: float) -> ProcessResult:
        calls.append((argv, timeout))
        payload = {
            "ok": True,
            "result": {
                "healthy": True,
                "protocolVersion": 1,
                "effectiveUid": 0,
                "mutationsEnabled": False,
            },
            "error": None,
        }
        return ProcessResult(0, json.dumps(payload).encode(), b"")

    transport = PkexecHealthTransport(
        pkexec=pkexec,
        helper=helper,
        runner=run,
        timeout=1,
    )
    client = AdminClient(None, transport=transport)
    assert client.available() is True
    response = client.request("health", {})
    assert response.ok and response.result is not None
    assert response.result["mutationsEnabled"] is False
    assert calls == [((str(pkexec), str(helper), "--health"), 5.0)]


@pytest.mark.security
def test_pkexec_transport_never_spawns_for_mutation(tmp_path: Path) -> None:
    called = False

    def run(_argv: tuple[str, ...], _timeout: float) -> ProcessResult:
        nonlocal called
        called = True
        raise AssertionError("runner não deve ser chamado")

    transport = PkexecHealthTransport(
        pkexec=tmp_path / "missing-pkexec",
        helper=tmp_path / "missing-helper",
        runner=run,
    )
    response = transport.request("set-tdp", {"watts": 10})
    assert not response.ok
    assert response.error is not None and response.error["code"] == "E-PRIV-DENIED"
    assert called is False


@pytest.mark.security
def test_pkexec_transport_reports_missing_and_polkit_denial(tmp_path: Path) -> None:
    missing = PkexecHealthTransport(
        pkexec=tmp_path / "missing-pkexec",
        helper=tmp_path / "missing-helper",
    )
    with pytest.raises(SteamZeroError, match="E-PRIV-HELPER-MISSING"):
        missing.request("health", {})

    pkexec = tmp_path / "pkexec"
    helper = tmp_path / "helper"
    for path in (pkexec, helper):
        path.write_text("fixture", encoding="utf-8")
        path.chmod(0o755)
    denied = PkexecHealthTransport(
        pkexec=pkexec,
        helper=helper,
        runner=lambda _argv, _timeout: ProcessResult(126, b"", b"denied"),
    ).request("health", {})
    assert not denied.ok
    assert denied.error is not None and denied.error["code"] == "E-PRIV-DENIED"


@pytest.mark.security
@pytest.mark.parametrize(
    ("result", "detail"),
    [
        (ProcessResult(0, b"not-json", b""), "JSON inválido"),
        (ProcessResult(0, b'{"ok":true}', b""), "envelope"),
        (
            ProcessResult(1, b'{"ok":true,"result":{},"error":null}', b""),
            "sucesso inconsistente",
        ),
        (
            ProcessResult(0, b'{"ok":false,"result":null,"error":{}}', b""),
            "falha inconsistente",
        ),
    ],
)
def test_pkexec_transport_rejects_malformed_helper_contract(
    tmp_path: Path, result: ProcessResult, detail: str
) -> None:
    pkexec = tmp_path / "pkexec"
    helper = tmp_path / "helper"
    for path in (pkexec, helper):
        path.write_text("fixture", encoding="utf-8")
        path.chmod(0o755)
    transport = PkexecHealthTransport(
        pkexec=pkexec,
        helper=helper,
        runner=lambda _argv, _timeout: result,
    )
    with pytest.raises(SteamZeroError, match="E-PRIV-PROTO-MISMATCH") as raised:
        transport.request("health", {})
    assert detail in raised.value.detail


@pytest.mark.security
def test_pkexec_transport_bounds_output_and_timeout(tmp_path: Path) -> None:
    pkexec = tmp_path / "pkexec"
    helper = tmp_path / "helper"
    for path in (pkexec, helper):
        path.write_text("fixture", encoding="utf-8")
        path.chmod(0o755)
    oversized = PkexecHealthTransport(
        pkexec=pkexec,
        helper=helper,
        runner=lambda _argv, _timeout: ProcessResult(0, b"x" * 65537, b""),
    )
    with pytest.raises(SteamZeroError, match="E-PRIV-PROTO-MISMATCH"):
        oversized.request("health", {})

    def timeout(_argv: tuple[str, ...], _seconds: float) -> ProcessResult:
        raise subprocess.TimeoutExpired("pkexec", 5)

    timed = PkexecHealthTransport(pkexec=pkexec, helper=helper, runner=timeout)
    with pytest.raises(SteamZeroError, match="E-PRIV-DENIED"):
        timed.request("health", {})


@pytest.mark.security
def test_ac_pr_02_allowlist_is_only_privileged_ops() -> None:
    # AC-PR-02: fluxos comuns (config write, library, import) NÃO estão na allowlist.
    assert set(protocol.ACTIONS) == {
        "health",
        "set-tdp",
        "set-gpu-clock",
        "write-sysctl",
        "install-udev-rule",
        "enable-system-unit",
        "mount-removable",
    }


@pytest.mark.security
def test_host_effector_only_exposes_read_only_health() -> None:
    health = AdminHelper(HostEffector()).handle(Request("health", {}))
    assert health.ok and health.result is not None
    assert health.result["mutationsEnabled"] is False
    denied = AdminHelper(HostEffector()).handle(Request("set-tdp", {"watts": 10}))
    assert not denied.ok
    assert denied.error is not None and denied.error["code"] == "E-PRIV-DENIED"


@pytest.mark.security
def test_admin_entrypoint_requires_root(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("steamzero.privileged.helper.os.geteuid", lambda: 1000)
    assert main(["--health"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["code"] == "E-PRIV-DENIED"


@pytest.mark.security
def test_admin_entrypoint_health_as_polkit_root(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("steamzero.privileged.helper.os.geteuid", lambda: 0)
    monkeypatch.setenv("PKEXEC_UID", "1000")
    monkeypatch.setattr(AdminHelper, "_audit", lambda *_args: None)
    assert main(["--health"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["result"]["protocolVersion"] == PROTOCOL_VERSION
    assert payload["result"]["mutationsEnabled"] is False


@pytest.mark.security
@given(
    action=st.text(min_size=0, max_size=20),
    params=st.dictionaries(st.text(max_size=8), st.integers() | st.text(max_size=8), max_size=4),
)
def test_fuzz_never_executes_without_full_gate(action: str, params: dict[str, object]) -> None:
    # ST-01: nenhuma execução sem passar por todo o gate de validação.
    helper, eff = _helper()
    resp = helper.handle(Request(action, params))
    if resp.ok:
        # só pode ter executado se a ação existe e o efetor foi chamado exatamente 1x
        assert action in protocol.ACTIONS
        assert len(eff.calls) == 1
    else:
        assert eff.calls == []
