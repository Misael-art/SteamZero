# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Support bundle anonimizado e revisável (SZ-OP-07, DATA-FLOW §bundle).

Fluxo: ``preview`` monta o bundle em memória e devolve o conteúdo integral mais um
``confirmToken`` derivado do digest; ``write`` remonta o bundle e só grava se o
token corresponder ao conteúdo atual — o que é salvo é exatamente o que foi revisto.
Nada é enviado automaticamente (N7). Paths do usuário são anonimizados e nenhum
conteúdo de save, key ou token é coletado.
"""

from __future__ import annotations

import getpass
import hashlib
import json
import platform
from pathlib import Path
from typing import Any

from steamzero import CONTRACT_VERSION, __version__
from steamzero.core import fs as corefs
from steamzero.core import paths
from steamzero.core.errors import SteamZeroError
from steamzero.diagnostics.doctor import run_doctor

BUNDLE_SCHEMA = "support-bundle-v1"


def _replacements() -> list[tuple[str, str]]:
    pairs = [(str(paths.state_home()), "$STATE"), (str(paths._home()), "$HOME")]
    try:
        user = getpass.getuser()
    except Exception:  # sem usuário resolvível não há o que mascarar
        user = ""
    if len(user) >= 3:
        pairs.append((user, "$USER"))
    # Mais longo primeiro: $STATE vive dentro de $HOME.
    return sorted(((k, v) for k, v in pairs if k and k != "/"), key=lambda p: -len(p[0]))


def anonymize(value: Any, replacements: list[tuple[str, str]] | None = None) -> Any:
    """Substitui recursivamente paths/nomes do usuário em strings."""
    reps = _replacements() if replacements is None else replacements
    if isinstance(value, str):
        for needle, token in reps:
            value = value.replace(needle, token)
        return value
    if isinstance(value, dict):
        return {k: anonymize(v, reps) for k, v in value.items()}
    if isinstance(value, list):
        return [anonymize(v, reps) for v in value]
    return value


def _digest(content: dict[str, Any]) -> str:
    canonical = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_bundle() -> dict[str, Any]:
    """Coleta read-only: versões, plataforma e doctor. Sem timestamps (digest estável)."""
    doctor_data, checks = run_doctor()
    content = {
        "schema": BUNDLE_SCHEMA,
        "steamzero": {"version": __version__, "contract": CONTRACT_VERSION},
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "doctor": {"data": doctor_data, "checks": checks},
    }
    anonymized: dict[str, Any] = anonymize(content)
    return anonymized


def preview() -> dict[str, Any]:
    content = build_bundle()
    digest = _digest(content)
    return {"bundle": content, "sha256": digest, "confirmToken": digest[:16]}


def write(out: Path, confirm_token: str) -> dict[str, Any]:
    """Grava o bundle revisado; recusa se o conteúdo mudou desde o preview."""
    content = build_bundle()
    digest = _digest(content)
    if confirm_token != digest[:16]:
        raise SteamZeroError(
            "E-TX-CONFIRM-REQUIRED",
            detail="token não corresponde ao bundle atual; rode --preview e revise novamente",
        )
    corefs.write_atomic_text(out, json.dumps(content, ensure_ascii=False, indent=2, sort_keys=True))
    return {"written": str(out), "sha256": digest}
