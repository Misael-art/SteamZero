# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Conformidade de lifecycle, parametrizada pelo registry real (Etapa 1).

O ponto desta suíte é **não** ter uma lista de emuladores. Ela enumera o
registry empacotado, e um manifesto `kind=emulator` novo entra automaticamente
em todos os cenários abaixo. Um adapter adicionado sem ciclo completo reprova
aqui antes de chegar à UI — que é o oposto do que a auditoria de 2026-08-03
encontrou, quando dezesseis emuladores eram oferecidos e dois funcionavam.

Por que manifesto derivado, e não o real: as fontes reais pinam SHA-256 de
binários de dezenas de MB, e nenhum byte sintético produz aquele hash. Cada
cenário deriva do manifesto real o que define o CONTRATO — id, kind,
capacidades, família da fonte — e substitui apenas a coordenada do artefato por
uma sintética. O que se prova é que o ciclo declarado por aquele adapter se
comporta; baixar o binário verdadeiro é papel da certificação em VM.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest

from steamzero.adapters.flatpak import FlatpakState
from steamzero.adapters.lifecycle import ComponentLifecycle
from steamzero.adapters.registry import AdapterRegistry, AdapterSource, load_manifest
from steamzero.core import state
from steamzero.core.errors import SteamZeroError

PAYLOAD = b"#!/bin/sh\necho conformidade\n"
PAYLOAD_SHA = hashlib.sha256(PAYLOAD).hexdigest()
UPDATED = b"#!/bin/sh\necho conformidade 2\n"
UPDATED_SHA = hashlib.sha256(UPDATED).hexdigest()
COMMIT = "a" * 64
URL = "https://fixtures.invalid/conformidade.AppImage"


def emulator_ids() -> list[str]:
    """Todos os `kind=emulator` do registry. Sem lista fixa, de propósito."""
    return [m.id for m in AdapterRegistry.bundled().list() if m.kind == "emulator"]


def derived(
    adapter_id: str,
    *,
    version: str = "1.0.0",
    sha: str = PAYLOAD_SHA,
    commit: str = COMMIT,
) -> dict[str, Any]:
    """Manifesto do adapter real com a coordenada do artefato trocada."""
    manifest = AdapterRegistry.bundled().get(adapter_id)
    raw = dict(manifest.raw)
    source = dict(raw["sources"][0])
    if source["type"] == "flatpak":
        source["version"] = commit
    else:
        source["version"] = version
        source["url"] = URL
        source["sha256"] = sha
    raw["sources"] = [source]
    raw.pop("requiresKeys", None)
    raw.pop("requiresFirmware", None)
    return raw


class FakeArtifacts:
    def __init__(self, artifacts: dict[str, bytes]) -> None:
        self.artifacts = artifacts

    def fetch(self, source: AdapterSource) -> bytes:
        assert source.url is not None
        return self.artifacts[source.url]


class FakeFlatpak:
    def __init__(self, ref: str, initial: FlatpakState | None = None) -> None:
        self.ref = ref
        self.current = initial or FlatpakState(False, ref)
        self.calls: list[tuple[Any, ...]] = []

    def status(self, ref: str) -> FlatpakState:
        return self.current

    def resolve(self, remote: str, ref: str, commit: str) -> str:
        return commit

    def install(self, remote: str, ref: str) -> None:
        self.calls.append(("install", ref))
        self.current = FlatpakState(True, ref, remote, COMMIT)

    def deploy(self, ref: str, commit: str) -> None:
        self.calls.append(("deploy", ref, commit))
        self.current = FlatpakState(True, ref, self.current.origin or "flathub", commit)

    def uninstall(self, ref: str) -> None:
        self.calls.append(("uninstall", ref))
        self.current = FlatpakState(False, ref)

    def smoke(self, ref: str, arguments: Sequence[str]) -> None:
        self.calls.append(("smoke", ref))


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[state.StateStore]:
    # A raiz de componentes do engine vem de XDG_DATA_HOME. Sem isolar por
    # teste, o deployment de um caso parametrizado vaza para o seguinte e o
    # cenário "recusado sem efeito" vê `installed` de um install anterior —
    # falso verde ao contrário, que esconderia uma recusa que não recusa.
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    opened = state.StateStore(tmp_path / "state.db")
    opened.migrate()
    try:
        yield opened
    finally:
        opened.close()


def _lifecycle(
    store: state.StateStore, raw: dict[str, Any], *, artifacts: dict[str, bytes] | None = None
) -> tuple[ComponentLifecycle, FakeFlatpak | None]:
    registry = AdapterRegistry([load_manifest(raw)])
    source = raw["sources"][0]
    if source["type"] == "flatpak":
        fake = FakeFlatpak(source["ref"])
        return ComponentLifecycle(store, registry, flatpak_factory=lambda: fake), fake
    port = FakeArtifacts(artifacts or {URL: PAYLOAD})
    return ComponentLifecycle(store, registry, artifacts=port), None


def _install(lifecycle: ComponentLifecycle, adapter_id: str) -> None:
    envelope = lifecycle.plan(adapter_id, "install")
    lifecycle.apply(envelope.plan_id, envelope.confirm_token)


@pytest.mark.parametrize("adapter_id", emulator_ids())
class TestEmulatorLifecycleConformance:
    """Um manifesto novo entra aqui sozinho; nenhuma lista para esquecer."""

    def test_clean_install_reaches_installed(
        self, adapter_id: str, store: state.StateStore
    ) -> None:
        lifecycle, _ = _lifecycle(store, derived(adapter_id))
        assert lifecycle.status(adapter_id)["state"] == "missing"
        _install(lifecycle, adapter_id)
        assert lifecycle.status(adapter_id)["state"] == "installed"

    def test_second_install_is_idempotent(self, adapter_id: str, store: state.StateStore) -> None:
        """Reinstalar o mesmo pino não pode reescrever o deployment."""
        lifecycle, _ = _lifecycle(store, derived(adapter_id))
        _install(lifecycle, adapter_id)
        again = lifecycle.plan(adapter_id, "install")
        assert again.action == "noop"
        assert lifecycle.status(adapter_id)["state"] == "installed"

    def test_verify_confirms_an_intact_deployment(
        self, adapter_id: str, store: state.StateStore
    ) -> None:
        lifecycle, _ = _lifecycle(store, derived(adapter_id))
        _install(lifecycle, adapter_id)
        report = lifecycle.verify(adapter_id)
        assert report["verified"] is True
        assert report["repairable"] is False

    def test_uninstall_is_planned_and_declared(
        self, adapter_id: str, store: state.StateStore
    ) -> None:
        """Os dois executores precisam oferecer o MESMO contrato público."""
        raw = derived(adapter_id)
        lifecycle, _ = _lifecycle(store, raw)
        _install(lifecycle, adapter_id)
        envelope = lifecycle.plan(adapter_id, "uninstall")
        assert envelope.action == "uninstall"

    def test_expired_plan_is_refused(self, adapter_id: str, store: state.StateStore) -> None:
        from dataclasses import replace as dataclass_replace

        lifecycle, _ = _lifecycle(store, derived(adapter_id))
        envelope = lifecycle.plan(adapter_id, "install")
        expirado = dataclass_replace(envelope, expires_at="2020-01-01T00:00:00+00:00")
        lifecycle._save_plan(expirado)  # noqa: SLF001 - fixar o instante sem esperar
        with pytest.raises(SteamZeroError) as error:
            lifecycle.apply(envelope.plan_id, envelope.confirm_token)
        # O código é E-TX-CONFIRM-REQUIRED, não STALE-PLAN: o que expira é a
        # AUTORIZAÇÃO do operador, não a descrição do mundo feita pelo plano.
        # A distinção importa para a UI — um caso pede reconfirmar, o outro
        # pede replanejar.
        assert error.value.code == "E-TX-CONFIRM-REQUIRED"
        assert lifecycle.status(adapter_id)["state"] == "missing"

    def test_wrong_token_is_refused_without_effect(
        self, adapter_id: str, store: state.StateStore
    ) -> None:
        lifecycle, _ = _lifecycle(store, derived(adapter_id))
        envelope = lifecycle.plan(adapter_id, "install")
        with pytest.raises(SteamZeroError):
            lifecycle.apply(envelope.plan_id, "token-errado")
        assert lifecycle.status(adapter_id)["state"] == "missing"

    def test_source_changed_after_the_plan_is_refused(
        self, adapter_id: str, store: state.StateStore
    ) -> None:
        """Fingerprint da fonte é recalculado contra o manifesto ATUAL."""
        raw = derived(adapter_id)
        lifecycle, _ = _lifecycle(store, raw)
        envelope = lifecycle.plan(adapter_id, "install")

        # Flatpak fixa commit, portátil fixa versão+sha256: mudar SÓ um dos
        # dois deixaria metade dos adapters com manifesto idêntico e o teste
        # passaria sem exercitar nada.
        mudado = derived(adapter_id, version="9.9.9", sha=UPDATED_SHA, commit="b" * 64)
        lifecycle._registry = AdapterRegistry([load_manifest(mudado)])  # noqa: SLF001

        with pytest.raises(SteamZeroError) as error:
            lifecycle.apply(envelope.plan_id, envelope.confirm_token)
        assert error.value.code == "E-TX-STALE-PLAN"
