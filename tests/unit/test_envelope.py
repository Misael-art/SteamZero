# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from steamzero.api.envelope import build_envelope, status_from_checks


def test_status_from_checks_ok_when_no_issues() -> None:
    assert status_from_checks([]) == "ok"


def test_status_from_checks_ok_when_all_good() -> None:
    checks = [{"status": "ok"}, {"status": "ok"}]
    assert status_from_checks(checks) == "ok"


def test_status_from_checks_failed_on_fail() -> None:
    checks = [{"status": "ok"}, {"status": "fail"}, {"status": "warn"}]
    assert status_from_checks(checks) == "failed"


def test_status_from_checks_degraded_on_warn() -> None:
    checks = [{"status": "ok"}, {"status": "warn"}]
    assert status_from_checks(checks) == "degraded"


def test_build_envelope_ok_derives_ok() -> None:
    env = build_envelope("test", "test", status="ok")
    assert env["ok"] is True
    assert env["status"] == "ok"


def test_build_envelope_explicit_ok_passed_through() -> None:
    env = build_envelope("test", "test", status="failed", ok=False)
    assert env["ok"] is False


def test_success_statuses_are_not_reported_as_failure() -> None:
    """Regressao dos 41 envelopes que diziam falha sobre operacao bem-sucedida.

    Medido instrumentando `build_envelope` na suite inteira: `ready` (19),
    `rolled-back` (13 de 14), `unverified` (6), `unchecked` (2) e `committed`
    (1) chegavam com `ok: false`. A derivacao so aceitava `ok`/`noop`/
    `degraded`, e tudo fora disso virava falha em silencio.

    O caso mais grave nao era o rollback: era `frontends plan`, o primeiro
    comando que qualquer pessoa roda, respondendo `ok: false` sobre um plano
    perfeitamente montado. E `rolled-back` estava INCONSISTENTE consigo mesmo —
    um chamador passava `ok=` explicito e acertava; treze nao passavam.
    """
    for status in ("ok", "noop", "degraded", "ready", "rolled-back", "committed"):
        assert build_envelope("t", "t", status=status)["ok"] is True, status
    # Nao conferido ainda e um resultado, nao um erro — mesma regua do degraded.
    for status in ("unchecked", "unverified"):
        assert build_envelope("t", "t", status=status)["ok"] is True, status
    for status in ("failed", "blocked"):
        assert build_envelope("t", "t", status=status)["ok"] is False, status


def test_unknown_status_degrades_instead_of_raising() -> None:
    """AGENTS.md §8: a saida da CLI nao pode virar excecao por status novo."""
    envelope = build_envelope("t", "t", status="status-que-nao-existe")
    assert envelope["ok"] is False
    assert envelope["status"] == "status-que-nao-existe"


def test_every_literal_status_is_declared_in_the_contract() -> None:
    """Um literal novo em `build_envelope` precisa ser classificado.

    Este e o gate que substitui um `raise` em runtime. Ele so alcanca os
    literais — `status=result.status` e afins escapam por construcao — mas
    literal foi exatamente como os cinco status mal classificados entraram.
    """
    import ast
    from pathlib import Path

    from steamzero.api.envelope import KNOWN_STATUSES

    source_root = Path(__file__).resolve().parents[2] / "src"
    undeclared: dict[str, list[str]] = {}
    for path in sorted(source_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call) and getattr(node.func, "id", "") == "build_envelope"
            ):
                continue
            for keyword in node.keywords:
                if keyword.arg != "status" or not isinstance(keyword.value, ast.Constant):
                    continue
                value = keyword.value.value
                if value not in KNOWN_STATUSES:
                    undeclared.setdefault(str(value), []).append(
                        f"{path.relative_to(source_root)}:{node.lineno}"
                    )
    assert undeclared == {}, (
        f"status nao declarado em KNOWN_STATUSES: {undeclared}; "
        "classifique como sucesso ou falha em api/envelope.py"
    )
