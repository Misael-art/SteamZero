# SPDX-License-Identifier: GPL-3.0-or-later
"""Gates executáveis de independência e do importador offline opcional."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from check_independence import check
from import_phasezero_snapshot import build_bundle


def test_default_package_has_no_legacy_runtime_dependency() -> None:
    root = Path(__file__).resolve().parents[2]
    assert check(root) == []


def test_offline_importer_creates_self_contained_bundle(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot"
    operations = snapshot / "operations"
    operations.mkdir(parents=True)
    (operations / "one.json").write_text(json.dumps({"mode": "handheld"}), encoding="utf-8")
    bundle = build_bundle(snapshot)
    assert bundle["runtimeDependency"] is False
    assert bundle["records"] == [
        {"sourceRelpath": "operations/one.json", "payload": {"mode": "handheld"}}
    ]
    # O bundle continua íntegro depois que a fonte deixa de existir.
    payload = json.loads(json.dumps(bundle))
    (operations / "one.json").unlink()
    assert payload["records"][0]["payload"]["mode"] == "handheld"


def test_offline_importer_rejects_symlink(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    (snapshot / "escape.json").symlink_to(outside)
    with pytest.raises(ValueError, match="insegura"):
        build_bundle(snapshot)


def test_qml_central_declares_handheld_accessibility_contract() -> None:
    root = Path(__file__).resolve().parents[2]
    qml = (root / "src/steamzero/ui/qml/Main.qml").read_text(encoding="utf-8")
    assert "Layout.minimumHeight: 48" in qml
    assert "Accessible.name" in qml
    assert "KeyNavigation" in qml
    assert '"/conflict/plan"' in qml
    assert '"/conflict/apply"' in qml
    assert "Plano bloqueado" in qml
    for section in ("Modo", "Controles e teclado", "Display e janelas", "Diagnóstico"):
        assert section in qml
