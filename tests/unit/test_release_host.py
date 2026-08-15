# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Automação de release/host sem publicar nem tocar no host real."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import subprocess
import zipfile
from collections.abc import Sequence
from dataclasses import replace
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
                "repository": release_host.DEFAULT_REPOSITORY,
                "runId": "42",
                "sourceCommit": commit,
                "sourceRef": "refs/heads/main",
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


def test_bundle_requires_ci_run_in_manifest_and_provenance(tmp_path: Path) -> None:
    root, _version, _commit = _bundle(tmp_path)
    manifest = root / "dist" / "runtime-wheelhouse" / "WHEELHOUSE-MANIFEST.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data.pop("githubRunId")
    manifest.write_text(json.dumps(data), encoding="utf-8")
    checksums = root / "build" / "SHA256SUMS"
    lines = checksums.read_text(encoding="utf-8").splitlines()
    checksums.write_text(
        "\n".join(
            f"{_sha256(manifest)}  dist/runtime-wheelhouse/WHEELHOUSE-MANIFEST.json"
            if line.endswith("dist/runtime-wheelhouse/WHEELHOUSE-MANIFEST.json")
            else line
            for line in lines
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(release_host.AutomationError, match="run de CI"):
        release_host.load_bundle(root)


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


def test_bundle_requires_checksummed_sbom_and_audit(tmp_path: Path) -> None:
    root, _version, _commit = _bundle(tmp_path)
    checksums = root / "build" / "SHA256SUMS"
    checksums.write_text(
        "\n".join(
            line
            for line in checksums.read_text(encoding="utf-8").splitlines()
            if not line.endswith("build/pip-audit.json")
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(release_host.AutomationError, match="cadeia de suprimentos"):
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


def test_candidate_update_ref_resolves_exact_remote_tip() -> None:
    commit = "a" * 40
    to_ref = "origin/codex/harmonize-ui-g45-release-candidate"
    source_ref = "refs/heads/codex/harmonize-ui-g45-release-candidate"
    remote_ref = "refs/remotes/origin/codex/harmonize-ui-g45-release-candidate"
    runner = _Runner(
        {
            ("git", "fetch", "origin", f"{source_ref}:{remote_ref}"): (0, "", ""),
            ("git", "rev-parse", f"{remote_ref}^{{commit}}"): (0, commit + "\n", ""),
            ("git", "rev-parse", "HEAD"): (0, commit + "\n", ""),
            ("git", "status", "--porcelain"): (0, "", ""),
        }
    )

    assert release_host._resolve_update_target(to_ref, runner=runner) == commit


@pytest.mark.parametrize(
    "to_ref",
    ["origin/feature/untrusted", "origin/codex/../main", "refs/heads/main"],
)
def test_candidate_update_ref_rejects_unscoped_or_unsafe_names(to_ref: str) -> None:
    with pytest.raises(release_host.AutomationError):
        release_host._source_ref_for_update(to_ref)


def test_ci_builds_push_artifact_for_explicit_release_candidates() -> None:
    workflow = (release_host.ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert 'branches: [main, "codex/*release-candidate*"]' in workflow


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


def test_cached_bundle_is_revalidated_against_current_green_ci(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fixture, _version, commit = _bundle(tmp_path)
    cache = tmp_path / "cache"
    shutil.copytree(fixture, cache / commit)
    runner = _PrepareRunner(fixture, commit)
    monkeypatch.setattr(release_host, "_require_cache_space", lambda *_args, **_kwargs: None)

    bundle = release_host._prepare_update_bundle(
        commit,
        cache_dir=cache,
        repository=release_host.DEFAULT_REPOSITORY,
        runner=runner,
    )

    assert bundle.commit == commit
    assert any(call[:3] == ("gh", "run", "list") for call in runner.calls)


def test_cached_bundle_rejects_manifest_from_another_repository(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fixture, _version, commit = _bundle(tmp_path)
    cache = tmp_path / "cache"
    shutil.copytree(fixture, cache / commit)
    manifest = cache / commit / "AUTOMATION-MANIFEST.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["repository"] = "attacker/fork"
    manifest.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(release_host, "_require_cache_space", lambda *_args, **_kwargs: None)

    with pytest.raises(release_host.AutomationError, match="diverge"):
        release_host._prepare_update_bundle(
            commit,
            cache_dir=cache,
            repository=release_host.DEFAULT_REPOSITORY,
            runner=_PrepareRunner(fixture, commit),
        )


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


def test_candidate_bundle_cannot_be_published_as_final_release(tmp_path: Path) -> None:
    root, _version, _commit = _bundle(tmp_path)
    bundle = replace(
        release_host.load_bundle(root),
        source_ref="refs/heads/codex/harmonize-ui-g45-release-candidate",
    )

    with pytest.raises(release_host.AutomationError, match="refs/heads/main"):
        release_host.publish(
            bundle,
            certification=tmp_path / "certification.json",
            notes=tmp_path / "notes.md",
            confirmation=f"PUBLICAR-v{bundle.version}",
            runner=_Runner({}),
        )


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


def _update_plan(bundle: release_host.Bundle) -> release_host.UpdatePlan:
    rollback = "0.1.0a41-bbbbbbbbbbbb"
    return release_host.UpdatePlan(
        current_release=rollback,
        target_release=bundle.release,
        source_commit=bundle.commit,
        rollback_release=rollback,
        run_id=bundle.run_id,
        wheel_sha256=bundle.wheel_sha256,
        data_schema_version=release_host.DATA_SCHEMA_VERSION,
        confirmation_token=f"ATUALIZAR-{rollback}-PARA-{bundle.release}",
    )


class _UpdateRunner:
    def __init__(
        self,
        *,
        target: str,
        rollback: str,
        fail_target_convergence: bool = False,
        fail_install: bool = False,
        fail_rollback: bool = False,
    ) -> None:
        self.target = target
        self.rollback = rollback
        self.current = rollback
        self.fail_target_convergence = fail_target_convergence
        self.fail_install = fail_install
        self.fail_rollback = fail_rollback
        self.calls: list[tuple[str, ...]] = []

    def __call__(
        self,
        argv: Sequence[str],
        _cwd: Path,
        _timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        call = tuple(argv)
        self.calls.append(call)
        if call[:3] == (
            "bigsudo",
            "/usr/bin/python3",
            str(release_host.ROOT / "tools" / "install_host.py"),
        ):
            action = call[3]
            if action == "install":
                if self.fail_install:
                    return subprocess.CompletedProcess(call, 1, "", "falha injetada")
                self.current = self.target
                return subprocess.CompletedProcess(call, 0, json.dumps({"ok": True}), "")
            if action == "rollback":
                if self.fail_rollback:
                    return subprocess.CompletedProcess(call, 1, "", "falha injetada")
                self.current = self.rollback
                return subprocess.CompletedProcess(call, 0, json.dumps({"ok": True}), "")
        if call[:3] == (str(release_host.HOST_MANAGER), "converge", "--expect-release"):
            if self.current == self.target and self.fail_target_convergence:
                return subprocess.CompletedProcess(call, 1, "", "timeout injetado")
            payload = {
                "ok": True,
                "data": {
                    "state": "converged",
                    "restarted": False,
                    "attempts": 0,
                    "daemonRelease": self.current,
                    "daemonCommit": "a" * 40,
                },
            }
            return subprocess.CompletedProcess(call, 0, json.dumps(payload), "")
        if call[:3] == ("systemctl", "--user", "stop"):
            return subprocess.CompletedProcess(call, 0, "", "")
        return subprocess.CompletedProcess(call, 127, "", f"inesperado: {call}")


def _patch_update_runtime(
    monkeypatch: pytest.MonkeyPatch,
    runner: _UpdateRunner,
) -> None:
    monkeypatch.setattr(
        release_host,
        "_read_host_truth",
        lambda _host_root=release_host.HOST_ROOT: {
            "installed": True,
            "ok": True,
            "release": runner.current,
            "sourceCommit": "a" * 40,
            "packageVersion": "0.1.0a42",
        },
    )
    monkeypatch.setattr(release_host, "_state_db_fingerprint", lambda: "stable-state")
    monkeypatch.setattr(
        release_host,
        "_activation_smokes",
        lambda active_release, **_kwargs: {
            "host": {"release": active_release},
            "doctor": {"ok": True},
            "gameMode": "ready",
            "qml": {"state": "started"},
        },
    )


def test_update_plan_requires_exact_token_before_privileged_call(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root, _version, commit = _bundle(tmp_path)
    bundle = release_host.load_bundle(root)
    runner = _Runner({})
    monkeypatch.setattr(release_host, "_resolve_update_target", lambda *_args, **_kwargs: commit)
    monkeypatch.setattr(release_host, "_prepare_update_bundle", lambda *_args, **_kwargs: bundle)
    monkeypatch.setattr(release_host, "_require_checkout", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(release_host, "_require_not_quarantined", lambda *_args: None)
    monkeypatch.setattr(
        release_host,
        "_host_preflight",
        lambda **_kwargs: {"release": "0.1.0a41-bbbbbbbbbbbb"},
    )

    with pytest.raises(release_host.AutomationError, match="confirmação inválida"):
        release_host.update(
            confirmation="sim",
            cache_dir=tmp_path / "cache",
            state_dir=tmp_path / "state",
            runner=runner,
        )

    assert not [call for call in runner.calls if call and call[0] == "bigsudo"]
    journal_path = next((tmp_path / "state" / "transactions").glob("*.json"))
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    assert journal["phase"] == "cancelled"


def test_update_plan_only_is_terminal_and_never_calls_bigsudo(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root, _version, commit = _bundle(tmp_path)
    bundle = release_host.load_bundle(root)
    runner = _Runner({})
    monkeypatch.setattr(release_host, "_resolve_update_target", lambda *_args, **_kwargs: commit)
    monkeypatch.setattr(release_host, "_prepare_update_bundle", lambda *_args, **_kwargs: bundle)
    monkeypatch.setattr(release_host, "_require_checkout", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(release_host, "_require_not_quarantined", lambda *_args: None)
    monkeypatch.setattr(
        release_host,
        "_host_preflight",
        lambda **_kwargs: {"release": "0.1.0a41-bbbbbbbbbbbb"},
    )

    result = release_host.update(
        plan_only=True,
        cache_dir=tmp_path / "cache",
        state_dir=tmp_path / "state",
        runner=runner,
    )

    assert result["plan"]["targetRelease"] == bundle.release
    assert result["physicalCertification"] is False
    assert not [call for call in runner.calls if call and call[0] == "bigsudo"]
    journal = json.loads(Path(result["journal"]).read_text(encoding="utf-8"))
    assert journal["phase"] == "planned"


def test_update_writes_discovery_before_bundle_download(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    commit = "a" * 40
    monkeypatch.setattr(release_host, "_resolve_update_target", lambda *_args, **_kwargs: commit)
    monkeypatch.setattr(
        release_host,
        "_read_host_truth",
        lambda _root: {"ok": True, "release": "0.1.0a41-bbbbbbbbbbbb"},
    )

    def interrupted(*_args: object, **_kwargs: object) -> release_host.Bundle:
        raise release_host.AutomationError("download interrompido")

    monkeypatch.setattr(release_host, "_prepare_update_bundle", interrupted)

    with pytest.raises(release_host.AutomationError, match="download interrompido"):
        release_host.update(
            plan_only=True,
            state_dir=tmp_path / "state",
            runner=_Runner({}),
        )

    journal_path = next((tmp_path / "state" / "transactions").glob("*.json"))
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    assert journal["phase"] == "discovered"
    assert journal["sourceCommit"] == commit


def test_update_transaction_commits_only_after_convergence_and_smokes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root, _version, _commit = _bundle(tmp_path)
    bundle = release_host.load_bundle(root)
    plan = _update_plan(bundle)
    runner = _UpdateRunner(target=bundle.release, rollback=plan.rollback_release)
    _patch_update_runtime(monkeypatch, runner)
    journal = release_host._new_update_journal(plan, state_dir=tmp_path / "state")

    result = release_host._execute_update_transaction(
        bundle,
        plan,
        journal,
        runner=runner,
        state_dir=tmp_path / "state",
    )

    phases = [event["phase"] for event in journal.document["events"]]
    assert phases == [
        "discovered",
        "bundle-verified",
        "preflight-passed",
        "approved",
        "install-started",
        "activated",
        "convergence-passed",
        "smokes-passed",
        "committed",
    ]
    assert result["deploymentHealthy"] is True
    assert result["physicalCertification"] is False
    assert runner.current == bundle.release


def test_failure_after_activation_rolls_back_and_quarantines_target(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root, _version, _commit = _bundle(tmp_path)
    bundle = release_host.load_bundle(root)
    plan = _update_plan(bundle)
    runner = _UpdateRunner(
        target=bundle.release,
        rollback=plan.rollback_release,
        fail_target_convergence=True,
    )
    _patch_update_runtime(monkeypatch, runner)
    journal = release_host._new_update_journal(plan, state_dir=tmp_path / "state")

    with pytest.raises(release_host.AutomationError, match="foi ativado e verificado"):
        release_host._execute_update_transaction(
            bundle,
            plan,
            journal,
            runner=runner,
            state_dir=tmp_path / "state",
        )

    assert runner.current == plan.rollback_release
    assert journal.phase == "failed-safe"
    quarantine = release_host._quarantine_path(bundle.release, tmp_path / "state")
    assert json.loads(quarantine.read_text(encoding="utf-8"))["state"] == "failed-verification"


def test_failure_before_activation_does_not_attempt_rollback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root, _version, _commit = _bundle(tmp_path)
    bundle = release_host.load_bundle(root)
    plan = _update_plan(bundle)
    runner = _UpdateRunner(
        target=bundle.release,
        rollback=plan.rollback_release,
        fail_install=True,
    )
    _patch_update_runtime(monkeypatch, runner)
    journal = release_host._new_update_journal(plan, state_dir=tmp_path / "state")

    with pytest.raises(release_host.AutomationError, match="instalação"):
        release_host._execute_update_transaction(
            bundle,
            plan,
            journal,
            runner=runner,
            state_dir=tmp_path / "state",
        )

    privileged_actions = [call[3] for call in runner.calls if call and call[0] == "bigsudo"]
    assert privileged_actions == ["install"]
    assert journal.phase == "failed-before-activation"


def test_install_failure_with_unreadable_current_rolls_back_defensively(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root, _version, _commit = _bundle(tmp_path)
    bundle = release_host.load_bundle(root)
    plan = _update_plan(bundle)
    runner = _UpdateRunner(
        target=bundle.release,
        rollback=plan.rollback_release,
        fail_install=True,
    )
    _patch_update_runtime(monkeypatch, runner)
    reads = iter(
        [
            {"ok": True, "release": plan.rollback_release},
            {"installed": True, "ok": False},
            {"installed": True, "ok": False},
        ]
    )
    monkeypatch.setattr(release_host, "_read_host_truth", lambda *_args: next(reads))
    journal = release_host._new_update_journal(plan, state_dir=tmp_path / "state")

    with pytest.raises(release_host.AutomationError, match="foi ativado e verificado"):
        release_host._execute_update_transaction(
            bundle,
            plan,
            journal,
            runner=runner,
            state_dir=tmp_path / "state",
        )

    privileged_actions = [call[3] for call in runner.calls if call and call[0] == "bigsudo"]
    assert privileged_actions == ["install", "rollback"]


def test_quarantine_write_failure_never_suppresses_verified_rollback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root, _version, _commit = _bundle(tmp_path)
    bundle = release_host.load_bundle(root)
    plan = _update_plan(bundle)
    runner = _UpdateRunner(
        target=bundle.release,
        rollback=plan.rollback_release,
        fail_target_convergence=True,
    )
    _patch_update_runtime(monkeypatch, runner)
    monkeypatch.setattr(
        release_host,
        "_mark_quarantined",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disco somente leitura")),
    )
    journal = release_host._new_update_journal(plan, state_dir=tmp_path / "state")

    with pytest.raises(release_host.AutomationError, match="evidência local ficou incompleta"):
        release_host._execute_update_transaction(
            bundle,
            plan,
            journal,
            runner=runner,
            state_dir=tmp_path / "state",
        )

    assert runner.current == plan.rollback_release
    privileged_actions = [call[3] for call in runner.calls if call and call[0] == "bigsudo"]
    assert privileged_actions == ["install", "rollback"]


def test_activated_journal_failure_rolls_back_instead_of_leaving_target_active(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root, _version, _commit = _bundle(tmp_path)
    bundle = release_host.load_bundle(root)
    plan = _update_plan(bundle)
    runner = _UpdateRunner(target=bundle.release, rollback=plan.rollback_release)
    _patch_update_runtime(monkeypatch, runner)
    journal = release_host._new_update_journal(plan, state_dir=tmp_path / "state")
    original_event = journal.event
    failed = False

    def event(phase: str, **kwargs: object) -> None:
        nonlocal failed
        if phase == "activated" and not failed:
            failed = True
            raise OSError("journal indisponível")
        original_event(phase, **kwargs)

    monkeypatch.setattr(journal, "event", event)

    with pytest.raises(release_host.AutomationError, match="foi ativado e verificado"):
        release_host._execute_update_transaction(
            bundle,
            plan,
            journal,
            runner=runner,
            state_dir=tmp_path / "state",
        )

    assert runner.current == plan.rollback_release


def test_rollback_failure_stops_units_and_records_critical_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root, _version, _commit = _bundle(tmp_path)
    bundle = release_host.load_bundle(root)
    plan = _update_plan(bundle)
    runner = _UpdateRunner(
        target=bundle.release,
        rollback=plan.rollback_release,
        fail_target_convergence=True,
        fail_rollback=True,
    )
    _patch_update_runtime(monkeypatch, runner)
    journal = release_host._new_update_journal(plan, state_dir=tmp_path / "state")

    with pytest.raises(release_host.AutomationError, match="ATENÇÃO"):
        release_host._execute_update_transaction(
            bundle,
            plan,
            journal,
            runner=runner,
            state_dir=tmp_path / "state",
        )

    stopped = [call[-1] for call in runner.calls if call[:3] == ("systemctl", "--user", "stop")]
    assert stopped == ["steamzero-core.service", "steamzero-core.socket"]
    assert journal.phase == "rollback-failed"


def test_resume_after_activation_verifies_without_reinstalling(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root, _version, _commit = _bundle(tmp_path)
    bundle = release_host.load_bundle(root)
    plan = _update_plan(bundle)
    runner = _UpdateRunner(target=bundle.release, rollback=plan.rollback_release)
    runner.current = bundle.release
    _patch_update_runtime(monkeypatch, runner)
    journal = release_host._new_update_journal(plan, state_dir=tmp_path / "state")
    journal.event(
        "approved",
        current_release=plan.rollback_release,
        data={"stateFingerprint": "stable-state"},
    )
    journal.event("install-started", current_release=plan.rollback_release)
    journal.event("activated", current_release=bundle.release)

    result = release_host._execute_update_transaction(
        bundle,
        plan,
        journal,
        runner=runner,
        state_dir=tmp_path / "state",
    )

    assert not [call for call in runner.calls if call and call[0] == "bigsudo"]
    assert result["activation"] == {"recovered": True}
    assert journal.phase == "committed"


def test_resume_after_rollback_verification_never_reactivates_failed_target(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root, _version, _commit = _bundle(tmp_path)
    bundle = release_host.load_bundle(root)
    plan = _update_plan(bundle)
    runner = _UpdateRunner(target=bundle.release, rollback=plan.rollback_release)
    _patch_update_runtime(monkeypatch, runner)
    journal = release_host._new_update_journal(plan, state_dir=tmp_path / "state")
    journal.event(
        "approved",
        current_release=plan.rollback_release,
        data={"stateFingerprint": "stable-state"},
    )
    journal.event("install-started", current_release=plan.rollback_release)
    journal.event("activated", current_release=bundle.release)
    journal.event(
        "rollback-required",
        current_release=bundle.release,
        data={"failedPhase": "convergence-passed"},
    )
    journal.event("rollback-started", current_release=bundle.release)
    journal.event("rollback-activated", current_release=plan.rollback_release)
    journal.event("rollback-verified", current_release=plan.rollback_release)

    with pytest.raises(release_host.AutomationError, match="foi ativado e verificado"):
        release_host._execute_update_transaction(
            bundle,
            plan,
            journal,
            runner=runner,
            state_dir=tmp_path / "state",
        )

    privileged_actions = [call[3] for call in runner.calls if call and call[0] == "bigsudo"]
    assert privileged_actions == ["rollback"]
    assert journal.phase == "failed-safe"


def test_transaction_journal_redacts_sensitive_event_fields(tmp_path: Path) -> None:
    root, _version, _commit = _bundle(tmp_path)
    bundle = release_host.load_bundle(root)
    journal = release_host._new_update_journal(_update_plan(bundle), state_dir=tmp_path / "state")

    journal.event(
        "cancelled",
        current_release="0.1.0a41-bbbbbbbbbbbb",
        data={
            "password": "never",
            "romPath": "/home/player/roms/game.iso",
            "detail": "/home/player/private",
            "errorType": "Expected",
        },
    )

    serialized = journal.path.read_text(encoding="utf-8")
    assert "never" not in serialized
    assert "game.iso" not in serialized
    assert "/home/player" not in serialized
    assert "<redacted>" in serialized


def test_global_update_lock_rejects_concurrent_transaction(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"

    with (
        release_host._update_lock(state_dir),
        pytest.raises(release_host.AutomationError, match="já está em andamento"),
        release_host._update_lock(state_dir),
    ):
        pytest.fail("lock concorrente não deveria ser adquirido")


def test_recovery_requires_fresh_exact_confirmation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root, _version, commit = _bundle(tmp_path)
    bundle = release_host.load_bundle(root)
    plan = _update_plan(bundle)
    cache = tmp_path / "cache"
    shutil.copytree(root, cache / commit)
    journal = release_host._new_update_journal(plan, state_dir=tmp_path / "state")
    journal.event(
        "approved",
        current_release=plan.rollback_release,
        data={"stateFingerprint": "stable-state"},
    )
    monkeypatch.setattr(release_host, "_require_checkout", lambda *_args, **_kwargs: None)
    runner = _Runner(
        {
            ("git", "rev-parse", "HEAD"): (0, commit + "\n", ""),
            ("git", "status", "--porcelain"): (0, "", ""),
        }
    )

    with pytest.raises(release_host.AutomationError, match="recuperação exige"):
        release_host.update(
            cache_dir=cache,
            state_dir=tmp_path / "state",
            runner=runner,
        )

    assert journal.phase == "approved"
    assert not [call for call in runner.calls if call and call[0] == "bigsudo"]


def test_plan_rejects_reinstalling_the_active_release(tmp_path: Path) -> None:
    root, _version, _commit = _bundle(tmp_path)
    bundle = release_host.load_bundle(root)

    with pytest.raises(release_host.AutomationError, match="já está ativa"):
        release_host._plan_update(bundle, {"release": bundle.release})


def test_quarantined_release_is_not_eligible_for_update(tmp_path: Path) -> None:
    release = "0.1.0a42-aaaaaaaaaaaa"
    release_host._mark_quarantined(
        release,
        source_commit="a" * 40,
        failed_phase="smokes-passed",
        state_dir=tmp_path,
    )

    with pytest.raises(release_host.AutomationError, match="quarentena"):
        release_host._require_not_quarantined(release, tmp_path)


def test_host_preflight_rejects_incompatible_data_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = "0.1.0a41-bbbbbbbbbbbb"
    monkeypatch.setattr(
        release_host,
        "_read_host_truth",
        lambda _root: {"ok": True, "release": release},
    )
    monkeypatch.setattr(
        release_host,
        "_installed_release_manifest",
        lambda _release, _root: {"release": _release},
    )
    active_cli = release_host.HOST_ROOT / "current" / "venv" / "bin" / "steamzero"
    runner = _Runner(
        {
            (str(active_cli), "doctor", "--json"): (
                0,
                json.dumps(
                    {
                        "ok": True,
                        "data": {
                            "schemaVersion": release_host.DATA_SCHEMA_VERSION + 1,
                            "pendingOperations": [],
                        },
                    }
                ),
                "",
            )
        }
    )

    with pytest.raises(release_host.AutomationError, match="compatível"):
        release_host._host_preflight(runner=runner, check_ownership=False)


def test_qml_smoke_accepts_only_alive_timeout() -> None:
    runner = _Runner({})
    runner.responses = {}

    def smoke_runner(
        argv: Sequence[str], cwd: Path, timeout: int
    ) -> subprocess.CompletedProcess[str]:
        runner.calls.append(tuple(argv))
        runner.cwds.append(cwd)
        assert timeout == 10
        return subprocess.CompletedProcess(argv, 124, "", "")

    result = release_host._qml_offscreen_smoke(
        "0.1.0a42-aaaaaaaaaaaa",
        runner=smoke_runner,
    )

    assert result["state"] == "started"
    assert "QT_QPA_PLATFORM=offscreen" in runner.calls[0]


def test_qml_smoke_rejects_premature_clean_exit() -> None:
    def smoke_runner(
        argv: Sequence[str], _cwd: Path, _timeout: int
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 0, "", "")

    with pytest.raises(release_host.AutomationError, match="não permaneceu ativo"):
        release_host._qml_offscreen_smoke(
            "0.1.0a42-aaaaaaaaaaaa",
            runner=smoke_runner,
        )


def test_state_db_fingerprint_includes_wal_commits(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    state_home = tmp_path / "state"
    database = state_home / "steamzero" / "state.db"
    database.parent.mkdir(parents=True)
    monkeypatch.setenv("XDG_STATE_HOME", str(state_home))
    connection = sqlite3.connect(database)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA wal_autocheckpoint=0")
        connection.execute("CREATE TABLE proof (value TEXT)")
        connection.commit()
        before = release_host._state_db_fingerprint()
        connection.execute("INSERT INTO proof VALUES ('wal-only-change')")
        connection.commit()
        assert (database.parent / "state.db-wal").is_file()

        after = release_host._state_db_fingerprint()
    finally:
        connection.close()

    assert before != after


def test_cache_space_preflight_rejects_low_disk(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    usage = type("Usage", (), {"free": 1})()
    monkeypatch.setattr(release_host.shutil, "disk_usage", lambda _path: usage)

    with pytest.raises(release_host.AutomationError, match="espaço livre insuficiente"):
        release_host._require_cache_space(tmp_path)


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
