# SPDX-License-Identifier: GPL-3.0-or-later
"""Tags, favoritos e coleções inteligentes locais e reversíveis."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from steamzero.api import contracts
from steamzero.core import paths, transaction
from steamzero.core.errors import SteamZeroError

_SCHEMA = "feat-collection-v1.schema.json"
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
_GAME_REF = re.compile(r"^(?:steam|emulation|cloud|port):[A-Za-z0-9._:@+-]{1,160}$")
_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
_FIELDS = frozenset({"source", "platformId", "tag", "favorite"})


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _empty() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "revision": 0,
        "tags": [],
        "favorites": [],
        "assignments": [],
        "collections": [],
    }


class CollectionManager:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or paths.collection_config_path()

    def state(self, games: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        document = self._load()
        catalog = self._catalog(games or [], document)
        payload = {
            "schemaVersion": 1,
            "generatedAt": _now(),
            "revision": document["revision"],
            "tags": document["tags"],
            "favorites": document["favorites"],
            "assignments": document["assignments"],
            "collections": [
                {
                    **collection,
                    "members": [
                        game["gameRef"]
                        for game in catalog
                        if self._matches(collection["rule"], game)
                    ],
                }
                for collection in document["collections"]
            ],
        }
        contracts.validate(payload, _SCHEMA)
        return payload

    def plan(self, action: dict[str, Any]) -> dict[str, Any]:
        before = self._load()
        after = json.loads(json.dumps(before))
        action_id = self._text(action, "actionId", 80)
        self._mutate(after, action_id, action)
        after["revision"] = before["revision"] + 1
        self._validate_document(after)
        content = (json.dumps(after, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
        plan = transaction.plan_write_files(
            {self._path: content},
            root=self._path.parent,
            kind=f"collections.{action_id}",
        )
        return {
            "planId": plan.plan_id,
            "confirmToken": plan.confirm_token,
            "actionId": action_id,
            "summary": self._summary(action_id, action),
            "beforeRevision": before["revision"],
            "afterRevision": after["revision"],
            "rollbackGuarantee": plan.rollback_guarantee,
            "expiresAt": plan.expires_at,
        }

    def apply(self, plan_id: str, confirm_token: str) -> dict[str, Any]:
        plan = transaction.load_plan(plan_id)
        if (
            not plan.kind.startswith("collections.")
            or Path(plan.root) != self._path.parent.resolve()
            or len(plan.actions) != 1
            or Path(plan.actions[0].target) != self._path.resolve()
            or plan.actions[0].kind != "write"
        ):
            raise SteamZeroError("E-TX-STALE-PLAN", detail="plano não pertence às coleções")
        expected = json.loads(plan.actions[0].new_content())
        self._validate_document(expected)

        def verify() -> None:
            if self._load() != expected:
                raise RuntimeError("estado de coleções divergiu após apply")

        result = transaction.apply(plan_id, confirm_token, smoke=verify)
        return {
            "status": result.status,
            "operationId": result.operation_id,
            "revision": expected["revision"],
        }

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            return _empty()
        if self._path.is_symlink() or not self._path.is_file():
            raise SteamZeroError("E-STATE-INTEGRITY", detail="estado de coleções inseguro")
        try:
            if self._path.stat().st_size > 1024 * 1024:
                raise SteamZeroError("E-CONTENT-LIMIT", detail="coleções excedem 1 MiB")
            value = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise SteamZeroError(
                "E-STATE-INTEGRITY", detail="estado de coleções corrompido"
            ) from exc
        self._validate_document(value)
        return cast(dict[str, Any], value)

    @classmethod
    def _validate_document(cls, value: Any) -> None:
        if not isinstance(value, dict) or set(value) != {
            "schemaVersion",
            "revision",
            "tags",
            "favorites",
            "assignments",
            "collections",
        }:
            raise SteamZeroError("E-STATE-INTEGRITY", detail="documento de coleções inválido")
        if value["schemaVersion"] != 1 or not isinstance(value["revision"], int):
            raise SteamZeroError("E-STATE-INTEGRITY", detail="versão de coleções inválida")
        if not all(
            isinstance(value[key], list)
            for key in value
            if key not in {"schemaVersion", "revision"}
        ):
            raise SteamZeroError("E-STATE-INTEGRITY", detail="listas de coleções inválidas")
        if len(value["tags"]) > 64 or len(value["favorites"]) > 10000:
            raise SteamZeroError("E-CONTENT-LIMIT", detail="limite de coleções excedido")
        tag_ids: set[str] = set()
        for tag in value["tags"]:
            if (
                not isinstance(tag, dict)
                or set(tag) != {"id", "name", "color"}
                or not isinstance(tag["id"], str)
                or not _SLUG.fullmatch(tag["id"])
                or not isinstance(tag["name"], str)
                or not 1 <= len(tag["name"].strip()) <= 48
                or not isinstance(tag["color"], str)
                or not _COLOR.fullmatch(tag["color"])
                or tag["id"] in tag_ids
            ):
                raise SteamZeroError("E-STATE-INTEGRITY", detail="tag inválida")
            tag_ids.add(tag["id"])
        if len(set(value["favorites"])) != len(value["favorites"]) or not all(
            isinstance(item, str) and _GAME_REF.fullmatch(item) for item in value["favorites"]
        ):
            raise SteamZeroError("E-STATE-INTEGRITY", detail="favoritos inválidos")
        seen_games: set[str] = set()
        for assignment in value["assignments"]:
            if (
                not isinstance(assignment, dict)
                or set(assignment) != {"gameRef", "tagIds"}
                or not isinstance(assignment["gameRef"], str)
                or not _GAME_REF.fullmatch(assignment["gameRef"])
                or assignment["gameRef"] in seen_games
                or not isinstance(assignment["tagIds"], list)
                or len(set(assignment["tagIds"])) != len(assignment["tagIds"])
                or not set(assignment["tagIds"]) <= tag_ids
            ):
                raise SteamZeroError("E-STATE-INTEGRITY", detail="atribuição de tag inválida")
            seen_games.add(assignment["gameRef"])
        collection_ids: set[str] = set()
        for collection in value["collections"]:
            if (
                not isinstance(collection, dict)
                or set(collection) != {"id", "name", "rule"}
                or not isinstance(collection["id"], str)
                or not _SLUG.fullmatch(collection["id"])
                or collection["id"] in collection_ids
                or not isinstance(collection["name"], str)
                or not 1 <= len(collection["name"].strip()) <= 64
            ):
                raise SteamZeroError("E-STATE-INTEGRITY", detail="coleção inválida")
            cls._validate_rule(collection["rule"], tag_ids)
            collection_ids.add(collection["id"])

    @staticmethod
    def _validate_rule(rule: Any, tag_ids: set[str]) -> None:
        if not isinstance(rule, dict) or set(rule) != {"match", "predicates"}:
            raise SteamZeroError("E-API-SCHEMA", detail="regra de coleção inválida")
        if rule["match"] not in {"all", "any"} or not isinstance(rule["predicates"], list):
            raise SteamZeroError("E-API-SCHEMA", detail="regra de coleção inválida")
        if not 1 <= len(rule["predicates"]) <= 8:
            raise SteamZeroError("E-API-SCHEMA", detail="regra precisa de 1 a 8 predicados")
        for predicate in rule["predicates"]:
            if (
                not isinstance(predicate, dict)
                or set(predicate) != {"field", "value"}
                or predicate["field"] not in _FIELDS
                or not isinstance(predicate["value"], str | bool)
                or (predicate["field"] == "favorite" and not isinstance(predicate["value"], bool))
                or (predicate["field"] == "tag" and predicate["value"] not in tag_ids)
            ):
                raise SteamZeroError("E-API-SCHEMA", detail="predicado de coleção inválido")

    def _mutate(self, document: dict[str, Any], action_id: str, action: dict[str, Any]) -> None:
        if action_id == "tag.upsert":
            tag_id = self._slug(action, "tagId")
            tag = {
                "id": tag_id,
                "name": self._text(action, "name", 48).strip(),
                "color": self._text(action, "color", 7),
            }
            document["tags"] = [item for item in document["tags"] if item["id"] != tag_id]
            document["tags"].append(tag)
            document["tags"].sort(key=lambda item: item["id"])
        elif action_id == "tag.delete":
            tag_id = self._slug(action, "tagId")
            document["tags"] = [item for item in document["tags"] if item["id"] != tag_id]
            for assignment in document["assignments"]:
                assignment["tagIds"] = [item for item in assignment["tagIds"] if item != tag_id]
            document["assignments"] = [
                assignment for assignment in document["assignments"] if assignment["tagIds"]
            ]
            document["collections"] = [
                item
                for item in document["collections"]
                if not any(
                    pred["field"] == "tag" and pred["value"] == tag_id
                    for pred in item["rule"]["predicates"]
                )
            ]
        elif action_id == "favorite.set":
            game_ref = self._game_ref(action)
            selected = self._boolean(action, "value")
            values = set(document["favorites"])
            values.add(game_ref) if selected else values.discard(game_ref)
            document["favorites"] = sorted(values)
        elif action_id == "game-tag.set":
            game_ref = self._game_ref(action)
            tag_id = self._slug(action, "tagId")
            if tag_id not in {item["id"] for item in document["tags"]}:
                raise SteamZeroError("E-API-SCHEMA", detail="tag inexistente")
            selected = self._boolean(action, "value")
            assignments = {item["gameRef"]: set(item["tagIds"]) for item in document["assignments"]}
            tags = assignments.setdefault(game_ref, set())
            tags.add(tag_id) if selected else tags.discard(tag_id)
            document["assignments"] = [
                {"gameRef": ref, "tagIds": sorted(values)}
                for ref, values in sorted(assignments.items())
                if values
            ]
        elif action_id == "collection.upsert":
            collection_id = self._slug(action, "collectionId")
            collection = {
                "id": collection_id,
                "name": self._text(action, "name", 64).strip(),
                "rule": action.get("rule"),
            }
            self._validate_rule(collection["rule"], {item["id"] for item in document["tags"]})
            document["collections"] = [
                item for item in document["collections"] if item["id"] != collection_id
            ]
            document["collections"].append(collection)
            document["collections"].sort(key=lambda item: item["id"])
        elif action_id == "collection.delete":
            collection_id = self._slug(action, "collectionId")
            document["collections"] = [
                item for item in document["collections"] if item["id"] != collection_id
            ]
        else:
            raise SteamZeroError("E-API-SCHEMA", detail="ação de coleção desconhecida")

    @staticmethod
    def _catalog(games: list[dict[str, Any]], document: dict[str, Any]) -> list[dict[str, Any]]:
        favorites = set(document["favorites"])
        assignments = {item["gameRef"]: item["tagIds"] for item in document["assignments"]}
        result: list[dict[str, Any]] = []
        for game in games[:10000]:
            game_ref = game.get("gameRef")
            if not isinstance(game_ref, str) or not _GAME_REF.fullmatch(game_ref):
                continue
            result.append(
                {
                    **game,
                    "favorite": game_ref in favorites,
                    "tags": assignments.get(game_ref, []),
                }
            )
        return result

    @staticmethod
    def _matches(rule: dict[str, Any], game: dict[str, Any]) -> bool:
        values = []
        for predicate in rule["predicates"]:
            field, expected = predicate["field"], predicate["value"]
            actual: Any = (
                expected in game.get("tags", [])
                if field == "tag"
                else game.get("favorite") is expected
                if field == "favorite"
                else game.get(field)
            )
            values.append(actual if field in {"tag", "favorite"} else actual == expected)
        return all(values) if rule["match"] == "all" else any(values)

    @staticmethod
    def _text(action: dict[str, Any], key: str, maximum: int) -> str:
        value = action.get(key)
        if not isinstance(value, str) or not value or len(value) > maximum or "\x00" in value:
            raise SteamZeroError("E-API-SCHEMA", detail=f"{key} inválido")
        return value

    @classmethod
    def _slug(cls, action: dict[str, Any], key: str) -> str:
        value = cls._text(action, key, 63)
        if not _SLUG.fullmatch(value):
            raise SteamZeroError("E-API-SCHEMA", detail=f"{key} inválido")
        return value

    @classmethod
    def _game_ref(cls, action: dict[str, Any]) -> str:
        value = cls._text(action, "gameRef", 180)
        if not _GAME_REF.fullmatch(value):
            raise SteamZeroError("E-API-SCHEMA", detail="gameRef inválido")
        return value

    @staticmethod
    def _boolean(action: dict[str, Any], key: str) -> bool:
        value = action.get(key)
        if not isinstance(value, bool):
            raise SteamZeroError("E-API-SCHEMA", detail=f"{key} precisa ser booleano")
        return value

    @staticmethod
    def _summary(action_id: str, action: dict[str, Any]) -> str:
        labels = {
            "tag.upsert": "Salvar tag",
            "tag.delete": "Excluir tag e referências",
            "favorite.set": "Alterar favorito",
            "game-tag.set": "Alterar tag do jogo",
            "collection.upsert": "Salvar coleção inteligente",
            "collection.delete": "Excluir coleção inteligente",
        }
        return labels.get(action_id, action_id)
