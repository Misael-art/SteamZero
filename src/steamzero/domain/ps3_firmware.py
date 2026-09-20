# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contrato de aquisição assistida do firmware oficial do PS3.

O contrato é deliberadamente estreito: apenas a URL publicada pela Sony para
o firmware 4.93, apenas ``PS3UPDAT.PUP`` e sem SHA-256 inventado. A política
``source-verified`` registra a origem e o hash observado; uma release futura
pode trocar para ``hash-pinned`` depois de revisão manual do mantenedor.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from steamzero.core import fs
from steamzero.core.errors import SteamZeroError

PS3_FIRMWARE_PLATFORM = "playstation-3"
PS3_FIRMWARE_VERSION = "4.93"
PS3_FIRMWARE_FILENAME = "PS3UPDAT.PUP"
PS3_FIRMWARE_SOURCE_URL = (
    "https://dbr01.ps3.update.playstation.net/update/ps3/image/br/"
    "2026_0318_a2b60b6ac1d2e49e230144345616927c/PS3UPDAT.PUP"
)
PS3_FIRMWARE_SOURCE_HOST = "dbr01.ps3.update.playstation.net"
PS3_FIRMWARE_INTEGRITY_POLICY = "source-verified"
PS3_FIRMWARE_MAX_BYTES = 512 * 1024 * 1024
PS3_FIRMWARE_MIN_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class Ps3FirmwareSource:
    platform_id: str = PS3_FIRMWARE_PLATFORM
    version: str = PS3_FIRMWARE_VERSION
    filename: str = PS3_FIRMWARE_FILENAME
    url: str = PS3_FIRMWARE_SOURCE_URL
    host: str = PS3_FIRMWARE_SOURCE_HOST
    integrity_policy: str = PS3_FIRMWARE_INTEGRITY_POLICY

    def validate(self) -> None:
        if (
            self.platform_id != PS3_FIRMWARE_PLATFORM
            or self.version != PS3_FIRMWARE_VERSION
            or self.filename != PS3_FIRMWARE_FILENAME
            or self.host != PS3_FIRMWARE_SOURCE_HOST
            or self.url != PS3_FIRMWARE_SOURCE_URL
        ):
            raise SteamZeroError(
                "E-CONTENT-FW-INCOMPAT",
                detail="o contrato do firmware não corresponde à fonte oficial aprovada",
            )
        parsed = urlsplit(self.url)
        if parsed.scheme != "https" or (parsed.hostname or "").casefold() != self.host:
            raise SteamZeroError(
                "E-CONTENT-FW-INCOMPAT",
                detail="a fonte do firmware não pertence à allowlist oficial da Sony",
            )
        if parsed.query or parsed.fragment or not parsed.path.endswith(f"/{self.filename}"):
            raise SteamZeroError(
                "E-CONTENT-FW-INCOMPAT",
                detail="a URL do firmware não corresponde ao arquivo oficial esperado",
            )
        if self.integrity_policy != PS3_FIRMWARE_INTEGRITY_POLICY:
            raise SteamZeroError(
                "E-API-SCHEMA",
                detail="hash-pinned exige digest revisado e ainda não está habilitado",
            )

    def to_dict(self) -> dict[str, str]:
        self.validate()
        return {
            "platformId": self.platform_id,
            "version": self.version,
            "filename": self.filename,
            "url": self.url,
            "host": self.host,
            "integrityPolicy": self.integrity_policy,
        }


@dataclass(frozen=True)
class Ps3FirmwareArtifact:
    source: Ps3FirmwareSource
    path: Path
    sha256: str
    size: int

    def metadata(self, *, installed_at: str | None = None) -> bytes:
        """Metadado privado para auditoria; não é conteúdo de firmware."""
        timestamp = installed_at or datetime.now(UTC).isoformat()
        payload = {
            "schemaVersion": 1,
            "state": "installed",
            "platformId": self.source.platform_id,
            "version": self.source.version,
            "filename": self.source.filename,
            "source": "Sony Interactive Entertainment",
            "sourceUrl": self.source.url,
            "integrityPolicy": self.source.integrity_policy,
            "sha256": self.sha256,
            "sizeBytes": self.size,
            "installedAt": timestamp,
        }
        return (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def validate_ps3_firmware(
    path: Path,
    source: Ps3FirmwareSource | None = None,
    *,
    min_bytes: int = PS3_FIRMWARE_MIN_BYTES,
    max_bytes: int = PS3_FIRMWARE_MAX_BYTES,
) -> Ps3FirmwareArtifact:
    contract = source or Ps3FirmwareSource()
    contract.validate()
    if path.is_symlink() or not path.is_file() or path.name != contract.filename:
        raise SteamZeroError(
            "E-CONTENT-FW-INCOMPAT",
            detail=f"o arquivo deve se chamar {contract.filename}",
        )
    size = path.stat().st_size
    if size < min_bytes:
        raise SteamZeroError(
            "E-CONTENT-INCOMPLETE",
            detail="o download do firmware parece truncado ou vazio",
        )
    if size > max_bytes:
        raise SteamZeroError(
            "E-CONTENT-LIMIT",
            detail="o firmware excede o limite seguro de download",
        )
    digest = fs.hash_file(path, algo="sha256")
    return Ps3FirmwareArtifact(contract, path, digest, size)
