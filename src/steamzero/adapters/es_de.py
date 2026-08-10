# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Publicação transacional de sistemas de emulação no ES-DE.

Integração pelo canal documentado de ``custom_systems`` (USERGUIDE do ES-DE):
sistemas declarados em ``~/.config/ES-DE/custom_systems/es_systems.xml`` são
mesclados aos sistemas internos do ES-DE. O ES-DE lê ``name``, ``fullname``,
``path``, ``extension``, ``command``, ``platform`` e ``theme`` de cada
``<system>`` e ignora atributos desconhecidos — o atributo ``steamzero="true"``
é o marcador de ownership deste adapter.

Diferente do Steam ROM Manager (canal de diretório com preservação byte a
byte de arquivos externos), ``es_systems.xml`` é um único documento
compartilhado com o operador: este adapter preserva conteúdo externo de forma
SEMÂNTICA (ordem dos sistemas, comentários, atributos e textos), nunca deleta
sistema sem marcador e só reescreve o arquivo quando há diferença real
(``skip_unchanged=True``), deixando rollback byte-idêntico para o núcleo
transacional. Ficam fora de escopo ``es_settings.xml`` e ``gamelists``,
gerados pelo próprio ES-DE.

Segurança de XML: o arquivo é limitado a 4 MiB, ``<!DOCTYPE>`` é rejeitado
(previne entidades externas/expansão) e o parser é o ElementTree padrão, que
não resolve entidades externas.
"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from steamzero.core import paths, transaction
from steamzero.core.errors import SteamZeroError

_MARKER_ATTR = "steamzero"
_MARKER_VALUE = "true"
_FILE_NAME = "es_systems.xml"
_MAX_FILE_BYTES = 4 * 1024 * 1024
_NAME_RE = re.compile(r"steamzero-[a-z0-9][a-z0-9-]{0,55}")
_PLATFORM_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
_EXTENSION_RE = re.compile(r"\.[A-Za-z0-9]{1,8}")
_DEFAULT_TARGET = "/usr/local/bin/steamzero"
_KIND = "frontend.esde-systems.sync"


def _invalid(detail: str) -> SteamZeroError:
    return SteamZeroError("E-STATE-INTEGRITY", detail=f"es_systems.xml inválido: {detail}")


class _CommentKeepingBuilder(ET.TreeBuilder):
    """Mantém comentários e instruções de processamento no round-trip.

    O TreeBuilder padrão descarta comentários; sem eles, a reescrita de um
    arquivo externo perderia conteúdo. ET serializa elementos comentário como
    ``<!--...-->``.
    """

    def comment(self, data: str) -> None:  # type: ignore[override]
        self.start(ET.Comment, {})
        self.data(data)
        self.end(ET.Comment)  # type: ignore[arg-type]

    def pi(self, target: str, data: str | None = None) -> None:  # type: ignore[override]
        self.start(ET.PI, {})
        self.data(f"{target} {data}".rstrip() if data else target)
        self.end(ET.PI)  # type: ignore[arg-type]


class EsDe:
    """Sincroniza apenas sistemas marcados com ``steamzero="true"``."""

    def __init__(
        self,
        *,
        roots: Sequence[Path] | None = None,
        target: str = _DEFAULT_TARGET,
    ) -> None:
        self._roots = tuple(roots) if roots is not None else (self._default_root(),)
        self._target = target

    @staticmethod
    def _default_root() -> Path:
        return paths.config_home() / "ES-DE" / "custom_systems"

    def _dir(self) -> Path:
        matches: list[Path] = []
        for root in self._roots:
            if root.exists():
                if root.is_symlink() or not root.is_dir():
                    raise SteamZeroError(
                        "E-COMPONENT-DEGRADED",
                        detail=f"diretorio custom_systems ES-DE inseguro: {root}",
                    )
                matches.append(root)
        if len(matches) == 0:
            return self._roots[0]
        unique = list(dict.fromkeys(matches))
        if len(unique) != 1:
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED",
                detail="diretorio custom_systems ES-DE ambíguo entre as raízes",
            )
        return unique[0]

    def _file(self) -> Path:
        return self._dir() / _FILE_NAME

    def status(self) -> dict[str, str]:
        """missing | configured | degraded | permissionDenied com causa."""
        try:
            file = self._file()
            file.stat()
        except SteamZeroError as exc:
            return {"status": "degraded", "detail": str(exc.detail)}
        except FileNotFoundError:
            return {"status": "missing", "detail": "es_systems.xml ausente"}
        except PermissionError:
            return {"status": "permissionDenied", "detail": "arquivo sem permissão de leitura"}
        try:
            root = self._parse(file)
        except PermissionError:
            return {"status": "permissionDenied", "detail": "arquivo sem permissão de leitura"}
        except SteamZeroError as exc:
            return {"status": "degraded", "detail": str(exc.detail)}
        managed = len(self._marked_systems(root))
        return {
            "status": "configured" if managed else "missing",
            "detail": f"{managed} sistema(s) SteamZero no custom_systems" if managed else "",
        }

    def _read_raw(self, file: Path) -> bytes:
        if file.is_symlink() or not file.is_file() or file.stat().st_size > _MAX_FILE_BYTES:
            raise _invalid(f"{file.name} é symlink, ausente ou excede 4 MiB")
        raw = file.read_bytes()
        if b"<!DOCTYPE" in raw.upper():
            raise _invalid("DOCTYPE/entidades externas não são aceitas")
        return raw

    def _parse(self, file: Path) -> ET.Element:
        raw = self._read_raw(file)
        try:
            root = ET.fromstring(  # noqa: S314 - conteúdo limitado a 4 MiB e DOCTYPE rejeitado
                raw,
                parser=ET.XMLParser(target=_CommentKeepingBuilder()),  # noqa: S314
            )
        except ET.ParseError as exc:
            raise _invalid(f"XML malformado: {exc}") from exc
        if root.tag != "systemList":
            raise _invalid(f"raiz <{root.tag}> não é <systemList>")
        return root

    @staticmethod
    def _system_name(system: ET.Element) -> str:
        return (system.findtext("name") or "").strip()

    @staticmethod
    def _marked_systems(root: ET.Element) -> list[ET.Element]:
        return [
            system for system in root.findall("system") if system.get(_MARKER_ATTR) == _MARKER_VALUE
        ]

    def managed_systems(self) -> set[str]:
        try:
            return {
                self._system_name(entry)
                for entry in self._marked_systems(self._parse(self._file()))
            }
        except (SteamZeroError, PermissionError, FileNotFoundError):
            return set()

    def plan(self, systems: Sequence[Mapping[str, Any]]) -> transaction.Plan:
        requested: dict[str, dict[str, Any]] = {}
        for system in systems:
            name = str(system.get("name", ""))
            if _NAME_RE.fullmatch(name) is None or name in requested:
                raise SteamZeroError("E-API-SCHEMA", detail="sistema ES-DE inválido ou duplicado")
            label = str(system.get("label", ""))
            path = str(system.get("path", ""))
            platform = str(system.get("platform", ""))
            extensions = system.get("extensions", [])
            if not label or len(label) > 200:
                raise SteamZeroError("E-API-SCHEMA", detail="sistema ES-DE sem label válido")
            if not path or not Path(path).is_absolute():
                raise SteamZeroError("E-API-SCHEMA", detail="sistema ES-DE sem path absoluto")
            if _PLATFORM_RE.fullmatch(platform) is None:
                raise SteamZeroError("E-API-SCHEMA", detail="sistema ES-DE sem platform válido")
            if not isinstance(extensions, Sequence) or not extensions:
                raise SteamZeroError("E-API-SCHEMA", detail="sistema ES-DE sem extensões")
            normalized: list[str] = []
            for extension in extensions:
                extension_str = str(extension)
                if _EXTENSION_RE.fullmatch(extension_str) is None:
                    raise SteamZeroError(
                        "E-API-SCHEMA", detail=f"extensão ES-DE inválida: {extension_str}"
                    )
                normalized.append(extension_str.lower())
            requested[name] = {
                "label": label,
                "path": path,
                "extensions": sorted(set(normalized)),
                "platform": platform,
                "theme": str(system.get("theme") or ""),
                "command": str(system.get("command") or "") or None,
            }

        file = self._file()
        if file.exists():
            existing = self._parse(file)
            foreign_names = {
                self._system_name(entry)
                for entry in existing.findall("system")
                if entry.get(_MARKER_ATTR) != _MARKER_VALUE
            }
            conflict = sorted(set(requested).intersection(foreign_names))
            if conflict:
                raise SteamZeroError(
                    "E-API-SCHEMA",
                    detail=f"nome de sistema em conflito com sistema externo: {conflict[0]}",
                )
        else:
            existing = None

        new_root = self._render(existing, requested)
        content = ET.tostring(new_root, encoding="utf-8", xml_declaration=True) + b"\n"
        return transaction.plan_write_files(
            {file: content}, root=self._dir(), kind=_KIND, skip_unchanged=True
        )

    def _render(
        self,
        existing: ET.Element | None,
        requested: Mapping[str, Mapping[str, Any]],
    ) -> ET.Element:
        root: ET.Element
        if existing is None:
            root = ET.Element("systemList")
        else:
            root = existing
            for system in self._marked_systems(root):
                root.remove(system)
        for name in sorted(requested):
            spec = requested[name]
            system = ET.SubElement(root, "system", {_MARKER_ATTR: _MARKER_VALUE})
            ET.SubElement(system, "name").text = name
            ET.SubElement(system, "fullname").text = spec["label"]
            ET.SubElement(system, "path").text = spec["path"]
            ET.SubElement(system, "extension").text = " ".join(spec["extensions"])
            command = ET.SubElement(system, "command", {"label": spec["label"]})
            command.text = (
                spec["command"] or f"{self._target} emulation launch --game-id %BASENAME%"
            )
            ET.SubElement(system, "platform").text = spec["platform"]
            if spec["theme"]:
                ET.SubElement(system, "theme").text = spec["theme"]
        return root

    def apply(
        self,
        plan_id: str,
        confirm_token: str,
        *,
        smoke: Callable[[], None] | None = None,
    ) -> transaction.ApplyResult:
        plan = transaction.load_plan(plan_id)
        file = Path(os.path.realpath(self._file()))
        directory = Path(os.path.realpath(self._dir()))
        if plan.kind != _KIND or Path(plan.root) != directory:
            raise SteamZeroError("E-TX-STALE-PLAN", detail="plano não pertence ao es_systems.xml")
        for action in plan.actions:
            target = Path(action.target)
            inside = file == target and not target.is_symlink()
            valid = inside and action.kind in {"write", "delete"}
            if not valid:
                raise SteamZeroError(
                    "E-TX-STALE-PLAN", detail="plano não pertence ao es_systems.xml"
                )

        def default_smoke() -> None:
            if any(action.kind == "write" for action in plan.actions):
                self._parse(file)

        return transaction.apply(plan_id, confirm_token, smoke=smoke or default_smoke)

    def verify(self, systems: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        plan = self.plan(systems)
        return {
            "converged": not plan.actions,
            "planActions": len(plan.actions),
            "managedSystems": sorted(self.managed_systems()),
        }
