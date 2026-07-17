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
    assert '"/component/plan"' in qml
    assert '"/component/apply"' in qml
    assert '"/steam/open"' in qml
    assert '"/steam/input/open"' in qml
    assert '"/steam/gameplay/plan"' in qml
    assert '"/steam/gameplay/apply"' in qml
    assert '"/steam/gameplay/recover"' in qml
    assert '"/steam/gameplay/launch-options/plan"' in qml
    assert '"/steam/gameplay/launch-options/apply"' in qml
    assert '"/steam/gameplay/launch-options/rollback"' in qml
    assert '"/system/lsfg/plan"' in qml
    assert '"/system/lsfg/apply"' in qml
    assert '"/system/lsfg/rollback"' in qml
    assert "Plano bloqueado" in qml
    for section in (
        "Visão geral",
        "Gerenciar emuladores",
        "Steam e integração",
        "Perfis do Desktop",
        "Saves e Sync",
        "Sistema e recuperação",
    ):
        assert section in qml
    gameplay_qml = (root / "src/steamzero/ui/qml/SteamGameplay.qml").read_text(encoding="utf-8")
    for contract in (
        "Prontidão do jogo",
        "Revisar e aplicar perfil",
        "Restaurar perfil seguro",
        "Feral GameMode",
        "Gamescope",
        "Abrir Sistema",
        "Frame generation",
        "Controles por jogo",
        "Editar no Steam",
    ):
        assert contract in gameplay_qml
    for contract in ("Preparar LSFG-VK", "Instalar e verificar", "Desfazer"):
        assert contract in qml
    for contract in (
        "Lançamento gerenciado",
        "Opção de inicialização Steam",
        "Restaurar estado",
        "Configurar na Steam",
        "Configurar e verificar",
        "Desfazer configuração",
        "Limpeza e manutenção",
        "Pacote de mídia",
        "SteamZero Game Mode",
        "Boot direto: protegido",
    ):
        assert contract in gameplay_qml
    main_qml = (root / "src/steamzero/ui/qml/Main.qml").read_text(encoding="utf-8")
    for route in (
        '"/steam/maintenance/plan"',
        '"/steam/maintenance/apply"',
        '"/steam/maintenance/recover"',
        '"/steam/media/plan"',
        '"/steam/media/apply"',
        '"/steam/media/rollback"',
    ):
        assert route in main_qml
