# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path

import pytest

from steamzero.core import transaction
from steamzero.core.errors import SteamZeroError


def test_copy_plan_rejects_space_requirement_override(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.write_bytes(b"content")
    target_root = tmp_path / "target"

    with pytest.raises(SteamZeroError) as exc:
        transaction.plan_copy_files(
            {source: target_root / "copy"},
            root=target_root,
            requirements_extra={"spaceBytes": 0},
        )

    assert exc.value.code == "E-API-SCHEMA"
