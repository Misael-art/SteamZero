# SPDX-License-Identifier: GPL-3.0-or-later

"""Contrato de prontidão v2 — o que cada número significa, não só como aparece.

Motivo (UX-03, docs/09-operations/AUDIT.md): nove produtores publicavam
``readiness.percent`` com grandezas diferentes entre si — categoria codificada
como número (20/45/35/100), proporção real de requisitos obrigatórios, simples
existência de jogos — e um único consumidor pintava tudo com a mesma regra
``percent >= 80``. O resultado é que 0%, 20%, 35% e 45% eram a mesma cor, e 100%
podia significar "existe um jogo inventariado".

Estes testes pinam o contrato: estado, causa e próxima ação separados de uma
proporção mensurável; percentual ausente quando não há denominador ou quando o
dado falta; "pronto" impossível com requisito obrigatório pendente ou sem base de
evidência declarada; e leitura explícita de payload antigo.
"""

import copy
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from steamzero.domain.readiness import (
    PENDING_STATUSES,
    READINESS_CONTRACT_VERSION,
    SATISFIED_STATUS,
    normalize_readiness,
    proportion,
    proportion_from_requirements,
    readiness,
    requirement_in_force,
)

SCHEMA = "emulation-workspace-v1.schema.json"


@lru_cache(maxsize=4)
def _validator(branch: str) -> Draft202012Validator:
    """Instancia o validador de um ramo de ``$defs`` do schema do workspace.

    ``branch`` escolhe entre ``readiness`` (o ``oneOf`` que a produção valida),
    ``readinessLegacy`` e ``readinessV2`` — os ramos separados servem para provar a
    exclusividade mútua, não só a aceitação.

    Só ``$defs`` e o ``$ref`` da raiz entram no documento: herdar as outras chaves
    do schema faria todo payload ser rejeitado por ``contextLabel`` e companhia, e
    os testes de recusa passariam sem testar recusa alguma. O ``$ref`` resolve
    dentro do próprio documento, então o teste lê a norma que ``contracts.validate``
    aplica na produção — não uma cópia.
    """
    document = json.loads(Path("src/steamzero/schemas", SCHEMA).read_text(encoding="utf-8"))
    assert branch in document["$defs"], (
        f"{SCHEMA} não declara $defs/{branch}: o contrato de prontidão não existe no schema"
    )
    return Draft202012Validator(
        {
            "$schema": document["$schema"],
            "$id": document["$id"],
            "$defs": document["$defs"],
            "$ref": f"#/$defs/{branch}",
        }
    )


def _minimal(**overrides: object) -> dict:
    kwargs: dict = {
        "state": "attention",
        "label": "Falta um passo",
        "cause": "Firmware obrigatório ausente.",
        "next_action": "Importe o firmware exigido pelo jogo.",
        "verification": "verified",
        "basis": "preflight",
    }
    kwargs.update(overrides)
    return readiness(**kwargs)  # type: ignore[arg-type]


def test_builder_declara_versao_e_preserva_a_separacao_de_campos() -> None:
    payload = _minimal()

    assert payload["contractVersion"] == READINESS_CONTRACT_VERSION == 2
    assert payload["state"] == "attention"
    assert payload["label"] == "Falta um passo"
    assert payload["cause"] == "Firmware obrigatório ausente."
    assert payload["nextAction"] == "Importe o firmware exigido pelo jogo."
    assert payload["verification"] == "verified"
    assert payload["basis"] == "preflight"
    # Nada de percentual inventado: sem proporção fornecida, não há número.
    assert payload["measure"]["percent"] is None
    assert payload["measure"]["absentReason"] == "not_measured"


def test_estado_e_verificacao_e_base_validados_em_vez_de_string_quaisquer() -> None:
    with pytest.raises(ValueError, match="state"):
        _minimal(state="pronto-para-jogar")
    with pytest.raises(ValueError, match="verification"):
        _minimal(verification="ok")
    with pytest.raises(ValueError, match="basis"):
        _minimal(basis="achismo")


def test_proporcao_medida_expoe_numerador_denominador_e_percent_juntos() -> None:
    media = proportion(
        "required_requirements", 2, 3, dimension_label="requisitos obrigatórios atendidos"
    )

    assert media["numerator"] == 2
    assert media["denominator"] == 3
    assert media["percent"] == 67
    assert media["absentReason"] is None
    # O número precisa nomear a si mesmo; sem isso ele volta a virar "prontidão".
    assert media["dimension"] == "required_requirements"
    assert media["dimensionLabel"] == "requisitos obrigatórios atendidos"


def test_denominador_zero_produz_percent_ausente_em_vez_de_cem() -> None:
    # Este era o caso mais caro: sem requisito obrigatório declarado, o produtor
    # antigo afirmava 100% (ou "pronto"), ou seja, ausência de medição virava
    # evidência de prontidão.
    media = proportion("required_requirements", 0, 0, absent_reason="zero_denominator")

    assert media["percent"] is None
    assert media["numerator"] == 0
    assert media["denominator"] == 0
    assert media["absentReason"] == "zero_denominator"


def test_denominador_zero_exige_motivo_em_vez_de_silencio() -> None:
    with pytest.raises(ValueError, match="absentReason"):
        proportion("required_requirements", 0, 0)


def test_dado_ausente_produz_percent_ausente_em_vez_de_zero() -> None:
    media = proportion(
        "game_inventory", numerator=None, denominator=None, absent_reason="missing_data"
    )

    assert media["percent"] is None
    assert media["numerator"] is None
    assert media["denominator"] is None
    assert media["absentReason"] == "missing_data"


def test_numerador_maior_que_denominador_e_recusado() -> None:
    with pytest.raises(ValueError, match="numerator"):
        proportion("required_requirements", 4, 3)


def test_proporcao_de_requisitos_separa_obrigatorios_de_opcionais() -> None:
    """O que está em vigor é o que o contrato declara: ``not-required`` isenta.

    ``required`` é a versão exigida (``RequirementCheck.required``), e o escopo
    global do host o preenche como ``None`` para keys e firmware que a plataforma
    exige sempre. Usar a truthiness dele como obrigatoriedade tirava toda
    ausência real do denominador.
    """
    rows = [
        {"required": "rev5", "status": "ok"},
        {"required": "rev5", "status": "missing"},
        {"required": None, "status": "unverified"},
        {"required": None, "status": "not-required"},
        {"required": None, "status": "not-required"},
    ]
    media = proportion_from_requirements(rows)

    assert media["numerator"] == 1  # apenas o atendido conta
    assert media["denominator"] == 3  # os três em vigor, não as cinco linhas
    assert media["percent"] == 33
    assert media["counts"] == {
        "satisfied": 1,
        "pending": 1,  # falta de verdade (missing/outdated)
        "unverified": 1,  # não verificado != ausente
        "notApplicable": 2,  # isentos ficam fora do denominador
    }


def test_criterio_de_vigor_e_unico_e_o_produtor_pode_injetar_o_dele() -> None:
    """Um documentário com obrigatoriedade em booleano injeta o próprio critério.

    É a mesma função que decide a proporção e a contagem de ajustes: se o
    produtor usasse um critério em cada lugar, a linha contaria nos dois baldes.
    """
    assert requirement_in_force({"required": None, "status": "missing"}) is True
    assert requirement_in_force({"required": None, "status": "not-required"}) is False

    ambiente = [{"required": True, "status": "ok"}, {"required": False, "status": "missing"}]
    media = proportion_from_requirements(ambiente, in_force=lambda row: bool(row["required"]))

    assert (media["numerator"], media["denominator"], media["percent"]) == (1, 1, 100)
    assert media["counts"]["notApplicable"] == 1


def test_proporcao_de_requisitos_sem_nenhum_obrigatorio_e_denominador_zero() -> None:
    media = proportion_from_requirements([{"required": None, "status": "not-required"}])

    assert media["percent"] is None
    assert media["denominator"] == 0
    assert media["absentReason"] == "zero_denominator"


def test_baldeamento_de_status_e_do_contrato_e_nao_reimplementado_por_produtor() -> None:
    """Produtores decidem o estado pelas mesmas constantes do baldeamento.

    Se um produtor mantiver sua própria lista de status pendentes, ``incomplete``
    pode contar como atendido na cor e como pendente no percentual — de novo, dois
    números para a mesma linha.
    """
    rows = [{"required": True, "status": status} for status in sorted(PENDING_STATUSES)]
    rows.append({"required": True, "status": SATISFIED_STATUS})
    media = proportion_from_requirements(rows)

    assert media["counts"] == {
        "satisfied": 1,
        "pending": len(PENDING_STATUSES),
        "unverified": 0,
        "notApplicable": 0,
    }
    assert media["percent"] == round(100 / (len(PENDING_STATUSES) + 1))


def test_pronto_com_requisito_obrigatorio_pendente_e_recusado() -> None:
    # Exigência da auditoria: nada de "pronto para jogar" com obrigatório pendente.
    with pytest.raises(ValueError, match="pendingRequired"):
        _minimal(state="ready", verification="verified", basis="preflight", pending_required=1)


def test_pronto_exige_verificacao_realizada() -> None:
    with pytest.raises(ValueError, match="verification"):
        _minimal(state="ready", verification="not_performed", basis="preflight", pending_required=0)


def test_pronto_exige_base_de_evidencia_declarada() -> None:
    # preflight e gameplay demonstrado são coisas diferentes; nenhuma delas é
    # assumida por omissão.
    with pytest.raises(ValueError, match="basis"):
        _minimal(state="ready", verification="verified", basis="none", pending_required=0)


def test_pronto_com_base_de_mera_existencia_e_recusado() -> None:
    """Existir não é evidência de que algo está pronto.

    ``inventory_existence`` (há jogos inventariados) e ``existence_only`` (existe
    um abridor) são bases legítimas para "não verificado" e para "atenção" — e os
    produtores reais usam-nas exatamente assim. O que elas não sustentam é a
    alegação "pronto": foi "existe um jogo nesta plataforma" que virou 100% na
    Emulação, e um contrato que a aceita continua permitindo o número artificial
    que a UX-03 existe para eliminar.
    """
    for basis in ("inventory_existence", "existence_only"):
        with pytest.raises(ValueError, match="basis"):
            _minimal(state="ready", verification="verified", basis=basis, pending_required=0)


def test_bases_de_existencia_continuam_legitimas_para_outros_estados() -> None:
    """A recusa é do "pronto", não do vocabulário.

    Se o contrato rejeitasse a base em si, os produtores honestos (Emulação e
    plataformas de nuvem) teriam de voltar a esconder de onde veio o estado.
    """
    for basis in ("inventory_existence", "existence_only"):
        payload = _minimal(
            state="unverified", verification="not_performed", basis=basis, pending_required=None
        )
        assert payload["basis"] == basis


def test_pronto_legitimo_nao_e_bloqueado_pelo_contrato() -> None:
    payload = _minimal(
        state="ready",
        verification="verified",
        basis="preflight",
        pending_required=0,
        measure=proportion("required_requirements", 3, 3),
    )

    assert payload["state"] == "ready"
    assert payload["measure"]["percent"] == 100
    assert payload["basis"] == "preflight"


def test_blockers_preservados_e_contados_contra_o_estado() -> None:
    payload = _minimal(blockers=["Falta key", "Falta firmware"], pending_required=2)

    assert payload["blockers"] == ["Falta key", "Falta firmware"]
    assert payload["pendingRequired"] == 2
    assert payload["pendingOptional"] is None


def test_normalizar_payload_legido_preserva_texto_mas_esconde_o_percent() -> None:
    legacy = {
        "percent": 85,
        "title": "Pronto com 1 ajuste recomendado",
        "detail": "Hardware compatível · Perfil seguro disponível",
        "blockers": ["Overlay pendente"],
    }
    payload = normalize_readiness(legacy, state="attention")

    assert payload["contractVersion"] == READINESS_CONTRACT_VERSION
    assert payload["state"] == "attention"
    assert payload["label"] == legacy["title"]
    assert payload["cause"] == legacy["detail"]
    assert payload["blockers"] == ["Overlay pendente"]
    # A dimensão de um percentual antigo não é recuperável: mostrá-lo seria
    # reafirmar a ambiguidade que esta fatia elimina.
    assert payload["measure"]["percent"] is None
    assert payload["measure"]["absentReason"] == "legacy_contract"
    assert payload["verification"] == "unknown"
    assert payload["basis"] == "none"


def test_normalizar_e_idempotente_para_payload_v2() -> None:
    payload = _minimal()

    assert normalize_readiness(payload) == payload


def test_normalizar_recusa_payload_malformado_em_vez_de_derivar_zero() -> None:
    with pytest.raises(ValueError, match="readiness"):
        normalize_readiness({"state": "ready"})


# --- o schema compartilhado é a mesma norma, não um texto paralelo -------------

_V2_MEDIDO = readiness(
    state="attention",
    label="Falta um passo",
    cause="Firmware obrigatório ausente.",
    next_action="Importe o firmware exigido pelo jogo.",
    verification="verified",
    basis="preflight",
    measure=proportion("required_requirements", 2, 3),
    pending_required=1,
)


def _errors(branch: str, payload: dict[str, Any]) -> list[str]:
    """Erros de ``#/$defs/<branch>`` como ``caminho/no_payload: mensagem``.

    ``oneOf`` resume as filhas em uma frase de contagem na raiz; o ``context`` traz
    os erros reais de cada ramo. Achatar devolve a ancoragem — sem ela, "recusado"
    não diria qual regra recusou, que é exatamente o problema desta fatia.
    """
    out: list[str] = []
    stack = list(_validator(branch).iter_errors(payload))
    while stack:
        error = stack.pop(0)
        if error.validator in {"oneOf", "anyOf"} and error.context:
            stack.extend(error.context)
            continue
        path = "/".join(str(part) for part in error.absolute_path) or "<raiz>"
        out.append(f"{path}: {error.message}")
    return sorted(out)


def _failures(payload: dict[str, Any]) -> list[str]:
    return _errors("readiness", payload)


def _refuses(payload: dict[str, Any], where: str, because: str) -> None:
    """Recusa não-vácua: a forma válida precisa passar no mesmo validador.

    Sem o controle, um schema que rejeita tudo — como o contrato anterior fazia
    com a forma v2 — seria lido como se recusasse exatamente o caso errado.
    """
    assert _failures(_V2_MEDIDO) == [], "controle v2 não valida; a recusa seria vacuosa"
    failures = _failures(payload)
    assert failures, f"schema aceitou o caso que deveria recusar ({where})"
    assert any(where in item and because in item for item in failures), failures


def test_schema_aceita_a_forma_v2_que_o_builder_produz() -> None:
    assert _failures(_V2_MEDIDO) == []


def test_schema_aceita_v2_sem_numero_com_motivo() -> None:
    payload = readiness(
        state="planned",
        label="Integração planejada",
        cause="A composição ainda não foi verificada neste host.",
        measure=proportion("required_requirements", 0, 0, absent_reason="zero_denominator"),
    )

    assert _failures(payload) == []


def test_schema_continua_aceitando_a_forma_v1_de_cache_e_fixtures() -> None:
    # Cache antigo e fixtures anteriores não podem virar rejeição de contrato;
    # quem lê v1 é ``normalize_readiness``, e o número deixa de aparecer.
    legado = {"percent": 45, "title": "Revisar", "detail": "Core ausente", "blockers": []}
    assert _failures(legado) == []
    assert _failures({"percent": 0}) == []


def test_schema_recusa_pronto_sem_verificacao_realizada() -> None:
    pronto = readiness(
        state="ready",
        label="Pronto",
        verification="verified",
        basis="preflight",
        pending_required=0,
        measure=proportion("required_requirements", 3, 3),
    )
    assert _failures(pronto) == []

    _refuses({**pronto, "verification": "not_performed"}, "verification", "'verified' was expected")
    _refuses({**pronto, "basis": "none"}, "basis", "is not one of")
    _refuses({**pronto, "pendingRequired": 1}, "pendingRequired", "is not one of")


def test_schema_recusa_numero_e_motivo_de_ausencia_juntos() -> None:
    # ``percent`` medido e ``absentReason`` juntos são duas alegações contrárias:
    # ou existe a proporção, ou existe a razão pela qual ela não existe.
    com_numero = copy.deepcopy(_V2_MEDIDO)
    com_numero["measure"]["absentReason"] = "not_measured"
    _refuses(com_numero, "measure/absentReason", "is not of type 'null'")

    denominador_zero = copy.deepcopy(_V2_MEDIDO)
    denominador_zero["measure"].update({"numerator": 0, "denominator": 0, "percent": 100})
    _refuses(denominador_zero, "measure/denominator", "minimum")

    sem_numero_sem_motivo = copy.deepcopy(_V2_MEDIDO)
    sem_numero_sem_motivo["measure"].update({"percent": None, "absentReason": None})
    _refuses(sem_numero_sem_motivo, "measure/absentReason", "is not one of")


def test_schema_recusa_dimensao_e_estado_fora_do_contrato() -> None:
    dimensao = copy.deepcopy(_V2_MEDIDO)
    dimensao["measure"]["dimension"] = "prontidao"
    _refuses(dimensao, "measure/dimension", "is not one of")

    _refuses({**_V2_MEDIDO, "state": "pronto-para-jogar"}, "state", "is not one of")


def test_schema_recusa_campo_nao_documentado() -> None:
    # O contrato cresce por decisão registrada, não por campo solto de produtor.
    _refuses({**_V2_MEDIDO, "score": 0.9}, "<raiz>", "'score' was unexpected")


def test_as_duas_formas_sao_mutuamente_exclusivas() -> None:
    """Nenhum payload casa com as duas normas ao mesmo tempo.

    ``oneOf`` exige exatamente um ramo: se as formas se sobrepusessem, a mesma
    prontidão valeria como v1 ambígua e como v2, e o consumidor voltaria a
    adivinhar o que o número significa — o defeito que esta fatia corrige.
    """
    legado = {"percent": 45, "title": "Revisar", "detail": "Core ausente", "blockers": []}
    assert _errors("readinessLegacy", legado) == []
    assert _errors("readinessV2", legado), "v1 legítima casou com v2"

    assert _errors("readinessV2", _V2_MEDIDO) == []
    assert _errors("readinessLegacy", _V2_MEDIDO), "v2 casou com o ramo legado"

    # Nem a mistura das duas passa: nenhum dos dois ramos a aceita.
    hibrido = {**_V2_MEDIDO, "percent": 45}
    assert _errors("readinessLegacy", hibrido)
    assert _errors("readinessV2", hibrido)
    assert _failures(hibrido), "oneOf aceitou payload que casa com zero ramos"


def test_builder_e_schema_recusam_a_mesma_afirmacao() -> None:
    """A recusa mais cara do produto não depende de quem valida."""
    with pytest.raises(ValueError, match="pendingRequired"):
        readiness(
            state="ready",
            label="Pronto",
            verification="verified",
            basis="preflight",
            pending_required=2,
        )
    _refuses(
        {**_V2_MEDIDO, "state": "ready", "verification": "verified", "basis": "preflight"},
        "pendingRequired",
        "is not one of",
    )
