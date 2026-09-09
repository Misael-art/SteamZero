# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Adapter de importação RetroArch (frente A1).

Playlist é índice, não catálogo. O teste central desta suíte é que o registro
resultante seja **magro**: preencher o que a fonte não tem seria inventar dado.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from steamzero.domain.game_record import GameRecordError
from steamzero.domain.metadata_import import import_retroarch_playlist

ROOT = "/roms/psx"
WHEN = "2026-09-09T00:00:00Z"


def _run(text: str, *, system_root: str = ROOT):
    return import_retroarch_playlist(
        text, platform_id="psx", system_root=system_root, retrieved_at=WHEN
    )


def _lpl(*items: dict[str, Any]) -> str:
    return json.dumps({"version": "1.5", "items": list(items)})


def test_traduz_entrada_completa() -> None:
    (record,) = _run(
        _lpl(
            {
                "path": "/roms/psx/Crash.chd",
                "label": "Crash Bandicoot",
                "core_name": "Beetle PSX HW",
                "crc32": "ABCDEF01|crc",
            }
        )
    ).records
    payload = record.to_mapping()
    assert record.title == "Crash Bandicoot"
    assert payload["path"] == "/roms/psx/Crash.chd"
    assert payload["hashes"] == {"crc32": "abcdef01"}
    assert payload["core"] == "Beetle-PSX-HW"


def test_registro_e_magro_porque_a_fonte_e_um_indice() -> None:
    """A playlist não tem descrição, gênero, arte nem data — nada é inventado."""
    (record,) = _run(_lpl({"path": "/roms/psx/x.chd", "label": "X"})).records
    payload = record.to_mapping()
    for absent in ("description", "genres", "media", "releaseDate", "rating", "players"):
        assert absent not in payload


def test_confianca_e_menor_que_a_do_esde() -> None:
    """Rótulo de playlist costuma ser o nome do arquivo, não o título."""
    from steamzero.domain.metadata_import import esde, retroarch

    assert retroarch.CONFIDENCE < esde.CONFIDENCE


def test_core_detect_nao_vira_core() -> None:
    (record,) = _run(_lpl({"path": "/roms/psx/x.chd", "label": "X", "core_name": "DETECT"})).records
    assert "core" not in record.to_mapping()


def test_crc32_placeholder_de_zeros_e_ignorado() -> None:
    """Zeros são o "não calculado" do RetroArch, não um hash real."""
    (record,) = _run(
        _lpl({"path": "/roms/psx/x.chd", "label": "X", "crc32": "00000000|crc"})
    ).records
    assert "hashes" not in record.to_mapping()


@pytest.mark.parametrize("bad", ["zzzz", "ABC", "ABCDEF0", "ABCDEF012"])
def test_crc32_malformado_e_ignorado_em_vez_de_gravado(bad: str) -> None:
    (record,) = _run(_lpl({"path": "/roms/psx/x.chd", "label": "X", "crc32": bad})).records
    assert "hashes" not in record.to_mapping()


def test_entrada_de_arquivo_comprimido_usa_o_container() -> None:
    (record,) = _run(_lpl({"path": "/roms/psx/pack.zip#jogo.bin", "label": "X"})).records
    payload = record.to_mapping()
    assert payload["path"] == "/roms/psx/pack.zip"
    assert payload["container"] == "archive"


def test_titulo_cai_para_o_nome_do_arquivo_sem_label() -> None:
    (record,) = _run(_lpl({"path": "/roms/psx/Jogo.chd"})).records
    assert record.title == "Jogo"


def test_availability_fica_unknown() -> None:
    (record,) = _run(_lpl({"path": "/roms/psx/x.chd", "label": "X"})).records
    assert record.availability == "unknown"


# -- recusas ----------------------------------------------------------------


def test_formato_antigo_de_seis_linhas_e_recusado_com_mensagem_explicita() -> None:
    """Adivinhar o formato produziria caminhos falsos em silêncio."""
    antiga = "/roms/psx/x.chd\nX\nDETECT\nDETECT\n00000000|crc\npsx.lpl\n"
    with pytest.raises(GameRecordError, match="formato antigo"):
        _run(antiga)


def test_path_que_escapa_da_raiz_e_recusado() -> None:
    result = _run(_lpl({"path": "../../etc/passwd", "label": "Hostil"}))
    assert result.records == ()
    assert "retroarch-path-recusado" in result.skipped[0][1]


def test_item_sem_path_e_recusado() -> None:
    result = _run(_lpl({"label": "Sem caminho"}))
    assert result.records == ()
    assert result.skipped == (("?", "retroarch-sem-path"),)


def test_item_que_nao_e_objeto_e_recusado() -> None:
    result = _run(json.dumps({"items": ["texto solto"]}))
    assert result.records == ()
    assert result.skipped[0][1] == "retroarch-item-nao-e-objeto"


def test_duplicado_e_recusado_uma_vez() -> None:
    result = _run(
        _lpl({"path": "/roms/psx/x.chd", "label": "A"}, {"path": "./x.chd", "label": "B"})
    )
    assert len(result.records) == 1
    assert result.skipped == (("B", "retroarch-id-duplicado"),)


def test_json_malformado_falha_com_mensagem_de_contrato() -> None:
    with pytest.raises(GameRecordError, match="malformada"):
        _run('{"items": [')


def test_items_que_nao_e_lista_e_recusado() -> None:
    with pytest.raises(GameRecordError, match="não é lista"):
        _run(json.dumps({"items": {"path": "x"}}))


def test_playlist_vazia_e_sem_items_nao_sao_erro() -> None:
    assert _run("").records == ()
    assert _run(json.dumps({"version": "1.5"})).records == ()


def test_system_root_relativo_e_recusado() -> None:
    with pytest.raises(GameRecordError, match="absoluto"):
        _run(_lpl({"path": "./x.chd"}), system_root="roms/psx")


# -- fusão -------------------------------------------------------------------


def test_playlist_nao_apaga_titulo_mais_rico_de_outra_fonte() -> None:
    """O rótulo da playlist é pobre; keepRichest protege o título real."""
    from steamzero.domain.metadata_import import import_esde_gamelist

    (rico,) = import_esde_gamelist(
        "<gameList><game><path>./x.chd</path><name>Crash Bandicoot</name></game></gameList>",
        platform_id="psx",
        system_root=ROOT,
        retrieved_at=WHEN,
    ).records
    (pobre,) = _run(_lpl({"path": "/roms/psx/x.chd", "label": "x"})).records
    assert rico.merge(pobre).record.title == "Crash Bandicoot"
