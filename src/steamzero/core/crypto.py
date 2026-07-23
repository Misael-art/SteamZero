# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Primitivas de integridade e envelopes autenticados.

Não é um keyring e não persiste chaves. Material de chave chega apenas no ponto
de uso por uma porta/resolver injetado e nunca integra mensagens de erro.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import secrets
import stat
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from steamzero.core.errors import SteamZeroError

_CHUNK = 1 << 20
_DIGEST_LENGTHS = {"sha256": 64, "sha512": 128, "blake2b": 128}
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_ENVELOPE_BYTES = 16 * 1024 * 1024
_ENVELOPE_KEYS = frozenset(
    {"schemaVersion", "algorithm", "keyId", "nonce", "payload", "payloadSha256", "tag"}
)


@dataclass(frozen=True)
class Digest:
    algorithm: str
    hexdigest: str

    def __post_init__(self) -> None:
        algorithm = self.algorithm.casefold()
        expected = _DIGEST_LENGTHS.get(algorithm)
        value = self.hexdigest.casefold()
        if (
            expected is None
            or len(value) != expected
            or not all(c in "0123456789abcdef" for c in value)
        ):
            raise ValueError("digest inválido")
        object.__setattr__(self, "algorithm", algorithm)
        object.__setattr__(self, "hexdigest", value)

    @classmethod
    def parse(cls, value: str) -> Digest:
        if value.count(":") != 1:
            raise ValueError("checksum deve usar algoritmo:hex")
        algorithm, hexdigest = value.split(":", 1)
        return cls(algorithm, hexdigest)

    def __str__(self) -> str:
        return f"{self.algorithm}:{self.hexdigest}"


def digest_bytes(data: bytes, *, algorithm: str = "sha256") -> Digest:
    return Digest(algorithm, _new_hash(algorithm, data).hexdigest())


def digest_file(path: Path, *, algorithm: str = "sha256") -> Digest:
    """Hash de arquivo regular sem seguir symlink e sem materializar o conteúdo."""
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise SteamZeroError("E-STORAGE-IO", detail="arquivo não pôde ser aberto") from exc
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="hash exige arquivo regular")
        hasher = _new_hash(algorithm)
        while chunk := os.read(fd, _CHUNK):
            hasher.update(chunk)
        return Digest(algorithm, hasher.hexdigest())
    finally:
        os.close(fd)


def verify_bytes(data: bytes, expected: Digest | str) -> Digest:
    checksum = Digest.parse(expected) if isinstance(expected, str) else expected
    actual = digest_bytes(data, algorithm=checksum.algorithm)
    if not hmac.compare_digest(actual.hexdigest, checksum.hexdigest):
        raise SteamZeroError("E-SUPPLY-CHECKSUM", detail="checksum divergente")
    return actual


def verify_file(path: Path, expected: Digest | str) -> Digest:
    checksum = Digest.parse(expected) if isinstance(expected, str) else expected
    actual = digest_file(path, algorithm=checksum.algorithm)
    if not hmac.compare_digest(actual.hexdigest, checksum.hexdigest):
        raise SteamZeroError("E-SUPPLY-CHECKSUM", detail="checksum divergente")
    return actual


@dataclass(frozen=True)
class DetachedSignature:
    algorithm: str
    key_id: str
    signature: bytes

    def __post_init__(self) -> None:
        if not _SAFE_ID.fullmatch(self.algorithm) or not _SAFE_ID.fullmatch(self.key_id):
            raise ValueError("identificador de assinatura inválido")
        if not self.signature or len(self.signature) > 4096:
            raise ValueError("assinatura vazia ou excessiva")

    @classmethod
    def from_base64(cls, *, algorithm: str, key_id: str, value: str) -> DetachedSignature:
        try:
            decoded = base64.b64decode(value, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("assinatura base64 inválida") from exc
        return cls(algorithm=algorithm, key_id=key_id, signature=decoded)


class SignatureVerifierPort(Protocol):
    """Adapter de algoritmo assimétrico ou hardware-backed."""

    def verify(
        self,
        *,
        algorithm: str,
        key_id: str,
        payload: bytes,
        signature: bytes,
    ) -> bool: ...


def verify_detached_signature(
    payload: bytes,
    signature: DetachedSignature,
    verifier: SignatureVerifierPort,
) -> None:
    if not verifier.verify(
        algorithm=signature.algorithm,
        key_id=signature.key_id,
        payload=payload,
        signature=signature.signature,
    ):
        raise SteamZeroError("E-SUPPLY-CHECKSUM", detail="assinatura inválida")


class HmacSha256Verifier:
    """Verifier determinístico para envelopes locais; chaves são injetadas."""

    def __init__(self, key_resolver: Callable[[str], bytes | None]) -> None:
        self._key_resolver = key_resolver

    def verify(
        self,
        *,
        algorithm: str,
        key_id: str,
        payload: bytes,
        signature: bytes,
    ) -> bool:
        if algorithm != "hmac-sha256":
            return False
        key = self._key_resolver(key_id)
        if key is None or len(key) < 16:
            return False
        expected = hmac.digest(key, payload, "sha256")
        return hmac.compare_digest(expected, signature)


def seal_envelope(payload: bytes, *, key_id: str, key: bytes) -> bytes:
    """Serializa payload visível com integridade/autenticidade HMAC.

    O envelope não cifra o conteúdo e, portanto, nunca deve carregar segredo.
    """
    if not _SAFE_ID.fullmatch(key_id) or len(key) < 16:
        raise ValueError("key id ou chave inválida")
    if len(payload) > _MAX_ENVELOPE_BYTES:
        raise SteamZeroError("E-CONTENT-LIMIT", detail="payload excede limite do envelope")
    nonce = secrets.token_bytes(16)
    digest = hashlib.sha256(payload).hexdigest()
    signed = _envelope_signed_bytes(key_id, nonce, digest, payload)
    document = {
        "schemaVersion": 1,
        "algorithm": "hmac-sha256",
        "keyId": key_id,
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "payload": base64.b64encode(payload).decode("ascii"),
        "payloadSha256": digest,
        "tag": base64.b64encode(hmac.digest(key, signed, "sha256")).decode("ascii"),
    }
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")


def open_envelope(
    raw: bytes,
    *,
    key_resolver: Callable[[str], bytes | None],
    max_payload_bytes: int = _MAX_ENVELOPE_BYTES,
) -> bytes:
    if len(raw) > (max_payload_bytes * 2) + 4096:
        raise SteamZeroError("E-CONTENT-LIMIT", detail="envelope excede limite")
    try:
        document = json.loads(raw)
        if not isinstance(document, dict) or frozenset(document) != _ENVELOPE_KEYS:
            raise ValueError("campos inesperados")
        if document["schemaVersion"] != 1 or document["algorithm"] != "hmac-sha256":
            raise ValueError("schema ou algoritmo incompatível")
        key_id = document["keyId"]
        digest = document["payloadSha256"]
        if not isinstance(key_id, str) or not _SAFE_ID.fullmatch(key_id):
            raise ValueError("key id inválido")
        if not isinstance(digest, str):
            raise ValueError("digest inválido")
        Digest("sha256", digest)
        nonce = _decode_b64(document["nonce"], expected_length=16)
        tag = _decode_b64(document["tag"], expected_length=32)
        payload = _decode_b64(document["payload"], max_length=max_payload_bytes)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SteamZeroError("E-CONTENT-UNSUPPORTED", detail="envelope inválido") from exc
    key = key_resolver(key_id)
    if key is None or len(key) < 16:
        raise SteamZeroError("E-SUPPLY-CHECKSUM", detail="chave do envelope indisponível")
    if not hmac.compare_digest(hashlib.sha256(payload).hexdigest(), digest):
        raise SteamZeroError("E-SUPPLY-CHECKSUM", detail="digest do envelope divergente")
    signed = _envelope_signed_bytes(key_id, nonce, digest, payload)
    if not hmac.compare_digest(hmac.digest(key, signed, "sha256"), tag):
        raise SteamZeroError("E-SUPPLY-CHECKSUM", detail="autenticidade do envelope inválida")
    return payload


class _HashPort(Protocol):
    def update(self, data: bytes) -> None: ...
    def hexdigest(self) -> str: ...


def _new_hash(algorithm: str, data: bytes = b"") -> _HashPort:
    normalized = algorithm.casefold()
    if normalized not in _DIGEST_LENGTHS:
        raise ValueError("algoritmo de hash não permitido")
    return cast(_HashPort, hashlib.new(normalized, data))


def _decode_b64(
    value: object,
    *,
    expected_length: int | None = None,
    max_length: int | None = None,
) -> bytes:
    if not isinstance(value, str):
        raise ValueError("base64 deve ser texto")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("base64 inválido") from exc
    if expected_length is not None and len(decoded) != expected_length:
        raise ValueError("comprimento base64 inválido")
    if max_length is not None and len(decoded) > max_length:
        raise ValueError("conteúdo base64 excessivo")
    return decoded


def _envelope_signed_bytes(key_id: str, nonce: bytes, digest: str, payload: bytes) -> bytes:
    return b"\0".join(
        (b"steamzero-envelope-v1", key_id.encode("utf-8"), nonce, digest.encode("ascii"), payload)
    )
