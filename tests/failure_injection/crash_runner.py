# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Runner auxiliar: aplica um plano sob STEAMZERO_CRASH_AT (recebe SIGKILL real).

Invocado por test_fi04_sigkill_subprocess.py em subprocesso. Lê o plano/token do
ambiente e chama transaction.apply — o crash gate mata o processo via SIGKILL.
Não é coletado pelo pytest (nome sem prefixo test_).
"""

from __future__ import annotations

import os

from steamzero.core import transaction


def main() -> int:
    plan_id = os.environ["SZ_PLAN_ID"]
    token = os.environ["SZ_TOKEN"]
    transaction.apply(plan_id, token)  # STEAMZERO_CRASH_AT dispara os.kill(SIGKILL)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
