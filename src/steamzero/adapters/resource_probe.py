# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Probe read-only de recursos por classe de processo (GAP-G30).

Lê exclusivamente procfs: ``/proc/<pid>/stat`` (estado, PPID, start-time,
comm), ``/proc/<pid>/status`` (VmRSS/VmSwap), ``/proc/<pid>/smaps_rollup``
(PSS quando suportado) e o marcador ``STEAMZERO_CLASS`` do environ. Nunca lê
command line (``/proc/<pid>/cmdline``) nem argv, e nunca persiste identidade
ou caminhos: cada snapshot reenumerar /proc e descarta a árvore ao terminar.

Todas as dependências de leitura são injetáveis (``read_text``, ``list_dir``,
``getpid`` e os provedores de identidade), então os testes exercitam os
caminhos de erro e reutilização de PID com árvores sintéticas, sem tocar em
processos reais.

Degrada, nunca levanta: procfs incompleto, permissão negada ou falha de
provedor produzem snapshot parcial com causa explícita (``complete``/``reason``).
"""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from steamzero.domain.resources import ProcessObservation, summarize

#: Valor do marcador STEAMZERO_CLASS no environ dos processos que o
#: SteamZero inicia (UI, daemon e emuladores). Filhos de emulador herdam o
#: marcador, mas a classificação como ``emulator-child`` usa a cadeia de PPID,
#: nunca o marcador sozinho.
_MARKER = "STEAMZERO_CLASS"

ReadText = Callable[[str], str | None]
ListDir = Callable[[str], list[str]]


def _read_text(path: str) -> str | None:
    """Lê arquivo texto curto; ``None`` = permission denied; ``""`` = ausente."""
    try:
        target = Path(path)
        if target.is_symlink() or not target.is_file() or target.stat().st_size > (1 << 20):
            return ""
        return target.read_text(encoding="utf-8", errors="replace").strip()
    except PermissionError:
        return None
    except OSError:
        return ""


def _read_bytes(path: str) -> bytes:
    try:
        target = Path(path)
        if target.is_symlink() or not target.is_file() or target.stat().st_size > (1 << 20):
            return b""
        return target.read_bytes()
    except PermissionError:
        return b""
    except OSError:
        return b""


def _list_dir(path: str) -> list[str]:
    try:
        return sorted(entry.name for entry in Path(path).iterdir())
    except OSError:
        return []


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def parse_stat(text: str) -> dict[str, Any] | None:
    """Parse de ``/proc/<pid>/stat``: pid, comm, state, ppid e starttime.

    O comm vem entre parênteses e pode conter espaços; o kernel o limita a 15
    caracteres e proíbe barras, então é seguro publicá-lo. Os campos restantes
    são posicionais: state (campo 3), ppid (4) e starttime (22).
    """
    open_at = text.find("(")
    close_at = text.rfind(")")
    if open_at <= 0 or close_at <= open_at:
        return None
    try:
        pid = int(text[:open_at].strip())
    except ValueError:
        return None
    comm = text[open_at + 1 : close_at]
    # O kernel permite '/' em comm via prctl; um caminho nunca deve vazar.
    # Barras viram '_' e o valor é limitado a 64 chars (defensivo; o kernel
    # limita a 15).
    comm = comm.replace("/", "_").strip()
    rest = text[close_at + 1 :].split()
    if len(rest) < 20:
        return None
    try:
        ppid = int(rest[1])
        starttime = int(rest[19])
    except ValueError:
        return None
    return {
        "pid": pid,
        "comm": comm[:64] or None,
        "state": rest[0],
        "ppid": ppid,
        "starttime": starttime,
    }


def parse_smaps_pss(text: str) -> int | None:
    """PSS total (kB) do ``smaps_rollup``; None se a linha não existir."""
    for line in text.splitlines():
        if line.startswith("Pss:"):
            parts = line.split()
            if len(parts) >= 2:
                try:
                    return int(parts[1]) * 1024
                except ValueError:
                    return None
    return None


def parse_status_memory(text: str) -> tuple[int | None, int | None]:
    """(VmRSS, VmSwap) em bytes a partir de ``/proc/<pid>/status``."""
    rss: int | None = None
    swap: int | None = None
    for line in text.splitlines():
        if line.startswith("VmRSS:"):
            parts = line.split()
            if len(parts) >= 2:
                try:
                    rss = int(parts[1]) * 1024
                except ValueError:
                    rss = None
        elif line.startswith("VmSwap:"):
            parts = line.split()
            if len(parts) >= 2:
                try:
                    swap = int(parts[1]) * 1024
                except ValueError:
                    swap = None
    return rss, swap


def parse_environ_class(content: bytes) -> str | None:
    """Valor de ``STEAMZERO_CLASS`` no environ; None se ausente/ilegível."""
    prefix = f"{_MARKER}=".encode()
    for entry in content.split(b"\0"):
        if entry.startswith(prefix):
            value = entry[len(prefix) :].decode("ascii", errors="replace").strip()
            return value or None
    return None


def lifecycle_from_state(state: str) -> str:
    if state in {"R", "S", "D"}:
        return "running"
    if state == "Z":
        return "zombie"
    if state in {"T", "t", "X", "x"}:
        return "stopped"
    return "unknown"


class ResourceProbe:
    """Sonda read-only da atribuição de consumo.

    Parâmetros de identidade (todos opcionais e injetáveis):

    - ``daemon_pid`` — PID declarado pelo daemon via ``system.hello``;
    - ``emulator_processes`` — ``(pid, start_ticks)`` das sessões de jogo
      ativas (start_ticks pode ser ``None`` quando a sessão nasceu antes da
      coluna); ``None`` aqui significa "sem rastreamento";
    - ``media_job_processes`` — ``(pid, start_ticks)`` de jobs de mídia
      isolados (hoje vazio: jobs rodam na thread do daemon).
    """

    def __init__(
        self,
        *,
        proc_root: str = "/proc",
        read_text: ReadText = _read_text,
        read_bytes: Callable[[str], bytes] = _read_bytes,
        list_dir: ListDir = _list_dir,
        getpid: Callable[[], int] = os.getpid,
        own_class: str | None = None,
        daemon_pid: Callable[[], int | None] | None = None,
        emulator_processes: Callable[[], list[tuple[int, int | None]]] | None = None,
        media_job_processes: Callable[[], list[tuple[int, int | None]]] | None = None,
        now: Callable[[], str] = _now_iso,
    ) -> None:
        self._proc_root = proc_root
        self._read_text = read_text
        self._read_bytes = read_bytes
        self._list_dir = list_dir
        self._getpid = getpid
        self._own_class = own_class
        self._daemon_pid = daemon_pid or (lambda: None)
        self._emulator_processes = emulator_processes or (lambda: [])
        self._media_job_processes = media_job_processes or (lambda: [])
        self._now = now

    def snapshot(self) -> dict[str, Any]:
        try:
            return self._snapshot()
        except Exception:
            return {
                "schemaVersion": 1,
                "observedAt": self._now(),
                "readOnly": True,
                "complete": False,
                "reason": "probe-failed",
                "classes": [],
                "totals": _empty_totals(),
                "processes": [],
            }

    def _snapshot(self) -> dict[str, Any]:
        pids = self._enumerate_pids()
        observations: list[ProcessObservation] = []
        complete = True
        reason: str | None = None
        if pids is None:
            return {
                "schemaVersion": 1,
                "observedAt": self._now(),
                "readOnly": True,
                "complete": False,
                "reason": "proc-unavailable",
                "classes": [],
                "totals": _empty_totals(),
                "processes": [],
            }
        parsed: dict[int, dict[str, Any]] = {}
        for pid in pids:
            stat = self._read_stat(pid)
            if stat is None:
                observations.append(
                    ProcessObservation(
                        pid=pid,
                        process_class="unknown",
                        evidence="unattributable",
                        lifecycle="unknown",
                        metric="unavailable",
                        pss_bytes=None,
                        rss_bytes=None,
                        swap_bytes=None,
                        comm=None,
                        start_ticks=None,
                        read_failure="proc-incomplete",
                    )
                )
                complete = False
                reason = "proc-incomplete"
                continue
            parsed[pid] = stat
        classified = self._classify(parsed)
        for pid in pids:
            stat = parsed.get(pid)
            if stat is None:
                continue
            process_class, evidence = classified.get(pid, ("unknown", "unattributable"))
            lifecycle = lifecycle_from_state(str(stat["state"]))
            if lifecycle == "zombie":
                observations.append(
                    ProcessObservation(
                        pid=pid,
                        process_class=process_class,
                        evidence=evidence,
                        lifecycle=lifecycle,
                        metric="pss",
                        pss_bytes=0,
                        rss_bytes=0,
                        swap_bytes=0,
                        comm=stat.get("comm"),
                        start_ticks=stat.get("starttime"),
                    )
                )
                continue
            memory = self._read_memory(pid, stat.get("starttime"))
            observations.append(
                ProcessObservation(
                    pid=pid,
                    process_class=process_class,
                    evidence=evidence,
                    lifecycle=lifecycle,
                    metric=memory["metric"],
                    pss_bytes=memory["pss"],
                    rss_bytes=memory["rss"],
                    swap_bytes=memory["swap"],
                    comm=stat.get("comm"),
                    start_ticks=stat.get("starttime"),
                    read_failure=memory["failure"],
                )
            )
            if memory["failure"] == "proc-incomplete":
                complete = False
                reason = "proc-incomplete"
        summary = summarize(
            observations,
            complete=complete,
            reason=reason,
        )
        summary["observedAt"] = self._now()
        return summary

    def _enumerate_pids(self) -> list[int] | None:
        try:
            entries = self._list_dir(self._proc_root)
        except OSError:
            return None
        pids: list[int] = []
        for entry in entries:
            if not entry.isdigit():
                continue
            try:
                pids.append(int(entry))
            except ValueError:
                continue
        return sorted(pids) or ([] if entries else None)

    def _read_stat(self, pid: int) -> dict[str, Any] | None:
        return parse_stat(self._read_text(f"{self._proc_root}/{pid}/stat") or "")

    def _read_memory(self, pid: int, start_ticks: int | None) -> dict[str, Any]:
        base = f"{self._proc_root}/{pid}"
        rollup = self._read_text(f"{base}/smaps_rollup")
        if rollup is None:
            return _unknown_memory("permission-denied")
        if not rollup:
            # smaps_rollup ausente (kernel antigo ou procfs restrito): fallback
            # explícito e declarado para RSS, com swap ainda do status.
            status = self._read_text(f"{base}/status")
            if status is None:
                return _unknown_memory("permission-denied")
            if not status:
                return _unknown_memory("proc-incomplete")
            rss, swap = parse_status_memory(status)
            if rss is None and swap is None:
                return _unknown_memory("proc-incomplete")
            return {
                "metric": "rss-fallback",
                "pss": None,
                "rss": rss,
                "swap": swap,
                "failure": None,
            }
        pss = parse_smaps_pss(rollup)
        if pss is None:
            return _unknown_memory("proc-incomplete")
        status = self._read_text(f"{base}/status")
        if status is None:
            return {
                "metric": "pss",
                "pss": pss,
                "rss": None,
                "swap": None,
                "failure": "permission-denied",
            }
        if not status:
            return {
                "metric": "pss",
                "pss": pss,
                "rss": None,
                "swap": None,
                "failure": "proc-incomplete",
            }
        _, swap = parse_status_memory(status)
        return {"metric": "pss", "pss": pss, "rss": None, "swap": swap, "failure": None}

    def _classify(self, parsed: dict[int, dict[str, Any]]) -> dict[int, tuple[str, str]]:
        result: dict[int, tuple[str, str]] = {}
        own_pid = self._getpid()
        daemon_pid = _safe_provider_pid(self._daemon_pid)
        emulators = _safe_identity_provider(self._emulator_processes)
        media_jobs = _safe_identity_provider(self._media_job_processes)
        expected_pids = {pid for pid, _ in [*emulators, *media_jobs]}

        # 1) Identidade própria, daemon e processos rastreados (sessão de jogo
        #    ou job de mídia): o start-time confere OU o marcador confere.
        for pid, stat in parsed.items():
            if pid == own_pid:
                result[pid] = (self._own_class or "unknown", "own-process")
                continue
            if daemon_pid is not None and pid == daemon_pid:
                result[pid] = ("daemon", "daemon-pid")
                continue
            for process_class, identity in (
                ("media-job", media_jobs),
                ("emulator", emulators),
            ):
                if _matches_identity(pid, stat, identity):
                    result[pid] = (process_class, "identity-provider")
                    break
        # 2) Filhos de emulador: cadeia de PPID até um emulador comprovado.
        for pid, stat in parsed.items():
            if pid in result:
                continue
            if _descends_from_emulator(pid, stat, parsed, result):
                result[pid] = ("emulator-child", "child-of-emulator")
        # 3) Marcador STEAMZERO_CLASS (environ) para os demais, inclusive para
        #    PIDs rastreados cujo start-time não conferiu: se o marcador está
        #    presente, o PID foi reutilizado por um processo novo do SteamZero.
        for pid, _stat in parsed.items():
            if pid in result:
                continue
            marker = self._read_marker(pid)
            if marker in {"ui", "daemon", "media-job", "emulator"}:
                result[pid] = (marker, "environ-marker")
        # 4) Restante: PID rastreado com identidade não comprovada é
        #    explicitamente "identity-mismatch" (nunca herda identidade antiga);
        #    o demais são não atribuíveis.
        for pid in parsed:
            if pid in result:
                continue
            if pid in expected_pids:
                result[pid] = ("unknown", "identity-mismatch")
            else:
                result[pid] = ("unknown", "unattributable")
        return result

    def _read_marker(self, pid: int) -> str | None:
        content = self._read_bytes(f"{self._proc_root}/{pid}/environ")
        if not content:
            return None
        return parse_environ_class(content)


def _descends_from_emulator(
    pid: int,
    stat: dict[str, Any],
    parsed: dict[int, dict[str, Any]],
    classified: dict[int, tuple[str, str]],
) -> bool:
    """Caminha a cadeia de PPID (máx. 16, com guarda de ciclo) até um emulador."""
    seen: set[int] = set()
    current = int(stat["ppid"])
    for _ in range(16):
        if current in seen or current <= 1 or current == pid:
            return False
        seen.add(current)
        if current in classified and classified[current][0] == "emulator":
            return True
        ancestor = parsed.get(current)
        if ancestor is None:
            return False
        current = int(ancestor["ppid"])
    return False


def _matches_identity(
    pid: int,
    stat: dict[str, Any],
    identity: list[tuple[int, int | None]],
) -> bool:
    observed_ticks = stat.get("starttime")
    for known_pid, known_ticks in identity:
        if known_pid != pid:
            continue
        if known_ticks is not None and known_ticks == observed_ticks:
            return True
        if known_ticks is not None:
            # PID reutilizado: o start-time não confere. Sem marcador, o
            # processo não herda a identidade antiga.
            continue
        return True
    return False


def _safe_provider_pid(provider: Callable[[], int | None]) -> int | None:
    try:
        pid = provider()
    except Exception:
        return None
    return pid if isinstance(pid, int) and pid > 1 else None


def _safe_identity_provider(
    provider: Callable[[], object],
) -> list[tuple[int, int | None]]:
    """Normaliza provedores de identidade tolerando dados inválidos em runtime."""
    try:
        entries = provider()
    except Exception:
        return []
    if not isinstance(entries, list):
        return []
    result: list[tuple[int, int | None]] = []
    for entry in entries:
        if not isinstance(entry, (tuple, list)) or len(entry) != 2:
            continue
        pid, ticks = entry
        if not isinstance(pid, int) or pid <= 1:
            continue
        if ticks is not None and not isinstance(ticks, int):
            ticks = None
        result.append((pid, ticks))
    return result


def _unknown_memory(failure: str) -> dict[str, Any]:
    return {
        "metric": "unavailable",
        "pss": None,
        "rss": None,
        "swap": None,
        "failure": failure,
    }


def _empty_totals() -> dict[str, Any]:
    return {
        "attributed": {
            "displayName": "Consumo atribuído",
            "processCount": 0,
            "pssBytes": 0,
            "swapBytes": 0,
            "processesWithUnknownMemory": 0,
        },
        "unattributable": {
            "displayName": "Não atribuível",
            "processCount": 0,
            "pssBytes": 0,
            "swapBytes": 0,
            "processesWithUnknownMemory": 0,
        },
    }
