# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Testes do gerador da matriz de capacidades (tools/capability_matrix.py).

O valor da matriz é ser derivada do código: se o documento puder envelhecer sem
ninguém notar, ela vira mais um catálogo que afirma feature inexistente — que foi
exatamente o defeito que a motivou. Por isso a divergência é verificada aqui, e
não só no `make`: o CI roda a suíte nos três Pythons.
"""

from __future__ import annotations

import capability_matrix


def test_committed_matrix_matches_the_code() -> None:
    assert capability_matrix.OUTPUT.is_file(), "matriz ausente; rode --write"
    committed = capability_matrix.OUTPUT.read_text(encoding="utf-8")
    assert committed == capability_matrix.render(), (
        "a matriz de capacidades divergiu do código; "
        "rode `make update-capability-matrix` e revise o diff"
    )


def test_render_is_deterministic() -> None:
    # Sem ordenação estável, o gate viraria ruído e seria desligado.
    assert capability_matrix.render() == capability_matrix.render()


def test_matrix_does_not_read_the_host() -> None:
    """A matriz precisa ser idêntica em qualquer máquina para servir de gate.

    O teste não prova ausência de I/O; prova que o resultado não muda quando os
    homes XDG mudam — que é a forma como estado de host vazaria para cá.
    """
    import os

    rendered = capability_matrix.render()
    original = os.environ.get("XDG_STATE_HOME")
    os.environ["XDG_STATE_HOME"] = "/nao/existe/em/lugar/nenhum"
    try:
        assert capability_matrix.render() == rendered
    finally:
        if original is None:
            os.environ.pop("XDG_STATE_HOME", None)
        else:
            os.environ["XDG_STATE_HOME"] = original


def test_core_providers_are_derived_not_asserted() -> None:
    """Se algum dia um adapter entregar core, a matriz precisa refletir sozinha."""
    from steamzero.adapters.registry import AdapterRegistry

    manifests = AdapterRegistry.bundled().list()
    assert capability_matrix._core_providers(manifests) == {
        manifest.id for manifest in manifests if manifest.kind == "core"
    }


def test_every_active_emulator_declares_the_mandatory_lifecycle() -> None:
    """O contrato só vale se faltar capacidade reprovar, não só aparecer na tabela."""
    from steamzero.adapters.registry import AdapterRegistry

    registry = AdapterRegistry.bundled()
    routes = capability_matrix.lifecycle.routes_for(registry)
    _table, violations, active, _config = capability_matrix._action_matrix(registry, routes)
    assert violations == [], f"emulador ativo com ciclo incompleto: {violations}"
    assert active == 15, "o denominador mudou; revise a matriz antes de seguir"


def test_the_gate_refuses_an_active_emulator_missing_a_mandatory_capability() -> None:
    """Regressão: remover `repair` de um manifesto precisa reprovar o gate.

    Sem esta prova, a tabela publicaria a lacuna e o CI seguiria verde — que é
    exatamente o padrão de "documento bonito, gate inerte" que a matriz existe
    para impedir.
    """
    from steamzero.adapters.registry import AdapterRegistry, load_manifest

    registry = AdapterRegistry.bundled()
    quebrado = []
    for manifest in registry.list():
        raw = dict(manifest.raw)
        if manifest.id == "dolphin":
            raw["capabilities"] = [c for c in raw["capabilities"] if c != "repair"]
        quebrado.append(load_manifest(raw))

    mutilado = AdapterRegistry(quebrado)
    routes = capability_matrix.lifecycle.routes_for(mutilado)
    _table, violations, _active, _config = capability_matrix._action_matrix(mutilado, routes)

    assert any("dolphin" in item and "repair" in item for item in violations)
