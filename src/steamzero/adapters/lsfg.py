# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Instalação user-scoped, pinada e reversível do LSFG-VK.

Somente o artefato oficial sem UI é aceito. A aquisição é limitada, verificada
por SHA-256 e extraída em memória com uma allowlist exata de entradas. A escrita
em ``~/.local`` passa pelo núcleo transacional G-FULL.
"""

from __future__ import annotations

import hashlib
import io
import json
import platform
import stat
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from steamzero.core import fs, transaction
from steamzero.core.errors import SteamZeroError

LSFG_VERSION = "1.0.0"
LSFG_SOURCE_URL = "https://github.com/PancakeTAS/lsfg-vk/releases/download/v1.0.0/lsfg-vk_noui.zip"
LSFG_ARCHIVE_SHA256 = "af5ee1626d9543349245520689da107c3ebc5ef3755086441fbb854173b8e096"
LSFG_LIBRARY_SHA256 = "de4954bcce6904b62b6c48f1525c7fd78b4c2d7f9a959edf621528d9363ebbfd"
LSFG_APP_ID = "993090"

_MAX_ARCHIVE_BYTES = 2 * 1024 * 1024
_MAX_ENTRY_BYTES = 2 * 1024 * 1024
_LIB_ENTRY = "lib/liblsfg-vk.so"
_MANIFEST_ENTRY = "share/vulkan/implicit_layer.d/VkLayer_LS_frame_generation.json"
_EXPECTED_ENTRIES = frozenset({_LIB_ENTRY, _MANIFEST_ENTRY})


class LsfgArtifactPort(Protocol):
    def fetch(self, url: str, *, max_bytes: int) -> bytes: ...


class OfficialLsfgArtifact:
    """Aquisição HTTP restrita ao asset oficial pinado."""

    def fetch(self, url: str, *, max_bytes: int) -> bytes:
        if url != LSFG_SOURCE_URL or max_bytes > _MAX_ARCHIVE_BYTES:
            raise SteamZeroError("E-SUPPLY-UPSTREAM-GONE", detail="origem LSFG fora da allowlist")
        request = urllib.request.Request(  # noqa: S310 - URL fixa e allowlisted
            url,
            headers={"User-Agent": "SteamZero-LSFG/1"},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
                raw_length = response.headers.get("Content-Length")
                if raw_length is not None and int(raw_length) > max_bytes:
                    raise SteamZeroError(
                        "E-CONTENT-UNSAFE-ARCHIVE",
                        detail="artefato LSFG excede o limite de aquisição",
                    )
                payload = bytes(response.read(max_bytes + 1))
        except SteamZeroError:
            raise
        except (OSError, ValueError, urllib.error.URLError) as exc:
            raise SteamZeroError(
                "E-SUPPLY-OFFLINE", detail=f"não foi possível obter LSFG-VK: {exc}"
            ) from exc
        if len(payload) > max_bytes:
            raise SteamZeroError(
                "E-CONTENT-UNSAFE-ARCHIVE",
                detail="artefato LSFG excede o limite de aquisição",
            )
        return payload


class LsfgInstaller:
    """Planeja install/reinstall do runtime LSFG-VK sem privilégios."""

    def __init__(
        self,
        *,
        root: Path | None = None,
        artifacts: LsfgArtifactPort | None = None,
        lossless_probe: Callable[[], bool] = lambda: False,
        machine: Callable[[], str] = platform.machine,
    ) -> None:
        self._root = (root or (Path.home() / ".local")).resolve()
        self._artifacts = artifacts or OfficialLsfgArtifact()
        self._lossless_probe = lossless_probe
        self._machine = machine
        self._last_operation_id: str | None = None

    @property
    def manifest_path(self) -> Path:
        return self._root / _MANIFEST_ENTRY

    @property
    def library_path(self) -> Path:
        return self._root / _LIB_ENTRY

    def status(self) -> dict[str, Any]:
        lossless_installed = self._lossless_probe()
        supported = self._machine().casefold() in {"x86_64", "amd64"}
        manifest = self._read_manifest()
        library_hash = self._hash_regular(self.library_path)
        if manifest is None and library_hash is None:
            state = "missing"
            detail = "Camada Vulkan LSFG-VK ainda não preparada."
        elif (
            manifest is not None
            and manifest.get("library_path") == str(self.library_path)
            and library_hash == LSFG_LIBRARY_SHA256
        ):
            state = "ready"
            detail = "Camada Vulkan oficial verificada e pronta para perfis por jogo."
        else:
            state = "degraded"
            detail = "Arquivos LSFG-VK incompletos ou diferentes da versão pinada."
        return {
            "id": "lsfg-vk",
            "state": state,
            "statusLabel": {
                "ready": "Verificado",
                "missing": "Não instalado",
                "degraded": "Reparo necessário",
            }[state],
            "detail": detail,
            "version": LSFG_VERSION if state == "ready" else None,
            "source": "PancakeTAS/lsfg-vk",
            "archiveSha256": LSFG_ARCHIVE_SHA256,
            "losslessScalingInstalled": lossless_installed,
            "supportedHardware": supported,
            "installable": supported and lossless_installed,
            "lastOperationId": self._last_operation_id,
        }

    def plan_install(self) -> dict[str, Any]:
        status = self.status()
        if not status["supportedHardware"]:
            raise SteamZeroError(
                "E-COMPONENT-UNSUPPORTED-DISTRO",
                detail="LSFG-VK pinado suporta somente hosts x86_64",
            )
        if not status["losslessScalingInstalled"]:
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED",
                detail=(
                    "Lossless Scaling (Steam App 993090) precisa estar instalado; "
                    "o SteamZero não redistribui seus componentes proprietários"
                ),
            )
        archive = self._artifacts.fetch(LSFG_SOURCE_URL, max_bytes=_MAX_ARCHIVE_BYTES)
        digest = hashlib.sha256(archive).hexdigest()
        if digest != LSFG_ARCHIVE_SHA256:
            raise SteamZeroError(
                "E-SUPPLY-CHECKSUM",
                detail=f"LSFG-VK {LSFG_VERSION}: checksum do download divergente",
            )
        entries = self._extract_allowlisted(archive)
        if hashlib.sha256(entries[_LIB_ENTRY]).hexdigest() != LSFG_LIBRARY_SHA256:
            raise SteamZeroError(
                "E-SUPPLY-CHECKSUM", detail="biblioteca LSFG-VK não corresponde ao release"
            )
        manifest = self._normalized_manifest(entries[_MANIFEST_ENTRY])
        files = {
            self.library_path: entries[_LIB_ENTRY],
            self.manifest_path: manifest,
        }
        plan = transaction.plan_write_files(files, root=self._root, kind="component.lsfg.install")
        action = "Reparar" if status["state"] == "degraded" else "Instalar"
        if status["state"] == "ready":
            action = "Revalidar"
        return {
            "planId": plan.plan_id,
            "confirmToken": plan.confirm_token,
            "expiresAt": plan.expires_at,
            "componentId": "lsfg-vk",
            "version": LSFG_VERSION,
            "source": LSFG_SOURCE_URL,
            "sha256": LSFG_ARCHIVE_SHA256,
            "downloadBytes": len(archive),
            "changes": [
                f"{action} biblioteca Vulkan em {self.library_path}",
                f"{action} manifesto em {self.manifest_path}",
            ],
            "blockers": [],
            "rollbackGuarantee": plan.rollback_guarantee,
        }

    def apply(self, plan_id: str, confirm_token: str) -> dict[str, Any]:
        plan = transaction.load_plan(plan_id)
        if plan.kind != "component.lsfg.install" or Path(plan.root) != self._root:
            raise SteamZeroError(
                "E-TX-STALE-PLAN", detail="plano não pertence ao instalador LSFG-VK"
            )

        def verify() -> None:
            status = self.status()
            if status["state"] != "ready":
                raise RuntimeError(str(status["detail"]))

        result = transaction.apply(plan_id, confirm_token, smoke=verify)
        self._last_operation_id = result.operation_id
        return {
            "status": "installed",
            "componentId": "lsfg-vk",
            "version": LSFG_VERSION,
            "operationId": result.operation_id,
            "message": "LSFG-VK verificado; volte ao perfil Steam para habilitá-lo por jogo.",
        }

    def rollback(self, operation_id: str) -> dict[str, Any]:
        if operation_id != self._last_operation_id:
            raise SteamZeroError(
                "E-TX-STALE-PLAN", detail="operação LSFG não pertence a esta sessão"
            )
        result = transaction.rollback(operation_id, reason="lsfg-manual")
        self._last_operation_id = None
        return {
            "status": result.status,
            "operationId": operation_id,
            "message": "Arquivos LSFG-VK restaurados para o estado anterior.",
        }

    def _normalized_manifest(self, raw: bytes) -> bytes:
        try:
            data = json.loads(raw)
            layer = data["layer"]
            if not isinstance(layer, dict) or layer.get("name") != "VK_LAYER_LS_frame_generation":
                raise ValueError("nome da camada inesperado")
            layer["library_path"] = str(self.library_path)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise SteamZeroError(
                "E-CONTENT-UNSAFE-ARCHIVE", detail=f"manifesto Vulkan LSFG inválido: {exc}"
            ) from exc
        return (json.dumps(data, indent=2, sort_keys=True) + "\n").encode()

    @staticmethod
    def _extract_allowlisted(archive: bytes) -> dict[str, bytes]:
        try:
            with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
                infos = [info for info in bundle.infolist() if not info.is_dir()]
                names = {info.filename for info in infos}
                if names != _EXPECTED_ENTRIES or len(infos) != len(_EXPECTED_ENTRIES):
                    raise SteamZeroError(
                        "E-CONTENT-UNSAFE-ARCHIVE",
                        detail="estrutura do release LSFG-VK fora da allowlist",
                    )
                extracted: dict[str, bytes] = {}
                for info in infos:
                    mode = (info.external_attr >> 16) & 0xFFFF
                    if stat.S_ISLNK(mode) or info.file_size > _MAX_ENTRY_BYTES:
                        raise SteamZeroError(
                            "E-CONTENT-UNSAFE-ARCHIVE",
                            detail=f"entrada LSFG insegura: {info.filename}",
                        )
                    with bundle.open(info) as handle:
                        payload = handle.read(_MAX_ENTRY_BYTES + 1)
                    if len(payload) > _MAX_ENTRY_BYTES:
                        raise SteamZeroError(
                            "E-CONTENT-UNSAFE-ARCHIVE",
                            detail=f"entrada LSFG excede limite: {info.filename}",
                        )
                    extracted[info.filename] = payload
                return extracted
        except SteamZeroError:
            raise
        except (OSError, zipfile.BadZipFile) as exc:
            raise SteamZeroError(
                "E-CONTENT-UNSAFE-ARCHIVE", detail=f"release LSFG-VK inválido: {exc}"
            ) from exc

    def _read_manifest(self) -> dict[str, Any] | None:
        if not self.manifest_path.is_file() or self.manifest_path.is_symlink():
            return None
        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            layer = data.get("layer")
        except (OSError, TypeError, json.JSONDecodeError):
            return None
        return layer if isinstance(layer, dict) else None

    @staticmethod
    def _hash_regular(path: Path) -> str | None:
        if not path.is_file() or path.is_symlink():
            return None
        return fs.hash_file(path, algo="sha256")
