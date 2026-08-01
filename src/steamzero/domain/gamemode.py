# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Verdade observada do Feral GameMode (G29).

Substitui a prontidão falsa baseada apenas na presença de ``gamemoderun`` por
um modelo com seis dimensões observáveis e efeitos individuais:

- ``binaryState``: presença do cliente ``gamemoderun``;
- ``daemonState``: disponibilidade do daemon ``gamemoded``;
- ``authorizationState``: autorização do usuário no socket do daemon;
- ``capabilityState``: prontidão derivada (missing/degraded/ready/unknown);
- ``activityState``: sessão ativa, ociosa, parcial ou não observável;
- ``effects``: evidência por efeito (governor, split lock, ioprio).

Regras semânticas (docs/KNOWN-GAPS.md GAP-G29): binário sozinho nunca é
``ready``; daemon ausente degrada; autorização negada é visível; falha de
permissão degrada sem bloquear lançamento; idle não é falha; parcial é
``degraded`` com efeitos recusados listados; falha de sondagem é ``unknown``
(nunca falso verde); nenhum estado deriva de journal histórico.

O plano administrativo é declarativo e auditável: explica a condição, lista os
passos pretendidos, exige confirmação humana e nunca executa mutação no host
(``executesHostChanges: false``). É validado contra o schema
``gamemode-admin-plan-v1.schema.json`` antes de ser publicado; payload inválido
vira erro de domínio ``E-STATE-INTEGRITY``, nunca KeyError/TypeError.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jsonschema

from steamzero.api import contracts
from steamzero.core.errors import SteamZeroError
from steamzero.core.ids import new_ulid

ADMIN_PLAN_SCHEMA = "gamemode-admin-plan-v1.schema.json"
PLAN_TTL = timedelta(minutes=15)

EFFECTS = ("governor", "splitLock", "ioprio")
EFFECT_STATES = ("applied", "denied", "unknown")
BINARY_STATES = ("present", "missing", "unknown")
DAEMON_STATES = ("available", "unavailable", "unknown")
AUTH_STATES = ("authorized", "denied", "unknown")
CAPABILITY_STATES = ("ready", "degraded", "missing", "unknown")
ACTIVITY_STATES = ("active", "idle", "partial", "unknown")

# condition -> (rowState, statusLabel, cause, requiresOperator)
_CONDITIONS: dict[str, tuple[str, str, str, bool]] = {
    "missing": (
        "missing",
        "GameMode não instalado",
        "gamemoderun não foi encontrado no PATH.",
        True,
    ),
    "binary-unknown": (
        "unknown",
        "Não foi possível verificar",
        "Não foi possível localizar o binário gamemoderun.",
        True,
    ),
    "daemon-unavailable": (
        "degraded",
        "Daemon indisponível",
        "O daemon gamemoded não está em execução.",
        True,
    ),
    "daemon-unknown": (
        "unknown",
        "Não foi possível verificar",
        "Não foi possível consultar o daemon gamemoded.",
        False,
    ),
    "auth-denied": (
        "degraded",
        "Autorização necessária",
        "O acesso ao socket do daemon foi negado para o usuário atual.",
        True,
    ),
    "auth-unknown": (
        "unknown",
        "Não foi possível verificar",
        "Não foi possível confirmar a autorização do usuário no daemon.",
        False,
    ),
    "partial": (
        "degraded",
        "Otimizações parcialmente aplicadas",
        "Sessão ativa com efeito recusado.",
        False,
    ),
    "active": (
        "ready",
        "Otimizações ativas",
        "Sessão ativa com otimizações aplicadas.",
        False,
    ),
    "idle": (
        "ready",
        "Pronto para otimizações",
        "Nenhum jogo usando GameMode.",
        False,
    ),
    "activity-unknown": (
        "unknown",
        "Não foi possível verificar",
        "Não foi possível observar a sessão de jogo.",
        False,
    ),
    "probe-failed": (
        "unknown",
        "Não foi possível verificar",
        "A verificação da prontidão do GameMode falhou.",
        False,
    ),
}

_STEPS: dict[str, tuple[str, ...]] = {
    "missing": (
        "Instale o pacote Feral GameMode (gamemode) pelo gerenciador de pacotes da distribuição.",
        "Reinicie a sessão de desktop para ativar o PATH atualizado.",
        "Verifique novamente a prontidão do GameMode.",
    ),
    "binary-unknown": (
        "Confirme que o pacote Feral GameMode está instalado.",
        "Confira que os diretórios de binários do sistema estão no PATH da sessão.",
        "Tente verificar novamente a prontidão do GameMode.",
    ),
    "daemon-unavailable": (
        "Inicie o daemon gamemoded (serviço do sistema) ou reinicie-o se estiver travado.",
        "Reinstale o pacote gamemode se o daemon não for encontrado.",
        "Verifique novamente a prontidão do GameMode.",
    ),
    "daemon-unknown": (
        "Tente verificar novamente a prontidão em instantes.",
        "Confirme a instalação do daemon gamemoded.",
    ),
    "auth-denied": (
        "Verifique se o usuário pertence ao grupo com acesso ao socket do daemon "
        "(ajuste administrativo).",
        "Confirme as permissões do socket do daemon em /run/user/<uid>/gamemode.sock.",
        "Tente verificar novamente a prontidão do GameMode.",
    ),
    "auth-unknown": (
        "Tente verificar novamente a prontidão em instantes.",
        "Verifique as permissões do socket do daemon.",
    ),
    "partial": (
        "Verifique por que o efeito foi recusado (governor da CPU ou limite de split lock).",
        "Ajuste a configuração do sistema se quiser aplicar todos os efeitos.",
    ),
    "active": ("Nenhuma ação necessária.",),
    "idle": ("Nenhuma ação necessária.",),
    "activity-unknown": ("Tente verificar novamente a prontidão em instantes.",),
    "probe-failed": ("Tente verificar novamente a prontidão em instantes.",),
}

_ROW_STATES = frozenset({"ready", "degraded", "missing", "unknown"})


def _require(value: str, allowed: frozenset[str], name: str) -> str:
    if value not in allowed:
        raise ValueError(f"{name} inválido: {value!r}")
    return value


@dataclass(frozen=True)
class GameModeTruth:
    """Snapshot imutável e sanitizado da verdade observada do GameMode."""

    binary_state: str
    daemon_state: str
    authorization_state: str
    capability_state: str
    activity_state: str
    effects: dict[str, str]
    condition: str
    cause: str
    remediation: str
    requires_operator: bool

    @property
    def state(self) -> str:
        """Estado da linha (ready/degraded/missing/unknown) consumido pela UI."""
        state = _CONDITIONS[self.condition][0]
        if state not in _ROW_STATES:  # pragma: no cover - invariante interno
            raise ValueError(f"estado de linha inválido: {state!r}")
        return state

    @property
    def status_label(self) -> str:
        return _CONDITIONS[self.condition][1]

    def to_dict(self) -> dict[str, Any]:
        """Forma serializada estável — sem argv, stdout, paths privados ou jogos."""
        return {
            "binaryState": self.binary_state,
            "daemonState": self.daemon_state,
            "authorizationState": self.authorization_state,
            "capabilityState": self.capability_state,
            "activityState": self.activity_state,
            "effects": dict(self.effects),
            "condition": self.condition,
            "state": self.state,
            "statusLabel": self.status_label,
            "cause": self.cause,
            "remediation": self.remediation,
            "requiresOperator": self.requires_operator,
        }

    @classmethod
    def failure(cls) -> GameModeTruth:
        """Verdade de pior caso para sondagem que falhou por completo."""
        return cls(
            binary_state="unknown",
            daemon_state="unknown",
            authorization_state="unknown",
            capability_state="unknown",
            activity_state="unknown",
            effects={key: "unknown" for key in EFFECTS},
            condition="probe-failed",
            cause=_CONDITIONS["probe-failed"][2],
            remediation="; ".join(_STEPS["probe-failed"]),
            requires_operator=False,
        )


def build_truth(
    *,
    binary_state: str,
    daemon_state: str,
    authorization_state: str,
    activity_state: str,
    effects: dict[str, str],
) -> GameModeTruth:
    """Deriva capabilityState, condição, causa e orientação das dimensões.

    A hierarquia de condições garante que nenhum estado inferior mascare uma
    falha superior: binário ausente > daemon > autorização > atividade.
    """
    binary_state = _require(binary_state, frozenset(BINARY_STATES), "binary_state")
    daemon_state = _require(daemon_state, frozenset(DAEMON_STATES), "daemon_state")
    authorization_state = _require(
        authorization_state, frozenset(AUTH_STATES), "authorization_state"
    )
    activity_state = _require(activity_state, frozenset(ACTIVITY_STATES), "activity_state")
    effects = {
        key: _require(str(effects.get(key, "unknown")), frozenset(EFFECT_STATES), key)
        for key in EFFECTS
    }

    if binary_state == "missing":
        capability_state = "missing"
    elif binary_state == "unknown":
        capability_state = "unknown"
    elif daemon_state == "unavailable":
        capability_state = "degraded"
    elif daemon_state == "unknown":
        capability_state = "unknown"
    elif authorization_state == "denied":
        capability_state = "degraded"
    elif authorization_state == "unknown":
        capability_state = "unknown"
    else:
        capability_state = "ready"

    if binary_state == "missing":
        condition = "missing"
    elif binary_state == "unknown":
        condition = "binary-unknown"
    elif daemon_state == "unavailable":
        condition = "daemon-unavailable"
    elif daemon_state == "unknown":
        condition = "daemon-unknown"
    elif authorization_state == "denied":
        condition = "auth-denied"
    elif authorization_state == "unknown":
        condition = "auth-unknown"
    elif activity_state == "partial":
        condition = "partial"
    elif activity_state == "active":
        condition = "active"
    elif activity_state == "idle":
        condition = "idle"
    else:
        condition = "activity-unknown"

    _, _, base_cause, requires_operator = _CONDITIONS[condition]
    if condition == "partial":
        denied = sorted(key for key, value in effects.items() if value == "denied")
        cause = f"Sessão ativa com efeito recusado: {', '.join(denied)}." if denied else base_cause
    else:
        cause = base_cause

    return GameModeTruth(
        binary_state=binary_state,
        daemon_state=daemon_state,
        authorization_state=authorization_state,
        capability_state=capability_state,
        activity_state=activity_state,
        effects=effects,
        condition=condition,
        cause=cause,
        remediation="; ".join(_STEPS[condition]),
        requires_operator=requires_operator,
    )


def render_admin_plan(
    truth: GameModeTruth,
    *,
    plan_id: str,
    confirm_token: str,
    created_at: datetime,
    expires_at: datetime,
) -> dict[str, Any]:
    """Monta o envelope do plano administrativo sem validar (para testes)."""
    steps = list(_STEPS[truth.condition])
    return {
        "schemaVersion": 1,
        "planId": plan_id,
        "confirmToken": confirm_token,
        "adapterId": "gamemode",
        "condition": truth.condition,
        "explanation": truth.cause,
        "remediationSteps": steps,
        "requiresOperator": truth.requires_operator,
        "executesHostChanges": False,
        "rollbackGuarantee": "Nenhuma alteração no host é executada por este plano.",
        "createdAt": created_at.isoformat(),
        "expiresAt": expires_at.isoformat(),
        "preview": "; ".join(steps),
    }


def validate_admin_plan(payload: dict[str, Any]) -> dict[str, Any]:
    """Valida o plano contra o schema antes de publicar; inválido vira erro de domínio."""
    try:
        contracts.validate(payload, ADMIN_PLAN_SCHEMA)
    except jsonschema.ValidationError as exc:
        raise SteamZeroError(
            "E-STATE-INTEGRITY", detail="plano administrativo do GameMode inválido"
        ) from exc
    return payload


def build_admin_plan(truth: GameModeTruth, *, now: datetime | None = None) -> dict[str, Any]:
    """Plano administrativo declarativo, validado e sem aplicação automática."""
    created = now if now is not None else datetime.now(UTC)
    payload = render_admin_plan(
        truth,
        plan_id=new_ulid(),
        confirm_token=secrets.token_urlsafe(9),
        created_at=created,
        expires_at=created + PLAN_TTL,
    )
    return validate_admin_plan(payload)
