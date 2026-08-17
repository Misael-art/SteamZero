# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""FI-06 (symlink/move) — publicação de links e movimentos também passa pela custódia.

O P1 da G45 atingiu exatamente os dois caminhos que ainda publicavam com
``os.replace``: a criação de symlink e o movimento de arquivo. ``os.replace``
sobrescreve o que estiver no destino, e a conferência anterior nunca fecha a
janela — o intruso que chega depois do guard é destruído.

Estes testes injetam o intruso NO ÚLTIMO instante (dentro da primitiva de
publicação) e exigem falha fechada com o intruso preservado byte a byte, ou —
no caso de crash no meio — recovery que restaura o estado inicial sem órfãos.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from steamzero.core import fs, journal, paths, transaction
from steamzero.core.errors import SteamZeroError

_INTRUSO = b"conteudo-que-nao-e-nosso\n"


def _orfaos_da_operacao(operation_id: str) -> list[str]:
    quarentena = paths.quarantine_for(operation_id)
    if not quarentena.is_dir():
        return []
    return [str(p) for p in quarentena.rglob("*") if p.is_file()]


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Isola o XDG_STATE_HOME por teste: o recovery só vê esta operação."""
    state = tmp_path / "state"
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    fs.ensure_state_layout()


class TestSymlink:
    def test_intruso_no_vazio_do_alvo_sobrevive_ao_link(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Arquivo alheio aparece no destino vazio no último instante.

        O symlink não pode substituir o intruso: a operação falha fechada e o
        intruso permanece intacto no lugar.
        """
        origem = tmp_path / "origem.bin"
        origem.write_bytes(b"ROM")
        alvo = tmp_path / "link.bin"
        plan = transaction.plan_symlink_files({origem: alvo}, root=tmp_path)

        original = fs.take_custody_named
        disparado = {"ok": False}

        def custodia_e_intruso(path: Path, custody: Path) -> Path | None:
            devolvido = original(path, custody)
            if path == alvo and not disparado["ok"]:
                disparado["ok"] = True
                if devolvido is None:
                    alvo.write_bytes(_INTRUSO)
            return devolvido

        monkeypatch.setattr(fs, "take_custody_named", custodia_e_intruso)

        with pytest.raises(SteamZeroError) as erro:
            transaction.apply(plan.plan_id, plan.confirm_token)

        monkeypatch.undo()
        assert erro.value.code in {"E-TX-STALE-PLAN", "E-TX-ROLLBACK-FAILED"}
        assert alvo.read_bytes() == _INTRUSO
        assert origem.read_bytes() == b"ROM"

    def test_crash_na_substituicao_de_symlink_rollback_restaura_o_link_antigo(
        self, tmp_path: Path
    ) -> None:
        """Substituição atômica de symlink (replace_existing) com crash.

        O link antigo é tomado em custódia antes da troca; crash no meio e o
        recovery devolve exatamente o mesmo symlink (mesmo readlink), sem órfãos.
        """
        origem1 = tmp_path / "origem1.bin"
        origem2 = tmp_path / "origem2.bin"
        origem1.write_bytes(b"ROM-1")
        origem2.write_bytes(b"ROM-2")
        alvo = tmp_path / "link.bin"
        plan1 = transaction.plan_symlink_files({origem1: alvo}, root=tmp_path)
        transaction.apply(plan1.plan_id, plan1.confirm_token)
        assert alvo.is_symlink() and Path(origem1.resolve()).exists()

        plan2 = transaction.plan_symlink_files(
            {origem2: alvo}, root=tmp_path, replace_existing=True
        )
        operation_id = ""
        transaction.set_crash_hook(
            lambda stage: (
                (_ for _ in ()).throw(transaction.SimulatedKill)
                if stage == "custody.taken"
                else None
            )
        )
        try:
            try:
                transaction.apply(plan2.plan_id, plan2.confirm_token)
            except transaction.SimulatedKill:
                pass
            else:
                pytest.fail("crash gate 'custody.taken' não disparou na troca de symlink")
        finally:
            transaction.set_crash_hook(None)

        results = transaction.recover_all()
        operacoes_do_crash = [r for r in results if r.outcome == "rolled-back"]
        assert len(operacoes_do_crash) == 1
        operation_id = operacoes_do_crash[0].operation_id
        assert alvo.is_symlink()
        assert alvo.resolve() == origem1.resolve()
        assert Path(origem2.resolve()).read_bytes() == b"ROM-2"
        assert _orfaos_da_operacao(operation_id) == []
        assert journal.is_terminal(journal.read_records(operation_id))


class TestMove:
    def test_intruso_no_destino_entre_guard_e_rename_sobrevive(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Arquivo alheio aparece no destino do move no último instante.

        O move não pode substituir o intruso: falha fechada, intruso preservado
        e origem intacta.
        """
        origem = tmp_path / "origem.bin"
        origem.write_bytes(b"dados")
        destino = tmp_path / "destino.bin"
        plan = transaction.plan_move_files({origem: destino}, root=tmp_path)

        original = fs.take_custody_named
        disparado = {"ok": False}

        def custodia_e_intruso(path: Path, custody: Path) -> Path | None:
            devolvido = original(path, custody)
            if path == destino and not disparado["ok"]:
                disparado["ok"] = True
                if devolvido is None:
                    destino.write_bytes(_INTRUSO)
            return devolvido

        monkeypatch.setattr(fs, "take_custody_named", custodia_e_intruso)

        with pytest.raises(SteamZeroError) as erro:
            transaction.apply(plan.plan_id, plan.confirm_token)

        monkeypatch.undo()
        assert erro.value.code in {"E-TX-STALE-PLAN", "E-TX-ROLLBACK-FAILED"}
        assert destino.read_bytes() == _INTRUSO
        assert origem.read_bytes() == b"dados"

    def test_crash_no_meio_do_move_recovery_restaura_origem(self, tmp_path: Path) -> None:
        """Crash entre a custódia e a publicação do move.

        Recovery: origem de volta com o conteúdo original, destino ausente,
        custódia liberada, journal terminal.
        """
        origem = tmp_path / "origem.bin"
        origem.write_bytes(b"dados")
        destino = tmp_path / "destino.bin"
        plan = transaction.plan_move_files({origem: destino}, root=tmp_path)

        transaction.set_crash_hook(
            lambda stage: (
                (_ for _ in ()).throw(transaction.SimulatedKill)
                if stage == "custody.taken"
                else None
            )
        )
        try:
            try:
                transaction.apply(plan.plan_id, plan.confirm_token)
            except transaction.SimulatedKill:
                pass
            else:
                pytest.fail("crash gate 'custody.taken' não disparou no move")
        finally:
            transaction.set_crash_hook(None)

        results = transaction.recover_all()
        assert len(results) == 1
        operation_id = results[0].operation_id
        assert results[0].outcome == "rolled-back"
        assert origem.read_bytes() == b"dados"
        assert not destino.exists()
        assert _orfaos_da_operacao(operation_id) == []
        assert journal.is_terminal(journal.read_records(operation_id))

    def test_rollback_do_move_preserva_intruso_que_ocupou_o_destino(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Rollback do move com o destino recém-ocupado por terceiro.

        O rollback remove o arquivo movido — mas só o que reconhece. Se outra
        entrada aparecer no destino no último instante, ela sobrevive e a
        operação falha fechada.
        """
        origem = tmp_path / "origem.bin"
        origem.write_bytes(b"dados")
        destino = tmp_path / "destino.bin"
        plan = transaction.plan_move_files({origem: destino}, root=tmp_path)
        resultado = transaction.apply(plan.plan_id, plan.confirm_token)
        operation_id = resultado.operation_id
        assert destino.read_bytes() == b"dados"

        original = fs.take_custody_named
        disparado = {"ok": False}

        def remove_com_intruso(path: Path, custody: Path) -> Path | None:
            if path == destino and not disparado["ok"]:
                disparado["ok"] = True
                destino.write_bytes(_INTRUSO)
            return original(path, custody)

        monkeypatch.setattr(fs, "take_custody_named", remove_com_intruso)

        with pytest.raises(SteamZeroError) as erro:
            transaction.rollback(operation_id, reason="teste")

        monkeypatch.undo()
        assert erro.value.code == "E-TX-ROLLBACK-FAILED"
        assert destino.read_bytes() == _INTRUSO
        assert origem.read_bytes() == b"dados"
        # a operação continua commitada; o rollback falhou SEM alegar conclusão
        assert not journal.has_type(journal.read_records(operation_id), journal.ROLLBACK)
