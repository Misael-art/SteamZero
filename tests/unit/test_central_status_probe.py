# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contratos da sonda do ``/status``: atribuição aritmética e evidência sem acervo.

A sonda é o instrumento que sustenta o "antes/depois" de UX-02. Se a aritmética
de atribuição mentir (somar mediana por chamada como se fosse custo por consulta,
ou subtrair média de p50) o relatório continua parecendo rigoroso e passa a
superestimar ou esconder o que sobra. E se o relatório vazar conteúdo do
catálogo, a evidência publicada deixa de ser só medição.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import central_status_probe as probe  # noqa: E402
from steamzero.adapters import desktop_dashboard as dashboard_module  # noqa: E402
from steamzero.domain.desktop import ExperienceCoordinator  # noqa: E402

#: Rótulos que o relatório precisa conseguir separar; duplicar funde blocos e
#: faz a atribuição somar duas coisas diferentes como se fossem uma.
ALL_LABELS = (
    [label for _path, label in probe.INSTANCE_TARGETS]
    + [label for _name, label in probe.MODULE_TARGETS]
    + [label for _klass, _attr, label in probe.CLASS_TARGETS]
)


def test_target_labels_are_unique_across_the_three_injection_kinds() -> None:
    assert len(set(ALL_LABELS)) == len(ALL_LABELS), "dois blocos compartilhando rótulo"


def test_percentile_refuses_to_invent_a_number_for_an_empty_sample() -> None:
    with pytest.raises(ValueError, match="nenhuma amostra"):
        probe.percentile([], 0.5)


def test_percentile_reads_the_closest_sample_below_and_never_past_the_end() -> None:
    ordered = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert probe.percentile(ordered, 0.5) == 30.0
    # Com amostra pequena o p95 é o maior valor medido, não um valor interpolado:
    # a diferença importa quando a bridge está fria e só há poucas consultas.
    assert probe.percentile(ordered, 0.95) == 50.0
    assert probe.percentile([7.5], 0.95) == 7.5


def test_summarize_keeps_mean_and_median_separate_and_reports_the_real_max() -> None:
    # Cauda longa deliberada: uma consulta fria de 9 s entre quatro de ~1 s.
    latencies = [1000.0, 1000.0, 1000.0, 1000.0, 9000.0]
    sizes = [100, 100, 100, 100, 4000]
    summary = probe.summarize(latencies, sizes)
    assert summary["samples"] == 5
    assert summary["p50Ms"] == 1000.0
    assert summary["meanMs"] == 2600.0
    assert summary["maxMs"] == 9000.0
    # O corpo máximo é o corpo máximo; usar o p50 aqui escondia o payload gordo.
    assert summary["payloadBytesMax"] == 4000
    assert summary["payloadBytesP50"] == 100


@pytest.mark.parametrize(
    ("latencies", "sizes", "expect"),
    [([], [10], "nenhuma amostra de latência"), ([5.0], [], "nenhuma amostra de payload")],
)
def test_summarize_refuses_each_empty_input_separately(
    latencies: list[float], sizes: list[int], expect: str
) -> None:
    with pytest.raises(ValueError, match=expect):
        probe.summarize(latencies, sizes)


def test_block_cost_is_normalised_per_query_not_per_call() -> None:
    """Um bloco que roda N vezes por consulta não pode custar N vezes mais."""
    timers = {
        # componentRow roda uma vez por componente: aqui, 3 por consulta.
        "componentRow": [10.0, 10.0, 10.0, 10.0, 10.0, 10.0],
        "themeState": [500.0, 700.0],
    }
    blocks = probe.block_summaries(timers, samples=2)
    assert blocks["componentRow"]["calls"] == 6
    assert blocks["componentRow"]["perQueryMs"] == 30.0
    assert blocks["themeState"]["perQueryMs"] == 600.0
    assert blocks["componentRow"]["medianPerCallMs"] == 10.0


def test_block_that_never_ran_is_reported_as_unmeasured_not_as_free() -> None:
    blocks = probe.block_summaries({"doctor": []}, samples=3)
    assert blocks["doctor"] == {"medianPerCallMs": None, "maxPerCallMs": None, "calls": 0}
    # Sem chaves inventadas: quem soma trata ausente como zero, quem lê vê null.
    assert "perQueryMs" not in blocks["doctor"]


def _report_payload() -> dict[str, Any]:
    return {
        "ok": True,
        "token": "segredo-do-processo",
        "dashboard": {
            "emulation": {"rows": [{"detail": "/home/fulano/.var/app/com.valvesoftware.Steam"}]},
            "theme": {"name": "aurora"},
        },
    }


def test_report_carries_sizes_and_latencies_but_never_the_payload_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        probe.ui_audit_runner,
        "_repository_context",
        lambda: {"commit": "deadbeef", "branch": "teste", "describe": "teste", "clean": True},
    )
    report = probe.build_report(
        role="teste",
        latencies=[120.0, 180.0],
        sizes=[2048, 4096],
        timers={"themeState": [40.0, 60.0]},
        key_sizes=probe.payload_key_sizes(_report_payload()),
        before=probe.survey(Path("/definitivamente-inexistente")),
        after=probe.survey(Path("/definitivamente-inexistente")),
    )
    serialized = json.dumps(report, ensure_ascii=False)
    assert "segredo-do-processo" not in serialized
    assert "/home/fulano" not in serialized
    assert report["stateSurvey"]["unchanged"] is True


def test_attribution_compares_mean_to_mean_so_the_residual_stays_positive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A soma por bloco é média por consulta: o termo comparável é a média.

    Subtrair do p50 dava resíduo negativo numa bridge fria — o caso exato da
    medição de 2026-09-26, em que o p50 era menor que a média.
    """
    monkeypatch.setattr(
        probe.ui_audit_runner,
        "_repository_context",
        lambda: {"commit": "x", "branch": "x", "describe": "x", "clean": True},
    )
    report = probe.build_report(
        role="teste",
        latencies=[1000.0, 1000.0, 1000.0, 1000.0, 9000.0],
        sizes=[10, 10, 10, 10, 10],
        timers={"themeState": [2000.0, 2000.0, 2000.0, 2000.0, 4000.0]},
        key_sizes={},
        before={},
        after={},
    )
    attributed = report["attribution"]["attributedMsPerQuery"]
    assert attributed == 2400.0
    residual = report["attribution"]["unattributedMsPerQuery"]
    assert residual == round(float(report["status"]["meanMs"]) - attributed, 1)
    assert residual == 200.0
    # A fórmula antiga (p50 menos a média atribuída) daria resíduo negativo:
    # exatamente o artefato observado na medição de 2026-09-26.
    assert float(report["status"]["p50Ms"]) - attributed < 0.0


def test_payload_key_sizes_splits_the_dashboard_envelope_without_losing_total() -> None:
    payload = _report_payload()
    sizes = probe.payload_key_sizes(payload)
    assert set(sizes) == {"ok", "token", "dashboard", "dashboard.emulation", "dashboard.theme"}
    assert sizes["dashboard"] > sizes["dashboard.emulation"] + sizes["dashboard.theme"]
    # Chaves de corpo vêm em bytes, não em conteúdo: nada aqui é lido depois.
    assert all(isinstance(value, int) for value in sizes.values())


def test_payload_key_sizes_tolerates_a_dashboard_that_is_not_a_mapping() -> None:
    assert probe.payload_key_sizes({"dashboard": None}) == {"dashboard": len("null")}


def test_survey_counts_the_tree_and_marks_absence_as_absent(tmp_path: Path) -> None:
    (tmp_path / "a").write_bytes(b"x" * 100)
    nested = tmp_path / "sub" / "deep"
    nested.mkdir(parents=True)
    (nested / "b").write_bytes(b"y" * 40)
    result = probe.survey(tmp_path)
    assert result["present"] == 1
    assert result["files"] == 2
    assert result["dirs"] == 2
    assert result["bytes"] == 140
    assert result["maxMtimeNs"] >= (tmp_path / "a").lstat().st_mtime_ns

    missing = probe.survey(tmp_path / "inausivel")
    assert missing == {"present": 0, "files": 0, "dirs": 0, "bytes": 0, "maxMtimeNs": 0}
    # Ausência não é árvore vazia: as duas situações têm assinaturas distintas.
    empty = tmp_path / "vazia"
    empty.mkdir()
    assert probe.survey(empty)["present"] == 1
    assert probe.survey(empty)["files"] == 0


def test_survey_does_not_follow_links_out_of_the_surveyed_tree(tmp_path: Path) -> None:
    outside = tmp_path / "fora"
    outside.mkdir()
    (outside / "grande.bin").write_bytes(b"z" * 50_000)
    tree = tmp_path / "arvore"
    tree.mkdir()
    os.symlink(outside / "grande.bin", tree / "link.bin")
    os.symlink(outside, tree / "link-dir")
    result = probe.survey(tree)
    assert result["files"] == 1
    # O link conta pelo próprio tamanho de destino, nunca pelo conteúdo de fora.
    assert result["bytes"] == len(str(outside / "grande.bin"))
    assert result["bytes"] < 50_000


def test_surveys_unchanged_notices_a_write_that_changed_nothing_visible() -> None:
    before = {"state": {"present": 1, "files": 3, "dirs": 0, "bytes": 30, "maxMtimeNs": 111}}
    rewritten = json.loads(json.dumps(before))
    rewritten["state"]["maxMtimeNs"] = 222
    assert probe.surveys_unchanged(before, before) is True
    # Escrever de novo sem mudar tamanho nem contagem ainda muda o mtime: é
    # exatamente o sinal de que a "leitura" tocou o acervo do host.
    assert probe.surveys_unchanged(before, rewritten) is False


class _FakeDashboard:
    """Tem um alvo definido na classe e o resto na instância: os dois ramos do restore."""

    def _component_row(self, *_args: Any, **_kwargs: Any) -> str:
        return "de classe"

    def __init__(self) -> None:
        for path in [name for name, _label in probe.INSTANCE_TARGETS]:
            if "." in path:
                owner = path.partition(".")[0]
                setattr(self, owner, _TwoPartOwner(owner))
            elif not hasattr(type(self), path):
                setattr(self, path, _own_target(path))


class _TwoPartOwner:
    def __init__(self, owner: str) -> None:
        self._owner = owner

    def __getattr__(self, name: str) -> Callable[..., str]:
        def method(*_args: Any, **_kwargs: Any) -> str:
            return f"{self._owner}.{name}"

        return method


def _own_target(name: str) -> Callable[..., str]:
    def call(*_args: Any, **_kwargs: Any) -> str:
        return name

    return call


def test_instrumented_covers_every_declared_target_and_labels_them() -> None:
    dashboard = _FakeDashboard()
    timers: dict[str, list[float]] = {}
    with probe.instrumented(dashboard, timers):
        for path, _label in probe.INSTANCE_TARGETS:
            container: Any = dashboard
            attribute = path
            if "." in path:
                attribute, _, method = path.partition(".")
                container = getattr(dashboard, attribute)
                attribute = method
            getattr(container, attribute)()
    assert set(timers) == set(ALL_LABELS)
    for _path, label in probe.INSTANCE_TARGETS:
        assert len(timers[label]) == 1, label
    # Instalado mas não chamado: aparece como bloco sem amostra, e não como
    # bloco medido em zero — a distinção é o que impede o resíduo de mentir.
    assert timers["domainStatus"] == []
    assert timers["uiContracts"] == []


def test_instrumented_restores_both_own_and_inherited_targets() -> None:
    dashboard = _FakeDashboard()
    original_row = dashboard._component_row
    original_state = dashboard.__dict__["_theme_state"]
    original_contracts = dashboard_module.handheld_ui_contracts
    original_coordinator_status = ExperienceCoordinator.status
    timers: dict[str, list[float]] = {}

    with probe.instrumented(dashboard, timers):
        assert "_component_row" in dashboard.__dict__, "a sombra deve existir durante a medição"
        assert dashboard_module.handheld_ui_contracts is not original_contracts
        assert ExperienceCoordinator.__dict__["status"] is not original_coordinator_status
        assert dashboard._component_row() == "de classe"
        assert timers["componentRow"]

    # Herdado da classe: apaga a sombra, não sobrescreve a classe.
    assert "_component_row" not in dashboard.__dict__
    assert dashboard._component_row == original_row
    # Próprio da instância: volta a função original por identidade.
    assert dashboard.__dict__["_theme_state"] is original_state
    assert dashboard_module.handheld_ui_contracts is original_contracts
    assert ExperienceCoordinator.status is original_coordinator_status
    assert dashboard._theme_state() == "_theme_state"


def test_instrumented_restores_even_when_the_measurement_fails() -> None:
    dashboard = _FakeDashboard()
    original = dashboard._doctor_runner
    timers: dict[str, list[float]] = {}
    with pytest.raises(RuntimeError, match="bridge caiu"), probe.instrumented(dashboard, timers):
        raise RuntimeError("bridge caiu")
    assert dashboard.__dict__["_doctor_runner"] is original


def test_instrumented_fails_loudly_when_a_block_is_renamed() -> None:
    """Silenciar um alvo ausente deixaria de atribuir tempo sem dizer nada."""
    dashboard = _FakeDashboard()
    del dashboard.__dict__["_registry_factory"]
    with pytest.raises(AttributeError), probe.instrumented(dashboard, {}):
        pass
