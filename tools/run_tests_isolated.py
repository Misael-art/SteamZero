# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Executa pytest sem permitir que a suíte toque o estado XDG do operador.

O isolamento precisa existir antes de ``pytest`` importar plugins e módulos de
teste. Por isso este runner cria os cinco homes XDG e só então abre um novo
processo Python. Uma fotografia exata dos metadados do state home original
reprova o gate se qualquer entrada real for criada, removida ou modificada.

A fotografia sozinha detecta *que* o state real mudou, não *quem* mudou. O
state home real tem outros donos legítimos — o daemon instalado
(``steamzero-core --systemd``) e comandos ``steamzero`` que o operador dispare
contra o host — e as escritas deles caem dentro da janela do pytest sem terem
relação com a suíte. Por isso o runner também atribui a mutação: varre os
processos steamzero que resolvem para o MESMO state home e separa os que já
existiam antes da janela (donos externos) dos que nasceram durante ela
(suspeitos de vazamento da suíte). Só o segundo caso reprova o gate.
"""

from __future__ import annotations

import hashlib
import os
import stat
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

_XDG_LAYOUT = {
    "XDG_STATE_HOME": "state",
    "XDG_DATA_HOME": "data",
    "XDG_CONFIG_HOME": "config",
    "XDG_CACHE_HOME": "cache",
    "XDG_RUNTIME_DIR": "runtime",
}
_HOME_SUBDIR = "home"
_TEST_ROOT_ENV = "STEAMZERO_TEST_XDG_ROOT"
_STATE_CHANGE_EXIT = 86
_PROC_ROOT = Path("/proc")
_WRITER_POLL_SECONDS = 2.0


@dataclass(frozen=True)
class StateEntry:
    """Metadados suficientes para detectar mutação sem ler conteúdo privado."""

    kind: str
    size: int
    mtime_ns: int
    ctime_ns: int
    link_target_hash: str = ""


@dataclass(frozen=True)
class StateSnapshot:
    root_exists: bool
    entries: tuple[tuple[str, StateEntry], ...]

    @property
    def file_count(self) -> int:
        return sum(entry.kind != "directory" for _, entry in self.entries)

    @property
    def directory_count(self) -> int:
        return sum(entry.kind == "directory" for _, entry in self.entries)

    @property
    def total_bytes(self) -> int:
        return sum(entry.size for _, entry in self.entries if entry.kind == "file")

    @property
    def max_mtime_ns(self) -> int:
        return max((entry.mtime_ns for _, entry in self.entries), default=0)

    def summary(self) -> str:
        return (
            f"exists={self.root_exists} files={self.file_count} "
            f"directories={self.directory_count} bytes={self.total_bytes} "
            f"max_mtime_ns={self.max_mtime_ns}"
        )


def resolve_real_state_home(environ: Mapping[str, str]) -> tuple[Path, str]:
    base_xdg = environ.get("XDG_STATE_HOME")
    if base_xdg is not None:
        return (Path(base_xdg) / "steamzero", "XDG_STATE_HOME")
    base_home = environ.get("HOME")
    if base_home is None:
        raise RuntimeError(
            "STEAMZERO: não é possível determinar o state home original — "
            "nem XDG_STATE_HOME nem HOME estão definidos no ambiente"
        )
    return (Path(base_home) / ".local" / "state" / "steamzero", "HOME-default")


def snapshot_state(root: Path) -> StateSnapshot:
    """Fotografa nomes e metadados, sem seguir links nem ler arquivos."""
    if not root.exists() and not root.is_symlink():
        return StateSnapshot(False, ())

    entries: list[tuple[str, StateEntry]] = []
    pending = [root]
    while pending:
        parent = pending.pop()
        try:
            children = sorted(parent.iterdir(), key=lambda item: item.name)
        except (FileNotFoundError, NotADirectoryError):
            continue
        for child in children:
            metadata = child.stat(follow_symlinks=False)
            mode = metadata.st_mode
            relative = child.relative_to(root).as_posix()
            if stat.S_ISDIR(mode):
                kind = "directory"
                pending.append(child)
            elif stat.S_ISREG(mode):
                kind = "file"
            elif stat.S_ISLNK(mode):
                kind = "symlink"
            else:
                kind = "other"
            target_hash = ""
            if kind == "symlink":
                target_hash = hashlib.sha256(os.readlink(child).encode("utf-8")).hexdigest()
            entries.append(
                (
                    relative,
                    StateEntry(
                        kind=kind,
                        size=metadata.st_size,
                        mtime_ns=metadata.st_mtime_ns,
                        ctime_ns=metadata.st_ctime_ns,
                        link_target_hash=target_hash,
                    ),
                )
            )
    return StateSnapshot(True, tuple(sorted(entries)))


@dataclass(frozen=True)
class ForeignWriter:
    """Processo steamzero, fora do isolamento, que resolve para o state real."""

    pid: int
    cmdline: str
    #: Segundos desde o boot em que o processo nasceu (mesma base de CLOCK_BOOTTIME).
    start_boottime: float
    #: ``True`` quando já existia antes da janela do pytest — dono externo, não a suíte.
    predates_window: bool

    def describe(self) -> str:
        origin = "anterior à janela" if self.predates_window else "NASCEU durante a janela"
        return f"pid={self.pid} ({origin}) cmd={self.cmdline}"


def _boottime_now() -> float:
    clock = getattr(time, "CLOCK_BOOTTIME", None)
    if clock is None:  # pragma: no cover - plataformas sem CLOCK_BOOTTIME
        return time.monotonic()
    return time.clock_gettime(clock)


def _read_proc_text(pid: int, name: str) -> str | None:
    try:
        return (_PROC_ROOT / str(pid) / name).read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return None


def _proc_environ(pid: int) -> dict[str, str] | None:
    raw = _read_proc_text(pid, "environ")
    if raw is None:
        return None
    environ: dict[str, str] = {}
    for chunk in raw.split("\0"):
        key, separator, value = chunk.partition("=")
        if separator:
            environ[key] = value
    return environ


def _proc_argv(pid: int) -> list[str]:
    raw = _read_proc_text(pid, "cmdline")
    if not raw:
        return []
    return [part for part in raw.split("\0") if part]


def _is_steamzero_process(argv: Sequence[str]) -> bool:
    """Só o executável (ou o script do interpretador) qualifica.

    Casar contra a linha inteira transforma qualquer shell, grep ou editor que
    apenas *mencione* "steamzero" num suposto dono do state home — e um dono
    inventado serviria de álibi para uma escrita real da suíte.
    """
    return any("steamzero" in part for part in argv[:2])


def _proc_start_boottime(pid: int) -> float | None:
    """Campo 22 de ``/proc/<pid>/stat``: nascimento em ticks desde o boot."""
    raw = _read_proc_text(pid, "stat")
    if raw is None:
        return None
    # O comm (campo 2) pode conter espaços e parênteses; corte após o último ')'.
    _, _, tail = raw.rpartition(")")
    fields = tail.split()
    if len(fields) < 20:
        return None
    try:
        ticks = int(fields[19])
    except ValueError:
        return None
    hertz = os.sysconf("SC_CLK_TCK")
    if hertz <= 0:  # pragma: no cover - sysconf degenerado
        return None
    return ticks / hertz


def scan_foreign_writers(
    real_state_home: Path, *, window_start_boottime: float
) -> dict[int, ForeignWriter]:
    """Processos steamzero, fora do isolamento, cujo state home é ``real_state_home``.

    Best-effort e read-only: qualquer processo ilegível é ignorado. Processos com
    ``STEAMZERO_TEST_XDG_ROOT`` no ambiente pertencem à suíte isolada e nunca
    escrevem no state real, portanto ficam de fora.
    """
    if not _PROC_ROOT.is_dir():  # pragma: no cover - plataformas sem /proc
        return {}

    target = str(real_state_home)
    own_pid = os.getpid()
    writers: dict[int, ForeignWriter] = {}
    try:
        candidates = list(_PROC_ROOT.iterdir())
    except OSError:  # pragma: no cover - /proc indisponível
        return {}

    for entry in candidates:
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid == own_pid:
            continue
        argv = _proc_argv(pid)
        if not _is_steamzero_process(argv):
            continue
        cmdline = " ".join(argv)
        environ = _proc_environ(pid)
        if environ is None or _TEST_ROOT_ENV in environ:
            continue
        try:
            resolved, _ = resolve_real_state_home(environ)
        except RuntimeError:
            continue
        if str(resolved) != target:
            continue
        start = _proc_start_boottime(pid)
        writers[pid] = ForeignWriter(
            pid=pid,
            cmdline=cmdline,
            start_boottime=-1.0 if start is None else start,
            # Sem leitura de nascimento, presume dono externo: acusar a suíte
            # sem prova é pior que deixar o operador conferir o processo nomeado.
            predates_window=True if start is None else start <= window_start_boottime,
        )
    return writers


class _WriterWatcher:
    """Amostra os donos externos durante a janela, para pegar processos curtos."""

    def __init__(self, real_state_home: Path, *, window_start_boottime: float) -> None:
        self._root = real_state_home
        self._window_start = window_start_boottime
        self._seen: dict[int, ForeignWriter] = {}
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="state-writer-watch", daemon=True)

    def sample(self) -> None:
        """Amostra agora. A primeira observação de um pid é a que vale."""
        try:
            found = scan_foreign_writers(self._root, window_start_boottime=self._window_start)
        except Exception:  # pragma: no cover - diagnóstico nunca derruba o gate
            return
        for pid, writer in found.items():
            self._seen.setdefault(pid, writer)

    def _loop(self) -> None:
        while not self._stop.wait(_WRITER_POLL_SECONDS):
            self.sample()

    def __enter__(self) -> _WriterWatcher:
        self.sample()
        self._thread.start()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self._stop.set()
        self._thread.join(timeout=5.0)

    @property
    def writers(self) -> dict[int, ForeignWriter]:
        return dict(self._seen)


def isolated_environment(root: Path, environ: Mapping[str, str]) -> dict[str, str]:
    child_env = dict(environ)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    home_dir = root / _HOME_SUBDIR
    home_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    home_dir.chmod(0o700)
    child_env["HOME"] = str(home_dir)
    for variable, directory in _XDG_LAYOUT.items():
        target = root / directory
        target.mkdir(mode=0o700, parents=True, exist_ok=True)
        target.chmod(0o700)
        child_env[variable] = str(target)
    child_env[_TEST_ROOT_ENV] = str(root)
    return child_env


def changed_entries(
    before: StateSnapshot, after: StateSnapshot
) -> tuple[list[str], list[str], list[str]]:
    before_entries = dict(before.entries)
    after_entries = dict(after.entries)
    created = sorted(after_entries.keys() - before_entries.keys())
    removed = sorted(before_entries.keys() - after_entries.keys())
    changed = sorted(
        name
        for name in before_entries.keys() & after_entries.keys()
        if before_entries[name] != after_entries[name]
    )
    return created, removed, changed


def _print_delta(before: StateSnapshot, after: StateSnapshot) -> None:
    created, removed, changed = changed_entries(before, after)
    print(f"before: {before.summary()}", file=sys.stderr)
    print(f"after:  {after.summary()}", file=sys.stderr)
    for label, names in (("created", created), ("removed", removed), ("changed", changed)):
        if names:
            sample = ", ".join(names[:20])
            suffix = f" (+{len(names) - 20})" if len(names) > 20 else ""
            print(f"{label}: {sample}{suffix}", file=sys.stderr)


def _report_external_writer(
    before: StateSnapshot,
    after: StateSnapshot,
    writers: Sequence[ForeignWriter],
    state_home: Path,
) -> None:
    print(
        "W-TEST-REAL-STATE-EXTERNAL-WRITER: o state home real mudou durante a janela "
        "do pytest, mas a suíte NÃO é a autora",
        file=sys.stderr,
    )
    print(f"state home: {state_home}", file=sys.stderr)
    _print_delta(before, after)
    print("donos externos ativos (já existiam antes da janela):", file=sys.stderr)
    for writer in writers:
        print(f"  - {writer.describe()}", file=sys.stderr)
    print(
        "Esses processos são donos legítimos do state home real e escrevem por conta\n"
        "própria (ex.: o reconciliador do daemon registra session.environment.changed\n"
        "a cada mudança de rede/energia). O gate não reprova por isso.\n"
        "Atenção: enquanto um dono externo está ativo, a atribuição fica degradada —\n"
        "uma escrita da própria suíte ficaria encoberta. Para rigor total, rode o gate\n"
        "com o daemon parado.",
        file=sys.stderr,
    )


def _report_state_change(
    before: StateSnapshot,
    after: StateSnapshot,
    suspects: Sequence[ForeignWriter] = (),
    state_home: Path | None = None,
) -> None:
    print(
        "E-TEST-REAL-STATE-MUTATED: pytest alterou o state home original",
        file=sys.stderr,
    )
    if state_home is not None:
        print(f"state home: {state_home}", file=sys.stderr)
    _print_delta(before, after)
    if suspects:
        print(
            "processos steamzero NASCIDOS durante a janela — prováveis autores "
            "(vazamento da suíte):",
            file=sys.stderr,
        )
        for writer in suspects:
            print(f"  - {writer.describe()}", file=sys.stderr)
        print(
            "Um teste deixou escapar um comando real, ou vazou um processo destacado que\n"
            "sobreviveu ao teste que o criou. Injete o runner falso, ou espere/mate o\n"
            "processo antes do teste terminar.",
            file=sys.stderr,
        )
    else:
        print(
            "Nenhum processo steamzero externo foi observado durante a janela.\n"
            "Causas a investigar, nesta ordem:\n"
            "  1. FALSO POSITIVO DO OPERADOR: qualquer comando `steamzero` executado\n"
            "     contra o host enquanto a suíte roda escreve nesse mesmo state home e\n"
            "     dispara este guard. Se você rodou um, rode o gate de novo sem tocar no\n"
            "     host. Comandos curtos podem terminar entre duas amostragens e não\n"
            "     aparecer nomeados acima.\n"
            "  2. Um teste deixou escapar um comando real (ex.: `systemctl --user`, cuja\n"
            "     unit sobe com o ambiente da sessão, não com o do teste).\n"
            "  3. Um processo destacado da suíte escreveu depois que o isolamento já\n"
            "     tinha sido desmontado.",
            file=sys.stderr,
        )


_INTERRUPT_EXIT = 130


def run_pytest(args: Sequence[str], *, environ: Mapping[str, str] | None = None) -> int:
    original_env = dict(os.environ if environ is None else environ)
    real_state_home, source = resolve_real_state_home(original_env)
    before = snapshot_state(real_state_home)
    print(f"real-state before: {before.summary()} source={source}")

    interrupted = False
    pytest_returncode = 0
    attributed_to_suite = False
    window_start = _boottime_now()
    with tempfile.TemporaryDirectory(prefix="steamzero-tests-") as temporary:
        isolated_root = Path(temporary)
        child_env = isolated_environment(isolated_root, original_env)
        with _WriterWatcher(real_state_home, window_start_boottime=window_start) as watcher:
            try:
                completed = subprocess.run(
                    [sys.executable, "-m", "pytest", *args],
                    env=child_env,
                    check=False,
                )
                pytest_returncode = completed.returncode
            except KeyboardInterrupt:
                interrupted = True
            finally:
                after = snapshot_state(real_state_home)
                print(f"real-state after:  {after.summary()} source={source}")
                # Fecha a janela com uma amostra própria: o __exit__ do watcher só
                # roda depois deste finally, tarde demais para a decisão.
                watcher.sample()
                if before != after:
                    observed = sorted(watcher.writers.values(), key=lambda item: item.pid)
                    external = [item for item in observed if item.predates_window]
                    suspects = [item for item in observed if not item.predates_window]
                    # Um dono externo já ativo antes da janela explica a mutação sem
                    # envolver a suíte; um processo nascido dentro dela, não.
                    if external and not suspects:
                        _report_external_writer(before, after, external, real_state_home)
                    else:
                        attributed_to_suite = True
                        _report_state_change(before, after, suspects, real_state_home)

    if attributed_to_suite:
        return _STATE_CHANGE_EXIT
    if interrupted:
        return _INTERRUPT_EXIT
    return pytest_returncode


def main(argv: Sequence[str] | None = None) -> int:
    return run_pytest(sys.argv[1:] if argv is None else argv)


if __name__ == "__main__":
    raise SystemExit(main())
