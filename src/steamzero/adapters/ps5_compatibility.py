# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Snapshot versionado da compatibilidade pública do SharpEmu para PS5."""

from __future__ import annotations

import hashlib
import importlib.resources
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from steamzero.domain.game_identity import IdentityScheme, validate_identity_value

_TITLE_ID_RE = re.compile(r"^PPS[A-Z][0-9A-Z]{5,12}(?:_[0-9A-Z]{2})?$")
_STATUSES = frozenset({"nothing", "boots", "menus", "ingame", "playable"})
_OPERATING_SYSTEMS = frozenset({"linux", "macos", "windows"})
_SOURCE_URL = "https://sharpemu.app/compatibility/"


def _ps5_source_kind(root: Path) -> str:
    """Classifica a origem sem publicar o caminho físico do usuário."""
    normalized = root.as_posix().casefold()
    if normalized.startswith(("//", "/net/")) or "/gvfs/" in normalized:
        return "network"
    if normalized.startswith(("/media/", "/run/media/", "/mnt/")):
        return "removable"
    return "local"


def _ps5_source_namespace(root: Path, source_kind: str) -> str:
    """Produz um namespace opaco que sobrevive à troca do ponto de montagem."""
    try:
        observed = root.stat()
        token = f"{source_kind}\0{observed.st_dev}\0{observed.st_ino}"
    except OSError:
        # O inventário só chama isto para uma origem existente; este fallback
        # mantém a falha explícita sem vazar o caminho absoluto para a UI.
        token = f"{source_kind}\0path\0{root.as_posix()}"
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:24]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_ps5_source_identity(
    path: Path,
    root: Path,
    *,
    title_id: str | None,
) -> dict[str, Any]:
    """Descreve uma entrada PS5 sem usar o caminho absoluto como identidade.

    O hash é do entrypoint que será lançado. O namespace identifica o volume
    ou compartilhamento observado, enquanto ``relativePath`` permite
    reconciliar o mesmo dump após uma remontagem em outro ponto.
    """
    relative_path = path.relative_to(root).as_posix()
    stat = path.stat()
    source_kind = _ps5_source_kind(root)
    source_namespace = _ps5_source_namespace(root, source_kind)
    try:
        entrypoint_sha256: str | None = _sha256_file(path)
    except OSError:
        entrypoint_sha256 = None
    identity_material = "\0".join(
        (
            "ps5-source-v1",
            source_kind,
            source_namespace,
            relative_path,
            str(stat.st_size),
            entrypoint_sha256 or "unavailable",
        )
    )
    stable_id = hashlib.sha256(identity_material.encode("utf-8")).hexdigest()[:24]
    source_identity: dict[str, Any] = {
        "sourceKind": source_kind,
        "volumeId": source_namespace if source_kind != "network" else None,
        "shareId": source_namespace if source_kind == "network" else None,
        "titleId": title_id,
        "relativePath": relative_path,
        "sizeBytes": stat.st_size,
        "entrypointSha256": entrypoint_sha256,
        "identityState": "verified" if entrypoint_sha256 else "degraded",
        "identityReason": None if entrypoint_sha256 else "ps5-entrypoint-hash-failed",
        "stableId": stable_id,
    }
    return source_identity


@dataclass(frozen=True)
class Ps5CompatibilityRecord:
    """Relatório público de um título em uma build e OS específicos."""

    title_id: str
    state: str
    tested_build: str
    tested_date: str
    tested_os: str
    game_version: str | None = None


@dataclass(frozen=True)
class Ps5CompatibilityCatalog:
    """Catálogo imutável carregado do snapshot empacotado."""

    source_url: str
    source_repository: str
    source_path: str
    source_commit: str
    snapshot_date: str
    records: tuple[Ps5CompatibilityRecord, ...]

    @property
    def by_title_id(self) -> dict[str, Ps5CompatibilityRecord]:
        return {record.title_id: record for record in self.records}

    def lookup(self, title_id: str | None) -> Ps5CompatibilityRecord | None:
        if not isinstance(title_id, str):
            return None
        return self.by_title_id.get(title_id.strip().upper())


def _require_string(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"compatibilidade PS5 exige {key}")
    return value.strip()


def _load_catalog(raw: dict[str, Any]) -> Ps5CompatibilityCatalog:
    source = raw.get("source")
    entries = raw.get("records")
    if not isinstance(source, dict) or not isinstance(entries, list):
        raise ValueError("snapshot de compatibilidade PS5 inválido")
    source_url = _require_string(source, "url")
    source_repository = _require_string(source, "repository")
    source_path = _require_string(source, "path")
    source_commit = _require_string(source, "commit")
    snapshot_date = _require_string(source, "snapshotDate")
    if source_url != _SOURCE_URL or not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("fonte de compatibilidade PS5 não está pinned")

    records: list[Ps5CompatibilityRecord] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("registro de compatibilidade PS5 inválido")
        title_id = _require_string(entry, "titleId").upper()
        if title_id in seen or not _TITLE_ID_RE.fullmatch(title_id):
            raise ValueError(f"Title ID PS5 inválido ou duplicado: {title_id}")
        if not validate_identity_value(IdentityScheme.PS5_TITLE_ID, title_id):
            raise ValueError(f"Title ID PS5 inválido: {title_id}")
        state = _require_string(entry, "state")
        tested_os = _require_string(entry, "testedOs")
        if state not in _STATUSES or tested_os not in _OPERATING_SYSTEMS:
            raise ValueError(f"registro PS5 fora do contrato: {title_id}")
        game_version = entry.get("gameVersion")
        if game_version is not None and (
            not isinstance(game_version, str) or not game_version.strip()
        ):
            raise ValueError(f"gameVersion PS5 inválida: {title_id}")
        records.append(
            Ps5CompatibilityRecord(
                title_id=title_id,
                state=state,
                tested_build=_require_string(entry, "testedBuild"),
                tested_date=_require_string(entry, "testedDate"),
                tested_os=tested_os,
                game_version=game_version.strip() if isinstance(game_version, str) else None,
            )
        )
        seen.add(title_id)
    declared_count = source.get("testedCount")
    if declared_count != len(records):
        raise ValueError("contagem declarada do snapshot PS5 diverge dos registros")
    return Ps5CompatibilityCatalog(
        source_url=source_url,
        source_repository=source_repository,
        source_path=source_path,
        source_commit=source_commit,
        snapshot_date=snapshot_date,
        records=tuple(records),
    )


@lru_cache(maxsize=1)
def bundled_ps5_compatibility() -> Ps5CompatibilityCatalog:
    resource = importlib.resources.files("steamzero.adapters").joinpath("ps5_compatibility.json")
    return _load_catalog(json.loads(resource.read_text(encoding="utf-8")))


def resolve_ps5_compatibility(
    title_id: str | None,
    runtime_build: str | None,
    *,
    runtime_os: str,
    catalog: Ps5CompatibilityCatalog | None = None,
) -> dict[str, Any]:
    """Resolve somente uma combinação de título, build e OS comprovada.

    Um relatório de Windows/macOS não é promovido para Linux, e um relatório de
    outra build não é tratado como compatível. O payload mantém o relatório
    encontrado para a UI explicar a razão do estado conservador.
    """
    active_build = runtime_build if runtime_build and runtime_build != "unknown" else None
    normalized_title = title_id.strip().upper() if isinstance(title_id, str) else None
    normalized_os = runtime_os.strip().lower()
    record = (catalog or bundled_ps5_compatibility()).lookup(normalized_title)
    result: dict[str, Any] = {
        "state": "unknown",
        "build": active_build,
        "testedBuild": record.tested_build if record else None,
        "testedOs": record.tested_os if record else None,
        "testedDate": record.tested_date if record else None,
        "gameVersion": record.game_version if record else None,
        "source": _SOURCE_URL,
    }
    if normalized_title is None:
        result["reason"] = "Title ID PS5 ausente; compatibilidade não pode ser consultada."
    elif record is None:
        result["reason"] = f"Nenhum relatório oficial para o Title ID {normalized_title}."
    elif active_build != record.tested_build:
        result["reason"] = (
            f"Relatório oficial disponível para build {record.tested_build}; "
            f"a build ativa {active_build or 'desconhecida'} não foi testada."
        )
    elif normalized_os != record.tested_os:
        result["reason"] = (
            f"Relatório oficial da build {record.tested_build} é para {record.tested_os}; "
            f"o host {normalized_os} não foi testado."
        )
    else:
        result["state"] = record.state
        result["reason"] = (
            f"Relatório oficial de {record.tested_os}, build {record.tested_build}, "
            f"em {record.tested_date}."
        )
    return result


def resolve_ps5_content_status(
    path: str | None,
    *,
    identity_verified: bool,
    identity_diagnosis: str | None,
) -> dict[str, str]:
    """Classifica a disponibilidade do dump sem promover conteúdo incompleto.

    ``state`` do workspace continua compatível com consumidores existentes;
    estes campos paralelos dão à UI uma causa específica e recuperável.
    """
    if not isinstance(path, str) or not path.strip():
        return {
            "contentState": "source-missing",
            "contentAvailability": "missing",
            "contentReason": "Origem PS5 ausente; reanexe a pasta do dump.",
        }
    source = Path(path)
    try:
        source_available = source.is_file() and not source.is_symlink()
    except OSError:
        source_available = False
    if not source_available:
        return {
            "contentState": "source-missing",
            "contentAvailability": "missing",
            "contentReason": "Origem PS5 ausente; reanexe a pasta do dump.",
        }
    if identity_verified and identity_diagnosis == "ps5-param-sfo":
        return {
            "contentState": "complete",
            "contentAvailability": "available",
            "contentReason": "Dump PS5 identificado por param.sfo.",
        }
    diagnosis = identity_diagnosis or "ps5-identity-unverified"
    return {
        "contentState": "content-incomplete",
        "contentAvailability": "degraded",
        "contentReason": f"Dump PS5 incompleto; identidade pendente ({diagnosis}).",
    }
