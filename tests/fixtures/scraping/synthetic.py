# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Payloads sintéticos e mínimos para testes de scraping.

Nenhum byte aqui é copiado de serviço externo: os artefatos são gerados no
próprio teste com magic bytes suficientes para a validação por assinatura.
"""

from __future__ import annotations

import json

#: PNG mínimo: assinatura + bytes de preenchimento (não decodificável de verdade,
#: suficiente para a checagem de magic bytes).
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 64

WEBP_BYTES = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 64

#: MP4: box size + ``ftyp`` (assinatura do container ISO BMFF).
MP4_BYTES = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00" + b"\x00" * 32

PDF_BYTES = b"%PDF-1.4\n" + b"\x00" * 64

#: Corpo de página de erro HTML — o "content-type enganoso" dos testes.
HTML_BYTES = b"<html><body>not an image</body></html>"


def screenscraper_json(medias: list[dict[str, object]]) -> bytes:
    """Monta payload JSON do ScreenScraper ``output=json``."""
    return json.dumps({"response": {"jeu": {"id": 1234, "medias": medias}}}).encode()


def screenscraper_error_json(code: str) -> bytes:
    """Monta payload de erro JSON do ScreenScraper."""
    return json.dumps({"error": {"code": code}}).encode()


def screenscraper_error_xml(code: str) -> bytes:
    """Monta payload de erro XML do ScreenScraper."""
    return (
        b'<?xml version="1.0"?>\n<data><error><code>' + code.encode() + b"</code></error></data>\n"
    )


def steamgriddb_json(data: object, *, success: bool = True) -> bytes:
    """Monta payload JSON do SteamGridDB v2."""
    return json.dumps({"success": success, "data": data}).encode()
