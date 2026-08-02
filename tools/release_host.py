#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Orquestra promoção e ativação de release sem duplicar os gates canônicos.

O comando é deliberadamente conservador:

* ``inspect`` nunca muta o host;
* ``prepare`` aceita somente um run ``push`` verde do commit exato;
* ``install`` e ``rollback`` chamam exclusivamente ``tools/install_host.py``;
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
import subprocess
import tempfile
import time
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from email.parser import Parser
from pathlib import Path

from build_wheelhouse import validate as validate_wheelhouse

ROOT = Path(__file__).resolve().parent.parent
HOST_ROOT = Path("/opt/steamzero")
HOST_MANAGER = Path("/usr/local/sbin/steamzero-host")
DEFAULT_REPOSITORY = "Misael-art/SteamZero"
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

CommandRunner = Callable[
    [Sequence[str], Path, int],
    subprocess.CompletedProcess[str],
]


class AutomationError(RuntimeError):
    """Falha pública e acionável da automação."""


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

    def public(self) -> dict[str, object]:
        data = asdict(self)
        for key in ("root", "wheel", "requirements", "wheelhouse", "manifest"):
            data[key] = str(data[key])
        return data


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def _verify_checksums(root: Path) -> int:
    checksum_file = root / "build" / "SHA256SUMS"
    if not checksum_file.is_file():
        raise AutomationError("bundle sem build/SHA256SUMS")
    checked = 0
    for line in checksum_file.read_text(encoding="utf-8").splitlines():
        match = CHECKSUM_RE.fullmatch(line)
        if match is None:
            raise AutomationError(f"linha de checksum malformada: {line!r}")
        path = _safe_checksum_path(root, match.group("path"))
        if not path.is_file():
            raise AutomationError(f"arquivo declarado em SHA256SUMS ausente: {match.group('path')}")
        if _sha256(path) != match.group("digest"):
            raise AutomationError(f"hash diverge: {match.group('path')}")
        checked += 1
    if checked < 5:
        raise AutomationError(f"SHA256SUMS incompleto: somente {checked} entradas")
    return checked


def load_bundle(root: Path) -> Bundle:
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
    _verify_checksums(root)

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
    if not isinstance(source, dict) or source.get("ref") != "refs/heads/main":
        raise AutomationError("proveniência não pertence a refs/heads/main")
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
    if run_id and provenance_run_id and str(run_id) != str(provenance_run_id):
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
    runner: CommandRunner = _default_runner,
) -> Bundle:
    if COMMIT_RE.fullmatch(commit) is None:
        raise AutomationError("--commit exige SHA completo")
    _run(
        [
            "git",
            "fetch",
            "origin",
            "refs/heads/main:refs/remotes/origin/main",
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
    origin_main = _git(["rev-parse", "refs/remotes/origin/main"], runner)
    if origin_main != commit:
        raise AutomationError("prepare aceita somente o tip exato de origin/main")
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
        bundle = load_bundle(temporary)
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
            "release": bundle.release,
        }
        (temporary / "AUTOMATION-MANIFEST.json").write_text(
            json.dumps(automation_manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if output.exists():
            output.rmdir()
        temporary.replace(output)
        return load_bundle(output)
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
    first = _run(
        [str(HOST_MANAGER), "converge", "--expect-release", release],
        timeout=120,
        runner=runner,
        purpose=f"convergência {release}",
    )
    second = _run(
        [str(HOST_MANAGER), "converge", "--expect-release", release],
        timeout=120,
        runner=runner,
        purpose=f"idempotência {release}",
    )
    try:
        first_data = json.loads(first.stdout)
        second_data = json.loads(second.stdout)
    except json.JSONDecodeError as exc:
        raise AutomationError("steamzero-host converge devolveu JSON inválido") from exc
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
    return {"first": first_data, "idempotent": second_data}


def _convergence_report(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise AutomationError("convergência não devolveu objeto JSON")
    data = payload.get("data")
    report = data if isinstance(data, dict) else payload
    if not isinstance(report, dict):
        raise AutomationError("convergência sem relatório")
    return report


def _post_activation(
    release: str,
    *,
    runner: CommandRunner,
    expected_commit: str | None = None,
    expected_version: str | None = None,
) -> dict[str, object]:
    convergence = _converge(release, runner=runner)
    doctor = _run(
        ["steamzero", "doctor", "--json"],
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
    host = _read_host_truth()
    if host.get("release") != release:
        raise AutomationError(f"current permaneceu em {host.get('release')}, esperado {release}")
    if expected_commit is not None and host.get("sourceCommit") != expected_commit:
        raise AutomationError("manifesto ativo não contém o sourceCommit esperado")
    if expected_version is not None and host.get("packageVersion") != expected_version:
        raise AutomationError("manifesto ativo não contém a packageVersion esperada")
    try:
        doctor_data = json.loads(doctor.stdout)
    except json.JSONDecodeError as exc:
        raise AutomationError("doctor devolveu JSON inválido") from exc
    if not isinstance(doctor_data, dict) or doctor_data.get("ok") is not True:
        raise AutomationError("doctor pós-ativação não declarou ok=true")
    doctor_payload = doctor_data.get("data")
    doctor_summary: dict[str, object] = {
        "ok": True,
        "status": doctor_data.get("status"),
    }
    if isinstance(doctor_payload, dict):
        for key in ("schemaVersion", "pendingOperations", "version"):
            if key in doctor_payload:
                doctor_summary[key] = doctor_payload[key]
    return {
        "convergence": convergence,
        "doctor": doctor_summary,
        "socket": socket.stdout.strip(),
        "service": service.stdout.strip(),
        "host": host,
    }


def install(
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
    command = [
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
    ]
    activated = _run(
        command,
        timeout=1800,
        runner=runner,
        purpose=f"instalação {bundle.release}",
    )
    try:
        activation_data = json.loads(activated.stdout)
    except json.JSONDecodeError as exc:
        raise AutomationError("install_host devolveu JSON inválido") from exc
    if not isinstance(activation_data, dict) or activation_data.get("ok") is not True:
        raise AutomationError("install_host não declarou ok=true")
    verified = _post_activation(
        bundle.release,
        runner=runner,
        expected_commit=bundle.commit,
        expected_version=bundle.version,
    )
    result = {
        "release": bundle.release,
        "sourceCommit": bundle.commit,
        "rollbackRelease": rollback_release,
        "activation": activation_data,
        "verification": verified,
    }
    evidence = _record(bundle.release, "install", result, state_dir=state_dir)
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
    expected = f"REVERTER-{release}"
    if confirmation != expected:
        raise AutomationError(f"confirmação inválida; esperado --confirm-rollback {expected}")
    _require_rollback(release)
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
    try:
        activation_data = json.loads(activated.stdout)
    except json.JSONDecodeError as exc:
        raise AutomationError("install_host rollback devolveu JSON inválido") from exc
    if not isinstance(activation_data, dict) or activation_data.get("ok") is not True:
        raise AutomationError("install_host rollback não declarou ok=true")
    verified = _post_activation(release, runner=runner)
    result = {"release": release, "activation": activation_data, "verification": verified}
    evidence_release = state_release or release
    evidence = _record(evidence_release, "rollback", result, state_dir=state_dir)
    result["evidence"] = str(evidence)
    return result


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
    target = install(
        bundle,
        rollback_release=rollback_release,
        confirmation=f"INSTALAR-{bundle.release}",
        runner=runner,
        state_dir=state_dir,
    )
    previous = rollback(
        rollback_release,
        confirmation=f"REVERTER-{rollback_release}",
        runner=runner,
        state_release=bundle.release,
        state_dir=state_dir,
    )
    restored = install(
        bundle,
        rollback_release=rollback_release,
        confirmation=f"INSTALAR-{bundle.release}",
        runner=runner,
        state_dir=state_dir,
    )
    result = {
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
    result = {
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
