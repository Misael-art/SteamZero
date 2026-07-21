# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Integração com o binário externo ns-emu-mod-downloader.

Chama o CLI ``ns-emu-mod-downloader`` como subprocesso para escanear jogos
instalados e baixar mods. O binário gerencia automaticamente o match por
Title ID + Build ID com os repositórios StevensND, Fl4sh9174, KeatonTheBot.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from steamzero.ports import ModCandidate, ModCatalogPort, ModIdentity

_MOD_TYPES_FROM_TOOL = {
    "ultrawide": "ultrawide",
    "60fps": "performance",
    "performance": "performance",
    "visual": "graphics",
    "graphics": "graphics",
    "gameplay": "gameplay",
    "patch": "patch",
    "fix": "patch",
}


class NsEmuModDownloaderSource(ModCatalogPort):
    """Fonte de mods via ns-emu-mod-downloader CLI.

    O binário externo escaneia uma pasta de ROMs, identifica Title IDs e
    Build IDs, e baixa mods correspondentes dos repositórios upstream.

    Se o binário não estiver disponível, a fonte fica vazia silenciosamente
    (fallback para outras fontes como GithubModSource e SemdSource).
    """

    def __init__(self, binary_path: str | Path = "ns-emu-mod-downloader") -> None:
        self._binary = str(binary_path)
        self._available: bool | None = None
        self._local_cache: list[ModCandidate] = []

    def _check_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            result = subprocess.run(  # noqa: S603
                [self._binary, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            self._available = result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            self._available = False
        return self._available

    # --- ModCatalogPort ------------------------------------------------------

    def search_by_title_id(self, title_id: str) -> list[ModCandidate]:
        self._ensure_cached()
        return [c for c in self._local_cache if c.title_id == title_id]

    def search_by_build_id(self, title_id: str, build_id: str) -> list[ModCandidate]:
        self._ensure_cached()
        return [c for c in self._local_cache if c.title_id == title_id and c.build_id == build_id]

    def refresh_catalog(self) -> int:
        self._local_cache.clear()
        return self._fetch_all()

    def _ensure_cached(self) -> None:
        if not self._local_cache and self._check_available():
            self._fetch_all()

    def _fetch_all(self) -> int:
        if not self._check_available():
            return 0
        try:
            result = subprocess.run(  # noqa: S603
                [self._binary, "list"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                return 0
            candidates = self._parse_list_output(result.stdout)
            self._local_cache = candidates
            return len(candidates)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            self._available = False
            return 0

    def _parse_list_output(self, output: str) -> list[ModCandidate]:
        """Interpreta a saída JSON ou textual do 'ns-emu-mod-downloader list'."""
        output = output.strip()
        if not output:
            return []

        if output.startswith("["):
            return self._parse_json(output)
        return self._parse_text(output)

    def _parse_json(self, output: str) -> list[ModCandidate]:
        try:
            data: list[dict[str, Any]] = json.loads(output)
        except json.JSONDecodeError:
            return []
        candidates: list[ModCandidate] = []
        for item in data:
            title_id = (item.get("title_id") or item.get("titleId") or "").upper()
            if not title_id:
                continue
            name = item.get("name") or item.get("mod_name") or "unknown"
            raw_type = item.get("type") or item.get("mod_type") or "other"
            candidates.append(
                ModCandidate(
                    title_id=title_id,
                    build_id=(item.get("build_id") or item.get("buildId") or "").upper() or None,
                    identity=ModIdentity(
                        name=name,
                        mod_type=_MOD_TYPES_FROM_TOOL.get(raw_type.lower(), "other"),
                        source="ns-emu-mod-downloader",
                        source_url=item.get("url") or "",
                        version=item.get("version"),
                        description=item.get("description"),
                        author=item.get("author") or item.get("repo"),
                    ),
                    match_confidence=1.0 if item.get("build_id") else 0.7,
                )
            )
        return candidates

    def _parse_text(self, output: str) -> list[ModCandidate]:
        candidates: list[ModCandidate] = []
        for line in output.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            title_id = parts[0].upper()
            if len(title_id) != 16 or not title_id.isalnum():
                continue
            name = " ".join(parts[1:])
            candidates.append(
                ModCandidate(
                    title_id=title_id,
                    build_id=None,
                    identity=ModIdentity(
                        name=name,
                        mod_type="other",
                        source="ns-emu-mod-downloader",
                        source_url="",
                    ),
                    match_confidence=0.6,
                )
            )
        return candidates

    def download_for_game(
        self,
        title_id: str,
        output_dir: Path,
        build_id: str | None = None,
        emulator_id: str | None = None,
    ) -> int:
        """Executa o binário para baixar mods de um Title ID específico."""
        if not self._check_available():
            return 0
        cmd = [self._binary, "download", title_id, "--output", str(output_dir)]
        if build_id:
            cmd.extend(["--build-id", build_id])
        if emulator_id:
            cmd.extend(["--emulator", emulator_id])
        try:
            result = subprocess.run(  # noqa: S603
                cmd, capture_output=True, text=True, timeout=120
            )
            return 0 if result.returncode == 0 else 1
        except (FileNotFoundError, subprocess.TimeoutExpired):
            self._available = False
            return 1
