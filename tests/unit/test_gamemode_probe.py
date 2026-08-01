# SPDX-License-Identifier: GPL-3.0-or-later
"""G29: verdade observada do Feral GameMode — regressões 1 a 14.

Probe read-only com dependências injetáveis: nenhum teste toca ferramentas
reais do host (which, runner, grupos, relógio e store são fakes).
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from steamzero.adapters.gamemode_probe import GameModeProbe, snapshot
from steamzero.adapters.steam_gameplay import SteamGameplayController
from steamzero.api import contracts
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore
from steamzero.domain.gamemode import (
    GameModeTruth,
    build_admin_plan,
    build_truth,
    render_admin_plan,
    validate_admin_plan,
)

SECRET = "segredo-que-nunca-deve-vazar-g29-42"

_OK_KEYS = {
    "binaryState",
    "daemonState",
    "authorizationState",
    "capabilityState",
    "activityState",
    "effects",
    "condition",
    "state",
    "statusLabel",
    "cause",
    "remediation",
    "requiresOperator",
}


def _completed(
    returncode: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["/usr/bin/gamemoded", "-s"], returncode, stdout, stderr)


def _store(session: dict[str, Any] | None = None, *, error: Exception | None = None):
    class FakeStore:
        def migrate(self) -> None:
            return

        def active_game_session(self, owner: str) -> dict[str, Any] | None:
            if error is not None:
                raise error
            return session

        def __enter__(self) -> FakeStore:
            return self

        def __exit__(self, *args: object) -> None:
            return

    return lambda: FakeStore()


def _probe(
    *,
    available: frozenset[str] = frozenset({"gamemoderun", "gamemoded"}),
    runner: Any = None,
    connect: str = "ok",
    governor: str = "performance",
    split_lock: str = "0",
    session: dict[str, Any] | None = None,
    store_error: Exception | None = None,
    socket_path: Path = Path("unused/gamemode.sock"),
) -> GameModeProbe:
    def which(name: str) -> str | None:
        return f"/usr/bin/{name}" if name in available else None

    def default_runner(_argv: list[str], _timeout: float) -> subprocess.CompletedProcess[str]:
        return _completed(0, "Server is running (v1.8.1)\n")

    if runner is None:
        runner = default_runner

    def connect_unix(_path: Path) -> str:
        return connect

    def read_text(path: Path) -> str:
        if path.name == "scaling_governor":
            return governor
        return split_lock

    return GameModeProbe(
        which=which,
        runner=runner,
        connect_unix=connect_unix,
        read_text=read_text,
        socket_path=socket_path,
        store_factory=_store(session, error=store_error),
    )


def _idle_session() -> dict[str, Any]:
    return {"game_id": "10", "state": "running", "owner": "steamzero-game-session"}


class TestBinary:
    def test_binary_missing_never_ready(self) -> None:
        truth = _probe(available=frozenset()).probe()
        assert truth.condition == "missing"
        assert truth.binary_state == "missing"
        assert truth.capability_state == "missing"
        assert truth.state == "missing"
        assert truth.status_label == "GameMode não instalado"
        assert truth.requires_operator is True

    def test_binary_missing_short_circuits_host_tools(self) -> None:
        def forbidden(*_args: object, **_kwargs: object) -> Any:
            raise AssertionError("probe não pode rodar ferramentas com binário ausente")

        probe = GameModeProbe(
            which=lambda _name: None,
            runner=forbidden,
            read_text=forbidden,
            connect_unix=lambda _path: "absent",
            store_factory=_store(None),
            socket_path=Path("unused/gamemode.sock"),
        )
        assert probe.probe().condition == "missing"


class TestDaemon:
    def test_daemon_unavailable_degrades(self) -> None:
        truth = _probe(available=frozenset({"gamemoderun"}), connect="absent").probe()
        assert truth.daemon_state == "unavailable"
        assert truth.condition == "daemon-unavailable"
        assert truth.capability_state == "degraded"
        assert truth.state == "degraded"
        assert truth.status_label == "Daemon indisponível"
        assert truth.requires_operator is True

    def test_daemon_nonzero_returncode_degrades_never_ready(self) -> None:
        truth = _probe(runner=lambda _a, _t: _completed(2, "syntax error")).probe()
        assert truth.daemon_state == "unavailable"
        assert truth.condition == "daemon-unavailable"
        assert truth.state == "degraded"
        assert truth.status_label == "Daemon indisponível"
        assert truth.state != "ready"

    def test_ambiguous_daemon_output_is_unknown_never_ready(self) -> None:
        truth = _probe(runner=lambda _a, _t: _completed(0, "bogus")).probe()
        assert truth.daemon_state == "unknown"
        assert truth.condition == "daemon-unknown"
        assert truth.state == "unknown"
        assert truth.status_label == "Não foi possível verificar"

    def test_timeout_yields_unknown_and_snapshot_available(self) -> None:
        def timeout_runner(_argv: list[str], _timeout: float) -> subprocess.CompletedProcess[str]:
            raise subprocess.TimeoutExpired("/usr/bin/gamemoded", 3.0)

        probe = _probe(runner=timeout_runner)
        assert probe.probe().daemon_state == "unknown"
        assert snapshot(probe=probe)["state"] == "unknown"


class TestAuthorization:
    def test_auth_denied_visible_with_admin_action(self) -> None:
        truth = _probe(connect="permission-denied").probe()
        assert truth.authorization_state == "denied"
        assert truth.condition == "auth-denied"
        assert truth.state == "degraded"
        assert truth.status_label == "Autorização necessária"
        assert truth.requires_operator is True
        plan = build_admin_plan(truth)
        assert plan["requiresOperator"] is True
        assert plan["executesHostChanges"] is False
        assert plan["remediationSteps"]

    def test_auth_unknown_never_claims_success(self) -> None:
        truth = _probe(connect="error").probe()
        assert truth.authorization_state == "unknown"
        assert truth.condition == "auth-unknown"
        assert truth.state == "unknown"
        assert truth.status_label == "Não foi possível verificar"


class TestActivity:
    def test_authorized_idle_is_ready_not_failure(self) -> None:
        truth = _probe(session=None).probe()
        assert truth.activity_state == "idle"
        assert truth.condition == "idle"
        assert truth.state == "ready"
        assert truth.status_label == "Pronto para otimizações"
        assert truth.effects == {"governor": "unknown", "splitLock": "unknown", "ioprio": "unknown"}

    def test_active_session_with_all_effects_applied(self) -> None:
        truth = _probe(session=_idle_session()).probe()
        assert truth.activity_state == "active"
        assert truth.condition == "active"
        assert truth.state == "ready"
        assert truth.status_label == "Otimizações ativas"
        assert truth.effects["governor"] == "applied"
        assert truth.effects["splitLock"] == "applied"

    def test_partial_lists_denied_effects(self) -> None:
        truth = _probe(session=_idle_session(), governor="powersave").probe()
        assert truth.activity_state == "partial"
        assert truth.condition == "partial"
        assert truth.state == "degraded"
        assert truth.status_label == "Otimizações parcialmente aplicadas"
        assert truth.effects["governor"] == "denied"
        assert "governor" in truth.cause

    def test_session_store_error_is_unknown_activity(self) -> None:
        truth = _probe(session=_idle_session(), store_error=OSError("lock")).probe()
        assert truth.activity_state == "unknown"
        assert truth.condition == "activity-unknown"
        assert truth.state == "unknown"

    def test_permission_denied_reads_do_not_crash(self) -> None:
        def denied_read(_path: Path) -> str:
            raise PermissionError("denied")

        probe = _probe(session=_idle_session())
        probe._read_text = denied_read  # type: ignore[assignment]
        truth = probe.probe()
        assert truth.effects["governor"] == "unknown"
        assert truth.effects["splitLock"] == "unknown"
        assert truth.condition == "active"


class TestProbeContract:
    def test_serialized_keys_are_stable_and_sanitized(self) -> None:
        truth = _probe(session=_idle_session()).probe()
        assert set(truth.to_dict()) == _OK_KEYS
        rendered = json.dumps(truth.to_dict(), ensure_ascii=False)
        for forbidden in ("argv", "stdout", "stderr", "command", "/usr/bin", "/home", "SECRET"):
            assert forbidden not in rendered

    def test_sensitive_outputs_never_leak(self) -> None:
        def leaky_runner(_argv: list[str], _timeout: float) -> subprocess.CompletedProcess[str]:
            return _completed(0, f"Server is running {SECRET}\n")

        def leaky_read(_path: Path) -> str:
            return SECRET

        probe = _probe(runner=leaky_runner, session=_idle_session())
        probe._read_text = leaky_read  # type: ignore[assignment]
        data = snapshot(probe=probe)
        rendered = json.dumps(data, ensure_ascii=False)
        assert SECRET not in rendered
        assert "gamemoded" not in rendered

    def test_controller_snapshot_degrades_gamemode_section_on_timeout(self, tmp_path: Path) -> None:
        def timeout_runner(_argv: list[str], _timeout: float) -> subprocess.CompletedProcess[str]:
            raise subprocess.TimeoutExpired("/usr/bin/gamemoded", 3.0)

        root = tmp_path / "Steam"
        (root / "steamapps").mkdir(parents=True)
        controller = SteamGameplayController(
            roots=(root,),
            which=lambda _name: None,
            store_factory=lambda: StateStore(tmp_path / "state.db"),
            gamemode_probe=_probe(runner=timeout_runner),
        )
        result = controller.snapshot({"context": {"deviceKind": "linux"}})
        assert result["gamemode"]["state"] == "unknown"
        gamemode_row = next(row for row in result["environment"] if row["id"] == "gamemode")
        assert gamemode_row["state"] == "unknown"
        assert gamemode_row["statusLabel"] == "Não foi possível verificar"
        assert result["readiness"]["percent"] < 100

    def test_controller_snapshot_ready_row_when_fully_observed(self, tmp_path: Path) -> None:
        root = tmp_path / "Steam"
        (root / "steamapps").mkdir(parents=True)
        controller = SteamGameplayController(
            roots=(root,),
            which=lambda _name: None,
            store_factory=lambda: StateStore(tmp_path / "state.db"),
            gamemode_probe=_probe(session=None),
        )
        result = controller.snapshot({"context": {"deviceKind": "linux"}})
        assert result["gamemode"]["state"] == "ready"
        gamemode_row = next(row for row in result["environment"] if row["id"] == "gamemode")
        assert gamemode_row["state"] == "ready"
        assert gamemode_row["statusLabel"] == "Pronto para otimizações"
        assert gamemode_row["detail"] == "Ocioso — nenhum jogo usando GameMode"
        assert result["readiness"]["percent"] == 67


class TestSharedState:
    def test_cli_snapshot_and_workspace_snapshot_share_derivation(self) -> None:
        probe = _probe(connect="permission-denied")
        cli_side = snapshot(probe=probe)
        assert cli_side["state"] == "degraded"
        assert cli_side["statusLabel"] == "Autorização necessária"
        assert snapshot(probe=_probe(session=None))["state"] == "ready"


class TestAdminPlan:
    def test_plan_validates_against_schema_and_is_declarative(self) -> None:
        truth = _probe(connect="permission-denied").probe()
        plan = build_admin_plan(truth, now=datetime(2026, 8, 1, tzinfo=UTC))
        contracts.validate(plan, "gamemode-admin-plan-v1.schema.json")
        assert plan["adapterId"] == "gamemode"
        assert plan["executesHostChanges"] is False
        assert plan["condition"] == "auth-denied"
        assert plan["preview"]

    def test_invalid_plan_raises_domain_error_never_key_error(self) -> None:
        payload = render_admin_plan(
            build_truth(
                binary_state="present",
                daemon_state="available",
                authorization_state="authorized",
                activity_state="idle",
                effects={"governor": "unknown", "splitLock": "unknown", "ioprio": "unknown"},
            ),
            plan_id="not-a-ulid",
            confirm_token="x",
            created_at=datetime(2026, 8, 1, tzinfo=UTC),
            expires_at=datetime(2026, 8, 1, 0, 15, tzinfo=UTC),
        )
        with pytest.raises(SteamZeroError) as error:
            validate_admin_plan(payload)
        assert error.value.code == "E-STATE-INTEGRITY"

    def test_invalid_condition_is_domain_error(self) -> None:
        with pytest.raises(SteamZeroError) as error:
            validate_admin_plan({"condition": "inventado", "executesHostChanges": False})
        assert error.value.code == "E-STATE-INTEGRITY"

    def test_controller_exposes_plan_without_apply_path(self) -> None:
        assert not hasattr(SteamGameplayController, "apply_gamemode_admin_plan")
        assert not hasattr(SteamGameplayController, "apply_gamemode")


class TestTruthInvariants:
    def test_build_truth_rejects_invalid_states(self) -> None:
        with pytest.raises(ValueError):
            build_truth(
                binary_state="inventado",
                daemon_state="available",
                authorization_state="authorized",
                activity_state="idle",
                effects={},
            )

    def test_failure_truth_is_unknown_never_green(self) -> None:
        truth = GameModeTruth.failure()
        assert truth.condition == "probe-failed"
        assert truth.state == "unknown"
        assert truth.status_label == "Não foi possível verificar"

    def test_condition_hierarchy_hides_nothing_below_missing(self) -> None:
        truth = build_truth(
            binary_state="missing",
            daemon_state="available",
            authorization_state="authorized",
            activity_state="active",
            effects={"governor": "applied", "splitLock": "applied", "ioprio": "unknown"},
        )
        assert truth.condition == "missing"
        assert truth.status_label == "GameMode não instalado"
