# SPDX-License-Identifier: GPL-3.0-or-later
"""Fronteira de rede dos artefatos portáteis pinados."""

from __future__ import annotations

from steamzero.adapters import engine
from steamzero.adapters.registry import AdapterSource


def test_github_release_asset_redirect_is_allowlisted_with_exact_host(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    captured: dict[str, object] = {}

    def fetch(url: str, **kwargs: object) -> bytes:
        captured["url"] = url
        captured.update(kwargs)
        return b"verified-payload"

    monkeypatch.setattr(engine, "fetch_bytes", fetch)
    source = AdapterSource(
        type="appimage",
        version="1.0.0",
        priority=1,
        url="https://github.com/example/project/releases/download/v1.0.0/example.AppImage",
        sha256="0" * 64,
    )

    assert engine.HttpsArtifactPort().fetch(source) == b"verified-payload"
    allowed = captured["allowed_redirect_hosts"]
    assert isinstance(allowed, set)
    assert "release-assets.githubusercontent.com" in allowed
    assert "evil.githubusercontent.com" not in allowed
