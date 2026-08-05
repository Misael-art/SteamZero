# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Automação de release/host sem publicar nem tocar no host real."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import zipfile
from collections.abc import Sequence
from pathlib import Path

import pytest

import release_host


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _wheel(path: Path, version: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            f"steamzero-{version}.dist-info/METADATA",
            f"Metadata-Version: 2.4\nName: steamzero\nVersion: {version}\n",
        )


def _bundle(tmp_path: Path) -> tuple[Path, str, str]:
    root = tmp_path / "bundle"
    dist = root / "dist"
    wheelhouse = dist / "runtime-wheelhouse"
    build = root / "build"
    wheelhouse.mkdir(parents=True)
    build.mkdir()
    version = "0.1.0a42"
    commit = "a" * 40
    wheel = dist / f"steamzero-{version}-py3-none-any.whl"
    _wheel(wheel, version)
    dependency = wheelhouse / "attrs-26.1.0-py3-none-any.whl"
    dependency.write_bytes(b"dependency")
    lock = root / "requirements-runtime.lock"
    lock.write_text("attrs==26.1.0\n", encoding="utf-8")
    manifest = {
        "schemaVersion": 1,
        "sourceCommit": commit,
        "sourceTreeState": "clean",
        "packageVersion": version,
        "requirementsLockSha256": _sha256(lock),
        "requirementsLockFile": lock.name,
        "dependencies": [
            {
                "filename": dependency.name,
                "sha256": _sha256(dependency),
                "size": dependency.stat().st_size,
                "nameParsed": True,
            }
        ],
        "dependencyCount": 1,
        "wheel": {
            "filename": wheel.name,
            "sha256": _sha256(wheel),
            "size": wheel.stat().st_size,
            "nameParsed": True,
        },
        "githubRunId": "42",
    }
    manifest_path = wheelhouse / "WHEELHOUSE-MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    provenance = {
        "schemaVersion": 1,
        "build": {"runId": "42", "sourceTreeState": "clean"},
        "source": {"commit": commit, "ref": "refs/heads/main"},
        "subject": {"name": wheel.name, "sha256": _sha256(wheel), "version": version},
    }
    provenance_path = build / "provenance.json"
    provenance_path.write_text(json.dumps(provenance), encoding="utf-8")
    sbom = build / "sbom.cdx.json"
    sbom.write_text("{}\n", encoding="utf-8")
    audit = build / "pip-audit.json"
    audit.write_text("{}\n", encoding="utf-8")
    archive = dist / "runtime-wheelhouse.tar.zst"
    archive.write_bytes(b"archive")
    checksummed = [wheel, sbom, provenance_path, archive, manifest_path, audit]
    (build / "SHA256SUMS").write_text(
        "".join(f"{_sha256(path)}  {path.relative_to(root)}\n" for path in checksummed),
        encoding="utf-8",
    )
    (root / "AUTOMATION-MANIFEST.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "runId": "42",
                "sourceCommit": commit,
                "release": f"{version}-{commit[:12]}",
            }
        ),
        encoding="utf-8",
    )
    return root, version, commit


def test_valid_bundle_binds_version_commit_and_run(tmp_path: Path) -> None:
    root, version, commit = _bundle(tmp_path)

    bundle = release_host.load_bundle(root)

    assert bundle.version == version
    assert bundle.commit == commit
    assert bundle.release == f"{version}-{commit[:12]}"
    assert bundle.run_id == "42"


def test_package_version_reads_the_real_source() -> None:
    """O parse por regex precisa concordar com o import — não é tautologia.

    ``_package_version`` lê ``__init__.py`` por expressão regular, sem importar
    o pacote; comparar com ``steamzero.__version__`` cruza dois caminhos
    independentes até a mesma verdade. Antes o valor era cravado no teste, o que
    exigia editá-lo a cada bump e não provava nada além do literal.
    """
    import steamzero

    assert release_host._package_version() == steamzero.__version__


def test_bundle_rejects_tampered_wheel(tmp_path: Path) -> None:
    root, _version, _commit = _bundle(tmp_path)
    wheel = next((root / "dist").glob("steamzero-*.whl"))
    wheel.write_bytes(wheel.read_bytes() + b"tampered")

    with pytest.raises(release_host.AutomationError, match="wheelhouse reprovado"):
        release_host.load_bundle(root)


def test_bundle_rejects_provenance_from_other_commit(tmp_path: Path) -> None:
    root, _version, _commit = _bundle(tmp_path)
    path = root / "build" / "provenance.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["source"]["commit"] = "b" * 40
    path.write_text(json.dumps(data), encoding="utf-8")
    checksum = root / "build" / "SHA256SUMS"
    checksum.write_text(
        checksum.read_text(encoding="utf-8").replace(
            next(
                line.split("  ")[0]
                for line in checksum.read_text(encoding="utf-8").splitlines()
                if line.endswith("build/provenance.json")
            ),
            _sha256(path),
        ),
        encoding="utf-8",
    )

    with pytest.raises(release_host.AutomationError, match="commit diverge"):
        release_host.load_bundle(root)


def test_checksum_cannot_escape_bundle(tmp_path: Path) -> None:
    root, _version, _commit = _bundle(tmp_path)
    checksums = root / "build" / "SHA256SUMS"
    checksums.write_text(f"{'0' * 64}  ../outside\n", encoding="utf-8")

    with pytest.raises(release_host.AutomationError, match="sair do bundle"):
        release_host.load_bundle(root)


def test_bundle_rejects_symlink_even_when_target_exists(tmp_path: Path) -> None:
    root, _version, _commit = _bundle(tmp_path)
    target = root / "build" / "external.json"
    target.write_text("{}\n", encoding="utf-8")
    link = root / "build" / "link.json"
    link.symlink_to(target)

    with pytest.raises(release_host.AutomationError, match="symlink"):
        release_host.load_bundle(root)


@pytest.mark.parametrize(
    "listing",
    [
        "",
        "../escape\n",
        "/absolute\n",
        "runtime-wheelhouse/../../escape\n",
        "other/file.whl\n",
    ],
)
def test_archive_listing_rejects_empty_traversal_and_foreign_roots(listing: str) -> None:
    with pytest.raises(release_host.AutomationError):
        release_host._validate_archive_listing(listing)


def test_archive_listing_accepts_only_the_wheelhouse_tree() -> None:
    release_host._validate_archive_listing(
        "runtime-wheelhouse/\nruntime-wheelhouse/dependency.whl\n"
    )


class _Runner:
    def __init__(self, responses: dict[tuple[str, ...], tuple[int, str, str]]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, ...]] = []
        self.cwds: list[Path] = []

    def __call__(
        self,
        argv: Sequence[str],
        cwd: Path,
        _timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        call = tuple(argv)
        self.calls.append(call)
        self.cwds.append(cwd)
        returncode, stdout, stderr = self.responses.get(call, (0, "", ""))
        return subprocess.CompletedProcess(call, returncode, stdout, stderr)


class _PrepareRunner:
    def __init__(self, fixture: Path, commit: str) -> None:
        self.fixture = fixture
        self.commit = commit
        self.calls: list[tuple[str, ...]] = []

    def __call__(
        self,
        argv: Sequence[str],
        _cwd: Path,
        _timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        call = tuple(argv)
        self.calls.append(call)
        if call == (
            "git",
            "fetch",
            "origin",
            "refs/heads/main:refs/remotes/origin/main",
        ):
            return subprocess.CompletedProcess(call, 0, "", "")
        if call == ("git", "rev-parse", "HEAD"):
            return subprocess.CompletedProcess(call, 0, self.commit + "\n", "")
        if call == ("git", "status", "--porcelain"):
            return subprocess.CompletedProcess(call, 0, "", "")
        if call == ("git", "rev-parse", "refs/remotes/origin/main"):
            return subprocess.CompletedProcess(call, 0, self.commit + "\n", "")
        if call[:4] == ("gh", "auth", "status", "-h"):
            return subprocess.CompletedProcess(call, 0, "", "")
        if call[:3] == ("gh", "run", "list"):
            payload = [
                {
                    "databaseId": 42,
                    "headSha": self.commit,
                    "status": "completed",
                    "conclusion": "success",
                    "event": "push",
                    "url": "https://example.invalid/run/42",
                }
            ]
            return subprocess.CompletedProcess(call, 0, json.dumps(payload), "")
        if call[:3] == ("gh", "run", "download"):
            destination = Path(call[call.index("--dir") + 1])
            shutil.copytree(self.fixture, destination, dirs_exist_ok=True)
            return subprocess.CompletedProcess(call, 0, "", "")
        if call[:3] == ("tar", "--zstd", "-tf"):
            return subprocess.CompletedProcess(
                call,
                0,
                "runtime-wheelhouse/\nruntime-wheelhouse/attrs.whl\n",
                "",
            )
        if call[:3] == ("tar", "--zstd", "--no-same-owner"):
            return subprocess.CompletedProcess(call, 0, "", "")
        return subprocess.CompletedProcess(call, 127, "", f"inesperado: {call}")


def test_prepare_downloads_exact_run_and_publishes_directory_atomically(tmp_path: Path) -> None:
    fixture, _version, commit = _bundle(tmp_path)
    output = tmp_path / "artifacts" / "a42"
    runner = _PrepareRunner(fixture, commit)

    bundle = release_host.prepare(commit=commit, output=output, runner=runner)

    assert bundle.root == output
    automation = json.loads((output / "AUTOMATION-MANIFEST.json").read_text(encoding="utf-8"))
    assert automation["runId"] == "42"
    assert automation["sourceCommit"] == commit
    assert not list(output.parent.glob(f".{output.name}.*"))


def test_discover_run_accepts_only_exact_successful_push() -> None:
    commit = "a" * 40
    command = (
        "gh",
        "run",
        "list",
        "--repo",
        release_host.DEFAULT_REPOSITORY,
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
    )
    runner = _Runner(
        {
            command: (
                0,
                json.dumps(
                    [
                        {
                            "databaseId": 42,
                            "headSha": commit,
                            "status": "completed",
                            "conclusion": "success",
                            "event": "push",
                            "url": "https://example.invalid/run/42",
                        },
                        {
                            "databaseId": 41,
                            "headSha": "b" * 40,
                            "status": "completed",
                            "conclusion": "success",
                            "event": "push",
                        },
                    ]
                ),
                "",
            )
        }
    )

    run = release_host._discover_run(commit, release_host.DEFAULT_REPOSITORY, runner=runner)

    assert run["databaseId"] == 42


def test_discover_run_rejects_ambiguous_successes() -> None:
    commit = "a" * 40
    payload = [
        {
            "databaseId": value,
            "headSha": commit,
            "status": "completed",
            "conclusion": "success",
            "event": "push",
        }
        for value in (41, 42)
    ]
    runner = _Runner({})
    runner.responses[
        (
            "gh",
            "run",
            "list",
            "--repo",
            release_host.DEFAULT_REPOSITORY,
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
        )
    ] = (0, json.dumps(payload), "")

    with pytest.raises(release_host.AutomationError, match="exatamente um"):
        release_host._discover_run(commit, release_host.DEFAULT_REPOSITORY, runner=runner)


def test_install_wrong_confirmation_never_calls_bigsudo(tmp_path: Path) -> None:
    root, _version, _commit = _bundle(tmp_path)
    bundle = release_host.load_bundle(root)
    runner = _Runner({})

    with pytest.raises(release_host.AutomationError, match="confirmação inválida"):
        release_host.install(
            bundle,
            rollback_release="0.1.0a41-bbbbbbbbbbbb",
            confirmation="sim",
            runner=runner,
        )

    assert not runner.calls


def test_install_calls_only_versioned_installer_for_privilege(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root, _version, _commit = _bundle(tmp_path)
    bundle = release_host.load_bundle(root)
    rollback_release = "0.1.0a41-bbbbbbbbbbbb"
    monkeypatch.setattr(release_host, "_require_checkout", lambda _bundle, _runner: None)
    monkeypatch.setattr(release_host, "_require_rollback", lambda _release: None)
    monkeypatch.setattr(
        release_host,
        "_post_activation",
        lambda _release, **_kwargs: {"host": {"release": _release}},
    )
    privileged = (
        "bigsudo",
        "/usr/bin/python3",
        str(release_host.ROOT / "tools" / "install_host.py"),
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
    )
    runner = _Runner({privileged: (0, json.dumps({"ok": True}), "")})

    result = release_host.install(
        bundle,
        rollback_release=rollback_release,
        confirmation=f"INSTALAR-{bundle.release}",
        runner=runner,
        state_dir=tmp_path / "state",
    )

    assert [call for call in runner.calls if "bigsudo" in call] == [privileged]
    assert runner.cwds[runner.calls.index(privileged)] == release_host.ROOT
    assert result["verification"]["host"]["release"] == bundle.release


def test_rollback_calls_only_versioned_installer_for_privilege(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    release = "0.1.0a41-bbbbbbbbbbbb"
    monkeypatch.setattr(release_host, "_require_rollback", lambda _release: None)
    monkeypatch.setattr(
        release_host,
        "_post_activation",
        lambda _release, **_kwargs: {"host": {"release": _release}},
    )
    runner = _Runner(
        {
            (
                "bigsudo",
                "/usr/bin/python3",
                str(release_host.ROOT / "tools" / "install_host.py"),
                "rollback",
                "--release",
                release,
            ): (0, json.dumps({"ok": True}), "")
        }
    )

    result = release_host.rollback(
        release,
        confirmation=f"REVERTER-{release}",
        runner=runner,
        state_dir=tmp_path / "state",
    )

    privileged = [call for call in runner.calls if "bigsudo" in call]
    assert privileged == [
        (
            "bigsudo",
            "/usr/bin/python3",
            str(release_host.ROOT / "tools" / "install_host.py"),
            "rollback",
            "--release",
            release,
        )
    ]
    assert result["verification"]["host"]["release"] == release


def test_cycle_wrong_token_stops_before_any_phase(tmp_path: Path) -> None:
    root, _version, _commit = _bundle(tmp_path)
    bundle = release_host.load_bundle(root)
    runner = _Runner({})

    with pytest.raises(release_host.AutomationError, match="confirmação inválida"):
        release_host.cycle(
            bundle,
            rollback_release="0.1.0a41-bbbbbbbbbbbb",
            confirmation="errado",
            runner=runner,
        )

    assert not runner.calls


def test_certification_requires_every_declared_gate(tmp_path: Path) -> None:
    root, _version, _commit = _bundle(tmp_path)
    bundle = release_host.load_bundle(root)
    path = tmp_path / "certification.json"
    path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "release": bundle.release,
                "sourceCommit": bundle.commit,
                "verdict": "approved",
                "requiredGates": {"machineCycle": True, "physicalUi": False},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(release_host.AutomationError, match="requiredGates"):
        release_host._load_certification(path, bundle)


def test_certification_rejects_omitting_a_required_physical_gate(tmp_path: Path) -> None:
    root, _version, _commit = _bundle(tmp_path)
    bundle = release_host.load_bundle(root)
    path = tmp_path / "certification.json"
    path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "release": bundle.release,
                "sourceCommit": bundle.commit,
                "verdict": "approved",
                "requiredGates": {"machineCycle": True},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(release_host.AutomationError, match="requiredGates"):
        release_host._load_certification(path, bundle)


def test_release_asset_state_requires_every_name_and_digest(tmp_path: Path) -> None:
    root, _version, _commit = _bundle(tmp_path)
    bundle = release_host.load_bundle(root)
    certification = tmp_path / "certification.json"
    certification.write_text("{}\n", encoding="utf-8")
    assets = release_host._release_assets(bundle, certification)
    present = assets[:-1]
    release_data = {
        "assets": [{"name": path.name, "digest": f"sha256:{_sha256(path)}"} for path in present]
    }

    missing, problems = release_host._release_asset_state(release_data, assets)

    assert missing == [certification]
    assert not problems


def test_release_assets_reject_automation_manifest_from_other_commit(tmp_path: Path) -> None:
    root, _version, _commit = _bundle(tmp_path)
    bundle = release_host.load_bundle(root)
    manifest = root / "AUTOMATION-MANIFEST.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["sourceCommit"] = "b" * 40
    manifest.write_text(json.dumps(data), encoding="utf-8")
    certification = tmp_path / "certification.json"
    certification.write_text("{}\n", encoding="utf-8")

    with pytest.raises(release_host.AutomationError, match="diverge"):
        release_host._release_assets(bundle, certification)


def test_release_asset_state_rejects_remote_digest_drift(tmp_path: Path) -> None:
    root, _version, _commit = _bundle(tmp_path)
    bundle = release_host.load_bundle(root)
    certification = tmp_path / "certification.json"
    certification.write_text("{}\n", encoding="utf-8")
    assets = release_host._release_assets(bundle, certification)
    release_data = {
        "assets": [{"name": path.name, "digest": f"sha256:{_sha256(path)}"} for path in assets]
    }
    release_data["assets"][0]["digest"] = f"sha256:{'0' * 64}"

    missing, problems = release_host._release_asset_state(release_data, assets)

    assert not missing
    assert bundle.wheel.name in problems[0]


def test_state_log_appends_atomically(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    release = "0.1.0a42-aaaaaaaaaaaa"

    path = release_host._record(release, "install", {"ok": True}, state_dir=state_dir)
    release_host._record(release, "cycle", {"ok": True}, state_dir=state_dir)

    document = json.loads(path.read_text(encoding="utf-8"))
    assert [event["phase"] for event in document["events"]] == ["install", "cycle"]
    assert not path.with_suffix(".tmp").exists()


def test_state_log_refuses_to_overwrite_corruption(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    release = "0.1.0a42-aaaaaaaaaaaa"
    path = state_dir / f"{release}.json"
    path.write_text("{broken", encoding="utf-8")

    with pytest.raises(release_host.AutomationError, match="state existente ilegível"):
        release_host._record(release, "install", {"ok": True}, state_dir=state_dir)

    assert path.read_text(encoding="utf-8") == "{broken"


@pytest.mark.parametrize(
    ("second", "message"),
    [
        ({"state": "converged", "restarted": True, "attempts": 1}, "idempotente"),
        ({"state": "pending", "restarted": False, "attempts": 0}, "não convergiu"),
    ],
)
def test_second_convergence_must_be_converged_without_restart(
    second: dict[str, object],
    message: str,
) -> None:
    release = "0.1.0a42-aaaaaaaaaaaa"
    command = (str(release_host.HOST_MANAGER), "converge", "--expect-release", release)
    runner = _Runner(
        {
            command: (
                0,
                json.dumps({"ok": True, "data": second}),
                "",
            )
        }
    )

    with pytest.raises(release_host.AutomationError, match=message):
        release_host._converge(release, runner=runner)


def test_source_has_no_privileged_escape_hatch() -> None:
    source = (release_host.ROOT / "tools" / "release_host.py").read_text(encoding="utf-8")

    assert source.count('"bigsudo"') == 2
    assert source.count('"tools" / "install_host.py"') == 2
    assert source.count('"tools/install_host.py"') == 0
    assert '"sudo"' not in source
