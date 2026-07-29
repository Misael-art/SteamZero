#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Produz o wheelhouse de runtime e o manifesto que o instalador valida.

Existe porque um diretório de wheels sem procedência não é utilizável: os
arquivos parecem corretos, instalam sem reclamar, e ninguém consegue afirmar de
onde vieram. O repositório tinha um `wheelhouse/` assim — 7,2 MB, não rastreado,
origem desconhecida — e ele nunca entra neste fluxo, nem como fallback.

A autoridade é a combinação: commit + `requirements-runtime.lock` + este comando
+ hashes dos artefatos resultantes. Com os quatro, o conjunto é reproduzível e
auditável; faltando qualquer um, é só um monte de arquivo.

Os wheels de terceiros NÃO são commitados. O que se versiona é o lock e este
gerador; os binários vivem como artefato do workflow da tag.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

SCHEMA_VERSION = 1

#: `nome-versão-pytag-abi-plataforma.whl`. O nome do arquivo é a única fonte
#: dessas quatro informações que não exige abrir o zip.
_WHEEL_NAME = re.compile(
    r"^(?P<name>[^-]+)-(?P<version>[^-]+)"
    r"-(?P<python>[^-]+)-(?P<abi>[^-]+)-(?P<platform>.+)\.whl$"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _describe(path: Path) -> dict[str, Any]:
    """Metadados de um wheel, derivados do nome e do conteúdo."""
    match = _WHEEL_NAME.match(path.name)
    entry: dict[str, Any] = {
        "filename": path.name,
        "sha256": _sha256(path),
        "size": path.stat().st_size,
    }
    if match is None:
        # Nome fora da convenção não é ignorado: entra no manifesto declarado
        # como não interpretável, para que a validação possa recusá-lo.
        entry["nameParsed"] = False
        return entry
    entry.update(
        {
            "nameParsed": True,
            "package": match.group("name").replace("_", "-"),
            "version": match.group("version"),
            "pythonTag": match.group("python"),
            "abiTag": match.group("abi"),
            "platformTag": match.group("platform"),
        }
    )
    return entry


def _source_commit() -> tuple[str, bool]:
    """Commit e se a árvore está suja.

    Árvore suja não é bloqueio aqui — é registro. O preflight de promoção é que
    recusa; misturar as duas responsabilidades esconderia qual das duas falhou.
    """
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            ).stdout.strip()
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown", True
    return commit, dirty


def download(lock: Path, destination: Path) -> list[Path]:
    """Baixa as dependências de runtime com hash verificado.

    ``--require-hashes`` é o ponto: sem ele o pip aceitaria qualquer artefato que
    satisfizesse a versão, e o wheelhouse deixaria de ser reproduzível sem que
    nada reclamasse.
    """
    destination.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "download",
            "--only-binary=:all:",
            "--require-hashes",
            "-r",
            str(lock),
            "-d",
            str(destination),
        ],
        check=True,
        timeout=1800,
    )
    return sorted(destination.glob("*.whl"))


def build_manifest(
    *,
    wheelhouse: Path,
    lock: Path,
    package_version: str,
    steamzero_wheel: Path | None = None,
    release_id: str | None = None,
) -> dict[str, Any]:
    commit, dirty = _source_commit()
    dependencies = [
        _describe(path)
        for path in sorted(wheelhouse.glob("*.whl"))
        if steamzero_wheel is None or path.name != steamzero_wheel.name
    ]
    manifest: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "sourceCommit": commit,
        "sourceTreeState": "dirty" if dirty else "clean",
        "packageVersion": package_version,
        "requirementsLockSha256": _sha256(lock),
        "requirementsLockFile": lock.name,
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "generatorVersion": f"build_wheelhouse/{SCHEMA_VERSION}",
        "pythonImplementation": sys.implementation.name,
        "pythonVersion": ".".join(str(part) for part in sys.version_info[:3]),
        "dependencies": dependencies,
        "dependencyCount": len(dependencies),
    }
    if release_id:
        manifest["releaseId"] = release_id
    if steamzero_wheel is not None and steamzero_wheel.is_file():
        manifest["wheel"] = _describe(steamzero_wheel)
    # Identifica a execução que produziu o conjunto. Sem isto, dois artefatos
    # do mesmo commit não são distinguíveis, e reproduzir um problema exige
    # adivinhar qual foi.
    for key, variable in (
        ("githubRunId", "GITHUB_RUN_ID"),
        ("githubRunAttempt", "GITHUB_RUN_ATTEMPT"),
        ("githubWorkflow", "GITHUB_WORKFLOW"),
        ("githubRepository", "GITHUB_REPOSITORY"),
    ):
        value = os.environ.get(variable)
        if value:
            manifest[key] = value
    return manifest


def validate(
    manifest: dict[str, Any],
    wheelhouse: Path,
    lock: Path | None = None,
    wheel: Path | None = None,
) -> list[str]:
    """Confere o conjunto contra o manifesto. Devolve os problemas encontrados.

    Devolve lista em vez de levantar na primeira falha: quem instala precisa ver
    tudo que está errado de uma vez, não descobrir um problema por execução.
    """
    problems: list[str] = []

    if manifest.get("schemaVersion") != SCHEMA_VERSION:
        problems.append(
            f"schemaVersion {manifest.get('schemaVersion')!r} incompatível; "
            f"este código lê {SCHEMA_VERSION}"
        )
        return problems

    for required in ("sourceCommit", "packageVersion", "requirementsLockSha256", "dependencies"):
        if not manifest.get(required):
            problems.append(f"manifesto sem {required!r}")
    if problems:
        return problems

    if manifest.get("sourceCommit") == "unknown":
        problems.append("manifesto sem commit de origem: conjunto não rastreável")
    if manifest.get("sourceTreeState") == "dirty":
        problems.append("wheelhouse gerado de árvore suja")

    if lock is not None:
        actual = _sha256(lock)
        if actual != manifest["requirementsLockSha256"]:
            problems.append(f"lock não confere: {actual} != {manifest['requirementsLockSha256']}")

    declared = {entry["filename"]: entry for entry in manifest["dependencies"]}

    # O wheel do SteamZero NÃO é dependência: é o produto, e vive fora do
    # wheelhouse. O manifesto o registra por procedência, e a conferência
    # acontece no caminho onde ele realmente está — procurá-lo dentro do
    # wheelhouse reprovava um conjunto correto.
    main = manifest.get("wheel")
    if main is not None and wheel is not None:
        if not wheel.is_file():
            problems.append(f"wheel principal ausente: {wheel}")
        elif _sha256(wheel) != main.get("sha256"):
            problems.append(f"{wheel.name}: sha256 diverge do manifesto")
    present = {path.name: path for path in wheelhouse.glob("*.whl")}
    for name, entry in declared.items():
        path = present.get(name)
        if path is None:
            problems.append(f"declarado no manifesto e ausente: {name}")
            continue
        digest = _sha256(path)
        if digest != entry["sha256"]:
            problems.append(f"{name}: sha256 {digest} != {entry['sha256']}")
        if path.stat().st_size != entry.get("size"):
            problems.append(f"{name}: tamanho difere do manifesto")
        if not entry.get("nameParsed", True):
            problems.append(f"{name}: nome fora da convenção de wheel")

    # Arquivo presente e não declarado é tão grave quanto o contrário: é
    # exatamente a forma de um wheel de origem desconhecida entrar no conjunto.
    #
    # O wheel do produto não conta como intruso se estiver aqui dentro, mas
    # também não pode ser EXIGIDO aqui — ele normalmente vive em `dist/`.
    # Somá-lo a `declared` antes desta linha fazia a checagem de presença
    # reprovar um conjunto correto.
    known = set(declared) | ({main["filename"]} if main else set())
    for name in sorted(set(present) - known):
        problems.append(f"presente e não declarado no manifesto: {name}")

    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=ROOT / "requirements-runtime.lock")
    parser.add_argument("--out", type=Path, default=ROOT / "dist" / "runtime-wheelhouse")
    parser.add_argument("--wheel", type=Path, help="wheel do SteamZero, para entrar no manifesto")
    parser.add_argument("--release-id", help="identificador da release, quando já conhecido")
    parser.add_argument("--version", help="packageVersion; padrão: steamzero.__version__")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="não baixa nada; apenas confere o conjunto existente contra o manifesto",
    )
    args = parser.parse_args(argv)

    manifest_path = args.out / "WHEELHOUSE-MANIFEST.json"

    if args.validate_only:
        if not manifest_path.is_file():
            print(f"manifesto ausente: {manifest_path}", file=sys.stderr)
            return 2
        problems = validate(
            json.loads(manifest_path.read_text(encoding="utf-8")),
            args.out,
            args.lock,
            args.wheel,
        )
        if problems:
            print("wheelhouse REPROVADO:", file=sys.stderr)
            for problem in problems:
                print(f"  - {problem}", file=sys.stderr)
            return 1
        print(f"wheelhouse confere: {manifest_path}")
        return 0

    version = args.version
    if version is None:
        sys.path.insert(0, str(ROOT / "src"))
        from steamzero import __version__ as version

    downloaded = download(args.lock, args.out)
    manifest = build_manifest(
        wheelhouse=args.out,
        lock=args.lock,
        package_version=version,
        steamzero_wheel=args.wheel,
        release_id=args.release_id,
    )
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    problems = validate(manifest, args.out, args.lock, args.wheel)
    if problems:
        print("conjunto recém-gerado já não confere:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print(f"{len(downloaded)} wheels em {args.out}")
    print(f"manifesto: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
