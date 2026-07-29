# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""GAP-G20 — a CLI reusa a composição do controller, não a sua própria.

O defeito não era argumento faltando. Eram DUAS implementações do mesmo read
model: `EmulationController.snapshot()` compunha a completa — chaves, firmware,
biblioteca, capabilities, `emulator_facts`, `core_present`, mais plataformas de
nuvem e resolução do emulador padrão — e a CLI mantinha uma segunda, parcial,
com apenas `probe`.

Medido no host de certificação, com `prod-*.keys` e 15 jogos em cache:

| | composição parcial | composição do controller |
|---|---|---|
| jogos | **0** | **15** |
| keys | **unverified** | **ok** (rev21) |

Para o usuário, "0 jogos e keys unverified" é indistinguível de "minhas keys
sumiram" — o sintoma relatado na a37.

Acrescentar argumentos à segunda implementação só adiaria a próxima
divergência. Por isso o teste central aqui não verifica argumentos: verifica
que a CLI **não compõe por conta própria**.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
CLI_SOURCE = ROOT / "src" / "steamzero" / "cli" / "main.py"


def _handler() -> ast.FunctionDef:
    tree = ast.parse(CLI_SOURCE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_cmd_emulation_workspace":
            return node
    raise AssertionError("_cmd_emulation_workspace não existe mais")


def _handler_source() -> str:
    return ast.get_source_segment(CLI_SOURCE.read_text(encoding="utf-8"), _handler()) or ""


def _handler_calls() -> set[str]:
    """Nomes efetivamente CHAMADOS no handler.

    Verificar por substring reprovaria o docstring, que cita
    `build_switch_workspace` para explicar o defeito. A primeira versão deste
    teste caiu exatamente nessa armadilha — a mesma que ele existe para impedir.
    """
    names: set[str] = set()
    for node in ast.walk(_handler()):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                names.add(node.func.attr)
    return names


class TestTheCliDoesNotComposeOnItsOwn:
    """O gate que impede a segunda implementação de renascer."""

    def test_the_handler_does_not_call_the_builder_directly(self) -> None:
        """`build_switch_workspace` no handler é a forma exata do defeito.

        Chamá-lo ali significa compor um read model paralelo ao do controller, e
        os dois divergem no primeiro argumento que alguém esquecer.
        """
        assert "build_switch_workspace" not in _handler_calls(), (
            "a CLI voltou a compor o workspace por conta própria; "
            "use EmulationController.snapshot()"
        )

    def test_the_handler_uses_the_controller(self) -> None:
        calls = _handler_calls()
        assert "EmulationController" in calls
        assert "snapshot" in calls

    def test_the_controller_is_closed(self) -> None:
        """Sessão vazada acumula a cada invocação da CLI."""
        source = _handler_source()
        assert "finally" in source
        assert "close" in source


class TestTheComposedWorkspaceCarriesHostState:
    """Prova por comportamento, não por leitura de fonte."""

    @staticmethod
    def _switch(workspace: dict[str, Any]) -> dict[str, Any]:
        return next(item for item in workspace["platforms"] if item.get("id") == "switch")

    def test_the_partial_composition_loses_games_and_keys(self) -> None:
        """Documenta o defeito, para que a correção tenha contra o que ser medida.

        Se esta asserção parar de valer, o `build_switch_workspace` sem
        argumentos passou a compor sozinho — e aí o teste acima perde o sentido.
        """
        from steamzero.domain.emulation_workspace import build_switch_workspace

        partial = build_switch_workspace(probe=lambda _emulator_id: True)
        platform = self._switch(partial)
        assert not platform.get("games"), "sem `games`, a composição parcial não perde nada"
        assert (platform.get("requirements") or {}).get("keys", {}).get("status") == "unverified"

    def test_the_full_composition_carries_games_and_requirements(self) -> None:
        """A composição do controller precisa transportar o estado do host.

        Não afirma um número: afirma que games e requisitos ATRAVESSAM. Fixar
        "15 jogos" amarraria o teste ao disco de uma máquina.
        """
        from steamzero.domain.emulation_workspace import build_switch_workspace

        # Os cinco campos que o schema exige, e não um dicionário aproximado:
        # o workspace valida o próprio contrato antes de retornar. A primeira
        # tentativa copiou os campos do cache do host e reprovou por schema —
        # o cache é a ENTRADA do enriquecimento, não a saída.
        games = [
            {
                "id": "g1",
                "titleId": "0100000000010000",
                "name": "Chrono",
                "state": "ready",
                "statusLabel": "Pronto para jogar",
            }
        ]
        full = build_switch_workspace(
            probe=lambda _emulator_id: True,
            # As SEIS chaves. `_requirement_payload` exige o conjunto completo
            # e, faltando qualquer uma, degrada em silêncio para `unverified` —
            # sem diagnóstico. A primeira versão deste teste passou três chaves
            # e viu `unverified`, exatamente como um produtor incompleto veria.
            keys={
                "kind": "keys",
                "status": "ok",
                "required": None,
                "installed": "rev21",
                "detail": "Keys próprias validadas.",
                "blocksPlay": False,
            },
            firmware={
                "kind": "firmware",
                "status": "ok",
                "required": None,
                "installed": "22.5.0",
                "detail": "Firmware próprio catalogado.",
                "blocksPlay": False,
            },
            games=games,
        )
        platform = self._switch(full)
        assert len(platform.get("games") or []) == 1
        requirements = platform.get("requirements") or {}
        assert requirements.get("keys", {}).get("status") == "ok"
        assert requirements.get("firmware", {}).get("status") == "ok"


class TestEveryStateArgumentIsExercised:
    """Enumera os argumentos que carregam estado do host.

    A revisão do PR #6 pediu explicitamente que `emulator_facts` entrasse no
    escopo. Fixar a lista aqui faz um argumento novo aparecer como falha, em vez
    de silenciosamente ficar de fora — que é como o defeito nasceu.
    """

    #: Parâmetros de `build_switch_workspace` que transportam estado do host.
    #: `selected_scope`/`selected_area` ficam de fora: são seleção de UI.
    STATE_ARGUMENTS = frozenset(
        {
            "catalog",
            "probe",
            "keys",
            "firmware",
            "games",
            "emulator_capabilities",
            "platform_registry",
            "emulator_facts",
            "core_present",
        }
    )

    def test_the_builder_signature_has_not_grown_silently(self) -> None:
        import inspect

        from steamzero.domain.emulation_workspace import build_switch_workspace

        actual = set(inspect.signature(build_switch_workspace).parameters) - {
            "selected_scope",
            "selected_area",
        }
        assert actual == self.STATE_ARGUMENTS, (
            "a assinatura mudou; conferir se o controller passa o argumento novo, "
            f"diferença: {actual ^ self.STATE_ARGUMENTS}"
        )

    @pytest.mark.parametrize(
        "argument", sorted({"keys", "firmware", "games", "emulator_facts", "core_present"})
    )
    def test_the_controller_passes_the_state_argument(self, argument: str) -> None:
        """O controller é a composição autoritativa: ele precisa passar cada um."""
        source = (ROOT / "src" / "steamzero" / "adapters" / "emulation.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        call = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "build_switch_workspace"
        )
        passed = {keyword.arg for keyword in call.keywords}
        assert argument in passed, f"o controller não passa {argument!r}"


class TestAPartialRequirementDegradesSilently:
    """Observação registrada durante o GAP-G20, não corrigida aqui.

    `_requirement_payload` exige seis chaves e, faltando qualquer uma, devolve
    `unverified` **sem diagnóstico**. É defensivo — um requisito parcial não é
    confiável —, mas o silêncio tem a forma exata do defeito da a37: o usuário
    vê "não verificado" e não distingue de "sumiu".

    O teste congela o comportamento atual para que uma mudança futura seja
    deliberada, e nomeia o custo.
    """

    def test_an_incomplete_requirement_becomes_unverified(self) -> None:
        from steamzero.domain.emulation_workspace import build_switch_workspace

        workspace = build_switch_workspace(
            probe=lambda _emulator_id: True,
            keys={"kind": "keys", "status": "ok", "installed": "rev21"},
        )
        platform = next(item for item in workspace["platforms"] if item.get("id") == "switch")
        keys = (platform.get("requirements") or {}).get("keys", {})
        assert keys.get("status") == "unverified"
        assert keys.get("installed") is None, "o valor informado é descartado junto"
