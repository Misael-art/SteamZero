# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Prova de isolamento em tempo de importação (antes da coleta).

Executado por ``test_collection_time_isolation_via_real_conftest`` via
subprocesso com ``tests/conftest.py`` real — o módulo verifica, no TOPO DO
MÓDULO, que HOME e ``paths.state_home()`` já estão isolados pelo bloco de
módulo do conftest antes de qualquer fixture executar.

O teste pai NÃO pré-define XDG_STATE_HOME ou STEAMZERO_TEST_XDG_ROOT.
O conftest cria o sandbox no carregamento do seu módulo (antes da coleta).

Uso (pelo teste, não manual)::

    HOME=<sentinel> STEAMZERO_TEST_ATTEST_PATH=<tmp/attest.json> \\
        python -m pytest tests/fixtures/import_time_xdg_probe.py \\
        --rootdir <project> -q --tb=short
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from steamzero.core import paths

# --- Isolamento verificado no carregamento do módulo (antes da coleta) ---

_ROOT_ENV = "STEAMZERO_TEST_XDG_ROOT"
_root_val = os.environ.get(_ROOT_ENV)

_ATTEST_ENV = "STEAMZERO_TEST_ATTEST_PATH"
_attest_path = os.environ.get(_ATTEST_ENV)

_errors: list[str] = []
_markers_ok = False

if _root_val is None:
    _errors.append(f"{_ROOT_ENV} não definido — conftest não isolou o ambiente")
else:
    root = Path(_root_val).resolve()

    expected_home = (root / "home").resolve()
    actual_home = Path.home().resolve()
    if actual_home != expected_home:
        _errors.append(f"HOME isolado incorreto: esperado {expected_home}, obtido {actual_home}")

    expected_state = (root / "state" / "steamzero").resolve()
    actual_state = paths.state_home().resolve()
    if actual_state != expected_state:
        _errors.append(
            f"state_home isolado incorreto: esperado {expected_state}, obtido {actual_state}"
        )

    if not _errors:
        actual_state.mkdir(parents=True, exist_ok=True)
        m1 = actual_state / ".probe-state-home-marker"
        m1.write_text("via-state-home", encoding="utf-8")

        home_state = actual_home / ".local" / "state" / "steamzero"
        home_state.mkdir(parents=True, exist_ok=True)
        m2 = home_state / ".probe-home-fallback-marker"
        m2.write_text("via-home-fallback", encoding="utf-8")

        _markers_ok = m1.read_text(encoding="utf-8") == "via-state-home" and (
            m2.read_text(encoding="utf-8") == "via-home-fallback"
        )
        if not _markers_ok:
            _errors.append("marcadores não puderam ser lidos após escrita")

if _errors:
    msg = " | ".join(_errors)
    raise RuntimeError(f"Probe de isolamento falhou: {msg}")

if _attest_path:
    sentinel_var = "STEAMZERO_TEST_HOME_SENTINEL"
    sentinel = os.environ.get(sentinel_var, "")
    attest = {
        "isolamento": "confirmado",
        "marcadores": "confirmados" if _markers_ok else "falha",
        "root_diferente_do_sentinel": (
            str(Path(_root_val).resolve()) != str(Path(sentinel).resolve())
            if sentinel and _root_val
            else "N/A"
        ),
    }
    Path(_attest_path).write_text(
        json.dumps(attest, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def test_probe_passed() -> None:
    """Confirma que o módulo foi carregado com sucesso (teste sempre passa)."""
    pass
