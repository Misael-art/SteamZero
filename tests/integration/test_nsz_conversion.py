# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""WI-4: integração do ConverterPort NSZ com o núcleo transacional.

Verifica que a conversão NSZ/NSP preserva o original, faz gating de disponibilidade
e falha de forma segura (rollback/recuperável). Usa apenas dumps sintéticos.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from steamzero.adapters.converters import (
    NszConverter,
    SwitchRomConversionService,
    ToolManifest,
    ToolRegistry,
)
from steamzero.core import fs, paths
from steamzero.core.errors import SteamZeroError
from steamzero.domain.convert import ConversionManager


@pytest.fixture
def nsz_tool() -> ToolManifest:
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


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    fs.ensure_state_layout()
    return tmp_path


def _fake_runner(produced: bytes | None) -> Any:
    def runner(argv: Any, _timeout: float) -> int:
        assert argv[0] == "nsz"
        # O nsz escreve a saída no diretório -o usando o stem do arquivo
        # fonte. O adapter depois move para o ``dst`` esperado pelo manager.
        if produced is not None:
            out_dir = Path(argv[3])
            src_path = Path(argv[-1])
            target_format = "nsz" if argv[1] == "-C" else "nsp"
            (out_dir / f"{src_path.stem}.{target_format}").write_bytes(produced)
        return 0 if produced is not None else 1

    return runner


def test_nsp_to_nsz_conversion_preserves_original(env: Path, nsz_tool: ToolManifest) -> None:
    src = env / "dump.nsp"
    src.write_bytes(b"original-nsp-bytes")
    before = fs.hash_file(src)

    registry = ToolRegistry([nsz_tool], which=lambda _tool: "/usr/bin/nsz")
    converter = NszConverter(runner=_fake_runner(b"compressed-nsz"), which=lambda _tool: "/bin/nsz")
    service = SwitchRomConversionService(registry, converter=converter)

    result = service.convert(src, "nsz")

    assert result.dest.exists()
    assert result.dest.suffix == ".nsz"
    assert result.dest.read_bytes() == b"compressed-nsz"
    assert fs.hash_file(src) == before
    assert not any(paths.staging_dir().iterdir())


def test_nsz_to_nsp_conversion_preserves_original(env: Path, nsz_tool: ToolManifest) -> None:
    src = env / "dump.nsz"
    src.write_bytes(b"compressed-nsz-bytes")
    before = fs.hash_file(src)

    registry = ToolRegistry([nsz_tool], which=lambda _tool: "/usr/bin/nsz")
    converter = NszConverter(
        runner=_fake_runner(b"decompressed-nsp"), which=lambda _tool: "/bin/nsz"
    )
    service = SwitchRomConversionService(registry, converter=converter)

    result = service.convert(src, "nsp")

    assert result.dest.exists()
    assert result.dest.suffix == ".nsp"
    assert result.dest.read_bytes() == b"decompressed-nsp"
    assert fs.hash_file(src) == before


def test_conversion_fails_safe_when_tool_returns_error(
    env: Path, nsz_tool: ToolManifest
) -> None:
    src = env / "dump.nsp"
    src.write_bytes(b"original-nsp-bytes")
    before = fs.hash_file(src)

    registry = ToolRegistry([nsz_tool], which=lambda _tool: "/usr/bin/nsz")
    converter = NszConverter(runner=_fake_runner(None), which=lambda _tool: "/bin/nsz")
    service = SwitchRomConversionService(registry, converter=converter)

    with pytest.raises(SteamZeroError) as exc:
        service.convert(src, "nsz")

    assert exc.value.code == "E-CONVERT-FAILED"
    assert fs.hash_file(src) == before
    assert not (paths.roms_dir() / "converted" / "dump.nsz").exists()
    assert not any(paths.staging_dir().iterdir())


def test_conversion_gated_when_tool_missing(env: Path, nsz_tool: ToolManifest) -> None:
    src = env / "dump.nsp"
    src.write_bytes(b"original-nsp-bytes")

    registry = ToolRegistry([nsz_tool], which=lambda _tool: None)
    service = SwitchRomConversionService(registry)

    with pytest.raises(SteamZeroError) as exc:
        service.convert(src, "nsz")

    assert exc.value.code == "E-COMPONENT-DEGRADED"
    assert "não está instalada" in exc.value.detail


def test_conversion_idempotent_and_rejects_collision(
    env: Path, nsz_tool: ToolManifest
) -> None:
    src = env / "dump.nsp"
    src.write_bytes(b"original-nsp-bytes")
    before = fs.hash_file(src)

    registry = ToolRegistry([nsz_tool], which=lambda _tool: "/usr/bin/nsz")
    converter = NszConverter(runner=_fake_runner(b"compressed-nsz"), which=lambda _tool: "/bin/nsz")
    service = SwitchRomConversionService(registry, converter=converter)

    service.convert(src, "nsz")

    # Segunda conversão do mesmo arquivo colide com o destino já existente
    with pytest.raises(SteamZeroError) as exc:
        service.convert(src, "nsz")

    assert exc.value.code == "E-TX-STALE-PLAN"
    assert fs.hash_file(src) == before


def test_conversion_manager_directly_with_nsz_port(env: Path, nsz_tool: ToolManifest) -> None:
    src = env / "dump.nsp"
    src.write_bytes(b"original-nsp-bytes")

    converter = NszConverter(runner=_fake_runner(b"compressed-nsz"), which=lambda _tool: "/bin/nsz")
    result = ConversionManager(converter).convert(src, "nsz", dest_dir=env / "out")

    assert result.dest.exists()
    assert result.dest.read_bytes() == b"compressed-nsz"
