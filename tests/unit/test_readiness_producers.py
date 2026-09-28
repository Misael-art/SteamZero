# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""UX-03 — o que cada produtor de prontidão realmente mede.

Cada teste parte de uma entrada sintética mínima e exige que a saída nomeie a
grandeza, separe obrigatório de opcional e se recuse a produzir percentual onde
não há medição. Os números citados nos comentários são os que o contrato
anterior publicava, medidos em
``docs/09-operations/evidence/2026-09-28-rc01-readiness-semantics/00-preflight-e-mapa-medido.log``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from steamzero.adapters.steam_gameplay import SteamGameplayController
from steamzero.core import transaction
from steamzero.core.state import StateStore
from steamzero.domain.cloud_platforms import CloudPlatformService
from steamzero.domain.emulation_workspace import compute_readiness
from steamzero.domain.gamemode import EFFECTS, GameModeTruth, build_truth
from steamzero.domain.platform_composer import EmulatorFacts, compose_platform
from steamzero.domain.platforms import PlatformRegistry, platform_placeholder
from steamzero.domain.readiness import READINESS_CONTRACT_VERSION

_INSTALLED_EMULATOR = [{"id": "eden", "installState": "installed"}]


def _requirement(status: str, *, required: bool = True) -> dict[str, Any]:
    return {
        "kind": "keys",
        "status": status,
        # O contrato real coloca aqui a **versão exigida**, não um booleano.
        "required": "rev5" if required else None,
        "installed": None,
        "detail": "—",
        "blocksPlay": status == "missing",
    }


def _waived(kind: str = "firmware") -> dict[str, Any]:
    """Linha que o jogo selecionado não exige: ``not-required`` é a única forma
    que o contrato tem de declarar isso, e vale ``required is None``."""
    return {
        "kind": kind,
        "status": "not-required",
        "required": None,
        "installed": None,
        "detail": "O jogo não declara requisito mínimo.",
        "blocksPlay": False,
    }


# --- domain/emulation_workspace.py :: compute_readiness -----------------------


def test_workspace_nao_afirma_pronto_com_key_obrigatoria_faltando() -> None:
    """Antes: ``percent=20`` para a categoria ``missing`` — 20 de quê?"""
    state, label, payload = compute_readiness(
        {"keys": _requirement("missing")}, _INSTALLED_EMULATOR
    )

    assert state == "blocked"
    assert payload["contractVersion"] == READINESS_CONTRACT_VERSION
    measure = payload["measure"]
    assert measure["dimension"] == "required_requirements"
    assert (measure["numerator"], measure["denominator"], measure["percent"]) == (0, 1, 0)
    assert payload["pendingRequired"] == 1
    assert payload["label"] == label
    assert payload["cause"] and payload["nextAction"]


def test_workspace_proporcao_vem_dos_requisitos_e_nao_da_categoria() -> None:
    """Um obrigatório atendido e outro não verificado são 1/2 = 50%.

    O contrato anterior devolvia 35% fixo para qualquer ``unverified``: o número
    era um rótulo colorido, não uma medição.
    """
    state, _label, payload = compute_readiness(
        {"keys": _requirement("ok"), "firmware": _requirement("unverified")},
        _INSTALLED_EMULATOR,
    )

    assert state == "unverified"
    measure = payload["measure"]
    assert (measure["numerator"], measure["denominator"], measure["percent"]) == (1, 2, 50)
    assert measure["counts"] == {
        "satisfied": 1,
        "pending": 0,
        "unverified": 1,
        "notApplicable": 0,
    }
    assert payload["verification"] == "not_performed"


def test_workspace_requisito_nao_exigido_fica_fora_da_proporcao_sem_contar_pendencia() -> None:
    """``not-required`` é como o contrato diz "o jogo não exige isto".

    Não entra no denominador e tampoco é um ajuste recomendado: contá-lo como
    pendência pintaria de amarelo um estado que é simplesmente pronto.
    """
    state, _label, payload = compute_readiness(
        {"keys": _requirement("ok"), "firmware": _waived()}, _INSTALLED_EMULATOR
    )

    assert state == "ready"
    assert payload["verification"] == "verified"
    assert payload["basis"] == "preflight"
    assert payload["pendingRequired"] == 0
    assert payload["pendingOptional"] == 0
    assert payload["measure"]["percent"] == 100
    assert payload["measure"]["counts"]["notApplicable"] == 1
    # Um requisito que o jogo não exige não é impedimento: viraria causa e
    # próxima ação inventados sobre um estado pronto.
    assert payload["cause"] is None
    assert payload["nextAction"] is None


def test_workspace_pendencia_que_nao_barra_o_jogo_e_atencao_e_ajuste_opcional() -> None:
    """``outdated`` exige ação mas não impede a jogatina: os dois baldes convivem.

    Antes isto era 45% — o código da categoria, não uma medição.
    """
    state, _label, payload = compute_readiness(
        {"keys": _requirement("outdated")}, _INSTALLED_EMULATOR
    )

    assert state == "attention"
    assert payload["measure"]["percent"] == 0
    assert payload["pendingRequired"] == 1
    assert payload["pendingOptional"] == 1


def test_workspace_emulador_ausente_e_causa_e_acao_sem_fabricar_percentual() -> None:
    """Antes: ``percent`` 100 (só requisitos obrigatórios contam) com emulador ausente.

    O número continuou legítimo — ele mede requisitos —, mas o estado não pode
    ser ``ready`` e a superfície precisa dizer o que falta e o que fazer.
    """
    state, _label, payload = compute_readiness(
        {"keys": _requirement("ok")}, [{"id": "eden", "installState": "not-installed"}]
    )

    assert state == "blocked"
    assert payload["measure"]["percent"] == 100
    assert payload["measure"]["dimension"] == "required_requirements"
    assert payload["cause"] and payload["nextAction"]
    assert payload["basis"] == "preflight"


def test_workspace_denominador_zero_esconde_o_numero_em_vez_de_dizer_cem() -> None:
    """Sem requisito em vigor algum o contrato anterior dizia ``Pronto`` 100%.

    Ali não há o que medir: o percentual desaparece e o estado continua honesto.
    """
    _state, _label, payload = compute_readiness({"keys": _waived()}, _INSTALLED_EMULATOR)

    measure = payload["measure"]
    assert measure["percent"] is None
    assert measure["absentReason"] == "zero_denominator"
    assert measure["denominator"] == 0
    assert measure["counts"] == {
        "satisfied": 0,
        "pending": 0,
        "unverified": 0,
        "notApplicable": 1,
    }


def test_workspace_emulador_degradado_marca_atencao_com_causa_e_acao() -> None:
    state, _label, payload = compute_readiness(
        {"keys": _requirement("ok")}, [{"id": "eden", "installState": "degraded"}]
    )

    assert state == "attention"
    assert payload["cause"]
    assert payload["nextAction"]
    assert payload["blockers"]


def test_workspace_ausencia_entra_na_proporcao_sem_versao_exigida_declarada() -> None:
    """``required`` é a **versão exigida**, não um booleano de obrigatoriedade.

    No escopo global do host a linha vem com ``required: None`` mesmo para keys
    ausentes: não há título selecionado para citar versão. Só ``not-required``
    retira uma linha do denominador, e a superfície não pode mostrar "nada a
    medir" justamente onde há um impedimento.
    """
    row = {
        "kind": "keys",
        "status": "missing",
        "required": None,
        "installed": None,
        "detail": "Keys ausentes.",
        "blocksPlay": True,
    }
    state, _label, payload = compute_readiness({"keys": row}, _INSTALLED_EMULATOR)

    measure = payload["measure"]
    assert (measure["numerator"], measure["denominator"], measure["percent"]) == (0, 1, 0)
    assert payload["pendingRequired"] == 1
    assert state == "blocked"


def test_workspace_pendencia_bloqueante_nao_e_contada_como_ajuste_opcional() -> None:
    """A mesma linha não pode ser bloqueio e ajuste recomendado ao mesmo tempo.

    ``pendingOptional`` é o subconjunto não bloqueante das pendências em vigor;
    se usasse outro critério, a contagem dupla apareceria na superfície.
    """
    row = {
        "kind": "keys",
        "status": "unverified",
        "required": None,
        "installed": "rev1",
        "detail": "Keys sem projeção validada.",
        "blocksPlay": True,
    }
    _state, _label, payload = compute_readiness({"keys": row}, _INSTALLED_EMULATOR)

    measure = payload["measure"]
    assert (measure["numerator"], measure["denominator"]) == (0, 1)
    assert measure["counts"] == {
        "satisfied": 0,
        "pending": 0,
        "unverified": 1,
        "notApplicable": 0,
    }
    assert payload["pendingRequired"] == 1
    assert payload["pendingOptional"] == 0


def test_workspace_dois_degradados_geram_duas_causas_mas_uma_acao() -> None:
    """A causa é por emulador; a ação é a mesma frase, e repeti-la na lista de
    bloqueios é ruído que a superfície mostra como dois itens idênticos.
    """
    _state, _label, payload = compute_readiness(
        {"keys": _requirement("ok")},
        [
            {"id": "eden", "installState": "degraded", "displayName": "Eden"},
            {"id": "citron", "installState": "degraded", "displayName": "Citron"},
        ],
    )

    assert payload["cause"] == "Eden está degradado."
    assert payload["blockers"] == ["Repare emuladores degradados antes de iniciar jogos."]


# --- domain/cloud_platforms.py ------------------------------------------------


class _FakeShortcuts:
    def __init__(self, published: set[str] | None = None) -> None:
        self.published = published or set()

    def managed_cloud_platform_ids(self) -> set[str]:
        return set(self.published)

    def plan_cloud(self, _platforms: Sequence[Mapping[str, Any]]) -> transaction.Plan:
        raise AssertionError("composição read-only não plana escrita")


def _cloud_rows(*, opener: str | None) -> list[dict[str, Any]]:
    service = CloudPlatformService(
        _FakeShortcuts(),
        which=lambda _command: opener,
        spawn=lambda _argv: None,
    )
    return service.platforms()


def test_cloud_abridor_disponivel_nao_vira_cinquenta_por_cento() -> None:
    """Antes: ``percent=50`` por existir ``xdg-open`` — metade de quê?"""
    row = _cloud_rows(opener="/usr/bin/xdg-open")[0]

    readiness = row["readiness"]
    assert readiness["contractVersion"] == READINESS_CONTRACT_VERSION
    assert readiness["state"] == "attention"
    assert readiness["measure"]["percent"] is None
    assert readiness["measure"]["absentReason"] == "not_measured"
    # Conta, assinatura, catálogo, região e rede continuam não verificados.
    assert readiness["verification"] == "not_performed"
    assert readiness["cause"]
    assert readiness["blockers"]


def test_cloud_sem_abridor_local_e_indisponivel_sem_numero() -> None:
    row = _cloud_rows(opener=None)[0]

    readiness = row["readiness"]
    assert readiness["state"] == "unavailable"
    assert readiness["measure"]["percent"] is None
    assert readiness["nextAction"]


# --- domain/platforms.py :: platform_placeholder ------------------------------


def test_placeholder_planejado_nao_divulga_zero_como_se_for_medicao() -> None:
    """Antes: ``percent=0`` para toda plataforma não composta — parecia medição."""
    registry = PlatformRegistry.bundled()
    payload = platform_placeholder(registry.get("snes"))

    readiness = payload["readiness"]
    assert readiness["state"] == "planned"
    assert readiness["contractVersion"] == READINESS_CONTRACT_VERSION
    assert readiness["measure"]["percent"] is None
    assert readiness["measure"]["absentReason"] == "not_measured"
    assert readiness["verification"] == "not_performed"
    assert readiness["cause"]


# --- domain/platform_composer.py ---------------------------------------------


def _installed(_adapter_id: str) -> EmulatorFacts:
    return EmulatorFacts(
        adapter_id="retroarch",
        display_name="RetroArch",
        icon_asset="../assets/retroarch.svg",
        installable=True,
        installed=True,
        version="abc123",
    )


def _absent(adapter_id: str) -> EmulatorFacts:
    return EmulatorFacts(
        adapter_id=adapter_id,
        display_name="RetroArch",
        icon_asset="../assets/retroarch.svg",
        installable=True,
        installed=False,
    )


def test_composer_launchavel_nao_transforma_booleem_percentual() -> None:
    """Antes: ``percent=100`` quando launchable.

    Launchable é um booleano de preflight, não uma proporção; não há numerador
    nem denominador por trás de 100%.
    """
    registry = PlatformRegistry.bundled()
    payload = compose_platform(
        registry.get("snes"), facts_for=_installed, core_present_for=lambda _core: True
    )

    readiness = payload["readiness"]
    assert payload["launchable"] is True
    assert readiness["state"] == "ready"
    assert readiness["basis"] == "preflight"
    assert readiness["verification"] == "verified"
    assert readiness["measure"]["dimension"] == "launch_preflight"
    assert readiness["measure"]["percent"] is None
    assert readiness["measure"]["absentReason"] == "not_measured"


def test_composer_sem_emulador_instalado_nomeia_falta_e_acao() -> None:
    registry = PlatformRegistry.bundled()
    payload = compose_platform(registry.get("snes"), facts_for=_absent)

    readiness = payload["readiness"]
    assert payload["launchable"] is False
    assert readiness["contractVersion"] == READINESS_CONTRACT_VERSION
    assert readiness["measure"]["percent"] is None
    assert readiness["cause"]
    assert readiness["nextAction"]
    assert readiness["blockers"]


# --- adapters/steam_gameplay.py ----------------------------------------------


class _StubGameModeProbe:
    """Sondagem sintética: o controle de gameplay só consome a verdade."""

    def __init__(self, truth: GameModeTruth) -> None:
        self._truth = truth

    def probe(self) -> GameModeTruth:
        return self._truth


def _gameplay_snapshot(
    tmp_path: Path,
    *,
    installed: Sequence[str] = (),
    gamemode: GameModeTruth | None = None,
) -> dict[str, Any]:
    root = tmp_path / "Steam"
    (root / "steamapps").mkdir(parents=True)
    controller = SteamGameplayController(
        roots=(root,),
        which=lambda name: f"/usr/bin/{name}" if name in installed else None,
        store_factory=lambda: StateStore(tmp_path / "state.db"),
        lsfg_manifests=(),
        vkbasalt_manifests=(),
        vkbasalt_config_root=tmp_path / "vkbasalt",
        gamemode_probe=_StubGameModeProbe(
            gamemode
            or build_truth(
                binary_state="present",
                daemon_state="available",
                authorization_state="authorized",
                activity_state="idle",
                effects=dict.fromkeys(EFFECTS, "applied"),
            )
        ),
    )
    return controller.snapshot({"context": {"deviceKind": "linux"}})


def test_gameplay_pronto_com_opcional_pendente_separa_as_duas_contagens(
    tmp_path: Path,
) -> None:
    """Antes: ``percent=100`` com título ``Pronto com 4 ajuste(s)`` — os ajustes
    contavam opcionais e o percentual, só obrigatórios. As duas coisas continuam
    reais, mas deixam de ser a mesma frase.
    """
    readiness = _gameplay_snapshot(tmp_path, installed=("gamescope",))["readiness"]

    assert readiness["contractVersion"] == READINESS_CONTRACT_VERSION
    assert readiness["state"] == "ready"
    # Preflight de capacidades: nada aqui demonstrou gameplay.
    assert readiness["basis"] == "preflight"
    assert readiness["verification"] == "verified"
    measure = readiness["measure"]
    assert measure["dimension"] == "required_requirements"
    # steam (steamapps presente) + gamescope + gamemode; os 4 opcionais fora.
    assert (measure["numerator"], measure["denominator"], measure["percent"]) == (3, 3, 100)
    assert readiness["pendingRequired"] == 0
    assert readiness["pendingOptional"] == 4


def test_gameplay_obrigatorio_ausente_nao_e_rotulado_pronto(tmp_path: Path) -> None:
    """Antes: 67% com o mesmo título ``Pronto`` — um obrigatório ausente é
    impedimento observado, e a superfície precisa dizer qual e o que fazer."""
    snapshot = _gameplay_snapshot(tmp_path)
    gamescope = next(row for row in snapshot["environment"] if row["id"] == "gamescope")
    readiness = snapshot["readiness"]

    assert gamescope["state"] == "missing"
    assert readiness["state"] == "blocked"
    measure = readiness["measure"]
    assert (measure["numerator"], measure["denominator"], measure["percent"]) == (2, 3, 67)
    assert readiness["pendingRequired"] == 1
    assert readiness["cause"] and "Gamescope" in readiness["cause"]
    assert readiness["nextAction"]
    assert readiness["blockers"]


def test_gameplay_sondagem_falha_e_verificacao_pendente_com_causa_do_dado(
    tmp_path: Path,
) -> None:
    """``unverified`` não é ``missing``: a linha não-observada continua no
    denominador, e causa/ação vêm da própria verdade sondada."""
    failure = GameModeTruth.failure()
    snapshot = _gameplay_snapshot(tmp_path, installed=("gamescope",), gamemode=failure)
    gamemode_row = next(row for row in snapshot["environment"] if row["id"] == "gamemode")
    readiness = snapshot["readiness"]

    assert gamemode_row["state"] == "unknown"
    assert readiness["state"] == "unverified"
    assert readiness["verification"] == "not_performed"
    measure = readiness["measure"]
    assert (measure["numerator"], measure["denominator"], measure["percent"]) == (2, 3, 67)
    assert measure["counts"] == {
        "satisfied": 2,
        "pending": 0,
        "unverified": 1,
        "notApplicable": 4,
    }
    assert readiness["cause"] == gamemode_row["cause"]
    assert readiness["nextAction"] == gamemode_row["remediation"]


# --- adapters/emulation.py :: editorial_platform_index -----------------------


def test_plataforma_editorial_com_jogos_nao_afirma_prontidao_cem_por_cento() -> None:
    """Antes: ``percent=100`` porque existia jogo — o que foi verificado? Nada.

    A contagem de jogos é real e continua visível; o que não existe é proporção
    de prontidão, então o número some e ``basis`` diz de onde veio o estado.
    """
    from steamzero.adapters.emulation import editorial_platform_index

    registry = PlatformRegistry.bundled()
    rows = editorial_platform_index(registry, [{"platform": "snes", "title": "Jogo de teste"}])
    snes = next(row for row in rows if row["id"] == "snes")

    readiness = snes["readiness"]
    assert readiness["contractVersion"] == READINESS_CONTRACT_VERSION
    assert readiness["basis"] == "inventory_existence"
    assert readiness["verification"] == "not_performed"
    assert readiness["state"] == "unverified"
    measure = readiness["measure"]
    assert measure["dimension"] == "game_inventory"
    # Existência de jogo não é proporção: numerador/denominador não existem, e a
    # contagem real continua declarada em ``counts``.
    assert (measure["numerator"], measure["denominator"], measure["percent"]) == (None, None, None)
    assert measure["counts"] == {"inventariados": 1}
    assert measure["absentReason"] == "not_measured"
    assert readiness["cause"]


def test_plataforma_editorial_sem_jogos_nao_recebe_zero_como_medido() -> None:
    from steamzero.adapters.emulation import editorial_platform_index

    registry = PlatformRegistry.bundled()
    rows = editorial_platform_index(registry, [])
    snes = next(row for row in rows if row["id"] == "snes")

    readiness = snes["readiness"]
    assert readiness["state"] == "unverified"
    assert readiness["basis"] == "none"
    assert readiness["measure"]["percent"] is None
    assert readiness["measure"]["counts"] == {"inventariados": 0}
    assert readiness["nextAction"]
