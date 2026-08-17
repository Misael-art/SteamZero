#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Orquestra promoção e ativação de release sem duplicar os gates canônicos.

O comando é deliberadamente conservador:

* ``inspect`` nunca muta o host;
* ``prepare`` aceita somente um run ``push`` verde do commit exato;
* ``install`` e ``rollback`` chamam exclusivamente ``tools/install_host.py``;
* ``update`` mantém lock+journal e reverte automaticamente após ativação falha;
* cada mutação exige um token que contém o alvo;
* ``publish`` exige evidência de certificação separada e aprovada.

O script se localiza pelo próprio arquivo, portanto o agente pode chamá-lo de
qualquer diretório. Subprocessos que dependem do checkout sempre executam na
raiz correta do repositório.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import zipfile
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from email.parser import Parser
from pathlib import Path
from typing import IO

import install_host
from build_wheelhouse import validate as validate_wheelhouse
from steamzero.core.migrations import LATEST as DATA_SCHEMA_VERSION

ROOT = Path(__file__).resolve().parent.parent
HOST_ROOT = Path("/opt/steamzero")
HOST_MANAGER = Path("/usr/local/sbin/steamzero-host")
DEFAULT_REPOSITORY = "Misael-art/SteamZero"
DEFAULT_UPDATE_REF = "origin/main"
MIN_CACHE_FREE_BYTES = 2 * 1024 * 1024 * 1024
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
RELEASE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*-[0-9a-f]{12}$")
TAG_RE = re.compile(r"^v[A-Za-z0-9][A-Za-z0-9._+-]*$")
CHECKSUM_RE = re.compile(r"^(?P<digest>[0-9a-f]{64})  (?P<path>[^\r\n]+)$")
REQUIRED_CERTIFICATION_GATES = (
    "machineCycle",
    "physicalUi",
    "canonicalRomLaunch",
    "statePreserved",
)
TERMINAL_UPDATE_PHASES = frozenset(
    {
        "planned",
        "cancelled",
        "failed-before-activation",
        "committed",
        "failed-safe",
        "rollback-failed",
    }
)
SENSITIVE_EVENT_KEYS = frozenset(
    {"password", "token", "credential", "secret", "rom", "library", "path"}
)

CommandRunner = Callable[
    [Sequence[str], Path, int],
    subprocess.CompletedProcess[str],
]


class AutomationError(RuntimeError):
    """Falha pública e acionável da automação."""


class ConvergenceError(AutomationError):
    """Falha estruturada devolvida pelo convergidor estável do host."""

    def __init__(self, report: dict[str, object]) -> None:
        self.state = str(report.get("state") or "unknown")
        self.code = str(report.get("code") or "E-HOST-CONVERGENCE")
        self.detail = str(report.get("detail") or "convergência sem detalhe")[:400]
        super().__init__(f"{self.code}: {self.detail}")


@dataclass(frozen=True)
class Bundle:
    root: Path
    version: str
    commit: str
    release: str
    wheel: Path
    wheel_sha256: str
    requirements: Path
    wheelhouse: Path
    manifest: Path
    run_id: str | None
    source_ref: str

    def public(self) -> dict[str, object]:
        data = asdict(self)
        for key in ("root", "wheel", "requirements", "wheelhouse", "manifest"):
            data[key] = str(data[key])
        return data


@dataclass(frozen=True)
class UpdatePlan:
    current_release: str
    target_release: str
    source_commit: str
    rollback_release: str
    run_id: str | None
    wheel_sha256: str
    data_schema_version: int
    confirmation_token: str

    def public(self) -> dict[str, object]:
        return {
            "currentRelease": self.current_release,
            "targetRelease": self.target_release,
            "sourceCommit": self.source_commit,
            "ci": "green",
            "bundle": "verified",
            "rollbackRelease": self.rollback_release,
            "dataSchemaVersion": self.data_schema_version,
            "userData": "preserved",
            "boot": "unchanged",
            "deploymentHealthy": False,
            "physicalCertification": False,
            "confirmationToken": self.confirmation_token,
        }


@dataclass
class UpdateJournal:
    path: Path
    document: dict[str, object]

    @property
    def phase(self) -> str:
        return str(self.document.get("phase") or "")

    @property
    def terminal(self) -> bool:
        return self.phase in TERMINAL_UPDATE_PHASES

    def event(
        self,
        phase: str,
        *,
        current_release: str | None,
        data: dict[str, object] | None = None,
    ) -> None:
        events = self.document.setdefault("events", [])
        if not isinstance(events, list):
            raise AutomationError(f"journal transacional inválido: {self.path.name}")
        payload: dict[str, object] = {
            "sequence": len(events) + 1,
            "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "phase": phase,
            "currentRelease": current_release,
        }
        if data:
            payload["data"] = _sanitize_event_data(data)
        events.append(payload)
        self.document["phase"] = phase
        _atomic_json(self.path, self.document)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sanitize_event_data(data: dict[str, object]) -> dict[str, object]:
    """Mantém somente evidência operacional que não identifica dados do usuário."""
    clean: dict[str, object] = {}
    for key, value in data.items():
        lowered = key.lower()
        if any(sensitive in lowered for sensitive in SENSITIVE_EVENT_KEYS):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            if isinstance(value, str) and ("/home/" in value or "/run/user/" in value):
                clean[key] = "<redacted>"
            else:
                clean[key] = value
        elif isinstance(value, dict):
            clean[key] = _sanitize_event_data(value)
        elif isinstance(value, list):
            clean[key] = [
                item for item in value if isinstance(item, (str, int, float, bool)) or item is None
            ]
    return clean


def _atomic_json(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(document, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _cache_dir() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "steamzero" / "release-automation"


def _transaction_dir(state_dir: Path | None = None) -> Path:
    return (state_dir or _state_dir()).expanduser() / "transactions"


@contextmanager
def _update_lock(state_dir: Path | None = None) -> Iterator[IO[str]]:
    directory = _transaction_dir(state_dir)
    directory.mkdir(parents=True, exist_ok=True)
    lock_path = directory / ".update.lock"
    with lock_path.open("a+", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise AutomationError("outra atualização SteamZero já está em andamento") from exc
        yield lock


def _start_update_journal(
    source_commit: str,
    *,
    source_ref: str = "refs/heads/main",
    current_release: str | None,
    state_dir: Path | None,
) -> UpdateJournal:
    directory = _transaction_dir(state_dir)
    directory.mkdir(parents=True, exist_ok=True)
    transaction_id = f"{source_commit[:12]}-{time.time_ns()}"
    path = directory / f"{transaction_id}.json"
    document: dict[str, object] = {
        "schemaVersion": 2,
        "transactionId": transaction_id,
        "targetRelease": None,
        "rollbackRelease": None,
        "sourceCommit": source_commit,
        "sourceRef": source_ref,
        "wheelSha256": None,
        "runId": None,
        "phase": "",
        "deploymentHealthy": False,
        "physicalCertification": False,
        "events": [],
    }
    journal = UpdateJournal(path=path, document=document)
    journal.event("discovered", current_release=current_release)
    return journal


def _bind_journal_bundle(
    journal: UpdateJournal,
    bundle: Bundle,
    *,
    current_release: str | None,
) -> None:
    if journal.document.get("sourceCommit") != bundle.commit:
        raise AutomationError("bundle diverge do commit descoberto no journal")
    journal.document.update(
        {
            "targetRelease": bundle.release,
            "wheelSha256": bundle.wheel_sha256,
            "runId": bundle.run_id,
        }
    )
    journal.event(
        "bundle-verified",
        current_release=current_release,
        data={"runId": bundle.run_id, "wheelSha256": bundle.wheel_sha256},
    )


def _bind_journal_preflight(journal: UpdateJournal, plan: UpdatePlan) -> None:
    _journal_matches(journal, plan, allow_missing_rollback=True)
    journal.document["rollbackRelease"] = plan.rollback_release
    journal.event(
        "preflight-passed",
        current_release=plan.current_release,
        data={"dataSchemaVersion": plan.data_schema_version},
    )


def _new_update_journal(
    plan: UpdatePlan,
    *,
    state_dir: Path | None,
) -> UpdateJournal:
    journal = _start_update_journal(
        plan.source_commit,
        current_release=plan.current_release,
        state_dir=state_dir,
    )
    journal.document.update(
        {
            "targetRelease": plan.target_release,
            "wheelSha256": plan.wheel_sha256,
            "runId": plan.run_id,
        }
    )
    journal.event(
        "bundle-verified",
        current_release=plan.current_release,
        data={"runId": plan.run_id, "wheelSha256": plan.wheel_sha256},
    )
    _bind_journal_preflight(journal, plan)
    return journal


def _load_unfinished_journal(state_dir: Path | None = None) -> UpdateJournal | None:
    directory = _transaction_dir(state_dir)
    if not directory.exists():
        return None
    unfinished: list[UpdateJournal] = []
    for path in sorted(directory.glob("*.json")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AutomationError(f"journal transacional ilegível: {path.name}") from exc
        if not isinstance(document, dict) or document.get("schemaVersion") != 2:
            raise AutomationError(f"journal transacional inválido: {path.name}")
        journal = UpdateJournal(path=path, document=document)
        if not journal.terminal:
            unfinished.append(journal)
    if len(unfinished) > 1:
        raise AutomationError("mais de uma transação incompleta exige recuperação manual")
    return unfinished[0] if unfinished else None


def _discovery_can_be_superseded(
    journal: UpdateJournal,
    *,
    next_commit: str,
    current_release: str | None,
    runner: CommandRunner,
) -> bool:
    """Confirma que um journal antigo nunca alcançou preparação ou ativação."""
    if journal.phase != "discovered" or journal.document.get("sourceCommit") == next_commit:
        return False
    if any(
        journal.document.get(key) is not None
        for key in ("targetRelease", "rollbackRelease", "wheelSha256", "runId")
    ):
        return False
    events = journal.document.get("events")
    if not isinstance(events, list) or len(events) != 1:
        return False
    discovery = events[0]
    if not isinstance(discovery, dict) or discovery.get("phase") != "discovered":
        return False
    if discovery.get("currentRelease") != current_release:
        return False
    if _git(["rev-parse", "HEAD"], runner) != next_commit:
        return False
    return not _git(["status", "--porcelain"], runner)


def _record_pre_activation_failure(
    journal: UpdateJournal,
    *,
    current_release: str | None,
    error: Exception,
) -> None:
    """Terminaliza uma falha comprovadamente anterior à instalação."""
    failed_phase = journal.phase
    try:
        journal.event(
            "failed-before-activation",
            current_release=current_release,
            data={"failedPhase": failed_phase, "errorType": type(error).__name__},
        )
    except Exception as evidence_error:
        raise AutomationError(
            "a preparação falhou antes da ativação e o journal não pôde ser terminalizado"
        ) from evidence_error


def _default_runner(
    argv: Sequence[str],
    cwd: Path,
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(argv),
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _run(
    argv: Sequence[str],
    *,
    cwd: Path = ROOT,
    timeout: int = 120,
    runner: CommandRunner = _default_runner,
    purpose: str,
) -> subprocess.CompletedProcess[str]:
    try:
        completed = runner(argv, cwd, timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        raise AutomationError(f"{purpose}: {exc}") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        if len(detail) > 1200:
            detail = detail[-1200:]
        raise AutomationError(f"{purpose} falhou (exit {completed.returncode}): {detail}")
    return completed


def _run_optional(
    argv: Sequence[str],
    *,
    cwd: Path = ROOT,
    timeout: int = 30,
    runner: CommandRunner = _default_runner,
) -> dict[str, object]:
    try:
        completed = runner(argv, cwd, timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "error": str(exc)}
    result: dict[str, object] = {"ok": completed.returncode == 0}
    text = completed.stdout.strip()
    if text:
        try:
            result["data"] = json.loads(text)
        except json.JSONDecodeError:
            result["output"] = text[:1200]
    if completed.returncode != 0:
        result["error"] = (completed.stderr or text).strip()[-1200:]
    return result


def _git(args: Sequence[str], runner: CommandRunner = _default_runner) -> str:
    completed = _run(
        ["git", *args],
        runner=runner,
        purpose=f"git {' '.join(args)}",
    )
    return completed.stdout.strip()


def _package_version(root: Path = ROOT) -> str:
    source = (root / "src" / "steamzero" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*"([^"]+)"$', source, re.MULTILINE)
    if match is None:
        raise AutomationError("não foi possível ler __version__ do pacote")
    return match.group(1)


def _wheel_identity(path: Path) -> tuple[str, str]:
    try:
        with zipfile.ZipFile(path) as archive:
            names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
            if len(names) != 1:
                raise AutomationError("wheel deve conter exatamente um METADATA")
            metadata = Parser().parsestr(archive.read(names[0]).decode("utf-8"))
    except (OSError, UnicodeDecodeError, zipfile.BadZipFile) as exc:
        raise AutomationError(f"wheel ilegível: {path.name}: {exc}") from exc
    project = metadata.get("Name")
    version = metadata.get("Version")
    if project != "steamzero" or not version:
        raise AutomationError(f"wheel inesperado: Name={project!r}, Version={version!r}")
    return project, version


def _safe_checksum_path(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise AutomationError(f"checksum tenta sair do bundle: {relative}") from exc
    return candidate


def _reject_bundle_symlinks(root: Path) -> None:
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise AutomationError(f"bundle contém symlink: {path.relative_to(root)}")


def _verify_checksums(root: Path) -> set[str]:
    checksum_file = root / "build" / "SHA256SUMS"
    if not checksum_file.is_file():
        raise AutomationError("bundle sem build/SHA256SUMS")
    checked: set[str] = set()
    for line in checksum_file.read_text(encoding="utf-8").splitlines():
        match = CHECKSUM_RE.fullmatch(line)
        if match is None:
            raise AutomationError(f"linha de checksum malformada: {line!r}")
        path = _safe_checksum_path(root, match.group("path"))
        if not path.is_file():
            raise AutomationError(f"arquivo declarado em SHA256SUMS ausente: {match.group('path')}")
        if _sha256(path) != match.group("digest"):
            raise AutomationError(f"hash diverge: {match.group('path')}")
        checked.add(match.group("path"))
    if len(checked) < 5:
        raise AutomationError(f"SHA256SUMS incompleto: somente {len(checked)} entradas")
    return checked


def load_bundle(root: Path, *, expected_ref: str = "refs/heads/main") -> Bundle:
    root = root.expanduser().resolve()
    _reject_bundle_symlinks(root)
    manifest_path = root / "dist" / "runtime-wheelhouse" / "WHEELHOUSE-MANIFEST.json"
    requirements = root / "requirements-runtime.lock"
    provenance_path = root / "build" / "provenance.json"
    if not manifest_path.is_file():
        raise AutomationError(f"manifesto do wheelhouse ausente: {manifest_path}")
    if not requirements.is_file():
        raise AutomationError("bundle sem requirements-runtime.lock")
    if not provenance_path.is_file():
        raise AutomationError("bundle sem build/provenance.json")

    try:
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AutomationError(f"metadata do bundle ilegível: {exc}") from exc
    if not isinstance(manifest_data, dict) or not isinstance(provenance, dict):
        raise AutomationError("manifesto e proveniência precisam ser objetos JSON")

    commit = str(manifest_data.get("sourceCommit") or "")
    version = str(manifest_data.get("packageVersion") or "")
    if COMMIT_RE.fullmatch(commit) is None:
        raise AutomationError(f"sourceCommit inválido no manifesto: {commit!r}")
    if manifest_data.get("sourceTreeState") != "clean":
        raise AutomationError("bundle não veio de árvore limpa")
    main_wheel = manifest_data.get("wheel")
    if not isinstance(main_wheel, dict) or not main_wheel.get("filename"):
        raise AutomationError("manifesto não declara o wheel principal")
    wheel = root / "dist" / str(main_wheel["filename"])
    if not wheel.is_file():
        raise AutomationError(f"wheel principal ausente: {wheel.name}")
    _project, wheel_version = _wheel_identity(wheel)
    if version != wheel_version:
        raise AutomationError(f"versão diverge: manifesto={version}, wheel={wheel_version}")

    problems = validate_wheelhouse(
        manifest_data,
        root / "dist" / "runtime-wheelhouse",
        requirements,
        wheel,
    )
    if problems:
        raise AutomationError("wheelhouse reprovado: " + "; ".join(problems))
    checksummed = _verify_checksums(root)
    required_supply_chain = {
        str(wheel.relative_to(root)),
        str(manifest_path.relative_to(root)),
        "build/provenance.json",
        "build/sbom.cdx.json",
        "build/pip-audit.json",
        "dist/runtime-wheelhouse.tar.zst",
    }
    missing_supply_chain = sorted(required_supply_chain - checksummed)
    if missing_supply_chain:
        raise AutomationError(
            "SHA256SUMS não cobre a cadeia de suprimentos: " + ", ".join(missing_supply_chain)
        )

    source = provenance.get("source")
    provenance_commit = str(
        provenance.get("sourceCommit")
        or provenance.get("commit")
        or (source.get("commit") if isinstance(source, dict) else "")
        or ""
    )
    if provenance_commit != commit:
        raise AutomationError(
            f"commit diverge entre manifesto e proveniência: {commit} != {provenance_commit}"
        )
    if not isinstance(source, dict) or source.get("ref") != expected_ref:
        raise AutomationError(f"proveniência não pertence a {expected_ref}")
    build = provenance.get("build")
    if not isinstance(build, dict) or build.get("sourceTreeState") != "clean":
        raise AutomationError("proveniência não declara sourceTreeState=clean")
    subjects: object = provenance.get("subjects")
    if not isinstance(subjects, list):
        single_subject = provenance.get("subject")
        subjects = [single_subject] if isinstance(single_subject, dict) else None
    if not isinstance(subjects, list):
        raise AutomationError("proveniência sem subjects")
    expected_digest = _sha256(wheel)
    matching_subject = False
    for subject in subjects:
        if not isinstance(subject, dict):
            continue
        digest = subject.get("sha256")
        if digest is None and isinstance(subject.get("digest"), dict):
            digest = subject["digest"].get("sha256")
        if subject.get("name") == wheel.name and digest == expected_digest:
            matching_subject = True
    if not matching_subject:
        raise AutomationError("proveniência não vincula nome e hash do wheel principal")

    run_id = manifest_data.get("githubRunId")
    provenance_run_id = build.get("runId")
    if not run_id or not provenance_run_id:
        raise AutomationError("bundle não vincula um run de CI ao manifesto e à proveniência")
    if str(run_id) != str(provenance_run_id):
        raise AutomationError(
            f"run diverge entre manifesto e proveniência: {run_id} != {provenance_run_id}"
        )
    release = f"{version}-{commit[:12]}"
    if RELEASE_RE.fullmatch(release) is None:
        raise AutomationError(f"release canônica inválida: {release}")
    return Bundle(
        root=root,
        version=version,
        commit=commit,
        release=release,
        wheel=wheel,
        wheel_sha256=expected_digest,
        requirements=requirements,
        wheelhouse=root / "dist" / "runtime-wheelhouse",
        manifest=manifest_path,
        run_id=str(run_id) if run_id else None,
        source_ref=expected_ref,
    )


def _read_host_truth(host_root: Path = HOST_ROOT) -> dict[str, object]:
    current = host_root / "current"
    data: dict[str, object] = {"installed": False}
    if not current.exists():
        return data
    try:
        target = current.resolve(strict=True)
        release = target.name
        manifest_path = target / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"installed": True, "ok": False, "error": str(exc)}
    return {
        "installed": True,
        "ok": True,
        "release": release,
        "packageVersion": manifest.get("packageVersion"),
        "sourceCommit": manifest.get("sourceCommit"),
    }


def inspect(
    *,
    runner: CommandRunner = _default_runner,
    host_root: Path = HOST_ROOT,
) -> dict[str, object]:
    head = _git(["rev-parse", "HEAD"], runner)
    dirty = bool(_git(["status", "--porcelain"], runner))
    branch = _git(["branch", "--show-current"], runner)
    origin_main = _git(["rev-parse", "refs/remotes/origin/main"], runner)
    latest_tag = _git(["describe", "--tags", "--abbrev=0", "--match", "v*"], runner)
    latest_tag_commit = _git(["rev-list", "-n", "1", latest_tag], runner)
    host = _read_host_truth(host_root)
    commands: dict[str, dict[str, object]] = {
        "githubAuth": _run_optional(["gh", "auth", "status", "-h", "github.com"], runner=runner),
        "cliVersion": _run_optional(["steamzero", "--version"], runner=runner),
        "doctor": _run_optional(["steamzero", "doctor", "--json"], timeout=60, runner=runner),
        "components": _run_optional(
            ["steamzero", "component", "list", "--json"], timeout=60, runner=runner
        ),
        "socket": _run_optional(
            ["systemctl", "--user", "is-active", "steamzero-core.socket"], runner=runner
        ),
        "service": _run_optional(
            ["systemctl", "--user", "is-active", "steamzero-core.service"], runner=runner
        ),
    }

    mismatches: list[str] = []
    if dirty:
        mismatches.append("worktree suja")
    if head != origin_main:
        mismatches.append("HEAD difere de origin/main")
    if host.get("sourceCommit") and host.get("sourceCommit") != latest_tag_commit:
        mismatches.append("host difere da última release tagueada")
    if not commands["githubAuth"]["ok"]:
        mismatches.append("GitHub CLI sem autenticação válida")
    for name in ("doctor", "components", "socket", "service"):
        if not commands[name]["ok"]:
            mismatches.append(f"probe {name} reprovado")
    return {
        "ok": not mismatches,
        "repository": {
            "root": str(ROOT),
            "branch": branch,
            "head": head,
            "originMain": origin_main,
            "clean": not dirty,
            "packageVersion": _package_version(),
            "latestTag": latest_tag,
            "latestTagCommit": latest_tag_commit,
        },
        "host": host,
        "probes": commands,
        "mismatches": mismatches,
    }


def _source_ref_for_update(to_ref: str) -> str:
    if to_ref == DEFAULT_UPDATE_REF:
        return "refs/heads/main"
    prefix = "origin/codex/"
    if not to_ref.startswith(prefix):
        raise AutomationError(
            f"update aceita {DEFAULT_UPDATE_REF} ou uma candidata explícita origin/codex/*"
        )
    branch = to_ref.removeprefix("origin/")
    if (
        branch.endswith(("/", "."))
        or ".." in branch
        or "@{" in branch
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", branch) is None
    ):
        raise AutomationError(f"referência candidata inválida: {to_ref}")
    return f"refs/heads/{branch}"


def _resolve_update_target(
    to_ref: str,
    *,
    runner: CommandRunner = _default_runner,
) -> str:
    source_ref = _source_ref_for_update(to_ref)
    remote_ref = f"refs/remotes/origin/{source_ref.removeprefix('refs/heads/')}"
    _run(
        ["git", "fetch", "origin", f"{source_ref}:{remote_ref}"],
        timeout=120,
        runner=runner,
        purpose=f"atualizar referência {to_ref}",
    )
    commit = _git(["rev-parse", f"{remote_ref}^{{commit}}"], runner)
    if COMMIT_RE.fullmatch(commit) is None:
        raise AutomationError(f"{to_ref} não resolveu para um commit completo")
    head = _git(["rev-parse", "HEAD"], runner)
    if head != commit:
        raise AutomationError(f"HEAD {head} difere do destino imutável {commit}")
    if _git(["status", "--porcelain"], runner):
        raise AutomationError("update recusa worktree suja")
    return commit


def _require_cache_space(path: Path, minimum: int = MIN_CACHE_FREE_BYTES) -> None:
    path.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(path).free
    if free < minimum:
        raise AutomationError(
            f"espaço livre insuficiente para atualização: {free} bytes; mínimo {minimum}"
        )


def _prepare_update_bundle(
    commit: str,
    *,
    cache_dir: Path | None,
    repository: str,
    runner: CommandRunner,
    source_ref: str = "refs/heads/main",
) -> Bundle:
    cache = (cache_dir or _cache_dir()).expanduser().resolve()
    _require_cache_space(cache)
    output = cache / commit
    if output.is_dir() and any(output.iterdir()):
        bundle = load_bundle(output, expected_ref=source_ref)
        if bundle.commit != commit:
            raise AutomationError("bundle em cache pertence a outro commit")
        _validate_cached_bundle_ci(
            bundle,
            repository=repository,
            source_ref=source_ref,
            runner=runner,
        )
        return bundle
    bundle = prepare(
        commit=commit,
        output=output,
        repository=repository,
        source_ref=source_ref,
        runner=runner,
    )
    bundle_bytes = sum(path.stat().st_size for path in bundle.root.rglob("*") if path.is_file())
    _require_cache_space(cache, max(512 * 1024 * 1024, bundle_bytes * 2))
    return bundle


def _validate_cached_bundle_ci(
    bundle: Bundle,
    *,
    repository: str,
    source_ref: str,
    runner: CommandRunner,
) -> None:
    """Revalida no GitHub a autoridade de um artifact mantido em cache local."""
    manifest_path = bundle.root / "AUTOMATION-MANIFEST.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AutomationError(f"manifesto da automação em cache ilegível: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("schemaVersion") != 1:
        raise AutomationError("manifesto da automação em cache inválido")
    expected = {
        "repository": repository,
        "sourceCommit": bundle.commit,
        "release": bundle.release,
        "runId": str(bundle.run_id or ""),
        "sourceRef": source_ref,
    }
    actual = {
        "repository": manifest.get("repository"),
        "sourceCommit": manifest.get("sourceCommit"),
        "release": manifest.get("release"),
        "runId": str(manifest.get("runId") or ""),
        "sourceRef": manifest.get("sourceRef"),
    }
    if actual != expected:
        raise AutomationError("manifesto da automação em cache diverge do bundle ou repositório")
    run = _discover_run(bundle.commit, repository, runner=runner)
    if str(run.get("databaseId") or "") != expected["runId"]:
        raise AutomationError("run verde atual diverge da proveniência do bundle em cache")


def _parse_json_object(
    completed: subprocess.CompletedProcess[str], purpose: str
) -> dict[str, object]:
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AutomationError(f"{purpose} devolveu JSON inválido") from exc
    if not isinstance(payload, dict):
        raise AutomationError(f"{purpose} não devolveu objeto JSON")
    return payload


def _installed_release_manifest(release: str, host_root: Path = HOST_ROOT) -> dict[str, object]:
    _require_rollback(release, host_root)
    try:
        manifest = install_host._verify_release(
            host_root / "releases" / release,
            expected_release=release,
            require_root_ownership=host_root == HOST_ROOT,
        )
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        raise AutomationError(
            f"release de rollback não passou verificação integral: {exc}"
        ) from exc
    return dict(manifest)


def _host_preflight(
    *,
    runner: CommandRunner,
    host_root: Path = HOST_ROOT,
    check_ownership: bool = True,
) -> dict[str, object]:
    host = _read_host_truth(host_root)
    release = host.get("release")
    if host.get("ok") is not True or not isinstance(release, str):
        raise AutomationError("host não possui release ativa verificável para rollback")
    manifest = _installed_release_manifest(release, host_root)
    if check_ownership:
        try:
            install_host.require_managed_activation_targets(install_host.Layout())
        except (OSError, RuntimeError, ValueError) as exc:
            raise AutomationError(f"preflight de ownership reprovado: {exc}") from exc

    active_cli = host_root / "current" / "venv" / "bin" / "steamzero"
    doctor = _run(
        [str(active_cli), "doctor", "--json"],
        timeout=120,
        runner=runner,
        purpose="doctor no preflight",
    )
    doctor_data = _parse_json_object(doctor, "doctor no preflight")
    if doctor_data.get("ok") is not True:
        raise AutomationError("doctor no preflight não declarou ok=true")
    doctor_payload = doctor_data.get("data")
    if not isinstance(doctor_payload, dict):
        raise AutomationError("doctor no preflight não declarou data")
    if doctor_payload.get("schemaVersion") != DATA_SCHEMA_VERSION:
        raise AutomationError(
            "rollback não é comprovadamente compatível com o schema de dados alvo: "
            f"host={doctor_payload.get('schemaVersion')}, alvo={DATA_SCHEMA_VERSION}"
        )
    pending = doctor_payload.get("pendingOperations")
    if pending not in (None, [], 0):
        raise AutomationError("host possui operações críticas pendentes")

    service_status = _run(
        [str(active_cli), "service", "status", "--json"],
        timeout=30,
        runner=runner,
        purpose="estado do daemon no preflight",
    )
    service_data = _parse_json_object(service_status, "estado do daemon no preflight")
    convergence = service_data.get("data")
    if (
        not isinstance(convergence, dict)
        or convergence.get("state") != "converged"
        or convergence.get("activatedRelease") != release
        or convergence.get("daemonRelease") != release
    ):
        raise AutomationError("daemon não está convergido com a release ativa")
    for unit in ("steamzero-core.socket", "steamzero-core.service"):
        _run(
            ["systemctl", "--user", "is-active", unit],
            runner=runner,
            purpose=f"unit {unit} no preflight",
        )
    return {
        "release": release,
        "manifest": manifest,
        "dataSchemaVersion": DATA_SCHEMA_VERSION,
        "doctor": {
            "ok": True,
            "pendingOperations": pending,
        },
        "daemon": {
            "state": "converged",
            "release": release,
            "commit": convergence.get("daemonCommit"),
        },
    }


def _plan_update(bundle: Bundle, preflight: dict[str, object]) -> UpdatePlan:
    rollback = preflight.get("release")
    if not isinstance(rollback, str):
        raise AutomationError("preflight não definiu a release de rollback")
    if rollback == bundle.release:
        raise AutomationError(f"release {bundle.release} já está ativa")
    return UpdatePlan(
        current_release=rollback,
        target_release=bundle.release,
        source_commit=bundle.commit,
        rollback_release=rollback,
        run_id=bundle.run_id,
        wheel_sha256=bundle.wheel_sha256,
        data_schema_version=DATA_SCHEMA_VERSION,
        confirmation_token=f"ATUALIZAR-{rollback}-PARA-{bundle.release}",
    )


def _discover_run(
    commit: str,
    repository: str,
    *,
    runner: CommandRunner = _default_runner,
) -> dict[str, object]:
    completed = _run(
        [
            "gh",
            "run",
            "list",
            "--repo",
            repository,
            "--workflow",
            "ci.yml",
            "--commit",
            commit,
            "--event",
            "push",
            "--json",
            "databaseId,headSha,status,conclusion,event,url",
            "--limit",
            "20",
        ],
        timeout=60,
        runner=runner,
        purpose="descobrir run CI do commit",
    )
    try:
        runs = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AutomationError("gh run list devolveu JSON inválido") from exc
    if not isinstance(runs, list):
        raise AutomationError("gh run list não devolveu uma lista")
    accepted = [
        run
        for run in runs
        if isinstance(run, dict)
        and run.get("headSha") == commit
        and run.get("event") == "push"
        and run.get("status") == "completed"
        and run.get("conclusion") == "success"
    ]
    if len(accepted) != 1:
        raise AutomationError(
            f"esperado exatamente um run push verde para {commit}; encontrados {len(accepted)}"
        )
    return accepted[0]


def _validate_archive_listing(listing: str) -> None:
    entries = [line.strip() for line in listing.splitlines() if line.strip()]
    if not entries:
        raise AutomationError("archive do wheelhouse está vazio")
    for entry in entries:
        path = Path(entry)
        if path.is_absolute() or ".." in path.parts:
            raise AutomationError(f"entrada insegura no archive: {entry}")
        if not path.parts or path.parts[0] != "runtime-wheelhouse":
            raise AutomationError(f"entrada fora de runtime-wheelhouse/: {entry}")


def prepare(
    *,
    commit: str,
    output: Path,
    repository: str = DEFAULT_REPOSITORY,
    run_id: str | None = None,
    source_ref: str = "refs/heads/main",
    runner: CommandRunner = _default_runner,
) -> Bundle:
    if COMMIT_RE.fullmatch(commit) is None:
        raise AutomationError("--commit exige SHA completo")
    _run(
        [
            "git",
            "fetch",
            "origin",
            f"{source_ref}:refs/remotes/origin/{source_ref.removeprefix('refs/heads/')}",
        ],
        timeout=120,
        runner=runner,
        purpose="atualizar referência origin/main",
    )
    head = _git(["rev-parse", "HEAD"], runner)
    if head != commit:
        raise AutomationError(f"checkout {head} difere do commit solicitado {commit}")
    if _git(["status", "--porcelain"], runner):
        raise AutomationError("prepare recusa worktree suja")
    remote_ref = f"refs/remotes/origin/{source_ref.removeprefix('refs/heads/')}"
    origin_source = _git(["rev-parse", remote_ref], runner)
    if origin_source != commit:
        raise AutomationError(f"prepare aceita somente o tip exato de {source_ref}")
    _run(
        ["gh", "auth", "status", "-h", "github.com"],
        runner=runner,
        purpose="autenticação do GitHub",
    )
    run = _discover_run(commit, repository, runner=runner)
    discovered_id = str(run.get("databaseId"))
    if run_id is not None and run_id != discovered_id:
        raise AutomationError(f"run solicitado {run_id} difere do run verde {discovered_id}")
    run_id = discovered_id

    output = output.expanduser().resolve()
    if output.exists() and any(output.iterdir()):
        raise AutomationError(f"diretório de saída não está vazio: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        _run(
            [
                "gh",
                "run",
                "download",
                run_id,
                "--repo",
                repository,
                "--name",
                f"steamzero-wheel-{commit}",
                "--dir",
                str(temporary),
            ],
            timeout=1800,
            runner=runner,
            purpose="download do artifact CI",
        )
        archive = temporary / "dist" / "runtime-wheelhouse.tar.zst"
        if not archive.is_file():
            raise AutomationError("artifact sem dist/runtime-wheelhouse.tar.zst")
        listing = _run(
            ["tar", "--zstd", "-tf", str(archive)],
            timeout=300,
            runner=runner,
            purpose="listagem segura do wheelhouse",
        )
        _validate_archive_listing(listing.stdout)
        _run(
            [
                "tar",
                "--zstd",
                "--no-same-owner",
                "--no-same-permissions",
                "-xf",
                str(archive),
                "-C",
                str(temporary / "dist"),
            ],
            timeout=300,
            runner=runner,
            purpose="extração do wheelhouse",
        )
        bundle = load_bundle(temporary, expected_ref=source_ref)
        if bundle.commit != commit:
            raise AutomationError(
                f"artifact pertence a {bundle.commit}, não ao commit solicitado {commit}"
            )
        automation_manifest = {
            "schemaVersion": 1,
            "preparedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "repository": repository,
            "runId": run_id,
            "runUrl": run.get("url"),
            "sourceCommit": commit,
            "sourceRef": source_ref,
            "release": bundle.release,
        }
        (temporary / "AUTOMATION-MANIFEST.json").write_text(
            json.dumps(automation_manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if output.exists():
            output.rmdir()
        temporary.replace(output)
        return load_bundle(output, expected_ref=source_ref)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _state_dir() -> Path:
    base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
    return base / "steamzero" / "release-automation"


def _record(
    release: str,
    phase: str,
    data: dict[str, object],
    *,
    state_dir: Path | None = None,
) -> Path:
    directory = (state_dir or _state_dir()).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{release}.json"
    lock_path = directory / f".{release}.lock"
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        document: dict[str, object] = {
            "schemaVersion": 1,
            "release": release,
            "events": [],
        }
        if path.is_file():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise AutomationError(f"state existente ilegível: {path}") from exc
            if not isinstance(loaded, dict) or loaded.get("release") != release:
                raise AutomationError(f"state existente pertence a outra release: {path}")
            document = loaded
        events = document.setdefault("events", [])
        if not isinstance(events, list):
            raise AutomationError(f"state inválido: {path}")
        events.append(
            {
                "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "phase": phase,
                "data": data,
            }
        )
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=directory,
                prefix=f".{path.name}.",
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                json.dump(document, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return path


def _require_checkout(bundle: Bundle, runner: CommandRunner) -> None:
    head = _git(["rev-parse", "HEAD"], runner)
    if head != bundle.commit:
        raise AutomationError(
            "instalador deve executar no checkout do artifact: "
            f"HEAD={head}, artifact={bundle.commit}"
        )
    if _git(["status", "--porcelain"], runner):
        raise AutomationError("instalação recusa worktree suja")
    if _package_version() != bundle.version:
        raise AutomationError("versão do checkout diverge do bundle")


def _require_rollback(release: str, host_root: Path = HOST_ROOT) -> None:
    if RELEASE_RE.fullmatch(release) is None:
        raise AutomationError(f"rollback release inválida: {release!r}")
    target = host_root / "releases" / release
    if not target.is_dir() or not (target / "manifest.json").is_file():
        raise AutomationError(f"rollback não está instalado e verificável: {release}")


def _converge(
    release: str,
    *,
    runner: CommandRunner,
) -> dict[str, object]:
    def execute(purpose: str) -> dict[str, object]:
        argv = [str(HOST_MANAGER), "converge", "--expect-release", release]
        try:
            completed = runner(argv, ROOT, 120)
        except (OSError, subprocess.SubprocessError) as exc:
            raise AutomationError(f"{purpose}: {exc}") from exc
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            detail = (completed.stderr or completed.stdout).strip()[-1200:]
            raise AutomationError(
                f"{purpose} devolveu JSON inválido (exit {completed.returncode}): {detail}"
            ) from exc
        if not isinstance(payload, dict):
            raise AutomationError(f"{purpose} não devolveu objeto JSON")
        report = _convergence_report(payload)
        if completed.returncode != 0:
            raise ConvergenceError(report)
        return payload

    first_data = execute(f"convergência {release}")
    second_data = execute(f"idempotência {release}")
    first_report = _convergence_report(first_data)
    second_report = _convergence_report(second_data)
    if first_report.get("state") != "converged":
        raise AutomationError(f"primeira convergência não convergiu: {first_report}")
    if second_report.get("state") != "converged":
        raise AutomationError(f"segunda convergência não convergiu: {second_report}")
    if second_report.get("restarted") is not False or second_report.get("attempts") != 0:
        raise AutomationError(
            "segunda convergência não foi idempotente: "
            f"restarted={second_report.get('restarted')}, "
            f"attempts={second_report.get('attempts')}"
        )
    for name, report in (("primeira", first_report), ("segunda", second_report)):
        if report.get("daemonRelease") != release or not isinstance(
            report.get("daemonCommit"), str
        ):
            raise AutomationError(
                f"{name} convergência não confirmou a identidade do daemon esperado"
            )
    return {"first": first_data, "idempotent": second_data}


def _convergence_report(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise AutomationError("convergência não devolveu objeto JSON")
    data = payload.get("data")
    report = data if isinstance(data, dict) else payload
    if not isinstance(report, dict):
        raise AutomationError("convergência sem relatório")
    daemon = report.get("daemon")
    if isinstance(daemon, dict):
        identity = daemon.get("identity")
        if isinstance(identity, dict):
            report = {
                **report,
                "daemonRelease": report.get("daemonRelease") or identity.get("releaseId"),
                "daemonCommit": report.get("daemonCommit") or identity.get("sourceCommit"),
            }
    return report


def _qml_offscreen_smoke(
    release: str,
    *,
    runner: CommandRunner,
    host_root: Path = HOST_ROOT,
) -> dict[str, object]:
    active_cli = host_root / "releases" / release / "venv" / "bin" / "steamzero"
    with tempfile.TemporaryDirectory(prefix="steamzero-update-ui-", dir="/tmp") as temporary:
        root = Path(temporary)
        command = [
            "/usr/bin/env",
            "HOME=/nonexistent",
            f"XDG_STATE_HOME={root / 'state'}",
            f"XDG_DATA_HOME={root / 'data'}",
            f"XDG_CONFIG_HOME={root / 'config'}",
            "QT_QPA_PLATFORM=offscreen",
            "QT_QUICK_BACKEND=software",
            "timeout",
            "--signal=TERM",
            "--kill-after=2",
            "5",
            str(active_cli),
            "desktop",
            "ui",
        ]
        try:
            completed = runner(command, ROOT, 10)
        except (OSError, subprocess.SubprocessError) as exc:
            raise AutomationError(f"smoke QML offscreen: {exc}") from exc
    if completed.returncode != 124:
        detail = (completed.stderr or completed.stdout).strip()[-600:]
        raise AutomationError(
            f"smoke QML offscreen não permaneceu ativo durante a janela de prova "
            f"(exit {completed.returncode}): {detail}"
        )
    return {"state": "started", "windowSeconds": 5, "exitCode": completed.returncode}


def _activation_smokes(
    release: str,
    *,
    runner: CommandRunner,
    expected_commit: str | None = None,
    expected_version: str | None = None,
    host_root: Path = HOST_ROOT,
) -> dict[str, object]:
    manifest = _installed_release_manifest(release, host_root)
    release_bin = host_root / "releases" / release / "venv" / "bin"
    version = _run(
        [str(release_bin / "steamzero"), "--version"],
        runner=runner,
        purpose="versão pós-ativação",
    )
    doctor = _run(
        [str(release_bin / "steamzero"), "doctor", "--json"],
        timeout=120,
        runner=runner,
        purpose="doctor pós-ativação",
    )
    socket = _run(
        ["systemctl", "--user", "is-active", "steamzero-core.socket"],
        runner=runner,
        purpose="socket pós-ativação",
    )
    service = _run(
        ["systemctl", "--user", "is-active", "steamzero-core.service"],
        runner=runner,
        purpose="service pós-ativação",
    )
    session = _run(
        [str(release_bin / "steamzero-gamemode-session"), "--check"],
        timeout=30,
        runner=runner,
        purpose="Game Mode pós-ativação",
    )
    qml = _qml_offscreen_smoke(release, runner=runner, host_root=host_root)
    host = _read_host_truth(host_root)
    if host.get("release") != release:
        raise AutomationError(f"current permaneceu em {host.get('release')}, esperado {release}")
    if expected_commit is not None and host.get("sourceCommit") != expected_commit:
        raise AutomationError("manifesto ativo não contém o sourceCommit esperado")
    if expected_version is not None and host.get("packageVersion") != expected_version:
        raise AutomationError("manifesto ativo não contém a packageVersion esperada")
    if expected_version is not None and expected_version not in version.stdout.strip():
        raise AutomationError("steamzero --version diverge da packageVersion esperada")
    doctor_data = _parse_json_object(doctor, "doctor")
    if doctor_data.get("ok") is not True:
        raise AutomationError("doctor pós-ativação não declarou ok=true")
    doctor_payload = doctor_data.get("data")
    if not isinstance(doctor_payload, dict):
        raise AutomationError("doctor pós-ativação não declarou data")
    if doctor_payload.get("schemaVersion") != DATA_SCHEMA_VERSION:
        raise AutomationError(
            "doctor pós-ativação declarou schema incompatível: "
            f"host={doctor_payload.get('schemaVersion')}, alvo={DATA_SCHEMA_VERSION}"
        )
    if doctor_payload.get("pendingOperations") not in (None, [], 0):
        raise AutomationError("doctor pós-ativação declarou operações críticas pendentes")
    doctor_summary: dict[str, object] = {
        "ok": True,
        "status": doctor_data.get("status"),
    }
    for key in ("schemaVersion", "pendingOperations", "version"):
        if key in doctor_payload:
            doctor_summary[key] = doctor_payload[key]
    return {
        "manifest": manifest,
        "version": version.stdout.strip(),
        "doctor": doctor_summary,
        "socket": socket.stdout.strip(),
        "service": service.stdout.strip(),
        "gameMode": session.stdout.strip(),
        "qml": qml,
        "host": host,
    }


def _post_activation(
    release: str,
    *,
    runner: CommandRunner,
    expected_commit: str | None = None,
    expected_version: str | None = None,
    host_root: Path = HOST_ROOT,
) -> dict[str, object]:
    convergence = _converge(release, runner=runner)
    smokes = _activation_smokes(
        release,
        runner=runner,
        expected_commit=expected_commit,
        expected_version=expected_version,
        host_root=host_root,
    )
    return {"convergence": convergence, **smokes}


def _install_only(bundle: Bundle, *, runner: CommandRunner) -> dict[str, object]:
    activated = _run(
        [
            "bigsudo",
            "/usr/bin/python3",
            str(ROOT / "tools" / "install_host.py"),
            "install",
            "--release",
            bundle.release,
            "--wheel",
            str(bundle.wheel),
            "--wheel-sha256",
            bundle.wheel_sha256,
            "--requirements",
            str(bundle.requirements),
            "--wheelhouse",
            str(bundle.wheelhouse),
            "--source-commit",
            bundle.commit,
        ],
        timeout=1800,
        runner=runner,
        purpose=f"instalação {bundle.release}",
    )
    activation_data = _parse_json_object(activated, "install_host")
    if activation_data.get("ok") is not True:
        raise AutomationError("install_host não declarou ok=true")
    return activation_data


def _rollback_only(release: str, *, runner: CommandRunner) -> dict[str, object]:
    activated = _run(
        [
            "bigsudo",
            "/usr/bin/python3",
            str(ROOT / "tools" / "install_host.py"),
            "rollback",
            "--release",
            release,
        ],
        timeout=300,
        runner=runner,
        purpose=f"rollback {release}",
    )
    activation_data = _parse_json_object(activated, "install_host rollback")
    if activation_data.get("ok") is not True:
        raise AutomationError("install_host rollback não declarou ok=true")
    return activation_data


def _install_unlocked(
    bundle: Bundle,
    *,
    rollback_release: str,
    confirmation: str,
    runner: CommandRunner = _default_runner,
    state_dir: Path | None = None,
) -> dict[str, object]:
    expected = f"INSTALAR-{bundle.release}"
    if confirmation != expected:
        raise AutomationError(f"confirmação inválida; esperado --confirm-install {expected}")
    _require_checkout(bundle, runner)
    _require_rollback(rollback_release)
    activation_data = _install_only(bundle, runner=runner)
    verified = _post_activation(
        bundle.release,
        runner=runner,
        expected_commit=bundle.commit,
        expected_version=bundle.version,
    )
    result: dict[str, object] = {
        "release": bundle.release,
        "sourceCommit": bundle.commit,
        "rollbackRelease": rollback_release,
        "activation": activation_data,
        "verification": verified,
    }
    evidence = _record(bundle.release, "install", result, state_dir=state_dir)
    result["evidence"] = str(evidence)
    return result


def install(
    bundle: Bundle,
    *,
    rollback_release: str,
    confirmation: str,
    runner: CommandRunner = _default_runner,
    state_dir: Path | None = None,
) -> dict[str, object]:
    with _update_lock(state_dir):
        return _install_unlocked(
            bundle,
            rollback_release=rollback_release,
            confirmation=confirmation,
            runner=runner,
            state_dir=state_dir,
        )


def _rollback_unlocked(
    release: str,
    *,
    confirmation: str,
    runner: CommandRunner = _default_runner,
    state_release: str | None = None,
    state_dir: Path | None = None,
) -> dict[str, object]:
    expected = f"REVERTER-{release}"
    if confirmation != expected:
        raise AutomationError(f"confirmação inválida; esperado --confirm-rollback {expected}")
    _require_rollback(release)
    activation_data = _rollback_only(release, runner=runner)
    verified = _post_activation(release, runner=runner)
    result: dict[str, object] = {
        "release": release,
        "activation": activation_data,
        "verification": verified,
    }
    evidence_release = state_release or release
    evidence = _record(evidence_release, "rollback", result, state_dir=state_dir)
    result["evidence"] = str(evidence)
    return result


def rollback(
    release: str,
    *,
    confirmation: str,
    runner: CommandRunner = _default_runner,
    state_release: str | None = None,
    state_dir: Path | None = None,
) -> dict[str, object]:
    with _update_lock(state_dir):
        return _rollback_unlocked(
            release,
            confirmation=confirmation,
            runner=runner,
            state_release=state_release,
            state_dir=state_dir,
        )


def _state_db_fingerprint() -> str:
    base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
    database = base / "steamzero" / "state.db"
    if not database.exists():
        return "absent"
    if database.is_symlink() or not database.is_file():
        raise AutomationError("state.db não é um arquivo regular")
    snapshot: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix="steamzero-state-snapshot-", suffix=".db", dir="/tmp", delete=False
        ) as handle:
            snapshot = Path(handle.name)
        source_uri = f"{database.resolve().as_uri()}?mode=ro"
        with (
            sqlite3.connect(source_uri, uri=True) as source,
            sqlite3.connect(snapshot) as destination,
        ):
            source.backup(destination)
        return _sha256(snapshot)
    except sqlite3.Error as exc:
        raise AutomationError(f"não foi possível fotografar state.db com WAL: {exc}") from exc
    finally:
        if snapshot is not None:
            snapshot.unlink(missing_ok=True)


def _quarantine_path(release: str, state_dir: Path | None) -> Path:
    return (state_dir or _state_dir()).expanduser() / "quarantine" / f"{release}.json"


def _mark_quarantined(
    release: str,
    *,
    source_commit: str,
    failed_phase: str,
    state_dir: Path | None,
) -> Path:
    path = _quarantine_path(release, state_dir)
    _atomic_json(
        path,
        {
            "schemaVersion": 1,
            "release": release,
            "sourceCommit": source_commit,
            "state": "failed-verification",
            "failedPhase": failed_phase,
            "recordedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        },
    )
    return path


def _require_not_quarantined(release: str, state_dir: Path | None) -> None:
    path = _quarantine_path(release, state_dir)
    if path.exists():
        raise AutomationError(
            f"release {release} está em quarentena failed-verification; "
            "investigue a evidência antes de nova ativação"
        )


def _stop_inconsistent_units(runner: CommandRunner) -> dict[str, object]:
    results: dict[str, object] = {}
    for unit in ("steamzero-core.service", "steamzero-core.socket"):
        outcome = _run_optional(
            ["systemctl", "--user", "stop", unit],
            runner=runner,
        )
        results[unit] = bool(outcome.get("ok"))
    return results


def _journal_event_data(journal: UpdateJournal, key: str) -> object | None:
    events = journal.document.get("events")
    if not isinstance(events, list):
        return None
    for event in reversed(events):
        if not isinstance(event, dict):
            continue
        data = event.get("data")
        if isinstance(data, dict) and key in data:
            value: object = data[key]
            return value
    return None


def _journal_has_phase(journal: UpdateJournal, phase: str) -> bool:
    events = journal.document.get("events")
    return isinstance(events, list) and any(
        isinstance(event, dict) and event.get("phase") == phase for event in events
    )


def _journal_matches(
    journal: UpdateJournal,
    plan: UpdatePlan,
    *,
    allow_missing_rollback: bool = False,
) -> None:
    expected = {
        "targetRelease": plan.target_release,
        "rollbackRelease": plan.rollback_release,
        "sourceCommit": plan.source_commit,
        "wheelSha256": plan.wheel_sha256,
    }
    mismatches = []
    for key, value in expected.items():
        actual = journal.document.get(key)
        if key == "rollbackRelease" and allow_missing_rollback and actual is None:
            continue
        if actual != value:
            mismatches.append(key)
    if mismatches:
        raise AutomationError(
            "transação incompleta pertence a outro plano: " + ", ".join(mismatches)
        )


def _finish_failed_update(
    *,
    bundle: Bundle,
    plan: UpdatePlan,
    journal: UpdateJournal,
    failed_phase: str,
    original_error: Exception,
    runner: CommandRunner,
    state_dir: Path | None,
    host_root: Path,
) -> None:
    current = _read_host_truth(host_root).get("release")
    evidence_errors: list[Exception] = []

    def record(
        phase: str,
        *,
        current_release: str | None,
        data: dict[str, object] | None = None,
    ) -> None:
        try:
            journal.event(phase, current_release=current_release, data=data)
        except Exception as exc:  # A segurança do host prevalece sobre a telemetria.
            evidence_errors.append(exc)

    record(
        "rollback-required",
        current_release=str(current) if current else None,
        data={
            "failedPhase": failed_phase,
            "errorType": type(original_error).__name__,
            **(
                {
                    "failureState": original_error.state,
                    "failureCode": original_error.code,
                    "failureDetail": original_error.detail,
                }
                if isinstance(original_error, ConvergenceError)
                else {}
            ),
        },
    )
    try:
        _mark_quarantined(
            bundle.release,
            source_commit=bundle.commit,
            failed_phase=failed_phase,
            state_dir=state_dir,
        )
    except Exception as exc:
        evidence_errors.append(exc)
    try:
        record("rollback-started", current_release=str(current) if current else None)
        _rollback_only(plan.rollback_release, runner=runner)
        record("rollback-activated", current_release=plan.rollback_release)
        convergence = _converge(plan.rollback_release, runner=runner)
        record(
            "convergence-passed",
            current_release=plan.rollback_release,
            data={"direction": "rollback"},
        )
        smokes = _activation_smokes(
            plan.rollback_release,
            runner=runner,
            host_root=host_root,
        )
        expected_state = _journal_event_data(journal, "stateFingerprint")
        if isinstance(expected_state, str) and _state_db_fingerprint() != expected_state:
            raise AutomationError("state.db divergiu após o rollback")
        record(
            "rollback-verified",
            current_release=plan.rollback_release,
            data={
                "daemonRelease": _convergence_report(convergence["idempotent"]).get(
                    "daemonRelease"
                ),
                "doctorOk": bool(smokes.get("doctor")),
            },
        )
        if not _quarantine_path(bundle.release, state_dir).is_file():
            try:
                _mark_quarantined(
                    bundle.release,
                    source_commit=bundle.commit,
                    failed_phase=failed_phase,
                    state_dir=state_dir,
                )
            except Exception as exc:
                evidence_errors.append(exc)
        record(
            "failed-safe",
            current_release=plan.rollback_release,
            data={"deploymentHealthy": False, "rollbackHealthy": True},
        )
    except Exception as rollback_error:
        units = _stop_inconsistent_units(runner)
        current_after = _read_host_truth(host_root).get("release")
        record(
            "rollback-failed",
            current_release=str(current_after) if current_after else None,
            data={
                "errorType": type(rollback_error).__name__,
                "unitsStopped": all(units.values()),
            },
        )
        raise AutomationError(
            f"ATENÇÃO: update {bundle.release} falhou e o rollback para "
            f"{plan.rollback_release} também falhou; units foram paradas. "
            f"Recupere com tools/release_host.py rollback --release "
            f"{plan.rollback_release} --confirm-rollback REVERTER-{plan.rollback_release}"
        ) from rollback_error
    if evidence_errors:
        raise AutomationError(
            f"update {bundle.release} falhou em {failed_phase}; rollback "
            f"{plan.rollback_release} foi verificado, mas a evidência local ficou incompleta"
        ) from original_error
    raise AutomationError(
        f"update {bundle.release} falhou em {failed_phase}; rollback "
        f"{plan.rollback_release} foi ativado e verificado"
    ) from original_error


def _execute_update_transaction(
    bundle: Bundle,
    plan: UpdatePlan,
    journal: UpdateJournal,
    *,
    runner: CommandRunner,
    state_dir: Path | None,
    host_root: Path = HOST_ROOT,
) -> dict[str, object]:
    _journal_matches(journal, plan)
    current = _read_host_truth(host_root).get("release")
    if _journal_has_phase(journal, "rollback-required"):
        _finish_failed_update(
            bundle=bundle,
            plan=plan,
            journal=journal,
            failed_phase=str(_journal_event_data(journal, "failedPhase") or "interrupted"),
            original_error=AutomationError("retomando rollback interrompido"),
            runner=runner,
            state_dir=state_dir,
            host_root=host_root,
        )

    before_fingerprint = _journal_event_data(journal, "stateFingerprint")
    if not isinstance(before_fingerprint, str):
        before_fingerprint = _state_db_fingerprint()
        journal.event(
            "approved",
            current_release=str(current) if current else None,
            data={"stateFingerprint": before_fingerprint},
        )

    activation_data: dict[str, object] | None = None
    if current != bundle.release:
        if current != plan.rollback_release:
            _finish_failed_update(
                bundle=bundle,
                plan=plan,
                journal=journal,
                failed_phase="unexpected-current",
                original_error=AutomationError("current não aponta para target nem rollback"),
                runner=runner,
                state_dir=state_dir,
                host_root=host_root,
            )
        journal.event("install-started", current_release=plan.rollback_release)
        try:
            activation_data = _install_only(bundle, runner=runner)
        except Exception as exc:
            after_error = _read_host_truth(host_root).get("release")
            if after_error == plan.rollback_release:
                journal.event(
                    "failed-before-activation",
                    current_release=str(after_error) if after_error else None,
                    data={"errorType": type(exc).__name__},
                )
                raise
                raise
            _finish_failed_update(
                bundle=bundle,
                plan=plan,
                journal=journal,
                failed_phase="install",
                original_error=exc,
                runner=runner,
                state_dir=state_dir,
                host_root=host_root,
            )
        current = _read_host_truth(host_root).get("release")
        if current != bundle.release:
            _finish_failed_update(
                bundle=bundle,
                plan=plan,
                journal=journal,
                failed_phase="activation-mismatch",
                original_error=AutomationError("install_host retornou sucesso sem ativar o target"),
                runner=runner,
                state_dir=state_dir,
                host_root=host_root,
            )
        try:
            journal.event("activated", current_release=bundle.release)
        except Exception as exc:
            _finish_failed_update(
                bundle=bundle,
                plan=plan,
                journal=journal,
                failed_phase="activated-evidence",
                original_error=exc,
                runner=runner,
                state_dir=state_dir,
                host_root=host_root,
            )

    try:
        convergence = _converge(bundle.release, runner=runner)
        report = _convergence_report(convergence["idempotent"])
        journal.event(
            "convergence-passed",
            current_release=bundle.release,
            data={
                "daemonRelease": report.get("daemonRelease"),
                "daemonCommit": report.get("daemonCommit"),
                "attempts": report.get("attempts"),
            },
        )
        smokes = _activation_smokes(
            bundle.release,
            runner=runner,
            expected_commit=bundle.commit,
            expected_version=bundle.version,
            host_root=host_root,
        )
        after_fingerprint = _state_db_fingerprint()
        if after_fingerprint != before_fingerprint:
            raise AutomationError("state.db mudou durante a atualização")
        journal.event(
            "smokes-passed",
            current_release=bundle.release,
            data={
                "doctorOk": True,
                "gameMode": "ready",
                "qml": "started-offscreen",
                "statePreserved": True,
            },
        )
    except Exception as exc:
        _finish_failed_update(
            bundle=bundle,
            plan=plan,
            journal=journal,
            failed_phase=journal.phase,
            original_error=exc,
            runner=runner,
            state_dir=state_dir,
            host_root=host_root,
        )

    journal.document["deploymentHealthy"] = True
    journal.event(
        "committed",
        current_release=bundle.release,
        data={"deploymentHealthy": True, "physicalCertification": False},
    )
    return {
        "release": bundle.release,
        "sourceCommit": bundle.commit,
        "rollbackRelease": plan.rollback_release,
        "activation": activation_data or {"recovered": True},
        "verification": {"convergence": convergence, **smokes},
        "deploymentHealthy": True,
        "physicalCertification": False,
        "journal": str(journal.path),
    }


def _require_recovery_checkout(commit: str, runner: CommandRunner) -> None:
    head = _git(["rev-parse", "HEAD"], runner)
    if head != commit:
        raise AutomationError(
            f"transação incompleta exige checkout do commit {commit}; HEAD atual é {head}"
        )
    if _git(["status", "--porcelain"], runner):
        raise AutomationError("recuperação recusa worktree suja")


def _resume_plan(journal: UpdateJournal, bundle: Bundle) -> UpdatePlan:
    rollback = journal.document.get("rollbackRelease")
    target = journal.document.get("targetRelease")
    if not isinstance(rollback, str) or target != bundle.release:
        raise AutomationError("journal incompleto diverge do bundle em cache")
    return UpdatePlan(
        current_release=rollback,
        target_release=bundle.release,
        source_commit=bundle.commit,
        rollback_release=rollback,
        run_id=bundle.run_id,
        wheel_sha256=bundle.wheel_sha256,
        data_schema_version=DATA_SCHEMA_VERSION,
        confirmation_token=f"ATUALIZAR-{rollback}-PARA-{bundle.release}",
    )


def _format_update_plan(plan: UpdatePlan) -> str:
    return "\n".join(
        (
            "Atualização SteamZero",
            "",
            f"Atual:     {plan.current_release}",
            f"Destino:   {plan.target_release}",
            f"Commit:    {plan.source_commit}",
            "CI:        verde",
            "Bundle:    verificado",
            f"Rollback:  {plan.rollback_release}",
            "Dados XDG: preservados",
            "Boot:      não será alterado",
            "Certificação física: pendente do operador",
        )
    )


def update(
    *,
    to_ref: str = DEFAULT_UPDATE_REF,
    confirmation: str | None = None,
    plan_only: bool = False,
    repository: str = DEFAULT_REPOSITORY,
    cache_dir: Path | None = None,
    state_dir: Path | None = None,
    runner: CommandRunner = _default_runner,
    input_fn: Callable[[str], str] | None = None,
    host_root: Path = HOST_ROOT,
    check_ownership: bool = True,
) -> dict[str, object]:
    """Executa ou recupera uma atualização inteira sob um único lock global."""
    with _update_lock(state_dir):
        unfinished = _load_unfinished_journal(state_dir)
        resolved_commit: str | None = None
        if unfinished is not None and unfinished.phase == "discovered":
            resolved_commit = _resolve_update_target(to_ref, runner=runner)
            current = _read_host_truth(host_root).get("release")
            current_release = str(current) if current else None
            if _discovery_can_be_superseded(
                unfinished,
                next_commit=resolved_commit,
                current_release=current_release,
                runner=runner,
            ):
                unfinished.event(
                    "failed-before-activation",
                    current_release=current_release,
                    data={
                        "failedPhase": "discovered",
                        "reason": "source-advanced-before-bundle-verification",
                    },
                )
                unfinished = None
        if unfinished is not None:
            commit = str(unfinished.document.get("sourceCommit") or "")
            source_ref = str(unfinished.document.get("sourceRef") or "refs/heads/main")
            if COMMIT_RE.fullmatch(commit) is None:
                raise AutomationError("journal incompleto não possui sourceCommit válido")
            _require_recovery_checkout(commit, runner)
            bundle_root = (cache_dir or _cache_dir()).expanduser().resolve() / commit
            if unfinished.phase == "discovered":
                current = _read_host_truth(host_root).get("release")
                current_release = str(current) if current else None
                try:
                    bundle = _prepare_update_bundle(
                        commit,
                        cache_dir=cache_dir,
                        repository=repository,
                        source_ref=source_ref,
                        runner=runner,
                    )
                    _bind_journal_bundle(
                        unfinished,
                        bundle,
                        current_release=current_release,
                    )
                except Exception as exc:
                    _record_pre_activation_failure(
                        unfinished,
                        current_release=current_release,
                        error=exc,
                    )
                    raise
            else:
                bundle = load_bundle(bundle_root, expected_ref=source_ref)
            _require_checkout(bundle, runner)
            if not _journal_has_phase(unfinished, "rollback-required"):
                _require_not_quarantined(bundle.release, state_dir)
            if unfinished.phase == "bundle-verified":
                preflight = _host_preflight(
                    runner=runner,
                    host_root=host_root,
                    check_ownership=check_ownership,
                )
                plan = _plan_update(bundle, preflight)
                _bind_journal_preflight(unfinished, plan)
            else:
                plan = _resume_plan(unfinished, bundle)
            if plan_only:
                return {
                    "plan": plan.public(),
                    "recoveryPhase": unfinished.phase,
                    "deploymentHealthy": False,
                    "physicalCertification": False,
                    "journal": str(unfinished.path),
                }
            supplied = confirmation
            if supplied is None and input_fn is not None:
                print(_format_update_plan(plan), file=sys.stderr)
                supplied = input_fn(f"Digite {plan.confirmation_token} para recuperar: ")
            if supplied != plan.confirmation_token:
                raise AutomationError(
                    f"recuperação exige --confirm-update {plan.confirmation_token}"
                )
            return _execute_update_transaction(
                bundle,
                plan,
                unfinished,
                runner=runner,
                state_dir=state_dir,
                host_root=host_root,
            )

        source_ref = _source_ref_for_update(to_ref)
        commit = resolved_commit or _resolve_update_target(to_ref, runner=runner)
        current = _read_host_truth(host_root).get("release")
        current_release = str(current) if current else None
        journal = _start_update_journal(
            commit,
            source_ref=source_ref,
            current_release=current_release,
            state_dir=state_dir,
        )
        try:
            bundle = _prepare_update_bundle(
                commit,
                cache_dir=cache_dir,
                repository=repository,
                source_ref=source_ref,
                runner=runner,
            )
            _bind_journal_bundle(
                journal,
                bundle,
                current_release=current_release,
            )
            _require_checkout(bundle, runner)
            _require_not_quarantined(bundle.release, state_dir)
            preflight = _host_preflight(
                runner=runner,
                host_root=host_root,
                check_ownership=check_ownership,
            )
            plan = _plan_update(bundle, preflight)
            _bind_journal_preflight(journal, plan)
            if plan_only:
                journal.event("planned", current_release=plan.current_release)
                return {
                    "plan": plan.public(),
                    "deploymentHealthy": False,
                    "physicalCertification": False,
                    "journal": str(journal.path),
                }
        except Exception as exc:
            _record_pre_activation_failure(
                journal,
                current_release=current_release,
                error=exc,
            )
            raise

        supplied = confirmation
        if supplied is None and input_fn is not None:
            print(_format_update_plan(plan), file=sys.stderr)
            supplied = input_fn(f"Digite {plan.confirmation_token} para continuar: ")
        if supplied != plan.confirmation_token:
            journal.event("cancelled", current_release=plan.current_release)
            raise AutomationError(
                f"confirmação inválida; esperado --confirm-update {plan.confirmation_token}"
            )
        return _execute_update_transaction(
            bundle,
            plan,
            journal,
            runner=runner,
            state_dir=state_dir,
            host_root=host_root,
        )


def cycle(
    bundle: Bundle,
    *,
    rollback_release: str,
    confirmation: str,
    runner: CommandRunner = _default_runner,
    state_dir: Path | None = None,
) -> dict[str, object]:
    expected = f"{bundle.release}->{rollback_release}->{bundle.release}"
    if confirmation != expected:
        raise AutomationError(f"confirmação inválida; esperado --confirm-cycle {expected}")
    with _update_lock(state_dir):
        target = _install_unlocked(
            bundle,
            rollback_release=rollback_release,
            confirmation=f"INSTALAR-{bundle.release}",
            runner=runner,
            state_dir=state_dir,
        )
        previous = _rollback_unlocked(
            rollback_release,
            confirmation=f"REVERTER-{rollback_release}",
            runner=runner,
            state_release=bundle.release,
            state_dir=state_dir,
        )
        restored = _install_unlocked(
            bundle,
            rollback_release=rollback_release,
            confirmation=f"INSTALAR-{bundle.release}",
            runner=runner,
            state_dir=state_dir,
        )
    result: dict[str, object] = {
        "release": bundle.release,
        "sourceCommit": bundle.commit,
        "rollbackRelease": rollback_release,
        "initial": target,
        "rollback": previous,
        "restored": restored,
        "machineCycle": "passed",
    }
    evidence = _record(bundle.release, "cycle", result, state_dir=state_dir)
    result["evidence"] = str(evidence)
    return result


def _load_certification(path: Path, bundle: Bundle) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AutomationError(f"evidência de certificação ilegível: {exc}") from exc
    if not isinstance(data, dict):
        raise AutomationError("evidência de certificação precisa ser objeto JSON")
    if data.get("schemaVersion") != 1:
        raise AutomationError("schemaVersion da certificação deve ser 1")
    if data.get("release") != bundle.release or data.get("sourceCommit") != bundle.commit:
        raise AutomationError("certificação pertence a outra release/commit")
    if data.get("verdict") != "approved":
        raise AutomationError("certificação não está aprovada")
    gates = data.get("requiredGates")
    if not isinstance(gates, dict):
        raise AutomationError("requiredGates da certificação precisa ser objeto")
    missing = [name for name in REQUIRED_CERTIFICATION_GATES if gates.get(name) is not True]
    if missing or any(value is not True for value in gates.values()):
        raise AutomationError("todos os requiredGates da certificação precisam ser true")
    return data


def _release_assets(bundle: Bundle, certification: Path) -> list[Path]:
    automation_manifest = bundle.root / "AUTOMATION-MANIFEST.json"
    try:
        automation = json.loads(automation_manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AutomationError(f"manifesto da automação ilegível: {exc}") from exc
    if not isinstance(automation, dict):
        raise AutomationError("manifesto da automação precisa ser objeto JSON")
    if (
        automation.get("sourceCommit") != bundle.commit
        or automation.get("release") != bundle.release
        or str(automation.get("runId")) != str(bundle.run_id)
    ):
        raise AutomationError("manifesto da automação diverge do bundle")
    paths = [
        bundle.wheel,
        bundle.root / "dist" / "runtime-wheelhouse.tar.zst",
        bundle.manifest,
        bundle.requirements,
        bundle.root / "build" / "SHA256SUMS",
        bundle.root / "build" / "provenance.json",
        bundle.root / "build" / "sbom.cdx.json",
        bundle.root / "build" / "pip-audit.json",
        automation_manifest,
        certification,
    ]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise AutomationError("assets duráveis ausentes: " + ", ".join(missing))
    names = [path.name for path in paths]
    if len(names) != len(set(names)):
        raise AutomationError("assets de release têm nomes duplicados")
    return paths


def _release_asset_state(
    release_data: object,
    local_assets: Sequence[Path],
) -> tuple[list[Path], list[str]]:
    if not isinstance(release_data, dict):
        raise AutomationError("gh release view não devolveu objeto JSON")
    assets = release_data.get("assets")
    if not isinstance(assets, list):
        raise AutomationError("GitHub release não publicou a lista de assets")
    remote = {
        str(asset.get("name")): asset
        for asset in assets
        if isinstance(asset, dict) and asset.get("name")
    }
    missing: list[Path] = []
    problems: list[str] = []
    for path in local_assets:
        asset = remote.get(path.name)
        if asset is None:
            missing.append(path)
            continue
        digest = asset.get("digest")
        expected = f"sha256:{_sha256(path)}"
        if digest != expected:
            problems.append(f"{path.name}: digest remoto {digest!r} != {expected}")
    return missing, problems


def _view_release(
    tag: str,
    repository: str,
    *,
    runner: CommandRunner,
) -> subprocess.CompletedProcess[str]:
    try:
        return runner(
            [
                "gh",
                "release",
                "view",
                tag,
                "--repo",
                repository,
                "--json",
                "tagName,url,isDraft,isPrerelease,assets",
            ],
            ROOT,
            60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AutomationError(f"consultar GitHub release {tag}: {exc}") from exc


def publish(
    bundle: Bundle,
    *,
    certification: Path,
    notes: Path,
    confirmation: str,
    repository: str = DEFAULT_REPOSITORY,
    runner: CommandRunner = _default_runner,
    state_dir: Path | None = None,
) -> dict[str, object]:
    if bundle.source_ref != "refs/heads/main":
        raise AutomationError(
            "publicação final aceita somente bundle proveniente de refs/heads/main"
        )
    tag = f"v{bundle.version}"
    if TAG_RE.fullmatch(tag) is None:
        raise AutomationError(f"tag inválida: {tag}")
    if confirmation != tag:
        raise AutomationError(f"confirmação inválida; esperado --confirm-publish {tag}")
    _require_checkout(bundle, runner)
    _load_certification(certification, bundle)
    if not notes.is_file():
        raise AutomationError(f"release notes ausentes: {notes}")
    assets = _release_assets(bundle, certification)
    _run(
        ["gh", "auth", "status", "-h", "github.com"],
        runner=runner,
        purpose="autenticação do GitHub",
    )
    existing = runner(["git", "rev-parse", "-q", "--verify", f"refs/tags/{tag}"], ROOT, 30)
    if existing.returncode == 0:
        tagged_commit = existing.stdout.strip()
        if tagged_commit != bundle.commit:
            tagged_commit = _git(["rev-list", "-n", "1", tag], runner)
        if tagged_commit != bundle.commit:
            raise AutomationError(f"{tag} já aponta para {tagged_commit}")
    else:
        _run(
            ["git", "tag", "-a", tag, bundle.commit, "-m", f"SteamZero {bundle.version}"],
            runner=runner,
            purpose=f"criar tag {tag}",
        )
    _run(
        ["git", "push", "origin", f"refs/tags/{tag}"],
        timeout=120,
        runner=runner,
        purpose=f"push da tag {tag}",
    )
    release_view = _view_release(tag, repository, runner=runner)
    if release_view.returncode == 0:
        try:
            release_data = json.loads(release_view.stdout)
        except json.JSONDecodeError as exc:
            raise AutomationError("gh release view devolveu JSON inválido") from exc
        if release_data.get("isDraft") is True or release_data.get("isPrerelease") is not True:
            raise AutomationError("release existente não é uma pre-release publicada")
        missing, problems = _release_asset_state(release_data, assets)
        if problems:
            raise AutomationError("assets remotos divergentes: " + "; ".join(problems))
        if missing:
            _run(
                [
                    "gh",
                    "release",
                    "upload",
                    tag,
                    *[str(path) for path in missing],
                    "--repo",
                    repository,
                ],
                timeout=600,
                runner=runner,
                purpose=f"completar assets da pre-release {tag}",
            )
    else:
        created = _run(
            [
                "gh",
                "release",
                "create",
                tag,
                *[str(path) for path in assets],
                "--repo",
                repository,
                "--verify-tag",
                "--prerelease",
                "--latest=false",
                "--title",
                f"SteamZero {bundle.version}",
                "--notes-file",
                str(notes),
            ],
            timeout=120,
            runner=runner,
            purpose=f"criar pre-release {tag}",
        )
        release_data = {"url": created.stdout.strip(), "tagName": tag}
    verified_view = _run(
        [
            "gh",
            "release",
            "view",
            tag,
            "--repo",
            repository,
            "--json",
            "tagName,url,isDraft,isPrerelease,assets",
        ],
        timeout=60,
        runner=runner,
        purpose=f"verificar pre-release {tag}",
    )
    try:
        verified_data = json.loads(verified_view.stdout)
    except json.JSONDecodeError as exc:
        raise AutomationError("verificação da release devolveu JSON inválido") from exc
    if verified_data.get("isDraft") is True or verified_data.get("isPrerelease") is not True:
        raise AutomationError("GitHub release final não é uma pre-release publicada")
    missing, problems = _release_asset_state(verified_data, assets)
    if missing or problems:
        detail = [f"ausentes: {[path.name for path in missing]}"] if missing else []
        detail.extend(problems)
        raise AutomationError("verificação dos assets reprovou: " + "; ".join(detail))
    release_data = {
        "url": verified_data.get("url"),
        "tagName": verified_data.get("tagName"),
        "assetCount": len(assets),
    }
    result: dict[str, object] = {
        "release": bundle.release,
        "sourceCommit": bundle.commit,
        "tag": tag,
        "githubRelease": release_data,
    }
    evidence = _record(bundle.release, "publish", result, state_dir=state_dir)
    result["evidence"] = str(evidence)
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="saída JSON compacta")
    subparsers = parser.add_subparsers(dest="action", required=True)
    subparsers.add_parser("inspect")

    verify = subparsers.add_parser("verify-bundle")
    verify.add_argument("--bundle", type=Path, required=True)

    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--commit", required=True)
    prepare_parser.add_argument("--output", type=Path, required=True)
    prepare_parser.add_argument("--repository", default=DEFAULT_REPOSITORY)
    prepare_parser.add_argument("--run-id")

    install_parser = subparsers.add_parser("install")
    install_parser.add_argument("--bundle", type=Path, required=True)
    install_parser.add_argument("--rollback-release", required=True)
    install_parser.add_argument("--confirm-install", required=True)
    install_parser.add_argument("--state-dir", type=Path)

    rollback_parser = subparsers.add_parser("rollback")
    rollback_parser.add_argument("--release", required=True)
    rollback_parser.add_argument("--confirm-rollback", required=True)
    rollback_parser.add_argument("--state-dir", type=Path)

    cycle_parser = subparsers.add_parser("cycle")
    cycle_parser.add_argument("--bundle", type=Path, required=True)
    cycle_parser.add_argument("--rollback-release", required=True)
    cycle_parser.add_argument("--confirm-cycle", required=True)
    cycle_parser.add_argument("--state-dir", type=Path)

    update_parser = subparsers.add_parser("update")
    update_parser.add_argument("--to", default=DEFAULT_UPDATE_REF)
    update_parser.add_argument("--plan", action="store_true")
    update_parser.add_argument("--confirm-update")
    update_parser.add_argument("--repository", default=DEFAULT_REPOSITORY)
    update_parser.add_argument("--cache-dir", type=Path)

    publish_parser = subparsers.add_parser("publish")
    publish_parser.add_argument("--bundle", type=Path, required=True)
    publish_parser.add_argument("--certification", type=Path, required=True)
    publish_parser.add_argument("--notes", type=Path, required=True)
    publish_parser.add_argument("--confirm-publish", required=True)
    publish_parser.add_argument("--repository", default=DEFAULT_REPOSITORY)
    publish_parser.add_argument("--state-dir", type=Path)
    return parser


def _emit(data: dict[str, object], compact: bool) -> None:
    print(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=None if compact else 2))


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.action == "inspect":
            result = inspect()
        elif args.action == "verify-bundle":
            result = {"ok": True, "bundle": load_bundle(args.bundle).public()}
        elif args.action == "prepare":
            bundle = prepare(
                commit=args.commit,
                output=args.output,
                repository=args.repository,
                run_id=args.run_id,
            )
            result = {"ok": True, "bundle": bundle.public()}
        elif args.action == "install":
            bundle = load_bundle(args.bundle)
            result = {
                "ok": True,
                "data": install(
                    bundle,
                    rollback_release=args.rollback_release,
                    confirmation=args.confirm_install,
                    state_dir=args.state_dir,
                ),
            }
        elif args.action == "rollback":
            result = {
                "ok": True,
                "data": rollback(
                    args.release,
                    confirmation=args.confirm_rollback,
                    state_dir=args.state_dir,
                ),
            }
        elif args.action == "cycle":
            bundle = load_bundle(args.bundle)
            result = {
                "ok": True,
                "data": cycle(
                    bundle,
                    rollback_release=args.rollback_release,
                    confirmation=args.confirm_cycle,
                    state_dir=args.state_dir,
                ),
            }
        elif args.action == "update":
            result = {
                "ok": True,
                "data": update(
                    to_ref=args.to,
                    confirmation=args.confirm_update,
                    plan_only=args.plan,
                    repository=args.repository,
                    cache_dir=args.cache_dir,
                    input_fn=input if sys.stdin.isatty() and not args.json else None,
                ),
            }
        else:
            bundle = load_bundle(args.bundle)
            result = {
                "ok": True,
                "data": publish(
                    bundle,
                    certification=args.certification,
                    notes=args.notes,
                    confirmation=args.confirm_publish,
                    repository=args.repository,
                    state_dir=args.state_dir,
                ),
            }
    except AutomationError as exc:
        _emit({"ok": False, "error": str(exc)}, args.json)
        return 1
    _emit(result, args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
