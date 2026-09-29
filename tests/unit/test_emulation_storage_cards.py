# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""UX-04 — o cartão de armazenamento publica MEDIDA, não prosa com unidade.

A auditoria pede "unidades localizadas e consistentes" (AUDIT.md:124). As páginas
que formatavam bytes cada uma do seu jeito agora delegam ao módulo compartilhado
``sizes.js``; este arquivo cobre o outro lado do defeito, o produtor: o texto cru
nascia em ``adapters/emulation.py`` já com a unidade escrita, e a página só podia
ecoá-lo — ``Emulation.qml`` devolvia ``String(card.metric)``.

Um número que chega como frase não é localizado, não converge com as outras
superfícies e não pode ser comparado. O contrato então é:

* a grandeza viaja como inteiro de bytes (``metricBytes``), nunca como texto;
* a capacidade do volume viaja como inteiro (``capacityBytes``);
* ausência viaja como ``None`` — não como ``0``;
* ``detail`` explica o estado, mas não reimprime a grandeza.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from steamzero.adapters import emulation as emulation_module
from steamzero.adapters.emulation import EmulationController, SessionSecretStore
from steamzero.core.state import StateStore

SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "steamzero"
    / "schemas"
    / "emulation-workspace-v1.schema.json"
)

_BUCKETO_GRANDE = {
    "id": "roms",
    "label": "ROMs",
    "state": "ready",
    "files": 3,
    "bytes": 1_073_741_824,
    "roots": 1,
    "error": None,
}
_BUCKETO_ZERO = {
    "id": "saves",
    "label": "Saves",
    "state": "empty",
    "files": 0,
    "bytes": 0,
    "roots": 1,
    "error": None,
}
_VOLUME_MEDIDO = {
    "state": "ready",
    "capacityBytes": 536_870_912_000,
    "freeBytes": 150_000_000_000,
    "usedBytes": 386_870_912_000,
    "error": None,
}
_VOLUME_AUSENTE = {
    "state": "unavailable",
    "capacityBytes": None,
    "freeBytes": None,
    "usedBytes": None,
    "error": "ponto de montagem não resolvido",
}


def _resumo(buckets: list[dict[str, Any]], volume: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "buckets": buckets,
        "totals": {
            "files": sum(int(bucket["files"]) for bucket in buckets),
            "bytes": sum(int(bucket["bytes"]) for bucket in buckets),
        },
        "volume": volume,
    }


def _controlador(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    resumo: dict[str, Any],
) -> EmulationController:
    """Controller real com a medição de disco substituída pelo fixture."""

    def _coletor(**_kwargs: Any) -> dict[str, Any]:
        return resumo

    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(emulation_module, "collect_storage_summary", _coletor)
    return EmulationController(
        store_factory=lambda: StateStore(tmp_path / "state.db"),
        which=lambda _command: None,
        spawn=lambda _argv: None,
        # Sem isto o controlador cai no SecretServiceStore real, que shela para o
        # secret-tool do host: passa onde há chaveiro, reprova onde não existe.
        secret_store=SessionSecretStore(),
    )


def _cartoes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, resumo: dict[str, Any]
) -> list[dict[str, Any]]:
    controller = _controlador(tmp_path, monkeypatch, resumo)
    cards = controller.snapshot({"context": {}})["platforms"][0]["areaData"]["storage"]["cards"]
    return [dict(card) for card in cards]


def _armazenagem(cartoes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [card for card in cartoes if str(card["id"]).startswith("storage-")]


def test_grandeza_do_bucket_viaja_como_inteiro_e_nao_como_texto(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cartoes = _cartoes(tmp_path, monkeypatch, _resumo([_BUCKETO_GRANDE], _VOLUME_MEDIDO))
    roms = next(card for card in _armazenagem(cartoes) if card["id"] == "storage-roms")

    assert roms.get("metricBytes") == 1_073_741_824, (
        "sem campo tipado a página não tem o que formatar — só ecoa a frase do produtor"
    )
    assert "metric" not in roms, (
        f"o cartão ainda publica a grandeza como texto ({roms.get('metric')!r}); "
        "frase não tem separador de locale nem unidade IEC consistente"
    )
    assert "byte(s)" not in roms["detail"] and " bytes" not in roms["detail"], (
        f"a prosa reimprime a medida ({roms['detail']!r}); o número da tela nasceria "
        "fora do formatador"
    )


def test_zero_medido_e_zero_e_ausencia_e_nenhum(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cartoes = _cartoes(tmp_path, monkeypatch, _resumo([_BUCKETO_ZERO], _VOLUME_AUSENTE))
    saves = next(card for card in _armazenagem(cartoes) if card["id"] == "storage-saves")
    volume = next(card for card in _armazenagem(cartoes) if card["id"] == "storage-volume")

    assert saves.get("metricBytes") == 0, (
        "0 byte medido não é dado ausente: virar '—' esconde uma medição real"
    )
    assert volume.get("metricBytes") is None, (
        f"volume não medido publicado como {volume.get('metricBytes')!r}: ausência não é zero"
    )
    assert volume.get("capacityBytes") is None
    assert "0 byte" not in volume["detail"], (
        f"a frase do volume fabrica zero a partir de ausência ({volume['detail']!r})"
    )


def test_capacidade_do_volume_viaja_como_inteiro(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cartoes = _cartoes(tmp_path, monkeypatch, _resumo([_BUCKETO_GRANDE], _VOLUME_MEDIDO))
    volume = next(card for card in _armazenagem(cartoes) if card["id"] == "storage-volume")

    assert volume.get("metricBytes") == 150_000_000_000
    assert volume.get("capacityBytes") == 536_870_912_000, (
        "a capacidade só existia dentro da prosa; sem campo tipado a tela não pode "
        "formatá-la e o usuário perde o total do volume"
    )
    assert "byte(s)" not in volume["detail"]


def test_schema_valida_o_tipo_da_grandeza() -> None:
    """Um `metricBytes` textual tem de ser recusado pelo contrato, não sobreviver."""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    propriedades = schema["$defs"]["card"]["properties"]
    assert "metricBytes" in propriedades and "capacityBytes" in propriedades, (
        "o cartão é additionalProperties: true, então nada prova que a medida viaja "
        "tipada — o campo precisa de validação própria"
    )
    # Mesmo recurso de tests/unit/test_readiness_contract.py: um ramo de `$defs` só
    # valida sozinho se o `$ref` interno (`#/$defs/state`) resolver no documento.
    validador = jsonschema.Draft202012Validator(
        {
            "$schema": schema["$schema"],
            "$id": schema["$id"],
            "$defs": schema["$defs"],
            "$ref": "#/$defs/card",
        }
    )
    base = {
        "id": "storage-volume",
        "title": "Volume",
        "detail": "Espaço livre do volume",
        "state": "ready",
        "statusLabel": "ok",
    }
    validador.validate(base | {"metricBytes": 4096, "capacityBytes": 4096})
    validador.validate(base | {"metricBytes": None, "capacityBytes": None})
    with pytest.raises(jsonschema.ValidationError):
        validador.validate(base | {"metricBytes": "4 KiB"})
    with pytest.raises(jsonschema.ValidationError):
        validador.validate(base | {"metricBytes": -1})


#: O mesmo defeito das quatro páginas reaparece onde o adapter escreve a unidade na
#: frase: um ``MiB`` fixo não é localizado, não escolhe andar e não pode ser
#: comparado. A varredura abaixo é a norma do workspace inteiro — se um cartão novo
#: nascer com grandeza na prosa, este teste o nomeia.
_GRANDEZA_NA_PROSA = re.compile(
    r"(?<![\w.])\d+(?:[.,]\d+)?\s*(?:bytes?|B\b|KiB|MiB|GiB|TiB|KB|MB|GB)"
)

_JOGO_PRESERVADO = {
    "id": "switch-1",
    "titleId": "0100ABCDEF123000",
    "name": "Jogo Salvo",
    "state": "ready",
    "statusLabel": "Pronto",
    "path": "/owned/switch-1.rom",
    "platform": "switch",
    "platformId": "switch",
    "saveTarget": {
        "confirmed": True,
        "destination": "/dados/saves/switch-1",
        "fileCount": 4,
        "size": 52_428_800,
        "emulatorVersion": "1.2.3",
        "compatibilityFingerprint": "fp-1",
    },
    "saveBackups": [
        {
            "recordKey": "abcdef0123456789",
            "createdAt": "2026-09-28T10:00:00Z",
            "size": 5_242_880,
            "integrity": "ok",
            "compatibilityFingerprint": "fp-1",
        }
    ],
}


def _workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[EmulationController, dict[str, Any]]:
    """Snapshot real com acervo, medição de disco e um update importado."""
    controller = _controlador(
        tmp_path, monkeypatch, _resumo([_BUCKETO_GRANDE, _BUCKETO_ZERO], _VOLUME_MEDIDO)
    )
    monkeypatch.setattr(controller, "_load_library_cache", lambda: ([_JOGO_PRESERVADO], 0))
    monkeypatch.setattr(controller, "_enrich_games", lambda games, *a: list(games))
    monkeypatch.setattr(controller, "_enrich_preservation", lambda games: games)
    monkeypatch.setattr(controller, "_enrich_controls", lambda games: games)
    update = tmp_path / "update.nsp"
    update.write_bytes(b"x" * 2_097_152)
    plan = controller.plan_action(
        {
            "actionId": "content.update.import",
            "path": str(update),
            "titleId": _JOGO_PRESERVADO["titleId"],
            "version": "1.2.0",
        }
    )
    controller.apply_action(str(plan["planId"]), str(plan["confirmToken"]))
    return controller, controller.snapshot({"context": {}})


def _varredura(workspace: dict[str, Any]) -> list[dict[str, Any]]:
    cartoes: list[dict[str, Any]] = []

    def andar(ramo: Any) -> None:
        if isinstance(ramo, dict):
            if {"id", "title", "detail"} <= ramo.keys():
                cartoes.append(ramo)
            for valor in ramo.values():
                andar(valor)
        elif isinstance(ramo, list):
            for item in ramo:
                andar(item)

    andar(workspace)
    return [card for card in cartoes if isinstance(card.get("detail"), str)]


def test_family_preservation_e_backup_estao_na_varredura(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sem família presente a varredura seria vacuosa — ela prova a presença antes."""
    _, workspace = _workspace(tmp_path, monkeypatch)
    ids = {str(card["id"]) for card in _varredura(workspace)}
    assert "preservation-save-switch-1" in ids, ids
    assert "backup-abcdef012345" in ids, ids
    assert "media-cache" in ids, ids
    assert any(i.startswith("content-") for i in ids), ids
    assert "storage-volume" in ids, ids


def test_nenhum_cartao_escreve_grandeza_na_prosa(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, workspace = _workspace(tmp_path, monkeypatch)
    ofensas = [
        f"{card['id']}: {card['detail']}"
        for card in _varredura(workspace)
        if _GRANDEZA_NA_PROSA.search(str(card["detail"]))
    ]
    assert ofensas == [], "a grandeza viaja inteira no contrato; a frase só explica o estado"


def test_preservation_e_backup_publicam_a_medida_como_inteiro(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, workspace = _workspace(tmp_path, monkeypatch)
    cartoes = {str(card["id"]): card for card in _varredura(workspace)}

    destino = cartoes["preservation-save-switch-1"]
    assert destino["metricBytes"] == 52_428_800, destino
    backup = cartoes["backup-abcdef012345"]
    assert backup["metricBytes"] == 5_242_880, backup


def test_conteudo_importado_publica_a_medida_como_inteiro(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O cartão de update/DLC nasce de uma importação real, não de um fixture solto."""
    _, workspace = _workspace(tmp_path, monkeypatch)
    registro = next(
        card for card in _varredura(workspace) if str(card["id"]).startswith("content-")
    )
    assert registro["metricBytes"] == 2_097_152, registro
    assert not _GRANDEZA_NA_PROSA.search(str(registro["detail"])), registro


def test_cache_de_midia_publica_a_medida_como_inteiro(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, workspace = _workspace(tmp_path, monkeypatch)
    cache = next(card for card in _varredura(workspace) if str(card["id"]) == "media-cache")
    assert cache["metricBytes"] == 0, cache
    assert "byte" not in str(cache["detail"]), cache
