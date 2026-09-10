# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Adapter de importação Steam (frente A1).

Duas fontes com garantias distintas: o manifesto ``.acf``, escrito pelo próprio
cliente Steam, e o atalho não-Steam, que é o que o usuário digitou. A diferença
de confiança entre elas é testada, porque é ela que decide quem vence na fusão.

O decodificador binário de ``shortcuts.vdf`` NÃO é exercitado aqui: ele vive em
``adapters.steam_shortcuts`` e tem testes próprios. Este adapter recebe linhas
já decodificadas, e é isso que os testes usam.
"""

from __future__ import annotations

from typing import Any

import pytest

from steamzero.domain.game_record import GameRecordError
from steamzero.domain.metadata_import import import_steam_appmanifest, import_steam_shortcuts

ROOT = "/home/u/.steam/steamapps"
WHEN = "2026-09-09T00:00:00Z"


def _acf(**fields: str) -> str:
    body = "\n".join(f'\t"{key}"\t\t"{value}"' for key, value in fields.items())
    return '"AppState"\n{\n' + body + "\n}\n"


def _run(text: str, *, library_root: str = ROOT):
    return import_steam_appmanifest(text, library_root=library_root, retrieved_at=WHEN)


def _shortcuts(*rows: dict[str, Any]):
    return import_steam_shortcuts(list(rows), retrieved_at=WHEN)


# -- appmanifest -------------------------------------------------------------


def test_traduz_manifesto_completo() -> None:
    (record,) = _run(
        _acf(appid="220", name="Half-Life 2", installdir="Half-Life 2", SizeOnDisk="6300000000")
    ).records
    payload = record.to_mapping()
    assert record.id == "steam-220"
    assert record.title == "Half-Life 2"
    assert payload["path"] == "/home/u/.steam/steamapps/common/Half-Life 2"
    assert payload["size"] == 6300000000


def test_jogo_nativo_nao_e_forcado_no_molde_de_emulacao() -> None:
    """Forçá-lo produziria um registro que mente sobre como o jogo roda."""
    (record,) = _run(_acf(appid="220", name="HL2", installdir="hl2")).records
    payload = record.to_mapping()
    assert payload["container"] == "directory"
    for absent in ("core", "biosRequirements", "emulatorId"):
        assert absent not in payload


def test_id_vem_do_appid_e_e_estavel() -> None:
    a = _run(_acf(appid="440", name="TF2", installdir="tf2")).records[0]
    b = _run(_acf(appid="440", name="Team Fortress 2", installdir="tf2")).records[0]
    assert a.id == b.id == "steam-440"


def test_bloco_aninhado_nao_sobrescreve_chave_do_topo() -> None:
    """``InstalledDepots`` repete chaves; achatar faria o bloco vencer."""
    text = (
        '"AppState"\n{\n\t"appid"\t\t"220"\n\t"name"\t\t"Half-Life 2"\n'
        '\t"installdir"\t\t"Half-Life 2"\n'
        '\t"InstalledDepots"\n\t{\n\t\t"221"\n\t\t{\n'
        '\t\t\t"name"\t\t"NAO DEVE VENCER"\n\t\t\t"installdir"\t\t"errado"\n\t\t}\n\t}\n}\n'
    )
    (record,) = _run(text).records
    assert record.title == "Half-Life 2"
    assert record.to_mapping()["path"].endswith("/common/Half-Life 2")


def test_escapes_do_vdf_sao_desfeitos() -> None:
    (record,) = _run(_acf(appid="1", name='Jogo \\"Aspas\\"', installdir="jogo")).records
    assert record.title == 'Jogo "Aspas"'


def test_manifesto_sem_appid_e_recusado() -> None:
    result = _run(_acf(name="Sem id", installdir="x"))
    assert result.records == ()
    assert result.skipped == (("Sem id", "steam-appid-ausente-ou-invalido"),)


def test_appid_nao_numerico_e_recusado() -> None:
    result = _run(_acf(appid="abc", name="X", installdir="x"))
    assert result.skipped[0][1] == "steam-appid-ausente-ou-invalido"


def test_manifesto_sem_installdir_e_recusado() -> None:
    result = _run(_acf(appid="220", name="X"))
    assert result.skipped == (("X", "steam-sem-installdir"),)


def test_installdir_que_escapa_da_biblioteca_e_recusado() -> None:
    result = _run(_acf(appid="220", name="Hostil", installdir="../../../etc"))
    assert result.records == ()
    assert "steam-path-recusado" in result.skipped[0][1]


def test_library_root_relativo_e_recusado() -> None:
    with pytest.raises(GameRecordError, match="absoluto"):
        _run(_acf(appid="220", name="X", installdir="x"), library_root="steamapps")


def test_manifesto_vazio_nao_explode() -> None:
    result = _run("")
    assert result.records == ()
    assert result.skipped[0][1] == "steam-appid-ausente-ou-invalido"


def test_size_invalido_e_omitido_em_vez_de_zerado() -> None:
    (record,) = _run(_acf(appid="1", name="X", installdir="x", SizeOnDisk="muito")).records
    assert "size" not in record.to_mapping()


# -- atalhos não-Steam -------------------------------------------------------


def test_traduz_atalho() -> None:
    (record,) = _shortcuts({"AppName": "Meu Jogo", "Exe": '"/opt/jogo/run.sh"'}).records
    payload = record.to_mapping()
    assert record.title == "Meu Jogo"
    assert payload["path"] == "/opt/jogo/run.sh"


def test_aspas_do_executavel_sao_removidas() -> None:
    (record,) = _shortcuts({"AppName": "X", "Exe": '"/opt/a b/run.sh"'}).records
    assert record.to_mapping()["path"] == "/opt/a b/run.sh"


def test_atalho_sem_exe_e_recusado() -> None:
    result = _shortcuts({"AppName": "Sem exe"})
    assert result.records == ()
    assert result.skipped == (("Sem exe", "steam-atalho-sem-exe"),)


def test_atalho_com_exe_so_de_aspas_e_recusado() -> None:
    result = _shortcuts({"AppName": "X", "Exe": '""'})
    assert result.skipped[0][1] == "steam-atalho-sem-exe"


def test_atalho_duplicado_e_recusado_uma_vez() -> None:
    result = _shortcuts({"AppName": "X", "Exe": "/a"}, {"AppName": "X", "Exe": "/b"})
    assert len(result.records) == 1
    assert result.skipped[0][1] == "steam-atalho-duplicado"


def test_linha_que_nao_e_objeto_e_recusada() -> None:
    result = import_steam_shortcuts(["texto solto"], retrieved_at=WHEN)
    assert result.records == ()
    assert result.skipped[0][1] == "steam-atalho-nao-e-objeto"


def test_lista_vazia_nao_e_erro() -> None:
    assert _shortcuts().records == ()


# -- confiança relativa ------------------------------------------------------


def test_manifesto_e_mais_confiavel_que_atalho() -> None:
    """O cliente Steam é dono do manifesto; o atalho é o que o usuário digitou."""
    from steamzero.domain.metadata_import import steam

    assert steam.CONFIDENCE_MANIFEST > steam.CONFIDENCE_SHORTCUT


def test_manifesto_e_mais_confiavel_que_a_playlist_do_retroarch() -> None:
    from steamzero.domain.metadata_import import retroarch, steam

    assert steam.CONFIDENCE_MANIFEST > retroarch.CONFIDENCE


def test_origens_sao_distinguiveis_na_proveniencia() -> None:
    """Fundir manifesto com atalho exige saber de onde cada campo veio."""
    (manifesto,) = _run(_acf(appid="1", name="X", installdir="x")).records
    (atalho,) = _shortcuts({"AppName": "X", "Exe": "/opt/x"}).records
    entry_a = manifesto.provenance_of("title")
    entry_b = atalho.provenance_of("title")
    assert entry_a is not None and entry_b is not None
    assert entry_a.source != entry_b.source


def test_reimportar_e_idempotente() -> None:
    text = _acf(appid="220", name="Half-Life 2", installdir="hl2")
    (primeiro,) = _run(text).records
    (segundo,) = _run(text).records
    assert primeiro.merge(segundo).record.to_mapping() == primeiro.to_mapping()
