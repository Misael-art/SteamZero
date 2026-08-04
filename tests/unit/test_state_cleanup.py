# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Quarentena, restauração e expurgo de artefatos órfãos (A42).

A v1 movia sem reconferir. Estes testes existem para que ela não volte: cada um
força um caminho adverso que, na v1, teria terminado em dado movido sem volta ou
em sucesso falso.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from steamzero.core import fs, paths
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore
from steamzero.domain import state_audit, state_cleanup


@pytest.fixture(autouse=True)
def _hermetic_state() -> None:
    """Zera staging/backups/journal antes de cada teste.

    O plano de limpeza enxerga TODOS os órfãos, não só o que o teste criou. Sem
    isto, a sobra de um teste entra no plano do seguinte e as contagens deixam
    de significar o que a asserção diz — foi assim que a primeira execução desta
    bateria reprovou. Atua sempre sobre o XDG isolado do conftest.
    """
    fs.ensure_state_layout()
    for root in (paths.staging_dir(), paths.backups_dir(), paths.journal_dir()):
        for child in list(root.iterdir()):
            if child.is_dir():
                fs.remove_tree(child)
            else:
                fs.remove_file(child)


def _orphan_tree(name: str, *, files: dict[str, str] | None = None) -> Path:
    fs.ensure_state_layout()
    tree = paths.staging_dir() / name
    tree.mkdir(parents=True, exist_ok=True)
    for rel, content in (files or {"marker.txt": "conteúdo"}).items():
        (tree / rel).write_text(content, encoding="utf-8")
    return tree


def _plan() -> dict[str, object]:
    with StateStore() as store:
        store.migrate()
        report = state_audit.audit(store)
    return state_cleanup.plan(report)


def _quarantine(name: str = "orfa") -> tuple[str, Path]:
    """Cria um órfão e o coloca em quarentena. Devolve (cleanupId, origem)."""
    origin = _orphan_tree(name)
    plan = _plan()
    result = state_cleanup.apply(str(plan["planId"]), str(plan["confirmToken"]))
    assert result["status"] == "quarantined"
    return str(result["cleanupId"]), origin


# --- plano ----------------------------------------------------------------


def test_plan_publishes_digest_bytes_and_expiry() -> None:
    _orphan_tree("com-digest")
    plan = _plan()
    assert plan["schemaVersion"] == state_cleanup.SCHEMA_VERSION
    assert plan["kind"] == "cleanup"
    assert int(plan["totalBytes"]) > 0  # type: ignore[arg-type]
    item = next(i for i in plan["items"] if i["name"] == "com-digest")  # type: ignore[attr-defined]
    assert len(item["digest"]) == 64  # sha256 hex
    # Endereço RELATIVO: um plano com caminho absoluto foi o vetor da v1.
    assert not item["relpath"].startswith("/")
    assert item["relpath"].startswith("staging/")


def test_digest_is_deterministic_and_content_sensitive(tmp_path: Path) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    for root in (a, b):
        (root / "sub").mkdir(parents=True)
        (root / "sub" / "f.txt").write_text("igual", encoding="utf-8")
    assert state_cleanup.measure(a) == state_cleanup.measure(b)

    (b / "sub" / "f.txt").write_text("diferente", encoding="utf-8")
    assert state_cleanup.measure(a)[1] != state_cleanup.measure(b)[1]


def test_symlink_is_refused_by_measure(tmp_path: Path) -> None:
    alvo = tmp_path / "alvo"
    alvo.write_text("x", encoding="utf-8")
    link = tmp_path / "link"
    link.symlink_to(alvo)
    with pytest.raises(SteamZeroError) as err:
        state_cleanup.measure(link)
    assert err.value.code == "E-CONTENT-UNSAFE-PATH"


@pytest.mark.parametrize("name", ["../fuga", "/absoluto", "sub/../../fora", "com\\barra"])
def test_traversal_in_name_is_refused(name: str) -> None:
    with pytest.raises(SteamZeroError) as err:
        state_cleanup._source_for("staging", name)
    assert err.value.code == "E-CONTENT-UNSAFE-PATH"


# --- aplicação ------------------------------------------------------------


def test_apply_rejects_wrong_token() -> None:
    _orphan_tree("token-errado")
    plan = _plan()
    with pytest.raises(SteamZeroError) as err:
        state_cleanup.apply(str(plan["planId"]), "token-que-nao-e-o-do-plano")
    assert err.value.code == "E-TX-CONFIRM-REQUIRED"


def test_apply_rejects_expired_plan() -> None:
    _orphan_tree("expirado")
    plan = _plan()
    plan_file = paths.plan_path(str(plan["planId"]))
    payload = json.loads(plan_file.read_text(encoding="utf-8"))
    payload["expiresAt"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    plan_file.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SteamZeroError) as err:
        state_cleanup.apply(str(plan["planId"]), str(plan["confirmToken"]))
    assert err.value.code == "E-TX-STALE-PLAN"


def test_apply_rejects_when_content_changed_since_plan() -> None:
    tree = _orphan_tree("mudou")
    plan = _plan()
    (tree / "marker.txt").write_text("conteúdo alterado depois do plano", encoding="utf-8")

    with pytest.raises(SteamZeroError) as err:
        state_cleanup.apply(str(plan["planId"]), str(plan["confirmToken"]))
    assert err.value.code == "E-TX-VERIFY-FAILED"
    assert tree.exists(), "nada pode ser movido quando a verificação falha"


def test_apply_rejects_item_that_stopped_being_orphan(monkeypatch: pytest.MonkeyPatch) -> None:
    _orphan_tree("readotado")
    plan = _plan()
    # Entre plano e aplicação, uma operação voltou a referenciar o artefato.
    vazio: dict[str, set[str]] = {"staging": set(), "backup": set(), "journal": set()}
    monkeypatch.setattr(state_cleanup, "_current_orphans", lambda: vazio)
    with pytest.raises(SteamZeroError) as err:
        state_cleanup.apply(str(plan["planId"]), str(plan["confirmToken"]))
    assert err.value.code == "E-TX-STALE-PLAN"


def test_apply_isolates_quarantine_per_operation() -> None:
    first_id, _ = _quarantine("primeira")
    second_id, _ = _quarantine("segunda")
    assert first_id != second_id
    # Cada operação tem raiz própria: duas limpezas nunca disputam o destino.
    assert state_cleanup.quarantine_for_cleanup(first_id).is_dir()
    assert state_cleanup.quarantine_for_cleanup(second_id).is_dir()


def test_apply_restores_everything_when_a_move_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    _orphan_tree("um")
    _orphan_tree("dois")
    plan = _plan()
    assert int(plan["count"]) >= 2  # type: ignore[arg-type]

    real_move = fs.move_tree
    chamadas = {"n": 0}

    def falha_no_segundo(src: Path, dest: Path) -> None:
        chamadas["n"] += 1
        if chamadas["n"] == 2:
            raise OSError("disco cheio no meio da movimentação")
        real_move(src, dest)

    monkeypatch.setattr(state_cleanup.fs, "move_tree", falha_no_segundo)
    with pytest.raises(SteamZeroError):
        state_cleanup.apply(str(plan["planId"]), str(plan["confirmToken"]))

    # O que já tinha sido movido voltou: nenhum órfão fica no limbo.
    assert (paths.staging_dir() / "um").exists()
    assert (paths.staging_dir() / "dois").exists()


def test_apply_reports_failed_when_rollback_also_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    _orphan_tree("a")
    _orphan_tree("b")
    plan = _plan()

    real_move = fs.move_tree
    chamadas = {"n": 0}

    def move(src: Path, dest: Path) -> None:
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            real_move(src, dest)
            return
        raise OSError("falha tanto ao mover quanto ao devolver")

    monkeypatch.setattr(state_cleanup.fs, "move_tree", move)
    result = state_cleanup.apply(str(plan["planId"]), str(plan["confirmToken"]))

    # Sucesso otimista aqui seria a pior saída possível.
    assert result["status"] == "failed"
    assert result["stillQuarantined"], "o inventário do que ficou fora do lugar é obrigatório"


# --- status ---------------------------------------------------------------


def test_status_is_readonly_and_idempotent() -> None:
    cleanup_id, _ = _quarantine("para-status")
    primeiro = state_cleanup.status(cleanup_id)
    segundo = state_cleanup.status(cleanup_id)
    assert primeiro == segundo
    assert primeiro["status"] == "quarantined"
    assert primeiro["retentionElapsed"] is False
    assert primeiro["present"] == primeiro["count"]


# --- restauração ----------------------------------------------------------


def test_restore_round_trip_preserves_bytes() -> None:
    conteudo = {"a.txt": "primeiro", "b.txt": "segundo"}
    origem = _orphan_tree("ida-e-volta", files=conteudo)
    antes = state_cleanup.measure(origem)

    plan = _plan()
    aplicado = state_cleanup.apply(str(plan["planId"]), str(plan["confirmToken"]))
    cleanup_id = str(aplicado["cleanupId"])
    assert not origem.exists()

    restore = state_cleanup.plan_restore(cleanup_id)
    state_cleanup.apply_restore(str(restore["planId"]), str(restore["confirmToken"]))

    assert origem.exists()
    assert state_cleanup.measure(origem) == antes, "restauração precisa ser byte a byte"


def test_restore_refuses_to_overwrite_a_reoccupied_origin() -> None:
    cleanup_id, origem = _quarantine("reocupada")
    origem.mkdir(parents=True, exist_ok=True)
    (origem / "novo.txt").write_text("dado novo, de outra operação", encoding="utf-8")

    plan = state_cleanup.plan_restore(cleanup_id)
    assert plan["count"] == 0
    assert "staging/reocupada" in plan["conflicts"]
    assert (origem / "novo.txt").read_text(encoding="utf-8").startswith("dado novo")


def test_restore_token_cannot_authorize_a_purge() -> None:
    cleanup_id, _ = _quarantine("troca-de-plano")
    restore = state_cleanup.plan_restore(cleanup_id)
    with pytest.raises(SteamZeroError) as err:
        state_cleanup.apply_purge(str(restore["planId"]), str(restore["confirmToken"]))
    assert err.value.code == "E-TX-STALE-PLAN"


# --- expurgo --------------------------------------------------------------


def test_purge_is_refused_before_retention() -> None:
    cleanup_id, _ = _quarantine("cedo-demais")
    with pytest.raises(SteamZeroError) as err:
        state_cleanup.plan_purge(cleanup_id)
    assert err.value.code == "E-CONTENT-BUSY"
    assert "retenção" in (err.value.detail or "")


def _expire_retention(cleanup_id: str) -> None:
    """Envelhece o manifesto — não existe flag de bypass, e não deve existir."""
    manifest = state_cleanup.quarantine_for_cleanup(cleanup_id) / "manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    passado = datetime.now(UTC) - timedelta(days=state_cleanup.RETENTION_DAYS + 1)
    payload["quarantinedAt"] = passado.isoformat()
    payload["retentionUntil"] = (passado + timedelta(days=state_cleanup.RETENTION_DAYS)).isoformat()
    manifest.write_text(json.dumps(payload), encoding="utf-8")


def test_purge_after_retention_leaves_only_a_tombstone() -> None:
    cleanup_id, _ = _quarantine("expurgavel")
    _expire_retention(cleanup_id)

    plan = state_cleanup.plan_purge(cleanup_id)
    assert plan["irreversible"] is True
    resultado = state_cleanup.apply_purge(str(plan["planId"]), str(plan["confirmToken"]))

    assert resultado["status"] == "purged"
    assert not state_cleanup.quarantine_for_cleanup(cleanup_id).exists()

    tombstone = json.loads(state_cleanup.history_path(cleanup_id).read_text(encoding="utf-8"))
    assert tombstone["count"] >= 1
    assert len(tombstone["aggregateDigest"]) == 64
    # O tombstone prova o que houve sem reintroduzir o que foi apagado.
    texto = json.dumps(tombstone)
    assert "/home/" not in texto and "relpath" not in texto and "items" not in texto


def test_tombstone_is_private() -> None:
    cleanup_id, _ = _quarantine("privado")
    _expire_retention(cleanup_id)
    plan = state_cleanup.plan_purge(cleanup_id)
    state_cleanup.apply_purge(str(plan["planId"]), str(plan["confirmToken"]))
    modo = state_cleanup.history_path(cleanup_id).stat().st_mode & 0o777
    assert modo == 0o600


def test_status_after_purge_reports_purged_not_missing() -> None:
    cleanup_id, _ = _quarantine("depois-do-expurgo")
    _expire_retention(cleanup_id)
    plan = state_cleanup.plan_purge(cleanup_id)
    state_cleanup.apply_purge(str(plan["planId"]), str(plan["confirmToken"]))

    # Idempotência de consulta: quem pergunta depois recebe "expurgado", não um
    # erro de inexistência que o operador leria como perda de rastro.
    depois = state_cleanup.status(cleanup_id)
    assert depois["status"] == "purged"
    assert depois["cleanupId"] == cleanup_id


def test_purge_refuses_when_quarantine_content_changed() -> None:
    cleanup_id, _ = _quarantine("adulterada")
    _expire_retention(cleanup_id)
    alvo = next(state_cleanup.quarantine_for_cleanup(cleanup_id).rglob("marker.txt"))
    alvo.write_text("alguém mexeu na quarentena", encoding="utf-8")

    plan = state_cleanup.plan_purge(cleanup_id)
    with pytest.raises(SteamZeroError) as err:
        state_cleanup.apply_purge(str(plan["planId"]), str(plan["confirmToken"]))
    assert err.value.code == "E-TX-VERIFY-FAILED"
