# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Adapter de importação Pegasus (frente A1).

As duas armadilhas do formato têm teste próprio: continuação indentada de
``description`` (cortar no primeiro ``\\n`` truncaria o texto) e ``files:``
plural, que é multi-disco e não jogos separados.
"""

from __future__ import annotations

import pathlib

import pytest

from steamzero.domain.game_record import GameRecordError
from steamzero.domain.metadata_import import import_pegasus_metadata

ROOT = "/roms/psx"
WHEN = "2026-09-09T00:00:00Z"


def _run(text: str, *, system_root: str = ROOT):
    return import_pegasus_metadata(
        text, platform_id="psx", system_root=system_root, retrieved_at=WHEN
    )


def test_traduz_jogo_completo() -> None:
    (record,) = _run(
        """collection: Sony PlayStation
shortname: psx

game: Crash Bandicoot
file: Crash.chd
developer: Naughty Dog
publisher: Sony
genre: Plataforma, Ação
players: 1-2
release: 1996-09-09
"""
    ).records
    payload = record.to_mapping()
    assert record.title == "Crash Bandicoot"
    assert payload["path"] == "/roms/psx/Crash.chd"
    assert payload["developer"] == "Naughty Dog"
    assert payload["genres"] == ["Plataforma", "Ação"]
    assert payload["players"] == 2
    assert payload["releaseDate"] == "1996-09-09"


def test_cabecalho_da_colecao_nao_vira_jogo() -> None:
    result = _run("collection: Sony PlayStation\nshortname: psx\nextensions: chd\n")
    assert result.records == ()
    assert result.skipped == ()


def test_descricao_multilinha_indentada_e_preservada_inteira() -> None:
    """Cortar no primeiro \\n truncaria a descrição."""
    (record,) = _run(
        """game: X
file: x.chd
description:
  Primeira linha.
  Segunda linha.
  .
  Depois do parágrafo.
"""
    ).records
    description = record.to_mapping()["description"]
    assert "Primeira linha." in description
    assert "Segunda linha." in description
    assert "Depois do parágrafo." in description


def test_linha_com_ponto_e_paragrafo_em_branco_nao_fim_do_campo() -> None:
    (record,) = _run("game: X\nfile: x.chd\ndescription:\n  A\n  .\n  B\n").records
    assert record.to_mapping()["description"] == "A\n\nB"


def test_files_plural_e_multi_disco_e_nao_jogos_separados() -> None:
    result = _run(
        """game: Final Fantasy IX
files:
  ff9-d1.chd
  ff9-d2.chd
  ff9-d3.chd
"""
    )
    assert len(result.records) == 1
    payload = result.records[0].to_mapping()
    assert payload["path"] == "/roms/psx/ff9-d1.chd"
    assert [entry["disc"] for entry in payload["discSet"]] == [1, 2, 3]
    assert payload["discSet"][2]["path"] == "/roms/psx/ff9-d3.chd"


def test_arquivo_unico_nao_gera_disc_set() -> None:
    (record,) = _run("game: X\nfile: x.chd\n").records
    assert "discSet" not in record.to_mapping()


def test_varios_jogos_em_blocos_separados() -> None:
    result = _run("game: A\nfile: a.chd\n\ngame: B\nfile: b.chd\n")
    assert [record.title for record in result.records] == ["A", "B"]


def test_availability_fica_unknown() -> None:
    (record,) = _run("game: X\nfile: x.chd\n").records
    assert record.availability == "unknown"


def test_campo_ausente_nao_e_inventado() -> None:
    (record,) = _run("game: X\nfile: x.chd\n").records
    payload = record.to_mapping()
    for absent in ("description", "developer", "publisher", "genres", "players", "releaseDate"):
        assert absent not in payload


# -- recusas ----------------------------------------------------------------


def test_jogo_sem_file_e_recusado_com_motivo() -> None:
    result = _run("game: Sem arquivo\ndeveloper: X\n")
    assert result.records == ()
    assert result.skipped == (("Sem arquivo", "pegasus-sem-file"),)


def test_path_que_escapa_da_raiz_e_recusado() -> None:
    result = _run("game: Hostil\nfile: ../../etc/passwd\n")
    assert result.records == ()
    assert "pegasus-path-recusado" in result.skipped[0][1]


def test_um_disco_hostil_recusa_o_jogo_inteiro() -> None:
    """Importar meia lista de discos daria um multi-disco silenciosamente
    incompleto."""
    result = _run("game: X\nfiles:\n  d1.chd\n  ../../etc/passwd\n")
    assert result.records == ()
    assert "pegasus-path-recusado" in result.skipped[0][1]


def test_duplicado_e_recusado_uma_vez() -> None:
    result = _run("game: A\nfile: x.chd\n\ngame: B\nfile: ./x.chd\n")
    assert len(result.records) == 1
    assert result.skipped == (("B", "pegasus-id-duplicado"),)


@pytest.mark.parametrize("raw", ["1996", "09/09/1996", "ontem"])
def test_release_em_formato_desconhecido_vira_aviso_e_nao_data_inventada(raw: str) -> None:
    (record,) = _run(f"game: X\nfile: x.chd\nrelease: {raw}\n").records
    assert "releaseDate" not in record.to_mapping()
    assert "pegasus-release-invalida" in record.warnings


def test_players_sem_numero_vira_aviso() -> None:
    (record,) = _run("game: X\nfile: x.chd\nplayers: vários\n").records
    assert "players" not in record.to_mapping()
    assert "pegasus-players-invalido" in record.warnings


def test_arquivo_vazio_nao_e_erro() -> None:
    assert _run("").records == ()


def test_system_root_relativo_e_recusado() -> None:
    with pytest.raises(GameRecordError, match="absoluto"):
        _run("game: X\nfile: x.chd\n", system_root="roms/psx")


def test_reimportar_e_idempotente() -> None:
    text = "game: X\nfile: x.chd\ndeveloper: Estúdio\n"
    (primeiro,) = _run(text).records
    (segundo,) = _run(text).records
    assert primeiro.merge(segundo).record.to_mapping() == primeiro.to_mapping()


# -- validação contra dados reais --------------------------------------------

# ``reference/`` é material de pesquisa e NÃO é versionado (.gitignore:36), então
# este teste pula na CI e em qualquer checkout limpo. Ele existe porque fixture
# sintética prova apenas consistência com as suposições de quem a escreveu: só
# um arquivo real prova que o adapter entendeu o formato. Quando presente, é a
# evidência mais forte desta suíte.
_REAL = pathlib.Path(__file__).resolve().parents[2] / "reference" / "EmuDeck" / "android" / "roms"


@pytest.mark.skipif(not _REAL.is_dir(), reason="reference/ não versionado; checkout sem pesquisa")
def test_processa_arquivos_reais_sem_excecao_e_sem_recusa() -> None:
    files = sorted(_REAL.rglob("metadata.pegasus.txt"))
    assert files, "reference/ presente mas sem metadata.pegasus.txt"
    total = 0
    for path in files:
        result = _run(path.read_text(encoding="utf-8", errors="replace"))
        assert result.skipped == (), f"{path} produziu recusas: {result.skipped[:3]}"
        total += len(result.records)
    assert total > 0, "nenhum registro extraído de arquivos reais"


@pytest.mark.skipif(not _REAL.is_dir(), reason="reference/ não versionado; checkout sem pesquisa")
def test_extracao_real_bate_com_a_fonte() -> None:
    """Não basta não quebrar: os campos precisam bater com o arquivo."""
    path = _REAL / "mame" / "metadata.pegasus.txt"
    if not path.is_file():
        pytest.skip("coleção mame ausente na referência")
    result = import_pegasus_metadata(
        path.read_text(encoding="utf-8"),
        platform_id="mame",
        system_root="/roms/mame",
        retrieved_at=WHEN,
    )
    by_title = {record.title: record.to_mapping() for record in result.records}
    aqua = by_title.get("Aqua Jack (World)")
    assert aqua is not None
    assert aqua["path"] == "/roms/mame/aquajack.zip"
    assert aqua["developer"] == "Taito"
    assert aqua["publisher"] == "Taito"
    assert aqua["releaseDate"] == "1990-01-01"
    assert aqua["players"] == 1
    ids = [record.id for record in result.records]
    assert len(ids) == len(set(ids)), "IDs colidiram em biblioteca real"
