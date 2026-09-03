# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Store de assets de tema: deduplicação, posse derivada e coleta segura."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from steamzero.core.errors import SteamZeroError
from steamzero.domain.theme_assets import (
    ThemeAssetStore,
    digest_bytes,
    live_digests,
    load_installed_manifests,
)


@pytest.fixture
def store(tmp_path: Path) -> ThemeAssetStore:
    return ThemeAssetStore(tmp_path / "theme-assets")


def _install(themes_root: Path, theme_id: str, assets: dict[str, str]) -> None:
    directory = themes_root / theme_id
    directory.mkdir(parents=True)
    (directory / "theme.json").write_text(
        json.dumps({"id": theme_id, "assets": {k: {"digest": v} for k, v in assets.items()}}),
        encoding="utf-8",
    )


def test_identical_content_is_stored_once(store: ThemeAssetStore) -> None:
    """A economia prometida: dois temas, o mesmo ícone, um blob."""
    payload = b"\x89PNG\r\n\x1a\n identical bytes"

    first = store.put("themes/a/icons/controller.png", payload)
    second = store.put("themes/b/art/gamepad.png", payload)

    assert first.digest == second.digest
    assert store.usage()["blobs"] == 1
    # O caminho lógico difere; o conteúdo é um só.
    assert first.logical_path != second.logical_path


def test_removing_a_theme_never_breaks_an_asset_another_theme_uses(
    store: ThemeAssetStore, tmp_path: Path
) -> None:
    """O requisito central: desinstalar um tema não pode quebrar o vizinho.

    Como a posse é derivada dos manifestos instalados, a remoção do diretório de
    um tema NÃO apaga blob nenhum por si só, e o blob compartilhado continua
    íntegro para quem restou.
    """
    shared = b"asset compartilhado entre dois temas"
    exclusive = b"asset exclusivo do tema que sai"
    shared_digest = store.put("shared.png", shared).digest
    exclusive_digest = store.put("only-a.png", exclusive).digest

    themes = tmp_path / "themes"
    _install(themes, "theme-a", {"logo": shared_digest, "bg": exclusive_digest})
    _install(themes, "theme-b", {"logo": shared_digest})

    # Desinstala o tema A removendo o seu diretório — nada toca o store.
    for item in (themes / "theme-a").iterdir():
        item.unlink()
    (themes / "theme-a").rmdir()

    remaining = live_digests(load_installed_manifests(themes))
    assert remaining == {shared_digest}
    assert store.verify(remaining)["ok"] is True
    # O blob exclusivo continua no disco: removê-lo é decisão do GC, não efeito
    # colateral de uma desinstalação.
    assert store.has(exclusive_digest)


def test_garbage_collection_reclaims_only_unreferenced_blobs(
    store: ThemeAssetStore, tmp_path: Path
) -> None:
    shared_digest = store.put("shared.png", b"ainda em uso").digest
    orphan_digest = store.put("orphan.png", b"ninguem referencia").digest

    themes = tmp_path / "themes"
    _install(themes, "theme-b", {"logo": shared_digest})
    live = live_digests(load_installed_manifests(themes))

    preview = store.collect_garbage(live)
    assert preview["dryRun"] is True
    assert preview["orphans"] == 1
    # Prévia não apaga.
    assert store.has(orphan_digest)

    applied = store.collect_garbage(live, dry_run=False)
    assert applied["orphans"] == 1
    assert not store.has(orphan_digest)
    assert store.has(shared_digest)


def test_unreadable_manifest_refuses_to_shrink_the_live_set(tmp_path: Path) -> None:
    """Manifesto corrompido não pode virar coleta de lixo silenciosa.

    Se um `theme.json` ilegível fosse simplesmente pulado, o conjunto vivo
    encolheria e o GC apagaria os blobs de um tema saudável cujo manifesto só
    estava temporariamente corrompido. Falhar fechado é a única resposta segura.
    """
    themes = tmp_path / "themes"
    _install(themes, "theme-a", {"logo": "a" * 64})
    (themes / "theme-a" / "theme.json").write_text("{ isto nao e json", encoding="utf-8")

    with pytest.raises(SteamZeroError) as excinfo:
        load_installed_manifests(themes)
    assert excinfo.value.code == "E-THEME-MANIFEST"


def test_verify_detects_missing_and_corrupt_blobs(store: ThemeAssetStore) -> None:
    good = store.put("good.png", b"conteudo integro").digest
    corrupted = store.put("bad.png", b"conteudo original").digest
    absent = digest_bytes(b"nunca gravado")

    # Corrompe o blob mantendo o nome — a falha que passa despercebida.
    store.blob_path(corrupted).write_bytes(b"conteudo adulterado")

    report = store.verify({good, corrupted, absent})
    assert report["ok"] is False
    assert report["missing"] == [absent]
    assert report["corrupt"] == [corrupted]


@pytest.mark.parametrize("digest", ["../../etc/passwd", "ZZZ", "a" * 63, ""])
def test_malformed_digest_is_refused(store: ThemeAssetStore, digest: str) -> None:
    """Digest vem de manifesto de terceiro: travessia não pode virar caminho."""
    with pytest.raises(SteamZeroError) as excinfo:
        store.blob_path(digest)
    assert excinfo.value.code == "E-THEME-UNSAFE"


def test_executable_content_is_refused_by_extension(store: ThemeAssetStore) -> None:
    """AGENTS §10: tema de terceiro não traz binário, biblioteca nem script."""
    for name in ("payload.so", "run.sh", "mod.py", "app.AppImage"):
        with pytest.raises(SteamZeroError) as excinfo:
            store.put(name, b"conteudo")
        assert excinfo.value.code == "E-THEME-UNSAFE"


def test_oversized_asset_is_refused(
    store: ThemeAssetStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("steamzero.domain.theme_assets.MAX_ASSET_BYTES", 16)
    with pytest.raises(SteamZeroError) as excinfo:
        store.put("big.png", b"x" * 17)
    assert excinfo.value.code == "E-THEME-LIMIT"
