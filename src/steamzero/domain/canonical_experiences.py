# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Identidades históricas do tema, separadas das famílias técnicas de execução."""

from __future__ import annotations

import builtins
import importlib.resources
import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from jsonschema import ValidationError

from steamzero.api import contracts
from steamzero.core.errors import SteamZeroError

_SCHEMA = "canonical-experience-catalog-v1.schema.json"


@dataclass(frozen=True)
class CanonicalExperience:
    id: str
    name: str
    kind: str
    group_id: str
    group_name: str
    status: str
    technical_platform_id: str | None
    parent_id: str | None
    runtimes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "groupId": self.group_id,
            "groupName": self.group_name,
            "status": self.status,
            "technicalPlatformId": self.technical_platform_id,
            "parentId": self.parent_id,
            "runtimes": list(self.runtimes),
            "themeKey": self.id,
        }


class CanonicalExperienceRegistry:
    """Registry fechado usado pelo tema; runtime continua nos platform manifests."""

    def __init__(self, experiences: builtins.list[CanonicalExperience]) -> None:
        self._items: dict[str, CanonicalExperience] = {}
        for experience in experiences:
            if experience.id in self._items:
                raise SteamZeroError(
                    "E-API-SCHEMA", detail=f"experiência canônica duplicada: {experience.id}"
                )
            self._items[experience.id] = experience
        unknown_parents = {
            experience.parent_id
            for experience in experiences
            if experience.parent_id is not None and experience.parent_id not in self._items
        }
        if unknown_parents:
            raise SteamZeroError(
                "E-API-SCHEMA",
                detail=f"experiências referenciam pais ausentes: {sorted(unknown_parents)}",
            )

    @classmethod
    @lru_cache(maxsize=1)
    def bundled(cls) -> CanonicalExperienceRegistry:
        resource = importlib.resources.files("steamzero.canonical_experiences").joinpath(
            "catalog-v1.json"
        )
        raw = json.loads(resource.read_text(encoding="utf-8"))
        try:
            contracts.validate(raw, _SCHEMA)
        except (ValidationError, KeyError, TypeError, ValueError) as exc:
            raise SteamZeroError(
                "E-API-SCHEMA", detail=f"catálogo canônico inválido: {exc}"
            ) from exc
        experiences: builtins.list[CanonicalExperience] = []
        for group in raw["groups"]:
            for item in group["experiences"]:
                experiences.append(
                    CanonicalExperience(
                        id=str(item["id"]),
                        name=str(item["name"]),
                        kind=str(item["kind"]),
                        group_id=str(group["id"]),
                        group_name=str(group["name"]),
                        status=str(item["status"]),
                        technical_platform_id=(
                            str(item["technicalPlatformId"])
                            if item["technicalPlatformId"] is not None
                            else None
                        ),
                        parent_id=str(item["parentId"]) if item["parentId"] is not None else None,
                        runtimes=tuple(str(runtime) for runtime in item["runtimes"]),
                    )
                )
        return cls(experiences)

    def get(self, experience_id: str) -> CanonicalExperience:
        try:
            return self._items[experience_id]
        except KeyError as exc:
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED",
                detail=f"experiência canônica desconhecida: {experience_id}",
            ) from exc

    def list(self) -> builtins.list[CanonicalExperience]:
        return builtins.list(self._items.values())

    def project(self) -> builtins.list[dict[str, Any]]:
        return [experience.to_dict() for experience in self.list()]
