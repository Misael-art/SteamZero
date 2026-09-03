# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Layout em disco (TRANSACTION-MODEL §Layout, ADR-0005).

Todos os caminhos derivam de XDG (sobrescrevíveis por env, o que permite isolar
o estado em testes). Permissões: diretórios 0700, arquivos 0600 (SR-07).

    $XDG_STATE_HOME/steamzero/
      state.db  journal/<opId>.jsonl  staging/<opId>/  backups/<opId>/
      quarantine/<opId>/  logs/core.jsonl
"""

from __future__ import annotations

import os
from pathlib import Path

APP = "steamzero"


def _home() -> Path:
    return Path.home()


def state_home() -> Path:
    """Raiz do estado: ``$XDG_STATE_HOME/steamzero`` (default ~/.local/state)."""
    base = os.environ.get("XDG_STATE_HOME")
    return (Path(base) if base else _home() / ".local" / "state") / APP


def data_home() -> Path:
    base = os.environ.get("XDG_DATA_HOME")
    return (Path(base) if base else _home() / ".local" / "share") / APP


def roms_dir() -> Path:
    return data_home() / "roms"


def bios_dir() -> Path:
    return data_home() / "bios"


def keys_dir() -> Path:
    return data_home() / "keys"


def firmware_dir() -> Path:
    return data_home() / "firmware"


def saves_dir() -> Path:
    return data_home() / "saves"


def media_dir() -> Path:
    return data_home() / "media"


# --- MediaHub subcaminhos (masters / optimized / views) --------------------
def media_masters_dir() -> Path:
    return media_dir() / "masters"


def media_optimized_dir() -> Path:
    return media_dir() / "optimized"


def media_views_dir() -> Path:
    return media_dir() / "views"


def media_registry_path() -> Path:
    return media_dir() / "registry" / "platforms-v1.json"


def media_assignments_path() -> Path:
    return media_dir() / "registry" / "assignments-v1.json"


def media_steam_view_manifest_path() -> Path:
    return media_dir() / "registry" / "steam-view-manifest-v1.json"


def media_steam_grid_dir(steam_user_id: str) -> Path:
    return media_views_dir() / "steam" / steam_user_id / "grid"


def mods_dir() -> Path:
    return data_home() / "mods"


def themes_dir() -> Path:
    return data_home() / "themes"


def theme_assets_dir() -> Path:
    """Store de assets de tema, endereçado por conteúdo.

    Separado de ``themes_dir()`` de propósito: ali moram os manifestos, que são
    a fonte de verdade do que está instalado, e aqui os blobs, que são cache
    reconstruível e compartilhado. Misturá-los faria a remoção de um tema
    parecer autorizada a apagar arte que outro ainda referencia.
    """
    return data_home() / "theme-assets"


def scenes_dir() -> Path:
    """Cenas compiladas de frontends declarativos, separadas de theme.json."""
    return data_home() / "scenes"


def config_home() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    return (Path(base) if base else _home() / ".config") / APP


def xdg_config_root() -> Path:
    """Raiz XDG de config do usuário, SEM o sufixo ``steamzero``.

    ``config_home()`` é o diretório do SteamZero. Um arquivo destinado a um
    emulador de terceiros (ex.: ``~/.config/duckstation``) precisa da raiz: se
    for escrito sob ``~/.config/steamzero/...`` o emulador nunca o lê e a
    melhoria fica "aplicada" sem efeito.
    """
    base = os.environ.get("XDG_CONFIG_HOME")
    return Path(base) if base else _home() / ".config"


def xdg_data_root() -> Path:
    """Raiz XDG de dados do usuário, sem o sufixo ``steamzero``."""
    base = os.environ.get("XDG_DATA_HOME")
    return Path(base) if base else _home() / ".local" / "share"


def xdg_state_root() -> Path:
    """Raiz XDG de estado do usuário, sem o sufixo ``steamzero``."""
    base = os.environ.get("XDG_STATE_HOME")
    return Path(base) if base else _home() / ".local" / "state"


def collection_config_path() -> Path:
    return config_home() / "collections-v1.json"


def theme_preference_path() -> Path:
    return config_home() / "theme-preference-v1.json"


def bitrot_state_path() -> Path:
    return state_home() / "bitrot-v1.json"


def runtime_dir() -> Path:
    """Diretório de runtime (socket): ``$XDG_RUNTIME_DIR/steamzero``."""
    base = os.environ.get("XDG_RUNTIME_DIR")
    if base:
        return Path(base) / APP
    return Path(f"/run/user/{os.getuid()}") / APP


# --- subcaminhos do estado -------------------------------------------------
def journal_dir() -> Path:
    return state_home() / "journal"


def staging_dir() -> Path:
    return state_home() / "staging"


def backups_dir() -> Path:
    return state_home() / "backups"


def quarantine_dir() -> Path:
    return state_home() / "quarantine"


def cache_home() -> Path:
    """Raiz de cache: ``$XDG_CACHE_HOME/steamzero`` (default ~/.cache)."""
    base = os.environ.get("XDG_CACHE_HOME")
    return (Path(base) if base else _home() / ".cache") / APP


def theme_catalog_cache_path() -> Path:
    return cache_home() / "theme-catalog-v1.json"


def theme_marketplace_config_path() -> Path:
    """Opt-in explícito do marketplace remoto.

    O marketplace nasce DESLIGADO: sem este arquivo não há catálogo remoto e
    nenhum host embutido é assumido. Ligar é decisão registrada do operador.
    """
    return config_home() / "theme-marketplace-v1.json"


def logs_dir() -> Path:
    return state_home() / "logs"


def plans_dir() -> Path:
    return state_home() / "plans"


def plan_path(plan_id: str) -> Path:
    return plans_dir() / f"{plan_id}.json"


def component_operations_dir() -> Path:
    return state_home() / "component-operations"


def component_operation_path(operation_id: str) -> Path:
    return component_operations_dir() / f"{operation_id}.json"


def steam_maintenance_plans_dir() -> Path:
    return state_home() / "steam-maintenance-plans"


def steam_maintenance_plan_path(plan_id: str) -> Path:
    return steam_maintenance_plans_dir() / f"{plan_id}.json"


def steam_maintenance_operations_dir() -> Path:
    return state_home() / "steam-maintenance-operations"


def steam_maintenance_operation_path(operation_id: str) -> Path:
    return steam_maintenance_operations_dir() / f"{operation_id}.json"


def state_db() -> Path:
    return state_home() / "state.db"


def core_log() -> Path:
    return logs_dir() / "core.jsonl"


def journal_path(operation_id: str) -> Path:
    return journal_dir() / f"{operation_id}.jsonl"


def staging_for(operation_id: str) -> Path:
    return staging_dir() / operation_id


def backup_for(operation_id: str) -> Path:
    return backups_dir() / operation_id


def quarantine_for(operation_id: str) -> Path:
    return quarantine_dir() / operation_id


#: Todos os diretórios base do estado (criados por core.fs.ensure_state_layout).
STATE_SUBDIRS = (journal_dir, staging_dir, backups_dir, quarantine_dir, logs_dir)
