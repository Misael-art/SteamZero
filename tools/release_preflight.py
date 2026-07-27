#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Preflight de promoção — read-only, não toca o host.

Existe por causa da a37: a release foi promovida, os quatro gates estavam
verdes, e ainda assim o host ficou com ``current`` apontando para a a37 enquanto
o daemon seguia executando a a35. Gate de teste não enxerga isso; este preflight
enxerga.

Nada aqui muta estado, baixa emulador, inicia processo ou fala com systemd. Os
dados de identidade do host chegam como argumento, coletados por quem tem
autorização; o preflight apenas confronta.

Uso:

    python3 tools/release_preflight.py --package-root src/steamzero
    python3 tools/release_preflight.py --package-root ... --identity identity.json

O arquivo de identidade, quando fornecido, tem o formato::

    {"manifest": {...}, "daemon": {...}, "doctor": {...}}

com cada objeto expondo ``packageVersion``, ``releaseId`` e ``sourceCommit``.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

# Entry points sem os quais o boot direto cai no greeter (incidente 2026-07-19).
BOOT_CHAIN_ENTRY_POINTS = (
    "steamzero-gamemode-boot",
    "steamzero-gamemode-session",
    "steamos-session-select",
)

# Diretórios de dados que precisam viajar dentro do pacote. Um wheel sem estes
# instala, importa e só falha quando o usuário abre a tela correspondente.
REQUIRED_PACKAGE_DIRS = (
    "schemas",
    "platform_manifests",
    "adapters/manifests",
    "ui/assets",
    "ui/qml",
    "themes",
)

IDENTITY_FIELDS = ("packageVersion", "releaseId", "sourceCommit")


@dataclass
class Report:
    failures: list[str] = field(default_factory=list)
    checks: int = 0

    def check(self, condition: bool, message: str) -> None:
        self.checks += 1
        if not condition:
            self.failures.append(message)

    @property
    def ok(self) -> bool:
        return not self.failures


def check_package_layout(package_root: Path, report: Report) -> None:
    """Todo diretório de dados exigido em runtime está presente e não vazio."""
    for relative in REQUIRED_PACKAGE_DIRS:
        directory = package_root / relative
        report.check(directory.is_dir(), f"diretório ausente no pacote: {relative}")
        if directory.is_dir():
            report.check(
                any(directory.iterdir()),
                f"diretório empacotado está vazio: {relative}",
            )


def check_entry_points(pyproject: Path, report: Report) -> None:
    """Os entry points de boot direto continuam declarados."""
    if not pyproject.is_file():
        report.check(False, f"pyproject.toml não encontrado em {pyproject}")
        return
    text = pyproject.read_text(encoding="utf-8")
    for name in BOOT_CHAIN_ENTRY_POINTS:
        report.check(
            f"{name} =" in text,
            f"entry point de boot direto não declarado: {name}",
        )


def check_manifest_assets(package_root: Path, report: Report) -> None:
    """Todo asset citado por manifesto existe fisicamente no pacote."""
    assets_dir = package_root / "ui" / "assets"
    if not assets_dir.is_dir():
        return
    packaged = {entry.name for entry in assets_dir.iterdir() if entry.is_file()}
    for relative in ("platform_manifests", "adapters/manifests"):
        directory = package_root / relative
        if not directory.is_dir():
            continue
        for manifest in sorted(directory.glob("*.json")):
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                report.check(False, f"manifesto ilegível: {manifest.name}")
                continue
            if not isinstance(data, dict):
                continue
            for key in ("artworkAsset", "iconAsset"):
                declared = data.get(key)
                if isinstance(declared, str) and declared:
                    report.check(
                        Path(declared).name in packaged,
                        f"{manifest.name} cita asset ausente: {declared}",
                    )


def check_identity_coherence(identity: dict[str, object] | None, report: Report) -> None:
    """Manifesto, daemon e doctor precisam descrever a MESMA geração.

    Este é o gate que faltava na a37. Sem os três lados, o preflight recusa em
    vez de assumir coerência: identidade ausente não é identidade compatível.
    """
    if identity is None:
        report.check(False, "identidade de runtime não fornecida; coerência não verificável")
        return

    sources: dict[str, dict[str, object]] = {}
    for side in ("manifest", "daemon", "doctor"):
        value = identity.get(side)
        if not isinstance(value, dict):
            report.check(False, f"identidade de '{side}' ausente ou malformada")
            continue
        sources[side] = value
        for field_name in IDENTITY_FIELDS:
            report.check(
                bool(value.get(field_name)),
                f"identidade de '{side}' não expõe {field_name}",
            )

    if len(sources) < 2:
        return
    for field_name in IDENTITY_FIELDS:
        observed = {side: data.get(field_name) for side, data in sources.items()}
        distinct = {str(v) for v in observed.values() if v}
        report.check(
            len(distinct) <= 1,
            f"gerações divergentes em {field_name}: {observed}",
        )


def check_daemon_generation(identity: dict[str, object] | None, report: Report) -> None:
    """Nenhum daemon da geração anterior pode continuar vivo."""
    if identity is None:
        return
    previous = identity.get("previousDaemonAlive")
    report.check(
        previous is not True,
        "daemon da geração anterior continua vivo após a ativação",
    )


def run(package_root: Path, pyproject: Path, identity: dict[str, object] | None) -> Report:
    report = Report()
    check_package_layout(package_root, report)
    check_entry_points(pyproject, report)
    check_manifest_assets(package_root, report)
    check_identity_coherence(identity, report)
    check_daemon_generation(identity, report)
    return report


def _load_identity(path: Path | None) -> dict[str, object] | None:
    if path is None:
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("arquivo de identidade precisa conter um objeto")
    return data


def _emit(report: Report, stream: Iterable[str] | None = None) -> None:
    del stream
    for failure in report.failures:
        print(f"FAIL: {failure}", file=sys.stderr)
    verdict = "OK" if report.ok else "REPROVADO"
    print(f"preflight de release: {verdict} ({report.checks} verificações)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-root", type=Path, default=Path("src/steamzero"))
    parser.add_argument("--pyproject", type=Path, default=Path("pyproject.toml"))
    parser.add_argument(
        "--identity",
        type=Path,
        default=None,
        help="JSON com identidade de manifest, daemon e doctor coletada do host",
    )
    parser.add_argument(
        "--skip-identity",
        action="store_true",
        help="verifica apenas o pacote; use antes de existir host alvo",
    )
    args = parser.parse_args(argv)

    identity = _load_identity(args.identity)
    report = Report()
    check_package_layout(args.package_root, report)
    check_entry_points(args.pyproject, report)
    check_manifest_assets(args.package_root, report)
    if not args.skip_identity:
        check_identity_coherence(identity, report)
        check_daemon_generation(identity, report)
    _emit(report)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
