# SPDX-License-Identifier: GPL-3.0-or-later
"""Contratos QML executados no compositor offscreen quando Qt está disponível."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

QML = shutil.which("qml6")
ROOT = Path(__file__).resolve().parents[2]

#: Ambiente visual ausente. Não é motivo para verde.
#:
#: Um `skip` aqui produz suíte verde num host onde NADA visual foi verificado —
#: e foi exatamente assim que a regressão de ícones da a37 atravessou os gates.
#: Os harnesses acima ainda usam `skipif`; o VS-03 converte todos.
DIAG_VISUAL_ENVIRONMENT = "QML-VISUAL-ENVIRONMENT-001"


def _qml_environment() -> dict[str, str]:
    """Keep Qt diagnostics observable even when the host routes them to journald."""
    env = os.environ.copy()
    env.update(
        {
            "QT_FORCE_STDERR_LOGGING": "1",
            "QT_LOGGING_RULES": "",
            "QT_QPA_PLATFORM": "offscreen",
            "QML_DISABLE_DISK_CACHE": "1",
        }
    )
    return env


def _assert_qml_clean(completed: subprocess.CompletedProcess[str], label: str) -> None:
    diagnostics = (
        "Binding loop",
        "Unable to assign",
        "TypeError:",
        "ReferenceError:",
        "Cannot open:",
    )
    assert completed.returncode == 0, (
        f"{label} falhou ({completed.returncode})\n"
        f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    )
    unexpected = [
        line
        for line in completed.stderr.splitlines()
        if any(marker in line for marker in diagnostics)
    ]
    assert not unexpected, f"{label} publicou diagnósticos QML inesperados:\n" + "\n".join(
        unexpected
    )


def _run_qml(harness: str, *arguments: str, scale_factor: int | None = None) -> None:
    """Executa um harness com os diagnósticos do Qt preservados."""
    env = _qml_environment()
    if scale_factor is not None:
        env["QT_SCALE_FACTOR"] = str(scale_factor)
    completed = subprocess.run(
        [str(QML), f"tests/qml/{harness}", "--", *arguments],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    _assert_qml_clean(completed, " ".join((harness, *arguments)))


class _ErrorServerHandler(BaseHTTPRequestHandler):
    """Retorna 200 em /status e 400 com error-v1 em /emulation/action/plan."""

    def do_GET(self) -> None:
        if self.path == "/status":
            self._ok({"status": "ok"})
        else:
            self._error(404, "not found")

    def do_POST(self) -> None:
        if self.path == "/emulation/action/plan":
            self._error(
                400,
                {
                    "error": {
                        "code": "E-TX-001",
                        "operationId": "op-transactional-789",
                        "title": "Falha na aplicação do plano",
                        "what": "Plano de ação conflitou com estado atual do emulador.",
                        "impact": "Nenhuma alteração foi aplicada.",
                        "autoAction": "",
                        "manualAction": "Revise o plano e tente novamente.",
                        "probableCause": (
                            "Um plano mais recente foi aplicado entre a leitura e a confirmação."
                        ),
                    }
                },
            )
        else:
            self._error(404, "not found")

    def _ok(self, body: dict) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(payload)

    def _error(self, code: int, body: dict | str) -> None:
        if isinstance(body, dict):
            payload = json.dumps(body).encode("utf-8")
        else:
            payload = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args: object) -> None:
        pass


@pytest.fixture(scope="session")
def _error_server() -> tuple[int, threading.Thread, HTTPServer]:
    host = "127.0.0.1"
    for port in range(42000, 43000):
        try:
            server = HTTPServer((host, port), _ErrorServerHandler)
        except OSError:
            continue
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return port, thread, server
    raise RuntimeError("nenhuma porta livre para o servidor de teste ErrorCard")


@pytest.mark.skipif(QML is None, reason="qml6 não está instalado neste host")
@pytest.mark.parametrize(
    "harness",
    [
        "check_handheld_shell.qml",
        "check_main_emulation.qml",
        "check_emulation.qml",
        "check_steam_gameplay_responsive.qml",
        "check_editorial_home.qml",
        "check_editorial_library.qml",
        "check_editorial_canonical_systems.qml",
        "check_media_effect_layer.qml",
        "check_asset_recipe_preview.qml",
        "check_scene_repeater.qml",
        "check_operational_metric_card.qml",
        "check_handheld_layout_focus.qml",
        "check_main_handheld_sections.qml",
        "check_credentials.qml",
        "check_credential_dialog_responsive.qml",
        "check_high_contrast.qml",
        # Prova Image.Ready de cada asset empacotado, não apenas o caminho.
        "check_packaged_assets.qml",
        # Identidade AURA no editor: preview no ThemeBridge, cancelar restaura.
        "check_theme_editor_aura.qml",
        "check_theme_editor_asset_recipes.qml",
    ],
)
def test_qml_handheld_harness_offscreen(harness: str) -> None:
    completed = subprocess.run(
        [str(QML), f"tests/qml/{harness}"],
        cwd=ROOT,
        env=_qml_environment(),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    _assert_qml_clean(completed, harness)


@pytest.mark.skipif(QML is None, reason="qml6 não está instalado neste host")
def test_editorial_library_renders_at_logical_scale_200() -> None:
    """A composição editorial continua utilizável em 4K físico a 200% lógico."""
    _run_qml("check_editorial_library.qml", scale_factor=2)


@pytest.mark.skipif(QML is None, reason="qml6 não está instalado neste host")
@pytest.mark.parametrize(
    ("arguments", "label"),
    [
        (("--system-count=37",), "37 sistemas em 1280x800"),
        (
            (
                "--system-count=37",
                "--long-system-status",
                "--capture-width=800",
                "--capture-height=1280",
                "--capture-high-contrast",
                "--geometry-only",
            ),
            "37 sistemas com rótulo longo em 800x1280 e alto contraste",
        ),
    ],
)
def test_editorial_system_cards_keep_the_minimum_geometry(
    arguments: tuple[str, ...], label: str
) -> None:
    """G36 — a grade dá a todos os cards, inclusive o último, a altura contratada."""
    _run_qml("check_editorial_library.qml", *arguments)


@pytest.mark.skipif(QML is None, reason="qml6 não está instalado neste host")
@pytest.mark.parametrize("stage", ("systems", "system", "library", "dossier", "launch"))
def test_editorial_capture_requested_stage_is_independent(tmp_path: Path, stage: str) -> None:
    """Cada etapa editorial captura o frame pedido sem depender do timer da jornada."""
    output = tmp_path / f"editorial-{stage}.png"
    _run_qml(
        "check_editorial_library.qml",
        f"--capture-stage={stage}",
        f"--capture-output={output}",
    )
    assert output.is_file() and output.stat().st_size > 0


@pytest.mark.skipif(QML is None, reason="qml6 não está instalado neste host")
def test_qml_emulation_error_card_via_transactional_failure(
    _error_server: tuple[int, threading.Thread, HTTPServer],
) -> None:
    port, _thread, _server = _error_server
    completed = subprocess.run(
        [
            str(QML),
            "tests/qml/check_emulation_error_active_errors.qml",
            "--steamzero-api",
            f"http://127.0.0.1:{port}",
            "--steamzero-token",
            "test",
        ],
        cwd=ROOT,
        env=_qml_environment(),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    _assert_qml_clean(completed, "Harness ErrorCard transacional")


@pytest.mark.visual
def test_scene_text_renders_what_the_adapter_emits() -> None:
    """VS-02 — o Qt precisa ACEITAR o payload do adapter, não só recebê-lo.

    Os testes em Python provam o mapeamento. Nenhum deles prova que
    `Text["AlignHCenter"]` resolve para o enum do Qt, que `font.weight: 600` é
    aceito, ou que `#80112233` não vira "Invalid property assignment" — o mesmo
    erro que já derrubou `rgba(212,84,84,0.08)` neste repositório.

    Ambiente sem Qt reprova explicitamente. Verde só existe quando alguém de fato
    renderizou.
    """
    if QML is None:
        pytest.fail(
            f"{DIAG_VISUAL_ENVIRONMENT}: qml6 ausente. O contrato entre o adapter "
            "e SceneText.qml não pode ser verificado sem runtime QML, e declarar "
            "verde sem verificar é o que deixou a regressão de ícones passar."
        )
    completed = subprocess.run(
        [str(QML), "tests/qml/check_scene_text.qml"],
        cwd=ROOT,
        env=_qml_environment(),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    _assert_qml_clean(completed, "check_scene_text.qml")
