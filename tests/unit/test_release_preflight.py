# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Preflight de promoção: reprova a jornada que quebrou o host na a37.

Nenhum teste aqui toca o host, baixa emulador ou inicia processo. A identidade
do host é fixture; o preflight só confronta.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from release_preflight import (
    BOOT_CHAIN_ENTRY_POINTS,
    REQUIRED_PACKAGE_DIRS,
    Report,
    check_daemon_generation,
    check_entry_points,
    check_identity_coherence,
    check_manifest_assets,
    check_package_layout,
    main,
)

_REPO = Path(__file__).resolve().parents[2]
_A37_COMMIT = "2aaa01d9d8b638b3d8e8c396ffbeed133da50ec2"
_A35_COMMIT = "7a1916e1e711bbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def _identity(version: str, release: str, commit: str) -> dict[str, str]:
    return {"packageVersion": version, "releaseId": release, "sourceCommit": commit}


def _coherent() -> dict[str, object]:
    same = _identity("0.1.0a37", "0.1.0a37-2aaa01d9d8b6", _A37_COMMIT)
    return {"manifest": dict(same), "daemon": dict(same), "doctor": dict(same)}


@pytest.fixture
def package(tmp_path: Path) -> Path:
    root = tmp_path / "steamzero"
    for relative in REQUIRED_PACKAGE_DIRS:
        directory = root / relative
        directory.mkdir(parents=True)
        (directory / "marcador.txt").write_text("conteúdo")
    return root


class TestPackageLayout:
    def test_complete_package_passes(self, package: Path) -> None:
        report = Report()
        check_package_layout(package, report)
        assert report.ok

    @pytest.mark.parametrize("missing", REQUIRED_PACKAGE_DIRS)
    def test_missing_directory_fails(self, package: Path, missing: str) -> None:
        target = package / missing
        for entry in target.iterdir():
            entry.unlink()
        target.rmdir()
        report = Report()
        check_package_layout(package, report)
        assert not report.ok
        assert any(missing in failure for failure in report.failures)

    def test_empty_directory_fails(self, package: Path) -> None:
        """Diretório presente mas vazio instala e só falha na tela do usuário."""
        target = package / "ui" / "assets"
        for entry in target.iterdir():
            entry.unlink()
        report = Report()
        check_package_layout(package, report)
        assert not report.ok
        assert any("vazio" in failure for failure in report.failures)


class TestBootEntryPoints:
    def test_real_pyproject_declares_boot_chain(self) -> None:
        report = Report()
        check_entry_points(_REPO / "pyproject.toml", report)
        assert report.ok, report.failures

    @pytest.mark.parametrize("dropped", BOOT_CHAIN_ENTRY_POINTS)
    def test_missing_entry_point_fails(self, tmp_path: Path, dropped: str) -> None:
        """Foi assim que o boot direto caiu no greeter por dois dias."""
        kept = [f'{name} = "x:y"' for name in BOOT_CHAIN_ENTRY_POINTS if name != dropped]
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("[project.scripts]\n" + "\n".join(kept) + "\n")
        report = Report()
        check_entry_points(pyproject, report)
        assert not report.ok
        assert any(dropped in failure for failure in report.failures)

    def test_absent_pyproject_fails(self, tmp_path: Path) -> None:
        report = Report()
        check_entry_points(tmp_path / "nao-existe.toml", report)
        assert not report.ok


class TestManifestAssets:
    def _manifest(self, package: Path, name: str, declared: str) -> None:
        (package / "platform_manifests" / name).write_text(
            json.dumps({"id": "x", "artworkAsset": declared})
        )

    def test_declared_asset_present_passes(self, package: Path) -> None:
        (package / "ui" / "assets" / "switch.svg").write_text("<svg/>")
        self._manifest(package, "01-x.platform.json", "../assets/switch.svg")
        report = Report()
        check_manifest_assets(package, report)
        assert report.ok

    def test_declared_asset_absent_fails(self, package: Path) -> None:
        """Sintoma direto da a37: manifesto cita ícone que não viajou no wheel."""
        self._manifest(package, "01-x.platform.json", "../assets/fantasma.svg")
        report = Report()
        check_manifest_assets(package, report)
        assert not report.ok
        assert any("fantasma.svg" in failure for failure in report.failures)

    def test_unreadable_manifest_fails(self, package: Path) -> None:
        (package / "platform_manifests" / "quebrado.json").write_text("{nao json")
        report = Report()
        check_manifest_assets(package, report)
        assert not report.ok
        assert any("ilegível" in failure for failure in report.failures)

    def test_real_package_has_no_missing_assets(self) -> None:
        report = Report()
        check_manifest_assets(_REPO / "src" / "steamzero", report)
        assert report.ok, report.failures


class TestIdentityCoherence:
    def test_same_generation_passes(self) -> None:
        report = Report()
        check_identity_coherence(_coherent(), report)
        assert report.ok, report.failures

    def test_a37_scenario_fails(self) -> None:
        """Reprodução literal do incidente: current na a37, daemon na a35."""
        identity = _coherent()
        stale = _identity("0.1.0a35", "0.1.0a35-7a1916e1e711", _A35_COMMIT)
        identity["daemon"] = dict(stale)
        identity["doctor"] = dict(stale)
        report = Report()
        check_identity_coherence(identity, report)
        assert not report.ok
        joined = " ".join(report.failures)
        assert "packageVersion" in joined
        assert "sourceCommit" in joined

    def test_only_daemon_diverges_fails(self) -> None:
        """Doctor pode concordar com o manifesto e o daemon ainda estar velho."""
        identity = _coherent()
        identity["daemon"] = _identity("0.1.0a35", "0.1.0a35-7a1916e1e711", _A35_COMMIT)
        report = Report()
        check_identity_coherence(identity, report)
        assert not report.ok

    def test_absent_identity_fails_closed(self) -> None:
        """Identidade ausente não é identidade compatível."""
        report = Report()
        check_identity_coherence(None, report)
        assert not report.ok

    @pytest.mark.parametrize("side", ["manifest", "daemon", "doctor"])
    def test_missing_side_fails(self, side: str) -> None:
        identity = _coherent()
        del identity[side]
        report = Report()
        check_identity_coherence(identity, report)
        assert not report.ok

    @pytest.mark.parametrize("field_name", ["packageVersion", "releaseId", "sourceCommit"])
    def test_side_without_field_fails(self, field_name: str) -> None:
        """Hoje o runtime não expõe sourceCommit; o preflight torna isso visível."""
        identity = _coherent()
        daemon = identity["daemon"]
        assert isinstance(daemon, dict)
        daemon[field_name] = ""
        report = Report()
        check_identity_coherence(identity, report)
        assert not report.ok
        assert any(field_name in failure for failure in report.failures)


class TestPreviousDaemonAlive:
    def test_alive_previous_daemon_fails(self) -> None:
        identity = _coherent()
        identity["previousDaemonAlive"] = True
        report = Report()
        check_daemon_generation(identity, report)
        assert not report.ok

    def test_absent_flag_passes(self) -> None:
        report = Report()
        check_daemon_generation(_coherent(), report)
        assert report.ok


class TestCommandLine:
    def test_source_tree_passes_without_identity(self) -> None:
        exit_code = main(
            [
                "--package-root",
                str(_REPO / "src" / "steamzero"),
                "--pyproject",
                str(_REPO / "pyproject.toml"),
                "--skip-identity",
            ]
        )
        assert exit_code == 0

    def test_requires_identity_by_default(self) -> None:
        exit_code = main(
            [
                "--package-root",
                str(_REPO / "src" / "steamzero"),
                "--pyproject",
                str(_REPO / "pyproject.toml"),
            ]
        )
        assert exit_code == 1

    def test_divergent_identity_exits_nonzero(self, tmp_path: Path) -> None:
        identity = _coherent()
        identity["daemon"] = _identity("0.1.0a35", "0.1.0a35-7a1916e1e711", _A35_COMMIT)
        path = tmp_path / "identity.json"
        path.write_text(json.dumps(identity))
        exit_code = main(
            [
                "--package-root",
                str(_REPO / "src" / "steamzero"),
                "--pyproject",
                str(_REPO / "pyproject.toml"),
                "--identity",
                str(path),
            ]
        )
        assert exit_code == 1

    def test_coherent_identity_exits_zero(self, tmp_path: Path) -> None:
        path = tmp_path / "identity.json"
        path.write_text(json.dumps(_coherent()))
        exit_code = main(
            [
                "--package-root",
                str(_REPO / "src" / "steamzero"),
                "--pyproject",
                str(_REPO / "pyproject.toml"),
                "--identity",
                str(path),
            ]
        )
        assert exit_code == 0
