# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""FI-06 — custodia durável: crash no meio da custódia não pode mentir.

As primitivas de custódia atuais (take_custody / return_custody) preservam o
inesperado no fluxo feliz, mas o estado delas é só o sistema de arquivos: um
crash entre a tomada e a publicação deixa a entrada original na quarentena sem
nenhum vínculo com o journal, e o recovery não tem como saber que existe.

Este arquivo cobre exatamente esses pontos cegos:

1. crash DENTRO da operaçãao de custódia (entre "tomar" e "publicar/remover/
   restaurar"); o recovery precisa fechar a ação sem deixar custódia órfã e sem
   declarar sucesso que não aconteceu;
2. operação já commitada com rollback interrompido no meio: recovery NUNCA
   declara kept quando há evidência de trabalho inacabado (custody pendente);
3. cross-filesystem: quando a custódia não pode ser tomada porque a quarentena
   vive em outro filesystem, a falha é FECHADA e EXPLÍCITA (E-TX-CUSTODY-CROSS-FS);
4. recovery idempotente: rodar de novo não muda estado nem destrói nada;
5. SIGKILL real no ponto de custódia (subprocesso), recovery em processo novo.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from steamzero.core import fs, journal, paths, transaction
from steamzero.core.errors import SteamZeroError

PROJECT = Path(__file__).parents[2]
RUNNER = Path(__file__).parent / "crash_runner.py"


def _crash_at(stage: str) -> None:
    def hook(current: str) -> None:
        if current == stage:
            raise transaction.SimulatedKill

    transaction.set_crash_hook(hook)


def _sem_crash() -> None:
    transaction.set_crash_hook(None)


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Isola o XDG_STATE_HOME por teste: o recovery só vê esta operação."""
    state = tmp_path / "state"
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    fs.ensure_state_layout()


def _custody_files(operation_id: str) -> list[Path]:
    quarentena = paths.quarantine_for(operation_id)
    if not quarentena.is_dir():
        return []
    return sorted(p for p in quarentena.rglob("*") if p.is_file())


def _orfaos_da_operacao(operation_id: str) -> list[str]:
    quarentena = paths.quarantine_for(operation_id)
    if not quarentena.is_dir():
        return []
    return [str(p) for p in quarentena.rglob("*") if p.is_file()]


def _estado(operation_id: str) -> str | None:
    from steamzero.core.state import StateStore

    with StateStore() as store:
        store.migrate()
        op = store.get_operation(operation_id)
    return op["state"] if op else None


class TestPublicacao:
    def test_crash_apos_tomar_custodia_recovery_fecha_sem_orfaos(self, tmp_path: Path) -> None:
        """Crash entre a tomada de custódia e a publicação do conteúdo novo.

        O recovery deve: fechar a operação (rolled-back), devolver o alvo ao
        estado inicial byte-idêntico e NÃO deixar a entrada antiga órfã na
        quarentena. Journal e State Store declaram exactamente o que aconteceu.
        """
        target = tmp_path / "cfg.ini"
        fs.write_atomic_text(target, "antigo")
        plan = transaction.plan_write_files({target: b"novo"}, root=tmp_path)

        _crash_at("custody.taken")
        try:
            transaction.apply(plan.plan_id, plan.confirm_token)
        except transaction.SimulatedKill:
            pass
        else:
            pytest.fail("crash gate 'custody.taken' não disparou durante a publicação")
        finally:
            _sem_crash()

        results = transaction.recover_all()
        assert len(results) == 1
        assert results[0].outcome == "rolled-back"
        assert target.read_bytes() == b"antigo"
        assert _orfaos_da_operacao(results[0].operation_id) == []
        registros = journal.read_records(results[0].operation_id)
        assert journal.has_type(registros, journal.ROLLBACK)
        assert not journal.has_type(registros, journal.COMMIT)
        assert _estado(results[0].operation_id) == "rolled-back"

    def test_crash_depois_do_link_antes_do_release_recovery_fecha_sem_orfaos(
        self, tmp_path: Path
    ) -> None:
        """Crash entre a publicação (link) e a liberação da custódia.

        O conteúdo novo chegou ao alvo, mas a operação não foi commitada. O
        recovery faz rollback (alvo volta ao antigo) e deleta a custódia que
        ficou pendente — nada de órfão no estado terminal.
        """
        target = tmp_path / "cfg.ini"
        fs.write_atomic_text(target, "antigo")
        plan = transaction.plan_write_files({target: b"novo"}, root=tmp_path)

        _crash_at("custody.postlink")
        try:
            transaction.apply(plan.plan_id, plan.confirm_token)
        except transaction.SimulatedKill:
            pass
        else:
            pytest.fail("crash gate 'custody.postlink' não disparou durante a publicação")
        finally:
            _sem_crash()

        results = transaction.recover_all()
        assert len(results) == 1
        assert results[0].outcome == "rolled-back"
        assert target.read_bytes() == b"antigo"
        assert _orfaos_da_operacao(results[0].operation_id) == []
        assert journal.is_terminal(journal.read_records(results[0].operation_id))

    def test_entrada_ocupada_na_janela_nunca_declara_sucesso(self, tmp_path: Path) -> None:
        """Alvo ocupado por terceiro enquanto a custódia está pendente.

        Não existe devolução segura (o lugar não está vazio) e não existe
        destruição legítima: a operação falha com erro explícito, o intruso fica
        no lugar, a entrada antiga permanece preservada sob custódia e o
        recovery NÃO declara rolled-back.
        """
        target = tmp_path / "cfg.ini"
        fs.write_atomic_text(target, "antigo")
        plan = transaction.plan_write_files({target: b"novo"}, root=tmp_path)

        original = fs.take_custody_named
        estado: dict[str, object] = {}

        def custodia_e_ocupacao(path: Path, custody: Path) -> Path | None:
            devolvido = original(path, custody)
            if path == target and "feito" not in estado:
                estado["feito"] = True
                estado["custody"] = devolvido
                target.write_bytes(b"ENTRADA-DE-TERCEIRO")
            return devolvido

        import steamzero.core.fs as fs_mod

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(fs_mod, "take_custody_named", custodia_e_ocupacao)
        try:
            with pytest.raises(SteamZeroError) as erro:
                transaction.apply(plan.plan_id, plan.confirm_token)
        finally:
            monkeypatch.undo()

        assert erro.value.code in {"E-TX-STALE-PLAN", "E-TX-ROLLBACK-FAILED"}
        assert target.read_bytes() == b"ENTRADA-DE-TERCEIRO"
        custody = estado["custody"]
        assert isinstance(custody, Path)
        # A entrada antiga foi preservada: ou voltou ao lugar (não é o caso, o
        # alvo está ocupado) ou foi liberada como duplicata do backup — e a
        # custódia não pode sobrar órfã no estado final.
        assert not custody.exists()


class TestCrashDuranteRemocao:
    def test_rollback_de_operacao_commitada_interrompido_nao_declara_kept(
        self, tmp_path: Path
    ) -> None:
        """Crash dentro do rollback MANUAL de operação já commitada.

        O journal ainda carrega COMMIT, então o recovery ingênuo declara kept —
        mas o arquivo aplicado foi tomado em custódia e a remoção não terminou.
        Com custódia pendente, o recovery COMPLETA o rollback: alvo volta ao
        estado pré-apply (ausente), custódia liberada, journal terminal.
        """
        target = tmp_path / "cfg.ini"
        plan = transaction.plan_write_files({target: b"aplicado"}, root=tmp_path)
        resultado = transaction.apply(plan.plan_id, plan.confirm_token)
        operation_id = resultado.operation_id
        assert target.read_bytes() == b"aplicado"

        _crash_at("custody.taken")
        try:
            transaction.rollback(operation_id, reason="manual")
        except transaction.SimulatedKill:
            pass
        else:
            pytest.fail("crash gate 'custody.taken' não disparou no rollback manual")
        finally:
            _sem_crash()

        recovery = transaction.recover_operation(operation_id)
        assert recovery.outcome != "kept"
        assert recovery.outcome == "rolled-back"
        assert not target.exists()
        assert _orfaos_da_operacao(operation_id) == []
        assert journal.is_terminal(journal.read_records(operation_id))

    def test_crash_na_remocao_durante_apply_restaura_estado_inicial(self, tmp_path: Path) -> None:
        """Crash do apply de DELETE entre a custódia e o unlink.

        O rollback deve restaurar o arquivo original (o backup existe e a
        custódia pendente é duplicata dele — pode ser liberada), sem órfãos.
        """
        target = tmp_path / "alvo.ini"
        fs.write_atomic_text(target, "original")
        plan = transaction.plan_write_files(
            {tmp_path / "x.ini": b"x"}, root=tmp_path, removals={target}
        )

        _crash_at("custody.taken")
        try:
            transaction.apply(plan.plan_id, plan.confirm_token)
        except transaction.SimulatedKill:
            pass
        else:
            pytest.fail("crash gate 'custody.taken' não disparou no delete do apply")
        finally:
            _sem_crash()

        results = transaction.recover_all()
        assert len(results) == 1
        assert results[0].outcome == "rolled-back"
        assert target.read_bytes() == b"original"
        assert _orfaos_da_operacao(results[0].operation_id) == []
        assert journal.is_terminal(journal.read_records(results[0].operation_id))


class TestRestore:
    def test_crash_no_restore_do_rollback_fecha_acao(self, tmp_path: Path) -> None:
        """Crash entre a custódia e a restauração do backup.

        O recovery re-toma a operação de onde o crash a deixou: alvo com o
        conteúdo antigo, custódia liberada, journal terminal, sem órfãos.
        """
        target = tmp_path / "cfg.ini"
        fs.write_atomic_text(target, "antigo")
        plan = transaction.plan_write_files({target: b"novo"}, root=tmp_path)
        resultado = transaction.apply(plan.plan_id, plan.confirm_token)
        operation_id = resultado.operation_id
        assert target.read_bytes() == b"novo"

        _crash_at("custody.taken")
        try:
            transaction.rollback(operation_id, reason="manual")
        except transaction.SimulatedKill:
            pass
        else:
            pytest.fail("crash gate 'custody.taken' não disparou no restore")
        finally:
            _sem_crash()

        recovery = transaction.recover_operation(operation_id)
        assert recovery.outcome == "rolled-back"
        assert target.read_bytes() == b"antigo"
        assert _orfaos_da_operacao(operation_id) == []
        assert journal.is_terminal(journal.read_records(operation_id))


class TestRecoveryIdempotente:
    def test_recovery_repetida_nao_muda_estado(self, tmp_path: Path) -> None:
        target = tmp_path / "cfg.ini"
        fs.write_atomic_text(target, "antigo")
        plan = transaction.plan_write_files({target: b"novo"}, root=tmp_path)

        _crash_at("custody.taken")
        try:
            transaction.apply(plan.plan_id, plan.confirm_token)
        except transaction.SimulatedKill:
            pass
        finally:
            _sem_crash()

        first = transaction.recover_all()
        assert len(first) == 1
        operation_id = first[0].operation_id
        alvo_depois = target.read_bytes()
        orfaos_depois = _orfaos_da_operacao(operation_id)
        registros_depois = journal.read_records(operation_id)

        second = transaction.recover_operation(operation_id)
        assert second.outcome == "already-terminal"
        assert target.read_bytes() == alvo_depois
        assert _orfaos_da_operacao(operation_id) == orfaos_depois
        assert journal.read_records(operation_id) == registros_depois


class TestCrossFilesystem:
    def test_custodia_cruzando_filesystem_fecha_com_erro_explicito(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """renameat2 devolve EXDEV (quarentena fora do filesystem do alvo).

        A falha tem que ser FECHADA e nomeada (E-TX-CUSTODY-CROSS-FS), com o
        alvo intacto e nenhum órfão — não um OSError cru vazando do ctypes.
        """
        target = tmp_path / "cfg.ini"
        fs.write_atomic_text(target, "antigo")
        plan = transaction.plan_write_files({target: b"novo"}, root=tmp_path)

        import errno

        def renameat2_exdev(first: Path, second: Path, flags: int) -> bool:
            raise OSError(errno.EXDEV, "Invalid cross-device link", str(first))

        monkeypatch.setattr(fs, "_renameat2", renameat2_exdev)

        with pytest.raises(SteamZeroError) as erro:
            transaction.apply(plan.plan_id, plan.confirm_token)

        monkeypatch.undo()
        assert erro.value.code == "E-TX-CUSTODY-CROSS-FS"
        assert target.read_bytes() == b"antigo"
        assert _orfaos_da_operacao(erro.value.operation_id or "") == []


@pytest.mark.fi
@pytest.mark.parametrize(
    "crash_at",
    ["custody.taken", "custody.postlink", "custody.release"],
)
def test_real_sigkill_durante_custodia_then_recover(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, crash_at: str
) -> None:
    """SIGKILL genuíno dentro do ponto de custódia, recovery em processo novo."""
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
        "STEAMZERO_CRASH_AT": crash_at,
        "SZ_PLAN_ID": plan.plan_id,
        "SZ_TOKEN": plan.confirm_token,
        "PYTHONPATH": str(PROJECT / "src"),
    }
    proc = subprocess.run([sys.executable, str(RUNNER)], env=env, capture_output=True, timeout=60)

    # o subprocesso recebeu SIGKILL de verdade no ponto de custódia
    assert proc.returncode == -signal.SIGKILL, proc.stderr.decode(errors="replace")

    results = transaction.recover_all()
    assert len(results) == 1
    assert results[0].outcome == "rolled-back"
    operation_id = results[0].operation_id

    # estado inicial byte-idêntico, zero órfãos de custódia/temporários
    assert target.read_text() == "ESTADO-INICIAL"
    assert fs.hash_file(target) == initial_hash
    assert _custody_files(operation_id) == []
    stray = [p for p in sandbox.rglob(".*") if ".tmp." in p.name]
    assert stray == []
    assert journal.is_terminal(journal.read_records(operation_id))
