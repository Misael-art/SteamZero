# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""WI-4: testes unitários do ConverterPort NSZ, tool-manifest e gating.

Toda conversão é de conteúdo legitimamente fornecido pelo usuário; os testes usam
apenas bytes sintéticos e nunca tocam em keys/firmware/ROMs reais.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from steamzero.adapters.converters import (
    NszConverter,
    SwitchRomConversionService,
    ToolManifest,
    ToolRegistry,
)
from steamzero.core.errors import SteamZeroError
from steamzero.ports import ConversionTimeout


def _verified_registry(manifest: ToolManifest) -> ToolRegistry:
    return ToolRegistry(
        [manifest],
        which=lambda _tool: "/usr/bin/nsz",
        probe=lambda _argv, _timeout: (0, "nsz 4.6.1"),
    )


@pytest.fixture
def nsz_manifest() -> ToolManifest:
    return ToolManifest(
        {
            "schemaVersion": 1,
            "id": "nsz",
            "kind": "converter",
            "conversions": [
                {"from": "nsp", "to": "nsz"},
                {"from": "nsz", "to": "nsp"},
            ],
            "sources": [
                {
                    "type": "pip",
                    "version": "4.6.1",
                    "priority": 1,
                    "ref": "nsz",
                    "sha256": "0" * 64,
                }
            ],
            "smokeTest": ["--version"],
            "license": "MIT",
            "upstream": "https://example.invalid/synthetic-nsz",
        }
    )


# --- ToolManifest -----------------------------------------------------------


def test_tool_manifest_supports_nsp_to_nsz(nsz_manifest: ToolManifest) -> None:
    assert nsz_manifest.supports("nsp", "nsz") is True
    assert nsz_manifest.supports("nsz", "nsp") is True


def test_tool_manifest_rejects_unknown_conversion(nsz_manifest: ToolManifest) -> None:
    assert nsz_manifest.supports("xci", "nsp") is False
    assert nsz_manifest.supports("nsp", "xci") is False


def test_tool_manifest_exposes_smoke_test(nsz_manifest: ToolManifest) -> None:
    assert nsz_manifest.smoke_test == ("--version",)


# --- ToolRegistry -----------------------------------------------------------


def test_registry_returns_tool_when_supported(nsz_manifest: ToolManifest) -> None:
    registry = _verified_registry(nsz_manifest)
    tool = registry.converter_tool("nsp", "nsz")
    assert tool is not None
    assert tool.id == "nsz"


def test_registry_returns_none_when_unsupported(nsz_manifest: ToolManifest) -> None:
    registry = _verified_registry(nsz_manifest)
    assert registry.converter_tool("xci", "nsp") is None


def test_registry_reports_availability_with_reason(nsz_manifest: ToolManifest) -> None:
    registry = ToolRegistry([nsz_manifest], which=lambda _tool: None)
    rows = registry.conversions()
    assert len(rows) == 2
    assert all(row["tool"] == "nsz" for row in rows)
    assert all(row["available"] is False for row in rows)
    assert all("não encontrada" in (row["reason"] or "") for row in rows)


def test_registry_reports_available_when_binary_present(
    nsz_manifest: ToolManifest,
) -> None:
    registry = ToolRegistry(
        [nsz_manifest],
        which=lambda tool: f"/bin/{tool}",
        probe=lambda _argv, _timeout: (0, "nsz 4.6.1"),
    )
    rows = registry.conversions()
    assert all(row["available"] is True for row in rows)
    assert all(row["reason"] is None for row in rows)


def test_registry_rejects_failed_smoke_and_wrong_version(nsz_manifest: ToolManifest) -> None:
    failed = ToolRegistry(
        [nsz_manifest],
        which=lambda _tool: "/bin/nsz",
        probe=lambda _argv, _timeout: (2, "broken"),
    )
    incompatible = ToolRegistry(
        [nsz_manifest],
        which=lambda _tool: "/bin/nsz",
        probe=lambda _argv, _timeout: (0, "nsz 3.0.0"),
    )

    assert failed.status("nsz")["state"] == "degraded"
    assert incompatible.status("nsz")["state"] == "incompatible"
    assert not failed.available("nsz")
    assert not incompatible.available("nsz")


def test_registry_probe_exception_degrades(nsz_manifest: ToolManifest) -> None:
    def broken_probe(_argv: Any, _timeout: float) -> tuple[int, str]:
        raise OSError("probe offline")

    registry = ToolRegistry([nsz_manifest], which=lambda _tool: "/bin/nsz", probe=broken_probe)

    assert registry.status("nsz")["state"] == "unverified"
    assert not registry.available("nsz")


# --- NszConverter -----------------------------------------------------------


def test_nsz_converter_build_argv_for_compress() -> None:
    argv = NszConverter._build_argv(Path("/in/game.nsp"), Path("/out/game.nsz"), "nsz")
    assert argv == ("nsz", "-C", "-o", "/out", "/in/game.nsp")


def test_nsz_converter_build_argv_for_decompress() -> None:
    argv = NszConverter._build_argv(Path("/in/game.nsz"), Path("/out/game.nsp"), "nsp")
    assert argv == ("nsz", "-D", "-o", "/out", "/in/game.nsz")


def test_nsz_converter_rejects_unsupported_conversion(tmp_path: Path) -> None:
    src = tmp_path / "game.xci"
    src.write_bytes(b"fake")
    conv = NszConverter(which=lambda _tool: "/usr/bin/nsz")
    with pytest.raises(SteamZeroError) as exc:
        conv.convert(src, tmp_path / "game.nsp", "nsp")
    assert exc.value.code == "E-API-SCHEMA"
    assert "não suportada" in exc.value.detail


def test_nsz_converter_degrades_when_binary_missing(tmp_path: Path) -> None:
    src = tmp_path / "game.nsp"
    src.write_bytes(b"fake")
    conv = NszConverter(which=lambda _tool: None)
    assert conv.convert(src, tmp_path / "game.nsz", "nsz") is False


def test_nsz_converter_succeeds_with_runner_returning_zero(tmp_path: Path) -> None:
    src = tmp_path / "game.nsp"
    src.write_bytes(b"fake")
    dst = tmp_path / "game.nsz"

    def runner(argv: Any, timeout: float) -> int:
        assert argv[0] == "nsz"
        dst.write_bytes(b"compressed")
        return 0

    conv = NszConverter(runner=runner, which=lambda _tool: "/usr/bin/nsz")
    assert conv.convert(src, dst, "nsz") is True
    assert dst.read_bytes() == b"compressed"


def test_nsz_converter_fails_when_runner_returns_nonzero(tmp_path: Path) -> None:
    src = tmp_path / "game.nsp"
    src.write_bytes(b"fake")
    dst = tmp_path / "game.nsz"

    def runner(_argv: Any, _timeout: float) -> int:
        return 1

    conv = NszConverter(runner=runner, which=lambda _tool: "/usr/bin/nsz")
    assert conv.convert(src, dst, "nsz") is False


def test_nsz_converter_fails_when_destination_is_symlink(tmp_path: Path) -> None:
    src = tmp_path / "game.nsp"
    src.write_bytes(b"fake")
    real = tmp_path / "real.nsz"
    real.write_bytes(b"exists")
    dst = tmp_path / "link.nsz"
    dst.symlink_to(real)

    def runner(_argv: Any, _timeout: float) -> int:
        return 0

    conv = NszConverter(runner=runner, which=lambda _tool: "/usr/bin/nsz")
    assert conv.convert(src, dst, "nsz") is False


def test_nsz_converter_timeout_is_propagated(tmp_path: Path) -> None:
    src = tmp_path / "game.nsp"
    src.write_bytes(b"fake")

    def runner(_argv: Any, _timeout: float) -> int:
        raise ConversionTimeout("estouro")

    conv = NszConverter(runner=runner, which=lambda _tool: "/usr/bin/nsz")
    with pytest.raises(ConversionTimeout):
        conv.convert(src, tmp_path / "game.nsz", "nsz")


def test_nsz_converter_runner_filenotfound_maps_to_error(tmp_path: Path) -> None:
    """Se o gating falhar e a ferramenta sumir entre o check e a execução."""
    src = tmp_path / "game.nsp"
    src.write_bytes(b"fake")

    def runner(_argv: Any, _timeout: float) -> int:
        raise FileNotFoundError("nsz")

    conv = NszConverter(runner=runner, which=lambda _tool: "/usr/bin/nsz")
    with pytest.raises(SteamZeroError) as exc:
        conv.convert(src, tmp_path / "game.nsz", "nsz")
    assert exc.value.code == "E-COMPONENT-DEGRADED"


def test_nsz_converter_reconciles_real_output_name(tmp_path: Path) -> None:
    """nsz nomeia a saída pelo stem da entrada; adapter move para ``dst``."""
    src = tmp_path / "game.nsp"
    src.write_bytes(b"fake")
    dst = tmp_path / "target.nsz"

    def runner(_argv: Any, _timeout: float) -> int:
        (tmp_path / "game.nsz").write_bytes(b"compressed")
        return 0

    conv = NszConverter(runner=runner, which=lambda _tool: "/usr/bin/nsz")
    assert conv.convert(src, dst, "nsz") is True
    assert dst.read_bytes() == b"compressed"
    assert not (tmp_path / "game.nsz").exists()


# --- SwitchRomConversionService (gating) ------------------------------------


def test_service_gates_unsupported_conversion(nsz_manifest: ToolManifest, tmp_path: Path) -> None:
    registry = _verified_registry(nsz_manifest)
    service = SwitchRomConversionService(registry)
    src = tmp_path / "game.xci"
    with pytest.raises(SteamZeroError) as exc:
        service.plan_convert(src, "nsp")
    assert exc.value.code == "E-COMPONENT-DEGRADED"
    assert "nenhuma ferramenta" in exc.value.detail


def test_service_gates_missing_tool(nsz_manifest: ToolManifest, tmp_path: Path) -> None:
    registry = ToolRegistry([nsz_manifest], which=lambda _tool: None)
    service = SwitchRomConversionService(registry)
    src = tmp_path / "game.nsp"
    src.write_bytes(b"fake")
    with pytest.raises(SteamZeroError) as exc:
        service.plan_convert(src, "nsz")
    assert exc.value.code == "E-COMPONENT-DEGRADED"
    assert "não encontrada" in exc.value.detail


def test_service_loads_manifest_from_json(nsz_manifest: ToolManifest, tmp_path: Path) -> None:
    path = tmp_path / "nsz-tool-manifest.json"
    path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "id": "nsz",
                "kind": "converter",
                "conversions": [{"from": "nsp", "to": "nsz"}],
                "sources": [
                    {
                        "type": "pip",
                        "version": "4.6.1",
                        "priority": 1,
                        "ref": "nsz",
                        "sha256": "0" * 64,
                    }
                ],
                "smokeTest": ["--version"],
                "license": "MIT",
                "upstream": "https://example.invalid/synthetic-nsz",
            }
        ),
        encoding="utf-8",
    )
    loaded = ToolManifest.from_path(path)
    assert loaded.id == "nsz"
    assert loaded.supports("nsp", "nsz")
