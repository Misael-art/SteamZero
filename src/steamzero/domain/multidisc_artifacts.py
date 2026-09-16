# SPDX-License-Identifier: GPL-3.0-or-later
"""Atomic, owned ``.m3u`` projection for a reconciled multi-disc set."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from steamzero.core import transaction
from steamzero.core.errors import SteamZeroError
from steamzero.domain.multidisc import MultiDiscSet

OWNERSHIP_MARKER = "# SteamZero-MultiDisc-Managed: true"


@dataclass(frozen=True)
class DescriptorProjection:
    path: Path
    content: str
    content_hash: str
    state: Literal["current", "stale", "conflict", "missing"]


def _safe_relative_path(path: Path, root: Path) -> str:
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise SteamZeroError(
            "E-CONTENT-UNSAFE-PATH", detail=f"mídia fora da playlist: {path}"
        ) from exc
    if not relative.parts or ".." in relative.parts:
        raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail=f"caminho relativo inválido: {path}")
    rendered = relative.as_posix()
    if any(ord(char) < 32 or char in "\r\n\x00" for char in rendered):
        raise SteamZeroError("E-TX-STALE-PLAN", detail="caminho contém controle ou quebra de linha")
    return rendered


def render_descriptor(logical_set: MultiDiscSet) -> str:
    """Render a deterministic playlist from current physical disc records."""

    if logical_set.descriptor_path is None:
        raise SteamZeroError("E-TX-STALE-PLAN", detail="playlist sem destino declarado")
    active = [disc for disc in logical_set.discs if disc.state in {"active", "converted"}]
    if len(active) != len(logical_set.discs) or not active:
        raise SteamZeroError("E-TX-STALE-PLAN", detail="playlist não pode ocultar disco ausente")
    root = logical_set.descriptor_path.parent
    lines = [OWNERSHIP_MARKER, f"# SteamZero-MultiDisc-Set: {logical_set.set_id}"]
    for disc in sorted(active, key=lambda item: item.disc_number):
        if disc.path is None:
            raise SteamZeroError("E-TX-STALE-PLAN", detail="disco sem caminho atual")
        if disc.path == disc.archive_path and disc.member_path is not None:
            raise SteamZeroError(
                "E-TX-STALE-PLAN",
                detail="playlist não pode apontar diretamente para container não extraído",
            )
        if disc.format.casefold() not in {value.casefold() for value in disc.accepted_formats}:
            raise SteamZeroError(
                "E-TX-STALE-PLAN",
                detail=f"formato não aceito pelo adapter: {disc.format}",
            )
        lines.append(_safe_relative_path(disc.path, root))
    return "\n".join(lines) + "\n"


def descriptor_projection(logical_set: MultiDiscSet) -> DescriptorProjection:
    content = render_descriptor(logical_set)
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    path = logical_set.descriptor_path
    if path is None:
        raise SteamZeroError("E-TX-STALE-PLAN", detail="playlist sem destino declarado")
    if path.is_symlink():
        raise SteamZeroError("E-TX-STALE-PLAN", detail="playlist gerenciada não pode ser symlink")
    if not path.exists():
        state: Literal["current", "stale", "conflict", "missing"] = "missing"
    else:
        current = path.read_text(encoding="utf-8")
        if not current.startswith(OWNERSHIP_MARKER + "\n"):
            state = "conflict"
        else:
            state = (
                "current"
                if hashlib.sha256(current.encode("utf-8")).hexdigest() == digest
                else "stale"
            )
    return DescriptorProjection(path, content, digest, state)


def plan_descriptor_update(logical_set: MultiDiscSet) -> transaction.Plan:
    """Plan an atomic update; user-owned descriptors are never overwritten."""

    projection = descriptor_projection(logical_set)
    if projection.state == "conflict":
        raise SteamZeroError(
            "E-TX-STALE-PLAN",
            detail="playlist existente não possui ownership SteamZero",
        )
    return transaction.plan_write_files(
        {projection.path: projection.content.encode("utf-8")},
        root=projection.path.parent,
        kind="multidisc.descriptor",
        skip_unchanged=True,
        requirements_extra={"descriptorHash": projection.content_hash},
    )


def apply_descriptor_update(plan: transaction.Plan) -> transaction.ApplyResult:
    if plan.kind != "multidisc.descriptor":
        raise SteamZeroError("E-TX-STALE-PLAN", detail="plano não é de playlist multidisco")
    return transaction.apply(plan.plan_id, plan.confirm_token)


__all__ = [
    "OWNERSHIP_MARKER",
    "DescriptorProjection",
    "apply_descriptor_update",
    "descriptor_projection",
    "plan_descriptor_update",
    "render_descriptor",
]
