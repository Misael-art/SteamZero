# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Publicação transacional de jogos locais pelo Steam ROM Manager (SRM).

Integração pelo canal público de manifests do parser Manual do SRM
(documentação ``manual-parser-input``): o SRM lê, de um único diretório,
arquivos JSON cujo objeto (ou array de objetos) carrega ``title``, ``target``,
``startIn``, ``launchOptions`` e ``appendArgsToExecutable``, e ignora campos
desconhecidos. O SRM nunca reescreve esse diretório, então o marcador
``steamzero`` é durável.

Este adapter nunca toca em ``configs.json`` (a lista de parsers): o SRM
reescreve esse arquivo a partir do próprio serializador e nenhum marcador
sobrevive ao round-trip — gerenciar parsers ali quebraria o contrato de não
duplicação e a preservação de conteúdo externo. Também não inicia nem
controla o aplicativo SRM; a publicação no Steam fica a cargo de uma
execução do SRM pelo operador.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from steamzero.core import transaction
from steamzero.core.errors import SteamZeroError

_MANIFEST_PREFIX = "steamzero-manifest-"
_MARKER_KEY = "steamzero"
_MAX_MANIFEST_BYTES = 2 * 1024 * 1024
_COLLECTION_RE = re.compile(r"[a-z][a-z0-9-]{0,63}")
_ENTRY_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_DEFAULT_TARGET = "/usr/local/bin/steamzero"
_DEFAULT_START_IN = "/usr/local/bin"
_KIND = "frontend.srm-manifests.sync"


def _invalid(detail: str) -> SteamZeroError:
    return SteamZeroError("E-STATE-INTEGRITY", detail=f"manifest SRM inválido: {detail}")


def _managed_name(collection: str) -> str:
    return f"{_MANIFEST_PREFIX}{collection}.json"


def _is_managed_file(name: str) -> bool:
    return name.startswith(_MANIFEST_PREFIX) and name.endswith(".json")


def _collection_of_file(name: str) -> str:
    return name[len(_MANIFEST_PREFIX) : -len(".json")]


def _marker(entry: Mapping[str, Any]) -> str | None:
    marker = entry.get(_MARKER_KEY)
    if not isinstance(marker, dict):
        return None
    collection = marker.get("collection")
    if not isinstance(collection, str) or _COLLECTION_RE.fullmatch(collection) is None:
        return None
    return collection


def _render_manifest(entries: Sequence[Mapping[str, Any]]) -> bytes:
    return json.dumps(list(entries), sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n"


class SteamRomManager:
    """Sincroniza apenas manifests de coleções identificadas como SteamZero."""

    def __init__(
        self,
        *,
        roots: Sequence[Path] | None = None,
        target: str = _DEFAULT_TARGET,
        start_in: str = _DEFAULT_START_IN,
    ) -> None:
        self._roots = tuple(roots) if roots is not None else (self._default_root(),)
        self._target = target
        self._start_in = start_in

    @staticmethod
    def _default_root() -> Path:
        env_base = os.environ.get("XDG_CONFIG_HOME")
        base = Path(env_base) if env_base else Path.home() / ".config"
        return base / "steam-rom-manager" / "userData" / "manifests"

    def _dir(self) -> Path:
        matches: list[Path] = []
        for root in self._roots:
            if root.exists():
                if root.is_symlink() or not root.is_dir():
                    raise SteamZeroError(
                        "E-COMPONENT-DEGRADED",
                        detail=f"diretorio de manifests SRM inseguro: {root}",
                    )
                matches.append(root)
        if len(matches) == 0:
            return self._roots[0]
        unique = list(dict.fromkeys(matches))
        if len(unique) != 1:
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED",
                detail="diretorio de manifests SRM ambíguo entre as raízes",
            )
        return unique[0]

    def status(self) -> dict[str, str]:
        """missing | configured | degraded | permissionDenied com causa."""
        try:
            directory = self._dir()
            directory.stat()
        except SteamZeroError as exc:
            return {"status": "degraded", "detail": str(exc.detail)}
        except FileNotFoundError:
            return {"status": "missing", "detail": "diretório de manifests ausente"}
        except PermissionError:
            return {"status": "permissionDenied", "detail": "diretório sem permissão de leitura"}
        if not directory.is_dir():
            return {"status": "missing", "detail": "diretório de manifests ausente"}
        try:
            published = self._load_published(directory)
        except PermissionError:
            return {"status": "permissionDenied", "detail": "diretório sem permissão de leitura"}
        except SteamZeroError as exc:
            return {"status": "degraded", "detail": str(exc.detail)}
        managed = sorted(published)
        return {
            "status": "configured" if managed else "missing",
            "detail": f"{len(managed)} manifest(s) SteamZero presentes" if managed else "",
        }

    @staticmethod
    def _read_tracked(path: Path) -> object:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > _MAX_MANIFEST_BYTES:
            raise _invalid(f"{path.name} é symlink, ausente ou excede 2 MiB")
        try:
            return json.loads(path.read_bytes())
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise _invalid(f"{path.name} não é JSON válido") from exc

    def _load_published(self, directory: Path) -> dict[str, list[dict[str, Any]]]:
        published: dict[str, list[dict[str, Any]]] = {}
        for path in sorted(
            entry
            for entry in directory.iterdir()
            if entry.is_file() and _is_managed_file(entry.name)
        ):
            payload = self._read_tracked(path)
            if not isinstance(payload, list):
                raise _invalid(f"{path.name} não contém um array de entradas")
            for entry in payload:
                marker_collection = self._entry(entry, path.name)
                published.setdefault(marker_collection, []).append(entry)
        return published

    def _entry(self, entry: object, filename: str) -> str:
        if not isinstance(entry, dict):
            raise _invalid(f"{filename} contém entrada não-objeto")
        title = entry.get("title")
        target = entry.get("target")
        if not isinstance(title, str) or not title:
            raise _invalid(f"{filename} tem entrada sem título")
        if not isinstance(target, str) or not target:
            raise _invalid(f"{filename} tem entrada sem target")
        entry_id = entry.get(_MARKER_KEY)
        if not isinstance(entry_id, dict):
            raise _invalid(f"{filename} tem entrada sem marcador SteamZero")
        collection = entry_id.get("collection")
        if not isinstance(collection, str) or _COLLECTION_RE.fullmatch(collection) is None:
            raise _invalid(f"{filename} tem marcador SteamZero inválido")
        if entry_id.get("id") is None:
            raise _invalid(f"{filename} tem marcador SteamZero sem id")
        if _collection_of_file(filename) != collection:
            raise _invalid(f"{filename} mistura coleção {collection} no arquivo errado")
        return collection

    def managed_collections(self) -> set[str]:
        directory = self._dir()
        if not directory.is_dir():
            return set()
        try:
            return set(self._load_published(directory).keys())
        except (SteamZeroError, PermissionError):
            return set()

    def plan(self, collections: Sequence[Mapping[str, Any]]) -> transaction.Plan:
        requested: dict[str, list[dict[str, Any]]] = {}
        seen_ids: set[str] = set()
        for collection in collections:
            slug = str(collection.get("slug", ""))
            if _COLLECTION_RE.fullmatch(slug) is None or slug in requested:
                raise SteamZeroError("E-API-SCHEMA", detail="coleção duplicada ou inválida")
            entries: list[dict[str, Any]] = []
            for game in collection.get("games", []):
                game_id = str(game.get("id", ""))
                title = str(game.get("title", ""))
                if _ENTRY_ID_RE.fullmatch(game_id) is None or not title or len(title) > 200:
                    raise SteamZeroError(
                        "E-API-SCHEMA", detail="jogo SRM com id ou título inválido"
                    )
                if game_id in seen_ids:
                    raise SteamZeroError("E-API-SCHEMA", detail=f"jogo SRM duplicado: {game_id}")
                seen_ids.add(game_id)
                entries.append(
                    {
                        "title": title,
                        "target": self._target,
                        "startIn": self._start_in,
                        "launchOptions": f"emulation launch --game-id {game_id}",
                        "appendArgsToExecutable": True,
                        _MARKER_KEY: {"collection": slug, "id": game_id},
                    }
                )
            entries.sort(
                key=lambda value: (value["title"].casefold(), str(value[_MARKER_KEY]["id"]))
            )
            requested[slug] = entries

        directory = self._dir()
        published = self._load_published(directory) if directory.is_dir() else {}
        files: dict[Path, bytes] = {}
        removals: set[Path] = set()
        for slug in sorted(requested):
            target = directory / _managed_name(slug)
            entries = requested[slug]
            if not entries and (published.get(slug) or target.exists()):
                removals.add(target)
            elif published.get(slug, []) != entries:
                files[target] = _render_manifest(entries)
        stale = sorted(set(published).difference(requested))
        for slug in stale:
            target = directory / _managed_name(slug)
            if target.exists() and not target.is_symlink() and target.is_file():
                removals.add(target)
        return transaction.plan_write_files(
            files, root=directory.parent, kind=_KIND, removals=removals, skip_unchanged=True
        )

    def apply(
        self,
        plan_id: str,
        confirm_token: str,
        *,
        smoke: Callable[[], None] | None = None,
    ) -> transaction.ApplyResult:
        plan = transaction.load_plan(plan_id)
        directory = Path(os.path.realpath(self._dir()))
        if plan.kind != _KIND or Path(plan.root) != directory.parent:
            raise SteamZeroError("E-TX-STALE-PLAN", detail="plano não pertence aos manifests SRM")
        for action in plan.actions:
            target = Path(action.target)
            inside = directory == target.parent and not target.is_symlink()
            if action.kind in {"write", "delete"}:
                valid = inside and _is_managed_file(target.name)
            else:
                valid = False
            if not valid:
                raise SteamZeroError(
                    "E-TX-STALE-PLAN", detail="plano não pertence aos manifests SRM"
                )

        def default_smoke() -> None:
            if any(action.kind == "write" for action in plan.actions):
                self._load_published(directory)

        return transaction.apply(plan_id, confirm_token, smoke=smoke or default_smoke)

    def verify(self, collections: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        plan = self.plan(collections)
        converged = not plan.actions
        directory = self._dir()
        return {
            "converged": converged,
            "planActions": len(plan.actions),
            "collectionFiles": sorted(
                path.name for path in directory.iterdir() if _is_managed_file(path.name)
            ),
        }
