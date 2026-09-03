# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Aquisição e instalação transacional de temas ES-DE."""

from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

import pytest

from steamzero.core.errors import SteamZeroError
from steamzero.domain.theme_acquire import (
    AcquisitionReport,
    ThemeTransaction,
    acquire_and_install,
    build_manifest,
    ingest_archive,
)
from steamzero.domain.theme_assets import ThemeAssetStore, live_digests, load_installed_manifests
from steamzero.domain.theme_sources import ThemeSource

_COMMIT = "a" * 40


def _source(theme_id: str = "org.esde.demo", name: str = "Demo") -> ThemeSource:
    return ThemeSource(
        id=theme_id,
        name=name,
        family="esde",
        author="Autora",
        credits=("Autora", "Autor Original"),
        license_id="CC-BY-NC-SA-4.0",
        license_source="README.md",
        homepage="https://exemplo.invalido",
        forge="github",
        repo="dono/repositorio",
        commit=_COMMIT,
    )


def _tarball(path: Path, files: dict[str, bytes], *, root: str = "repositorio-aaaa") -> Path:
    with tarfile.open(path, "w:gz") as archive:
        for name, payload in files.items():
            info = tarfile.TarInfo(f"{root}/{name}")
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    return path


@pytest.fixture
def store(tmp_path: Path) -> ThemeAssetStore:
    return ThemeAssetStore(tmp_path / "assets")


@pytest.fixture
def themes(tmp_path: Path) -> Path:
    root = tmp_path / "themes"
    root.mkdir()
    return root


def test_ingestion_streams_members_into_the_store(store: ThemeAssetStore, tmp_path: Path) -> None:
    archive = _tarball(
        tmp_path / "t.tar.gz",
        {"theme.xml": b"<theme/>", "art/logo.png": b"conteudo-png"},
    )

    report = ingest_archive(archive, _source(), store)

    # O prefixo `<repo>-<commit>/` some: senão o mesmo arquivo em duas versoes
    # do tema pareceria dois arquivos e a deduplicacao nao aconteceria.
    assert set(report.assets) == {"theme.xml", "art/logo.png"}
    assert report.files == 2
    assert store.usage()["blobs"] == 2


def test_second_theme_with_identical_art_pays_only_for_what_is_new(
    store: ThemeAssetStore, tmp_path: Path
) -> None:
    """A economia prometida, medida: o comum entra uma vez só."""
    shared = b"icone identico nos dois temas" * 64
    # Conteudo PROPRIO de cada tema precisa diferir, senao o store unifica os
    # dois — corretamente — e o teste deixaria de distinguir o compartilhado do
    # exclusivo, que e justamente o que ele existe para medir.
    first = _tarball(tmp_path / "a.tar.gz", {"shared.png": shared, "a.xml": b"<theme>a</theme>"})
    second = _tarball(tmp_path / "b.tar.gz", {"shared.png": shared, "b.xml": b"<theme>bb</theme>"})

    report_a = ingest_archive(first, _source("org.esde.a"), store)
    report_b = ingest_archive(second, _source("org.esde.b"), store)

    assert report_a.bytes_deduplicated == 0
    assert report_a.bytes_ingested == len(shared) + len(b"<theme>a</theme>")
    # O segundo tema paga so pelo que e dele.
    assert report_b.bytes_deduplicated == len(shared)
    assert report_b.bytes_ingested == len(b"<theme>bb</theme>")
    # Tres blobs, nao quatro: o compartilhado tem um so.
    assert store.usage()["blobs"] == 3


def test_content_outside_the_trust_boundary_is_skipped_not_installed(
    store: ThemeAssetStore, tmp_path: Path
) -> None:
    """AGENTS §10: tema de terceiro não traz binário, script nem biblioteca."""
    archive = _tarball(
        tmp_path / "t.tar.gz",
        {"theme.xml": b"<theme/>", "payload.so": b"\x7fELF", "run.sh": b"#!/bin/sh"},
    )

    report = ingest_archive(archive, _source(), store)

    assert set(report.assets) == {"theme.xml"}
    assert store.usage()["blobs"] == 1


def test_symlink_member_is_fatal(store: ThemeAssetStore, tmp_path: Path) -> None:
    """Link é recusado pelo cabeçalho, antes de qualquer leitura."""
    path = tmp_path / "hostil.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        info = tarfile.TarInfo("repo-aaaa/atalho.png")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/shadow"
        archive.addfile(info)

    with pytest.raises(SteamZeroError) as excinfo:
        list(ingest_archive(path, _source(), store))
    assert excinfo.value.code == "E-CONTENT-UNSAFE-PATH"


def test_path_traversal_member_is_fatal(store: ThemeAssetStore, tmp_path: Path) -> None:
    archive = _tarball(tmp_path / "t.tar.gz", {"../../../etc/passwd.png": b"x"})

    with pytest.raises(SteamZeroError):
        ingest_archive(archive, _source(), store)


def test_archive_without_usable_content_fails_closed(
    store: ThemeAssetStore, tmp_path: Path
) -> None:
    """Instalar um tema vazio seria pior que falhar: o usuário veria um tema
    que existe e não desenha nada."""
    archive = _tarball(tmp_path / "t.tar.gz", {"run.sh": b"#!/bin/sh"})

    with pytest.raises(SteamZeroError) as excinfo:
        ingest_archive(archive, _source(), store)
    assert excinfo.value.code == "E-CONTENT-INCOMPLETE"


def test_manifest_carries_the_attribution_chain() -> None:
    """CC-BY-NC-SA exige atribuição, e três dos cinco temas são derivados."""
    report = AcquisitionReport(theme_id="org.esde.demo", assets={"a.png": "b" * 64})

    manifest = build_manifest(_source(), report)

    assert manifest["credits"] == ["Autora", "Autor Original"]
    assert manifest["license"] == "CC-BY-NC-SA-4.0"
    assert manifest["origin"]["commit"] == _COMMIT
    assert manifest["version"] == _COMMIT[:12]


def test_install_refuses_a_manifest_pointing_at_missing_blobs(
    store: ThemeAssetStore, themes: Path
) -> None:
    """Senão o tema instalaria quebrado e o defeito só apareceria ao renderizar."""
    report = AcquisitionReport(theme_id="org.esde.demo", assets={"a.png": "c" * 64})

    with pytest.raises(SteamZeroError) as excinfo:
        ThemeTransaction(themes, store).install(_source(), report)
    assert excinfo.value.code == "E-CONTENT-INCOMPLETE"


def test_install_is_refused_when_already_present_unless_forced(
    store: ThemeAssetStore, themes: Path, tmp_path: Path
) -> None:
    archive = _tarball(tmp_path / "t.tar.gz", {"theme.xml": b"<theme/>"})
    report = ingest_archive(archive, _source(), store)
    transaction = ThemeTransaction(themes, store)
    transaction.install(_source(), report)

    with pytest.raises(SteamZeroError):
        transaction.install(_source(), report)

    replaced = transaction.install(_source(), report, force=True)
    assert replaced["replaced"] is True


def test_rollback_restores_the_previous_manifest_and_keeps_every_blob(
    store: ThemeAssetStore, themes: Path, tmp_path: Path
) -> None:
    """O requisito do operador: rollback completo SEM quebrar asset compartilhado."""
    shared = b"asset que os dois temas usam" * 32
    vizinho = _tarball(tmp_path / "v.tar.gz", {"shared.png": shared, "v.xml": b"<theme/>"})
    antigo = _tarball(tmp_path / "1.tar.gz", {"shared.png": shared, "a.xml": b"<theme>v1</theme>"})
    novo = _tarball(tmp_path / "2.tar.gz", {"shared.png": shared, "b.xml": b"<theme>v2</theme>"})

    transaction = ThemeTransaction(themes, store)
    transaction.install(
        _source("org.esde.vizinho"), ingest_archive(vizinho, _source("org.esde.vizinho"), store)
    )
    transaction.install(_source(), ingest_archive(antigo, _source(), store))
    before = (themes / "org.esde.demo" / "theme.json").read_bytes()

    upgraded = transaction.install(_source(), ingest_archive(novo, _source(), store), force=True)
    assert (themes / "org.esde.demo" / "theme.json").read_bytes() != before

    undone = transaction.rollback("org.esde.demo", upgraded["operationId"])

    assert undone["restoredPrevious"] is True
    assert (themes / "org.esde.demo" / "theme.json").read_bytes() == before
    # O vizinho continua íntegro, e o blob compartilhado nunca saiu.
    live = live_digests(load_installed_manifests(themes))
    assert store.verify(live)["ok"] is True


def test_rollback_of_a_first_install_removes_the_theme(
    store: ThemeAssetStore, themes: Path, tmp_path: Path
) -> None:
    archive = _tarball(tmp_path / "t.tar.gz", {"theme.xml": b"<theme/>"})
    transaction = ThemeTransaction(themes, store)
    installed = transaction.install(_source(), ingest_archive(archive, _source(), store))

    undone = transaction.rollback("org.esde.demo", installed["operationId"])

    assert undone["restoredPrevious"] is False
    assert not (themes / "org.esde.demo" / "theme.json").exists()
    assert undone["assetsPreserved"] is True


def test_uninstall_never_touches_blobs(
    store: ThemeAssetStore, themes: Path, tmp_path: Path
) -> None:
    shared = b"compartilhado"
    a = _tarball(tmp_path / "a.tar.gz", {"s.png": shared, "a.xml": b"<theme/>"})
    b = _tarball(tmp_path / "b.tar.gz", {"s.png": shared, "b.xml": b"<theme/>"})
    transaction = ThemeTransaction(themes, store)
    transaction.install(_source("org.esde.a"), ingest_archive(a, _source("org.esde.a"), store))
    transaction.install(_source("org.esde.b"), ingest_archive(b, _source("org.esde.b"), store))
    blobs_before = store.usage()["blobs"]

    transaction.uninstall("org.esde.a")

    assert store.usage()["blobs"] == blobs_before
    remaining = live_digests(load_installed_manifests(themes))
    assert store.verify(remaining)["ok"] is True


def test_acquire_and_install_cleans_the_archive_but_keeps_the_undo(
    store: ThemeAssetStore, themes: Path, tmp_path: Path
) -> None:
    """O tarball vai embora; o `previous-theme.json` fica, porque é o rollback."""
    prepared = _tarball(tmp_path / "src.tar.gz", {"theme.xml": b"<theme/>"})
    captured: dict[str, Path] = {}

    def fake_download(source: ThemeSource, *, operation_id: str, **_: object) -> Path:
        from steamzero.core import fs

        staged = fs.stage_bytes(operation_id, "theme.tar.gz", prepared.read_bytes())
        captured["archive"] = staged
        return staged

    result = acquire_and_install(_source(), store, themes, download=fake_download)

    assert result["assetCount"] == 1
    assert not captured["archive"].exists()
    assert (themes / "org.esde.demo" / "theme.json").is_file()


def test_theme_id_cannot_escape_the_themes_directory(store: ThemeAssetStore, themes: Path) -> None:
    hostile = ThemeSource(
        id="../../evadido",
        name="x",
        family="esde",
        author="x",
        credits=("x",),
        license_id="CC0-1.0",
        license_source="",
        homepage="",
        forge="github",
        repo="a/b",
        commit=_COMMIT,
    )
    report = AcquisitionReport(theme_id=hostile.id, assets={})

    with pytest.raises(SteamZeroError) as excinfo:
        ThemeTransaction(themes, store).install(hostile, report)
    assert excinfo.value.code == "E-THEME-UNSAFE"


def test_installed_manifest_is_valid_json_with_sorted_assets(
    store: ThemeAssetStore, themes: Path, tmp_path: Path
) -> None:
    archive = _tarball(tmp_path / "t.tar.gz", {"z.png": b"z", "a.png": b"a", "theme.xml": b"<t/>"})
    transaction = ThemeTransaction(themes, store)
    transaction.install(_source(), ingest_archive(archive, _source(), store))

    manifest = json.loads((themes / "org.esde.demo" / "theme.json").read_text(encoding="utf-8"))

    assert list(manifest["assets"]) == sorted(manifest["assets"])
    assert manifest["kind"] == "steamzero-theme-v1"
