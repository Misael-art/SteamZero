# SPDX-License-Identifier: GPL-3.0-or-later
"""Contratos locais do harness descartável M10."""

from __future__ import annotations

import stat
from pathlib import Path

from tools.vm_harness.provision import VmConfig, _private_identity


def test_private_identity_is_copied_with_secure_mode_and_can_be_cleaned(
    tmp_path: Path,
) -> None:
    source = tmp_path / "shared-volume-key"
    source.write_bytes(b"test-private-key")
    source.chmod(0o777)
    config = VmConfig(
        source_commit="a" * 40,
        vm_name="steamzero-m10-test",
        base_image=tmp_path / "arch.qcow2",
        ssh_public_key=tmp_path / "identity.pub",
        ssh_private_key=source,
        work_dir=tmp_path / "work",
    )

    identity_file = _private_identity(config)

    assert identity_file != source
    assert identity_file.read_bytes() == b"test-private-key"
    assert stat.S_IMODE(identity_file.stat().st_mode) == 0o600
    identity_file.unlink()
    assert not identity_file.exists()
