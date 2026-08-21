# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Instalador de melhorias por jogo: render → alvos → filtragem de ownership.

Onda de costura: este módulo monta APENAS o conteúdo a escrever (bytes +
caminhos relativos) e a filtragem de gerenciabilidade. Escrever pertence ao
fluxo transacional (``plan_write_files``/``apply``); nenhum arquivo é aberto
aqui. A política anti-cheat já foi aplicada antes (``policy_decision``) e é
re-checada por definição a cada render.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from steamzero.adapters.enhancements.renderers import (
    EnhancementRecipe,
    RenderedEnhancementFile,
    manageability_check,
    render_file,
)
from steamzero.core.errors import SteamZeroError
from steamzero.domain.game_enhancements import (
    EnhancementKind,
    ProviderRole,
    policy_decision,
)

_PATH_TOKENS = frozenset({"XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME"})

#: Preferência de formato por tipo de melhoria (primeiro declarado no
#: manifesto vence).
_KIND_FORMAT_ORDER: dict[EnhancementKind, tuple[str, ...]] = {
    EnhancementKind.CHEAT: ("pcsx2-pnach", "cemu-rules", "dolphin-gameini"),
    EnhancementKind.MOD: ("rpcs3-yaml", "duckstation-ini"),
}

_ALLOWED_FIELDS = frozenset(
    {"kind", "category", "title", "source", "description", "version", "codes", "settingLines"}
)


def flatpak_config_home(raw_manifest: Mapping[str, Any], *, home: Path) -> Path | None:
    """Config real de um app Flatpak: ``~/.var/app/<ref>/config``.

    O diretório XDG do host NÃO é lido por um app sandboxed: declarar
    ``{XDG_CONFIG_HOME}`` para um emulador Flatpak grava num caminho que o
    emulador nunca abre — melhoria "aplicada" sem efeito nenhum.
    """
    sources = raw_manifest.get("sources")
    if not isinstance(sources, list):
        return None
    for source in sources:
        if not isinstance(source, dict) or source.get("type") != "flatpak":
            continue
        ref = source.get("ref")
        if isinstance(ref, str) and ref.strip():
            return home / ".var" / "app" / ref.strip() / "config"
    return None


def expand_path_template(
    raw: str,
    *,
    config_home: Path,
    data_home: Path,
    state_home: Path,
    flatpak_config: Path | None = None,
) -> Path:
    """Expande tokens XDG em caminho absoluto do manifesto do adapter."""
    if not isinstance(raw, str) or not raw.strip():
        raise SteamZeroError("E-API-SCHEMA", detail="template de caminho ausente")
    tokens: dict[str, str] = {
        "XDG_CONFIG_HOME": str(config_home),
        "XDG_DATA_HOME": str(data_home),
        "XDG_STATE_HOME": str(state_home),
    }
    if flatpak_config is not None:
        tokens["FLATPAK_CONFIG_HOME"] = str(flatpak_config)
    try:
        expanded = raw.strip().format_map(tokens)
    except (KeyError, ValueError) as exc:
        raise SteamZeroError(
            "E-API-SCHEMA", detail=f"token desconhecido no template: {raw!r}"
        ) from exc
    path = Path(expanded)
    if not path.is_absolute():
        raise SteamZeroError("E-API-SCHEMA", detail=f"template não é absoluto: {raw!r}")
    return path


@dataclass(frozen=True)
class EnhancementTarget:
    """Capacidade de melhorias declarada por um manifesto de emulador."""

    emulator_id: str
    target_dir: Path
    formats: tuple[str, ...]
    supplied: frozenset[EnhancementKind] = frozenset()


def resolve_enhancement_target(
    raw_manifest: dict[str, Any],
    *,
    config_home: Path,
    data_home: Path,
    state_home: Path,
) -> EnhancementTarget | None:
    """Resolve ``paths.enhancementsDir`` + ``enhancements.formats``.

    ``None`` quando o emulador não declara melhoria gerenciada — o chamador
    degrada (nada a escrever), nunca falha.
    """
    enhancements = raw_manifest.get("enhancements")
    if not isinstance(enhancements, dict):
        return None
    formats = tuple(
        str(entry)
        for entry in enhancements.get("formats") or ()
        if isinstance(entry, str) and entry
    )
    paths = raw_manifest.get("paths")
    if not isinstance(paths, dict) or not formats:
        return None
    template = paths.get("enhancementsDir")
    if not isinstance(template, str) or not template.strip():
        return None
    supplied: set[EnhancementKind] = set()
    for entry in enhancements.get("supplied") or ():
        if not isinstance(entry, str):
            continue
        try:
            supplied.add(EnhancementKind(entry))
        except ValueError:
            continue
    try:
        target_dir = expand_path_template(
            template,
            config_home=config_home,
            data_home=data_home,
            state_home=state_home,
            flatpak_config=flatpak_config_home(raw_manifest, home=Path.home()),
        )
    except SteamZeroError:
        # Manifesto mal declarado (ex.: token Flatpak sem fonte flatpak) degrada
        # para "sem melhoria gerenciada" em vez de impedir o lançamento. A
        # declaração errada é pega em test_enhancement_coverage, não no campo.
        return None
    return EnhancementTarget(
        emulator_id=str(raw_manifest.get("id", "")),
        target_dir=target_dir,
        formats=formats,
        supplied=frozenset(supplied),
    )


@dataclass(frozen=True)
class EnhancementDefinition:
    """Definição persistida no settings do jogo (opt-in explícito por jogo)."""

    kind: EnhancementKind
    category: str
    title: str
    source: str
    description: str = ""
    version: str | None = None
    codes: tuple[str, ...] = ()
    setting_lines: tuple[str, ...] = ()
    _nonce: str = field(default="", init=False)

    @classmethod
    def from_mapping(cls, raw: Any) -> EnhancementDefinition:
        if not isinstance(raw, dict):
            raise SteamZeroError("E-API-SCHEMA", detail="definição de melhoria inválida")
        unknown = set(raw).difference(_ALLOWED_FIELDS)
        if unknown:
            raise SteamZeroError(
                "E-API-SCHEMA", detail=f"campo desconhecido na melhoria: {sorted(unknown)}"
            )
        kind_raw = raw.get("kind")
        if not isinstance(kind_raw, str):
            raise SteamZeroError("E-API-SCHEMA", detail="tipo de melhoria ausente")
        try:
            kind = EnhancementKind(kind_raw)
        except ValueError as exc:
            raise SteamZeroError(
                "E-API-SCHEMA", detail=f"tipo de melhoria inválido: {kind_raw!r}"
            ) from exc
        category = raw.get("category")
        title = raw.get("title")
        source = raw.get("source")
        if not isinstance(category, str) or not category.strip():
            raise SteamZeroError("E-API-SCHEMA", detail="categoria obrigatória")
        if not isinstance(title, str) or not title.strip():
            raise SteamZeroError("E-API-SCHEMA", detail="título obrigatório")
        if not isinstance(source, str) or not source.strip():
            raise SteamZeroError("E-API-SCHEMA", detail="proveniência obrigatória")
        description = raw.get("description") or ""
        if not isinstance(description, str):
            raise SteamZeroError("E-API-SCHEMA", detail="descrição inválida")
        version = raw.get("version") or None
        if version is not None and (not isinstance(version, str) or len(version) > 64):
            raise SteamZeroError("E-API-SCHEMA", detail="versão inválida")
        codes = _string_list(raw.get("codes"), "codes")
        setting_lines = _string_list(raw.get("settingLines"), "settingLines")
        if kind is EnhancementKind.CHEAT and not codes:
            raise SteamZeroError("E-ENHANCEMENT-DENIED", detail="cheat exige ao menos um código")
        if kind is EnhancementKind.MOD and not setting_lines:
            raise SteamZeroError(
                "E-ENHANCEMENT-DENIED", detail="mod técnico exige ao menos uma chave"
            )
        return cls(
            kind=kind,
            category=category.strip(),
            title=title.strip(),
            source=source.strip(),
            description=description.strip(),
            version=version,
            codes=codes,
            setting_lines=setting_lines,
        )

    def to_mapping(self) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "kind": self.kind.value,
            "category": self.category,
            "title": self.title,
            "source": self.source,
            "codes": list(self.codes),
            "settingLines": list(self.setting_lines),
        }
        if self.description:
            entry["description"] = self.description
        if self.version is not None:
            entry["version"] = self.version
        return entry


def _string_list(value: Any, key: str) -> tuple[str, ...]:
    if value in (None, ""):
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise SteamZeroError("E-API-SCHEMA", detail=f"campo inválido: {key}")
    cleaned = tuple(item.strip() for item in value if item.strip())
    return cleaned


def first_compatible_format(kind: EnhancementKind, declared: tuple[str, ...]) -> str | None:
    """Primeiro formato declarado que o tipo de melhoria consegue renderizar."""
    for fmt in _KIND_FORMAT_ORDER.get(kind, ()):
        if fmt in declared:
            return fmt
    return None


#: Esquemas cujo valor identifica o jogo no NOME do arquivo de melhoria
#: (serial PSX/PS2, GameID do GameCube/Wii, TITLE_ID do PS3).
_SERIAL_SCHEMES = frozenset(
    {
        "psx-serial",
        "ps2-serial",
        "ps2-elf-crc32",
        "gc-game-id",
        "wii-game-id",
        "ps3-title-id",
    }
)

#: Esquemas cujo valor entra no CONTEÚDO como lista de títulos (Cemu, Switch).
_TITLE_ID_SCHEMES = frozenset({"switch-title-id", "wiiu-product-id"})


def identity_parts(scheme: str | None, value: str | None) -> tuple[str | None, tuple[str, ...]]:
    """Deriva (serial, title_ids) da identidade verificada do jogo.

    Sem isto, GameCube, Wii, PS3 e Wii U caem no caso vazio e nenhum renderer
    consegue nomear o arquivo por jogo — a melhoria vira arquivo compartilhado.
    """
    if not isinstance(scheme, str) or not isinstance(value, str) or not value:
        return None, ()
    if scheme in _TITLE_ID_SCHEMES:
        return None, (value.upper(),)
    if scheme in _SERIAL_SCHEMES:
        return value, ()
    return None, ()


def build_recipe(definition: EnhancementDefinition) -> EnhancementRecipe:
    return EnhancementRecipe(
        kind=definition.kind,
        category=definition.category,
        title=definition.title,
        source=definition.source,
        codes=definition.codes,
        version=definition.version,
        author="SteamZero",
    )


def render_definitions(
    definitions: tuple[EnhancementDefinition, ...],
    *,
    target: EnhancementTarget,
    scheme: str | None,
    value: str | None,
) -> tuple[list[RenderedEnhancementFile], list[dict[str, str]]]:
    """Renderiza cada definição no primeiro formato compatível declarado.

    Rendering falho ou formato ausente degrada aquele item (skip com razão);
    nunca derruba o lançamento do jogo.
    """
    rendered: list[RenderedEnhancementFile] = []
    skipped: list[dict[str, str]] = []
    serial, title_ids = identity_parts(scheme, value)
    for definition in definitions:
        fmt = first_compatible_format(definition.kind, target.formats)
        if fmt is None:
            skipped.append(
                {"title": definition.title, "reason": "emulador não declara formato compatível"}
            )
            continue
        try:
            recipe = build_recipe(definition)
            file = render_file(
                fmt,
                recipe,
                serial=serial,
                title_ids=title_ids,
                settings=definition.setting_lines,
            )
        except SteamZeroError as exc:
            skipped.append({"title": definition.title, "reason": str(exc)})
            continue
        rendered.append(file)
    return rendered, skipped


def installation_files(
    rendered: list[RenderedEnhancementFile],
    *,
    target_dir: Path,
) -> dict[Path, bytes]:
    """Conteúdo final por caminho absoluto (última definição vence por arquivo)."""
    writes: dict[Path, bytes] = {}
    for file in rendered:
        target = target_dir / file.relative_path
        if ".." in target.parts or not target.is_relative_to(target_dir):
            raise SteamZeroError(
                "E-API-SCHEMA", detail=f"caminho relativo inválido: {file.relative_path!r}"
            )
        writes[target] = file.data
    return writes


def filter_managed(
    writes: dict[Path, bytes],
    *,
    existing: dict[Path, bytes],
) -> tuple[dict[Path, bytes], list[dict[str, str]]]:
    """Ownership + idempotência: nunca substitui arquivo de terceiros.

    - alvo inexistente → escrever;
    - alvo com exatamente o mesmo conteúdo → já aplicado (no-op);
    - alvo com marcador do SteamZero e conteúdo diferente → substituir;
    - alvo sem marcador (terceiro) → pular com razão.
    """
    to_do: dict[Path, bytes] = {}
    skipped: list[dict[str, str]] = []
    for path, content in writes.items():
        prior = existing.get(path)
        if prior is None:
            to_do[path] = content
            continue
        if prior == content:
            continue
        ok, reason = manageability_check(prior)
        if not ok:
            skipped.append({"path": str(path), "reason": reason})
            continue
        to_do[path] = content
    return to_do, skipped


def role_for_kind(target: EnhancementTarget, kind: EnhancementKind) -> ProviderRole:
    """Papel do provedor: emulador é dono quando declara o tipo em ``supplied``."""
    if kind in target.supplied:
        return ProviderRole.EMULATOR_SUPPLIED
    return ProviderRole.STEAMZERO_SUPPLIED


def validate_policy(
    kind: EnhancementKind,
    category: str,
    *,
    role: ProviderRole,
    source: str | None,
) -> None:
    """Re-checagem da política anti-cheat no ponto de uso (idempotente)."""
    decision = policy_decision(kind, category, role=role, source=source)
    if not decision.allowed:
        raise SteamZeroError("E-ENHANCEMENT-DENIED", detail=decision.reason or "negada")
