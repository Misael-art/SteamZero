# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""G27: fachada ComponentLifecycle — roteamento, verdade de estado e planos v2.

A matriz AppImage/Flatpak x missing/installed/degraded/EOL é o contrato: nenhum
estado pode colapsar em outro, falha de um adapter não derruba os demais, e o
plano v2 sobrevive a processos diferentes. Nenhum teste executa flatpak real
nem toca o host.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest

from fixtures.eol_adapter import EOL_ID, EOL_REF, eol_registry
from steamzero.adapters.flatpak import FlatpakState
from steamzero.adapters.lifecycle import ComponentLifecycle, route_for
from steamzero.adapters.registry import AdapterRegistry, AdapterSource, load_manifest
from steamzero.core import fs, paths, state
from steamzero.core.errors import SteamZeroError

TARGET = "a" * 64


class FakeFlatpak:
    """Porta Flatpak determinística: instala, deploya e resolve commits pinados."""

    def __init__(self, initial: FlatpakState | None = None) -> None:
        self.current = initial or FlatpakState(False, "org.libretro.RetroArch")
        self.available = {TARGET}
        self.blocked: set[str] = set()
        self.fail_status: Exception | None = None
        self.calls: list[tuple[object, ...]] = []

    def status(self, ref: str) -> FlatpakState:
        self.calls.append(("status", ref))
        if self.fail_status is not None:
            raise self.fail_status
        if self.current.ref != ref:
            return FlatpakState(False, ref)
        return self.current

    def resolve(self, remote: str, ref: str, commit: str) -> str:
        self.calls.append(("resolve", remote, ref, commit))
        if commit in self.blocked:
            raise SteamZeroError("E-SUPPLY-UPSTREAM-GONE")
        return commit

    def install(self, remote: str, ref: str) -> None:
        self.calls.append(("install", remote, ref))
        self.current = FlatpakState(True, ref, remote, "f" * 64)

    def deploy(self, ref: str, commit: str) -> None:
        self.calls.append(("deploy", ref, commit))
        self.current = FlatpakState(True, ref, self.current.origin or "flathub", commit)

    def uninstall(self, ref: str) -> None:
        self.calls.append(("uninstall", ref))
        self.current = FlatpakState(False, ref)

    def smoke(self, ref: str, arguments: Sequence[str]) -> None:
        self.calls.append(("smoke", ref, *arguments))


class FakeArtifacts:
    def __init__(self, artifacts: dict[str, bytes]) -> None:
        self.artifacts = artifacts
        self.requests: list[str] = []

    def fetch(self, source: AdapterSource) -> bytes:
        assert source.url is not None
        self.requests.append(source.url)
        return self.artifacts[source.url]


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[state.StateStore]:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    fs.ensure_state_layout()
    opened = state.open_state()
    yield opened
    opened.close()


def portable_manifest(
    version: str,
    payload: bytes,
    *,
    capabilities: list[str] | None = None,
) -> dict:
    return {
        "schemaVersion": 1,
        "id": "demo-emulator",
        "kind": "emulator",
        "platforms": ["demo"],
        "capabilities": capabilities
        or ["detect", "status", "install", "update", "verify", "uninstall"],
        "sources": [
            {
                "type": "appimage",
                "version": version,
                "priority": 1,
                "url": f"https://fixtures.invalid/demo-{version}.AppImage",
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        ],
        "verify": {"smokeTest": ["--version"]},
        "license": "MIT",
        "upstream": "https://example.invalid/demo",
    }


def executable_payload(body: str = "#!/bin/sh\necho ok\n") -> bytes:
    return body.encode()


def portable_registry(
    version: str, payload: bytes, *, capabilities: list[str] | None = None
) -> AdapterRegistry:
    return AdapterRegistry(
        [load_manifest(portable_manifest(version, payload, capabilities=capabilities))]
    )


def bundled_with_fake(flatpak: FakeFlatpak, store: state.StateStore) -> ComponentLifecycle:
    registry = AdapterRegistry.bundled()
    return ComponentLifecycle(
        store,
        registry,
        flatpak_factory=lambda: flatpak,  # type: ignore[arg-type]
    )


def eol_with_fake(flatpak: FakeFlatpak, store: state.StateStore) -> ComponentLifecycle:
    return ComponentLifecycle(
        store,
        eol_registry(),
        flatpak_factory=lambda: flatpak,  # type: ignore[arg-type]
    )


class TestRoutingMatrix:
    """AppImage/Flatpak x missing/installed/degraded/EOL sem colapso de estado."""

    def test_portable_missing(self, store: state.StateStore, tmp_path: Path) -> None:
        registry = portable_registry("1.0.0", executable_payload())
        lifecycle = ComponentLifecycle(store, registry, artifacts=FakeArtifacts({}))
        status = lifecycle.status("demo-emulator")
        assert status["state"] == "missing"
        assert status["installed"] is False
        assert status["executor"] == "engine"
        assert status["sourceType"] == "appimage"
        assert status["targetVersion"] == "1.0.0"

    def test_portable_installed(self, store: state.StateStore, tmp_path: Path) -> None:
        payload = executable_payload()
        registry = portable_registry("1.0.0", payload)
        lifecycle = ComponentLifecycle(
            store,
            registry,
            artifacts=FakeArtifacts({"https://fixtures.invalid/demo-1.0.0.AppImage": payload}),
        )
        envelope = lifecycle.plan("demo-emulator", "install")
        result = lifecycle.apply(envelope.plan_id, envelope.confirm_token)
        assert result["executor"] == "engine"
        status = lifecycle.status("demo-emulator")
        assert status["state"] == "installed"
        assert status["installed"] is True
        assert status["version"] == "1.0.0"

    def test_portable_degraded_preserves_version_and_origin(
        self, store: state.StateStore, tmp_path: Path
    ) -> None:
        payload = executable_payload()
        registry = portable_registry("1.0.0", payload)
        lifecycle = ComponentLifecycle(
            store,
            registry,
            artifacts=FakeArtifacts({"https://fixtures.invalid/demo-1.0.0.AppImage": payload}),
        )
        envelope = lifecycle.plan("demo-emulator", "install")
        lifecycle.apply(envelope.plan_id, envelope.confirm_token)
        root = store_paths_component_root(tmp_path)
        current = root / "demo-emulator" / "current.json"
        metadata = json.loads(current.read_text(encoding="utf-8"))
        metadata["manifestHash"] = "0" * 64
        fs.write_atomic_text(current, json.dumps(metadata))

        status = lifecycle.status("demo-emulator")
        assert status["state"] == "degraded", "drift de manifesto não pode virar 'não instalado'"
        assert status["installed"] is False
        assert status["version"] == "1.0.0", "versão do drift precisa ser preservada"
        assert status["origin"] == "appimage"
        assert status["detail"]

    def test_flatpak_missing(self, store: state.StateStore) -> None:
        lifecycle = bundled_with_fake(
            FakeFlatpak(FlatpakState(False, "org.libretro.RetroArch")), store
        )
        status = lifecycle.status("retroarch")
        assert status["state"] == "missing"
        assert status["executor"] == "flatpak"
        assert status["sourceType"] == "flatpak"
        expected = AdapterRegistry.bundled().get("retroarch").preferred_source("flatpak").version
        assert status["targetVersion"] == expected

    def test_flatpak_installed(self, store: state.StateStore) -> None:
        expected = AdapterRegistry.bundled().get("retroarch").preferred_source("flatpak").version
        fake = FakeFlatpak(FlatpakState(True, "org.libretro.RetroArch", "flathub", expected))
        lifecycle = bundled_with_fake(fake, store)
        status = lifecycle.status("retroarch")
        assert status["state"] == "installed"
        assert status["version"] == expected
        assert status["origin"] == "flatpak"

    def test_bundled_eol_source_not_installed_stays_honest(self, store: state.StateStore) -> None:
        lifecycle = eol_with_fake(FakeFlatpak(FlatpakState(False, EOL_REF)), store)
        status = lifecycle.status(EOL_ID)
        assert status["state"] == "missing"
        assert status["endOfLife"] is True
        assert status["installable"] is False
        assert "fim de vida" in status["detail"]

    def test_bundled_eol_source_installed_preserves_observed_truth(
        self, store: state.StateStore
    ) -> None:
        source = eol_registry().get(EOL_ID).preferred_source("flatpak", allow_eol=True)
        fake = FakeFlatpak(FlatpakState(True, source.ref, source.remote, source.version))
        lifecycle = eol_with_fake(fake, store)
        status = lifecycle.status(EOL_ID)
        assert status["state"] == "installed"
        assert status["version"] == source.version
        assert status["origin"] == "flatpak"
        assert status["endOfLife"] is True
        assert status["installable"] is False

    def test_flatpak_degraded_preserves_commit(self, store: state.StateStore) -> None:
        fake = FakeFlatpak(FlatpakState(True, "org.libretro.RetroArch", "flathub", "b" * 64))
        lifecycle = bundled_with_fake(fake, store)
        status = lifecycle.status("retroarch")
        assert status["state"] == "degraded"
        assert status["installed"] is False
        assert status["version"] == "b" * 64, "commit do drift precisa ser preservado"

    def test_eol_source_not_installed_is_missing_with_reason(self, store: state.StateStore) -> None:
        lifecycle = eol_with_fake(FakeFlatpak(), store)
        status = lifecycle.status(EOL_ID)
        assert status["state"] == "missing"
        assert status["endOfLife"] is True
        assert status["installable"] is False
        assert "fim de vida" in (status["detail"] or "")

    def test_no_bundled_emulator_ships_an_eol_source(self) -> None:
        """Nenhum emulador ativo pode depender de fonte descontinuada.

        É o critério de conclusão da Etapa 1 virado gate: se um manifesto voltar
        a apontar para fonte EOL, o adapter cai em ``executor=none`` e a ação
        aparece na UI como possível quando não é.
        """
        eol = [
            manifest.id
            for manifest in AdapterRegistry.bundled().list()
            if manifest.kind == "emulator" and route_for(manifest).end_of_life
        ]
        assert eol == [], f"emuladores com fonte EOL: {eol}"


class TestFailureAggregation:
    def test_status_all_isolates_failing_adapter(self, store: state.StateStore) -> None:
        fake = FakeFlatpak()
        fake.fail_status = SteamZeroError("E-COMPONENT-DEGRADED", detail="flatpak quebrado")
        registry = AdapterRegistry.bundled()
        lifecycle = ComponentLifecycle(store, registry, flatpak_factory=lambda: fake)  # type: ignore[arg-type]
        rows = lifecycle.status_all()
        by_id = {row["id"]: row for row in rows}
        assert len(rows) == len(registry.list())
        failed = by_id["retroarch"]
        assert failed["state"] == "unavailable"
        assert "flatpak quebrado" in (failed["detail"] or "")
        assert by_id["eden"]["state"] == "missing", "falha de um adapter não derruba os demais"

    def test_status_never_raises_for_adapter_failure(self, store: state.StateStore) -> None:
        fake = FakeFlatpak()
        fake.fail_status = RuntimeError("boom")
        lifecycle = bundled_with_fake(fake, store)
        status = lifecycle.status("retroarch")
        assert status["state"] == "unavailable"
        assert "boom" in (status["detail"] or "")


class TestPlanSurvivesProcess:
    """Envelope v2 persistido: plan e apply em instâncias/processos diferentes."""

    def _install(self, store: state.StateStore, payload: bytes, version: str = "1.0.0"):
        url = f"https://fixtures.invalid/demo-{version}.AppImage"
        registry = portable_registry(version, payload)
        first = ComponentLifecycle(store, registry, artifacts=FakeArtifacts({url: payload}))
        envelope = first.plan("demo-emulator", "install")
        return first, envelope

    def test_engine_plan_applies_from_a_new_instance(
        self, store: state.StateStore, tmp_path: Path
    ) -> None:
        payload = executable_payload()
        _first, envelope = self._install(store, payload)
        assert envelope.executor == "engine"
        assert envelope.delegated["transactionPlanId"]

        second = ComponentLifecycle(
            store,
            portable_registry("1.0.0", payload),
            artifacts=FakeArtifacts({"https://fixtures.invalid/demo-1.0.0.AppImage": payload}),
        )
        result = second.apply(envelope.plan_id, envelope.confirm_token)
        assert result["status"] == "ok"
        assert second.status("demo-emulator")["state"] == "installed"

    def test_flatpak_plan_applies_from_a_new_instance(self, store: state.StateStore) -> None:
        fake = FakeFlatpak()
        first = bundled_with_fake(fake, store)
        envelope = first.plan("retroarch", "install")
        assert envelope.executor == "flatpak"
        assert envelope.delegated["flatpakPlanId"]

        second = bundled_with_fake(fake, store)
        result = second.apply(envelope.plan_id, envelope.confirm_token)
        assert result["status"] == "ok"
        assert result["executor"] == "flatpak"
        assert second.status("retroarch")["state"] == "installed"

    def test_legacy_flatpak_v1_plan_still_applies(self, store: state.StateStore) -> None:
        fake = FakeFlatpak()
        lifecycle = bundled_with_fake(fake, store)
        v1 = lifecycle._flatpak().plan_install("retroarch")  # type: ignore[attr-defined]
        result = lifecycle.apply(v1.plan_id, v1.confirm_token)
        assert result["status"] == "ok"
        assert result["planVersion"] == 1

    def test_manifest_change_yields_stale_plan(self, store: state.StateStore) -> None:
        payload = executable_payload()
        _first, envelope = self._install(store, payload)
        updated = portable_registry("2.0.0", executable_payload("#!/bin/sh\necho v2\n"))
        second = ComponentLifecycle(
            store,
            updated,
            artifacts=FakeArtifacts(
                {
                    "https://fixtures.invalid/demo-2.0.0.AppImage": executable_payload(
                        "#!/bin/sh\necho v2\n"
                    )
                }
            ),
        )
        with pytest.raises(SteamZeroError) as error:
            second.apply(envelope.plan_id, envelope.confirm_token)
        assert error.value.code == "E-TX-STALE-PLAN"
        assert second.status("demo-emulator")["state"] == "missing", (
            "plano stale não pode ter efeito"
        )

    def test_corrupt_v2_plan_is_rejected_before_deserialization(
        self, store: state.StateStore, tmp_path: Path
    ) -> None:
        plan_id = "01J000000000000000000000CC"
        plan_path = paths.plan_path(plan_id)
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(
            json.dumps({"schemaVersion": 2, "planId": plan_id, "executor": "engine"}),
            encoding="utf-8",
        )
        lifecycle = bundled_with_fake(FakeFlatpak(), store)
        with pytest.raises(SteamZeroError) as error:
            lifecycle.apply(plan_id, "confirm")
        assert error.value.code == "E-STATE-INTEGRITY"

    def test_corrupt_v2_plan_without_schema_version_is_stale(
        self, store: state.StateStore, tmp_path: Path
    ) -> None:
        plan_id = "01J000000000000000000000CD"
        plan_path = paths.plan_path(plan_id)
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(json.dumps({"planId": plan_id}), encoding="utf-8")
        lifecycle = bundled_with_fake(FakeFlatpak(), store)
        with pytest.raises(SteamZeroError) as error:
            lifecycle.apply(plan_id, "confirm")
        assert error.value.code == "E-TX-STALE-PLAN"

    def test_wrong_confirm_token_is_rejected(self, store: state.StateStore) -> None:
        payload = executable_payload()
        _first, envelope = self._install(store, payload)
        second = ComponentLifecycle(
            store, portable_registry("1.0.0", payload), artifacts=FakeArtifacts({})
        )
        with pytest.raises(SteamZeroError) as error:
            second.apply(envelope.plan_id, "token-errado")
        assert error.value.code == "E-TX-CONFIRM-REQUIRED"

    def test_corrupt_v2_plan_with_wrong_delegated_key_is_rejected(
        self, store: state.StateStore
    ) -> None:
        fake = FakeFlatpak()
        lifecycle = bundled_with_fake(fake, store)
        envelope = lifecycle.plan("retroarch", "install")
        plan_path = paths.plan_path(envelope.plan_id)
        raw = json.loads(plan_path.read_text(encoding="utf-8"))
        raw["delegated"] = {"wrongKey": "x"}
        plan_path.write_text(json.dumps(raw), encoding="utf-8")
        with pytest.raises(SteamZeroError) as error:
            lifecycle.apply(envelope.plan_id, envelope.confirm_token)
        assert error.value.code == "E-STATE-INTEGRITY"

    def test_corrupt_v2_plan_with_non_object_root_is_rejected(
        self, store: state.StateStore, tmp_path: Path
    ) -> None:
        fake = FakeFlatpak()
        lifecycle = bundled_with_fake(fake, store)
        envelope = lifecycle.plan("retroarch", "install")
        plan_path = paths.plan_path(envelope.plan_id)
        plan_path.write_text("[1, 2, 3]", encoding="utf-8")
        with pytest.raises(SteamZeroError) as error:
            lifecycle.apply(envelope.plan_id, envelope.confirm_token)
        assert error.value.code == "E-STATE-INTEGRITY"

    def test_v2_plan_rejects_executor_delegated_mismatch(self, store: state.StateStore) -> None:
        payload = executable_payload()
        _first, envelope = self._install(store, payload)
        plan_path = paths.plan_path(envelope.plan_id)
        raw = json.loads(plan_path.read_text(encoding="utf-8"))
        raw["delegated"] = {"flatpakPlanId": "01J000000000000000000000CC"}
        plan_path.write_text(json.dumps(raw), encoding="utf-8")
        with pytest.raises(SteamZeroError) as error:
            _first.apply(envelope.plan_id, envelope.confirm_token)
        assert error.value.code == "E-STATE-INTEGRITY"

    def test_v2_plan_rejects_flatpak_delegated_mismatch(self, store: state.StateStore) -> None:
        fake = FakeFlatpak()
        lifecycle = bundled_with_fake(fake, store)
        envelope = lifecycle.plan("retroarch", "install")
        plan_path = paths.plan_path(envelope.plan_id)
        raw = json.loads(plan_path.read_text(encoding="utf-8"))
        raw["delegated"] = {"transactionPlanId": "01J000000000000000000000CC"}
        plan_path.write_text(json.dumps(raw), encoding="utf-8")
        with pytest.raises(SteamZeroError) as error:
            lifecycle.apply(envelope.plan_id, envelope.confirm_token)
        assert error.value.code == "E-STATE-INTEGRITY"

    def test_v2_plan_rejects_non_ulid_delegated_id(self, store: state.StateStore) -> None:
        fake = FakeFlatpak()
        lifecycle = bundled_with_fake(fake, store)
        envelope = lifecycle.plan("retroarch", "install")
        plan_path = paths.plan_path(envelope.plan_id)
        raw = json.loads(plan_path.read_text(encoding="utf-8"))
        raw["delegated"] = {"flatpakPlanId": "nao-ulid"}
        plan_path.write_text(json.dumps(raw), encoding="utf-8")
        with pytest.raises(SteamZeroError) as error:
            lifecycle.apply(envelope.plan_id, envelope.confirm_token)
        assert error.value.code == "E-STATE-INTEGRITY"

    def test_v2_plan_rejects_non_ascii_confirm_token(self, store: state.StateStore) -> None:
        fake = FakeFlatpak()
        lifecycle = bundled_with_fake(fake, store)
        envelope = lifecycle.plan("retroarch", "install")
        with pytest.raises(SteamZeroError) as error:
            lifecycle.apply(envelope.plan_id, "token-ç")
        assert error.value.code == "E-STATE-INTEGRITY"

    def test_v2_plan_rejects_expiry_without_timezone(self, store: state.StateStore) -> None:
        fake = FakeFlatpak()
        lifecycle = bundled_with_fake(fake, store)
        envelope = lifecycle.plan("retroarch", "install")
        plan_path = paths.plan_path(envelope.plan_id)
        raw = json.loads(plan_path.read_text(encoding="utf-8"))
        raw["expiresAt"] = "2026-08-01T00:00:00"
        plan_path.write_text(json.dumps(raw), encoding="utf-8")
        with pytest.raises(SteamZeroError) as error:
            lifecycle.apply(envelope.plan_id, envelope.confirm_token)
        assert error.value.code == "E-STATE-INTEGRITY"


class TestLaunchRouting:
    """launch roteia pela família da fonte, inclusive EOL instalado."""

    def test_flatpak_eol_installed_launches_through_flatpak(self, store: state.StateStore) -> None:
        source = eol_registry().get(EOL_ID).preferred_source("flatpak", allow_eol=True)
        fake = FakeFlatpak(FlatpakState(True, source.ref, source.remote, source.version))
        spawned: list[tuple[object, ...]] = []
        lifecycle = ComponentLifecycle(
            store,
            eol_registry(),
            flatpak_factory=lambda: fake,  # type: ignore[arg-type]
            which=lambda _name: "/usr/bin/flatpak",
            spawn=lambda argv: spawned.append(tuple(argv)) or 0,  # type: ignore[return-value]
        )
        result = lifecycle.launch(EOL_ID)
        assert result["status"] == "started"
        assert spawned == [("/usr/bin/flatpak", "run", "--user", source.ref)]

    def test_stop_flatpak_eol_is_not_supported(self, store: state.StateStore) -> None:
        source = eol_registry().get(EOL_ID).preferred_source("flatpak", allow_eol=True)
        fake = FakeFlatpak(FlatpakState(True, source.ref, source.remote, source.version))
        lifecycle = eol_with_fake(fake, store)
        result = lifecycle.stop(EOL_ID)
        assert result["status"] == "not-supported"
        assert "Flatpak" in result["detail"]


class TestRollbackRouting:
    def test_flatpak_rollback_uses_operation_file(self, store: state.StateStore) -> None:
        fake = FakeFlatpak()
        lifecycle = bundled_with_fake(fake, store)
        envelope = lifecycle.plan("retroarch", "install")
        applied = lifecycle.apply(envelope.plan_id, envelope.confirm_token)
        rolled = lifecycle.rollback(str(applied["operationId"]))
        assert rolled["executor"] == "flatpak"
        assert rolled["status"] == "rolled-back"

    def test_engine_rollback_uses_transaction(self, store: state.StateStore) -> None:
        payload = executable_payload()
        url = "https://fixtures.invalid/demo-1.0.0.AppImage"
        lifecycle = ComponentLifecycle(
            store, portable_registry("1.0.0", payload), artifacts=FakeArtifacts({url: payload})
        )
        envelope = lifecycle.plan("demo-emulator", "install")
        applied = lifecycle.apply(envelope.plan_id, envelope.confirm_token)
        rolled = lifecycle.rollback(str(applied["operationId"]))
        assert rolled["executor"] == "engine"
        assert rolled["status"] == "rolled-back"
        assert rolled["adapterId"] == "demo-emulator"
        assert lifecycle.status("demo-emulator")["state"] == "missing"


def store_paths_component_root(tmp_path: Path) -> Path:
    from steamzero.core import paths

    return paths.data_home() / "components"


class TestVerifyAndRepair:
    """Etapa 1: verify é leitura; repair só existe para o que já reprovou."""

    def _installed(self, store: state.StateStore, tmp_path: Path) -> ComponentLifecycle:
        payload = executable_payload()
        registry = portable_registry("1.0.0", payload)
        lifecycle = ComponentLifecycle(
            store,
            registry,
            artifacts=FakeArtifacts({"https://fixtures.invalid/demo-1.0.0.AppImage": payload}),
        )
        envelope = lifecycle.plan("demo-emulator", "install")
        lifecycle.apply(envelope.plan_id, envelope.confirm_token)
        return lifecycle

    def test_verify_is_read_only_and_confirms_intact_deployment(
        self, store: state.StateStore, tmp_path: Path
    ) -> None:
        lifecycle = self._installed(store, tmp_path)
        before = lifecycle.status("demo-emulator")
        report = lifecycle.verify("demo-emulator")
        assert report["verified"] is True
        assert report["repairable"] is False
        assert report["state"] == "installed"
        # Verificar não pode mudar nada.
        assert lifecycle.status("demo-emulator") == before

    def test_verify_refuses_to_call_a_drifted_payload_intact(
        self, store: state.StateStore, tmp_path: Path
    ) -> None:
        lifecycle = self._installed(store, tmp_path)
        root = store_paths_component_root(tmp_path)
        payload = root / "demo-emulator" / "releases" / "1.0.0" / "payload"
        payload.write_bytes(b"corrompido")

        report = lifecycle.verify("demo-emulator")
        assert report["verified"] is False
        assert report["state"] == "degraded"
        assert report["repairable"] is True
        assert report["detail"]

    def test_repair_is_refused_on_an_intact_component(
        self, store: state.StateStore, tmp_path: Path
    ) -> None:
        """Botão que rebaixa artefato íntegro e não conserta nada não existe."""
        lifecycle = self._installed(store, tmp_path)
        with pytest.raises(SteamZeroError) as error:
            lifecycle.plan("demo-emulator", "repair")
        assert error.value.code == "E-API-SCHEMA"
        assert "installed" in (error.value.detail or "")

    def test_repair_restores_a_drifted_payload_and_marks_repairing(
        self, store: state.StateStore, tmp_path: Path
    ) -> None:
        lifecycle = self._installed(store, tmp_path)
        root = store_paths_component_root(tmp_path)
        payload = root / "demo-emulator" / "releases" / "1.0.0" / "payload"
        payload.write_bytes(b"corrompido")
        assert lifecycle.status("demo-emulator")["state"] == "degraded"

        envelope = lifecycle.plan("demo-emulator", "repair")
        assert envelope.action == "repair"

        # `repairing` precisa estar persistido ANTES do efeito: uma interrupção
        # no meio tem de ser distinguível de corrupção nova.
        marked: list[str] = []
        original = store.save_component

        def spy(component: dict[str, object]) -> None:
            marked.append(str(component["state"]))
            original(component)

        store.save_component = spy  # type: ignore[method-assign]
        try:
            lifecycle.apply(envelope.plan_id, envelope.confirm_token)
        finally:
            store.save_component = original  # type: ignore[method-assign]

        assert "repairing" in marked, "reparo precisa declarar-se em curso antes de mutar"
        assert lifecycle.status("demo-emulator")["state"] == "installed"
