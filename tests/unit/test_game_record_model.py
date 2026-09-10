# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Modelo canônico ``GameRecord`` (frente A1).

Prova as duas invariantes que justificam o modelo existir: campo desconhecido
sobrevive ao round-trip, e fonte pobre não apaga informação rica. As fixtures
são as mesmas da frente A0 — se o modelo divergir do contrato, estes testes
reprovam junto com os de schema.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from steamzero.domain.game_record import (
    ConflictPolicy,
    GameRecord,
    GameRecordError,
    MediaRole,
    conflict_warning,
    validate_mapping,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "aura-contracts" / "game-record"


def _valid_fixtures() -> list[Path]:
    paths = sorted((FIXTURES / "valid").glob("*.json"))
    assert paths, f"fixtures válidas ausentes em {FIXTURES / 'valid'}"
    return paths


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _base_record(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schemaVersion": 1,
        "id": "sz-fixture-base",
        "title": "Base",
        "platformId": "psx",
        "path": "/roms/psx/base.chd",
        "availability": "available",
        "updatedAt": "2026-09-09T00:00:00Z",
    }
    payload.update(overrides)
    return payload


# -- contrato ---------------------------------------------------------------


@pytest.mark.parametrize("path", _valid_fixtures(), ids=lambda p: p.stem)
def test_fixtures_validas_carregam_no_modelo(path: Path) -> None:
    record = GameRecord.from_mapping(_load(path))
    assert record.id
    assert record.title
    assert record.availability


@pytest.mark.parametrize("path", _valid_fixtures(), ids=lambda p: p.stem)
def test_round_trip_preserva_o_payload_inteiro(path: Path) -> None:
    """Inclui campos que este código não conhece — a invariante nº 1."""
    original = _load(path)
    assert GameRecord.from_mapping(original).to_mapping() == original


def test_campo_desconhecido_sobrevive_ao_round_trip() -> None:
    payload = _base_record(campoDeFormatoFuturo={"aninhado": [1, 2, 3]})
    restored = GameRecord.from_mapping(payload).to_mapping()
    assert restored["campoDeFormatoFuturo"] == {"aninhado": [1, 2, 3]}


def test_registro_sem_campo_obrigatorio_e_recusado() -> None:
    payload = _base_record()
    del payload["platformId"]
    with pytest.raises(GameRecordError, match="platformId"):
        GameRecord.from_mapping(payload)


def test_erro_de_validacao_cita_o_campo_culpado() -> None:
    """Erro que anuncia a causa errada custa mais que erro nenhum."""
    with pytest.raises(GameRecordError, match=r"/availability"):
        GameRecord.from_mapping(_base_record(availability="talvez"))


def test_validate_mapping_aceita_fixture_valida() -> None:
    validate_mapping(_load(_valid_fixtures()[0]))


def test_to_mapping_nao_compartilha_estado_com_o_registro() -> None:
    record = GameRecord.from_mapping(_base_record(genres=["rpg"]))
    mutated = record.to_mapping()
    mutated["genres"].append("ação")
    assert record.to_mapping()["genres"] == ["rpg"]


# -- mídia ------------------------------------------------------------------


def test_arte_ausente_e_estado_normal_nao_erro() -> None:
    record = GameRecord.from_mapping(_base_record())
    assert record.media(MediaRole.COVER) is None


def test_media_devolve_o_asset_do_papel_pedido() -> None:
    record = GameRecord.from_mapping(
        _base_record(media={"cover": {"path": "/art/c.png", "format": "png"}})
    )
    cover = record.media(MediaRole.COVER)
    assert cover is not None and cover["path"] == "/art/c.png"
    assert record.media(MediaRole.FANART) is None


# -- fusão ------------------------------------------------------------------


def _with_provenance(field_name: str, policy: ConflictPolicy, **overrides: Any) -> dict[str, Any]:
    return _base_record(
        provenance={
            field_name: {
                "source": "esde",
                "retrievedAt": "2026-09-09T00:00:00Z",
                "confidence": 0.5,
                "conflictPolicy": policy.value,
            }
        },
        **overrides,
    )


def test_fusao_exige_o_mesmo_id() -> None:
    a = GameRecord.from_mapping(_base_record())
    b = GameRecord.from_mapping(_base_record(id="sz-outro"))
    with pytest.raises(GameRecordError, match="mesmo id"):
        a.merge(b)


def test_keep_richest_impede_fonte_pobre_de_apagar_descricao() -> None:
    """A invariante nº 2, e a razão de o plano proibir importador destrutivo."""
    rico = GameRecord.from_mapping(
        _with_provenance("description", ConflictPolicy.KEEP_RICHEST, description="Uma descrição.")
    )
    pobre = GameRecord.from_mapping(_base_record(description="x"))
    assert rico.merge(pobre).record.to_mapping()["description"] == "Uma descrição."


def test_keep_richest_aceita_valor_mais_rico() -> None:
    pobre = GameRecord.from_mapping(
        _with_provenance("description", ConflictPolicy.KEEP_RICHEST, description="x")
    )
    rico = GameRecord.from_mapping(_base_record(description="Uma descrição completa."))
    assert pobre.merge(rico).record.to_mapping()["description"] == "Uma descrição completa."


def test_campo_ausente_e_adicionado_e_nao_conta_como_conflito() -> None:
    atual = GameRecord.from_mapping(_base_record())
    novo = GameRecord.from_mapping(_base_record(developer="Estúdio"))
    outcome = atual.merge(novo)
    assert outcome.record.to_mapping()["developer"] == "Estúdio"
    assert outcome.conflicts == ()


def test_prefer_source_deixa_o_valor_que_chega_vencer() -> None:
    atual = GameRecord.from_mapping(
        _with_provenance("title", ConflictPolicy.PREFER_SOURCE, title="Título antigo e longo")
    )
    novo = GameRecord.from_mapping(_base_record(title="Novo"))
    assert atual.merge(novo).record.title == "Novo"


def test_conflito_manual_preserva_o_valor_e_registra_estado_explicito() -> None:
    atual = GameRecord.from_mapping(
        _with_provenance("title", ConflictPolicy.MANUAL, title="Título humano")
    )
    novo = GameRecord.from_mapping(_base_record(title="Título automático"))
    outcome = atual.merge(novo)
    assert outcome.conflicts == ("title",)
    assert outcome.record.title == "Título humano"
    assert "conflict-manual-title" in outcome.record.warnings


def test_conflito_manual_nao_reivindica_a_proveniencia_da_fonte_recusada() -> None:
    """O valor não mudou; alegar a nova origem falsearia o estado."""
    atual = GameRecord.from_mapping(
        _with_provenance("title", ConflictPolicy.MANUAL, title="Título humano")
    )
    novo = GameRecord.from_mapping(
        _base_record(
            title="Título automático",
            provenance={
                "title": {
                    "source": "scraper",
                    "retrievedAt": "2026-09-09T01:00:00Z",
                    "confidence": 0.9,
                    "conflictPolicy": "preferSource",
                }
            },
        )
    )
    entry = atual.merge(novo).record.provenance_of("title")
    assert entry is not None and entry.source == "esde"


def test_fusao_repetida_e_idempotente() -> None:
    atual = GameRecord.from_mapping(_base_record(description="Uma descrição."))
    novo = GameRecord.from_mapping(_base_record(description="x"))
    uma = atual.merge(novo).record
    duas = uma.merge(novo).record
    assert uma.to_mapping() == duas.to_mapping()


def test_warning_de_conflito_nao_duplica_entre_fusoes() -> None:
    atual = GameRecord.from_mapping(
        _with_provenance("title", ConflictPolicy.MANUAL, title="Título humano")
    )
    novo = GameRecord.from_mapping(_base_record(title="Outro"))
    once = atual.merge(novo).record
    twice = once.merge(novo).record
    assert twice.warnings.count("conflict-manual-title") == 1


def test_proveniencia_com_politica_invalida_e_recusada() -> None:
    record = GameRecord.from_mapping(
        _base_record(
            provenance={
                "title": {
                    "source": "esde",
                    "retrievedAt": "2026-09-09T00:00:00Z",
                    "confidence": 0.5,
                    "conflictPolicy": "keepRichest",
                }
            }
        )
    )
    corrupted = record.to_mapping()
    corrupted["provenance"]["title"]["conflictPolicy"] = "sempreEu"
    with pytest.raises(GameRecordError, match="conflictPolicy"):
        GameRecord.from_mapping(corrupted, validate=False).provenance_of("title")


def test_codigo_de_aviso_respeita_o_alfabeto_do_contrato() -> None:
    """``warnings`` são códigos para máquina, não frase para humano."""
    import re

    for field_name in ("title", "sortTitle", "biosRequirements", "a" * 200):
        assert re.fullmatch(r"^[a-z0-9][a-z0-9-]{1,63}$", conflict_warning(field_name))
    assert conflict_warning("sortTitle") == "conflict-manual-sort-title"
