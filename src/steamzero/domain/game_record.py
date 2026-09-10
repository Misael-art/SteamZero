# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Modelo canônico ``GameRecord`` (frente A1 do plano AURA).

O contrato normativo é o schema empacotado em
``src/steamzero/schemas/game-record-v1.schema.json`` (frente A0). Este módulo é
a face Python dele: nunca reescreve as regras, valida contra o próprio schema.
Duplicar enum ou limite aqui criaria uma segunda fonte de verdade que divergiria
em silêncio.

Duas invariantes governam a importação, e ambas existem porque a alternativa é
perder dado do usuário:

1. **Campo desconhecido sobrevive ao round-trip.** Um formato externo mais novo
   que este código não pode ser truncado por ele. ``to_mapping`` devolve o que
   ``from_mapping`` recebeu.
2. **Fonte pobre não apaga informação rica.** Todo campo carrega proveniência
   com origem, timestamp, confiança e política de conflito; a fusão respeita a
   política declarada e registra o conflito em vez de escolher em silêncio.

Conflito não resolvido vira estado explícito em ``warnings`` — a UI degrada
honestamente (AGENTS.md §8). Este módulo é domínio puro: não lê disco, não
acessa rede e não importa adapters.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any

_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "game-record-v1.schema.json"

#: Campos obrigatórios do schema. Mantido para mensagens de erro legíveis;
#: a validação real continua sendo feita pelo schema.
_REQUIRED = ("schemaVersion", "id", "title", "platformId", "path", "availability", "updatedAt")


class ConflictPolicy(Enum):
    """Como resolver duas fontes que discordam sobre o mesmo campo."""

    KEEP_RICHEST = "keepRichest"
    PREFER_SOURCE = "preferSource"
    MANUAL = "manual"


class MediaRole(Enum):
    """Papéis de mídia do contrato. A engine deriva variações; não há outros."""

    COVER = "cover"
    FANART = "fanart"
    SCREENSHOT = "screenshot"
    MARQUEE = "marquee"
    VIDEO = "video"
    ICON = "icon"


class GameRecordError(ValueError):
    """Registro inválido perante o contrato."""


@lru_cache(maxsize=1)
def _schema() -> dict[str, Any]:
    if not _SCHEMA_PATH.is_file():
        raise GameRecordError(f"schema de contrato ausente: {_SCHEMA_PATH}")
    loaded = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise GameRecordError("schema de contrato malformado: raiz não é objeto")
    return loaded


def validate_mapping(payload: Mapping[str, Any]) -> None:
    """Valida contra o schema de A0, ou levanta ``GameRecordError``.

    A mensagem cita o JSON Pointer do campo culpado. Erro que anuncia a causa
    errada custa mais tempo do que erro nenhum.
    """
    from jsonschema import Draft202012Validator, FormatChecker

    validator = Draft202012Validator(_schema(), format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(dict(payload)), key=lambda err: list(err.path))
    if not errors:
        return
    first = errors[0]
    pointer = "/" + "/".join(str(part) for part in first.path) if first.path else "/"
    raise GameRecordError(f"GameRecord inválido em {pointer}: {first.message}")


@dataclass(frozen=True)
class ProvenanceEntry:
    """Origem, timestamp, confiança e política de conflito de um campo."""

    source: str
    retrieved_at: str
    confidence: float
    conflict_policy: ConflictPolicy = ConflictPolicy.KEEP_RICHEST

    def to_mapping(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "retrievedAt": self.retrieved_at,
            "confidence": self.confidence,
            "conflictPolicy": self.conflict_policy.value,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> ProvenanceEntry:
        try:
            policy = ConflictPolicy(payload["conflictPolicy"])
        except (KeyError, ValueError) as exc:
            raise GameRecordError(
                f"conflictPolicy inválida em proveniência: {payload.get('conflictPolicy')!r}"
            ) from exc
        try:
            return cls(
                source=str(payload["source"]),
                retrieved_at=str(payload["retrievedAt"]),
                confidence=float(payload["confidence"]),
                conflict_policy=policy,
            )
        except KeyError as exc:
            raise GameRecordError(f"proveniência sem campo obrigatório: {exc.args[0]}") from exc


def _slug(text: str) -> str:
    """``camelCase`` -> ``kebab-case`` restrito ao alfabeto de ``warnings``."""
    out: list[str] = []
    for char in text:
        if char.isupper():
            out.append("-")
            out.append(char.lower())
        elif char.isalnum():
            out.append(char.lower())
        else:
            out.append("-")
    return "".join(out).strip("-") or "campo"


def conflict_warning(field_name: str) -> str:
    """Código de aviso para conflito manual.

    ``warnings`` é lista de códigos legíveis por máquina (o schema restringe a
    ``^[a-z0-9][a-z0-9-]{1,63}$``), não texto para humano: a UI traduz o código
    pelo catálogo de mensagens. Frase solta aqui reprova no contrato.
    """
    return f"conflict-manual-{_slug(field_name)}"[:64].rstrip("-")


def _richness(value: Any) -> int:
    """Quanta informação um valor carrega, para ``keepRichest``.

    Só compara valores do mesmo campo. Não é uma métrica universal de
    qualidade: é o desempate mínimo que impede um formato pobre de apagar um
    rico.
    """
    if value is None:
        return -1
    if isinstance(value, str):
        return len(value.strip())
    if isinstance(value, Mapping):
        return len(value)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return len(value)
    return 0


@dataclass(frozen=True)
class MergeOutcome:
    """Resultado de uma fusão: registro final e os conflitos não resolvidos."""

    record: GameRecord
    conflicts: tuple[str, ...] = ()


@dataclass(frozen=True)
class GameRecord:
    """Registro canônico de um jogo.

    ``payload`` é o mapeamento completo e já validado. Os acessores tipados
    cobrem o núcleo; campos desconhecidos permanecem intactos no payload para
    sobreviver ao round-trip.
    """

    payload: Mapping[str, Any] = field(default_factory=dict)

    # -- construção ---------------------------------------------------------

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any], *, validate: bool = True) -> GameRecord:
        if not isinstance(payload, Mapping):
            raise GameRecordError("GameRecord exige um mapeamento")
        missing = [key for key in _REQUIRED if key not in payload]
        if missing:
            raise GameRecordError(f"GameRecord sem campo obrigatório: {', '.join(missing)}")
        frozen = json.loads(json.dumps(dict(payload)))
        if validate:
            validate_mapping(frozen)
        return cls(payload=frozen)

    def to_mapping(self) -> dict[str, Any]:
        """Cópia profunda do payload, incluindo campos desconhecidos."""
        copied: dict[str, Any] = json.loads(json.dumps(dict(self.payload)))
        return copied

    # -- acessores do núcleo ------------------------------------------------

    @property
    def id(self) -> str:
        return str(self.payload["id"])

    @property
    def title(self) -> str:
        return str(self.payload["title"])

    @property
    def platform_id(self) -> str:
        return str(self.payload["platformId"])

    @property
    def availability(self) -> str:
        return str(self.payload["availability"])

    @property
    def warnings(self) -> tuple[str, ...]:
        raw = self.payload.get("warnings") or ()
        return tuple(str(item) for item in raw)

    def media(self, role: MediaRole) -> dict[str, Any] | None:
        """Asset de um papel, ou ``None`` quando ausente.

        Arte ausente é estado normal, não erro: o tema tem fallback obrigatório
        para todas as regiões (ADR-0028).
        """
        media = self.payload.get("media")
        if not isinstance(media, Mapping):
            return None
        asset = media.get(role.value)
        return dict(asset) if isinstance(asset, Mapping) else None

    def provenance_of(self, field_name: str) -> ProvenanceEntry | None:
        provenance = self.payload.get("provenance")
        if not isinstance(provenance, Mapping):
            return None
        entry = provenance.get(field_name)
        return ProvenanceEntry.from_mapping(entry) if isinstance(entry, Mapping) else None

    # -- fusão --------------------------------------------------------------

    def merge(self, incoming: GameRecord) -> MergeOutcome:
        """Funde ``incoming`` neste registro respeitando a proveniência.

        Regra por campo, decidida pela política declarada na proveniência do
        registro que já existe (o que chega não dita como será tratado):

        - ``preferSource``: o valor que chega vence.
        - ``keepRichest``: vence o valor com mais informação; empate mantém o
          atual, para que reimportar seja idempotente.
        - ``manual``: nada muda e o conflito é registrado em ``warnings``.

        Campo ausente no atual é sempre adicionado — isso não é conflito.
        """
        if incoming.id != self.id:
            raise GameRecordError(
                f"fusão exige o mesmo id: {self.id!r} != {incoming.id!r}",
            )

        merged = self.to_mapping()
        conflicts: list[str] = []

        for key, new_value in incoming.payload.items():
            if key in {"provenance", "warnings"}:
                continue
            if key not in merged:
                merged[key] = json.loads(json.dumps(new_value))
                continue
            current = merged[key]
            if current == new_value:
                continue

            policy = self._policy_for(key)
            if policy is ConflictPolicy.PREFER_SOURCE:
                merged[key] = json.loads(json.dumps(new_value))
            elif policy is ConflictPolicy.KEEP_RICHEST:
                if _richness(new_value) > _richness(current):
                    merged[key] = json.loads(json.dumps(new_value))
            else:
                conflicts.append(key)

        provenance = self._merged_provenance(incoming, conflicts)
        if provenance:
            merged["provenance"] = provenance
        elif "provenance" in merged:
            # ``provenance`` exige minProperties 1: mapa vazio é inválido.
            del merged["provenance"]

        if conflicts:
            existing = list(merged.get("warnings") or [])
            for key in conflicts:
                note = conflict_warning(key)
                if note not in existing:
                    existing.append(note)
            merged["warnings"] = existing

        return MergeOutcome(record=GameRecord.from_mapping(merged), conflicts=tuple(conflicts))

    def _policy_for(self, field_name: str) -> ConflictPolicy:
        entry = self.provenance_of(field_name)
        return entry.conflict_policy if entry else ConflictPolicy.KEEP_RICHEST

    def _merged_provenance(self, incoming: GameRecord, conflicts: Sequence[str]) -> dict[str, Any]:
        """Proveniência do resultado.

        Um campo em conflito manual conserva a proveniência atual: o valor não
        mudou, logo alegar a nova origem seria falsear o estado.
        """
        current = self.payload.get("provenance")
        result: dict[str, Any] = dict(current) if isinstance(current, Mapping) else {}
        other = incoming.payload.get("provenance")
        if isinstance(other, Mapping):
            for key, entry in other.items():
                if key in conflicts:
                    continue
                result[key] = dict(entry) if isinstance(entry, Mapping) else entry
        return result
