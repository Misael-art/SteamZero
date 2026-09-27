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
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

QML = shutil.which("qml6")
ROOT = Path(__file__).resolve().parents[2]

#: Ambiente visual ausente. Não é motivo para verde.
#:
#: Um `skip` aqui produz suíte verde num host onde NADA visual foi verificado —
#: e foi exatamente assim que a regressão de ícones da a37 atravessou os gates.
#: O marcador `visual` roteia este módulo ao gate canônico, que reprova sem
#: runtime em vez de transformar a ausência em verde.
DIAG_VISUAL_ENVIRONMENT = "QML-VISUAL-ENVIRONMENT-001"
pytestmark = pytest.mark.visual


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


@pytest.fixture(autouse=True)
def _require_qml_runtime() -> None:
    """Ambiente sem QML reprova o gate visual com diagnóstico explícito."""
    if QML is None:
        pytest.fail(
            f"{DIAG_VISUAL_ENVIRONMENT}: qml6/qml ausente; o harness visual não pode ser verificado"
        )


# Harnesses que carregam um asset SVG do pacote. A imagem canônica do gate
# declara qt6-svg; a sonda continua sendo uma defesa contra uma imagem publicada
# sem o plugin que o contrato visual exige.
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
        "launcher/check_launcher_activation.qml",
        "launcher/check_launcher_accessibility.qml",
        "launcher/check_launcher_covers.qml",
        "launcher/check_launcher_session_osd.qml",
        "launcher/check_launcher_save_state_gallery.qml",
        "launcher/check_launcher_session_peripherals.qml",
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
        # UX-01: a tinta dos avisos sobre superfície fixa é calculada, e o
        # cálculo precisa sobreviver ao tema escuro e ao alto contraste.
        "check_warning_surface_contrast.qml",
        # Prova Image.Ready de cada asset empacotado, não apenas o caminho.
        "check_packaged_assets.qml",
        # Identidade AURA no editor: preview no ThemeBridge, cancelar restaura.
        "check_theme_editor_aura.qml",
        "check_theme_editor_asset_recipes.qml",
        "check_responsive_components.qml",
    ],
)
def test_qml_handheld_harness_offscreen(harness: str) -> None:
    if harness in _SVG_HARNESSES and not _qml_decodes_svg():
        pytest.fail(
            f"{DIAG_VISUAL_ENVIRONMENT}: runtime sem plugin de imagem SVG; "
            f"{harness} carrega asset .svg"
        )
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


def test_media_effect_layer_composes_with_the_advanced_renderer() -> None:
    """O caminho de produção compõe: Qt >= 6.5 publica a capacidade e o launcher a passa.

    Sem este teste, todo o gate de mídia rodava no caminho degradado. As camadas
    que só existem para alimentar o MultiEffect (textura intermediária e máscara
    gradiente) nunca eram exercitadas com um consumidor real, e um gate delas
    passaria igual estando errado nos dois sentidos.
    """
    _run_qml("check_media_effect_layer.qml", "--steamzero-qtquick-effects")


def test_editorial_library_renders_at_logical_scale_200() -> None:
    """A composição editorial continua utilizável em 4K físico a 200% lógico."""
    _run_qml("check_editorial_library.qml", scale_factor=2)


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


#: Contagem de GET /status servidos pela ponte de cena da RC-01. O servidor é de
#: sessão (porta estável), então o estado da sequência vive aqui e é zerado pelo
#: fixture de teste.
_CENTRAL_LOADING_CALLS: list[str] = []
_CENTRAL_LOADING_LOCK = threading.Lock()


def _central_loading_status() -> dict[str, object]:
    """Um /status mínimo, mas com a forma que o `Main.qml` consome.

    Não é o payload do produto: é a menor leitura que ainda exercita os bindings
    reais. Se uma chave obrigatória faltar, o Qt reclama em stderr e
    `_assert_qml_clean` reprova — que é exatamente o contrato que a RC-01 abriu.
    """
    return {
        "truthState": "stale",
        "desiredProfile": "handheld-desktop",
        "appliedProfile": None,
        "observedProfile": None,
        "effectiveProfile": "handheld-desktop",
        "recommendedProfile": "handheld-desktop",
        "statusReasons": ["A leitura da cena encontrou perfil desejado não aplicado."],
        "recoveryRequired": False,
        "independentRuntime": True,
        "observation": {
            "checkedEffects": [],
            "unavailableEffects": [],
            "ambiguousCandidates": [],
            "errors": [],
        },
        "context": {
            "deviceKind": "deck-lcd",
            "displays": [],
            "capabilities": [],
            "conflicts": [],
        },
        "dashboard": {
            "accessibility": {"reducedMotion": False, "highContrast": False},
            "components": [
                {
                    "id": "dolphin",
                    "name": "Dolphin",
                    "description": "Emulador de Wii e GameCube",
                    "iconName": "dolphin-emu",
                    "systems": ["Wii", "GameCube"],
                    "state": "installed",
                    "statusLabel": "Instalado",
                    "versionLabel": "2407",
                    "targetVersion": "2407",
                    "detail": "Dolphin 2407 medido pela ponte.",
                    "blockedReason": "",
                    "action": {
                        "kind": "detail",
                        "label": "Detalhes",
                        "enabled": False,
                    },
                }
            ],
            "steam": [],
            "sync": {
                "pending": 0,
                "conflicted": 0,
                "done": 0,
                "items": [],
                "dependency": "Cena RC-01; nenhuma mutação exposta.",
            },
            "doctor": {"state": "healthy", "checks": []},
            "playtime": {"schemaVersion": 1, "totalPlayedSeconds": 0, "games": []},
            "collections": {"schemaVersion": 1, "favorites": [], "tags": [], "collections": []},
            "libraryHealth": {
                "schemaVersion": 1,
                "state": "unchecked",
                "counts": {
                    "verified": 0,
                    "suspect": 0,
                    "missing": 0,
                    "error": 0,
                    "unavailable": 0,
                    "unchecked": 0,
                },
            },
            "emulation": {
                "schemaVersion": 1,
                "truthState": "ready",
                "contextLabel": "Cena RC-01",
                "platforms": [],
                "jobs": [],
            },
            "steamGameplay": {"schemaVersion": 1, "games": [], "environment": []},
            "uiContracts": {"schemaVersion": 1, "states": [], "actions": [], "byId": {}},
        },
    }


class _CentralLoadingHandler(BaseHTTPRequestHandler):
    """Ponte de cena da RC-01: leitura boa, renovação que falha, recuperação.

    A primeira resposta é atrasada de propósito. Sem atraso o `Main.qml` já
    estaria em `ready` quando o harness olhasse, e o guard de sobreposição e a
    fase `loading` seriam declarados verdes sem nunca terem sido observados.
    """

    first_response_delay_seconds = 0.5

    def do_GET(self) -> None:
        if self.path.split("?")[0] != "/status":
            self._send(404, "rota fora da cena")
            return
        with _CENTRAL_LOADING_LOCK:
            _CENTRAL_LOADING_CALLS.append(self.path)
            call_number = len(_CENTRAL_LOADING_CALLS)
        if call_number == 2:
            self._send(
                500,
                json.dumps(
                    {
                        "error": {
                            "code": "E-STATUS-SCENE",
                            "title": "A renovação do estado falhou",
                            "detail": "A central não pôde reler o host nesta tentativa.",
                            "what": "Leitura GET /status recusou.",
                            "impact": "O último estado lido permanece na tela.",
                            "autoAction": "",
                            "manualAction": "Tente novamente.",
                            "probableCause": "Cena controlada pelo teste.",
                            "operationId": "",
                        }
                    }
                ),
            )
            return
        if call_number == 1:
            time.sleep(self.first_response_delay_seconds)
        self._send(200, json.dumps(_central_loading_status()))

    def _send(self, code: int, body: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args: object) -> None:
        pass


@pytest.mark.visual
def test_central_loading_phases_are_observable_offscreen() -> None:
    """RC-01 (UX-02) — a Central tem de ser legível enquanto carrega.

    O `/status` do host real leva segundos; durante esse intervalo a Home
    publicava os fallbacks como se fossem medições ("Não instalado", "Nenhum
    jogo publicado ainda", "Nenhuma pendência" em verde). Este teste roda o
    `Main.qml` contra uma ponte que demora, falha e recupera, e cobra as quatro
    fases no objeto vivo.

    Sem runtime QML o teste reprova: verde sem renderização é o modo como a
    regressão de ícones já atravessou os gates (G13).
    """
    if QML is None:
        pytest.fail(
            f"{DIAG_VISUAL_ENVIRONMENT}: qml6 ausente. As fases de carregamento "
            "da Central não podem ser verificadas sem runtime QML, e declarar "
            "verde sem renderizar é o defeito que a RC-01 combate."
        )
    port = _start_central_loading_bridge()
    completed = _run_central_loading_harness(port)
    with _CENTRAL_LOADING_LOCK:
        served = len(_CENTRAL_LOADING_CALLS)
    assert served == 3, f"a cena esperava três GET /status, a ponte serviu {served}"
    _assert_qml_clean(completed, "ponte de cena da RC-01")


def _run_central_loading_harness(port: int, *extra: str) -> subprocess.CompletedProcess[str]:
    """Roda o harness da RC-01 contra a ponte de cena na porta dada.

    O `--` é obrigatório: sem ele o `qml6` trata cada argumento como outro
    arquivo de componente e gasta um load falho por parâmetro.
    """
    return subprocess.run(
        [
            str(QML),
            "tests/qml/check_central_loading.qml",
            "--",
            "--steamzero-api",
            f"http://127.0.0.1:{port}",
            "--steamzero-token",
            "cena-rc01",
            *extra,
        ],
        cwd=ROOT,
        env=_qml_environment(),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


@pytest.mark.visual
@pytest.mark.parametrize("phase", ("loading", "stale"))
def test_central_loading_frames_are_capturable(tmp_path: Path, phase: str) -> None:
    """RC-01 — o quadro que as asserções descrevem pode virar evidência.

    A fase aferida tem de ser gravável sem depender de timing humano: a
    capturing é pedida ao harness, que só sai depois de o frame compor. Um PNG
    em branco passaria por evidência, então a cena real também é medida.
    """
    if QML is None:
        pytest.fail(f"{DIAG_VISUAL_ENVIRONMENT}: qml6 ausente; nenhum frame é gravável")
    output = tmp_path / f"central-{phase}.png"
    completed = _run_central_loading_harness(
        _start_central_loading_bridge(),
        f"--capture-phase={phase}",
        f"--capture-output={output}",
    )
    _assert_qml_clean(completed, f"captura {phase} da Central")
    assert output.is_file() and output.stat().st_size > 0, (
        f"harness pediu o quadro `{phase}` e nenhuma imagem foi gravada em {output}"
    )
    from PIL import Image

    image = Image.open(output)
    image.load()
    assert image.width >= 1280 and image.height >= 800, (
        f"o quadro `{phase}` saiu com {image.width}x{image.height}, menor que a janela"
    )
    # Um frame ainda não composto seria uma superfície vazia de uma cor só.
    colors = image.convert("RGB").getcolors(maxcolors=1_000_000)
    distinct = len(colors) if colors is not None else 1_000_000
    assert distinct > 8, f"o quadro `{phase}` tem {distinct} cores: não mostra a cena aferida"


def _start_central_loading_bridge() -> int:
    """Sobe uma ponte por teste: a sequência de respostas é por instância."""
    host = "127.0.0.1"
    for port in range(43000, 44000):
        try:
            server = HTTPServer((host, port), _CentralLoadingHandler)
        except OSError:
            continue
        # A sequência é contada por módulo, não por servidor: sem este reset,
        # um segundo teste veria "4a chamada" e a cena mudaria de significado.
        with _CENTRAL_LOADING_LOCK:
            del _CENTRAL_LOADING_CALLS[:]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return port
    raise RuntimeError("nenhuma porta livre para a ponte de cena da RC-01")
