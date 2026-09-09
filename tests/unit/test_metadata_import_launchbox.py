# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Adapter de importação LaunchBox (frente A1).

Formato do Windows: caminho com barra invertida e letra de unidade, rating em
estrelas 0..5 e sinalizadores que o usuário já marcou na origem. Cada uma
dessas diferenças tem teste próprio, porque nenhuma pode vazar para o contrato.
"""

from __future__ import annotations

import pytest

from steamzero.domain.game_record import GameRecordError
from steamzero.domain.metadata_import import import_launchbox_xml

ROOT = "/roms/psx"
WHEN = "2026-09-09T00:00:00Z"


def _run(xml: str, *, system_root: str = ROOT):
    return import_launchbox_xml(xml, platform_id="psx", system_root=system_root, retrieved_at=WHEN)


def _lb(*games: str) -> str:
    return "<?xml version='1.0'?><LaunchBox>" + "".join(games) + "</LaunchBox>"


def _game(**fields: str) -> str:
    body = "".join(f"<{tag}>{value}</{tag}>" for tag, value in fields.items())
    return f"<Game>{body}</Game>"


def test_traduz_jogo_completo() -> None:
    (record,) = _run(
        _lb(
            _game(
                Title="Crash Bandicoot",
                ApplicationPath="Games\\psx\\Crash.chd",
                Developer="Naughty Dog",
                Publisher="Sony",
                Genre="Platform; Action",
                MaxPlayers="2",
                CommunityStarRating="4.25",
                ReleaseDate="1996-09-09T00:00:00",
                Notes="Um marsupial.",
            )
        )
    ).records
    payload = record.to_mapping()
    assert record.title == "Crash Bandicoot"
    assert payload["path"] == "/roms/psx/Games/psx/Crash.chd"
    assert payload["genres"] == ["Platform", "Action"]
    assert payload["players"] == 2
    assert payload["releaseDate"] == "1996-09-09"
    assert payload["description"] == "Um marsupial."


# -- diferenças do Windows ---------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Games\\x.chd", "/roms/psx/Games/x.chd"),
        ("C:\\Games\\x.chd", "/roms/psx/Games/x.chd"),
        ("D:\\x.chd", "/roms/psx/x.chd"),
        ("Games/x.chd", "/roms/psx/Games/x.chd"),
    ],
)
def test_caminho_do_windows_e_convertido_e_contido(raw: str, expected: str) -> None:
    """Manter a letra de unidade produziria caminho que não existe no host."""
    (record,) = _run(_lb(_game(Title="X", ApplicationPath=raw))).records
    assert record.to_mapping()["path"] == expected


def test_rating_em_estrelas_vira_escala_canonica_0_a_100() -> None:
    """LaunchBox usa 0..5 estrelas; o contrato fixa uma escala só."""
    for stars, expected in (("5", 100.0), ("4.25", 85.0), ("0", 0.0), ("2.5", 50.0)):
        (record,) = _run(
            _lb(_game(Title="X", ApplicationPath="x.chd", CommunityStarRating=stars))
        ).records
        assert record.to_mapping()["rating"] == expected


@pytest.mark.parametrize("bad", ["6", "-1", "muitas"])
def test_rating_invalido_vira_aviso_e_nao_numero_inventado(bad: str) -> None:
    (record,) = _run(
        _lb(_game(Title="X", ApplicationPath="x.chd", CommunityStarRating=bad))
    ).records
    assert "rating" not in record.to_mapping()
    assert any(w.startswith("launchbox-rating") for w in record.warnings)


# -- sinalizadores da origem -------------------------------------------------


def test_entrada_marcada_como_quebrada_nao_entra_como_jogo_normal() -> None:
    """O usuário já registrou esse estado; escondê-lo seria falsear."""
    (record,) = _run(_lb(_game(Title="X", ApplicationPath="x.chd", Broken="true"))).records
    assert record.availability == "incompatible"


def test_entrada_oculta_na_origem_gera_aviso() -> None:
    (record,) = _run(_lb(_game(Title="X", ApplicationPath="x.chd", Hide="true"))).records
    assert "launchbox-entrada-oculta-na-origem" in record.warnings


def test_entrada_normal_fica_unknown() -> None:
    (record,) = _run(_lb(_game(Title="X", ApplicationPath="x.chd"))).records
    assert record.availability == "unknown"
    assert record.warnings == ()


# -- recusas ----------------------------------------------------------------


def test_jogo_sem_application_path_e_recusado() -> None:
    result = _run(_lb(_game(Title="Sem caminho")))
    assert result.records == ()
    assert result.skipped == (("Sem caminho", "launchbox-sem-application-path"),)


def test_path_que_escapa_da_raiz_e_recusado() -> None:
    result = _run(_lb(_game(Title="Hostil", ApplicationPath="..\\..\\etc\\passwd")))
    assert result.records == ()
    assert "launchbox-path-recusado" in result.skipped[0][1]


def test_xml_com_dtd_e_recusado() -> None:
    with pytest.raises(GameRecordError, match="DTD ou entidade"):
        _run('<!DOCTYPE LaunchBox [<!ENTITY x SYSTEM "file:///etc/passwd">]><LaunchBox/>')


def test_xml_malformado_falha_com_mensagem_de_contrato() -> None:
    with pytest.raises(GameRecordError, match="malformado"):
        _run("<LaunchBox><Game>")


def test_duplicado_e_recusado_uma_vez() -> None:
    result = _run(
        _lb(_game(Title="A", ApplicationPath="x.chd"), _game(Title="B", ApplicationPath=".\\x.chd"))
    )
    assert len(result.records) == 1
    assert result.skipped == (("B", "launchbox-id-duplicado"),)


def test_players_fora_de_faixa_vira_aviso() -> None:
    (record,) = _run(_lb(_game(Title="X", ApplicationPath="x.chd", MaxPlayers="999"))).records
    assert "players" not in record.to_mapping()
    assert "launchbox-players-fora-de-faixa" in record.warnings


def test_xml_vazio_nao_e_erro() -> None:
    assert _run(_lb()).records == ()


def test_system_root_relativo_e_recusado() -> None:
    with pytest.raises(GameRecordError, match="absoluto"):
        _run(_lb(_game(Title="X", ApplicationPath="x.chd")), system_root="roms/psx")


# -- fusão -------------------------------------------------------------------


def test_confianca_e_maior_que_a_da_playlist_do_retroarch() -> None:
    from steamzero.domain.metadata_import import launchbox, retroarch

    assert launchbox.CONFIDENCE > retroarch.CONFIDENCE


def test_reimportar_e_idempotente() -> None:
    xml = _lb(_game(Title="X", ApplicationPath="x.chd", Notes="Uma nota."))
    (primeiro,) = _run(xml).records
    (segundo,) = _run(xml).records
    assert primeiro.merge(segundo).record.to_mapping() == primeiro.to_mapping()
