# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Identidade de runtime: carregada no build, nunca consultada em disco.

Estes testes não constroem wheel nem tocam o host (AGENTS.md §4). Exercitam as
funções do hook e do módulo de identidade diretamente.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from steamzero.core.identity import (
    UNKNOWN_COMMIT,
    RuntimeIdentity,
    runtime_identity,
)

_A37 = "2aaa01d9d8b638b3d8e8c396ffbeed133da50ec2"
_A35 = "7a1916e1e711bbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def _identity(version: str, commit: str, dirty: bool = False) -> RuntimeIdentity:
    return RuntimeIdentity(
        package_version=version,
        source_commit=commit,
        source_dirty=dirty,
        release_id=f"{version}-{commit[:12]}" if commit != UNKNOWN_COMMIT else "",
    )


class TestIdentityMatching:
    def test_same_generation_matches(self) -> None:
        a = _identity("0.1.0a37", _A37)
        assert a.matches(_identity("0.1.0a37", _A37))

    def test_a37_scenario_does_not_match(self) -> None:
        """Reprodução do incidente: daemon a35 sob release a37."""
        daemon = _identity("0.1.0a35", _A35)
        release = _identity("0.1.0a37", _A37)
        assert not release.matches(daemon)
        assert not daemon.matches(release)

    def test_same_version_different_commit_does_not_match(self) -> None:
        """Duas builds da mesma versão a partir de commits diferentes."""
        a = _identity("0.1.0a37", _A37)
        b = _identity("0.1.0a37", _A35)
        assert not a.matches(b)

    def test_unknown_never_matches_even_itself(self) -> None:
        """Identidade desconhecida não é identidade compatível.

        Assumir compatibilidade sem prova é exatamente o erro da a37.
        """
        unknown = _identity("0.1.0a37", UNKNOWN_COMMIT)
        assert unknown.known is False
        assert not unknown.matches(unknown)

    def test_empty_commit_is_not_known(self) -> None:
        assert _identity("0.1.0a37", "").known is False

    def test_known_identity_reports_release_id(self) -> None:
        assert _identity("0.1.0a37", _A37).release_id == "0.1.0a37-2aaa01d9d8b6"


class TestIdentityPayload:
    def test_payload_exposes_the_three_fields_the_preflight_compares(self) -> None:
        payload = _identity("0.1.0a37", _A37).to_dict()
        for field in ("packageVersion", "releaseId", "sourceCommit"):
            assert payload[field], f"{field} precisa estar presente e não vazio"

    def test_dirty_tree_is_visible_in_payload(self) -> None:
        assert _identity("0.1.0a37", _A37, dirty=True).to_dict()["sourceDirty"] is True


class TestDevTreeFallback:
    def test_without_build_info_identity_degrades_not_raises(self) -> None:
        """Árvore de desenvolvimento não tem _build_info; o núcleo segue usável."""
        identity = runtime_identity()
        assert identity.package_version
        if not identity.known:
            assert identity.source_commit == UNKNOWN_COMMIT
            assert identity.release_id == ""


class TestBuildHook:
    """O hook grava a origem; nenhum wheel é construído aqui."""

    def _hook(self):  # type: ignore[no-untyped-def]
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        import hatch_build

        return hatch_build

    def test_render_emits_importable_module(self, tmp_path: Path) -> None:
        hook = self._hook()
        target = tmp_path / "_build_info.py"
        target.write_text(hook.render(_A37, False), encoding="utf-8")
        namespace: dict[str, object] = {}
        exec(compile(target.read_text(), str(target), "exec"), namespace)  # noqa: S102
        assert namespace["SOURCE_COMMIT"] == _A37
        assert namespace["SOURCE_DIRTY"] is False

    def test_render_is_deterministic(self) -> None:
        """Mesmo commit gera os mesmos bytes: builds byte-idênticos preservados."""
        hook = self._hook()
        assert hook.render(_A37, False) == hook.render(_A37, False)

    def test_render_exposes_only_commit_and_dirty(self) -> None:
        """Só hash e flag.

        Qualquer outro dado injetado — timestamp, caminho de build, hostname —
        faria dois builds do mesmo commit divergirem byte a byte e quebraria a
        conferência de builds idênticos do fluxo de release.
        """
        import ast

        hook = self._hook()
        module = ast.parse(hook.render(_A37, True))
        assigned = {
            target.id
            for node in module.body
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        assert assigned == {"SOURCE_COMMIT", "SOURCE_DIRTY"}, (
            f"o módulo gravado só pode declarar origem, mas declara {assigned}"
        )
        # Os valores precisam ser literais: nada calculado em tempo de import.
        for node in module.body:
            if isinstance(node, ast.Assign):
                assert isinstance(node.value, ast.Constant), (
                    "valor de origem precisa ser literal, não expressão avaliada"
                )

    def test_resolve_source_without_git_returns_unknown(self, tmp_path: Path) -> None:
        hook = self._hook()
        commit, dirty = hook.resolve_source(tmp_path)
        assert commit == UNKNOWN_COMMIT
        assert dirty is False

    def test_resolve_source_reads_real_repository(self, tmp_path: Path) -> None:
        hook = self._hook()
        repo = tmp_path / "repo"
        repo.mkdir()

        def git(*args: str) -> None:
            subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, timeout=30)

        git("init", "-q")
        git("config", "user.email", "t@example.invalid")
        git("config", "user.name", "T")
        (repo / "a.txt").write_text("um")
        git("add", "a.txt")
        git("commit", "-q", "-m", "primeiro")

        commit, dirty = hook.resolve_source(repo)
        assert len(commit) == 40
        assert dirty is False

        (repo / "a.txt").write_text("dois")
        _commit, dirty_after = hook.resolve_source(repo)
        assert dirty_after is True, "árvore alterada precisa ser reportada como suja"

    def test_write_build_info_creates_expected_module(self, tmp_path: Path) -> None:
        hook = self._hook()
        written = hook.write_build_info(tmp_path)
        assert written.exists()
        assert written.name == "_build_info.py"
        assert "SOURCE_COMMIT" in written.read_text(encoding="utf-8")


class TestPackagingDeclaresProvenance:
    """Guarda contra remover silenciosamente a injeção de origem."""

    def _pyproject(self) -> str:
        root = Path(__file__).resolve().parents[2]
        return (root / "pyproject.toml").read_text(encoding="utf-8")

    def test_build_hook_is_wired(self) -> None:
        text = self._pyproject()
        assert 'path = "hatch_build.py"' in text

    def test_generated_module_is_declared_as_artifact(self) -> None:
        """Sem isto o hatchling excluiria o arquivo do wheel por respeitar o
        .gitignore, e o pacote instalado ficaria sem identidade — falhando de
        volta para 'unknown' silenciosamente."""
        assert 'artifacts = ["src/steamzero/_build_info.py"]' in self._pyproject()

    def test_backend_path_is_not_set(self) -> None:
        """backend-path restringe onde o backend é procurado e quebrou o build:
        'Cannot find module hatchling.build'. O hook não precisa dele."""
        assert "backend-path" not in self._pyproject()


class TestGeneratedModuleIsNotCommitted:
    def test_build_info_is_ignored_by_git(self) -> None:
        """A origem vem do git no build, nunca de um arquivo versionado."""
        root = Path(__file__).resolve().parents[2]
        assert "src/steamzero/_build_info.py" in (root / ".gitignore").read_text()

    def test_build_info_is_absent_from_the_tree(self) -> None:
        root = Path(__file__).resolve().parents[2]
        tracked = subprocess.run(
            ["git", "ls-files", "src/steamzero/_build_info.py"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert tracked.stdout.strip() == "", "_build_info.py não pode ser versionado"


@pytest.mark.parametrize("field", ["packageVersion", "releaseId", "sourceCommit"])
def test_preflight_rejects_missing_identity_field(field: str) -> None:
    """O preflight já reprova campo vazio, então 'unknown' não vira brecha."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    from release_preflight import Report, check_identity_coherence

    same = {"packageVersion": "0.1.0a37", "releaseId": "0.1.0a37-2aaa", "sourceCommit": _A37}
    identity: dict[str, object] = {
        "manifest": dict(same),
        "daemon": {**same, field: ""},
        "doctor": dict(same),
    }
    report = Report()
    check_identity_coherence(identity, report)
    assert not report.ok


class TestBuildInfoIsRead:
    """Caminho em que o módulo gravado pelo build EXISTE."""

    def _with_build_info(self, monkeypatch: pytest.MonkeyPatch, commit: str, dirty: bool) -> None:
        import types

        module = types.ModuleType("steamzero._build_info")
        module.SOURCE_COMMIT = commit  # type: ignore[attr-defined]
        module.SOURCE_DIRTY = dirty  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "steamzero._build_info", module)

    def test_identity_uses_injected_commit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._with_build_info(monkeypatch, _A37, False)
        identity = runtime_identity()
        assert identity.source_commit == _A37
        assert identity.source_dirty is False
        assert identity.known is True
        assert identity.release_id == "0.1.0a37-2aaa01d9d8b6"

    def test_dirty_flag_is_propagated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._with_build_info(monkeypatch, _A37, True)
        assert runtime_identity().source_dirty is True

    def test_empty_commit_in_module_degrades_to_unknown(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._with_build_info(monkeypatch, "", False)
        identity = runtime_identity()
        assert identity.source_commit == UNKNOWN_COMMIT
        assert identity.known is False

    def test_short_commit_yields_no_release_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Hash truncado não deriva releaseId: melhor vazio que id inventado."""
        self._with_build_info(monkeypatch, "abc123", False)
        assert runtime_identity().release_id == ""
