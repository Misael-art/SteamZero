# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Ownership metadata for generated library artifacts.

Derived files are never guessed from platform-specific folder names. Producers
write a small, versioned sidecar that ties the artifact back to its source ROM
paths; the file manager can then offer the derived set for reversible cleanup.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from steamzero.core import fs
from steamzero.core.errors import SteamZeroError

DERIVED_MANIFEST = ".steamzero-derived.json"
DERIVED_OWNERSHIP = "SteamZero-Derived-Content: true"


def _relative(root: Path, path: Path, *, generated: bool = False) -> str:
    resolved_root = root.resolve(strict=False)
    resolved_path = fs.resolve_within(resolved_root, path)
    if resolved_path.is_symlink():
        raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="artefato derivado usa symlink")
    try:
        relative = resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="caminho fora da biblioteca") from exc
    if generated and relative.parts[:2] != (".steamzero", "derived"):
        raise SteamZeroError(
            "E-CONTENT-UNSAFE-PATH", detail="artefato fora da árvore derivada gerenciada"
        )
    if not generated and relative.parts[:1] == (".steamzero",):
        raise SteamZeroError(
            "E-CONTENT-UNSAFE-PATH", detail="origem não pode ser conteúdo gerenciado"
        )
    return relative.as_posix()


def _recorded_path(root: Path, value: str) -> Path:
    relative = fs.validate_relative_entry(value)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="manifesto aponta para symlink")
    return fs.resolve_within(root, root / relative)


def derived_manifest_bytes(
    root: Path,
    artifact_path: Path,
    owner_paths: Sequence[Path],
    *,
    operation: str,
    platform_id: str,
    title: str,
) -> bytes:
    """Return a canonical, path-bounded manifest for one generated artifact set."""
    owners = sorted({_relative(root, path) for path in owner_paths}, key=str.casefold)
    if not owners:
        raise SteamZeroError("E-CONTENT-INCOMPLETE", detail="artefato sem ROM de origem")
    payload = {
        "schemaVersion": 1,
        "ownership": DERIVED_OWNERSHIP,
        "artifactPath": _relative(root, artifact_path, generated=True),
        "ownerPaths": owners,
        "operation": operation,
        "platformId": platform_id,
        "title": title,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def write_derived_manifest(
    root: Path,
    artifact_path: Path,
    owner_paths: Sequence[Path],
    *,
    operation: str,
    platform_id: str,
    title: str,
) -> Path:
    """Publish or idempotently verify the sidecar for a completed derivation."""
    artifact = fs.resolve_within(root, artifact_path)
    manifest_path = (
        artifact / DERIVED_MANIFEST
        if artifact.is_dir()
        else artifact.with_name(artifact.name + ".steamzero-derived.json")
    )
    content = derived_manifest_bytes(
        root,
        artifact,
        owner_paths,
        operation=operation,
        platform_id=platform_id,
        title=title,
    )
    try:
        fs.write_atomic(manifest_path, content, must_not_exist=True)
        return manifest_path
    except FileExistsError as exc:
        existing = read_derived_manifest(manifest_path, root)
        expected_artifact = fs.resolve_within(root, artifact)
        expected_owners = {fs.resolve_within(root, owner) for owner in owner_paths}
        if (
            existing is not None
            and existing["artifactPath"] == expected_artifact
            and set(existing["ownerPaths"]) == expected_owners
            and existing["operation"] == operation
            and existing["platformId"] == platform_id
            and existing["title"] == title
        ):
            return manifest_path
        raise SteamZeroError(
            "E-TX-STALE-PLAN", detail="manifesto de relação existente diverge do derivado"
        ) from exc


def read_derived_manifest(path: Path, root: Path) -> Mapping[str, Any] | None:
    """Read a valid owned manifest; malformed or unsafe metadata is not trusted."""
    if path.is_symlink() or not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, Mapping) or value.get("schemaVersion") != 1:
            return None
        if value.get("ownership") != DERIVED_OWNERSHIP:
            return None
        artifact = value.get("artifactPath")
        owners = value.get("ownerPaths")
        operation = value.get("operation")
        platform = value.get("platformId")
        title = value.get("title")
        if (
            not isinstance(artifact, str)
            or not isinstance(owners, list)
            or not owners
            or not all(isinstance(owner, str) and owner for owner in owners)
            or not isinstance(operation, str)
            or not isinstance(platform, str)
            or not isinstance(title, str)
        ):
            return None
        resolved_root = root.resolve(strict=False)
        if Path(artifact).parts[:2] != (".steamzero", "derived"):
            return None
        if any(Path(owner).parts[:1] == (".steamzero",) for owner in owners):
            return None
        artifact_path = _recorded_path(resolved_root, artifact)
        owner_paths = [_recorded_path(resolved_root, owner) for owner in owners]
        if not artifact_path.exists():
            return None
        return {
            "artifactPath": artifact_path,
            "ownerPaths": owner_paths,
            "operation": operation,
            "platformId": platform,
            "title": title,
        }
    except (OSError, ValueError, TypeError, SteamZeroError):
        return None
