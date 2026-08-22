# SPDX-License-Identifier: GPL-3.0-or-later
"""Registro fechado dos métodos JSON-RPC expostos pelo ``steamzero-core``.

O transporte nunca encaminha uma linha de comando arbitrária. Cada método possui
campos conhecidos, limites e uma tradução determinística para o mesmo handler da
CLI. Isso mantém CLI e UI sobre uma única camada de ações sem abrir reflexão ou
execução de shell (SR-19).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# A UI já reserva 1 900 000 ms para instalação governada. O transporte do CLI
# usa o mesmo limite explícito: é suficiente para download + verificação, mas
# não deixa uma thread do daemon travada virar espera infinita para o usuário.
_COMPONENT_APPLY_TIMEOUT = 1900.0


class InvalidParams(ValueError):
    """Parâmetros RPC não correspondem ao schema fechado do método."""


@dataclass(frozen=True)
class Field:
    rpc_name: str
    cli_flag: str
    required: bool = True
    choices: frozenset[str] = frozenset()


@dataclass(frozen=True)
class MethodSpec:
    method: str
    domain: str
    action: str | None
    fields: tuple[Field, ...] = ()
    mutation: bool = False
    timeout: float = 2.0

    def params_to_args(self, params: object) -> list[str]:
        if params is None:
            params = {}
        if not isinstance(params, dict) or not all(isinstance(key, str) for key in params):
            raise InvalidParams("params precisa ser um objeto")
        allowed = {field.rpc_name for field in self.fields} | {"correlationId"}
        unknown = set(params) - allowed
        if unknown:
            raise InvalidParams(f"campos desconhecidos: {', '.join(sorted(unknown))}")
        correlation = params.get("correlationId")
        if correlation is not None:
            _validated_text("correlationId", correlation, maximum=64)
        args: list[str] = []
        for field in self.fields:
            value = params.get(field.rpc_name)
            if value is None:
                if field.required:
                    raise InvalidParams(f"campo obrigatório ausente: {field.rpc_name}")
                continue
            text = _validated_text(field.rpc_name, value)
            if field.choices and text not in field.choices:
                raise InvalidParams(
                    f"valor inválido para {field.rpc_name}: esperado "
                    + ", ".join(sorted(field.choices))
                )
            args.extend((field.cli_flag, text))
        return args

    def args_to_params(self, args: list[str], correlation_id: str) -> dict[str, str]:
        values: dict[str, str] = {}
        fields = {field.cli_flag: field for field in self.fields}
        index = 0
        while index < len(args):
            flag = args[index]
            field = fields.get(flag)
            if field is None or index + 1 >= len(args):
                raise InvalidParams(f"flag não suportada pelo daemon: {flag}")
            if field.rpc_name in values:
                raise InvalidParams(f"flag duplicada: {flag}")
            text = _validated_text(field.rpc_name, args[index + 1])
            if field.choices and text not in field.choices:
                raise InvalidParams(f"valor inválido para {field.rpc_name}")
            values[field.rpc_name] = text
            index += 2
        for field in self.fields:
            if field.required and field.rpc_name not in values:
                raise InvalidParams(f"flag obrigatória ausente: {field.cli_flag}")
        values["correlationId"] = correlation_id
        return values


def _validated_text(name: str, value: object, *, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum or "\x00" in value:
        raise InvalidParams(f"{name} precisa ser texto não vazio com até {maximum} caracteres")
    return value


_ID = Field("id", "--id")
_GAME_ID = Field("gameId", "--game-id")
_PLAN_ID = Field("planId", "--plan-id")
_CONFIRM = Field("confirmToken", "--confirm")
_OPERATION_ID = Field("operationId", "--operation-id")
_LIMIT = Field("limit", "--limit", required=False)
_CURSOR = Field("cursor", "--cursor", required=False)
_STATE = Field("state", "--state", required=False)
_KIND = Field("kind", "--kind", required=False)
_ENTITY = Field("entity", "--entity", required=False)
_PLATFORM_ID = Field("platformId", "--platform")
_PROFILE_ID = Field("profileId", "--profile")
_SCOPE = Field(
    "scope",
    "--scope",
    required=False,
    choices=frozenset({"global", "platform", "game", "device", "mode"}),
)
_SCOPE_ID = Field("scopeId", "--scope-id", required=False)
_ORIENTATION = Field(
    "orientation",
    "--orientation",
    required=False,
    choices=frozenset({"landscape", "portrait-left", "portrait-right"}),
)
_ACTION_JSON = Field("actionJson", "--action-json")
_SPEC_JSON = Field("specJson", "--spec-json")
_TARGET = Field(
    "target",
    "--target",
    required=False,
    choices=frozenset({"srm", "esde"}),
)

METHOD_SPECS: tuple[MethodSpec, ...] = (
    # doctor.run varre o host inteiro; os testes já o invocam com timeout=10.
    MethodSpec("doctor.run", "doctor", None, timeout=30.0),
    MethodSpec("jobs.list", "jobs", "list", (_LIMIT, _CURSOR, _STATE)),
    MethodSpec("operations.list", "operations", "list", (_LIMIT, _CURSOR)),
    MethodSpec("operations.show", "operations", "show", (_OPERATION_ID,)),
    MethodSpec(
        "operations.rollback.plan",
        "operations",
        "rollback-plan",
        (_OPERATION_ID,),
        mutation=True,
    ),
    MethodSpec(
        "operations.rollback.apply",
        "operations",
        "rollback-apply",
        (_PLAN_ID, _CONFIRM),
        mutation=True,
    ),
    MethodSpec("events.page", "events", "page", (_LIMIT, _CURSOR, _KIND, _ENTITY)),
    MethodSpec("state.export", "state", "export"),
    MethodSpec("state.audit", "state", "audit"),
    MethodSpec("state.cleanup.plan", "state", "cleanup-plan", mutation=True),
    MethodSpec(
        "state.cleanup.apply",
        "state",
        "cleanup-apply",
        (_PLAN_ID, _CONFIRM),
        mutation=True,
    ),
    MethodSpec("component.list", "component", "list"),
    MethodSpec("component.status", "component", "status", (_ID,)),
    MethodSpec("component.plan", "component", "plan", (_ID,), mutation=True),
    # Uma operação Flatpak pode baixar e verificar artefatos por minutos. O
    # limite é deliberado, e o planId também identifica a operação persistida:
    # em timeout/desconexão, ``operations list --follow`` mostra o terminal.
    MethodSpec(
        "component.apply",
        "component",
        "apply",
        (_PLAN_ID, _CONFIRM),
        mutation=True,
        timeout=_COMPONENT_APPLY_TIMEOUT,
    ),
    MethodSpec("component.rollback", "component", "rollback", (_OPERATION_ID,), mutation=True),
    MethodSpec("component.recover", "component", "recover", mutation=True),
    MethodSpec("session.environment", "session", "environment"),
    MethodSpec("session.status", "session", "status", (_GAME_ID,)),
    MethodSpec("session.recover", "session", "recover", (_GAME_ID,), mutation=True),
    MethodSpec("playtime.list", "playtime", "list", (_LIMIT, _CURSOR)),
    MethodSpec("playtime.show", "playtime", "show", (_GAME_ID,)),
    MethodSpec("collections.list", "collections", "list"),
    MethodSpec(
        "collections.plan",
        "collections",
        "plan",
        (_ACTION_JSON,),
        mutation=True,
    ),
    MethodSpec(
        "collections.apply",
        "collections",
        "apply",
        (_PLAN_ID, _CONFIRM),
        mutation=True,
    ),
    MethodSpec("health.status", "health", "status"),
    MethodSpec("health.plan", "health", "plan", mutation=True),
    MethodSpec(
        "health.apply",
        "health",
        "apply",
        (_PLAN_ID, _CONFIRM),
        mutation=True,
    ),
    MethodSpec("desktop.status", "desktop", "status"),
    MethodSpec(
        "desktop.plan",
        "desktop",
        "plan",
        (
            Field(
                "profile",
                "--profile",
                required=False,
                choices=frozenset({"auto", "handheld", "dock", "safe"}),
            ),
        ),
        mutation=True,
    ),
    MethodSpec("desktop.apply", "desktop", "apply", (_PLAN_ID, _CONFIRM), mutation=True),
    MethodSpec("desktop.reset", "desktop", "reset", (_PLAN_ID, _CONFIRM), mutation=True),
    MethodSpec("desktop.recover", "desktop", "recover", mutation=True),
    # BUG-01: workspace compõe o estado de emulação inteiro; medido em ~13,3 s
    # no host (13.28/13.32/13.33 s com timeout=60 → ready). O default de 2,0 s
    # expirava e virava E-API-CONTRACT. 30,0 s é o teto verificado do round-trip.
    MethodSpec("emulation.workspace", "emulation", "workspace", timeout=30.0),
    MethodSpec("cloud.list", "cloud", "list"),
    MethodSpec("cloud.launch", "cloud", "launch", (_PLATFORM_ID,), mutation=True),
    MethodSpec("cloud.plan", "cloud", "plan", mutation=True),
    MethodSpec("cloud.apply", "cloud", "apply", (_PLAN_ID, _CONFIRM), mutation=True),
    MethodSpec("hud.presets", "hud", "presets"),
    MethodSpec("controls.profiles", "controls", "profiles", (_PLATFORM_ID,)),
    MethodSpec(
        "controls.plan",
        "controls",
        "plan",
        (_PLATFORM_ID, _PROFILE_ID, _SCOPE, _SCOPE_ID, _ORIENTATION),
        mutation=True,
    ),
    MethodSpec("controls.apply", "controls", "apply", (_PLAN_ID, _CONFIRM), mutation=True),
    MethodSpec(
        "controls.rollback",
        "controls",
        "rollback",
        (_OPERATION_ID,),
        mutation=True,
    ),
    # frontends: a spec viaja como texto JSON fechado (--spec-json); o flag
    # --spec <arquivo> é deliberadamente local — o daemon não recebe paths
    # arbitrários. apply medido em 4-35 ms no lab; 2,0 s default cobre.
    MethodSpec("frontends.status", "frontends", "status"),
    MethodSpec("frontends.plan", "frontends", "plan", (_SPEC_JSON,), mutation=True),
    MethodSpec(
        "frontends.apply",
        "frontends",
        "apply",
        (_PLAN_ID, _CONFIRM, _TARGET),
        mutation=True,
    ),
    MethodSpec("frontends.verify", "frontends", "verify", (_SPEC_JSON,)),
    MethodSpec(
        "frontends.rollback",
        "frontends",
        "rollback",
        (_OPERATION_ID, _TARGET),
        mutation=True,
    ),
)

METHODS = {spec.method: spec for spec in METHOD_SPECS}
CLI_METHODS = {(spec.domain, spec.action): spec for spec in METHOD_SPECS}


def capabilities() -> list[dict[str, Any]]:
    methods = [
        {"method": spec.method, "authorization": "mutate" if spec.mutation else "read"}
        for spec in METHOD_SPECS
    ]
    methods.append(
        {
            "method": "events.subscribe",
            "authorization": "read",
            "transport": "json-rpc-notifications",
        }
    )
    return methods
