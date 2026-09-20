# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import subprocess

from steamzero.adapters.ps5_runtime import Ps5RuntimeReadiness, check_ps5_runtime


def _completed(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["vulkaninfo", "--summary"], returncode, stdout=stdout)


def test_ps5_runtime_accepts_x64_with_a_real_vulkan_summary() -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((argv, kwargs))
        return _completed("Vulkan Instance Version: 1.4.0\nDevices:\n")

    readiness = check_ps5_runtime(
        machine=lambda: "AMD64",
        which=lambda command: "/usr/sbin/vulkaninfo" if command == "vulkaninfo" else None,
        run=run,
    )

    assert readiness == Ps5RuntimeReadiness(True, "amd64", True)
    assert calls == [
        (
            ["/usr/sbin/vulkaninfo", "--summary"],
            {
                "stdin": subprocess.DEVNULL,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
                "text": True,
                "timeout": 5,
                "check": False,
            },
        )
    ]


def test_ps5_runtime_rejects_unsupported_architecture_without_probing() -> None:
    called = False

    def which(_command: str) -> str | None:
        nonlocal called
        called = True
        return "/usr/sbin/vulkaninfo"

    readiness = check_ps5_runtime(machine=lambda: "aarch64", which=which)

    assert readiness == Ps5RuntimeReadiness(False, "aarch64", False, "ps5-architecture-unsupported")
    assert called is False


def test_ps5_runtime_reports_missing_vulkan_tool() -> None:
    readiness = check_ps5_runtime(machine=lambda: "x86_64", which=lambda _command: None)

    assert readiness == Ps5RuntimeReadiness(False, "x86_64", False, "ps5-vulkan-tool-missing")


def test_ps5_runtime_reports_nonzero_or_malformed_probe() -> None:
    for result in (
        _completed("Vulkan Instance Version: 1.4.0\nDevices:\n", returncode=1),
        _completed("Vulkan Instance Version: 1.4.0\n", returncode=0),
    ):
        readiness = check_ps5_runtime(
            machine=lambda: "x86_64",
            which=lambda _command: "/usr/sbin/vulkaninfo",
            run=lambda *_args, _result=result, **_kwargs: _result,
        )
        assert readiness == Ps5RuntimeReadiness(False, "x86_64", False, "ps5-vulkan-probe-failed")


def test_ps5_runtime_reports_probe_timeout() -> None:
    def run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired("vulkaninfo", 5)

    readiness = check_ps5_runtime(
        machine=lambda: "x86_64",
        which=lambda _command: "/usr/sbin/vulkaninfo",
        run=run,
    )

    assert readiness == Ps5RuntimeReadiness(False, "x86_64", False, "ps5-vulkan-probe-failed")
