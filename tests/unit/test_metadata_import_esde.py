# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Adapter de importação ES-DE (frente A1).

Cobre a tradução feliz e, sobretudo, as recusas: caminho que escapa da raiz,
XML hostil, campo fora de faixa e entrada duplicada. Um importador que aceita
tudo é um importador que corrompe a biblioteca em silêncio.

Fixtures são sintéticas e o adapter não lê disco: nenhuma biblioteca real é
tocada por estes testes.
"""

from __future__ import annotations

import pytest

from steamzero.domain.game_record import GameRecordError
from steamzero.domain.metadata_import import import_esde_gamelist

ROOT = "/roms/psx"
WHEN = "2026-09-09T00:00:00Z"


def _run(xml: str, *, platform_id: str = "psx", system_root: str = ROOT):
    return import_esde_gamelist(
        xml, platform_id=platform_id, system_root=system_root, retrieved_at=WHEN
    )


def _gamelist(*games: str) -> str:
    return "<?xml version='1.0'?><gameList>" + "".join(games) + "</gameList>"


def _game(**fields: str) -> str:
    body = "".join(f"<{tag}>{value}</{tag}>" for tag, value in fields.items())
    return f"<game>{body}</game>"


# -- tradução ---------------------------------------------------------------


def test_traduz_jogo_completo() -> None:
    result = _run(
        _gamelist(
            _game(
                path="./Crash.chd",
                name="Crash Bandicoot",
                desc="Um marsupial.",
                developer="Naughty Dog",
                publisher="Sony",
                genre="Plataforma",
                players="1-2",
                rating="0.85",
                releasedate="19960909T000000",
                image="./media/crash.png",
            )
        )
    )
    assert result.skipped == ()
    (record,) = result.records
    payload = record.to_mapping()
    assert record.title == "Crash Bandicoot"
    assert payload["path"] == "/roms/psx/Crash.chd"
    assert payload["developer"] == "Naughty Dog"
    assert payload["genres"] == ["Plataforma"]
    assert payload["players"] == 2
    assert payload["rating"] == 8.5
    assert payload["releaseDate"] == "1996-09-09"
    assert payload["media"]["cover"] == {"path": "/roms/psx/media/crash.png", "format": "png"}


def test_campo_ausente_fica_ausente_e_nao_e_inventado() -> None:
    (record,) = _run(_gamelist(_game(path="./x.chd", name="X"))).records
    payload = record.to_mapping()
    for absent in ("description", "developer", "publisher", "rating", "players", "media"):
        assert absent not in payload


def test_availability_fica_unknown_porque_o_adapter_nao_le_disco() -> None:
    """Afirmar ``available`` sem olhar o arquivo seria inventar estado."""
    (record,) = _run(_gamelist(_game(path="./x.chd", name="X"))).records
    assert record.availability == "unknown"


def test_titulo_cai_para_o_nome_do_arquivo_quando_nao_ha_name() -> None:
    (record,) = _run(_gamelist(_game(path="./Sem Nome.chd"))).records
    assert record.title == "Sem Nome"


def test_proveniencia_registra_origem_e_politica_por_campo() -> None:
    (record,) = _run(_gamelist(_game(path="./x.chd", name="X", developer="Estúdio"))).records
    entry = record.provenance_of("developer")
    assert entry is not None
    assert entry.source == "esde"
    assert entry.retrieved_at == WHEN
    assert entry.conflict_policy.value == "keepRichest"


def test_proveniencia_nao_cobre_campos_de_controle() -> None:
    (record,) = _run(_gamelist(_game(path="./x.chd", name="X"))).records
    assert record.provenance_of("schemaVersion") is None


# -- recusas ----------------------------------------------------------------


@pytest.mark.parametrize(
    "hostile",
    ["../../etc/passwd", "./../../etc/passwd", "~/segredo.chd"],
)
def test_caminho_que_escapa_da_raiz_e_recusado(hostile: str) -> None:
    """Normalizar em silêncio viraria leitura de arquivo arbitrário."""
    result = _run(_gamelist(_game(path=hostile, name="Hostil")))
    assert result.records == ()
    assert len(result.skipped) == 1
    assert "esde-path-recusado" in result.skipped[0][1]


def test_jogo_sem_path_e_recusado_com_motivo() -> None:
    result = _run(_gamelist(_game(name="Sem caminho")))
    assert result.records == ()
    assert result.skipped == (("Sem caminho", "esde-sem-path"),)


def test_entrada_duplicada_e_recusada_uma_vez_so() -> None:
    result = _run(_gamelist(_game(path="./x.chd", name="A"), _game(path="./x.chd", name="B")))
    assert len(result.records) == 1
    assert result.skipped == (("B", "esde-id-duplicado"),)


def test_xml_malformado_falha_com_mensagem_de_contrato() -> None:
    with pytest.raises(GameRecordError, match="malformado"):
        _run("<gameList><game>")


def test_system_root_relativo_e_recusado() -> None:
    with pytest.raises(GameRecordError, match="absoluto"):
        _run(_gamelist(_game(path="./x.chd")), system_root="roms/psx")


def test_gamelist_vazio_nao_e_erro() -> None:
    result = _run(_gamelist())
    assert result.records == ()
    assert result.skipped == ()


# -- normalização de campos hostis -------------------------------------------


@pytest.mark.parametrize("raw", ["2.0", "-0.5", "muito bom"])
def test_rating_invalido_vira_ausencia_com_aviso_e_nao_numero_inventado(raw: str) -> None:
    (record,) = _run(_gamelist(_game(path="./x.chd", name="X", rating=raw))).records
    payload = record.to_mapping()
    assert "rating" not in payload
    assert any(w.startswith("esde-rating") for w in record.warnings)


def test_players_com_texto_livre_aproveita_o_maximo() -> None:
    (record,) = _run(_gamelist(_game(path="./x.chd", name="X", players="2-4"))).records
    assert record.to_mapping()["players"] == 4


def test_players_sem_numero_vira_ausencia_com_aviso() -> None:
    (record,) = _run(_gamelist(_game(path="./x.chd", name="X", players="vários"))).records
    assert "players" not in record.to_mapping()
    assert "esde-players-invalido" in record.warnings


def test_media_de_formato_desconhecido_e_descartada_com_aviso() -> None:
    (record,) = _run(_gamelist(_game(path="./x.chd", name="X", image="./a.psd"))).records
    payload = record.to_mapping()
    assert "media" not in payload
    assert "esde-media-formato-desconhecido-cover" in record.warnings


def test_media_que_escapa_da_raiz_e_descartada_sem_derrubar_o_jogo() -> None:
    (record,) = _run(_gamelist(_game(path="./x.chd", name="X", image="../../../a.png"))).records
    assert "media" not in record.to_mapping()
    assert "esde-media-recusada-cover" in record.warnings


def test_video_usa_formato_de_video_e_nao_de_imagem() -> None:
    (record,) = _run(_gamelist(_game(path="./x.chd", name="X", video="./v.mp4"))).records
    assert record.to_mapping()["media"]["video"] == {"path": "/roms/psx/v.mp4", "format": "mp4"}


def test_video_com_extensao_de_imagem_e_descartado() -> None:
    (record,) = _run(_gamelist(_game(path="./x.chd", name="X", video="./v.png"))).records
    assert "media" not in record.to_mapping()


# -- integração com a fusão --------------------------------------------------


def test_reimportar_o_mesmo_gamelist_e_idempotente() -> None:
    xml = _gamelist(_game(path="./x.chd", name="X", desc="Uma descrição."))
    (primeiro,) = _run(xml).records
    (segundo,) = _run(xml).records
    assert primeiro.merge(segundo).record.to_mapping() == primeiro.to_mapping()


def test_gamelist_pobre_nao_apaga_descricao_mais_rica() -> None:
    """A invariante do plano: formato pobre não destrói informação rica."""
    (rico,) = _run(_gamelist(_game(path="./x.chd", name="X", desc="Descrição longa."))).records
    (pobre,) = _run(_gamelist(_game(path="./x.chd", name="X", desc="."))).records
    assert rico.merge(pobre).record.to_mapping()["description"] == "Descrição longa."


@pytest.mark.parametrize(
    "hostile",
    [
        '<!DOCTYPE gameList [<!ENTITY x SYSTEM "file:///etc/passwd">]><gameList/>',
        "<!doctype gameList><gameList><game><path>&x;</path></game></gameList>",
        '<?xml version="1.0"?><!ENTITY e "x"><gameList/>',
    ],
)
def test_xml_com_dtd_ou_entidade_e_recusado(hostile: str) -> None:
    """XXE: recusar é mais barato e mais verificável que desarmar o parser."""
    with pytest.raises(GameRecordError, match="DTD ou entidade"):
        _run(hostile)


def test_diretorio_irmao_com_prefixo_igual_nao_e_aceito_como_interno() -> None:
    """``/roms/psx-mal`` NÃO está sob ``/roms/psx``; startswith deixaria passar."""
    result = _run(_gamelist(_game(path="/roms/psx-mal/x.chd", name="Vizinho")))
    assert result.records == ()
    assert "esde-path-recusado" in result.skipped[0][1]


def test_caminho_absoluto_dentro_da_raiz_e_aceito() -> None:
    (record,) = _run(_gamelist(_game(path="/roms/psx/ok.chd", name="OK"))).records
    assert record.to_mapping()["path"] == "/roms/psx/ok.chd"
