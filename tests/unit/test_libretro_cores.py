# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Ciclo real de um core contido no arquivo Libretro pinado."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from steamzero.adapters.libretro_cores import LibretroCoreExecutor
from steamzero.adapters.lifecycle import ComponentLifecycle
from steamzero.adapters.registry import AdapterRegistry, AdapterSource, load_manifest
from steamzero.core import fs, paths, state, transaction
from steamzero.core.errors import SteamZeroError

_PREFIX = "RetroArch-Linux-x86_64/RetroArch-Linux-x86_64.AppImage.home/.config/retroarch/cores/"


class Artifacts:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def fetch(self, source: AdapterSource) -> bytes:
        return self.payload


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[state.StateStore]:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    fs.ensure_state_layout()
    opened = state.open_state()
    yield opened
    opened.close()


def _archive_reader(payload: bytes, core_id: str):
    expected = _PREFIX + f"{core_id}_libretro.so"

    def read_member(_archive: bytes, target: str) -> bytes:
        if target != expected:
            raise SteamZeroError(
                "E-SUPPLY-REMOTE-FAILED", detail="arquivo não contém exatamente o core declarado"
            )
        return payload

    return read_member


def _registry(archive: bytes, payload: bytes) -> AdapterRegistry:
    bundled = AdapterRegistry.bundled()
    retroarch = bundled.get("retroarch")
    raw = json.loads(json.dumps(bundled.get("libretro-mgba").raw))
    raw["sources"][0]["sha256"] = hashlib.sha256(archive).hexdigest()
    raw["core"]["sha256"] = hashlib.sha256(payload).hexdigest()
    return AdapterRegistry([retroarch, load_manifest(raw)])


def test_install_verify_rollback_and_refuse_unowned_overwrite(
    store: state.StateStore, tmp_path: Path
) -> None:
    payload = b"real-libretro-core"
    archive = b"pinned-archive"
    root = tmp_path / "cores"
    executor = LibretroCoreExecutor(
        store,
        _registry(archive, payload),
        Artifacts(archive),
        core_root=root,
        archive_reader=_archive_reader(payload, "mgba"),
    )

    prepared = executor.plan_install("libretro-mgba")
    assert executor.status("libretro-mgba")["state"] == "missing"
    applied = executor.apply(prepared, prepared.plan.confirm_token)
    assert executor.status("libretro-mgba")["state"] == "installed"
    assert (root / "mgba_libretro.so").read_bytes() == payload

    executor.rollback("libretro-mgba", applied.operation_id)
    assert executor.status("libretro-mgba")["state"] == "missing"

    fs.write_atomic(root / "mgba_libretro.so", b"other-owner")
    with pytest.raises(SteamZeroError, match="recusa sobrescrever"):
        executor.plan_install("libretro-mgba")


def test_refuses_archive_without_the_exact_declared_member(
    store: state.StateStore, tmp_path: Path
) -> None:
    archive = b"pinned-archive-with-other-core"
    executor = LibretroCoreExecutor(
        store,
        _registry(archive, b"not-mgba"),
        Artifacts(archive),
        core_root=tmp_path / "cores",
        archive_reader=_archive_reader(b"not-mgba", "other"),
    )

    with pytest.raises(SteamZeroError, match="não contém exatamente o core declarado"):
        executor.plan_install("libretro-mgba")


def test_component_lifecycle_keeps_plan_apply_and_rollback_for_a_core(
    store: state.StateStore, tmp_path: Path
) -> None:
    payload = b"lifecycle-core"
    archive = b"pinned-archive"
    lifecycle = ComponentLifecycle(
        store,
        _registry(archive, payload),
        artifacts=Artifacts(archive),
        libretro_core_root=tmp_path / "cores",
        libretro_archive_reader=_archive_reader(payload, "mgba"),
    )

    planned = lifecycle.plan("libretro-mgba")
    assert planned.executor == "libretro"
    applied = lifecycle.apply(planned.plan_id, planned.confirm_token)
    assert applied["executor"] == "libretro"
    assert lifecycle.verify("libretro-mgba")["verified"] is True
    rolled = lifecycle.rollback(str(applied["operationId"]))
    assert rolled["executor"] == "libretro"
    assert lifecycle.status("libretro-mgba")["state"] == "missing"


def test_component_lifecycle_refuses_a_substituted_core_delegate(
    store: state.StateStore, tmp_path: Path
) -> None:
    payload = b"delegate-core"
    archive = b"pinned-archive"
    lifecycle = ComponentLifecycle(
        store,
        _registry(archive, payload),
        artifacts=Artifacts(archive),
        libretro_core_root=tmp_path / "cores",
        libretro_archive_reader=_archive_reader(payload, "mgba"),
    )
    planned = lifecycle.plan("libretro-mgba")
    prepared = lifecycle._libretro().plan_install("libretro-mgba")  # type: ignore[attr-defined]
    alien = transaction.plan_write_files({}, root=tmp_path / "not-cores", kind="component.install")
    forged = planned.to_dict()
    forged["schemaVersion"] = 2
    forged["confirmToken"] = prepared.plan.confirm_token
    forged["delegated"] = {"transactionPlanId": alien.plan_id}
    fs.write_atomic_text(paths.plan_path(planned.plan_id), json.dumps(forged))

    with pytest.raises(SteamZeroError, match="plano não pertence a um core Libretro"):
        lifecycle.apply(planned.plan_id, prepared.plan.confirm_token)


def test_our_own_core_at_the_previous_pin_can_be_updated(tmp_path, monkeypatch) -> None:
    """Atualizar um core nosso não pode ser confundido com sobrescrever alheio.

    `_owned_target` perguntava "o arquivo instalado bate com o digest NOVO?".
    Um core nosso, no pin anterior, responde NÃO — exatamente como um core que
    outra ferramenta instalou. As duas situações ficavam indistinguíveis, e a
    recusa `E-CONTENT-INCOMPLETE` impedia qualquer update de core.

    A pergunta certa é outra: o arquivo bate com o digest que NÓS registramos ao
    instalar? Isso separa "nosso, desatualizado" de "de outra pessoa".
    """
    import json as _json

    from steamzero.adapters.libretro_cores import LibretroCoreExecutor

    root = tmp_path / "cores"
    (root / ".steamzero").mkdir(parents=True)
    antigo = b"core-antigo"
    alvo = root / "demo_libretro.so"
    alvo.write_bytes(antigo)
    digest_antigo = hashlib.sha256(antigo).hexdigest()
    (root / ".steamzero" / "libretro-demo.json").write_text(
        _json.dumps({"schemaVersion": 1, "coreSha256": digest_antigo}), encoding="utf-8"
    )

    owned = LibretroCoreExecutor._target_is_ours(alvo, root / ".steamzero" / "libretro-demo.json")

    assert owned is True, (
        "um core nosso no pin anterior foi tratado como arquivo de terceiro; "
        "nenhum update de core seria possível"
    )


def test_a_core_from_someone_else_is_still_refused(tmp_path) -> None:
    """A protecao que o guard existe para dar continua de pe.

    Afrouxar a pergunta do ownership nao pode virar licenca para sobrescrever o
    core de outra ferramenta. Tres formas de "nao e nosso" precisam continuar
    reprovando: sem metadado, metadado que nao corresponde ao arquivo, e
    symlink no lugar do alvo.
    """
    import json as _json

    from steamzero.adapters.libretro_cores import LibretroCoreExecutor

    root = tmp_path / "cores"
    meta_dir = root / ".steamzero"
    meta_dir.mkdir(parents=True)
    alvo = root / "demo_libretro.so"
    alvo.write_bytes(b"core-de-outra-ferramenta")
    meta = meta_dir / "libretro-demo.json"

    assert LibretroCoreExecutor._target_is_ours(alvo, meta) is False, (
        "core sem metadado nosso foi tratado como nosso"
    )

    meta.write_text(_json.dumps({"schemaVersion": 1, "coreSha256": "0" * 64}), encoding="utf-8")
    assert LibretroCoreExecutor._target_is_ours(alvo, meta) is False, (
        "arquivo que nao corresponde ao digest registrado foi tratado como nosso"
    )

    link = root / "link_libretro.so"
    link.symlink_to(alvo)
    assert LibretroCoreExecutor._target_is_ours(link, meta) is False, (
        "symlink no lugar do alvo foi tratado como nosso"
    )
