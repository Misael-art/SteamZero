# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Regressões do isolamento HOME + XDG que fecha GAP-G26."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

import run_tests_isolated
from run_tests_isolated import (
    _STATE_CHANGE_EXIT,
    _TEST_ROOT_ENV,
    _XDG_LAYOUT,
    ForeignWriter,
    changed_entries,
    isolated_environment,
    resolve_real_state_home,
    snapshot_state,
)

_XDG_LAYOUT_VARS = tuple(_XDG_LAYOUT)


def test_autouse_fixture_isolates_all_xdg_homes(isolated_xdg_root: Path) -> None:
    root = isolated_xdg_root.resolve(strict=True)
    for variable, directory in _XDG_LAYOUT.items():
        assert Path(os.environ[variable]).resolve(strict=True) == (root / directory).resolve(
            strict=True
        )


def test_autouse_fixture_isolates_home(isolated_xdg_root: Path) -> None:
    root = isolated_xdg_root.resolve(strict=True)
    home = Path(os.environ["HOME"]).resolve(strict=True)
    assert home == (root / "home").resolve(strict=True)


def test_home_negative_escape_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import tests.conftest as cft

    root = tmp_path / "sandbox"
    root.mkdir(parents=True)
    (root / "home").mkdir()
    (root / "home-escape").mkdir()

    cft._configure_xdg(root)
    monkeypatch.setenv("HOME", str(root / "home-escape"))
    with pytest.raises(pytest.UsageError, match="HOME escapa do isolamento"):
        cft._assert_xdg_matches(root)


def test_home_negative_symlink_escape_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tests.conftest as cft

    root = tmp_path / "sandbox"
    root.mkdir(parents=True)
    (root / "home").mkdir()
    escape_target = tmp_path / "outside"
    escape_target.mkdir()
    symlinked_home = root / "home" / "linked"
    symlinked_home.symlink_to(escape_target, target_is_directory=True)

    cft._configure_xdg(root)
    monkeypatch.setenv("HOME", str(symlinked_home))
    with pytest.raises(pytest.UsageError, match="HOME escapa do isolamento"):
        cft._assert_xdg_matches(root)


def test_isolated_home_is_not_real(tmp_path: Path) -> None:
    env = {"HOME": "/real/home"}
    for v, d in _XDG_LAYOUT.items():
        env[v] = f"/real/{d}"
    result = isolated_environment(tmp_path / "iso", env)
    assert result["HOME"] != "/real/home"
    assert not result["HOME"].startswith(str(Path.home()))


def test_resolve_xdg_precedence(tmp_path: Path) -> None:
    xdg_state = tmp_path / "xdg-state"
    xdg_state.mkdir()
    home_dir = tmp_path / "home-fallback"
    home_dir.mkdir()
    env = {"XDG_STATE_HOME": str(xdg_state), "HOME": str(home_dir)}
    path, source = resolve_real_state_home(env)
    assert path == (xdg_state / "steamzero")
    assert source == "XDG_STATE_HOME"


def test_resolve_home_fallback(tmp_path: Path) -> None:
    home_dir = tmp_path / "fallback-home"
    home_dir.mkdir()
    env = {"HOME": str(home_dir)}
    path, source = resolve_real_state_home(env)
    assert path == (home_dir / ".local" / "state" / "steamzero")
    assert source == "HOME-default"


def test_resolve_global_home_ignored(tmp_path: Path) -> None:
    xdg_state = tmp_path / "xdg-state"
    xdg_state.mkdir()
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    env = {"XDG_STATE_HOME": str(xdg_state), "HOME": str(fake_home)}
    path, source = resolve_real_state_home(env)
    assert path == (xdg_state / "steamzero")
    assert source == "XDG_STATE_HOME"


def test_resolve_rejects_missing_both() -> None:
    with pytest.raises(RuntimeError, match="nem XDG_STATE_HOME nem HOME"):
        resolve_real_state_home({})


def test_isolated_environment_overrides_all_vars(tmp_path: Path) -> None:
    root = tmp_path / "isolated"
    original = {variable: f"/real/{directory}" for variable, directory in _XDG_LAYOUT.items()}
    original["HOME"] = "/real/home"

    result = isolated_environment(root, original)

    assert result["HOME"] == str(root / "home")
    for variable, directory in _XDG_LAYOUT.items():
        assert result[variable] == str(root / directory)
    assert result[_TEST_ROOT_ENV] == str(root)
    assert (root / "home").is_dir()
    assert all((root / directory).is_dir() for directory in _XDG_LAYOUT.values())


def test_snapshot_detects_create_change_and_remove(tmp_path: Path) -> None:
    root = tmp_path / "state" / "steamzero"
    root.mkdir(parents=True)
    kept = root / "kept.json"
    removed = root / "removed.json"
    kept.write_text("before", encoding="utf-8")
    removed.write_text("remove", encoding="utf-8")
    before = snapshot_state(root)

    kept.write_text("after-longer", encoding="utf-8")
    removed.unlink()
    (root / "created.json").write_text("new", encoding="utf-8")
    after = snapshot_state(root)

    created, deleted, changed = changed_entries(before, after)
    assert created == ["created.json"]
    assert deleted == ["removed.json"]
    assert changed == ["kept.json"]


def test_runner_rejects_any_change_to_original_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_base = tmp_path / "real-state"
    real_root = real_base / "steamzero"
    real_root.mkdir(parents=True)

    def mutate_real_state(argv, *, env, check):
        assert check is False
        assert "pytest" in argv
        assert Path(env["XDG_STATE_HOME"]) != real_base
        journal = real_root / "journal"
        journal.mkdir()
        (journal / "unexpected.jsonl").write_text("mutation", encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(run_tests_isolated.subprocess, "run", mutate_real_state)

    assert (
        run_tests_isolated.run_pytest([], environ={"XDG_STATE_HOME": str(real_base)})
        == _STATE_CHANGE_EXIT
    )


def test_runner_preserves_pytest_exit_when_original_state_is_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_base = tmp_path / "real-state"

    def finish_without_writes(argv, *, env, check):
        assert check is False
        assert Path(env["XDG_STATE_HOME"]) != real_base
        return subprocess.CompletedProcess(argv, 7)

    monkeypatch.setattr(run_tests_isolated.subprocess, "run", finish_without_writes)

    result = run_tests_isolated.run_pytest([], environ={"XDG_STATE_HOME": str(real_base)})
    assert result == 7


# ---------------------------------------------------------------------------
# Helpers de parser de entrypoints (Make + CI + classificação Python)
# ---------------------------------------------------------------------------


def _extract_make_commands(make_output: str) -> list[list[str]]:
    """Extrai comandos lógicos de saída de ``make -n``, unindo continuações \\.

    Cada comando lógico é tokenizado com ``shlex``.
    Linhas em branco e comentários (``#`` como primeiro token) são ignorados.
    """
    commands: list[list[str]] = []
    buf: list[str] = []
    for raw in make_output.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        if line.endswith("\\"):
            buf.append(line[:-1].rstrip())
        else:
            buf.append(line)
            combined = " ".join(buf)
            buf = []
            try:
                tokens = shlex.split(combined)
            except ValueError:
                continue
            if tokens and not tokens[0].startswith("#"):
                commands.append(tokens)
    if buf:
        combined = " ".join(buf)
        try:
            tokens = shlex.split(combined)
        except ValueError:
            pass
        else:
            if tokens and not tokens[0].startswith("#"):
                commands.append(tokens)
    return commands


def _extract_ci_commands(ci_yml: str) -> list[list[str]]:
    """Extrai comandos lógicos dos blocos ``run:`` e ``run |`` de YAML CI.

    Comentários (linhas começando com ``#``) e linhas vazias são ignorados.
    Cada comando tokenizado com ``shlex``.
    """
    commands: list[list[str]] = []
    lines = ci_yml.splitlines()
    buf: list[str] = []
    in_block = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("run:"):
            remainder = stripped[len("run:") :].strip()
            commands.append(_finish_ci_buf(buf))
            buf.clear()
            if remainder:
                buf.append(remainder)
            in_block = True
        elif stripped.startswith("run |"):
            commands.append(_finish_ci_buf(buf))
            buf.clear()
            in_block = True
        elif in_block:
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("-") and not stripped.startswith(" "):
                commands.append(_finish_ci_buf(buf))
                buf.clear()
            elif stripped.endswith("\\"):
                buf.append(stripped[:-1].rstrip())
            else:
                buf.append(stripped)
                commands.append(_finish_ci_buf(buf))
                buf.clear()
    if in_block:
        commands.append(_finish_ci_buf(buf))
    return [tokens for tokens in commands if tokens]


def _finish_ci_buf(buf: list[str]) -> list[str]:
    """Concatena ``buf``, tokeniza com shlex e retorna argv."""
    if not buf:
        return []
    try:
        return shlex.split(" ".join(buf))
    except ValueError:
        return []


def _classify_python_argv(argv: list[str], script: str = "tools/run_tests_isolated.py") -> bool:
    """Verdadeiro se o primeiro executável de ``argv`` é Python E o argumento
    seguinte é exatamente ``script``.

    Aceita como executável Python: ``python``, ``python3``, ``.venv/bin/python``
    ou qualquer basename compatível com ``pythonX.Y``.
    """
    if len(argv) < 2:
        return False
    first = argv[0]
    second = argv[1]
    if second != script:
        return False
    basename = Path(first).name
    if basename in ("python", "python3"):
        return True
    # pythonX.Y — ex.: python3.11, python3.13
    if basename.startswith("python") and len(basename) > 6:
        rest = basename[6:]
        if "." in rest and rest.replace(".", "").isdigit():
            return True
    return False


def _iter_python_invocations(lines: list[str]) -> list[list[str]]:
    """Itera linhas de texto procurando invocações Python do runner.

    Cada linha é tokenizada com ``shlex``; apenas comandos onde o primeiro
    token executável é Python e o segundo é ``tools/run_tests_isolated.py``
    são aceitos.
    """
    script = "tools/run_tests_isolated.py"
    hits: list[list[str]] = []
    for line in lines:
        try:
            tokens = shlex.split(line)
        except ValueError:
            continue
        if not tokens:
            continue
        if tokens[0].startswith("#"):
            continue
        if _classify_python_argv(tokens, script):
            hits.append(tokens)
    return hits


def _check_make_target(runner_script: str, make_target: str, root: Path) -> None:
    result = subprocess.run(
        ["make", "-n", make_target],
        capture_output=True,
        text=True,
        cwd=str(root),
    )
    assert result.returncode == 0, (
        f"make -n {make_target} failed: rc={result.returncode}\nstderr={result.stderr}"
    )
    commands = _extract_make_commands(result.stdout)
    hits = [c for c in commands if _classify_python_argv(c, runner_script)]
    assert len(hits) >= 1, (
        f"make -n {make_target} does not invoke {runner_script}.\nCommands extracted: {commands}"
    )


def test_canonical_entrypoints_use_isolated_runner() -> None:
    root = Path(__file__).resolve().parents[2]
    script = "tools/run_tests_isolated.py"

    _check_make_target(script, "test", root)
    _check_make_target(script, "cov", root)
    _check_make_target(script, "qml-visual", root)

    # Controles negativos do _classify_python_argv
    negative_cases: list[tuple[str, list[str]]] = [
        ("echo", ["echo", script]),
        ("printf", ["printf", "%s", script]),
        ("false && python", ["false", "&&", "python", script]),
        ("echo ok && python", ["echo", "ok", "&&", "python", script]),
        ("comentário", ["#", script]),
        ("ls", ["ls", script]),
        ("python -c", ["python", "-c", f'print("{script}")']),
    ]
    for label, argv in negative_cases:
        assert not _classify_python_argv(argv, script), (
            f"controle negativo '{label}' deveria rejeitar argv={argv}"
        )

    # Controles positivos do _classify_python_argv
    positive_cases: list[tuple[str, list[str]]] = [
        ("python", ["python", script]),
        ("python3", ["python3", script]),
        (".venv/bin/python", [".venv/bin/python", script]),
        ("python3.11", ["python3.11", script]),
    ]
    for label, argv in positive_cases:
        assert _classify_python_argv(argv, script), (
            f"controle positivo '{label}' deveria aceitar argv={argv}"
        )

    # _extract_make_commands — continuação com \
    make_raw = (
        "python tools/run_tests_isolated.py tests -q\n"
        ".venv/bin/python tools/run_tests_isolated.py tests -q \\\n"
        "  --timeout 60\n"
        "# comment\n"
        "echo not-python\n"
    )
    make_cmds = _extract_make_commands(make_raw)
    assert len(make_cmds) == 3, (
        f"expected 3 commands from make_raw, got {len(make_cmds)}: {make_cmds}"
    )
    assert _classify_python_argv(make_cmds[0], script)
    assert _classify_python_argv(make_cmds[1], script)
    assert not _classify_python_argv(make_cmds[2], script)

    # CI
    ci_yml = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    ci_commands = _extract_ci_commands(ci_yml)
    ci_hits = [c for c in ci_commands if _classify_python_argv(c, script)]
    assert len(ci_hits) == 2, (
        f"CI must contain exactly 2 invocations of {script} "
        f"(pytest + coverage), found {len(ci_hits)}:\n" + "\n".join(str(a) for a in ci_hits)
    )

    governance = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert f"python {script} tests -q" in governance, (
        f"AGENTS.md must contain full canonical command 'python {script} tests -q'"
    )


def test_collection_time_isolation_via_real_conftest(tmp_path: Path) -> None:
    sentinel = tmp_path / "real-user-home"
    sentinel.mkdir(parents=True, exist_ok=True)
    sentinel_state = sentinel / ".local" / "state" / "steamzero"
    sentinel_state.mkdir(parents=True)
    sentinel_file = sentinel_state / "sentinel.txt"
    sentinel_file.write_text("real-user-state", encoding="utf-8")

    before_entries = sorted(
        p.relative_to(sentinel).as_posix()
        for p in sentinel.rglob("*")
        if not p.is_symlink() or p.is_dir()
    )

    attest_path = tmp_path / "attest.json"

    project_root = Path(__file__).resolve().parents[2]
    probe = project_root / "tests" / "fixtures" / "import_time_xdg_probe.py"
    assert probe.is_file(), f"probe not found at {probe}"

    clean_env = {k: v for k, v in os.environ.items() if not k.startswith("XDG_")}
    clean_env["HOME"] = str(sentinel)
    clean_env["STEAMZERO_TEST_HOME_SENTINEL"] = str(sentinel)
    clean_env["STEAMZERO_TEST_ATTEST_PATH"] = str(attest_path)
    clean_env.pop("XDG_STATE_HOME", None)
    clean_env.pop("XDG_DATA_HOME", None)
    clean_env.pop("XDG_CONFIG_HOME", None)
    clean_env.pop("XDG_CACHE_HOME", None)
    clean_env.pop("XDG_RUNTIME_DIR", None)
    clean_env.pop("STEAMZERO_TEST_XDG_ROOT", None)
    clean_env.pop("PYTEST_ADDOPTS", None)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(probe),
            "-q",
            "--tb=long",
            "-p",
            "no:cacheprovider",
            "--rootdir",
            str(project_root),
        ],
        env=clean_env,
        capture_output=True,
        text=True,
        cwd=str(project_root),
    )
    assert result.returncode == 0, (
        f"probe test failed — REAL conftest.py não isolou antes da coleta:\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )

    assert attest_path.is_file(), (
        f"attestation not written at {attest_path}:\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    attest = json.loads(attest_path.read_text(encoding="utf-8"))
    assert attest.get("isolamento") == "confirmado", f"isolation not confirmed: {attest}"
    assert attest.get("root_diferente_do_sentinel") is not False, f"root matches sentinel: {attest}"

    after_entries = sorted(
        p.relative_to(sentinel).as_posix()
        for p in sentinel.rglob("*")
        if not p.is_symlink() or p.is_dir()
    )
    assert before_entries == after_entries, (
        f"sentinel tree foi modificado pelo probe:\nbefore={before_entries}\nafter={after_entries}"
    )
    assert sentinel_file.read_text(encoding="utf-8") == "real-user-state", (
        "sentinel.txt foi modificado pelo probe"
    )


def _capture_snapshots_called(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    calls: list[bool] = []
    _original = run_tests_isolated.snapshot_state

    def tracking_snapshot(root):
        calls.append(True)
        return _original(root)

    monkeypatch.setattr(run_tests_isolated, "snapshot_state", tracking_snapshot)
    return calls


def test_interrupt_returns_130_on_intact_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_base = tmp_path / "real-state"
    real_root = real_base / "steamzero"
    real_root.mkdir(parents=True)

    def raise_keyboard_interrupt(argv, *, env, check):
        raise KeyboardInterrupt()

    monkeypatch.setattr(run_tests_isolated.subprocess, "run", raise_keyboard_interrupt)
    snap_calls = _capture_snapshots_called(monkeypatch)

    result = run_tests_isolated.run_pytest([], environ={"XDG_STATE_HOME": str(real_base)})
    assert result == 130, f"expected 130 on interrupt, got {result}"
    assert len(snap_calls) >= 2, (
        f"snapshot_state must be called at least twice (before + after), "
        f"called {len(snap_calls)} times"
    )


def test_interrupt_returns_86_on_mutated_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_base = tmp_path / "real-state"
    real_root = real_base / "steamzero"
    real_root.mkdir(parents=True)

    def raise_keyboard_interrupt(argv, *, env, check):
        journal = real_root / "journal"
        journal.mkdir()
        (journal / "unexpected.jsonl").write_text("mutation", encoding="utf-8")
        raise KeyboardInterrupt()

    monkeypatch.setattr(run_tests_isolated.subprocess, "run", raise_keyboard_interrupt)
    snap_calls = _capture_snapshots_called(monkeypatch)

    result = run_tests_isolated.run_pytest([], environ={"XDG_STATE_HOME": str(real_base)})
    assert result == _STATE_CHANGE_EXIT, (
        f"expected {_STATE_CHANGE_EXIT} on interrupt + mutation, got {result}"
    )
    assert len(snap_calls) >= 2


def test_normal_returns_86_on_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real_base = tmp_path / "real-state"
    real_root = real_base / "steamzero"
    real_root.mkdir(parents=True)

    def mutate_passing(argv, *, env, check):
        journal = real_root / "journal"
        journal.mkdir()
        (journal / "unexpected.jsonl").write_text("mutation", encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(run_tests_isolated.subprocess, "run", mutate_passing)
    snap_calls = _capture_snapshots_called(monkeypatch)

    result = run_tests_isolated.run_pytest([], environ={"XDG_STATE_HOME": str(real_base)})
    assert result == _STATE_CHANGE_EXIT
    assert len(snap_calls) >= 2


def test_normal_returns_pytest_returncode_on_intact_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_base = tmp_path / "real-state"

    def finish_with_code_3(argv, *, env, check):
        return subprocess.CompletedProcess(argv, 3)

    monkeypatch.setattr(run_tests_isolated.subprocess, "run", finish_with_code_3)

    result = run_tests_isolated.run_pytest([], environ={"XDG_STATE_HOME": str(real_base)})
    assert result == 3


def test_snapshot_called_in_finally_even_on_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_base = tmp_path / "real-state"
    real_root = real_base / "steamzero"
    real_root.mkdir(parents=True)

    def raise_bogus(argv, *, env, check):
        raise RuntimeError("unexpected failure in subprocess")

    monkeypatch.setattr(run_tests_isolated.subprocess, "run", raise_bogus)
    snap_calls = _capture_snapshots_called(monkeypatch)

    with pytest.raises(RuntimeError, match="unexpected failure in subprocess"):
        run_tests_isolated.run_pytest([], environ={"XDG_STATE_HOME": str(real_base)})

    assert len(snap_calls) >= 2, (
        f"snapshot_state must be called even on unexpected error (called {len(snap_calls)} times)"
    )


def test_unexpected_exception_with_mutation_reports_and_repropagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    real_base = tmp_path / "real-state"
    real_root = real_base / "steamzero"
    real_root.mkdir(parents=True)

    def raise_bogus_after_mutation(argv, *, env, check):
        journal = real_root / "journal"
        journal.mkdir()
        (journal / "unexpected.jsonl").write_text("mutation", encoding="utf-8")
        raise RuntimeError("unexpected failure after mutation")

    monkeypatch.setattr(run_tests_isolated.subprocess, "run", raise_bogus_after_mutation)
    snap_calls = _capture_snapshots_called(monkeypatch)

    with pytest.raises(RuntimeError, match="unexpected failure after mutation"):
        run_tests_isolated.run_pytest([], environ={"XDG_STATE_HOME": str(real_base)})

    assert len(snap_calls) >= 2, (
        f"snapshot_state must be called even on unexpected error with mutation "
        f"(called {len(snap_calls)} times)"
    )
    stderr_output = capsys.readouterr().err
    assert "E-TEST-REAL-STATE-MUTATED" in stderr_output, (
        f"mutation must be reported via _report_state_change on stderr when "
        f"unexpected exception + mutation occur.\nstderr:\n{stderr_output}"
    )


# ---------------------------------------------------------------------------
# Atribuição da mutação: dono externo do state real vs. vazamento da suíte
#
# O daemon instalado (``steamzero-core --systemd``) e comandos ``steamzero`` do
# operador escrevem no MESMO state home que o guard fotografa. Sem atribuição, o
# guard culpa o pytest por escrita alheia e o gate fica vermelho de rotina.
# ---------------------------------------------------------------------------


def _write_fake_proc(
    root: Path, pid: int, *, cmdline: str, environ: dict[str, str], ticks: int
) -> None:
    entry = root / str(pid)
    entry.mkdir(parents=True)
    (entry / "cmdline").write_bytes(("\0".join(cmdline.split(" ")) + "\0").encode())
    (entry / "environ").write_bytes(("".join(f"{k}={v}\0" for k, v in environ.items())).encode())
    # /proc/<pid>/stat: pid (comm) state ... starttime é o campo 22.
    tail = " ".join(["S"] + ["0"] * 18 + [str(ticks)])
    (entry / "stat").write_text(f"{pid} (fake proc) {tail} 0 0 0\n", encoding="utf-8")


def _fake_writer(
    pid: int, *, predates: bool, cmd: str = "steamzero-core --systemd"
) -> ForeignWriter:
    return ForeignWriter(pid=pid, cmdline=cmd, start_boottime=1.0, predates_window=predates)


def _run_with_mutation_and_writers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    writers: list[ForeignWriter],
    returncode: int = 0,
) -> int:
    real_base = tmp_path / "real-state"
    real_root = real_base / "steamzero"
    real_root.mkdir(parents=True)

    def mutate(argv, *, env, check):
        journal = real_root / "journal"
        journal.mkdir()
        (journal / "unexpected.jsonl").write_text("mutation", encoding="utf-8")
        return subprocess.CompletedProcess(argv, returncode)

    monkeypatch.setattr(run_tests_isolated.subprocess, "run", mutate)
    monkeypatch.setattr(
        run_tests_isolated,
        "scan_foreign_writers",
        lambda root, *, window_start_boottime: {w.pid: w for w in writers},
    )
    return run_tests_isolated.run_pytest([], environ={"XDG_STATE_HOME": str(real_base)})


def test_external_writer_predating_window_does_not_fail_the_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Daemon do host vivo desde antes da janela: mutação real, culpa que não é da suíte."""
    result = _run_with_mutation_and_writers(
        tmp_path, monkeypatch, [_fake_writer(4242, predates=True)], returncode=0
    )

    assert result == 0, f"dono externo não pode reprovar o gate, got {result}"
    stderr_output = capsys.readouterr().err
    assert "W-TEST-REAL-STATE-EXTERNAL-WRITER" in stderr_output
    assert "pid=4242" in stderr_output, "o guard precisa nomear o processo externo"
    assert "E-TEST-REAL-STATE-MUTATED" not in stderr_output


def test_external_writer_preserves_pytest_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dono externo não pode mascarar teste reprovado."""
    result = _run_with_mutation_and_writers(
        tmp_path, monkeypatch, [_fake_writer(4242, predates=True)], returncode=1
    )
    assert result == 1


def test_process_born_during_window_is_blamed_as_suite_leak(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Processo steamzero nascido dentro da janela é vazamento da suíte: 86."""
    result = _run_with_mutation_and_writers(
        tmp_path, monkeypatch, [_fake_writer(5150, predates=False)]
    )

    assert result == _STATE_CHANGE_EXIT
    stderr_output = capsys.readouterr().err
    assert "E-TEST-REAL-STATE-MUTATED" in stderr_output
    assert "pid=5150" in stderr_output
    assert "NASCEU durante a janela" in stderr_output


def test_suspect_wins_over_external_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Daemon ativo não pode servir de álibi para processo nascido na janela."""
    result = _run_with_mutation_and_writers(
        tmp_path,
        monkeypatch,
        [_fake_writer(4242, predates=True), _fake_writer(5150, predates=False)],
    )

    assert result == _STATE_CHANGE_EXIT, "suspeito nascido na janela tem de reprovar"
    assert "pid=5150" in capsys.readouterr().err


def test_mutation_without_writers_still_fails_and_names_operator_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Sem processo observado, o guard mantém 86 e ensina o falso positivo do operador."""
    result = _run_with_mutation_and_writers(tmp_path, monkeypatch, [])

    assert result == _STATE_CHANGE_EXIT
    stderr_output = capsys.readouterr().err
    assert "E-TEST-REAL-STATE-MUTATED" in stderr_output
    assert "FALSO POSITIVO DO OPERADOR" in stderr_output, (
        "quem lê o 86 precisa saber, no ponto do erro, que um comando `steamzero` "
        f"concorrente dispara o guard.\nstderr:\n{stderr_output}"
    )
    assert "systemctl --user" in stderr_output


def test_intact_state_never_reports_writers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    real_base = tmp_path / "real-state"

    monkeypatch.setattr(
        run_tests_isolated.subprocess,
        "run",
        lambda argv, *, env, check: subprocess.CompletedProcess(argv, 0),
    )
    monkeypatch.setattr(
        run_tests_isolated,
        "scan_foreign_writers",
        lambda root, *, window_start_boottime: {4242: _fake_writer(4242, predates=True)},
    )

    assert run_tests_isolated.run_pytest([], environ={"XDG_STATE_HOME": str(real_base)}) == 0
    stderr_output = capsys.readouterr().err
    assert "EXTERNAL-WRITER" not in stderr_output
    assert "E-TEST-REAL-STATE-MUTATED" not in stderr_output


def test_writer_appearing_only_at_window_close_is_still_observed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """A amostra de fechamento tem de entrar na decisão.

    O ``__exit__`` do watcher roda depois do ``finally`` que decide o veredito;
    sem uma amostra explícita no fechamento, um dono que só aparece no fim da
    janela some e o gate culpa a suíte por escrita alheia.
    """
    real_base = tmp_path / "real-state"
    real_root = real_base / "steamzero"
    real_root.mkdir(parents=True)
    calls: list[int] = []

    def mutate(argv, *, env, check):
        (real_root / "tocado.jsonl").write_text("mutation", encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0)

    def scan_visible_only_after_first_call(root, *, window_start_boottime):
        calls.append(1)
        if len(calls) == 1:
            return {}
        return {4242: _fake_writer(4242, predates=True)}

    monkeypatch.setattr(run_tests_isolated.subprocess, "run", mutate)
    monkeypatch.setattr(
        run_tests_isolated, "scan_foreign_writers", scan_visible_only_after_first_call
    )

    result = run_tests_isolated.run_pytest([], environ={"XDG_STATE_HOME": str(real_base)})

    assert len(calls) >= 2, "o watcher precisa amostrar também no fechamento da janela"
    stderr_output = capsys.readouterr().err
    assert result == 0, (
        f"dono externo visto na amostra de fechamento não pode reprovar o gate "
        f"(got {result}).\nstderr:\n{stderr_output}"
    )
    assert "pid=4242" in stderr_output


def test_watcher_skips_polling_when_real_state_home_is_absent(tmp_path: Path) -> None:
    """Sem state home real (o caso do CI) o gate não paga thread de polling."""
    watcher = run_tests_isolated._WriterWatcher(tmp_path / "inexistente", window_start_boottime=0.0)
    with watcher:
        assert not watcher._thread.is_alive(), "não deve haver polling sem state home real"
    assert watcher.writers == {}


def test_watcher_polls_when_real_state_home_exists(tmp_path: Path) -> None:
    real_root = tmp_path / "steamzero"
    real_root.mkdir()
    watcher = run_tests_isolated._WriterWatcher(real_root, window_start_boottime=0.0)
    with watcher:
        assert watcher._thread.is_alive(), "com state home real, o polling precisa rodar"


def test_scan_finds_steamzero_process_sharing_the_real_state_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_proc = tmp_path / "proc"
    home = tmp_path / "home"
    _write_fake_proc(
        fake_proc,
        4242,
        cmdline="/opt/steamzero/current/venv/bin/steamzero-core --systemd",
        environ={"HOME": str(home)},
        ticks=100,
    )
    monkeypatch.setattr(run_tests_isolated, "_PROC_ROOT", fake_proc)

    found = run_tests_isolated.scan_foreign_writers(
        home / ".local" / "state" / "steamzero", window_start_boottime=500.0
    )

    assert set(found) == {4242}
    assert found[4242].predates_window is True, "nascido em t=1s, janela em t=500s"
    assert "steamzero-core" in found[4242].cmdline


def test_scan_marks_process_born_after_window_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_proc = tmp_path / "proc"
    home = tmp_path / "home"
    _write_fake_proc(
        fake_proc,
        4243,
        cmdline="/usr/local/bin/steamzero doctor",
        environ={"HOME": str(home)},
        ticks=99999,
    )
    monkeypatch.setattr(run_tests_isolated, "_PROC_ROOT", fake_proc)

    found = run_tests_isolated.scan_foreign_writers(
        home / ".local" / "state" / "steamzero", window_start_boottime=500.0
    )

    assert found[4243].predates_window is False


def test_scan_ignores_isolated_suite_processes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Processo com o marcador de isolamento escreve no root temporário, nunca no real."""
    fake_proc = tmp_path / "proc"
    home = tmp_path / "home"
    _write_fake_proc(
        fake_proc,
        4244,
        cmdline="/usr/local/bin/steamzero doctor",
        environ={"HOME": str(home), _TEST_ROOT_ENV: str(tmp_path / "steamzero-tests-abc")},
        ticks=100,
    )
    monkeypatch.setattr(run_tests_isolated, "_PROC_ROOT", fake_proc)

    assert (
        run_tests_isolated.scan_foreign_writers(
            home / ".local" / "state" / "steamzero", window_start_boottime=500.0
        )
        == {}
    )


def test_scan_ignores_process_that_only_mentions_steamzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mencionar "steamzero" não faz de ninguém dono do state home.

    Um shell, grep ou editor com a palavra na linha de comando viraria um dono
    externo inventado — e um dono inventado serviria de álibi para uma escrita
    real da suíte, que é justamente o que o guard existe para pegar.
    """
    fake_proc = tmp_path / "proc"
    home = tmp_path / "home"
    _write_fake_proc(
        fake_proc,
        4247,
        cmdline="/bin/bash -c grep -rn steamzero /mnt/projeto/src",
        environ={"HOME": str(home)},
        ticks=100,
    )
    monkeypatch.setattr(run_tests_isolated, "_PROC_ROOT", fake_proc)

    assert (
        run_tests_isolated.scan_foreign_writers(
            home / ".local" / "state" / "steamzero", window_start_boottime=500.0
        )
        == {}
    )


def test_scan_accepts_interpreter_running_a_steamzero_script(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O daemon real é `python3 .../steamzero-core --systemd`: o nome está no argv[1]."""
    fake_proc = tmp_path / "proc"
    home = tmp_path / "home"
    _write_fake_proc(
        fake_proc,
        4248,
        cmdline="/opt/releases/venv/bin/python3 /opt/current/venv/bin/steamzero-core --systemd",
        environ={"HOME": str(home)},
        ticks=100,
    )
    monkeypatch.setattr(run_tests_isolated, "_PROC_ROOT", fake_proc)

    found = run_tests_isolated.scan_foreign_writers(
        home / ".local" / "state" / "steamzero", window_start_boottime=500.0
    )

    assert set(found) == {4248}


def test_scan_ignores_unrelated_and_foreign_state_homes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_proc = tmp_path / "proc"
    home = tmp_path / "home"
    # Processo do usuário sem relação com o projeto: mesmo HOME, não é escritor.
    _write_fake_proc(
        fake_proc, 4245, cmdline="/usr/bin/firefox", environ={"HOME": str(home)}, ticks=100
    )
    # Processo steamzero apontado para OUTRO state home.
    _write_fake_proc(
        fake_proc,
        4246,
        cmdline="/usr/local/bin/steamzero doctor",
        environ={"HOME": str(home), "XDG_STATE_HOME": str(tmp_path / "outro")},
        ticks=100,
    )
    monkeypatch.setattr(run_tests_isolated, "_PROC_ROOT", fake_proc)

    assert (
        run_tests_isolated.scan_foreign_writers(
            home / ".local" / "state" / "steamzero", window_start_boottime=500.0
        )
        == {}
    )
