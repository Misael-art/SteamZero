# SPDX-License-Identifier: GPL-3.0-or-later
"""A seleção de origem de BIOS não transforma paths em API pública."""

from __future__ import annotations

from pathlib import Path

from steamzero.domain.bios_sources import approved_bios_sources, sanitize_bios_source_label


def test_approved_bios_sources_are_real_deduplicated_and_never_managed(tmp_path: Path) -> None:
    home = tmp_path / "home"
    first = home / "Emulation" / "bios"
    second = home / ".config" / "retroarch" / "system"
    managed = first
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    (home / "emulation" / "bios").mkdir(parents=True)
    (home / ".local" / "share" / "retroarch" / "system").parent.mkdir(parents=True)
    (home / ".local" / "share" / "retroarch" / "system").symlink_to(second)

    sources = approved_bios_sources(home=home, managed_dir=managed)

    assert [(item.label, item.path) for item in sources] == [
        ("~/emulation/bios", home / "emulation" / "bios"),
        ("~/.config/retroarch/system", second),
    ]
    assert len({item.source_id for item in sources}) == len(sources)
    assert all("/home/" not in item.label for item in sources)


def test_bios_source_label_removes_control_characters_and_home_path(tmp_path: Path) -> None:
    home = tmp_path / "private-home"
    label = sanitize_bios_source_label(home / "Emulation" / "bio\u202es", home)

    assert label == "~/Emulation/bios"
    assert str(home) not in label
