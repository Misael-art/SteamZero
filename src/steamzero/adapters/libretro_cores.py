# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Executor transacional dos cores Libretro publicados em arquivo 7z pinado.

O Buildbot do Libretro publica os cores Linux em um arquivo único. Este módulo
nunca extrai o arquivo inteiro nem aceita nomes vindos do cliente: cada adapter
declara um único core e seu digest, a entrada do 7z é conferida contra o caminho
canônico e só então é copiada para o diretório do RetroArch dentro de um plano
confirmável. Arquivo de terceiro no destino não é sobrescrito.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from steamzero.adapters.engine import ArtifactPort
from steamzero.adapters.registry import AdapterManifest, AdapterRegistry, AdapterSource
from steamzero.core import crypto, fs, paths, transaction
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore

_ARCHIVE_PREFIX = (
    "RetroArch-Linux-x86_64/RetroArch-Linux-x86_64.AppImage.home/.config/retroarch/cores/"
)
_MAX_CORE_BYTES = 128 * 1024 * 1024
_METADATA_DIR = ".steamzero-managed"
_ARCHIVE_OK = 0
_ARCHIVE_EOF = 1
_READ_CHUNK = 1024 * 1024

ArchiveReader = Callable[[bytes, str], bytes]


@dataclass(frozen=True)
class PreparedLibretroCore:
    manifest: AdapterManifest
    source: AdapterSource
    plan: transaction.Plan


class LibretroCoreExecutor:
    """Instala um core declarado sem tocar nos demais arquivos do RetroArch."""

    def __init__(
        self,
        store: StateStore,
        registry: AdapterRegistry,
        artifacts: ArtifactPort,
        *,
        core_root: Path | None = None,
        archive_reader: ArchiveReader | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._artifacts = artifacts
        self._root = core_root or _default_core_root()
        self._archive_reader = archive_reader or _extract_7z_member
        fs.ensure_dir(self._root)

    def status(self, adapter_id: str) -> dict[str, object]:
        manifest, source, core_id, digest = self._details(adapter_id)
        target = self._target(core_id)
        metadata = self._metadata_path(manifest.id)
        if not target.exists() and not target.is_symlink() and not metadata.exists():
            return {"id": adapter_id, "state": "missing"}
        try:
            if target.is_symlink() or not target.is_file():
                raise ValueError("core ausente ou não é arquivo regular")
            if metadata.is_symlink() or not metadata.is_file():
                raise ValueError("metadados de ownership ausentes")
            raw = json.loads(metadata.read_text(encoding="utf-8"))
            if raw != self._metadata(manifest, source, core_id, digest):
                raise ValueError("metadados do core divergem do manifesto")
            if target.stat().st_size > _MAX_CORE_BYTES:
                raise ValueError("core excede o limite de tamanho")
            if fs.hash_file(target, algo="sha256") != digest:
                raise ValueError("checksum do core diverge")
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            return {
                "id": adapter_id,
                "state": "degraded",
                "version": source.version,
                "origin": source.type,
                "detail": str(exc),
            }
        return {
            "id": adapter_id,
            "state": "installed",
            "version": source.version,
            "origin": source.type,
            "sha256": digest,
        }

    def plan_install(self, adapter_id: str, *, force: bool = False) -> PreparedLibretroCore:
        manifest, source, core_id, digest = self._details(adapter_id)
        target = self._target(core_id)
        metadata_path = self._metadata_path(manifest.id)
        status = self.status(adapter_id)
        if status["state"] == "installed" and not force:
            return PreparedLibretroCore(
                manifest,
                source,
                transaction.plan_write_files({}, root=self._root, kind="libretro.install"),
            )
        present = (
            target.exists()
            or target.is_symlink()
            or metadata_path.exists()
            or metadata_path.is_symlink()
        )
        if present and not self._owned_target(manifest, source, core_id, digest):
            raise SteamZeroError(
                "E-CONTENT-INCOMPLETE",
                detail="core existente não é gerenciado pelo SteamZero; recusa sobrescrever",
            )

        extracted = self._extract_verified(manifest, source, core_id, digest)
        metadata = json.dumps(
            self._metadata(manifest, source, core_id, digest),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        plan = transaction.plan_copy_files(
            {extracted: target},
            root=self._root,
            kind="libretro.install",
            writes={metadata_path: metadata},
            replace_existing=target.exists() or target.is_symlink(),
        )
        return PreparedLibretroCore(manifest, source, plan)

    def plan_uninstall(self, adapter_id: str) -> PreparedLibretroCore:
        manifest, source, core_id, digest = self._details(adapter_id)
        if not self._owned_target(manifest, source, core_id, digest):
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED",
                detail="core ausente ou sem ownership verificável; recusa remover",
            )
        plan = transaction.plan_write_files(
            {},
            root=self._root,
            kind="libretro.uninstall",
            removals={self._target(core_id), self._metadata_path(manifest.id)},
        )
        return PreparedLibretroCore(manifest, source, plan)

    def apply(self, prepared: PreparedLibretroCore, confirm_token: str) -> transaction.ApplyResult:
        def verify() -> None:
            expected = "missing" if prepared.plan.kind == "libretro.uninstall" else "installed"
            if self.status(prepared.manifest.id)["state"] != expected:
                raise RuntimeError("estado do core após apply não confere com o plano")

        result = transaction.apply(prepared.plan.plan_id, confirm_token, smoke=verify)
        try:
            self.persist_status(prepared.manifest.id)
        except Exception:
            transaction.rollback(result.operation_id, reason="libretro-state-failed")
            raise
        return result

    def validate_plan(self, prepared: PreparedLibretroCore) -> None:
        """Recusa um plano delegado trocado antes de qualquer efeito.

        O envelope de lifecycle aponta para um ``transactionPlanId``. A leitura
        desse arquivo deve provar que ainda é o plano pendente deste adapter,
        dentro da raiz de cores gerenciada, e que não carrega alvo adicional.
        """
        manifest, _source, core_id, _digest = self._details(prepared.manifest.id)
        plan = prepared.plan
        if plan.status != "pending":
            raise SteamZeroError("E-TX-STALE-PLAN", detail="plano de core não está pendente")
        if plan.kind not in {"libretro.install", "libretro.uninstall"}:
            raise SteamZeroError("E-TX-STALE-PLAN", detail="plano não pertence a um core Libretro")
        if Path(plan.root) != self._root:
            raise SteamZeroError("E-TX-STALE-PLAN", detail="plano de core aponta para outra raiz")
        allowed = {self._target(core_id), self._metadata_path(manifest.id)}
        if any(Path(action.target) not in allowed for action in plan.actions):
            raise SteamZeroError(
                "E-TX-STALE-PLAN", detail="plano de core contém alvo não permitido"
            )

    def rollback(self, adapter_id: str, operation_id: str) -> transaction.RollbackResult:
        result = transaction.rollback(operation_id, reason="libretro-manual")
        self.persist_status(adapter_id)
        return result

    def persist_status(self, adapter_id: str) -> None:
        manifest = self._registry.get(adapter_id)
        observed = self.status(adapter_id)
        self._store.save_component(
            {
                "id": adapter_id,
                "adapter_id": adapter_id,
                "kind": manifest.kind,
                "version": observed.get("version"),
                "origin": observed.get("origin"),
                "state": observed["state"],
                "manifest_hash": manifest.manifest_hash,
            }
        )

    def _extract_verified(
        self, manifest: AdapterManifest, source: AdapterSource, core_id: str, digest: str
    ) -> Path:
        if source.sha256 is None:
            raise SteamZeroError("E-SUPPLY-NO-CHECKSUM", detail="arquivo de cores sem digest")
        artifact = self._artifacts.fetch(source)
        if crypto.digest_bytes(artifact).hexdigest != source.sha256:
            raise SteamZeroError("E-SUPPLY-CHECKSUM", detail="arquivo de cores diverge do pin")
        expected_name = _ARCHIVE_PREFIX + f"{core_id}_libretro.so"
        stage = paths.staging_dir() / "libretro" / source.sha256 / manifest.id
        fs.ensure_dir(stage)
        try:
            payload = self._archive_reader(artifact, expected_name)
        except SteamZeroError:
            raise
        except (OSError, ValueError) as exc:
            raise SteamZeroError(
                "E-SUPPLY-REMOTE-FAILED", detail=f"arquivo de cores inválido: {exc}"
            ) from exc
        extracted = stage / "payload.so"
        fs.write_atomic(extracted, payload, mode=0o600)
        try:
            if (
                not fs.is_within(stage, extracted)
                or extracted.is_symlink()
                or not extracted.is_file()
            ):
                raise ValueError("extração do core não é arquivo regular seguro")
            if extracted.stat().st_size > _MAX_CORE_BYTES:
                raise ValueError("core excede o limite de tamanho")
            if fs.hash_file(extracted, algo="sha256") != digest:
                raise ValueError("digest do core extraído diverge do manifesto")
        except (OSError, ValueError) as exc:
            raise SteamZeroError("E-SUPPLY-CHECKSUM", detail=str(exc)) from exc
        return extracted

    def _owned_target(
        self, manifest: AdapterManifest, source: AdapterSource, core_id: str, digest: str
    ) -> bool:
        target = self._target(core_id)
        metadata = self._metadata_path(manifest.id)
        if (
            target.is_symlink()
            or metadata.is_symlink()
            or not target.is_file()
            or not metadata.is_file()
        ):
            return False
        try:
            return (
                json.loads(metadata.read_text(encoding="utf-8"))
                == self._metadata(manifest, source, core_id, digest)
                and fs.hash_file(target, algo="sha256") == digest
            )
        except (OSError, ValueError, json.JSONDecodeError):
            return False

    def _details(self, adapter_id: str) -> tuple[AdapterManifest, AdapterSource, str, str]:
        manifest = self._registry.get(adapter_id)
        if manifest.kind != "core" or manifest.core is None:
            raise SteamZeroError("E-API-SCHEMA", detail=f"{adapter_id} não é adapter de core")
        source = manifest.preferred_source("archive", allow_eol=False)
        return manifest, source, manifest.core.id, manifest.core.sha256

    def _target(self, core_id: str) -> Path:
        return self._root / f"{core_id}_libretro.so"

    def _metadata_path(self, adapter_id: str) -> Path:
        return self._root / _METADATA_DIR / f"{adapter_id}.json"

    @staticmethod
    def _metadata(
        manifest: AdapterManifest, source: AdapterSource, core_id: str, digest: str
    ) -> dict[str, Any]:
        return {
            "schemaVersion": 1,
            "adapterId": manifest.id,
            "coreId": core_id,
            "coreSha256": digest,
            "archiveSha256": source.sha256,
            "version": source.version,
            "manifestHash": manifest.manifest_hash,
        }


def _default_core_root() -> Path:
    return Path.home() / ".var/app/org.libretro.RetroArch/config/retroarch/cores"


def _extract_7z_member(artifact: bytes, expected_name: str) -> bytes:
    """Lê uma única entrada 7z usando a libarchive do sistema.

    A dependência fica no host, em vez de introduzir uma cadeia de extensões
    Python no wheel. A API só recebe bytes já pinados e um nome canônico criado
    pelo executor; nunca materializa nem publica outras entradas do arquivo.
    """
    library_name = ctypes.util.find_library("archive")
    if library_name is None:
        raise SteamZeroError(
            "E-COMPONENT-DEGRADED", detail="libarchive não está disponível para ler cores 7z"
        )
    try:
        library = ctypes.CDLL(library_name)
        _configure_libarchive(library)
    except (AttributeError, OSError) as exc:
        raise SteamZeroError(
            "E-COMPONENT-DEGRADED", detail=f"libarchive indisponível: {exc}"
        ) from exc

    archive = library.archive_read_new()
    if not archive:
        raise SteamZeroError("E-SUPPLY-REMOTE-FAILED", detail="não criou leitor de arquivo 7z")
    buffer = ctypes.create_string_buffer(artifact)
    payload: bytes | None = None
    try:
        _archive_ok(library, archive, library.archive_read_support_filter_all(archive))
        _archive_ok(library, archive, library.archive_read_support_format_7zip(archive))
        _archive_ok(
            library,
            archive,
            library.archive_read_open_memory(
                archive, ctypes.cast(buffer, ctypes.c_void_p), len(artifact)
            ),
        )
        while True:
            entry = ctypes.c_void_p()
            result = library.archive_read_next_header(archive, ctypes.byref(entry))
            if result == _ARCHIVE_EOF:
                break
            _archive_ok(library, archive, result)
            raw_name = library.archive_entry_pathname(entry)
            if raw_name is None:
                raise ValueError("entrada 7z sem nome")
            name = raw_name.decode("utf-8", errors="strict")
            if name != expected_name:
                _archive_ok(library, archive, library.archive_read_data_skip(archive))
                continue
            if payload is not None:
                raise ValueError("arquivo contém exatamente o core declarado mais de uma vez")
            payload = _archive_member_data(library, archive)
        if payload is None:
            raise ValueError("arquivo não contém exatamente o core declarado")
        return payload
    except SteamZeroError:
        raise
    except (UnicodeDecodeError, ValueError) as exc:
        raise SteamZeroError(
            "E-SUPPLY-REMOTE-FAILED", detail=f"arquivo de cores inválido: {exc}"
        ) from exc
    finally:
        library.archive_read_free(archive)


def _configure_libarchive(library: ctypes.CDLL) -> None:
    archive_p = ctypes.c_void_p
    library.archive_read_new.argtypes = []
    library.archive_read_new.restype = archive_p
    for name in ("archive_read_support_filter_all", "archive_read_support_format_7zip"):
        function = getattr(library, name)
        function.argtypes = [archive_p]
        function.restype = ctypes.c_int
    library.archive_read_open_memory.argtypes = [archive_p, ctypes.c_void_p, ctypes.c_size_t]
    library.archive_read_open_memory.restype = ctypes.c_int
    library.archive_read_next_header.argtypes = [archive_p, ctypes.POINTER(archive_p)]
    library.archive_read_next_header.restype = ctypes.c_int
    library.archive_entry_pathname.argtypes = [archive_p]
    library.archive_entry_pathname.restype = ctypes.c_char_p
    library.archive_read_data.argtypes = [archive_p, ctypes.c_void_p, ctypes.c_size_t]
    library.archive_read_data.restype = ctypes.c_ssize_t
    library.archive_read_data_skip.argtypes = [archive_p]
    library.archive_read_data_skip.restype = ctypes.c_int
    library.archive_error_string.argtypes = [archive_p]
    library.archive_error_string.restype = ctypes.c_char_p
    library.archive_read_free.argtypes = [archive_p]
    library.archive_read_free.restype = ctypes.c_int


def _archive_member_data(library: ctypes.CDLL, archive: ctypes.c_void_p) -> bytes:
    data = bytearray()
    chunk = ctypes.create_string_buffer(_READ_CHUNK)
    while True:
        size = library.archive_read_data(archive, chunk, len(chunk))
        if size < 0:
            _archive_ok(library, archive, int(size))
        if size == 0:
            return bytes(data)
        if len(data) + size > _MAX_CORE_BYTES:
            raise ValueError("core excede o limite de tamanho")
        data.extend(chunk.raw[:size])


def _archive_ok(library: ctypes.CDLL, archive: ctypes.c_void_p, result: int) -> None:
    if result == _ARCHIVE_OK:
        return
    detail = library.archive_error_string(archive)
    message = detail.decode("utf-8", errors="replace") if detail else f"código {result}"
    raise SteamZeroError("E-SUPPLY-REMOTE-FAILED", detail=f"libarchive: {message}")
