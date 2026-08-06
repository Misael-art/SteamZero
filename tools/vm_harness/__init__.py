# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Harness de VM descartável para certificar o M10 (DEBT-A7).

A suíte de testes prova a lógica do driver com fakes; a VM real (provisionamento
via virt-install/cloud-init) roda fora da suíte, sob autorização explícita do
operador, seguindo o protocolo de 8 passos de ``docs/09-operations/OPERATIONAL-
TRUST-GATES.md``.
"""
