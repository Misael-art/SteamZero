# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Rotas do catálogo de temas ES-DE, exercidas pela ponte da UI.

Uma sonda comportamental, não estrutural: cada rota é chamada e o EFEITO é
verificado no disco. Conferir apenas que a ação aparece no contrato provaria
que alguém a declarou, não que ela faz alguma coisa — e um controle declarado
que não age é precisamente o defeito que este projeto vem removendo.
"""

from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

import pytest

from steamzero.adapters.desktop_contracts import handheld_ui_contracts
from steamzero.adapters.desktop_dashboard import DesktopDashboard
from steamzero.core.errors import SteamZeroError
from steamzero.domain import theme_acquire
from steamzero.domain.theme_sources import ThemeSource

_COMMIT = "b" * 40


@pytest.fixture
def dashboard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DesktopDashboard:
    """Isola o estado do usuário: nenhuma rota pode tocar o HOME real."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    from steamzero.core import paths

    paths.themes_dir().mkdir(parents=True, exist_ok=True)
    return DesktopDashboard()


def _fake_theme(tmp_path: Path, theme_id: str, files: dict[str, bytes]) -> ThemeSource:
    archive = tmp_path / f"{theme_id}.tar.gz"
    with tarfile.open(archive, "w:gz") as handle:
        for name, payload in files.items():
            info = tarfile.TarInfo(f"repo-{_COMMIT[:8]}/{name}")
            info.size = len(payload)
            handle.addfile(info, io.BytesIO(payload))
    return ThemeSource(
        id=theme_id,
        name=theme_id,
        family="esde",
        author="Autora",
        credits=("Autora",),
        license_id="CC0-1.0",
        license_source="LICENSE",
        homepage="",
        forge="github",
        repo="dono/repo",
        commit=_COMMIT,
    )


def test_every_catalog_action_is_declared_in_the_contract() -> None:
    actions = {action["id"] for action in handheld_ui_contracts()["actions"]}

    assert {
        "theme.catalog.list",
        "theme.catalog.install",
        "theme.catalog.rollback",
        "theme.catalog.uninstall",
        "theme.store.gc",
    } <= actions


def test_destructive_actions_require_explicit_confirmation() -> None:
    """Remover tema e apagar blob não podem acontecer sem pedido."""
    actions = {action["id"]: action for action in handheld_ui_contracts()["actions"]}

    assert actions["theme.catalog.uninstall"]["confirmation"]["required"] is True
    assert actions["theme.catalog.uninstall"]["confirmation"]["mode"] == "explicit"
    assert actions["theme.store.gc"]["confirmation"]["required"] is True
    # Instalar não é destrutivo e não exige confirmação extra.
    assert actions["theme.catalog.install"]["confirmation"]["required"] is False


def test_list_publishes_the_curated_entries_and_the_excluded_ones(
    dashboard: DesktopDashboard,
) -> None:
    """Os excluídos viajam com o motivo: a ausência não pode parecer
    esquecimento."""
    payload = dashboard.theme_catalog_list()

    assert len(payload["entries"]) == 5
    assert all(entry["installed"] is False for entry in payload["entries"])
    assert len(payload["excluded"]) == 4
    for item in payload["excluded"]:
        assert "licen" in item["reason"].casefold()
    assert payload["storeUsage"]["blobs"] == 0


def test_list_marks_what_is_installed_and_whether_it_is_up_to_date(
    dashboard: DesktopDashboard, tmp_path: Path
) -> None:
    from steamzero.core import paths

    source = _fake_theme(tmp_path, "org.esde.iconic", {"theme.xml": b"<theme/>"})
    report = theme_acquire.ingest_archive(
        tmp_path / "org.esde.iconic.tar.gz", source, dashboard._theme_store()
    )
    theme_acquire.ThemeTransaction(paths.themes_dir(), dashboard._theme_store()).install(
        source, report
    )

    entry = next(e for e in dashboard.theme_catalog_list()["entries"] if e["id"] == source.id)

    assert entry["installed"] is True
    # A versão instalada é a do commit falso, não a do catálogo: instalado e
    # atualizado são coisas diferentes, e a rota precisa distingui-las.
    assert entry["installedVersion"] == _COMMIT[:12]
    assert entry["upToDate"] is False


def test_uninstall_removes_the_theme_and_gc_reclaims_only_orphans(
    dashboard: DesktopDashboard, tmp_path: Path
) -> None:
    """O ciclo que o operador pediu: remover sem quebrar o vizinho."""
    from steamzero.core import paths

    shared = b"asset compartilhado" * 32
    store = dashboard._theme_store()
    transaction = theme_acquire.ThemeTransaction(paths.themes_dir(), store)
    for theme_id, own in (("org.esde.iconic", b"<a/>"), ("org.esde.modern", b"<b/>")):
        source = _fake_theme(tmp_path, theme_id, {"s.png": shared, "t.xml": own})
        report = theme_acquire.ingest_archive(tmp_path / f"{theme_id}.tar.gz", source, store)
        transaction.install(source, report)
    blobs_before = store.usage()["blobs"]

    dashboard.theme_catalog_uninstall("org.esde.iconic")

    # Remover não apaga blob: o compartilhado ainda tem dono.
    assert store.usage()["blobs"] == blobs_before
    preview = dashboard.theme_store_gc()
    assert preview["dryRun"] is True
    assert preview["orphans"] == 1  # só o XML exclusivo do tema removido

    applied = dashboard.theme_store_gc(apply=True)
    assert applied["orphans"] == 1
    # O vizinho continua íntegro depois da coleta.
    remaining = json.loads(
        (paths.themes_dir() / "org.esde.modern" / "theme.json").read_text(encoding="utf-8")
    )
    assert store.verify(entry["digest"] for entry in remaining["assets"].values())["ok"] is True


def test_rollback_route_restores_the_previous_manifest(
    dashboard: DesktopDashboard, tmp_path: Path
) -> None:
    from steamzero.core import paths

    store = dashboard._theme_store()
    transaction = theme_acquire.ThemeTransaction(paths.themes_dir(), store)
    first = _fake_theme(tmp_path, "org.esde.iconic", {"t.xml": b"<v1/>"})
    transaction.install(
        first,
        theme_acquire.ingest_archive(tmp_path / "org.esde.iconic.tar.gz", first, store),
    )
    manifest_path = paths.themes_dir() / "org.esde.iconic" / "theme.json"
    before = manifest_path.read_bytes()

    second = _fake_theme(tmp_path, "org.esde.iconic", {"t.xml": b"<v2-diferente/>"})
    upgraded = transaction.install(
        second,
        theme_acquire.ingest_archive(tmp_path / "org.esde.iconic.tar.gz", second, store),
        force=True,
    )
    assert manifest_path.read_bytes() != before

    undone = dashboard.theme_catalog_rollback("org.esde.iconic", upgraded["operationId"])

    assert undone["restoredPrevious"] is True
    assert undone["assetsPreserved"] is True
    assert manifest_path.read_bytes() == before


def test_installing_a_theme_outside_the_catalog_is_refused(
    dashboard: DesktopDashboard,
) -> None:
    """A rota não é uma porta para URL arbitrária: só o curado passa."""
    with pytest.raises(SteamZeroError) as excinfo:
        dashboard.theme_catalog_install("org.esde.slick")
    assert excinfo.value.code == "E-THEME-NOT-FOUND"
