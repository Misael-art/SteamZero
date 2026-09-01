# SPDX-License-Identifier: GPL-3.0-or-later
"""Contratos QML executados no compositor offscreen quando Qt está disponível."""

from __future__ import annotations

import functools
import json
import os
import shutil
import subprocess
import tempfile
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


# Harnesses que carregam um asset SVG do pacote. A imagem canônica do gate
# visual traz qt6-declarative e qt6-base, mas NÃO o plugin de imagem SVG: os
# quatro falham com "QML Image: Error decoding" enquanto os outros 21 passam.
# Pular com a razão explícita é melhor que removê-los do gate — o dia em que a
# imagem ganhar o plugin, eles voltam sozinhos.
_SVG_HARNESSES = frozenset(
    {
        "check_asset_recipe_preview.qml",
        "check_editorial_library.qml",
        "check_packaged_assets.qml",
        "check_theme_editor_asset_recipes.qml",
    }
)


@functools.lru_cache(maxsize=1)
def _qml_decodes_svg() -> bool:
    """Descobre, executando, se o runtime consegue decodificar SVG."""
    if QML is None:
        return False
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8">'
        '<rect width="8" height="8" fill="#22d3ee"/></svg>'
    )
    with tempfile.TemporaryDirectory(prefix="steamzero-svg-probe-") as tmp:
        root = Path(tmp)
        (root / "probe.svg").write_text(svg, encoding="utf-8")
        (root / "probe.qml").write_text(
            "import QtQuick\n"
            "Item {\n"
            "    Image { id: img; source: 'probe.svg' }\n"
            "    Timer {\n"
            "        interval: 200; running: true; repeat: false\n"
            "        onTriggered: Qt.exit(img.status === Image.Ready ? 0 : 3)\n"
            "    }\n"
            "}\n",
            encoding="utf-8",
        )
        completed = subprocess.run(
            [str(QML), str(root / "probe.qml")],
            capture_output=True,
            text=True,
            env=_qml_environment(),
            timeout=60,
            check=False,
        )
    return completed.returncode == 0


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


# Marcado como visual porque é onde o runtime existe de verdade: o job
# `quality` gastava 76 s tentando provisionar Qt via apt e terminava com
# "qml6 indisponível", então estes harnesses nunca rodaram no CI. A imagem
# canônica do gate visual traz o Qt fixado por digest.
@pytest.mark.visual
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
        "check_scene_containers.qml",
        # Navegação por controle do AURA Launcher. Capacidade separada da AURA
        # UI: mora em seu próprio diretório e não promove o estado dela.
        "launcher/check_launcher_home.qml",
        "launcher/check_launcher_game_page.qml",
        "launcher/check_launcher_shell.qml",
        "launcher/check_launcher_accessibility.qml",
        "launcher/check_launcher_covers.qml",
        "check_asset_color_transform.qml",
        "check_glass_panel.qml",
        "check_scene_motion.qml",
        "check_scene_surfaces.qml",
        "check_theme_studio_canvas.qml",
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
    if harness in _SVG_HARNESSES and not _qml_decodes_svg():
        pytest.skip("runtime sem plugin de imagem SVG; o harness carrega asset .svg")
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
def test_darkbutton_stays_readable_on_the_light_theme(tmp_path: Path) -> None:
    """P0-1/P0-2 da auditoria: DarkButton legível no tema claro.

    O label segue a paleta do pai (nada de texto claro hardcodado sobre fundo
    claro) e o texto renderiza escuro sobre o fundo claro: o harness salva a
    cena e este teste conta os pixels escuros dentro do retângulo do botão da
    sidebar (x220-420, y100-148 no canvas 640x300).
    """
    output = tmp_path / "darkbutton-theme.png"
    _run_qml("check_darkbutton_theme.qml", f"--capture-output={output}")
    from PIL import Image

    im = Image.open(output).convert("RGB")
    dark = 0
    for y in range(100, 148):
        for x in range(220, 420):
            r, g, b = im.getpixel((x, y))
            if 0.299 * r + 0.587 * g + 0.114 * b < 115:
                dark += 1
    assert dark > 40, (
        f"texto do botão não aparece escuro sobre o fundo claro (pixels escuros: {dark})"
    )


@pytest.mark.skipif(QML is None, reason="qml6 não está instalado neste host")
def test_media_effect_layer_refuses_a_surface_without_a_decode_ceiling() -> None:
    """Uma superfície que esquece o teto de decode não carrega.

    O teto é `required` justamente porque o esquecimento seria silencioso: a
    mídia apareceria igual e o custo só surgiria como rolagem travada num
    aparelho que o autor da superfície talvez não tenha. Este teste guarda a
    garantia contra o conserto tentador — devolver um valor padrão à propriedade
    faria o erro de carregamento sumir junto com a proteção.
    """
    qml_directory = ROOT / "src" / "steamzero" / "ui" / "qml"
    with tempfile.TemporaryDirectory(prefix="steamzero-decode-ceiling-") as tmp:
        probe = Path(tmp) / "probe.qml"
        probe.write_text(
            "import QtQuick\n"
            f'import "{qml_directory.as_uri()}"\n'
            "Item {\n"
            '    MediaEffectLayer { source: "cover.png" }\n'
            "    Timer { interval: 50; running: true; onTriggered: Qt.exit(0) }\n"
            "}\n",
            encoding="utf-8",
        )
        completed = subprocess.run(
            [str(QML), str(probe)],
            cwd=ROOT,
            env=_qml_environment(),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    assert completed.returncode != 0, (
        "MediaEffectLayer aceitou uma superfície sem teto de decode declarado\n"
        f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    )
    assert "Required property decodeSize was not initialized" in completed.stderr, (
        "a recusa deve nomear o teto de decode, senão o autor da superfície não "
        f"sabe o que declarar\nstderr:\n{completed.stderr}"
    )


@pytest.mark.skipif(QML is None, reason="qml6 não está instalado neste host")
def test_media_effect_layer_composes_with_the_advanced_renderer() -> None:
    """O caminho de produção compõe: Qt >= 6.5 publica a capacidade e o launcher a passa.

    Sem este teste, todo o gate de mídia rodava no caminho degradado. As camadas
    que só existem para alimentar o MultiEffect (textura intermediária e máscara
    gradiente) nunca eram exercitadas com um consumidor real, e um gate delas
    passaria igual estando errado nos dois sentidos.
    """
    _run_qml("check_media_effect_layer.qml", "--steamzero-qtquick-effects")


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


@pytest.mark.visual
def test_controls_profile_card_never_shows_green_without_proof() -> None:
    """G45 — a tela precisa separar perfil salvo, traduzido e valendo.

    O perfil de controle era resolvido, gravado e desenhado por ninguém, então
    o usuário não tinha como distinguir "escolhi um perfil" de "o perfil vale no
    emulador". O harness percorre os oito estados publicados e cobra a regra que
    importa: só `applied` pode ficar verde. `pending-write` tem todos os bindings
    resolvidos e mesmo assim não é pronto — o arquivo ainda não existe.

    Sem `skip`: um verde num host onde nada foi renderizado é exatamente como a
    regressão de ícones da a37 atravessou os gates (G13).
    """
    if QML is None:
        pytest.fail(
            f"{DIAG_VISUAL_ENVIRONMENT}: qml6 ausente. Os estados do cartão de "
            "perfil de controle não podem ser verificados sem runtime QML, e "
            "declarar verde sem renderizar é o defeito que a G45 registra."
        )
    completed = subprocess.run(
        [str(QML), "tests/qml/check_controls_profile_card.qml"],
        cwd=ROOT,
        env=_qml_environment(),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    _assert_qml_clean(completed, "check_controls_profile_card.qml")
