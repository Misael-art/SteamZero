# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Protocolo de 8 passos para mutações no Deck (OPERATIONAL-TRUST-GATES).

Cada mutação em hardware de produção (ou na VM que o precede) segue estes
passos. São referência canônica para o driver e o provisionador: nenhum código
deve afirmar "certificado" sem que cada passo tenha sido observado.

O protocolo é uma lista de tuplas (id, descrição) para que relatórios de
evidência possam citar o passo em que cada checkpoint foi coletado.
"""

from __future__ import annotations

PROTOCOL_STEPS: tuple[tuple[str, str], ...] = (
    ("p1-vm-first", "Executar primeiro em VM descartável; logs do mesmo commit."),
    ("p2-snapshot", "Snapshot Btrfs nomeado; confirmar espaço, montagem e restore."),
    ("p3-recovery-console", "Console de recuperação independente: TTY + SSH testados."),
    ("p4-baseline-readonly", "Baseline read-only (systemd, mounts, bateria, TDP, owners)."),
    ("p5-one-cap-at-a-time", "Uma capacidade por vez: plano, confirmação, snapshot, rollback."),
    ("p6-exercise-failures", "Exercitar hotplug/suspend/queda do processo no apply."),
    ("p7-confirm-and-reboot", "Confirmar estado; reiniciar sessão; então o host."),
    ("p8-restore-snapshot", "Restaurar snapshot em ensaio controlado; anexar evidência."),
)
