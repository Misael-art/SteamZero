#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Gera a matriz de capacidades a partir do CÓDIGO, nunca da documentação.

Existe porque documento escrito à mão envelhece calado. A auditoria de
2026-08-03 encontrou o catálogo de features anunciando store central de BIOS,
sync de saves e migração por UUID — três módulos sem um único consumidor no
produto — enquanto a UI oferecia sob a mesma aparência dezesseis emuladores dos
quais dois estavam instalados.

A matriz aqui é derivada dos manifestos empacotados, do roteamento de lifecycle
e do catálogo de contratos de UI. Ela não sabe opinar: só publica o que o código
declara e o que ele recusa. Nada é lido do host — o resultado é idêntico em
qualquer máquina, o que permite usá-lo como gate.

Uso:
    python tools/capability_matrix.py --write   # regrava o documento
    python tools/capability_matrix.py --check   # reprova se o commit divergiu
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from steamzero.adapters import lifecycle  # noqa: E402
from steamzero.adapters.desktop_contracts import handheld_ui_contracts  # noqa: E402
from steamzero.adapters.registry import AdapterManifest, AdapterRegistry  # noqa: E402
from steamzero.domain.launch_profile import parse_launch  # noqa: E402
from steamzero.domain.platforms import PlatformRegistry  # noqa: E402

OUTPUT = ROOT / "docs" / "01-product" / "CAPABILITY-MATRIX.md"

_HEADER = """<!-- GERADO POR tools/capability_matrix.py — NÃO EDITE À MÃO. -->
<!-- Regrave com: python tools/capability_matrix.py --write -->

# CAPABILITY-MATRIX — o que o código declara, e o que ele recusa

Derivada dos manifestos empacotados, do roteamento de lifecycle e do catálogo de
contratos de UI. **Nada aqui é lido do host**: o documento é idêntico em qualquer
máquina, e o gate `--check` reprova quando o código muda sem regravá-lo.

Esta matriz responde "o produto consegue oferecer isto?", **não** "isto funciona".
Capacidade declarada é promessa do manifesto; execução real exige evidência de
host, que vive nos relatórios de certificação.
"""


def _cell(value: object) -> str:
    """Escapa o separador de coluna para não quebrar a tabela."""
    return str(value).replace("|", "\\|")


def _table(headers: Iterable[str], rows: Iterable[Iterable[object]]) -> str:
    head = list(headers)
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    lines.extend("| " + " | ".join(_cell(cell) for cell in row) + " |" for row in rows)
    return "\n".join(lines)


def _core_providers(
    manifests: Iterable[AdapterManifest], routes: dict[str, lifecycle.LifecycleRoute]
) -> set[str]:
    """Nomes de cores com adapter, hash do binário e executor instalável.

    Um manifesto sem executor ainda é apenas uma intenção. Contá-lo aqui
    liberaria plataformas que o produto não consegue preparar, exatamente o
    tipo de bloqueio falso (ou promessa falsa) que a matriz precisa impedir.
    """
    return {
        manifest.core.id
        for manifest in manifests
        if manifest.kind == "core"
        and manifest.core is not None
        and (route := routes.get(manifest.id)) is not None
        and route.executor == "libretro"
        and route.installable
    }


def _emulator_section(registry: AdapterRegistry) -> tuple[str, dict[str, lifecycle.LifecycleRoute]]:
    rows = []
    routes: dict[str, lifecycle.LifecycleRoute] = {}
    for manifest in registry.list():
        route = lifecycle.route_for(manifest)
        routes[manifest.id] = route
        rows.append(
            (
                manifest.id,
                manifest.kind,
                route.source_type or "—",
                "sim" if route.end_of_life else "não",
                route.executor,
                "sim" if route.installable else "**não**",
                len(manifest.capabilities),
                route.reason or "—",
            )
        )
    table = _table(
        (
            "adapter",
            "kind",
            "fonte",
            "EOL",
            "executor",
            "instalável",
            "capacidades declaradas",
            "motivo da recusa",
        ),
        rows,
    )
    return table, routes


def _platform_section(
    platforms: PlatformRegistry,
    routes: dict[str, lifecycle.LifecycleRoute],
    core_providers: set[str],
) -> tuple[str, list[str], int]:
    rows = []
    cores_needed: set[str] = set()
    blocked = 0
    for platform in platforms.list():
        if platform.kind == "cloud":
            # Cloud é uma família de execução própria: a URL allowlisted é
            # aberta pelo serviço CloudPlatformService, não por um emulador.
            # Contar sua ausência de emulador como bloqueio inventaria uma
            # limitação que o manifesto deliberadamente não declara.
            rows.append((platform.id, "serviço cloud", "browser", "—", "—", "nenhum"))
            continue
        primary = next(
            (item for item in platform.emulators if item.get("role") == "primary"),
            None,
        ) or next(iter(platform.emulators), None)
        if primary is None:
            rows.append((platform.id, "—", "—", "—", "—", "**nenhum emulador declarado**"))
            blocked += 1
            continue
        adapter_id = str(primary["adapterId"])
        route = routes.get(adapter_id)
        # `systems` passou a ser exigido para validar `systemCores`; sem ele a
        # matriz levantava E-API-SCHEMA em atari-classics. Mesmo argumento que
        # o controller e o composer já passam.
        profile = parse_launch(
            platform.id,
            adapter_id,
            primary.get("launch"),
            systems=platform.systems,
        )
        core = profile.core if profile is not None else None
        if core:
            cores_needed.add(core)
        bios = ", ".join(profile.requires_bios) if profile and profile.requires_bios else "—"

        blockers = []
        if route is None or not route.installable:
            blockers.append("emulador não instalável")
        if core and core not in core_providers:
            blockers.append(f"core `{core}` sem instalador")
        if blockers:
            blocked += 1
        rows.append(
            (
                platform.id,
                adapter_id,
                route.executor if route else "—",
                core or "—",
                bios,
                "; ".join(blockers) if blockers else "nenhum",
            )
        )
    table = _table(
        (
            "plataforma",
            "emulador primário",
            "executor",
            "core exigido",
            "BIOS declarada",
            "bloqueio",
        ),
        rows,
    )
    return table, sorted(cores_needed), blocked


def _ui_section() -> tuple[str, int, int]:
    contracts = handheld_ui_contracts()
    actions = contracts["actions"]
    rows = []
    for action in actions:
        if action["applicability"] == "applicable" and action["enabled"]:
            continue
        rows.append(
            (
                action["id"],
                action["endpoint"] or "—",
                action["applicability"],
                action["reason"] or "—",
            )
        )
    table = _table(("ação", "endpoint", "aplicabilidade", "motivo declarado"), rows)
    return table, len(actions), len(rows)


#: Capacidades que um emulador ativo precisa declarar. É o ciclo que o produto
#: implementa ponta a ponta hoje; faltar qualquer uma reprova o gate, porque
#: significaria oferecer um emulador cujo ciclo de vida tem buraco.
MANDATORY_CAPABILITIES = ("detect", "status", "install", "update", "verify", "repair", "uninstall")


def _action_matrix(
    registry: AdapterRegistry, routes: dict[str, lifecycle.LifecycleRoute]
) -> tuple[str, list[str], int, int]:
    """Uma linha por emulador, uma coluna por ação do contrato.

    Devolve (tabela, violações, ativos, com openConfig). Violação é emulador
    ativo sem capacidade obrigatória, sem executor, ou com fonte EOL — o gate
    reprova em qualquer uma.
    """
    rows = []
    violations: list[str] = []
    active = 0
    with_config = 0
    for manifest in registry.list():
        if manifest.kind != "emulator":
            continue
        route = routes[manifest.id]
        retired = bool(manifest.raw.get("retired"))
        caps = manifest.capabilities
        if not retired:
            active += 1
            missing = [name for name in MANDATORY_CAPABILITIES if name not in caps]
            if missing:
                violations.append(f"{manifest.id}: faltam capacidades {missing}")
            if route.executor == "none" or not route.installable:
                violations.append(f"{manifest.id}: sem executor ({route.reason})")
            if route.end_of_life:
                violations.append(f"{manifest.id}: fonte EOL ativa")

        # rollback e recovery são do executor, não do manifesto: os dois
        # executores reais oferecem ambos, e "none" não oferece nenhum.
        has_executor = route.executor in {"engine", "flatpak"}
        # `stop` sinaliza grupo de processo; no Flatpak o runtime é o dono e a
        # resposta honesta é `not-supported`, não um sinal em PID alheio.
        stop = "sim" if route.executor == "engine" else "n/d"
        open_config = "sim" if isinstance(manifest.raw.get("openConfig"), dict) else "**não**"
        if open_config == "sim":
            with_config += 1
        rows.append(
            (
                manifest.id,
                "retired" if retired else "ativo",
                route.executor,
                *("sim" if name in caps else "**não**" for name in MANDATORY_CAPABILITIES),
                "sim" if has_executor else "não",
                stop,
                open_config,
                "sim" if route.end_of_life else "não",
                route.reason or "—",
            )
        )
    table = _table(
        (
            "emulador",
            "suporte",
            "executor",
            *MANDATORY_CAPABILITIES,
            "rollback/recovery",
            "stop",
            "open-config",
            "EOL",
            "motivo da recusa",
        ),
        rows,
    )
    return table, violations, active, with_config


def render() -> str:
    registry = AdapterRegistry.bundled()
    platforms = PlatformRegistry.bundled()
    manifests = registry.list()
    emulators, routes = _emulator_section(registry)
    core_providers = _core_providers(manifests, routes)
    action_table, _violations, active_emulators, with_open_config = _action_matrix(registry, routes)
    platform_table, cores_needed, blocked_platforms = _platform_section(
        platforms, routes, core_providers
    )
    ui_table, total_actions, blocked_actions = _ui_section()

    installable = sum(1 for route in routes.values() if route.installable)

    parts = [
        _HEADER,
        "## Resumo",
        "",
        _table(
            ("dimensão", "valor"),
            (
                ("adapters declarados", len(manifests)),
                ("adapters instaláveis pelo lifecycle", f"{installable} de {len(manifests)}"),
                ("plataformas declaradas", len(platforms.list())),
                ("plataformas com bloqueio", f"{blocked_platforms} de {len(platforms.list())}"),
                ("cores libretro exigidos", len(cores_needed)),
                ("cores libretro com instalador", len(core_providers)),
                ("ações de UI publicadas", total_actions),
                ("ações declaradas indisponíveis", blocked_actions),
            ),
        ),
        "",
        "## Adapters e roteamento de lifecycle",
        "",
        "Capacidade declarada no manifesto não implica execução verificada: a coluna",
        "`instalável` é o que `lifecycle.route_for` aceita **antes** de tentar.",
        "",
        emulators,
        "",
        "## Lifecycle por emulador e por ação",
        "",
        "Uma linha por emulador `kind=emulator`, uma coluna por ação do contrato.",
        "O gate reprova quando um emulador **ativo** não declara capacidade",
        "obrigatória, fica sem executor ou mantém fonte EOL.",
        "",
        action_table,
        "",
        (
            f"**{active_emulators} emuladores ativos** · "
            f"obrigatórias: {', '.join(MANDATORY_CAPABILITIES)} · "
            f"`open-config` declarado em **{with_open_config} de {active_emulators}**."
        ),
        "",
        (
            "`open-config` não é obrigatório ainda porque nenhum manifesto declara o argv:"
            " emuladores não compartilham forma de abrir configuração, e inventar um"
            " produziria botão que abre a coisa errada. A lacuna fica contada aqui até"
            " que o argv de cada upstream seja verificado."
            if with_open_config < active_emulators
            else "`open-config` declarado por todos os emuladores ativos."
        ),
        "",
        "## Plataformas e bloqueios de jogabilidade",
        "",
        platform_table,
        "",
        "## Cores libretro exigidos",
        "",
        (
            f"{len(cores_needed)} cores são exigidos pelos perfis de lançamento e "
            f"{len(core_providers)} têm adapter, hash de conteúdo e executor."
            + (
                " Enquanto esse número for zero, nenhuma plataforma que dependa de core"
                " é jogável pelo produto: o core precisa ser instalado por fora."
                if not core_providers
                else ""
            )
        ),
        "",
        ", ".join(f"`{core}`" for core in cores_needed) or "—",
        "",
        "## Ações de UI declaradas indisponíveis",
        "",
        "A bridge publica estas ações com o motivo, em vez de escondê-las — a UI as",
        "mostra desabilitadas com a causa. Ausência aqui não significa funcionamento",
        "verificado, apenas que o contrato não se declara indisponível.",
        "",
        ui_table,
        "",
    ]
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true", help="regrava o documento")
    group.add_argument("--check", action="store_true", help="reprova se divergir do commit")
    args = parser.parse_args(argv)

    registry = AdapterRegistry.bundled()
    _, violations, _, _ = _action_matrix(registry, lifecycle.routes_for(registry))
    if violations:
        # Reprova antes de gravar: um documento que registra emulador ativo com
        # ciclo incompleto legitimaria o buraco em vez de cobrá-lo.
        print("lifecycle incompleto em emulador ativo:", file=sys.stderr)
        for item in violations:
            print(f"  - {item}", file=sys.stderr)
        return 1

    rendered = render()
    if args.write:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(rendered, encoding="utf-8")
        print(f"matriz de capacidades gravada em {OUTPUT.relative_to(ROOT)}")
        return 0

    if not OUTPUT.is_file():
        print(f"matriz ausente: {OUTPUT.relative_to(ROOT)}; rode --write", file=sys.stderr)
        return 1
    if OUTPUT.read_text(encoding="utf-8") != rendered:
        print(
            f"matriz de capacidades desatualizada: {OUTPUT.relative_to(ROOT)}\n"
            "o código mudou e o documento não; rode --write e revise o diff",
            file=sys.stderr,
        )
        return 1
    print("matriz de capacidades: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
