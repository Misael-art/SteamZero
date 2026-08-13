# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""FI-05 — o alvo muda DENTRO da janela destrutiva, no ultimo instante.

Tres rodadas de correcao trataram este problema conferindo o alvo imediatamente
antes de escrever, remover ou restaurar. Conferir antes nunca fecha a janela:
entre a conferencia e o syscall destrutivo cabe uma troca, e foi exatamente ai
que cada correcao anterior continuou perdendo dado alheio.

Estes testes injetam o intruso DEPOIS de toda conferencia e ANTES do syscall que
destroi. Eles nao aceitam "janela pequena": ou a entrada inesperada sobrevive
byte a byte, ou a operacao falha fechada.

Cada caso cobra quatro coisas ao mesmo tempo:

1. erro explicito (`E-TX-STALE-PLAN` ou `E-TX-ROLLBACK-FAILED`);
2. intruso preservado byte a byte;
3. nenhum temporario ou quarentena orfao depois da recuperacao;
4. o journal/estado NAO alegando rollback completo quando ele falhou.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from steamzero.core import fs, journal, paths, transaction
from steamzero.core.errors import SteamZeroError

_INTRUSO = b'input_device = "chegou na ultima janela"\n'


def _plan(tmp_path: Path, content: bytes = b"novo") -> tuple[Path, transaction.Plan]:
    target = tmp_path / "cfg.ini"
    plan = transaction.plan_write_files({target: content}, root=tmp_path, kind="test.write")
    return target, plan


def _orfaos(tmp_path: Path, operation_id: str | None = None) -> list[str]:
    """Temporarios no diretorio do alvo e custodias DESTA operacao.

    A varredura e por operacao de proposito: um caso de falha fechada CONSERVA a
    custodia dele, e varrer a quarentena inteira faria o resto do arquivo
    reprovar por causa dessa preservacao deliberada.
    """
    restos = [p.name for p in tmp_path.iterdir() if p.name.startswith(".") and ".tmp." in p.name]
    if operation_id is not None:
        quarentena = paths.quarantine_for(operation_id)
        if quarentena.is_dir():
            restos += [str(p) for p in quarentena.rglob("*") if p.is_file()]
    return restos


def _rollback_alegado_completo(operation_id: str) -> bool:
    registros = journal.read_records(operation_id)
    return any(r.get("type") == "operation.rolled-back" for r in registros)


class TestPublicacaoSobreAlvoExistente:
    def test_intruso_entre_a_conferencia_e_a_publicacao_sobrevive(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Injeta depois do hash de verificacao, antes do syscall que publica."""
        target, _ = _plan(tmp_path, b"antigo")
        target.write_bytes(b"antigo")
        _, plan = _plan(tmp_path, b"novo")

        original = fs.hash_file
        disparado = {"ok": False}

        def hash_e_intruso(path: Path) -> str:
            resultado = original(path)
            if not disparado["ok"] and path == target:
                disparado["ok"] = True
                target.write_bytes(_INTRUSO)
            return resultado

        monkeypatch.setattr(fs, "hash_file", hash_e_intruso)

        with pytest.raises(SteamZeroError) as erro:
            transaction.apply(plan.plan_id, plan.confirm_token)

        monkeypatch.undo()
        assert erro.value.code in {"E-TX-STALE-PLAN", "E-TX-ROLLBACK-FAILED"}
        assert target.read_bytes() == _INTRUSO
        assert _orfaos(tmp_path) == []

    def test_sem_primitiva_segura_a_operacao_falha_fechada(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`renameat2` indisponivel nao autoriza publicar com janela.

        Sem primitiva que troque ou mova sem substituir, nao ha como publicar
        preservando o inesperado. A resposta correta e recusar, nao arriscar.
        """
        target, _ = _plan(tmp_path, b"antigo")
        target.write_bytes(b"antigo")
        _, plan = _plan(tmp_path, b"novo")
        monkeypatch.setattr(fs, "_rename_exchange", lambda _a, _b: False)
        monkeypatch.setattr(fs, "_rename_noreplace", lambda _a, _b: False)

        with pytest.raises(SteamZeroError):
            transaction.apply(plan.plan_id, plan.confirm_token)

        monkeypatch.undo()
        assert target.read_bytes() == b"antigo"
        assert _orfaos(tmp_path) == []

    def test_ocupacao_do_alvo_apos_a_custodia_falha_fechada_e_conserva(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A unica janela que resta, e o que deve acontecer nela.

        Depois que o alvo e tomado em custodia, ele fica VAZIO por um instante.
        Se algo ocupar esse vazio, publicar por cima destruiria a entrada nova, e
        devolver a antiga tambem. A operacao falha fechada e CONSERVA as duas: a
        nova fica no lugar, a antiga permanece sob custodia e o erro diz onde.
        """
        target, _ = _plan(tmp_path, b"antigo")
        target.write_bytes(b"antigo")
        _, plan = _plan(tmp_path, b"novo")

        original = fs.take_custody_named
        estado: dict[str, object] = {}

        def custodia_e_ocupacao(path: Path, custody: Path) -> Path | None:
            devolvido = original(path, custody)
            if path == target and "feito" not in estado:
                estado["feito"] = True
                estado["custody"] = devolvido
                target.write_bytes(_INTRUSO)
            return devolvido

        monkeypatch.setattr(fs, "take_custody_named", custodia_e_ocupacao)

        with pytest.raises(SteamZeroError) as erro:
            transaction.apply(plan.plan_id, plan.confirm_token)

        monkeypatch.undo()
        assert erro.value.code in {"E-TX-STALE-PLAN", "E-TX-ROLLBACK-FAILED"}
        # Nada foi destruido: o intruso esta no lugar...
        assert target.read_bytes() == _INTRUSO
        # ...e a entrada antiga foi resolvida com o estado terminal limpo:
        # como o backup a preserva byte a byte, a custodia nao sobra orfa.
        custody = estado["custody"]
        assert isinstance(custody, Path)
        assert not custody.exists()
        assert _orfaos(tmp_path) == []


class TestRollback:
    def test_delete_nao_remove_intruso_injetado_apos_o_guard(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Alvo ausente no plano; intruso aparece depois do fingerprint do guard.

        O guard do `delete` confere e SO ENTAO remove. Entre as duas coisas cabe
        a criacao de um arquivo que nao e nosso, e removê-lo destroi dado alheio.
        """
        target, plan = _plan(tmp_path, b"novo")
        resultado = transaction.apply(plan.plan_id, plan.confirm_token)

        original = transaction._fingerprint
        disparado = {"ok": False}

        def fingerprint_e_intruso(path: Path) -> str | None:
            valor = original(path)
            if not disparado["ok"] and path == target:
                disparado["ok"] = True
                target.write_bytes(_INTRUSO)
            return valor

        monkeypatch.setattr(transaction, "_fingerprint", fingerprint_e_intruso)

        with pytest.raises(SteamZeroError) as erro:
            transaction.rollback(resultado.operation_id, reason="teste")

        monkeypatch.undo()
        assert erro.value.code == "E-TX-ROLLBACK-FAILED"
        assert target.read_bytes() == _INTRUSO
        assert _orfaos(tmp_path, resultado.operation_id) == []
        assert not _rollback_alegado_completo(resultado.operation_id)

    def test_restore_nao_sobrescreve_entrada_que_ocupou_o_alvo(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Mesma janela, no caminho de restauracao.

        O `restore` tambem toma o alvo em custodia antes de copiar o backup. Se
        algo ocupar o vazio, o backup NAO e copiado por cima: falha fechada, com
        as duas entradas conservadas.
        """
        target, _ = _plan(tmp_path, b"antigo")
        target.write_bytes(b"antigo")
        _, plan = _plan(tmp_path, b"novo")
        resultado = transaction.apply(plan.plan_id, plan.confirm_token)
        assert target.read_bytes() == b"novo"

        original = fs.take_custody_named
        estado: dict[str, object] = {}

        def custodia_e_ocupacao(path: Path, custody: Path) -> Path | None:
            devolvido = original(path, custody)
            if path == target and "feito" not in estado:
                estado["feito"] = True
                estado["custody"] = devolvido
                target.write_bytes(_INTRUSO)
            return devolvido

        monkeypatch.setattr(fs, "take_custody_named", custodia_e_ocupacao)

        with pytest.raises(SteamZeroError) as erro:
            transaction.rollback(resultado.operation_id, reason="teste")

        monkeypatch.undo()
        assert erro.value.code == "E-TX-ROLLBACK-FAILED"
        assert target.read_bytes() == _INTRUSO
        custody = estado["custody"]
        assert isinstance(custody, Path)
        assert custody.read_bytes() == b"novo"
        assert not _rollback_alegado_completo(resultado.operation_id)
