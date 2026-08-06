#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Provisiona uma VM descartável e certifica o M10 dentro dela (DEBT-A7).

ESTE SCRIPT NÃO RODA NA SUÍTE DE TESTES. Ele provisiona uma VM real via
``virt-install`` + cloud-init (Arch base, SDDM, flatpak), executa o driver
``driver.certify_m10`` dentro da VM por SSH contra o ``flatpak`` real, e grava o
relatório de evidência em ``docs/diagnostics/``.

Governança (AGENTS.md S1): rodar este script exige autorização explícita do
operador na thread em curso, porque provisiona uma VM no host do operador
(consome KVM/CPU/disco). O host de produção do operador nunca é mutado por este
script; a VM é descartável e removida ao final.

Protocolo de 8 passos (``docs/09-operations/OPERATIONAL-TRUST-GATES.md``):
  p1 VM primeiro (este script);
  p2 snapshot btrfs da VM antes de mutar;
  p3 console de recuperação (TTY/SSH da VM);
  p4 baseline read-only dentro da VM;
  p5 uma capacidade por vez (o driver já impõe um emulador por vez);
  p6 exercitar queda do processo no meio do apply (driver futuras);
  p7 confirmar estado;
  p8 restaurar snapshot da VM em ensaio controlado.

Uso (após autorização do operador):

    python tools/vm_harness/provision.py \\
        --source-commit <full-sha> \\
        --vm-name steamzero-m10 \\
        --disk-size-gb 40 \\
        --memory-mib 4096 \\
        --cpus 4

O ``--source-commit`` é obrigatório: a evidência só vale vinculada ao commit
exato em que a VM foi construída. O relatório é gravado em
``docs/diagnostics/<data>-m10-vm-evidence.md``.

Pré-requisitos no host do operador: KVM/libvirt prontos (WORKLOG Sessão 29
documenta o lab no Deck: QEMU 11.0.2, libvirt 12.5, virt-install 5.1.0, OVMF,
swtpm, ``/dev/kvm`` acessível). O script valida estes binários antes de iniciar.
"""

from __future__ import annotations

import argparse
import datetime as dt
import shutil
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))

#: Binários exigidos no host do operador para provisionar a VM.
REQUIRED_BINARIES: tuple[str, ...] = ("virt-install", "virsh", "cloud-localds", "qemu-img")


def _preflight() -> None:
    """Valida que o host tem o lab KVM/libvirt pronto antes de qualquer efeito."""
    missing = [name for name in REQUIRED_BINARIES if shutil.which(name) is None]
    if missing:
        raise SystemExit(
            "lab KVM/libvirt incompleto; binários ausentes: "
            + ", ".join(missing)
            + " (ver WORKLOG Sessão 29 para a instalação no Deck)"
        )


def _emit_plan(*, vm_name: str, disk_size_gb: int, memory_mib: int, cpus: int) -> str:
    """Descreve o plano de provisionamento SEM executar nada.

    O plano é impresso para o operador revisar antes de autorizar; a execução
    efetiva fica em ``_run_provision``, chamada só após confirmação.
    """
    return textwrap.dedent(f"""\
        Plano de provisionamento da VM descartável M10:

          nome:       {vm_name}
          disco:      {disk_size_gb} GB (qcow2 descartável)
          memória:    {memory_mib} MiB
          cpus:       {cpus}
          base:       Arch Linux + SDDM + flatpak (cloud-init)
          isolamento: VM removida ao final; host de produção intocado

        Protocolo de 8 passos será seguido (p1-p8). O driver certify_m10 roda
        dentro da VM por SSH contra o flatpak real. A evidência será gravada em
        docs/diagnostics/<data>-m10-vm-evidence.md vinculada ao --source-commit.
    """)


def _run_provision(*, vm_name: str, disk_size_gb: int, memory_mib: int, cpus: int) -> None:
    """Executa o provisionamento da VM.

    Place-holder intencional: a execução real de virt-install/cloud-init/SSH fica
    fora do escopo de código verde (AGENTS.md S4 — não construir artefatos fora
    de pedido). A implementação completa exige autorização do operador na thread
    em curso e é preenchida quando o operador autoriza a rodar a VM.
    """
    raise SystemExit(
        "provisionamento real requer autorização explícita do operador na thread "
        "em curso (AGENTS.md S1). O plano acima foi emitido para revisão; "
        "autorize nomeando este script para executar."
    )


def _write_evidence_stub(*, source_commit: str) -> Path:
    """Cria o esqueleto do relatório de evidência para o operador preencher.

    A evidência real só existe depois que a VM roda; este esqueleto documenta o
    formato esperado e o vínculo ao commit.
    """
    date = dt.date.today().isoformat()
    target = ROOT / "docs" / "diagnostics" / f"{date}-m10-vm-evidence.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        textwrap.dedent(f"""\
            # Evidência de certificação M10 (VM descartável) — ESQUELETO

            - **Commit de origem:** `{source_commit}`
            - **Data:** {date}
            - **Estado:** PENDENTE — a VM ainda não rodou sob autorização.

            Este esqueleto documenta o formato da evidência que fecha DEBT-A7.
            Ele é preenchido por ``driver.render_evidence_report`` depois que a VM
            roda os 3 ciclos (install->update->rollback->roll-forward) para
            RetroArch + PCSX2 + PPSSPP. Nada aqui substitui a execução real.
        """),
        encoding="utf-8",
    )
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source-commit", required=True, help="commit exato da fonte da VM")
    parser.add_argument("--vm-name", default="steamzero-m10")
    parser.add_argument("--disk-size-gb", type=int, default=40)
    parser.add_argument("--memory-mib", type=int, default=4096)
    parser.add_argument("--cpus", type=int, default=4)
    parser.add_argument("--plan", action="store_true", help="apenas emite o plano, não executa")
    args = parser.parse_args(argv)

    _preflight()
    print(
        _emit_plan(
            vm_name=args.vm_name,
            disk_size_gb=args.disk_size_gb,
            memory_mib=args.memory_mib,
            cpus=args.cpus,
        )
    )
    stub = _write_evidence_stub(source_commit=args.source_commit)
    print(f"esqueleto de evidência: {stub.relative_to(ROOT)}")

    if args.plan:
        return 0
    _run_provision(
        vm_name=args.vm_name,
        disk_size_gb=args.disk_size_gb,
        memory_mib=args.memory_mib,
        cpus=args.cpus,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
