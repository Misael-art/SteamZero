# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Testes do sanitizador de fixtures (tools/capture_screenscraper_payload.py).

O script captura respostas reais do ScreenScraper com credencial do operador e
grava o resultado em ``tests/fixtures/`` — caminho versionado. Estes testes são
a prova de que nada sensível sobrevive: credencial de aplicação, credencial de
conta, bloco ``ssuser`` e query string das URLs de mídia.

Regra do arquivo: todo segredo do payload de entrada é afirmado AUSENTE da
saída. Um sanitizador que silenciosamente para de casar reprova aqui.
"""

from __future__ import annotations

import json

import capture_screenscraper_payload as capture

_DEVID = "DEVID-DO-OPERADOR"
_DEVPASSWORD = "SENHA-DA-APLICACAO"
_SSID = "LOGIN-PESSOAL"
_SSPASSWORD = "SENHA-PESSOAL"
_ACCOUNT = "conta-do-operador"
_EMAIL = "operador@example.invalid"

_SECRETS = (_DEVID, _DEVPASSWORD, _SSID, _SSPASSWORD, _ACCOUNT, _EMAIL)

_MEDIA_URL = (
    "https://www.screenscraper.fr/image.php"
    f"?gameid=1&media=box-2D&devid={_DEVID}&devpassword={_DEVPASSWORD}"
)

_XML_PAYLOAD = f"""<?xml version="1.0"?>
<Data>
  <ssuser>
    <id>{_ACCOUNT}</id>
    <email>{_EMAIL}</email>
    <maxthreads>1</maxthreads>
  </ssuser>
  <devid>{_DEVID}</devid>
  <devpassword>{_DEVPASSWORD}</devpassword>
  <ssid>{_SSID}</ssid>
  <sspassword>{_SSPASSWORD}</sspassword>
  <jeu>
    <medias>
      <media type="box-2D" region="wor">{_MEDIA_URL}</media>
    </medias>
  </jeu>
</Data>
""".encode()

_JSON_PAYLOAD = json.dumps(
    {
        "response": {
            "ssuser": {"id": _ACCOUNT, "email": _EMAIL, "maxthreads": "1"},
            "jeu": {
                "id": "1",
                "medias": [{"type": "box-2D", "region": "wor", "url": _MEDIA_URL}],
            },
        }
    }
).encode()


def test_xml_sanitizer_removes_every_secret() -> None:
    out = capture._sanitize_xml(_XML_PAYLOAD).decode()
    leaked = [secret for secret in _SECRETS if secret in out]
    assert leaked == [], f"segredo sobreviveu ao sanitizador XML: {leaked}"


def test_json_sanitizer_removes_every_secret() -> None:
    out = capture._sanitize_json(_JSON_PAYLOAD).decode()
    leaked = [secret for secret in _SECRETS if secret in out]
    assert leaked == [], f"segredo sobreviveu ao sanitizador JSON: {leaked}"


def test_xml_sanitizer_preserves_structure_under_test() -> None:
    """O fixture precisa continuar exercitando o parser depois de higienizado."""
    out = capture._sanitize_xml(_XML_PAYLOAD).decode()
    assert "<jeu>" in out
    assert "<medias>" in out
    assert 'type="box-2D"' in out
    assert 'region="wor"' in out
    assert "<ssuser>" in out


def test_json_sanitizer_preserves_structure_under_test() -> None:
    payload = json.loads(capture._sanitize_json(_JSON_PAYLOAD))
    media = payload["response"]["jeu"]["medias"][0]
    assert media["type"] == "box-2D"
    assert media["region"] == "wor"
    assert media["url"].startswith("https://example.com/screenscraper/")


def test_media_url_query_string_is_not_merely_masked_in_place() -> None:
    """A URL inteira é trocada por placeholder — não basta mascarar o parâmetro."""
    out = capture._sanitize_xml(_XML_PAYLOAD).decode()
    assert "screenscraper.fr/image.php" not in out
    assert "https://example.com/screenscraper/" in out


def test_console_url_mask_hides_credentials() -> None:
    masked = capture._mask_url(
        f"https://www.screenscraper.fr/api2/jeuInfos.php?devid={_DEVID}"
        f"&devpassword={_DEVPASSWORD}&ssid={_SSID}&romnom=Jogo"
    )
    assert _DEVID not in masked
    assert _DEVPASSWORD not in masked
    assert _SSID not in masked
    assert "romnom=Jogo" in masked
