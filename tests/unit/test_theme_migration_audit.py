# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Auditoria executável da migração: fidelidade por área e nomes sem tradutor."""

from __future__ import annotations

from pathlib import Path

import pytest

from steamzero.domain.retrofe_declarations import collect_declarations
from steamzero.domain.retrofe_text_slice import TextSliceCompiler
from steamzero.domain.scene_typing import Category
from steamzero.domain.theme_migration_audit import (
    CORPUS_PROPERTY_COUNT,
    PROPERTY_CATEGORIES,
    CategoryFidelity,
    audit_migration,
    slice_migrated_properties,
)

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "retrofe"


def _fixture(name: str):
    path = FIXTURES / f"{name}.xml"
    return collect_declarations(path.read_text(encoding="utf-8"), file=f"retrofe/{name}.xml")


class TestMigratedScope:
    def test_the_scope_is_derived_from_the_slice_registry(self) -> None:
        assert slice_migrated_properties() == frozenset(TextSliceCompiler._HANDLERS) | frozenset(
            TextSliceCompiler._DEFERRED
        )

    def test_the_text_handlers_are_migrated(self) -> None:
        migrated = slice_migrated_properties()
        for name in (
            "fontColor",
            "selectedFontColor",
            "font",
            "fontSize",
            "alignment",
            "x",
            "y",
            "width",
            "height",
            "value",
            "type",
        ):
            assert name in migrated, name

    def test_untouched_corpus_names_are_not_migrated(self) -> None:
        migrated = slice_migrated_properties()
        for name in ("layer", "src"):
            assert name not in migrated, name

    def test_the_corpus_constant_is_the_gates_constant(self) -> None:
        assert CORPUS_PROPERTY_COUNT == 388


class TestCategoryTable:
    def test_the_table_is_closed_over_the_fixture_names(self) -> None:
        observed: set[str] = set()
        for name in ("vs04_positive", "vs04_negative"):
            for item in _fixture(name).declarations:
                if item.counts_as_source:
                    observed.add(item.property_name)
        unknown = sorted(name for name in observed if name not in PROPERTY_CATEGORIES)
        assert unknown == [], f"nomes sem categoria no relatório: {unknown}"

    def test_type_is_honestly_unknown(self) -> None:
        """`type` é chave de conteúdo (reloadableText), sem análogo no contrato."""
        assert PROPERTY_CATEGORIES["type"] is Category.UNKNOWN
        audit = audit_migration(_fixture("vs04_positive"))
        unknown = next((f for f in audit.by_category if f.category is Category.UNKNOWN), None)
        assert unknown is not None
        assert unknown.declared > 0

    def test_every_entry_names_a_real_retrofe_property(self) -> None:
        observed: set[str] = set()
        for name in ("vs04_positive", "vs04_negative"):
            for item in _fixture(name).declarations:
                if item.counts_as_source:
                    observed.add(item.property_name)
        ghosts = sorted(set(PROPERTY_CATEGORIES) - observed)
        assert ghosts == [], f"entradas sem evidência nas fixtures: {ghosts}"


class TestFixtureAudit:
    @pytest.mark.parametrize(
        ("fixture", "declared", "not_migrated"),
        [("vs04_positive", 65, ()), ("vs04_negative", 73, ("layer", "src"))],
    )
    def test_the_fixture_audit_is_consistent(
        self, fixture: str, declared: int, not_migrated: tuple[str, ...]
    ) -> None:
        declarations = _fixture(fixture)
        audit = audit_migration(declarations)
        assert audit.declared == declarations.source_property_count == declared
        assert audit.not_migrated == not_migrated
        assert audit.migrated == declared - len(not_migrated)
        assert audit.corpus_gate_ok
        assert audit.corpus_total == CORPUS_PROPERTY_COUNT

    def test_categories_sum_to_the_total(self) -> None:
        for name in ("vs04_positive", "vs04_negative"):
            audit = audit_migration(_fixture(name))
            total = sum(item.declared for item in audit.by_category)
            assert total == audit.declared
            migrated = sum(item.migrated for item in audit.by_category)
            assert migrated == audit.migrated

    def test_fidelity_is_per_area_not_aggregated(self) -> None:
        """Fidelidade agregada esconderia que a área de mídia está em zero."""
        audit = audit_migration(_fixture("vs04_negative"))
        media = next(f for f in audit.by_category if f.category is Category.MEDIA)
        assert media.declared >= 1
        assert media.migrated == 0
        assert media.fidelity == 0.0

    def test_the_audit_is_deterministic(self) -> None:
        first = audit_migration(_fixture("vs04_positive"))
        second = audit_migration(_fixture("vs04_positive"))
        assert first == second
        assert first.to_dict() == second.to_dict()

    def test_the_report_is_serializable(self) -> None:
        payload = audit_migration(_fixture("vs04_positive")).to_dict()
        assert payload["sourcePropertyCount"] == 65
        assert payload["corpusPropertyCount"] == 388
        assert payload["corpusGateOk"] is True
        assert "layer" in audit_migration(_fixture("vs04_negative")).to_dict()["notMigrated"]

    def test_the_audit_reports_declared_only(self) -> None:
        """Default, herdado e derivado não são declaração e não entram no relatório."""
        audit = audit_migration(_fixture("vs04_positive"))
        assert audit.declared == 65


class TestAuditUnit:
    def test_an_unknown_name_is_reported_not_swallowed(self) -> None:
        declarations = collect_declarations('<text value="x" animParam="1"/>', file="sintetico.xml")
        audit = audit_migration(declarations)
        assert audit.declared == 2
        assert audit.migrated == 1
        assert audit.not_migrated == ("animParam",)
        unknown = next(f for f in audit.by_category if f.category is Category.UNKNOWN)
        assert unknown.declared == 1
        assert unknown.migrated == 0

    def test_an_empty_set_is_total_and_passes_the_gate(self) -> None:
        declarations = collect_declarations("<menu/>", file="vazio.xml")
        audit = audit_migration(declarations)
        assert audit.declared == 0
        assert audit.migrated == 0
        assert audit.fidelity == 1.0
        assert audit.corpus_gate_ok
        assert audit.by_category == ()

    def test_the_corpus_gate_flips_when_everything_is_migrated(self) -> None:
        """Quando a fatia cobrir o corpus inteiro, o relatório diz que o gate caiu."""
        synthetic = collect_declarations(
            "<text " + " ".join(f'{name}="1"' for name in ("x", "y", "width", "height")) + "/>",
            file="gate.xml",
        )
        audit = audit_migration(synthetic, corpus_total=4)
        assert audit.corpus_gate_ok is False
        assert audit.fidelity == 1.0

    def test_category_fidelity_never_divides_by_zero(self) -> None:
        assert CategoryFidelity(Category.COLOR, declared=0, migrated=0).fidelity == 1.0
        assert CategoryFidelity(Category.LAYOUT, declared=2, migrated=1).fidelity == 0.5

    def test_migrated_names_without_declarations_stay_out_of_the_report(self) -> None:
        declarations = collect_declarations('<text value="x"/>', file="somente-valor.xml")
        audit = audit_migration(declarations)
        assert audit.migrated == 1
        assert audit.not_migrated == ()
