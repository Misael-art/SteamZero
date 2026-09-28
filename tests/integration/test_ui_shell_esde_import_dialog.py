# SPDX-License-Identifier: GPL-3.0-or-later
"""RC-01 (UX-05/UX-07, 4ª fatia) — o diálogo "Importar tema ES-DE" do SHELL.

É o segundo exemplar desse diálogo no produto. O primeiro vive em
`ThemeEditorPanel.qml` (corrigido na 3ª fatia); este vive em `Main.qml:2879`, aberto
por um botão da área de diagnósticos da seção Sistema (`Main.qml:6427`). Nada testava
este caminho: os `objectName` `theme-import-esde-*` não aparecem em arquivo de teste
algum antes desta fatia, e é por isso que a mesma classe de defeito sobreviveu aqui.

A diferença de bancada em relação à 3ª fatia é o ponto central: o painel recebe
`request`/`requestAction` **injetados**, então o harness anterior pôde stubear a
ponte. O shell não — `Main.qml:967` fala por `XMLHttpRequest` com `shell.apiUrl`.
Aqui a ponte é um servidor real em loopback, e os contratos que `requestAction`
resolve vêm de `desktop_contracts.handheld_ui_contracts()`, a mesma função que o
produto publica em `/status`. Stub de contrato aqui seria exatamente o erro que a
RC-01 combate.

O que é exercitado, com eventos reais de teclado:

* abrir → examinar → preencher → navegar → publicar/cancelar;
* o corpo que excede a banda (24 esquemas de 48 px ≈ 1 150 px de conteúdo contra
  uma moldura de ~560 px) tem de ser rolável, e as ações têm de estar acessíveis
  **sem** que o teste toque em `contentY`;
* rótulo que não cabe no controle (nome de esquema com 72 caracteres) não pode
  empurrar a moldura nem sair dela sem revelação pelo próprio foco;
* recusa visível e ações alcançáveis depois do erro; rede caída não deixa o
  diálogo inútil;
* 48 px por alvo, foco visível, escala de texto pela alavanca real do produto
  (`dashboard.accessibility.visualScale`), erro e recuperação;
* a banda é o `Flickable` que clipa, não o `ScrollView` que o embrulha. Medido:
  com `bottomPadding` de 60 px as duas alturas diferem exatamente por esse
  padding (491 contra 431), e o `ScrollView` nem expõe `contentY`. Comparar com a
  moldura externa dava um oráculo 60 px mais tolerante que a tela: a reprovação
  da suíte integral anunciava "4 px fora" de um alvo 64 px abaixo do pé da área
  recortada;
* `test_10_a_banda_que_muda_mantem_o_foco_revelado` fecha o teorema que faltava:
  revelar pelo foco é um instantâneo ligado a `onActiveFocusItemChanged`, e a
  banda da seção Sistema muda DEBAIXO de um foco que não mudou (a faixa de
  atenção do `/status` tira 94 px, os cartões de diagnóstico crescem a coluna, a
  janela é redimensionada). Sem revalidação, o controle focado fica fora da tela
  com folga de rolagem disponível — é o vermelho que a suíte integral cobrava sob
  carga, reproduzido aqui deterministicamente em 5 s, sem carga.

Papéis dos testes, espelhando o gate da 3ª fatia para que as duas provas sejam
comparáveis:

* as guardas de intenção leem o harness e rodam **sem Qt** — são a guarda contra
  "consertar" a reprovação trocando tecla real por chamada de volta, atraso fixo,
  rolagem manual ou stub da ponte;
* `test_a_jornada_esde_do_shell_cabe_no_viewport_dado` (`visual`) roda a suíte
  inteira no runtime QML e reprova se qualquer cenário falhar **ou se qualquer
  função deixar de aparecer como `PASS`** — a prova de que o denominador rodou;
* `test_alvos_de_48_px_e_escala_de_texto_no_dialogo_do_shell` (`visual`) mede a
  moldura real em três escalas;
* `test_a_escala_de_texto_publicada_muda_a_geometria_do_dialogo` (`visual`) é a
  asserção de não-vazio daquela medição: se a escala não move a geometria, as três
  leituras seriam a mesma leitura;
* `test_capturas_de_evidencia_da_jornada_do_shell` (`visual`) publica PNG +
  geografia + ambiente + saída da cena **antes** das asserções, no diretório que o
  CI anexa;
* `test_o_contrato_de_captura_reprova_vazio_ausente_e_corte` prova, sem Qt, que a
  asserção de captura acima não é decorativa.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))

from qml_capture_runner import (  # noqa: E402
    CanonicalEnvironment,
    CaptureError,
    assert_not_empty,
    parse_messages,
)
from steamzero.adapters.desktop_contracts import handheld_ui_contracts  # noqa: E402

HARNESS = ROOT / "tests" / "qml" / "check_shell_esde_import_dialog_journey.qml"
CAPTURE = ROOT / "tests" / "qml" / "capture_shell_esde_import_dialog.qml"
CONFIG = ROOT / "build" / "ui-shell-esde-import-dialog.json"
LOGS = ROOT / "build" / "qml-logs"
EVIDENCE_DIR = ROOT / "build" / "visual-evidence" / "shell-esde-import"

#: Fundo declarado pelas cenas de captura; contra ele "imagem uniforme" deixa de
#: ser imagem (`capture_shell_esde_import_dialog.qml`).
BACKGROUND = "#071019"

TOKEN = "jornada-esde-shell"

#: Nome do `TestCase` no harness: entra no padrão de `PASS` abaixo.
SUITE = "ShellEsdeImportJourney"

#: Denominador da suíte. O driver exige cada função como `PASS` na saída do
#: `qmltestrunner`: renomear, excluir ou ver uma função pulada reprova aqui, em
#: vez de deixar o verde encolher em silêncio.
FUNCTIONS = (
    "test_01_o_botao_real_abre_o_modal_e_o_foco_entra_no_corpo",
    "test_02_examinar_pela_rota_real_publica_os_esquemas",
    "test_03_teclas_reais_de_d_pad_percorrem_o_dialogo_com_foco_visivel",
    "test_04_tab_e_shift_tab_reais_nao_saem_do_modal",
    "test_05_as_setas_e_backspace_editam_sem_roubar_a_navegacao",
    "test_06_publicar_pela_tecla_real_exerce_a_rota_e_recupera",
    "test_07_escape_e_cancelar_fecham_sem_gravar_nada",
    "test_08_o_rodape_fica_na_banda_com_conteudo_que_excede",
    "test_09_escala_de_texto_nao_corta_a_moldura",
    "test_10_a_banda_que_muda_mantem_o_foco_revelado",
)

#: 21 frases: o `detail` que o host devolve numa recusa de conversão. O envelope
#: do produto tem `title` curto e i18n, e `errorMessage()` do shell prefere
#: `title` (lido em `Main.qml`), então o aviso do corpo mostraria só a frase
#: curta. O cenário `aviso-longo` põe o relatório no `title`, que é o único
#: caminho real por que texto comprido chega ao corpo do diálogo — e é por isso
#: que ele existe separado de `recusa`.
_REFUSAL_DETAIL = " | ".join(
    f"Esquema {index:02d} recusado: o arquivo de tema declara um caminho absoluto "
    "fora da pasta do tema e nada foi copiado."
    for index in range(1, 22)
)

_REFUSAL_TITLE = "A importação do tema ES-DE foi recusada"

#: Alavancas declarativas de cada cenário. O harness não conhece nomes de
#: cenário: lê contagem de esquemas, desfecho do apply, tamanho do aviso, tamanho
#: dos rótulos e escala — e a expectativa do desfecho, que ele confirma por
#: impressão.
#:
#: `chega_em_importar` é expectativa do **teste**, não alavanca da cena: declara se
#: a jornada alcança a tecla real em Importar e, portanto, se um POST a `/apply` é
#: devido. No estado vazio o produto mantém o botão desabilitado (sem esquema
#: selecionado não há o que publicar), e aí a prova honesta é o inverso: nenhum POST.
SCENARIOS: dict[str, dict[str, object]] = {
    "tipico": {
        "esquemas": 24,
        "aplicar": "ok",
        "aviso": "curto",
        "nomes": "curtos",
        "chega_em_importar": True,
        "espera": {"fechar": True, "aviso": False},
    },
    "sem-esquema": {
        "esquemas": 0,
        # Inerte por construção: com `esquemas: 0` o botão não habilita e a ponte
        # nunca é chamada. Mantido para o payload ser o mesmo das recusas.
        "aplicar": "recusa",
        "aviso": "curto",
        "nomes": "curtos",
        "chega_em_importar": False,
        "espera": {"fechar": False, "aviso": True},
    },
    "recusa": {
        "esquemas": 24,
        "aplicar": "recusa",
        "aviso": "curto",
        "nomes": "curtos",
        "chega_em_importar": True,
        "espera": {"fechar": False, "aviso": True},
    },
    "aviso-longo": {
        "esquemas": 24,
        "aplicar": "recusa",
        "aviso": "longo",
        "nomes": "curtos",
        "chega_em_importar": True,
        "espera": {"fechar": False, "aviso": True},
    },
    "nomes-longos": {
        "esquemas": 24,
        "aplicar": "ok",
        "aviso": "curto",
        "nomes": "longos",
        "chega_em_importar": True,
        "espera": {"fechar": True, "aviso": False},
    },
    "falha-de-rede": {
        "esquemas": 24,
        "aplicar": "rede",
        "aviso": "curto",
        "nomes": "curtos",
        "chega_em_importar": True,
        "espera": {"fechar": False, "aviso": True},
    },
}

#: `(viewport, cenário)` efetivamente medidos. Os dois viewports cobrem o
#: compacto (1280x800 é o handheld largo) nos cenários que mudam a forma do
#: diálogo; os demais correm no compacto, onde o corte acontece.
JORNADA = (
    ("949x593", "tipico"),
    ("949x593", "sem-esquema"),
    ("949x593", "recusa"),
    ("949x593", "aviso-longo"),
    ("949x593", "nomes-longos"),
    ("949x593", "falha-de-rede"),
    ("1280x800", "tipico"),
    ("1280x800", "aviso-longo"),
)

CAPTURE_NAMES = (
    "1-compacto-aberto",
    "2-compacto-24-esquemas",
    "3-compacto-nome-focado",
    "4-compacto-recusa-com-aviso",
    "5-largo-recusa-com-aviso",
)

#: Cena de captura → cenário da ponte. `aviso-longo` é o que produz o corpo que
#: passa da banda com recusa; `nomes-longos` é o que produz texto que não cabe.
CAPTURE_CENARIOS = {
    "1-compacto-aberto": "tipico",
    "2-compacto-24-esquemas": "tipico",
    "3-compacto-nome-focado": "nomes-longos",
    "4-compacto-recusa-com-aviso": "aviso-longo",
    "5-largo-recusa-com-aviso": "aviso-longo",
}


def _qt6_binaries() -> tuple[str | None, str | None]:
    runner = next(
        (
            str(candidate)
            for candidate in (
                Path("/usr/lib/qt6/bin/qmltestrunner"),
                Path("/usr/lib64/qt6/bin/qmltestrunner"),
            )
            if candidate.is_file() and os.access(candidate, os.X_OK)
        ),
        shutil.which("qmltestrunner6"),
    )
    qml = next(
        (
            str(candidate)
            for candidate in (
                Path("/usr/lib/qt6/bin/qml"),
                Path("/usr/lib64/qt6/bin/qml"),
            )
            if candidate.is_file() and os.access(candidate, os.X_OK)
        ),
        shutil.which("qml6"),
    )
    return runner, qml


RUNNER, QML = _qt6_binaries()


def _environment(**overrides: str) -> dict[str, str]:
    """Ambiente canônico do gate visual, declarado — não herdado do host.

    `CanonicalEnvironment` é o mesmo ambiente que produz as baselines versionadas
    das cenas de painel (fonte empacotada isolada, locale e DPI fixos). No host
    existem 828 fontes no fontconfig; na imagem do gate não existe nenhuma, e sem
    isolamento o texto sai como tofu com geometria correta — captura que não prova
    nada. `QML_XHR_ALLOW_FILE_READ` é exigido pelo padrão dos harnesses de jornada
    do shell, que recebem a porta da ponte por arquivo efêmero em `build/`, como
    faz `check_credential_journey_e2e.qml`.
    """
    environment = CanonicalEnvironment().to_env()
    environment["QML_XHR_ALLOW_FILE_READ"] = "1"
    environment.update({key: value for key, value in overrides.items() if value})
    return environment


def _scheme(index: int, *, long_names: bool) -> dict[str, object]:
    """Entrada fiel ao payload real de `theme_import_esde_inspect`.

    O produto devolve `id`, `name`, `scheme` e `isMonochrome` (lido em
    `desktop_dashboard.py:1848-1861`). O `name` longo é o caminho honesto para
    texto que não cabe no controle: 72 caracteres de rótulo de esquema, que o
    delegate pode elidir, espremer ou empurrar para fora da moldura conforme a
    implementação — medido, não afirmado.
    """
    name = (
        f"Esquema {index:02d} - variação de contraste derivada do fundo "
        "com nome propositalmente longo"
        if long_names
        else f"Esquema {index:02d}"
    )
    return {
        "id": f"esquema-{index}",
        "name": name,
        "scheme": name,
        "isMonochrome": index % 3 == 0,
    }


def _error_envelope(scenario: dict[str, object]) -> dict[str, object]:
    title = _REFUSAL_DETAIL if scenario["aviso"] == "longo" else _REFUSAL_TITLE
    return {
        "error": {
            "code": "E-THEME-ESDE-REFUSAL",
            "title": title,
            "detail": _REFUSAL_DETAIL,
            "what": "POST recusado pela ponte de cena.",
            "impact": "Nenhum tema foi criado; o tema ativo permanece inalterado.",
            "autoAction": "",
            "manualAction": "Corrija o caminho do tema e examine novamente.",
            "probableCause": "Cena controlada pelo teste.",
            "operationId": "",
        }
    }


def _status_payload(scenario: dict[str, object]) -> dict[str, object]:
    """Um `/status` mínimo com a forma que o `Main.qml` consome.

    Não é o payload do produto: é a menor leitura que ainda exercita os bindings
    reais. `uiContracts` é o catálogo **verdadeiro** de `desktop_contracts`, para
    que `requestAction` resolva `theme.import.esde.*` pela rota publicada em vez de
    fingir um contrato — sem isso o shell reprova por contrato ausente e o teste
    mede outra coisa.
    """
    return {
        "truthState": "ready",
        "desiredProfile": "handheld-desktop",
        "appliedProfile": "handheld-desktop",
        "observedProfile": "handheld-desktop",
        "effectiveProfile": "handheld-desktop",
        "recommendedProfile": "handheld-desktop",
        "statusReasons": [],
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
            "accessibility": {
                "reducedMotion": False,
                "highContrast": False,
                #: A alavanca de escala do produto: `Main.qml:38-40` liga
                #: `_fallbackAccessibility` a este bloco, `ThemeBridge.qml:31-34`
                #: a converte em `hostVisualScale` (limitado a [1, 2]) e
                #: `Main.qml:83` a expõe como `scaledTextSize()`. Escala medida
                #: por aqui é escala real, não `QT_SCALE_FACTOR` improvisado.
                "visualScale": scenario["escala"],
            },
            "components": [],
            "steam": [],
            "sync": {
                "pending": 0,
                "conflicted": 0,
                "done": 0,
                "items": [],
                "dependency": "Cena da 4ª fatia; nenhuma mutação exposta.",
            },
            "doctor": {"state": "healthy", "checks": []},
            "playtime": {"schemaVersion": 1, "totalPlayedSeconds": 0, "games": []},
            "collections": {
                "schemaVersion": 1,
                "favorites": [],
                "tags": [],
                "collections": [],
            },
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
                "contextLabel": "Cena da 4ª fatia",
                "platforms": [],
                "jobs": [],
            },
            "steamGameplay": {"schemaVersion": 1, "games": [], "environment": []},
            "uiContracts": handheld_ui_contracts(),
        },
    }


class _JourneyHandler(BaseHTTPRequestHandler):
    """Ponte da jornada: `/status` publica contratos; inspecionar e importar respondem.

    Os contadores em `_JourneyState` são a prova de que a tecla exercitou a rota
    real: um `verify()` sem eles aceitaria um diálogo que nunca chamou a bridge.
    """

    state: _JourneyState

    def _autorizado(self) -> bool:
        # `Main.qml:987` envia `X-SteamZero-Token` em toda requisição. Exigir aqui
        # é o que faz o verde provar a rota autenticada, e não um POST anônimo.
        return self.headers.get("X-SteamZero-Token") == self.state.token

    def do_GET(self) -> None:
        if self.path.split("?")[0] != "/status":
            self._send(404, '{"error":{"code":"E-CENA","title":"rota fora da cena"}}')
            return
        self.state.status_calls += 1
        self._send(200, json.dumps(_status_payload(self.state.scenario)))

    def do_POST(self) -> None:
        if not self._autorizado():
            self.state.unauthorized += 1
            self._send(
                401,
                json.dumps(
                    {
                        "error": {
                            "code": "E-TOKEN",
                            "title": "token ausente",
                            "detail": "a jornada não passou pela rota autenticada",
                        }
                    }
                ),
            )
            return
        path = self.path.split("?")[0]
        body = self._body()
        if path == "/theme/import/esde/inspect":
            self.state.inspect_calls.append(body)
            count = int(self.state.scenario["esquemas"])  # type: ignore[arg-type]
            long_names = self.state.scenario["nomes"] == "longos"
            self._send(
                200,
                json.dumps(
                    {
                        "source": str(body.get("source", "")),
                        "schemes": [
                            _scheme(index, long_names=long_names) for index in range(1, count + 1)
                        ],
                        "unsupportedSlots": [],
                    }
                ),
            )
            return
        if path == "/theme/import/esde/apply":
            self.state.apply_calls.append(body)
            outcome = str(self.state.scenario["aplicar"])
            if outcome == "recusa":
                self._send(409, json.dumps(_error_envelope(self.state.scenario)))
                return
            if outcome == "rede":
                # Sem resposta: o `XMLHttpRequest` do Qt encerra em erro de rede
                # e o diálogo tem de sobreviver a isso com a edição preservada.
                self.close_connection = True
                return
            self._send(200, json.dumps({"ok": True, "themeId": "tema-importado"}))
            return
        self._send(404, '{"error":{"code":"E-CENA","title":"rota fora da cena"}}')

    def _body(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            parsed = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _send(self, code: int, body: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args: object) -> None:
        pass


class _JourneyState:
    def __init__(self, scenario: str, escala: float = 1.0) -> None:
        self.name = scenario
        self.scenario = dict(SCENARIOS[scenario], escala=escala)
        self.token = TOKEN
        self.status_calls = 0
        self.unauthorized = 0
        self.inspect_calls: list[dict[str, object]] = []
        self.apply_calls: list[dict[str, object]] = []


class _Bridge(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    #: Porta real depois do bind em 0. Chama-se `porta` e não `server_port`
    #: porque `http.server.server_bind()` atribui `self.server_port` no `__init__`,
    #: e uma propriedade sem setter reprova a construção da ponte antes do teste.
    @property
    def porta(self) -> int:
        return int(self.server_address[1])

    def handle_error(self, request: object, client_address: object) -> None:
        # A cena `falha-de-rede` fecha a conexão sem responder; o servidor
        # registraria traceback em stderr e o gate de ruído do Qt reprovaria por
        # infraestrutura, não por contrato.
        pass


def _start_bridge(scenario: str, escala: float = 1.0) -> tuple[_Bridge, _JourneyState]:
    state = _JourneyState(scenario, escala)

    class _Bound(_JourneyHandler):
        pass

    _Bound.state = state
    bridge = _Bridge(("127.0.0.1", 0), _Bound)
    threading.Thread(target=bridge.serve_forever, daemon=True).start()
    return bridge, state


def _log_path(label: str) -> Path:
    LOGS.mkdir(parents=True, exist_ok=True)
    return LOGS / f"shell-esde-{label}.txt"


def _gravar_log(
    caminho: Path, command: list[str], completed: subprocess.CompletedProcess[str]
) -> str:
    """Log estável por execução: o usuário audita artefatos, não narração."""
    corpo = "\n".join(
        [
            f"# comando: {' '.join(command)}",
            f"# returncode: {completed.returncode}",
            "",
            "--- stdout ---",
            completed.stdout or "",
            "--- stderr ---",
            completed.stderr or "",
        ]
    )
    caminho.write_text(corpo, encoding="utf-8")
    return str(caminho)


def _run_qmltestrunner(
    bridge: _Bridge,
    scenario: str,
    viewport: str,
    *,
    escala: float = 1.0,
    label: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Config efêmera + `qmltestrunner` sobre o harness, com log estável."""
    assert RUNNER is not None, "QML-VISUAL-ENVIRONMENT-001: qmltestrunner ausente"
    tag = label or f"{viewport}-{scenario}-e{escala}"
    _write_config(bridge.porta, scenario, viewport, escala)
    command = [str(RUNNER), "-input", str(HARNESS)]
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=_environment(),
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
        )
    finally:
        CONFIG.unlink(missing_ok=True)
    log = _gravar_log(_log_path(tag), command, completed)
    completed.stdout += f"\n# log desta execucao: {log}\n"
    return completed


def _write_config(port: int, scenario: str, viewport: str, escala: float) -> None:
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    base = SCENARIOS[scenario]
    payload: dict[str, object] = {
        "apiUrl": f"http://127.0.0.1:{port}",
        "apiToken": TOKEN,
        "viewport": viewport,
        "escala": escala,
        "esquemas": base["esquemas"],
        "nomesLongos": base["nomes"] == "longos",
        "avisoLongo": base["aviso"] == "longo",
        "aplicar": base["aplicar"],
        "espera": base["espera"],
    }
    CONFIG.write_text(json.dumps(payload), encoding="utf-8")


def _assert_qml_clean(completed: subprocess.CompletedProcess[str], label: str) -> None:
    """Nenhum QML warning proibido: o mesmo contrato dos gates anteriores."""
    forbidden = [m.text for m in parse_messages(completed.stderr) if m.forbidden]
    assert not forbidden, f"{label}: stderr proibido do Qt\n" + "\n".join(forbidden)


def _assert_denominador(stdout: str, label: str) -> None:
    """Cada função da suíte apareceu como `PASS` — nada encolheu em silêncio.

    `qmltestrunner` devolve 0 também quando não executa função alguma; sem esta
    leitura o denominador poderia ser zero e o verde continuar igual.

    A linha real é `PASS   : qmltestrunner::ShellEsdeImportJourney::test_01_…()`:
    o `()` final faz parte do nome impresso, e compará-lo cru com `FUNCTIONS` não
    achava NENHUMA das nove — o que se apresentava como "funções fora do
    denominador" exatamente quando todas tinham passado.
    """
    presentes = {
        linha.rsplit("::", 1)[1].strip().removesuffix("()")
        for linha in stdout.splitlines()
        if linha.strip().startswith("PASS") and "::" in linha
    }
    faltando = [nome for nome in FUNCTIONS if nome not in presentes]
    assert not faltando, (
        f"{label}: funções fora do denominador (não rodaram, foram puladas ou "
        f"renomeadas): {faltando}\npresentes: {sorted(presentes)}"
    )
    assert "cleanupTestCase" in presentes, (
        f"{label}: a leitura do denominador não casou nenhuma linha real do "
        f"qmltestrunner; presentes = {sorted(presentes)}"
    )


#: `QT_MESSAGE_PATTERN` é `%{type}|%{message}`, então a linha real chega como
#: `debug|GEOMETRIA|…`: a âncora de início de linha não casa nada, e o `console.log`
#: da cena vai para o **stderr** (o ambiente canônico força isso), não para o
#: stdout. Ambas as formas estão erradas aqui e produziram o mesmo sintoma — um
#: dicionário vazio, que parece "a cena não declarou nada" quando a cena declarou
#: tudo. A precedent é `test_esde_import_dialog_compact.py`, que casa a substring
#: e alimenta o parser com stdout + stderr concatenados.
_GEOMETRIA = re.compile(r"GEOMETRIA\|(?P<cena>[^|\n]+)\|(?P<campos>[^\n]*)")

#: Um inteiro de pixel declarado pela cena; `ausente` não é número e reprova a
#: asserção de escala em vez de virar comparação contra zero.
_NUMERO = re.compile(r"^\d+$")


def _geometrias(saida: str) -> dict[str, dict[str, str]]:
    """`GEOMETRIA|<cena>|chave=valor|…` → dicionário por cena.

    A cena declara a própria janela; sem essa declaração nenhuma asserção de
    banda ou de recorte é verificável, porque o teste teria de adivinhar o
    viewport que renderizou.
    """
    parsed: dict[str, dict[str, str]] = {}
    for match in _GEOMETRIA.finditer(saida):
        campos: dict[str, str] = {}
        for part in match.group("campos").split("|"):
            if "=" in part:
                key, value = part.split("=", 1)
                campos[key.strip()] = value.strip()
        parsed[match.group("cena")] = campos
    return parsed


def _retangulo(campos: dict[str, str], chave: str, cena: str) -> tuple[int, int, int, int]:
    assert chave in campos, f"{cena}: campo {chave!r} não declarado: {sorted(campos)}"
    parts = campos[chave].split(",")
    assert len(parts) == 4, f"{cena}/{chave} deveria ser x,y,largura,altura: {campos[chave]}"
    return tuple(int(float(part)) for part in parts)  # type: ignore[return-value]


def _janela(campos: dict[str, str], cena: str) -> tuple[int, int]:
    assert "janela" in campos, f"{cena}: a cena não declarou a própria janela"
    partes = campos["janela"].split("x")
    assert len(partes) == 2, f"{cena}/janela deveria ser LxA: {campos['janela']}"
    return int(partes[0]), int(partes[1])


def _dentro_da_moldura(campos: dict[str, str], regiao: str, cena: str) -> None:
    """`rodape`/`acao` inteiros dentro da moldura que a própria cena declarou."""
    x, y, largura, altura = _retangulo(campos, regiao, cena)
    mx, my, mw, mh = _retangulo(campos, "moldura", cena)
    assert largura > 0 and altura > 0, (
        f"{cena}/{regiao} com tamanho zero ({largura}x{altura}): um controle "
        "invisível não pode ser alcançado por tecla nenhuma"
    )
    assert x >= mx - 1 and y >= my - 1, (
        f"{cena}/{regiao} começa fora da moldura {mx},{my},{mw},{mh}: {campos[regiao]}"
    )
    assert x + largura <= mx + mw + 1, (
        f"{cena}/{regiao} passa da direita da moldura: {x}+{largura} > {mx}+{mw}"
    )
    assert y + altura <= my + mh + 1, (
        f"{cena}/{regiao} passa do pé da moldura: {y}+{altura} > {my}+{mh} — "
        "é o corte que a 4ª fatia existe para corrigir"
    )


# ---------------------------------------------------------------------------
# Guardas de intenção: rodam sem Qt.
# ---------------------------------------------------------------------------


def _harness_source() -> str:
    assert HARNESS.is_file(), f"{HARNESS} não existe"
    return HARNESS.read_text(encoding="utf-8")


def test_o_harness_usa_teclas_reais_e_a_rota_autenticada() -> None:
    """O contrato de viewport só vale medido com teclado real e bridge real."""
    fonte = _harness_source()
    for exiga in (
        "keyPress",
        "keyRelease",
        "Qt.Key_Down",
        "Qt.Key_Up",
        "Qt.Key_Tab",
        "Qt.Key_Backtab",
        "Qt.Key_Escape",
        "Qt.Key_Space",
        "Qt.Key_Backspace",
        "shell.esdeImportDialogControl",
        "shell.apiUrl",
        "shell.apiToken",
        'shell.sectionIndexOf("system")',
    ):
        assert exiga in fonte, f"o harness perdeu {exiga!r}: sem isso a prova não é real"


def test_o_harness_nao_pode_stubear_a_ponte() -> None:
    """O shell fala por XHR; stub de `requestAction` reescreveria a jornada."""
    fonte = _harness_source()
    for proibido in ("function requestAction", "function request(", "onClicked:"):
        assert proibido not in fonte, (
            f"o harness contém {proibido!r}: no shell a ação sai por XMLHttpRequest "
            "pela rota publicada, e stubar isso prova o stub, não o produto"
        )


def test_o_harness_nao_pode_rolar_na_mao_dos_atestes() -> None:
    """`contentY` escrito pelo teste invalidaria a prova de rolagem load-bearing."""
    fonte = _harness_source()
    corpo = fonte.split("TestCase")[1] if "TestCase" in fonte else fonte
    atribuicoes = re.findall(r"^\s*(?:[A-Za-z_][\w.]*\.)?contentY\s*=", corpo, re.M)
    assert not atribuicoes, (
        f"o harness escreve em contentY ({len(atribuicoes)}x); a banda tem de ser "
        "alcançada com tecla real"
    )
    for proibido in (".scrollTo(", "positionViewAt"):
        assert proibido not in fonte, f"{proibido} é rolagem manual disfarçada"


def test_a_espera_e_observavel_com_limite_e_falha() -> None:
    """Nada de espera sem limite, nem de atraso fixo no lugar do estado."""
    fonte = _harness_source()
    assert "function until(" in fonte, (
        "o harness não usa espera observável com limite e falha explícita; um "
        "diálogo que nunca abre viraria timeout silencioso ou verde falso"
    )
    assert "requestActivate" in fonte, (
        "sem janela ativa não há foco de teclado, e nenhuma tecla chega a controle "
        "algum — a asserção viraria medição do nada"
    )
    assert "Qt.callLater" not in fonte, (
        "o harness chama a revelação do foco à mão: quem revela é o produto "
        "(`Main.qml:837-845`), e o teste só pode ESPERAR o efeito dele"
    )
    assert not re.search(r"wait\(\s*(?:[3-9]\d\d|\d{4,})\s*\)", fonte), (
        "o harness usa intervalo fixo grande em vez de condição observável"
    )


def test_a_ponte_publica_o_contrato_verdadeiro_e_nao_um_stub() -> None:
    """`uiContracts` vem de `desktop_contracts`, a única fonte do produto."""
    fonte = Path(__file__).read_text(encoding="utf-8")
    assert "handheld_ui_contracts()" in fonte, (
        "a ponte precisa publicar os contratos reais; sem eles `requestAction` "
        "reprova por contrato ausente e o teste mede outra coisa"
    )
    assert '"theme.import.esde.inspect"' in fonte or "theme/import/esde/inspect" in fonte
    assert len(_REFUSAL_DETAIL) > 1200, (
        f"relatório de recusa com {len(_REFUSAL_DETAIL)} caracteres não excede "
        "nenhuma banda; o cenário virou decoração"
    )
    assert len(JORNADA) >= 8, f"a matriz de cenários encolheu: {JORNADA}"
    assert set(CAPTURE_CENARIOS) == set(CAPTURE_NAMES), "captura e cenários divergiram"
    #: A asserção inversa de `/apply` precisa de uma cena que a exercite; sem ela,
    #: "nenhum POST no estado vazio" seria uma asserção sobre nada.
    sem_publicar = [
        nome for nome, alavancas in SCENARIOS.items() if alavancas["chega_em_importar"] is False
    ]
    assert sem_publicar == ["sem-esquema"], (
        f"a expectativa de importação inalcansável mudou de dono: {sem_publicar}"
    )
    assert SCENARIOS["sem-esquema"]["esquemas"] == 0, (
        "o cenário sem POST ao /apply não é mais o de estado vazio: "
        f"{SCENARIOS['sem-esquema']['esquemas']} esquemas"
    )


def test_a_captura_de_evidencia_existe_e_usa_dados_locais() -> None:
    """A cena de captura existe, não baixa nada e só escreve no diretório pedido."""
    assert CAPTURE.is_file(), f"{CAPTURE} não existe"
    fonte = CAPTURE.read_text(encoding="utf-8")
    assert "--output-dir=" in fonte, "a cena recebe o diretório do teste"
    assert not re.search(r"https?://", fonte), (
        "a cena de captura não pode buscar nada na rede (o endereço da ponte chega "
        "pelo arquivo de configuração efêmero)"
    )
    assert "esdeImportDialogControl" in fonte, (
        "a cena captura o diálogo do shell, não um quadro genérico"
    )


# ---------------------------------------------------------------------------
# A jornada em si: roda com Qt, marcada como `visual`.
# ---------------------------------------------------------------------------


@pytest.mark.visual
@pytest.mark.parametrize("viewport,cenario", JORNADA)
def test_a_jornada_esde_do_shell_cabe_no_viewport_dado(viewport: str, cenario: str) -> None:
    """abrir → examinar → preencher → navegar → publicar/cancelar, com teclas reais.

    O vermelho desta fatia é medido aqui. No `Main.qml:2879` atual o diálogo não
    declara `height`, o corpo é um `ColumnLayout { anchors.fill: parent }` sem
    mecanismo de rolagem e as ações vivem no fim desse fluxo: com 24 esquemas o
    botão "Importar" fica abaixo do pé da moldura, e nenhuma tecla o alcança.
    """
    if RUNNER is None:
        pytest.fail(
            "QML-VISUAL-ENVIRONMENT-001: qmltestrunner ausente. A jornada do diálogo "
            "ES-DE do shell não pode ser verificada sem runtime QML; declarar verde "
            "sem renderizar é o defeito que a RC-01 combate."
        )
    bridge, state = _start_bridge(cenario)
    esperado = SCENARIOS[cenario]["espera"]
    try:
        completed = _run_qmltestrunner(bridge, cenario, viewport)
    finally:
        bridge.shutdown()
        bridge.server_close()

    assert state.unauthorized == 0, (
        "a ponte devolveu 401 por token: a jornada não passou pela rota autenticada "
        f"de `Main.qml` ({state.unauthorized} requisições)"
    )
    assert state.status_calls >= 1, (
        "a ponte nunca serviu /status; o shell não leu os contratos publicados"
    )
    assert state.inspect_calls, (
        "nenhum POST a /theme/import/esde/inspect: o clique em Examinar não exerceu "
        "a rota publicada"
    )
    if SCENARIOS[cenario]["chega_em_importar"] is True:
        assert state.apply_calls, (
            "nenhum POST a /theme/import/esde/apply: a jornada não chegou a "
            f"Importar pelas teclas reais ({viewport}/{cenario})"
        )
    else:
        assert not state.apply_calls, (
            f"{viewport}/{cenario}: o estado vazio publicou {len(state.apply_calls)}x "
            "sem nenhum esquema selecionado — o botão Importar tem de manter-se "
            "desabilitado, e um POST nesta cena é importação fantasma"
        )
    assert completed.returncode == 0, (
        f"jornada {viewport}/{cenario} reprovou (status={state.status_calls}, "
        f"inspect={len(state.inspect_calls)}, apply={len(state.apply_calls)}, "
        f"espera={esperado}):\n{completed.stdout}\n{completed.stderr}"
    )
    _assert_denominador(completed.stdout, f"jornada {viewport}/{cenario}")
    _assert_qml_clean(completed, f"jornada {viewport}/{cenario}")
    for chave, valor in esperado.items():  # type: ignore[union-attr]
        esperado_marca = f"DESBFECHO {chave}={int(bool(valor))}"
        assert esperado_marca in completed.stdout, (
            f"jornada {viewport}/{cenario}: o desfecho {chave}={valor} não foi "
            f"confirmado pelo harness\n{completed.stdout}"
        )


@pytest.mark.visual
@pytest.mark.parametrize("escala", ("1.0", "1.25", "1.5"))
def test_alvos_de_48_px_e_escala_de_texto_no_dialogo_do_shell(escala: str) -> None:
    """Os 48 px por alvo medidos **dentro do shell**, na moldura real do diálogo.

    A 3ª fatia mediu o painel; aqui a medição é no diálogo de `Main.qml`, com a
    escala publicada pelo `/status` — o mesmo caminho por que o Plasma pede
    tipografia maior. A não-vacuidade dessa escolha é assertada separadamente em
    `test_a_escala_de_texto_publicada_muda_a_geometria_do_dialogo`.
    """
    if RUNNER is None:
        pytest.fail("QML-VISUAL-ENVIRONMENT-001: qmltestrunner ausente")
    bridge, state = _start_bridge("tipico", float(escala))
    try:
        completed = _run_qmltestrunner(
            bridge,
            "tipico",
            "949x593",
            escala=float(escala),
            label=f"48px-escala-{escala}",
        )
    finally:
        bridge.shutdown()
        bridge.server_close()
    assert completed.returncode == 0, (
        f"escala {escala} reprovou (apply={len(state.apply_calls)}):\n"
        f"{completed.stdout}\n{completed.stderr}"
    )
    _assert_denominador(completed.stdout, f"escala {escala}")
    _assert_qml_clean(completed, f"escala {escala}")
    cena = _geometrias(completed.stdout).get("dialogo")
    assert cena is not None, (
        f"cena 'dialogo' ausente na escala {escala}: {sorted(_geometrias(completed.stdout))}"
    )
    assert _janela(cena, "dialogo") == (949, 593), (
        f"escala {escala}: a janela medida não é a declarada pelo teste ({cena.get('janela')})"
    )
    for regiao in ("rodape", "acao"):
        _, _, largura, altura = _retangulo(cena, regiao, f"escala {escala}")
        assert largura >= 48 and altura >= 48, (
            f"UX-05: {regiao} com {largura}x{altura} px na escala {escala} "
            f"({cena[regiao]}) — o alvo mínimo de toque é 48 px"
        )


@pytest.mark.visual
def test_a_escala_de_texto_publicada_muda_a_geometria_do_dialogo() -> None:
    """Escala 1.0 → 1.5 tem de mover o texto e o extento rolável; senão não foi medida.

    Asserção separada da medição de 48 px porque os vermelhos significam coisas
    diferentes: alvo abaixo de 48 px é defeito de toque; geometria imune à escala é
    o diálogo ignorando a preferência de tipografia do host — e as três leituras de
    escala seriam a mesma leitura repetida.

    O que **não** serve de prova é a altura visível do corpo: ela é travada pelo teto
    do diálogo (`Math.min(root.height - 32, 560)`, o padrão da casa em
    `credentialDialog`) e na janela do Deck esse teto já é a própria janela. Medir
    por ali dava 474 px nas duas escalas mesmo com o produto obedecendo — foi o que
    este teste fez antes. As grandezas que a escala publicada obriga a mover são o
    rótulo do corpo e o extento rolável (`conteudo=`), e é nelas que bate.
    """
    if RUNNER is None:
        pytest.fail("QML-VISUAL-ENVIRONMENT-001: qmltestrunner ausente")
    leituras: dict[str, dict[str, int]] = {}
    for escala in ("1.0", "1.5"):
        bridge, state = _start_bridge("tipico", float(escala))
        try:
            completed = _run_qmltestrunner(
                bridge,
                "tipico",
                "949x593",
                escala=float(escala),
                label=f"escala-par-{escala}",
            )
        finally:
            bridge.shutdown()
            bridge.server_close()
        assert completed.returncode == 0, (
            f"escala {escala} reprovou:\n{completed.stdout}\n{completed.stderr}"
        )
        cena = _geometrias(completed.stdout).get("dialogo")
        assert cena is not None, f"cena 'dialogo' ausente na escala {escala}"
        assert state.apply_calls, f"escala {escala} sem apply pela rota real"
        rotulo = cena.get("rotulo")
        conteudo = cena.get("conteudo")
        assert rotulo is not None and conteudo is not None, (
            f"escala {escala}: a cena não declarou rotulo/conteudo — sem eles a "
            f"leitura de escala não é verificável: {sorted(cena)}"
        )
        assert _NUMERO.match(rotulo) and _NUMERO.match(conteudo), (
            f"escala {escala}: rotulo={rotulo} conteudo={conteudo}, esperados inteiros"
        )
        leituras[escala] = {"rotulo": int(rotulo), "conteudo": int(conteudo)}
    for grandeza in ("rotulo", "conteudo"):
        antes = leituras["1.0"][grandeza]
        depois = leituras["1.5"][grandeza]
        assert depois > antes, (
            f"a altura de {grandeza} não respondeu à escala publicada pelo /status "
            f"(1.0 → {antes} px, 1.5 → {depois} px): o diálogo ignora a preferência "
            "de tipografia do host, e as medições por escala seriam a mesma leitura "
            "repetida"
        )


@pytest.mark.visual
def test_capturas_de_evidencia_da_jornada_do_shell(tmp_path: Path) -> None:
    """PNG + geografia + ambiente + saída da cena, publicados ANTES das asserções.

    Publicar primeiro é o contrato desta fatia: quando uma asserção reprova, a
    imagem que a desmente é exatamente a que o CI precisa anexar. O diretório é
    `build/visual-evidence/**`, o glob do job `qml-visual-linux`.
    """
    if QML is None:
        pytest.fail("QML-VISUAL-ENVIRONMENT-001: qml6 ausente para a cena de captura")
    output = tmp_path / "capturas"
    output.mkdir()
    publicados: dict[str, subprocess.CompletedProcess[str]] = {}
    for cenario in sorted(set(CAPTURE_CENARIOS.values())):
        bridge, _estado = _start_bridge(cenario)
        command = [
            str(QML),
            str(CAPTURE),
            "--",
            f"--output-dir={output}",
            f"--cenario={cenario}",
        ]
        try:
            _write_config(bridge.porta, cenario, "949x593", 1.0)
            completed = subprocess.run(
                command,
                cwd=ROOT,
                env=_environment(),
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
            completed.stdout += (
                "\n# log: "
                + _gravar_log(_log_path(f"captura-{cenario}"), command, completed)
                + "\n"
            )
        finally:
            CONFIG.unlink(missing_ok=True)
            bridge.shutdown()
            bridge.server_close()
        publicados[cenario] = completed
    _publicar(output, tmp_path, publicados)

    # `console.log` da cena sai pelo stderr no ambiente canônico; somar os dois é
    # o que o precedent da 3ª fatia faz. Ler só stdout dava um mapa de geografia
    # vazio — que a asserção de abaixo reportava como "a cena não declarou",
    # invertendo a culpa: quem não leu foi o teste, não a cena.
    saida_das_cenas = "\n".join((c.stdout or "") + (c.stderr or "") for c in publicados.values())
    for cenario, completed in publicados.items():
        assert completed.returncode == 0, (
            f"cena do cenário {cenario} reprovou:\n{completed.stdout}\n{completed.stderr}"
        )
        _assert_qml_clean(completed, f"cena {cenario}")

    from PIL import Image

    cenas = _geometrias(saida_das_cenas)
    for nome in CAPTURE_NAMES:
        arquivo = output / f"{nome}.png"
        assert arquivo.is_file() and arquivo.stat().st_size > 0, (
            f"{nome} não foi capturada: {sorted(p.name for p in output.iterdir())}"
        )
        with Image.open(arquivo) as imagem:
            imagem.load()
            dimensoes = imagem.size
        assert nome in cenas, f"{nome} não declarou geografia; nada é verificável"
        declarada = _janela(cenas[nome], nome)
        assert dimensoes == declarada, f"{nome}: PNG mede {dimensoes}, a cena declarou {declarada}"
        assert_not_empty(arquivo, background=BACKGROUND)
        # Sem `if regiao in …`: a opção de não declarar o rodapé ou a ação
        # apagaria a asserção em silêncio, e foi exatamente assim que o defeito
        # sobreviveu — nada neste diálogo exigia que o alvo coubesse na moldura.
        for regiao in ("rodape", "acao"):
            _dentro_da_moldura(cenas[nome], regiao, nome)


def _publicar(
    output: Path, tmp_path: Path, publicados: dict[str, subprocess.CompletedProcess[str]]
) -> None:
    """Evidência escrita em `build/visual-evidence/**` antes de qualquer asserção."""
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    for arquivo in sorted(output.glob("*.png")):
        shutil.copyfile(arquivo, EVIDENCE_DIR / arquivo.name)
    (EVIDENCE_DIR / "geometria.json").write_text(
        json.dumps(
            _geometrias(
                "\n".join((c.stdout or "") + (c.stderr or "") for c in publicados.values())
            ),
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (EVIDENCE_DIR / "ambiente.json").write_text(
        json.dumps(
            {
                "binario": str(QML),
                "cwd": str(ROOT),
                "tmp": str(tmp_path),
                "cenarios": sorted(publicados),
                "ambiente": sorted(_environment()),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (EVIDENCE_DIR / "saida-da-cena.txt").write_text(
        "\n".join(
            f"===== {cenario} =====\n{(c.stdout or '')}{(c.stderr or '')}"
            for cenario, c in publicados.items()
        ),
        encoding="utf-8",
    )


def test_o_contrato_de_captura_reprova_vazio_ausente_e_corte(tmp_path: Path) -> None:
    """Prova de mordida, sem Qt: o contrato de captura acima reprova de verdade.

    Se algum destes passar, a asserção de captura é decorativa: imagem uniforme,
    conteúdo ausente, rodapé abaixo do pé da moldura, alvo além da direita e alvo
    de largura zero.
    """
    from PIL import Image

    vazio = tmp_path / "uniforme.png"
    Image.new("RGBA", (640, 560), BACKGROUND).save(vazio)
    with pytest.raises(CaptureError):
        assert_not_empty(vazio, background=BACKGROUND)

    faltando = tmp_path / "inexistente.png"
    assert not faltando.exists()
    with pytest.raises(FileNotFoundError):
        Image.open(faltando)

    with pytest.raises(AssertionError):
        _dentro_da_moldura(
            {"moldura": "0,0,640,560", "rodape": "20,610,600,48"}, "rodape", "cena-sintetica"
        )

    with pytest.raises(AssertionError):
        _dentro_da_moldura(
            {"moldura": "0,0,640,560", "acao": "700,500,140,48"}, "acao", "cena-sintetica"
        )

    with pytest.raises(AssertionError):
        _dentro_da_moldura(
            {"moldura": "0,0,640,560", "acao": "20,500,0,48"}, "acao", "cena-sintetica"
        )

    with pytest.raises(AssertionError):
        _dentro_da_moldura({"moldura": "0,0,640,560"}, "rodape", "cena-sintetica")

    #: O parser entra na prova de mordida com a linha EXATA que a cena publica.
    #: `QT_MESSAGE_PATTERN` é `%{type}|%{message}`, então nada chega com
    #: `GEOMETRIA` no início da linha; testar só os dicionários montados à mão
    #: deixou o parser ler zero cenas enquanto esta prova continuava verde, e o
    #: sintoma apareceu como "a cena não declarou geografia".
    linha_real = (
        "debug|GEOMETRIA|2-compacto-24-esquemas|capturado=Main|janela=949x593"
        "|moldura=155,0,640,593|corpo=161,32,628,555|rodape=155,559,640,34"
        "|acao=709,1646,80,48|esquemas=24|aviso=0|cenario=tipico"
    )
    parseada = _geometrias(linha_real)
    assert list(parseada) == ["2-compacto-24-esquemas"], (
        f"a linha real não foi parseada: {parseada}"
    )
    assert parseada["2-compacto-24-esquemas"]["acao"] == "709,1646,80,48"
    #: E a mordida no caso que originou a fatia: com 24 esquemas o Importar cai a
    #: y=1646 numa moldura que termina em y=593. Se isto NÃO reprovar, o contrato
    #: de captura não enxerga o defeito que veio medir.
    with pytest.raises(AssertionError):
        _dentro_da_moldura(parseada["2-compacto-24-esquemas"], "acao", "2-compacto-24-esquemas")
    assert _geometrias("qml: nenhuma linha declarada aqui") == {}
