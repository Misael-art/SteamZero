from __future__ import annotations

from pathlib import Path

from steamzero.adapters.discovery.format_parsers import (
    NroParser,
    NspParser,
    XciParser,
    allowed_extension,
)
from steamzero.adapters.discovery.root_scanner import RomRootScanner


def test_nsp_parser_supports() -> None:
    p = NspParser()
    assert p.supports(Path("game.nsp"))
    assert p.supports(Path("game.NSZ"))
    assert p.supports(Path("game.nsz"))
    assert not p.supports(Path("game.xci"))
    assert not p.supports(Path("game.nro"))


def test_nsp_parser_title_id_from_name() -> None:
    p = NspParser()
    tid = p.parse_title_id(Path("Super Game [0100123456789ABC][v1].nsp"))
    assert tid == "0100123456789ABC"


def test_nsp_parser_title_id_from_parent() -> None:
    p = NspParser()
    tid = p.parse_title_id(Path("/roms/0100DEADBEEF1234/game.nsp"))
    assert tid == "0100DEADBEEF1234"


def test_nsp_parser_content_kind_base() -> None:
    p = NspParser()
    assert p.parse_content_kind(Path("game.nsp")) == "base"


def test_nsp_parser_content_kind_update() -> None:
    p = NspParser()
    kind = p.parse_content_kind(Path("Game [UPD][v65536].nsp"))
    assert kind == "update"


def test_nsp_parser_content_kind_dlc() -> None:
    p = NspParser()
    kind = p.parse_content_kind(Path("Game [DLC].nsp"))
    assert kind == "dlc"


def test_nsp_parser_version() -> None:
    p = NspParser()
    v = p.parse_version(Path("Game [v65536].nsp"))
    assert v == "65536"


def test_nsp_parser_version_none() -> None:
    p = NspParser()
    assert p.parse_version(Path("game.nsp")) is None


def test_xci_parser_supports() -> None:
    p = XciParser()
    assert p.supports(Path("game.xci"))
    assert p.supports(Path("game.XCZ"))
    assert not p.supports(Path("game.nsp"))


def test_xci_parser_title_id() -> None:
    p = XciParser()
    tid = p.parse_title_id(Path("Game [0100AAAA12345678].xci"))
    assert tid == "0100AAAA12345678"


def test_xci_parser_content_kind() -> None:
    p = XciParser()
    assert p.parse_content_kind(Path("game.xci")) == "base"


def test_xci_parser_update() -> None:
    p = XciParser()
    kind = p.parse_content_kind(Path("Game [UPD].xci"))
    assert kind == "update"


def test_nro_parser_supports() -> None:
    p = NroParser()
    assert p.supports(Path("game.nro"))
    assert not p.supports(Path("game.nsp"))


def test_nro_parser_title_id() -> None:
    p = NroParser()
    assert p.parse_title_id(Path("game.nro")) is None
    tid = p.parse_title_id(Path("/roms/0100FFFFFFFFFFFF/game.nro"))
    assert tid == "0100FFFFFFFFFFFF"


def test_nro_parser_content_kind() -> None:
    p = NroParser()
    assert p.parse_content_kind(Path("game.nro")) == "base"


def test_nro_parser_version() -> None:
    p = NroParser()
    assert p.parse_version(Path("game.nro")) is None


def test_allowed_extension() -> None:
    assert allowed_extension(Path("game.nsp"))
    assert allowed_extension(Path("game.xci"))
    assert allowed_extension(Path("game.nsz"))
    assert allowed_extension(Path("game.nro"))
    assert not allowed_extension(Path("game.txt"))
    assert not allowed_extension(Path("game.zip"))
    assert not allowed_extension(Path("game"))


def test_root_scanner_empty_dir(tmp_path: Path) -> None:
    scanner = RomRootScanner()
    results = scanner.discover(tmp_path)
    assert results == []


def test_root_scanner_discover_base(tmp_path: Path) -> None:
    rom = tmp_path / "game.nsp"
    rom.write_text("dummy")
    scanner = RomRootScanner()
    results = scanner.discover(tmp_path)
    assert len(results) == 1
    assert results[0].fmt == "nsp"
    assert results[0].content_kind == "base"
    assert results[0].size_bytes > 0


def test_root_scanner_discover_recursive(tmp_path: Path) -> None:
    sub = tmp_path / "sub"
    sub.mkdir()
    rom = sub / "game.nsp"
    rom.write_text("dummy")
    scanner = RomRootScanner()
    results = scanner.discover_recursive(tmp_path)
    assert len(results) == 1
    assert results[0].path == rom


def test_root_scanner_ignores_symlink(tmp_path: Path) -> None:
    rom = tmp_path / "real.nsp"
    rom.write_text("dummy")
    link = tmp_path / "link.nsp"
    link.symlink_to(rom)
    scanner = RomRootScanner()
    results = scanner.discover(tmp_path)
    assert len(results) == 1
    assert results[0].path == rom


def test_root_scanner_ignores_unknown_extension(tmp_path: Path) -> None:
    f = tmp_path / "notes.txt"
    f.write_text("hello")
    scanner = RomRootScanner()
    results = scanner.discover(tmp_path)
    assert results == []
