# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""FI-06 — P1: a janela entre o rename da custódia e o registro ``custody.taken``.

A sequência da custódia durável é

    custody.intent (fsync) -> tomar a entrada (rename atômico)
    custody.taken  (fsync) -> verificar -> publicar/remover/restaurar
    custody.released(fsync) -> liberar a entrada sob custódia

O crash gate ``custody.taken`` é TARDIO: ele dispara DEPOIS de
``journal.custody_taken`` já estar persistido. Existe uma janela entre a
execução do rename (o alvo já saiu do lugar e está na quarentena) e o registro
da tomada no journal. Um processo morto nessa janela deixa:

- ``custody.intent`` SEM ``custody.taken`` correspondente, mas COM arquivo de
  custódia existente no caminho determinístico ``custody.<custodyId>`` (o
  ``custodyId`` é por TENTATIVA: ``custody.<actionId>.<seq>``, de modo que
  apply e rollback da mesma ação nunca colidem);

- o alvo ausente e o conteúdo SÓ dentro da quarentena;

- o recovery tentando re-tomar o alvo para o MESMO caminho determinístico já
  ocupado => ``FileExistsError`` aberto, alvo permanece ausente e o conteúdo
  fica preso na quarentena (perda de dado silenciosa).

Os testes abaixo reproduzem essa janela de forma determinística: o rename real
executa e, logo em seguida, a execução é interrompida (``SimulatedKill``) antes
de ``take_custody_named`` retornar ao chamador — o mesmo efeito de um SIGKILL
entre o syscall e o retorno. O último teste mata um SUBPROCESSO com SIGKILL
genuíno dentro dessa janela (gate ``custody.after-rename``) e recupera em
processo novo.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from steamzero.core import fs, journal, paths, transaction

PROJECT = Path(__file__).parents[2]
RUNNER = Path(__file__).parent / "crash_runner.py"


def _crash_apos_rename_na_primeira_tomada(monkeypatch: pytest.MonkeyPatch) -> None:
    """O rename real da custódia executa; a execução morre antes do retorno.

    É exatamente a janela do P1: ``take_custody_named`` fez o rename (o alvo
    está na quarentena), mas ``custody.taken`` NUNCA vai ser registrado porque
    o processo morreu no meio da função. Chamadas seguintes se comportam como o
    original, para o recovery poder rodar.
    """

    real = fs._rename_noreplace
    disparos = {"n": 0}

    def rename_e_crash(src: Path, dst: Path) -> bool:
        resultado = real(src, dst)
        if disparos["n"] == 0:
            disparos["n"] += 1
            raise transaction.SimulatedKill
        disparos["n"] += 1
        return resultado

    monkeypatch.setattr(fs, "_rename_noreplace", rename_e_crash)


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Isola o XDG_STATE_HOME por teste: o recovery só vê esta operação."""
    state = tmp_path / "state"
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    fs.ensure_state_layout()


def _orfaos_da_operacao(operation_id: str) -> list[str]:
    quarentena = paths.quarantine_for(operation_id)
    if not quarentena.is_dir():
        return []
    return [str(p) for p in quarentena.rglob("*") if p.is_file()]


def _custody_files(operation_id: str) -> list[Path]:
    quarentena = paths.quarantine_for(operation_id)
    if not quarentena.is_dir():
        return []
    return sorted(p for p in quarentena.rglob("*") if p.is_file())


def _intents_nao_fechados(operation_id: str) -> list[str]:
    """``custody.intent`` de janela interrompida que o recovery NÃO fechou.

    Um intent é de janela interrompida quando NÃO há ``custody.taken`` depois
    dele (o rename executou, a tomada nunca foi registrada). Fechar de verdade
    é registrar, DEPOIS do intent, um ``custody.released`` com ``reason`` em
    ``done``/``returned`` — a custódia física foi liberada ou devolvida de
    forma EXPLÍCITA.

    Um ``released(absent)`` ou um released de um ciclo ANTERIOR com o mesmo
    caminho determinístico NÃO fecha a janela: a colisão de ``actionId`` pode
    fazer o recovery "passar" por acidente, sem nunca reconhecer o rename que
    aconteceu — este é o P1. Como cada tentativa tem seu próprio
    ``custodyId`` (``custody.<actionId>.<seq>``), a correlação abaixo usa
    actionId+caminho juntos, nunca actionId sozinho.
    """
    registros = journal.read_records(operation_id)
    nao_fechados: list[str] = []
    for i, intent in enumerate(registros):
        if intent.get("type") != "custody.intent":
            continue
        chave = (intent.get("actionId"), intent.get("custody"))
        tomada_depois = any(
            r.get("type") == "custody.taken" and (r.get("actionId"), r.get("custody")) == chave
            for r in registros[i + 1 :]
        )
        if tomada_depois:
            continue
        fechado_depois = any(
            r.get("type") == "custody.released"
            and (r.get("actionId"), r.get("custody")) == chave
            and r.get("reason") in {"done", "returned"}
            for r in registros[i + 1 :]
        )
        if not fechado_depois:
            nao_fechados.append(str(intent.get("custody")))
    return nao_fechados


class TestJanelaRenameTakenDaPublicacao:
    def test_crash_apos_rename_na_publicacao_recovery_restaura_e_libera(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Atualização de arquivo existente: morte entre rename e custody.taken.

        O alvo "antigo" já saiu do lugar (renomeado para a quarentena) e não há
        ``custody.taken``. O recovery precisa: devolver o alvo ao estado
        inicial, liberar a custódia (identidade aceita), journal terminal e
        ZERO órfãos. Hoje o re-take esbarra no caminho determinístico ocupado
        e estoura ``FileExistsError`` — o alvo fica ausente de verdade.
        """
        target = tmp_path / "cfg.ini"
        fs.write_atomic_text(target, "antigo")
        plan = transaction.plan_write_files({target: b"novo"}, root=tmp_path)
        initial_hash = fs.hash_file(target)

        _crash_apos_rename_na_primeira_tomada(monkeypatch)
        with pytest.raises(transaction.SimulatedKill):
            transaction.apply(plan.plan_id, plan.confirm_token)

        results = transaction.recover_all()
        assert len(results) == 1
        operation_id = results[0].operation_id
        assert results[0].outcome == "rolled-back"
        assert target.read_bytes() == b"antigo"
        assert fs.hash_file(target) == initial_hash
        assert _orfaos_da_operacao(operation_id) == []
        assert journal.is_terminal(journal.read_records(operation_id))


class TestJanelaRenameTakenDoDeleteCommitado:
    def test_crash_apos_rename_no_delete_do_rollback_commitado(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Rollback/delete de operação commitada: morte entre rename e taken.

        A operação criou o arquivo e foi commitada; o rollback manual tomou o
        arquivo em custódia e morreu antes de registrar a tomada. O recovery
        precisa COMPLETAR o rollback: alvo ausente, custódia liberada, sem
        órfãos, journal terminal. Hoje o re-take do delete re-toma o MESMO
        caminho determinístico já ocupado e estoura ``FileExistsError``.
        """
        target = tmp_path / "criado.ini"
        plan = transaction.plan_write_files({target: b"conteudo"}, root=tmp_path)
        resultado = transaction.apply(plan.plan_id, plan.confirm_token)
        assert target.read_bytes() == b"conteudo"

        _crash_apos_rename_na_primeira_tomada(monkeypatch)
        with pytest.raises(transaction.SimulatedKill):
            transaction.rollback(resultado.operation_id)

        recovery = transaction.recover_operation(resultado.operation_id)
        assert recovery.outcome == "rolled-back"
        assert not target.exists()
        assert _orfaos_da_operacao(resultado.operation_id) == []
        assert journal.is_terminal(journal.read_records(resultado.operation_id))


class TestJanelaRenameTakenDoRestoreCommitado:
    def test_crash_apos_rename_no_restore_do_rollback_commitado(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Rollback/restore de operação commitada: morte entre rename e taken.

        A operação substituiu o conteúdo (commitada); o rollback manual tomou
        o valor aplicado em custódia e morreu antes do ``custody.taken``. O
        recovery precisa terminar o restore: alvo com o conteúdo antigo,
        custódia liberada, sem órfãos, terminal. Hoje o restore re-toma o
        caminho determinístico já ocupado e estoura ``FileExistsError``.
        """
        target = tmp_path / "cfg.ini"
        fs.write_atomic_text(target, "antigo")
        plan = transaction.plan_write_files({target: b"novo"}, root=tmp_path)
        resultado = transaction.apply(plan.plan_id, plan.confirm_token)
        assert target.read_bytes() == b"novo"

        _crash_apos_rename_na_primeira_tomada(monkeypatch)
        with pytest.raises(transaction.SimulatedKill):
            transaction.rollback(resultado.operation_id)

        recovery = transaction.recover_operation(resultado.operation_id)
        assert recovery.outcome == "rolled-back"
        assert target.read_bytes() == b"antigo"
        assert _orfaos_da_operacao(resultado.operation_id) == []
        assert _intents_nao_fechados(resultado.operation_id) == []
        assert journal.is_terminal(journal.read_records(resultado.operation_id))


class TestJanelaRenameTakenDoSymlink:
    def test_crash_apos_rename_na_substituicao_de_symlink(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Substituição atômica de symlink: morte entre rename e taken.

        O link legítimo antigo foi tomado em custódia (renomeado para a
        quarentena) e o processo morreu antes do ``custody.taken``. O recovery
        precisa restaurar o link antigo e liberar a custódia — hoje o restore
        do symlink tenta re-tomar o alvo para o caminho determinístico já
        ocupado e estoura ``FileExistsError``.
        """
        origem1 = tmp_path / "origem1.bin"
        origem2 = tmp_path / "origem2.bin"
        origem1.write_bytes(b"ROM-1")
        origem2.write_bytes(b"ROM-2")
        alvo = tmp_path / "icone.png"
        plan1 = transaction.plan_symlink_files({origem1: alvo}, root=tmp_path)
        transaction.apply(plan1.plan_id, plan1.confirm_token)
        assert alvo.is_symlink() and alvo.resolve() == origem1.resolve()

        plan2 = transaction.plan_symlink_files(
            {origem2: alvo}, root=tmp_path, replace_existing=True
        )
        _crash_apos_rename_na_primeira_tomada(monkeypatch)
        with pytest.raises(transaction.SimulatedKill):
            transaction.apply(plan2.plan_id, plan2.confirm_token)

        results = transaction.recover_all()
        rollback = [r for r in results if r.outcome == "rolled-back"]
        assert len(rollback) == 1, results
        operation_id = rollback[0].operation_id
        assert alvo.is_symlink() and alvo.resolve() == origem1.resolve()
        assert _orfaos_da_operacao(operation_id) == []
        assert journal.is_terminal(journal.read_records(operation_id))


class TestJanelaRenameTakenDoMove:
    def test_crash_apos_rename_no_move_do_rollback_commitado(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Rollback de move commitado: morte entre rename e taken.

        O arquivo movido (no destino) foi tomado em custódia e o processo
        morreu antes do ``custody.taken``. O recovery precisa terminar o
        move-restore: origem com o conteúdo original, destino ausente e a
        entrada movida LIBERADA — hoje o ``_restore_move`` re-toma o caminho
        determinístico já ocupado e estoura ``FileExistsError``.
        """
        origem = tmp_path / "origem.bin"
        origem.write_bytes(b"dados")
        destino = tmp_path / "destino.bin"
        plan = transaction.plan_move_files({origem: destino}, root=tmp_path)
        resultado = transaction.apply(plan.plan_id, plan.confirm_token)
        assert destino.read_bytes() == b"dados"
        assert not origem.exists()

        _crash_apos_rename_na_primeira_tomada(monkeypatch)
        with pytest.raises(transaction.SimulatedKill):
            transaction.rollback(resultado.operation_id)

        recovery = transaction.recover_operation(resultado.operation_id)
        assert recovery.outcome == "rolled-back"
        assert origem.read_bytes() == b"dados"
        assert not destino.exists()
        assert _orfaos_da_operacao(resultado.operation_id) == []
        assert _intents_nao_fechados(resultado.operation_id) == []
        assert journal.is_terminal(journal.read_records(resultado.operation_id))


class TestJanelaRenameTakenComAlvoReocupado:
    def test_alvo_reocupado_apos_rename_falha_fechada_e_libera_custodia(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Alvo reocupado por terceiro na janela: falhar fechado, sem órfão.

        A custódia existe (conteúdo original "antigo" na quarentena) e o alvo
        foi reocupado pelo intruso. Como a identidade da custódia é duplicata
        byte-a-byte do backup (o undo a reconhece), o recovery a libera — o
        estado final NÃO pode deixar custódia órfã — e o rollback falha fechado
        recusando sobrescrever o intruso (FI-05, janela única restante).
        """
        target = tmp_path / "cfg.ini"
        fs.write_atomic_text(target, "antigo")
        plan = transaction.plan_write_files({target: b"novo"}, root=tmp_path)
        _INTRUSO = b"ENTRADA-DE-TERCEIRO"

        _crash_apos_rename_na_primeira_tomada(monkeypatch)
        with pytest.raises(transaction.SimulatedKill):
            transaction.apply(plan.plan_id, plan.confirm_token)
        target.write_bytes(_INTRUSO)

        recovery = transaction.recover_all()
        assert len(recovery) == 1
        operation_id = recovery[0].operation_id
        assert recovery[0].outcome == "rollback-failed"
        assert target.read_bytes() == _INTRUSO
        assert _orfaos_da_operacao(operation_id) == []
        assert _custody_files(operation_id) == []
        registros = journal.read_records(operation_id)
        assert not journal.is_terminal(registros)


@pytest.mark.fi
def test_real_sigkill_apos_rename_then_recover(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """SIGKILL genuíno dentro da janela rename->taken, recovery em processo novo.

    O subprocesso roda o apply com ``STEAMZERO_CRASH_AT=custody.after-rename``
    (gate disparado DEPOIS do rename da custódia, antes do ``custody.taken``) e
    é morto por SIGKILL de verdade. O recovery em processo novo precisa fechar a
    operação: alvo no estado inicial, zero órfãos, zero temporários.
    """
    state = tmp_path / "state"
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    fs.ensure_state_layout()

    target = sandbox / "cfg.ini"
    fs.write_atomic_text(target, "ESTADO-INICIAL")
    initial_hash = fs.hash_file(target)

    plan = transaction.plan_write_files({target: b"NOVO"}, root=sandbox)
    env = {
        **os.environ,
        "XDG_STATE_HOME": str(state),
        "STEAMZERO_CRASH_AT": "custody.after-rename",
        "SZ_PLAN_ID": plan.plan_id,
        "SZ_TOKEN": plan.confirm_token,
        "PYTHONPATH": str(PROJECT / "src"),
    }
    proc = subprocess.run([sys.executable, str(RUNNER)], env=env, capture_output=True, timeout=60)

    assert proc.returncode == -signal.SIGKILL, proc.stderr.decode(errors="replace")

    results = transaction.recover_all()
    assert len(results) == 1
    assert results[0].outcome == "rolled-back"
    operation_id = results[0].operation_id

    assert target.read_text() == "ESTADO-INICIAL"
    assert fs.hash_file(target) == initial_hash
    assert _custody_files(operation_id) == []
    stray = [p for p in sandbox.rglob(".*") if ".tmp." in p.name]
    assert stray == []
    assert journal.is_terminal(journal.read_records(operation_id))
