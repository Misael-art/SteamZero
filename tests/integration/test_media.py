# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Mídia local: canonicalização, payload hostil e rollback RT-11."""

from __future__ import annotations

from pathlib import Path

import pytest

from steamzero.core import fs, ids
from steamzero.core.errors import SteamZeroError
from steamzero.domain.media import MediaAssignment, MediaLibrary

_PNG = b"\x89PNG\r\n\x1a\n" + b"synthetic-png"
_JPG = b"\xff\xd8\xff" + b"synthetic-jpeg"


def _assignment(game_id: str, kind: str = "boxart") -> MediaAssignment:
    return MediaAssignment(game_id, kind, "fixture-provider", "CC0-1.0")


@pytest.mark.integration
@pytest.mark.rt
def test_rt11_canonicalization_and_orphan_quarantine_rollback(tmp_path: Path) -> None:
    root = tmp_path / "media"
    assigned = root / "downloads" / "cover.payload"
    orphan = root / "downloads" / "unused.payload"
    fs.write_atomic(assigned, _PNG)
    fs.write_atomic(orphan, _JPG)
    before = {str(path.relative_to(root)): fs.hash_file(path) for path in fs.iter_files(root)}
    game_id = ids.new_ulid()
    media = MediaLibrary()
    plan = media.plan_reconcile(root, {"downloads/cover.payload": _assignment(game_id)})
    result = media.apply(plan.plan_id, plan.confirm_token)

    canonical = root / "canonical" / game_id / "boxart.png"
    quarantined = list((root / ".quarantine" / "orphans").iterdir())
    assert canonical.read_bytes() == _PNG
    assert len(quarantined) == 1 and quarantined[0].read_bytes() == _JPG
    assert not assigned.exists() and not orphan.exists()

    assert media.rollback(result.operation_id).status == "rolled-back"
    assert media.rollback(result.operation_id).status == "rolled-back"
    after = {str(path.relative_to(root)): fs.hash_file(path) for path in fs.iter_files(root)}
    assert after == before
    assert not canonical.exists()
    assert not quarantined[0].exists()


@pytest.mark.integration
@pytest.mark.rt
def test_rt11_failed_validation_restores_canonical_and_orphan_sources(tmp_path: Path) -> None:
    root = tmp_path / "media"
    assigned = root / "cover.bin"
    orphan = root / "orphan.bin"
    fs.write_atomic(assigned, _PNG)
    fs.write_atomic(orphan, _JPG)
    media = MediaLibrary()
    plan = media.plan_reconcile(root, {"cover.bin": _assignment(ids.new_ulid())})

    def reject_index() -> None:
        raise RuntimeError("índice recusou a canonicalização")

    with pytest.raises(SteamZeroError) as error:
        media.apply(plan.plan_id, plan.confirm_token, smoke=reject_index)
    assert error.value.code == "E-TX-VERIFY-FAILED"
    assert assigned.read_bytes() == _PNG
    assert orphan.read_bytes() == _JPG
    assert list(fs.iter_files(root / "canonical")) == []
    assert list(fs.iter_files(root / ".quarantine")) == []


@pytest.mark.integration
@pytest.mark.security
def test_st06_bad_magic_oversize_and_bidi_are_quarantined(tmp_path: Path) -> None:
    root = tmp_path / "media"
    bad_magic = root / "bad.png"
    oversized = root / "large.png"
    bidi = root / "evil\u202ename.png"
    fs.write_atomic(bad_magic, b"not-an-image")
    fs.write_atomic(oversized, _PNG + b"x" * 100)
    fs.write_atomic(bidi, _PNG)
    game_id = ids.new_ulid()
    assignment = _assignment(game_id)
    plan = MediaLibrary(max_bytes=32).plan_reconcile(
        root,
        {"bad.png": assignment, "large.png": assignment, "evil\u202ename.png": assignment},
    )
    result = MediaLibrary.apply(plan.plan_id, plan.confirm_token)
    quarantined = list((root / ".quarantine" / "orphans").iterdir())
    assert len(quarantined) == 3
    assert all(path.name.isascii() for path in quarantined)
    assert not (root / "canonical" / game_id).exists()
    MediaLibrary.rollback(result.operation_id)
