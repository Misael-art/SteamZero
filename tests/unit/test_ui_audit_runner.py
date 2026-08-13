# SPDX-License-Identifier: GPL-3.0-or-later
"""Contratos do harness de auditoria visual.

O harness é o instrumento que produz a evidência da UI. Quando ele mente — CLI
inexistente, warnings silenciados por regra global, manifesto sem commit — a
auditoria inteira herda a mentira. Estes testes cobrem o instrumento, não a tela.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import ui_audit_runner as runner  # noqa: E402


def test_cli_argv_uses_an_entry_point_the_package_actually_publishes() -> None:
    """Regressão: `python -m steamzero` nunca funcionou.

    A auditoria de 2026-08-13 gravou no manifesto
    "No module named steamzero.__main__; 'steamzero' is a package and cannot be
    directly executed" no lugar de status e doctor.
    """
    assert importlib.util.find_spec("steamzero.__main__") is None, (
        "se o pacote passar a publicar __main__, este teste deve ser revisto "
        "junto com a escolha de entrada do runner"
    )
    assert importlib.util.find_spec(runner.CLI_MODULE) is not None

    argv = runner.cli_argv("doctor", "--json")
    assert argv[1:3] == ["-m", runner.CLI_MODULE]
    assert "-m" not in argv or argv[2] != "steamzero"


def test_qml_environment_does_not_silence_warnings_globally() -> None:
    """QT_LOGGING_RULES global escondia os nossos warnings junto com os do Breeze."""
    env = runner._qml_env()
    assert env["QT_LOGGING_RULES"] == ""
    assert env["QT_FORCE_STDERR_LOGGING"] == "1"


def test_warnings_are_split_between_our_qml_and_the_host_style() -> None:
    stderr = "\n".join(
        [
            "qrc:/qt-project.org/imports/QtQuick/Controls/Breeze/Button.qml:12:5: "
            "QML Button: Binding loop detected",
            "file:///home/user/src/steamzero/ui/qml/Main.qml:88:9: "
            "TypeError: Cannot read property 'id' of null",
            "some unrelated chatter without a diagnostic word",
        ]
    )
    classified = runner._classify_warnings(stderr)
    assert classified["ownCount"] == 1
    assert classified["externalCount"] == 1
    assert "Main.qml" in classified["own"][0]
    assert "Breeze" in classified["external"][0]


def test_process_status_names_the_signal_that_killed_the_harness() -> None:
    """qmlReturncode=-11 precisa aparecer como crash, não como 'apenas != 0'."""
    crashed = runner._process_status(-11)
    assert crashed["outcome"] == "crashed"
    assert crashed["signal"] == "SIGSEGV"
    assert runner._process_status(0)["outcome"] == "ok"
    assert runner._process_status(2)["outcome"] == "failed"


def test_programmatic_checks_fail_when_the_harness_crashed() -> None:
    checks = runner._programmatic_checks(
        pngs=[{"name": "a.png", "bytes": 10, "viewport": "1280x800"}],
        records=[{"name": "a", "viewport": "1280x800"}],
        warnings={"ownCount": 0, "externalCount": 3},
        process=runner._process_status(-11),
    )
    by_id = {check["id"]: check for check in checks}
    assert by_id["harness-terminou-sem-crash"]["passed"] is False
    assert by_id["qml-proprio-sem-warning"]["passed"] is True
    assert by_id["toda-captura-tem-conteudo"]["passed"] is True


def test_programmatic_checks_fail_on_our_own_qml_warnings() -> None:
    checks = runner._programmatic_checks(
        pngs=[],
        records=[],
        warnings={"ownCount": 2, "externalCount": 0},
        process=runner._process_status(0),
    )
    by_id = {check["id"]: check for check in checks}
    assert by_id["qml-proprio-sem-warning"]["passed"] is False
    assert by_id["harness-terminou-sem-crash"]["passed"] is True


def test_capture_records_are_parsed_from_the_harness_stdout() -> None:
    stdout = "\n".join(
        [
            "AUDIT-OK /tmp/x/deck-overview.png",
            'AUDIT-META {"name": "deck-overview", "viewport": "1280x800", '
            '"themeId": "org.steamzero.default"}',
            "AUDIT-META not-json-at-all",
        ]
    )
    records = runner._parse_capture_records(stdout)
    assert len(records) == 1
    assert records[0]["viewport"] == "1280x800"


def test_existing_evidence_from_another_commit_is_not_overwritten(tmp_path: Path) -> None:
    """Evidência histórica vale pela data e pelo commit; sobrescrever apaga a base."""
    manifest = tmp_path / "MANIFEST.json"
    manifest.write_text(json.dumps({"repository": {"commit": "a" * 40}}), encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        runner._guard_historical_evidence(tmp_path, "b" * 40, overwrite=False)
    assert "evidência histórica" in str(excinfo.value)

    # O mesmo commit é recaptura, não substituição.
    runner._guard_historical_evidence(tmp_path, "a" * 40, overwrite=False)
    # E o operador pode substituir de propósito.
    runner._guard_historical_evidence(tmp_path, "b" * 40, overwrite=True)
