# SPDX-License-Identifier: GPL-3.0-or-later
"""Backup/restore operacional de saves e shader caches de emuladores Switch."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import stat
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from steamzero.core import fs, ids, paths, transaction
from steamzero.core.errors import SteamZeroError
from steamzero.domain.switch_content import ContentRecord, SwitchContentManager

_SAVE_FILE_LIMIT = 64 * 1024 * 1024
_SAVE_TOTAL_LIMIT = 256 * 1024 * 1024
_SHADER_FILE_LIMIT = 1024 * 1024 * 1024
_SHADER_TOTAL_LIMIT = 4 * 1024 * 1024 * 1024
_MAX_FILES = 20_000


@dataclass(frozen=True)
class PreservationTarget:
    kind: str
    game_id: str
    title_id: str
    emulator_id: str
    root: Path
    emulator_version: str = "unknown"
    compatibility_fingerprint: str = ""


@dataclass(frozen=True)
class PreparedPreservationPlan:
    plan: transaction.Plan
    staging_root: Path


class PreservationService:
    """Expõe somente árvores existentes, únicas e livres de symlinks."""

    def __init__(
        self,
        content: SwitchContentManager,
        *,
        targets: Sequence[PreservationTarget] | None = None,
        progress: Callable[[int, int], None] | None = None,
        emulator_version: Callable[[str], str] | None = None,
    ) -> None:
        self._content = content
        self._targets = tuple(targets or ())
        self._progress = progress
        self._emulator_version = emulator_version or (lambda _emulator_id: "unknown")

    def target_status(
        self, game_id: str, title_id: str, emulator_id: str, kind: str
    ) -> dict[str, object]:
        matches = self._matching_targets(game_id, title_id, emulator_id, kind)
        if len(matches) != 1:
            return {
                "confirmed": False,
                "reason": (
                    "destino não detectado"
                    if not matches
                    else "mais de um destino compatível foi detectado"
                ),
                "ambiguous": len(matches) > 1,
            }
        target = matches[0]
        files = _safe_tree_files(target.root, kind)
        total = sum(path.stat().st_size for path in files)
        return {
            "confirmed": True,
            "reason": "",
            "ambiguous": False,
            "destination": str(target.root),
            "emulatorId": target.emulator_id,
            "emulatorVersion": target.emulator_version,
            "compatibilityFingerprint": target.compatibility_fingerprint,
            "size": total,
            "fileCount": len(files),
            "integrity": _tree_digest(target.root, files),
        }

    def backups(self, title_id: str, emulator_id: str, kind: str) -> list[dict[str, object]]:
        rows = [
            record
            for record in self._content.list_records(title_id=title_id, kind=kind)
            if record.emulator_id == emulator_id and _backup_metadata(record.version) is not None
        ]
        result: list[dict[str, object]] = []
        for record in sorted(rows, key=lambda item: item.version or "", reverse=True):
            metadata = _backup_metadata(record.version)
            if metadata is None:
                continue
            result.append(
                {
                    "recordKey": record.record_key,
                    "createdAt": metadata["createdAt"],
                    "size": record.size,
                    "sha256": record.sha256,
                    "integrity": _record_integrity(record),
                    "emulatorId": record.emulator_id,
                    "compatibilityFingerprint": metadata.get("fingerprint", ""),
                }
            )
        return result

    def plan_backup(
        self, game_id: str, title_id: str, emulator_id: str, kind: str
    ) -> PreparedPreservationPlan:
        target = self._require_target(game_id, title_id, emulator_id, kind)
        staging = paths.staging_dir() / "preservation" / ids.new_ulid()
        archive = staging / "tree.zip"
        try:
            _archive_tree(target.root, archive, kind, progress=self._progress)
            created_at = datetime.now(UTC).isoformat()
            metadata = {
                "schemaVersion": 1,
                "createdAt": created_at,
                "fingerprint": target.compatibility_fingerprint if kind == "shader-cache" else "",
            }
            decision = self._content.plan_import(
                archive,
                kind=kind,
                title_id=title_id,
                version="backup:" + _compact_metadata(metadata),
                emulator_id=emulator_id,
            )
            if decision.plan is None:
                raise SteamZeroError("E-TX-STALE-PLAN", detail="backup já catalogado")
        except Exception:
            self.cleanup(staging)
            raise
        return PreparedPreservationPlan(decision.plan, staging)

    def plan_restore(
        self,
        game_id: str,
        title_id: str,
        emulator_id: str,
        kind: str,
        record_key: str,
    ) -> PreparedPreservationPlan:
        target = self._require_target(game_id, title_id, emulator_id, kind)
        record = self._record(record_key, title_id, emulator_id, kind)
        metadata = _backup_metadata(record.version)
        if metadata is None:
            raise SteamZeroError("E-CONTENT-INCOMPLETE", detail="backup sem metadados")
        expected = str(metadata.get("fingerprint", ""))
        if kind == "shader-cache" and expected != target.compatibility_fingerprint:
            raise SteamZeroError(
                "E-CONTENT-UNSUPPORTED",
                detail=(
                    "fingerprint do cache diverge do driver/emulador atual: "
                    f"backup={expected or 'ausente'} atual={target.compatibility_fingerprint}"
                ),
            )
        staging = paths.staging_dir() / "preservation" / ids.new_ulid()
        extracted = staging / "extracted"
        try:
            _extract_archive(record, extracted, kind, progress=self._progress)
            incoming = _safe_tree_files(extracted, kind)
            copies = [(source, target.root / source.relative_to(extracted)) for source in incoming]
            incoming_targets = {destination for _source, destination in copies}
            current = _safe_tree_files(target.root, kind)
            removals = {path for path in current if path not in incoming_targets}
            plan = transaction.plan_copy_files(
                copies,
                removals=removals,
                root=target.root,
                kind=f"preservation.{kind}.restore",
                replace_existing=True,
                requirements_extra={
                    "backupRecord": record.record_key,
                    "compatibilityFingerprint": expected,
                },
            )
        except Exception:
            self.cleanup(staging)
            raise
        return PreparedPreservationPlan(plan, staging)

    def plan_shader_invalidation(
        self, game_id: str, title_id: str, emulator_id: str
    ) -> transaction.Plan:
        target = self._require_target(game_id, title_id, emulator_id, "shader-cache")
        files = [
            path.relative_to(target.root).as_posix()
            for path in _safe_tree_files(target.root, "shader-cache")
            if ".invalidated" not in path.relative_to(target.root).parts
        ]
        if not files:
            raise SteamZeroError("E-CONTENT-INCOMPLETE", detail="cache de shader está vazio")
        return SwitchContentManager.plan_invalidate_shader_cache(
            target.root,
            files,
            title_id=title_id,
            compatibility_fingerprint=target.compatibility_fingerprint,
        )

    @staticmethod
    def cleanup(staging_root: Path) -> None:
        if staging_root.parent == paths.staging_dir() / "preservation":
            fs.remove_tree(staging_root)

    def _record(self, record_key: str, title_id: str, emulator_id: str, kind: str) -> ContentRecord:
        record = next(
            (
                item
                for item in self._content.list_records(title_id=title_id, kind=kind)
                if item.record_key == record_key and item.emulator_id == emulator_id
            ),
            None,
        )
        if record is None:
            raise SteamZeroError("E-CONTENT-INCOMPLETE", detail="backup não catalogado")
        return record

    def _require_target(
        self, game_id: str, title_id: str, emulator_id: str, kind: str
    ) -> PreservationTarget:
        matches = self._matching_targets(game_id, title_id, emulator_id, kind)
        if len(matches) != 1:
            raise SteamZeroError(
                "E-CONTENT-UNSAFE-PATH",
                detail=(
                    "destino seguro não encontrado"
                    if not matches
                    else "restore bloqueado: destino ambíguo"
                ),
            )
        return matches[0]

    def _matching_targets(
        self, game_id: str, title_id: str, emulator_id: str, kind: str
    ) -> list[PreservationTarget]:
        explicit = [
            target
            for target in self._targets
            if target.game_id == game_id
            and target.title_id.upper() == title_id.upper()
            and target.emulator_id == emulator_id
            and target.kind == kind
            and _safe_target_root(target.root)
        ]
        if explicit:
            return explicit
        return _discover_targets(
            game_id,
            title_id,
            emulator_id,
            kind,
            emulator_version=self._emulator_version(emulator_id),
        )


def host_driver_fingerprint(drm_root: Path | None = None) -> str:
    """Impressão do driver gráfico do host.

    ``drm_root`` existe para teste: sem ponto de injeção esta função só é
    exercitada em máquina com GPU real, e a cobertura passa a depender do
    hardware de quem roda a suíte em vez do código.
    """
    material: dict[str, object] = {
        "kernel": platform.release(),
        "machine": platform.machine(),
        "drm": [],
    }
    drm: list[str] = []
    root = drm_root if drm_root is not None else Path("/sys/class/drm")
    for uevent in sorted(root.glob("card*/device/uevent")):
        try:
            rows = [
                line
                for line in uevent.read_text(encoding="utf-8").splitlines()
                if line.startswith(("DRIVER=", "PCI_ID=", "PCI_SLOT_NAME="))
            ]
        except OSError:
            continue
        drm.extend(rows)
    material["drm"] = drm
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:24]


def _discover_targets(
    game_id: str,
    title_id: str,
    emulator_id: str,
    kind: str,
    *,
    emulator_version: str,
    home: Path | None = None,
) -> list[PreservationTarget]:
    # ``home`` injetável: caminhar o diretório real do usuário torna a cobertura
    # dependente de quais emuladores estão instalados na máquina.
    home = home if home is not None else Path.home()
    roots = _candidate_roots(home, emulator_id, kind)
    matches: list[PreservationTarget] = []
    wanted = title_id.casefold()
    for base in roots:
        if base.is_symlink() or not base.is_dir():
            continue
        visited = 0
        for current, dirnames, _filenames in os.walk(base, followlinks=False):
            visited += 1
            if visited > 5_000:
                break
            dirnames[:] = [name for name in dirnames if name != ".invalidated"]
            current_path = Path(current)
            if current_path.name.casefold() != wanted:
                continue
            if not _safe_target_root(current_path):
                continue
            matches.append(
                PreservationTarget(
                    kind=kind,
                    game_id=game_id,
                    title_id=title_id.upper(),
                    emulator_id=emulator_id,
                    root=current_path.resolve(),
                    emulator_version=emulator_version,
                    compatibility_fingerprint=(
                        _shader_fingerprint(emulator_id, emulator_version)
                        if kind == "shader-cache"
                        else ""
                    ),
                )
            )
    unique = {target.root: target for target in matches}
    return list(unique.values())


def _shader_fingerprint(emulator_id: str, emulator_version: str) -> str:
    material = f"{host_driver_fingerprint()}:{emulator_id}:{emulator_version}"
    return hashlib.sha256(material.encode()).hexdigest()[:24]


def _candidate_roots(home: Path, emulator_id: str, kind: str) -> tuple[Path, ...]:
    aliases = {
        "eden": ("eden", "Eden", "yuzu"),
        "citron": ("citron", "Citron", "yuzu"),
        "ryubing": ("Ryubing", "Ryujinx", "ryubing"),
    }.get(emulator_id, (emulator_id,))
    roots: list[Path] = []
    for alias in aliases:
        if kind == "save":
            roots.extend(
                (
                    home / ".local/share" / alias / "nand/user/save",
                    home / ".config" / alias / "bis/user/save",
                )
            )
        else:
            roots.extend(
                (
                    home / ".local/share" / alias / "shader",
                    home / ".cache" / alias / "shader",
                    home / ".config" / alias / "games",
                )
            )
    return tuple(dict.fromkeys(roots))


def _safe_target_root(root: Path) -> bool:
    try:
        if root.is_symlink() or not root.is_dir():
            return False
        resolved = root.resolve(strict=True)
        return resolved == root.absolute() and all(
            not parent.is_symlink() for parent in root.parents
        )
    except OSError:
        return False


def _limits(kind: str) -> tuple[int, int]:
    if kind == "save":
        return _SAVE_FILE_LIMIT, _SAVE_TOTAL_LIMIT
    if kind == "shader-cache":
        return _SHADER_FILE_LIMIT, _SHADER_TOTAL_LIMIT
    raise SteamZeroError("E-API-SCHEMA", detail="tipo de preservação inválido")


def _safe_tree_files(root: Path, kind: str) -> list[Path]:
    if not _safe_target_root(root):
        raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="raiz contém symlink ou é inválida")
    file_limit, total_limit = _limits(kind)
    files: list[Path] = []
    total = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="árvore contém symlink")
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if ".invalidated" in relative.parts:
            continue
        size = path.stat().st_size
        if size > file_limit:
            raise SteamZeroError("E-CONTENT-LIMIT", detail="arquivo excede limite seguro")
        total += size
        if total > total_limit or len(files) >= _MAX_FILES:
            raise SteamZeroError("E-CONTENT-LIMIT", detail="árvore excede limite seguro")
        files.append(path)
    return files


def _tree_digest(root: Path, files: Sequence[Path]) -> str:
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(fs.hash_file(path).encode())
    return digest.hexdigest()


def _archive_tree(
    root: Path,
    archive: Path,
    kind: str,
    *,
    progress: Callable[[int, int], None] | None,
) -> None:
    files = _safe_tree_files(root, kind)
    if not files:
        raise SteamZeroError("E-CONTENT-INCOMPLETE", detail="árvore de preservação está vazia")
    fs.ensure_dir(archive.parent)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
        manifest_files: list[dict[str, object]] = []
        for index, path in enumerate(files, start=1):
            relative = path.relative_to(root).as_posix()
            output.write(path, relative)
            manifest_files.append(
                {"path": relative, "sha256": fs.hash_file(path), "size": path.stat().st_size}
            )
            if progress is not None:
                progress(index, len(files))
        output.writestr(
            "STEAMZERO-MANIFEST.json",
            json.dumps(
                {"schemaVersion": 1, "files": manifest_files},
                sort_keys=True,
                separators=(",", ":"),
            ),
        )


def _extract_archive(
    record: ContentRecord,
    destination: Path,
    kind: str,
    *,
    progress: Callable[[int, int], None] | None,
) -> None:
    if record.blob.is_symlink() or not record.blob.is_file():
        raise SteamZeroError("E-CONTENT-INCOMPLETE", detail="arquivo de backup ausente")
    if fs.hash_file(record.blob, algo="sha256") != record.sha256:
        raise SteamZeroError("E-CONTENT-INCOMPLETE", detail="hash do backup diverge")
    file_limit, total_limit = _limits(kind)
    fs.ensure_dir(destination)
    with zipfile.ZipFile(record.blob) as archive:
        infos = [item for item in archive.infolist() if item.filename != "STEAMZERO-MANIFEST.json"]
        if len(infos) > _MAX_FILES:
            raise SteamZeroError("E-CONTENT-LIMIT", detail="backup contém arquivos demais")
        total = 0
        seen: set[str] = set()
        for index, info in enumerate(infos, start=1):
            relative = fs.validate_relative_entry(info.filename)
            if str(relative) in seen or info.is_dir():
                raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="entrada duplicada/inválida")
            seen.add(str(relative))
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="backup contém symlink")
            total += info.file_size
            if info.file_size > file_limit or total > total_limit:
                raise SteamZeroError("E-CONTENT-LIMIT", detail="backup excede limite seguro")
            target = fs.resolve_within(destination, destination / relative)
            with archive.open(info) as source:
                fs.write_stream_atomic(target, source, max_bytes=file_limit)
            if progress is not None:
                progress(index, len(infos))
    manifest_path = destination.parent / "manifest-check.json"
    with zipfile.ZipFile(record.blob) as archive:
        try:
            manifest = json.loads(archive.read("STEAMZERO-MANIFEST.json"))
        except (KeyError, json.JSONDecodeError) as exc:
            raise SteamZeroError(
                "E-CONTENT-INCOMPLETE", detail="manifest de backup inválido"
            ) from exc
    fs.write_atomic_text(manifest_path, json.dumps(manifest, sort_keys=True))
    expected = {
        str(item["path"]): str(item["sha256"])
        for item in manifest.get("files", [])
        if isinstance(item, dict) and "path" in item and "sha256" in item
    }
    actual = {
        path.relative_to(destination).as_posix(): fs.hash_file(path)
        for path in _safe_tree_files(destination, kind)
    }
    if actual != expected:
        raise SteamZeroError("E-CONTENT-INCOMPLETE", detail="conteúdo do backup diverge")


def _record_integrity(record: ContentRecord) -> str:
    try:
        if record.blob.is_symlink() or fs.hash_file(record.blob, algo="sha256") != record.sha256:
            return "failed"
    except OSError:
        return "failed"
    return "verified"


def _compact_metadata(value: dict[str, object]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
    if len(encoded) > 120:
        raise SteamZeroError("E-API-SCHEMA", detail="metadados de backup excedem limite")
    return encoded


def _backup_metadata(version: str | None) -> dict[str, object] | None:
    if version is None or not version.startswith("backup:"):
        return None
    try:
        value = json.loads(version.removeprefix("backup:"))
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) and value.get("schemaVersion") == 1 else None
