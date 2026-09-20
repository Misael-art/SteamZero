# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

from steamzero.adapters.console_runtime_readiness import check_xemu_runtime


def _write_config(path: Path, *, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["[sys.files]"]
    lines.extend(f'{key} = "{value}"' for key, value in values.items())
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_xemu_missing_machine_files_is_actionable_without_spawn(tmp_path: Path) -> None:
    config = tmp_path / "xemu.toml"
    _write_config(config, values={"eeprom_path": str(tmp_path / "eeprom.bin")})
    (tmp_path / "eeprom.bin").write_bytes(b"eeprom")

    readiness = check_xemu_runtime(candidates=(config,))

    assert readiness.ready is False
    assert readiness.config_found is True
    assert readiness.missing == ("flash", "mcpx", "hdd")
    assert readiness.reason == "xbox-machine-files-missing"


def test_xemu_accepts_complete_machine_configuration(tmp_path: Path) -> None:
    paths = {
        key: tmp_path / name
        for key, name in {
            "eeprom_path": "eeprom.bin",
            "flash_path": "flash.bin",
            "mcpx_path": "mcpx.bin",
            "hdd_path": "xbox.img",
        }.items()
    }
    for path in paths.values():
        path.write_bytes(b"machine-file")
    config = tmp_path / "xemu.toml"
    _write_config(config, values={key: str(value) for key, value in paths.items()})

    readiness = check_xemu_runtime(candidates=(config,))

    assert readiness.ready is True
    assert readiness.missing == ()
    assert readiness.reason == ""


def test_xemu_invalid_config_is_recoverable(tmp_path: Path) -> None:
    config = tmp_path / "xemu.toml"
    config.write_text("[sys.files\n", encoding="utf-8")

    readiness = check_xemu_runtime(candidates=(config,))

    assert readiness.ready is False
    assert readiness.config_found is True
    assert readiness.reason == "xbox-machine-config-invalid"
