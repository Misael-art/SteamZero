# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contrato de prontidão v2 — uma só semântica para todos os produtores.

Um número de prontidão já significou coisas diferentes conforme a superfície:
categoria codificada como percentual, proporção de requisitos obrigatórios,
simples existência de jogos inventariados, ou 100% quando não havia nada a
medir. A regra única de consumo no QML (``percent >= 80``) apagava a diferença.

Este módulo separa as três coisas que estavam colapsadas:

- ``state`` / ``label`` / ``cause`` / ``nextAction`` — o que o usuário entende e
  o que pode fazer em seguida;
- ``measure`` — uma proporção **mensurada**, com numerador, denominador, a
  dimensão nomeada e ``percent`` ausente quando não há denominador ou o dado
  falta;
- ``verification`` / ``basis`` / ``pendingRequired`` / ``pendingOptional`` — se
  aquilo foi verificado, com que evidência (preflight ou gameplay demonstrado) e
  o que ainda falta, distinguindo obrigatório de opcional.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

READINESS_CONTRACT_VERSION = 2

STATES = frozenset(
    {"ready", "attention", "blocked", "unverified", "unavailable", "planned", "degraded"}
)
VERIFICATIONS = frozenset({"verified", "not_performed", "not_applicable", "unknown"})
BASES = frozenset(
    {"preflight", "demonstrated_gameplay", "inventory_existence", "existence_only", "none"}
)
ABSENT_REASONS = frozenset({"zero_denominator", "not_measured", "missing_data", "legacy_contract"})
# Bases que sustentam a alegação "pronto": o lançamento foi checado (preflight) ou
# já houve gameplay demonstrado. ``inventory_existence`` e ``existence_only`` ficam
# de fora de propósito — nelas o que existe é um catálogo ou um abridor, não uma
# verificação, e foi "existe um jogo" que virou 100% antes da UX-03.
READY_BASES = frozenset({"preflight", "demonstrated_gameplay"})
# Dimensões registradas: um produtor precisa dizer *o que* mediu, e uma dimensão
# nova entra por aqui, de propósito, em vez de nascer como um número solto.
DIMENSIONS = frozenset(
    {
        "required_requirements",
        "optional_requirements",
        "game_inventory",
        "launch_preflight",
        "not_measured",
    }
)

# Baldeamento de status compartilhado com os produtores: um produtor que
# reimplementasse esta regra voltaria a produzir números divergentes.
SATISFIED_STATUS = "ok"
PENDING_STATUSES = frozenset({"missing", "outdated", "incomplete"})
# ``not-required`` é a única forma que um produtor de requisito tem de dizer
# "esta linha não está em vigor para o jogo/plataforma selecionada".
NOT_REQUIRED_STATUS = "not-required"


def requirement_in_force(row: Mapping[str, Any]) -> bool:
    """Critério padrão de obrigatoriedade para linhas do contrato de requisito.

    ``required`` aqui é a **versão exigida** (``"rev5"``, ``"18.1.0"``, nomes de
    BIOS), e o escopo global do workspace o preenche como ``None`` mesmo para
    keys e firmware — que a plataforma exige sempre. Confiar na truthiness dele
    deixava toda ausência real fora do denominador, e ``blocksPlay`` não resolve:
    é derivado do status, então uma linha atendida o publica como ``False``.
    Quem não exige declara ``status == "not-required"``.
    """
    return str(row.get("status", "unverified")) != NOT_REQUIRED_STATUS


# Legado: os únicos campos que um payload v1 podia usar. Um dicionário sem nenhum
# deles não é uma prontidão, e adivinhar ("provavelmente 0%") é o que produz o
# problema que este módulo elimina.
_LEGACY_KEYS = frozenset({"percent", "title", "detail", "blockers"})


def _one_of(value: Any, allowed: frozenset[str], field: str) -> str:
    text = str(value)
    if text not in allowed:
        raise ValueError(
            f"readiness: {field} {text!r} fora do contrato (esperado um de {sorted(allowed)})"
        )
    return text


def proportion(
    dimension: str,
    numerator: int | None = None,
    denominator: int | None = None,
    *,
    dimension_label: str | None = None,
    absent_reason: str | None = None,
    counts: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Uma proporção real, ou a razão explícita pela qual não existe número."""
    _one_of(dimension, DIMENSIONS, "dimension")
    if numerator is None or denominator is None:
        if absent_reason is None:
            raise ValueError("readiness: proportion sem numerador/denominador exige absentReason")
        _one_of(absent_reason, ABSENT_REASONS, "absentReason")
        resolved_numerator: int | None = None
        resolved_denominator: int | None = None
        percent: int | None = None
    else:
        resolved_numerator = int(numerator)
        resolved_denominator = int(denominator)
        if resolved_numerator < 0 or resolved_denominator < 0:
            raise ValueError("readiness: proportion não aceita contagem negativa")
        if resolved_numerator > resolved_denominator:
            raise ValueError(
                f"readiness: numerator {resolved_numerator} acima do denominator "
                f"{resolved_denominator}"
            )
        if resolved_denominator == 0:
            if absent_reason is None:
                raise ValueError(
                    "readiness: denominator zero exige absentReason (não vira 100 nem 0)"
                )
            _one_of(absent_reason, ABSENT_REASONS, "absentReason")
            percent = None
        else:
            if absent_reason is not None:
                raise ValueError("readiness: absentReason só acompanha percent ausente")
            percent = round(100 * resolved_numerator / resolved_denominator)
    return {
        "dimension": dimension,
        "dimensionLabel": dimension_label or dimension,
        "numerator": resolved_numerator,
        "denominator": resolved_denominator,
        "percent": percent,
        "absentReason": absent_reason if percent is None else None,
        "counts": dict(counts) if counts is not None else None,
    }


def not_measured(reason: str = "not_measured") -> dict[str, Any]:
    return proportion("not_measured", absent_reason=reason)


def proportion_from_requirements(
    rows: Iterable[Mapping[str, Any]],
    *,
    dimension_label: str = "requisitos obrigatórios atendidos",
    in_force: Callable[[Mapping[str, Any]], bool] = requirement_in_force,
) -> dict[str, Any]:
    """Proporção sobre requisitos **obrigatórios**, com opcionais fora do denominador.

    ``unverified`` não é ``missing``: uma linha não verificada não conta como
    atendida, mas o motivo pelo qual ela falta é outro, e ela continua visível em
    ``counts``.

    A obrigatoriedade é decidida por ``in_force``, e o produtor tem de usar a
    **mesma** função para contar pendências opcionais — se um balde usa
    ``required`` e outro usa ``status``, a mesma linha vira bloqueio e ajuste
    recomendado ao mesmo tempo.
    """
    satisfied = 0
    pending = 0
    unverified = 0
    not_applicable = 0
    for row in rows:
        if not in_force(row):
            not_applicable += 1
            continue
        status = str(row.get("status", "unverified"))
        if status == SATISFIED_STATUS:
            satisfied += 1
        elif status in PENDING_STATUSES:
            pending += 1
        else:
            unverified += 1
    counts = {
        "satisfied": satisfied,
        "pending": pending,
        "unverified": unverified,
        "notApplicable": not_applicable,
    }
    denominator = satisfied + pending + unverified
    if denominator == 0:
        return proportion(
            "required_requirements",
            0,
            0,
            dimension_label=dimension_label,
            absent_reason="zero_denominator",
            counts=counts,
        )
    return proportion(
        "required_requirements",
        satisfied,
        denominator,
        dimension_label=dimension_label,
        counts=counts,
    )


def readiness(
    *,
    state: str,
    label: str,
    cause: str | None = None,
    next_action: str | None = None,
    blockers: Sequence[str] = (),
    verification: str = "unknown",
    basis: str = "none",
    measure: dict[str, Any] | None = None,
    pending_required: int | None = None,
    pending_optional: int | None = None,
) -> dict[str, Any]:
    """Payload de prontidão v2: estado, causa, ação e medição em campos próprios."""
    resolved_state = _one_of(state, STATES, "state")
    resolved_verification = _one_of(verification, VERIFICATIONS, "verification")
    resolved_basis = _one_of(basis, BASES, "basis")
    if pending_required is not None and pending_required < 0:
        raise ValueError("readiness: pendingRequired não aceita contagem negativa")
    if resolved_state == "ready":
        # A alegação mais cara do produto: "pronto" não é produzida por
        # ausência de dado, por categoria otimista nem por percentual alto.
        if pending_required:
            raise ValueError(
                f"readiness: state 'ready' recusado com pendingRequired={pending_required}"
            )
        if resolved_verification != "verified":
            raise ValueError(
                f"readiness: state 'ready' exige verification 'verified', veio "
                f"{resolved_verification!r}"
            )
        if resolved_basis not in READY_BASES:
            raise ValueError(
                f"readiness: state 'ready' exige basis de evidência de verificação "
                f"({sorted(READY_BASES)}), veio {resolved_basis!r}"
            )
    return {
        "contractVersion": READINESS_CONTRACT_VERSION,
        "state": resolved_state,
        "label": str(label),
        "cause": cause,
        "nextAction": next_action,
        "blockers": [str(item) for item in blockers],
        "verification": resolved_verification,
        "basis": resolved_basis,
        "pendingRequired": pending_required,
        "pendingOptional": pending_optional,
        "measure": measure if measure is not None else not_measured(),
    }


def normalize_readiness(
    payload: Mapping[str, Any],
    *,
    state: str | None = None,
) -> dict[str, Any]:
    """Interpreta prontidão de qualquer versão do contrato como v2.

    Payloads sem ``contractVersion`` publicavam um percentual cuja dimensão não
    existia no contrato — não há como recuperá-la. Eles preservam o texto e o
    estado, e o número deixa de ser exibido: ausente é honesto, 0 é uma alegação.
    """
    if not isinstance(payload, Mapping):
        raise ValueError("readiness: payload de prontidão precisa ser um mapeamento")
    if int(payload.get("contractVersion") or 0) >= READINESS_CONTRACT_VERSION:
        return dict(payload)
    if not _LEGACY_KEYS.intersection(payload):
        raise ValueError(
            "readiness: payload sem contractVersion e sem nenhum campo de prontidão "
            "conhecido (percent/title/detail/blockers)"
        )
    resolved_state = str(state) if str(state or "") in STATES else "unverified"
    return {
        "contractVersion": READINESS_CONTRACT_VERSION,
        "state": resolved_state,
        "label": str(payload.get("title") or ""),
        "cause": payload.get("detail"),
        "nextAction": None,
        "blockers": [str(item) for item in payload.get("blockers") or ()],
        "verification": "unknown",
        "basis": "none",
        "pendingRequired": None,
        "pendingOptional": None,
        "measure": not_measured("legacy_contract"),
    }
