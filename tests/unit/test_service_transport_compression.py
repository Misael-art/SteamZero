# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Compressão negociada no transporte do core (respostas grandes).

O cap de 1 MiB por frame é propriedade de segurança do transporte; o que
faltava era o caminho para respostas legítimas maiores que ele — o
``emulation workspace`` num acervo real já nasce acima do cap. A negociação
é por campo de extensão no request (``acceptGzip``): servidor antigo ignora,
cliente antigo nunca envia.
"""

from __future__ import annotations

import base64
import gzip
import json

import pytest

from steamzero.service import client as client_mod
from steamzero.service import core as core_mod


def _big_response(rows: int = 3000) -> dict:
    """Resultado grande e repetitivo — a forma real do workspace."""
    return {
        "jsonrpc": "2.0",
        "id": 7,
        "result": {
            "envelope": {
                "domain": "emulation",
                "action": "workspace",
                "data": {
                    "games": [
                        {
                            "id": f"game-{index:06d}",
                            "name": f"Jogo de Teste {index:06d}",
                            "platform": "master-system",
                            "state": "ready",
                        }
                        for index in range(rows)
                    ]
                },
            },
            "exitCode": 0,
        },
    }


def test_encode_compresses_only_when_negotiated_and_large() -> None:
    response = _big_response()

    plain = core_mod._encode_response(response, accept_gzip=False)
    assert b"__payload" not in plain
    assert json.loads(plain) == response

    negotiated = core_mod._encode_response(response, accept_gzip=True)
    assert len(negotiated) < len(plain)
    wrapped = json.loads(negotiated)
    assert wrapped["result"]["__payload"] == "gzip+base64"
    assert wrapped["id"] == 7


def test_encode_keeps_small_and_error_responses_plain() -> None:
    small = {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}
    assert core_mod._encode_response(small, accept_gzip=True) == json.dumps(
        small, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")

    big_error = {
        "jsonrpc": "2.0",
        "id": 2,
        "error": {"code": -32603, "data": "x" * (core_mod._COMPRESS_THRESHOLD + 1024)},
    }
    plain = core_mod._encode_response(big_error, accept_gzip=True)
    assert b"__payload" not in plain


def test_roundtrip_encode_then_unwrap_returns_original() -> None:
    response = _big_response()
    wire = core_mod._encode_response(response, accept_gzip=True)
    # O frame na rede precisa caber no cap do transporte.
    assert len(wire) <= client_mod._MAX_RESPONSE

    wrapped = json.loads(wire)
    assert client_mod._unwrap_result(wrapped["result"]) == response["result"]


def test_unwrap_passes_plain_result_through() -> None:
    result = {"envelope": {"ok": True}}
    assert client_mod._unwrap_result(result) is result


def test_unwrap_refuses_malformed_compressed_result() -> None:
    from steamzero.service.client import CoreProtocolError

    with pytest.raises(CoreProtocolError):
        client_mod._unwrap_result({"__payload": "gzip+base64"})
    with pytest.raises(CoreProtocolError):
        client_mod._unwrap_result({"__payload": "gzip+base64", "data": "###", "decodedSize": 10})


def test_unwrap_refuses_size_mismatch() -> None:
    from steamzero.service.client import CoreProtocolError

    raw = json.dumps({"ok": True}).encode("utf-8")
    data = base64.b64encode(gzip.compress(raw)).decode("ascii")
    with pytest.raises(CoreProtocolError, match="tamanho declarado"):
        client_mod._unwrap_result(
            {"__payload": "gzip+base64", "data": data, "decodedSize": len(raw) + 1}
        )


def test_unwrap_refuses_oversized_decoded_payload() -> None:
    from steamzero.service.client import CoreResponseTooLarge

    raw = b'{"pad": "' + b"0" * (client_mod._MAX_DECODED + 1024) + b'"}'
    data = base64.b64encode(gzip.compress(raw)).decode("ascii")
    with pytest.raises(CoreResponseTooLarge):
        client_mod._unwrap_result(
            {"__payload": "gzip+base64", "data": data, "decodedSize": len(raw)}
        )


def test_encode_refuses_logical_overflow_with_honest_error() -> None:
    response = _big_response(rows=200_000)
    assert len(json.dumps(response, ensure_ascii=False)) > core_mod._MAX_LOGICAL_RESPONSE

    wire = core_mod._encode_response(response, accept_gzip=True)
    wrapped = json.loads(wire)
    assert "error" in wrapped
    assert "excede o limite" in wrapped["error"]["message"]


def test_request_accepts_gzip_reads_extension_field() -> None:
    assert core_mod._request_accepts_gzip(
        b'{"jsonrpc":"2.0","id":1,"method":"m","params":{},"acceptGzip":true}\n'
    )
    assert not core_mod._request_accepts_gzip(
        b'{"jsonrpc":"2.0","id":1,"method":"m","params":{}}\n'
    )
    assert not core_mod._request_accepts_gzip(b"nao-json\n")
