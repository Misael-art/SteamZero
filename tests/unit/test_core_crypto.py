from __future__ import annotations

import base64
import hashlib
import hmac
import json
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from steamzero.core.crypto import (
    DetachedSignature,
    Digest,
    HmacSha256Verifier,
    digest_bytes,
    digest_file,
    open_envelope,
    seal_envelope,
    verify_bytes,
    verify_detached_signature,
    verify_file,
)
from steamzero.core.errors import SteamZeroError


def test_digests_are_canonical_and_constant_time_verified(tmp_path: Path) -> None:
    payload = b"steamzero"
    expected = hashlib.sha256(payload).hexdigest()
    assert str(digest_bytes(payload)) == f"sha256:{expected}"
    assert digest_file(_write_fixture(tmp_path, payload)).hexdigest == expected
    assert verify_bytes(payload, f"sha256:{expected}").hexdigest == expected
    actual = verify_file(_write_fixture(tmp_path, payload), Digest("sha256", expected))
    assert actual.hexdigest == expected

    with pytest.raises(SteamZeroError, match="E-SUPPLY-CHECKSUM"):
        verify_bytes(payload, f"sha256:{'0' * 64}")


@pytest.mark.parametrize(
    "value",
    ["sha1:00", "sha256", "sha256:xyz", f"sha256:{'0' * 63}", f"sha512:{'0' * 64}"],
)
def test_digest_parser_rejects_ambiguous_or_unapproved_values(value: str) -> None:
    with pytest.raises(ValueError):
        Digest.parse(value)


def test_digest_file_refuses_symlink_and_non_regular(tmp_path: Path) -> None:
    target = _write_fixture(tmp_path, b"x")
    link = tmp_path / "link"
    link.symlink_to(target)
    with pytest.raises(SteamZeroError):
        digest_file(link)
    with pytest.raises(SteamZeroError):
        digest_file(tmp_path)


def test_detached_signature_uses_injected_verifier() -> None:
    key = b"k" * 32
    payload = b"manifest"
    raw_signature = hmac.digest(key, payload, "sha256")
    signature = DetachedSignature.from_base64(
        algorithm="hmac-sha256",
        key_id="test-key",
        value=base64.b64encode(raw_signature).decode(),
    )
    verifier = HmacSha256Verifier(lambda key_id: key if key_id == "test-key" else None)
    verify_detached_signature(payload, signature, verifier)

    with pytest.raises(SteamZeroError, match="E-SUPPLY-CHECKSUM"):
        verify_detached_signature(payload + b"!", signature, verifier)
    assert verifier.verify(
        algorithm="ed25519",
        key_id="test-key",
        payload=payload,
        signature=raw_signature,
    ) is False


def test_detached_signature_parser_is_bounded() -> None:
    with pytest.raises(ValueError):
        DetachedSignature.from_base64(algorithm="bad space", key_id="key", value="AA==")
    with pytest.raises(ValueError):
        DetachedSignature.from_base64(algorithm="hmac-sha256", key_id="key", value="not-base64")
    with pytest.raises(ValueError):
        DetachedSignature("hmac-sha256", "key", b"x" * 4097)


def test_authenticated_envelope_roundtrip_and_tamper_detection() -> None:
    key = b"local-key-material-with-32-bytes!"
    raw = seal_envelope(b"visible metadata", key_id="vault:test", key=key)
    assert b"local-key-material" not in raw
    opened = open_envelope(
        raw,
        key_resolver=lambda key_id: key if key_id == "vault:test" else None,
    )
    assert opened == b"visible metadata"

    document = json.loads(raw)
    document["payload"] = base64.b64encode(b"tampered").decode()
    tampered = json.dumps(document).encode()
    with pytest.raises(SteamZeroError, match="E-SUPPLY-CHECKSUM"):
        open_envelope(tampered, key_resolver=lambda _key_id: key)

    with pytest.raises(SteamZeroError, match="E-SUPPLY-CHECKSUM"):
        open_envelope(raw, key_resolver=lambda _key_id: None)


@given(st.binary(max_size=1024))
def test_envelope_parser_roundtrips_arbitrary_binary(payload: bytes) -> None:
    key = b"k" * 32
    raw = seal_envelope(payload, key_id="property-key", key=key)
    assert open_envelope(raw, key_resolver=lambda _key_id: key) == payload


@given(st.binary(max_size=512))
def test_external_bytes_never_escape_as_untyped_parser_failures(raw: bytes) -> None:
    try:
        open_envelope(raw, key_resolver=lambda _key_id: b"k" * 32, max_payload_bytes=256)
    except SteamZeroError as exc:
        assert exc.code in {"E-CONTENT-LIMIT", "E-CONTENT-UNSUPPORTED", "E-SUPPLY-CHECKSUM"}


def test_envelope_limits_and_schema_are_fail_closed() -> None:
    with pytest.raises(ValueError):
        seal_envelope(b"x", key_id="bad key", key=b"k" * 32)
    with pytest.raises(ValueError):
        seal_envelope(b"x", key_id="key", key=b"short")
    with pytest.raises(SteamZeroError, match="E-CONTENT-LIMIT"):
        open_envelope(b"x" * 5000, key_resolver=lambda _key_id: b"k" * 32, max_payload_bytes=1)
    with pytest.raises(SteamZeroError, match="E-CONTENT-UNSUPPORTED"):
        open_envelope(b"{}", key_resolver=lambda _key_id: b"k" * 32)


def _write_fixture(tmp_path: Path, data: bytes) -> Path:
    path = tmp_path / "fixture.bin"
    path.write_bytes(data)
    return path
