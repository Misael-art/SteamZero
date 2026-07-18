# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contrato do instalador host versionado sem tocar em caminhos do sistema."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import install_host


def _layout(tmp_path: Path) -> install_host.Layout:
    return install_host.Layout(
        root=tmp_path / "opt" / "steamzero",
        command=tmp_path / "usr" / "local" / "bin" / "steamzero",
        manager=tmp_path / "usr" / "local" / "sbin" / "steamzero-host",
        desktop=tmp_path
        / "usr"
        / "local"
        / "share"
        / "applications"
        / "org.steamzero.SteamZero.desktop",
        user_service=tmp_path
        / "usr"
        / "local"
        / "lib"
        / "systemd"
        / "user"
        / "steamzero-core.service",
        user_socket=tmp_path
        / "usr"
        / "local"
        / "lib"
        / "systemd"
        / "user"
        / "steamzero-core.socket",
        gamemode_session=tmp_path
        / "usr"
        / "share"
        / "wayland-sessions"
        / "steamzero-gamemode.desktop",
        legacy_gamemode_session=tmp_path
        / "usr"
        / "local"
        / "share"
        / "wayland-sessions"
        / "steamzero-gamemode.desktop",
        gamemode_command=tmp_path / "usr" / "local" / "bin" / "steamzero-gamemode-session",
        gamemode_boot_command=tmp_path / "usr" / "local" / "libexec" / "steamzero-gamemode-boot",
        host_prepare_command=tmp_path / "usr" / "local" / "libexec" / "steamzero-host-prepare",
        admin_command=tmp_path / "usr" / "local" / "libexec" / "steamzero-admin",
        polkit_policy=tmp_path
        / "usr"
        / "share"
        / "polkit-1"
        / "actions"
        / "io.github.misael-art.steamzero.admin.policy",
    )


def _release(layout: install_host.Layout, name: str) -> Path:
    release = layout.releases / name
    executable = release / "venv" / "bin" / "steamzero"
    artifacts = release / "artifacts"
    executable.parent.mkdir(parents=True)
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "print('0.1.0') if '--version' in sys.argv else "
        "print(json.dumps({'status': 'ok'}))\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    artifacts.mkdir()
    wheel = artifacts / "steamzero-test.whl"
    requirements = artifacts / "requirements-runtime.lock"
    installer = artifacts / "install_host.py"
    wheel.write_text("wheel", encoding="utf-8")
    requirements.write_text("lock", encoding="utf-8")
    installer.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    installer.chmod(0o755)
    (release / "manifest.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "release": name,
                "wheelFile": wheel.name,
                "wheelSha256": install_host._sha256(wheel),
                "requirementsSha256": install_host._sha256(requirements),
                "installerSha256": install_host._sha256(installer),
            }
        ),
        encoding="utf-8",
    )
    return release


def test_release_id_rejects_traversal() -> None:
    for invalid in ("../escape", "/absolute", "", "release with spaces"):
        with pytest.raises(ValueError):
            install_host._release_id(invalid)


def test_release_identity_is_canonical_version_plus_exact_commit() -> None:
    commit = "a" * 40
    assert install_host._canonical_release("0.1.0a1", commit) == f"0.1.0a1-{commit[:12]}"
    with pytest.raises(ValueError, match="SHA-1 completo"):
        install_host._canonical_release("0.1.0a1", "a" * 12)


def test_v2_manifest_requires_matching_release_provenance(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    release = _release(layout, "release-a")
    manifest_path = release / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        {
            "schemaVersion": 2,
            "packageVersion": "0.1.0a1",
            "sourceCommit": "b" * 40,
            "sourceTreeState": "clean",
        }
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(RuntimeError, match="versão e ao commit"):
        install_host._verify_release(release)


def test_activation_and_rollback_switch_current_atomically(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    _release(layout, "release-a")
    _release(layout, "release-b")

    install_host._activate(layout, "release-a")
    assert layout.current.readlink() == Path("releases/release-a")
    assert layout.command.readlink() == layout.current / "venv" / "bin" / "steamzero"
    assert "X-SteamZero-Managed=true" in layout.desktop.read_text(encoding="utf-8")

    result = install_host.rollback(layout, "release-b")
    assert result["release"] == "release-b"
    assert layout.current.readlink() == Path("releases/release-b")
    assert install_host.status(layout)["release"] == "release-b"


def test_activation_refuses_unmanaged_command_without_switching(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    _release(layout, "release-a")
    _release(layout, "release-b")
    install_host._activate(layout, "release-a")
    layout.command.unlink()
    layout.command.write_text("do not replace", encoding="utf-8")

    with pytest.raises(RuntimeError, match="não gerenciado"):
        install_host._activate(layout, "release-b")

    assert layout.current.readlink() == Path("releases/release-a")


def test_verify_rejects_manifest_directory_mismatch(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    release = _release(layout, "release-a")
    manifest = json.loads((release / "manifest.json").read_text(encoding="utf-8"))
    manifest["release"] = "other"
    (release / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(RuntimeError, match="não corresponde"):
        install_host._verify_release(release)


def test_verify_rejects_tampered_release_artifact(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    release = _release(layout, "release-a")
    (release / "artifacts" / "steamzero-test.whl").write_text("tampered", encoding="utf-8")

    with pytest.raises(RuntimeError, match="integridade inválida: wheel"):
        install_host._verify_release(release)


def test_manager_is_stable_across_release_rollback(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    _release(layout, "release-a")
    _release(layout, "release-b")
    legacy_target = str(layout.current / "artifacts" / "install_host.py")
    layout.manager.parent.mkdir(parents=True)
    layout.manager.symlink_to(legacy_target)

    install_host._publish_manager(layout)
    published = layout.manager.read_bytes()
    assert layout.manager.is_file() and not layout.manager.is_symlink()

    install_host._activate(layout, "release-a")
    install_host.rollback(layout, "release-b")

    assert layout.manager.read_bytes() == published
    assert layout.current.readlink() == Path("releases/release-b")


def test_manager_refuses_unmanaged_regular_file(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    layout.manager.parent.mkdir(parents=True)
    layout.manager.write_text("do not replace", encoding="utf-8")

    with pytest.raises(RuntimeError, match="gerenciador não gerenciado"):
        install_host._publish_manager(layout)


def test_activation_publishes_and_removes_user_units_by_release_capability(
    tmp_path: Path,
) -> None:
    layout = _layout(tmp_path)
    modern = _release(layout, "release-modern")
    core = modern / "venv" / "bin" / "steamzero-core"
    core.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    core.chmod(0o755)
    session = modern / "venv" / "bin" / "steamzero-gamemode-session"
    session.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    session.chmod(0o755)
    admin = modern / "venv" / "bin" / "steamzero-admin"
    admin.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    admin.chmod(0o755)
    _release(layout, "release-legacy")

    install_host._activate(layout, "release-modern")
    assert "ListenStream=%t/steamzero/core.sock" in layout.user_socket.read_text()
    assert str(layout.current / "venv" / "bin" / "steamzero-core") in (
        layout.user_service.read_text()
    )
    assert "Name=SteamZero Game Mode" in layout.gamemode_session.read_text()
    assert "phasezero" not in layout.gamemode_session.read_text().casefold()
    assert layout.gamemode_command.readlink() == (
        layout.current / "venv" / "bin" / "steamzero-gamemode-session"
    )
    assert layout.admin_command.readlink() == (layout.current / "venv" / "bin" / "steamzero-admin")
    policy = layout.polkit_policy.read_text(encoding="utf-8")
    assert "io.github.misael-art.steamzero.admin" in policy
    assert str(layout.admin_command) in policy

    install_host._activate(layout, "release-legacy")
    assert not layout.user_service.exists()
    assert not layout.user_socket.exists()
    assert not layout.gamemode_session.exists()
    assert not layout.gamemode_command.exists()
    assert not layout.admin_command.exists()
    assert not layout.polkit_policy.exists()


def test_activation_refuses_unmanaged_gamemode_command(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    modern = _release(layout, "release-modern")
    session = modern / "venv" / "bin" / "steamzero-gamemode-session"
    session.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    session.chmod(0o755)
    layout.gamemode_command.parent.mkdir(parents=True)
    layout.gamemode_command.write_text("do not replace", encoding="utf-8")

    with pytest.raises(RuntimeError, match="comando não gerenciado"):
        install_host._activate(layout, "release-modern")

    assert not layout.current.exists()
