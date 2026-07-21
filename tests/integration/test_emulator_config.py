# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""WI-3: perfis conhecidos bons, diff/preview e aplicação transacional."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from jsonschema import ValidationError

from steamzero.api import contracts
from steamzero.core import fs, state
from steamzero.core.errors import SteamZeroError
from steamzero.domain.emulator_config import (
    EmulatorConfigurator,
    KnownGoodProfileCatalog,
    diff_settings,
    merge_settings,
    render_ini,
)


def _catalog() -> KnownGoodProfileCatalog:
    return KnownGoodProfileCatalog(
        {
            "schemaVersion": 1,
            "platform": "switch",
            "entries": [
                {
                    "titleId": "0100000000010000",
                    "label": "generic",
                    "settings": {"Renderer": {"resolution_scale": 2, "async_shaders": True}},
                },
                {
                    "titleId": "0100000000010000",
                    "emulator": "eden",
                    "label": "eden-specific",
                    "settings": {"Renderer": {"resolution_scale": 3}},
                },
            ],
        }
    )


@pytest.fixture
def root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    fs.ensure_state_layout()
    opened = state.open_state()
    yield tmp_path / "cfg"
    opened.close()


def test_empty_catalog_is_valid_and_returns_none() -> None:
    catalog = KnownGoodProfileCatalog.empty("switch")
    assert catalog.lookup("0100000000010000") is None


def test_schema_rejects_bad_title_id() -> None:
    with pytest.raises(ValidationError):
        contracts.validate(
            {
                "schemaVersion": 1,
                "platform": "switch",
                "entries": [{"titleId": "XYZ", "settings": {"a": {"b": 1}}}],
            },
            "known-good-profile-v1.schema.json",
        )


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("Renderer\n[Injected]", "safe", "value"),
        ("Renderer", "vsync\nowned", "value"),
        ("Renderer", "safe", "value\nowned=true"),
        ("Renderer]", "safe", "value"),
        ("Renderer", "safe=owned", "value"),
        ("Renderer", "safe", "value=owned"),
        ("Renderer", "safe", "value]owned"),
    ],
)
def test_schema_and_renderer_reject_ini_injection(section: str, key: str, value: str) -> None:
    payload = {
        "schemaVersion": 1,
        "platform": "switch",
        "entries": [
            {
                "titleId": "0100000000010000",
                "settings": {section: {key: value}},
            }
        ],
    }
    with pytest.raises(ValidationError):
        contracts.validate(payload, "known-good-profile-v1.schema.json")
    with pytest.raises(SteamZeroError) as exc:
        render_ini({section: {key: value}})
    assert exc.value.code == "E-API-SCHEMA"


def test_lookup_prefers_emulator_specific_over_generic() -> None:
    catalog = _catalog()
    generic = catalog.lookup("0100000000010000")
    assert generic["Renderer"]["resolution_scale"] == 2
    specific = catalog.lookup("0100000000010000", emulator="eden")
    assert specific["Renderer"]["resolution_scale"] == 3


def test_lookup_is_case_insensitive_on_title_id() -> None:
    assert _catalog().lookup("0100000000010000".lower()) is not None


def test_diff_reports_added_changed_unchanged() -> None:
    current = {"Renderer": {"resolution_scale": 1, "vsync": True}}
    desired = {"Renderer": {"resolution_scale": 2, "vsync": True, "async_shaders": True}}
    diff = diff_settings(current, desired)
    assert diff.changed["Renderer"]["resolution_scale"] == (1, 2)
    assert diff.added["Renderer"]["async_shaders"] is True
    assert diff.unchanged == 1
    assert not diff.is_empty


def test_render_ini_is_deterministic_and_sorted() -> None:
    settings = {"B": {"z": 1, "a": True}, "A": {"k": "v"}}
    rendered = render_ini(settings).decode()
    assert rendered == "[A]\nk=v\n\n[B]\na=true\nz=1\n"


def test_merge_preserves_untouched_keys() -> None:
    merged = merge_settings({"Core": {"cpu": "auto"}}, {"Renderer": {"scale": 2}})
    assert merged["Core"]["cpu"] == "auto"
    assert merged["Renderer"]["scale"] == 2


def test_preview_without_profile_reports_no_change() -> None:
    cfg = EmulatorConfigurator(KnownGoodProfileCatalog.empty("switch"))
    diff = cfg.preview("0100000000010000", {"Core": {"cpu": "auto"}})
    assert diff.is_empty


def test_plan_apply_writes_merged_config_with_rollback(root: Path) -> None:
    cfg = EmulatorConfigurator(_catalog())
    root.mkdir()
    config_path = root / "eden.ini"
    config_path.write_bytes(render_ini({"Core": {"cpu": "auto"}}))
    plan = cfg.plan_apply(
        "0100000000010000",
        {"Core": {"cpu": "auto"}},
        config_path=config_path,
        root=root,
        emulator="eden",
    )
    applied = cfg.apply(plan.plan_id, plan.confirm_token)
    written = config_path.read_text()
    assert "resolution_scale=3" in written
    assert "cpu=auto" in written  # chave não tocada preservada
    cfg.rollback(applied.operation_id)
    assert "resolution_scale=3" not in config_path.read_text()


def test_plan_apply_without_profile_is_degraded(root: Path) -> None:
    cfg = EmulatorConfigurator(KnownGoodProfileCatalog.empty("switch"))
    root.mkdir()
    with pytest.raises(SteamZeroError) as exc:
        cfg.plan_apply("0100000000010000", {"Core": {}}, config_path=root / "x.ini", root=root)
    assert exc.value.code == "E-COMPONENT-DEGRADED"


def test_plan_apply_rejects_config_path_outside_root(root: Path, tmp_path: Path) -> None:
    cfg = EmulatorConfigurator(_catalog())
    root.mkdir()
    with pytest.raises((SteamZeroError, ValueError)):
        cfg.plan_apply(
            "0100000000010000",
            {"Core": {"cpu": "auto"}},
            config_path=tmp_path / "outside.ini",
            root=root,
        )
