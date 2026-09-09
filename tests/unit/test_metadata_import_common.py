# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contrato de tradução compartilhado pelos adapters (frente A1).

A defesa de caminho vive aqui uma vez só de propósito: replicada por adapter,
uma cópia acabaria divergindo e viraria a brecha que as outras fecham. Estes
testes são a prova central dela — cada adapter só precisa provar que a usa.
"""

from __future__ import annotations

import pytest

from steamzero.domain.metadata_import._common import (
    PathRefused,
    build_provenance,
    media_asset,
    normalized_players,
    require_absolute_root,
    resolve_path,
    slug_id,
)

ROOT = "/roms/psx"


# -- contenção de caminho ----------------------------------------------------


@pytest.mark.parametrize(
    "hostile",
    [
        "../../etc/passwd",
        "./../../etc/passwd",
        "a/../../../etc/passwd",
        "~/segredo.chd",
        "~root/segredo.chd",
        "/etc/passwd",
        "/roms/psx-mal/x.chd",
        "",
        "   ",
        "x\x00.chd",
    ],
)
def test_caminho_hostil_e_recusado(hostile: str) -> None:
    with pytest.raises(PathRefused):
        resolve_path(hostile, ROOT)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("./x.chd", "/roms/psx/x.chd"),
        ("x.chd", "/roms/psx/x.chd"),
        ("sub/x.chd", "/roms/psx/sub/x.chd"),
        ("sub/../x.chd", "/roms/psx/x.chd"),
        ("./media/./art.png", "/roms/psx/media/art.png"),
        ("/roms/psx/x.chd", "/roms/psx/x.chd"),
        ("  ./x.chd  ", "/roms/psx/x.chd"),
    ],
)
def test_caminho_interno_e_resolvido(raw: str, expected: str) -> None:
    assert resolve_path(raw, ROOT) == expected


def test_irmao_com_prefixo_igual_nao_e_interno() -> None:
    """``startswith`` daria ``/roms/psx-mal`` como interno a ``/roms/psx``."""
    with pytest.raises(PathRefused):
        resolve_path("/roms/psx-mal/x.chd", ROOT)
    assert resolve_path("/roms/psx/ok.chd", ROOT) == "/roms/psx/ok.chd"


def test_raiz_relativa_e_recusada() -> None:
    with pytest.raises(ValueError, match="absoluto"):
        require_absolute_root("roms/psx")


# -- identificador -----------------------------------------------------------


def test_id_e_estavel_entre_chamadas() -> None:
    """Instável, reimportar duplicaria em vez de fundir."""
    assert slug_id("psx", "/roms/psx/Crash.chd") == slug_id("psx", "/roms/psx/Crash.chd")


def test_id_respeita_o_alfabeto_do_contrato() -> None:
    import re

    for path in ["/roms/psx/Jogo Com Espaço.chd", "/roms/psx/ÀÉÎ.chd", "/roms/psx/....chd"]:
        assert re.fullmatch(r"^[a-z0-9][a-z0-9._-]{0,127}$", slug_id("psx", path))


def test_ids_de_caminhos_diferentes_nao_colidem() -> None:
    assert slug_id("psx", "/roms/psx/a.chd") != slug_id("psx", "/roms/psx/b.chd")


# -- mídia -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "role", "fmt"),
    [
        ("/a/x.png", "cover", "png"),
        ("/a/x.JPG", "cover", "jpeg"),
        ("/a/x.jpeg", "fanart", "jpeg"),
        ("/a/x.webp", "cover", "webp"),
        ("/a/x.mp4", "video", "mp4"),
        ("/a/x.webm", "video", "webm"),
    ],
)
def test_formato_consumivel_vira_asset(path: str, role: str, fmt: str) -> None:
    asset = media_asset(path, role=role)
    assert asset == {"path": path, "format": fmt}


@pytest.mark.parametrize(
    ("path", "role"),
    [
        ("/a/x.psd", "cover"),
        ("/a/x.tiff", "cover"),
        ("/a/x.png", "video"),
        ("/a/x.mp4", "cover"),
        ("/a/sem-extensao", "cover"),
    ],
)
def test_formato_nao_consumivel_e_descartado(path: str, role: str) -> None:
    """Registrar formato que a engine não consome faria a UI prometer arte
    que nunca aparece."""
    assert media_asset(path, role=role) is None


# -- proveniência ------------------------------------------------------------


def test_proveniencia_cobre_todo_campo_de_dado() -> None:
    payload = {"id": "x", "title": "T", "path": "/p"}
    prov = build_provenance(
        payload, source="esde", retrieved_at="2026-09-09T00:00:00Z", confidence=0.5
    )
    assert set(prov) == {"id", "title", "path"}
    assert prov["title"]["source"] == "esde"
    assert prov["title"]["conflictPolicy"] == "keepRichest"


def test_proveniencia_nao_reivindica_metadados_do_proprio_registro() -> None:
    """``schemaVersion``/``warnings`` não vêm da fonte; reivindicá-los inflaria
    a proveniência com origem falsa."""
    payload = {"schemaVersion": 1, "warnings": ["x"], "provenance": {}, "title": "T"}
    prov = build_provenance(
        payload, source="esde", retrieved_at="2026-09-09T00:00:00Z", confidence=0.5
    )
    assert set(prov) == {"title"}


# -- jogadores ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("1", 1), ("1-2", 2), ("2+", 2), ("até 4", 4), ("1 - 8", 8), ("sem número", None), ("", None)],
)
def test_jogadores_a_partir_de_texto_livre(raw: str, expected: int | None) -> None:
    assert normalized_players(raw) == expected
