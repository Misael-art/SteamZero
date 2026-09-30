# SPDX-License-Identifier: GPL-3.0-or-later
"""RC-01 (UX-05/UX-07, corte ES-DE na shell) — a resposta TARDIA do importador ES-DE.

Gate irmão de `test_ui_shell_retrofe_import_late_response.py`, aplicado ao importador
ES-DE do painel de edição (`ThemeEditorPanel.qml`, trio `*EsdeImport()`), que em `c4975979` NÃO tem
o contrato de geração que a fatia RetroFE estabeleceu (`grep -c esdeImportGeneration
ThemeEditorPanel.qml` = 0). O vermelho desta fatia é a ausência desse contrato: a
resposta que chega depois de a superfície mudar escreve por cima dela, nas
callbacks de `inspectEsdeImport()` e `applyEsdeImport()`; o fechamento baixa a
bandeira de um pedido vivo (`resetEsdeImport()`) e a recusa por dedup não tem
rollback (o despacho arma e não devolve).

As três anteriores de ES-DE (`check_esde_import_dialog_compact_viewport.qml`,
`check_shell_esde_import_dialog_journey.qml`) exercitam o diálogo RAIZ de `Main.qml`,
ou injetam `requestAction` e chamam as callbacks DENTRO do stub: sincronia não
exercita atraso, e por construção a resposta nunca chega depois de a superfície ter
mudado. Aqui a ponte é um `ThreadingHTTPServer` real em loopback que DORME antes de
responder, e o cliente é o `XMLHttpRequest` do produto (o `request()` de
`Main.qml`, `xhr.timeout`).

O que se prova, cena por cena, está no cabeçalho de
`tests/qml/check_shell_esde_import_late_response.qml`. Este arquivo acrescenta as
duas leituras que nenhum `verify()` do QML pode fazer sozinho:

* **a ordem em que a ponte SERVIU as respostas** — sem ela, "o pedido mais novo
  venceu" pode ser apenas a sorte de o lento ter respondido primeiro;
* **a re-listagem de temas como evento da ponte** — `refreshThemeList()`
  dispara `GET /theme/list` na callback de sucesso do apply. Num diálogo já
  fechado isso é invisível na superfície; a asserção é "nenhum `GET /theme/list`
  depois do último `POST /theme/import/esde/apply`", e
  o contrafactual é a jornada do `test_01`, onde o `GET /theme/list` TEM de aparecer
  depois do `POST` — sem ele a asserção seria satisfeita por ausência de medição.

Por que `ThreadingHTTPServer` e não `HTTPServer`: com uma thread só, o atraso da
primeira requisição serializaria a segunda e a ordem de chegada jamais se inverteria.
O atraso que inverte a ordem É o mecanismo do teste — `test_a_ordem_de_resposta_inverte`
confere que ele ocorreu, em vez de presumi-lo.

Papéis: as guardas de intenção rodam sem Qt e impedem que o verde volte por stub da
ponte, tecla simulada, rolagem na mão do teste ou atraso fixo no lugar do estado. O
portão `visual` roda a suíte QML inteira uma vez e reconcile as contagens.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))

from qml_capture_runner import CanonicalEnvironment, parse_messages  # noqa: E402
from steamzero.adapters.desktop_contracts import handheld_ui_contracts  # noqa: E402

HARNESS = ROOT / "tests" / "qml" / "check_shell_esde_import_late_response.qml"
#: O produto lido por guarda, nunca pelo harness: a equivalência de um mutante é
#: propriedade da habilitação real dos botões, e morre em `Main.qml`.
MAIN_QML = ROOT / "src" / "steamzero" / "ui" / "qml" / "Main.qml"
CONFIG = ROOT / "build" / "ui-shell-esde-import-late.json"
LOGS = ROOT / "build" / "qml-logs"

TOKEN = "resposta-tardia-esde-shell"

#: Nome do `TestCase` no harness.
SUITE = "ShellEsdeImportLateResponse"

#: Denominador da suíte. Renomear, excluir ou pular uma função reprova aqui, em vez
#: de deixar o verde encolher em silêncio.
FUNCTIONS = (
    "test_01_a_rota_real_do_shell_examina_e_importa_como_editavel",
    "test_02_fechar_com_pedido_em_voo_nao_recebe_a_resposta_tardia",
    "test_03_o_pedido_mais_novo_nao_perde_para_o_anterior",
    "test_04_publicar_em_voo_e_fechar_nao_anuncia_sucesso_tardio",
    "test_05_a_recusa_devolve_a_bandeira_e_nao_descarta_o_resultado_corrente",
    "test_06_a_repeticao_recusada_com_pedido_revogado_nao_trava_o_dialogo",
    "test_07_a_rota_raiz_examina_e_importa_com_o_aviso_de_sucesso",
    "test_08_fechar_a_rota_raiz_com_pedido_em_voo_nao_recebe_a_resposta_tardia",
    "test_09_aplicar_na_rota_raiz_em_voo_e_fechar_nao_anuncia_sucesso_tardio",
    "test_10_a_recusa_na_rota_raiz_devolve_a_bandeira_e_nao_trava_o_dialogo",
)

#: As alavancas de atraso. `lenta` responde DEPOIS de `rapida` apesar de ter saído
#: antes; `curta` é a jornada sem atraso significativo; `revogada` (4 000 ms) só
#: existe para as cenas de recusa: fechar, reabrir, escrever e clicar consome bem
#: mais que os 1 500 ms da `lenta`, e uma janela curta trocaria a alegação ("payload
#: idêntico recusado com o pedido ainda em voo") por "o teste andou devagar". Os
#: valores não são trocáveis: `test_a_ordem_de_resposta_inverte` reprova se a
#: inversão não acontecer.
ORIGENS: dict[str, dict[str, object]] = {
    "curta": {
        "fonte": "/media/esde/tema-curta",
        "esquemas": 2,
        "prefixo": "curta-esquema-",
        "atraso_ms": 120,
    },
    "rapida": {
        "fonte": "/media/esde/tema-rapida",
        "esquemas": 1,
        "prefixo": "rapida-esquema-",
        "atraso_ms": 120,
    },
    "lenta": {
        "fonte": "/media/esde/tema-lenta",
        "esquemas": 3,
        "prefixo": "lenta-esquema-",
        "atraso_ms": 1500,
    },
    "revogada": {
        "fonte": "/media/esde/tema-revogada",
        "esquemas": 2,
        "prefixo": "revogada-esquema-",
        "atraso_ms": 4000,
    },
}

#: Quantas vezes cada rota é exercitada pela suíte inteira. Contado, não afirmado:
#: o portão reconcilia com o log da ponte, e a cena de captura do `test_01` depende
#: disso para ser real.
#:
#: Os dois cliques recusados (`test_05`, `test_06`) NÃO entram nesta conta:
#: O `requestAction` devolve `false` antes de construir o `XMLHttpRequest`. A conta sobe
#: só com os examines reais (01: curta; 02: lenta; 03: lenta + rapida; 04: lenta;
#: 05: revogada + rapida; 06: revogada), e é exatamente isso que a testemunha por
#: origem reconcilia — se a recusa fosse muda apenas no cliente, a origem apareceria
#: duas vezes no log e a cena estaria provando outra coisa.
ESPERADO_INSPECT = 12
ESPERADO_APPLY = 4

#: As duas origens que `test_03` põe em voo ao mesmo tempo. Os sufixos são os
#: literais da cena (`examinar("lenta", "anterior")` /
#: `examinar("rapida", "mais-novo")`) e a composição é a do `origem()` do harness
#: (`<fonte>-<sufixo>`). A ponte atende a suíte inteira, então as cenas de atraso
#: compartilham o mesmo contador: filtrar a corrida pelo *prefixo* da alavanca
#: arrastaria o examine de `test_02` (`…-tardia`) e de `test_04` (`…-aplicar-tardio`)
#: para dentro da medição.
CORRIDA: dict[str, str] = {
    "lenta": f"{ORIGENS['lenta']['fonte']}-anterior",
    "rapida": f"{ORIGENS['rapida']['fonte']}-mais-novo",
}

_VIEWPORT = "1280x800"
_ESCALA = 1.0


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


RUNNER, _QML = _qt6_binaries()


def _environment(**overrides: str) -> dict[str, str]:
    """Ambiente canônico do gate visual, declarado — não herdado do host.

    `QML_XHR_ALLOW_FILE_READ` é exigido pelo padrão dos harnesses de jornada do
    shell, que recebem a porta da ponte por arquivo efêmero em `build/`.
    """
    environment = CanonicalEnvironment().to_env()
    environment["QML_XHR_ALLOW_FILE_READ"] = "1"
    environment.update({key: value for key, value in overrides.items() if value})
    return environment


def _alavanca(source: object) -> dict[str, object]:
    """De qual alavanca é esta origem — pelo prefixo declarado na configuração.

    Uma origem que não casa com nenhuma alavanca seria respondida com atraso
    arbitrário, e o teste deixaria de medir o que diz medir.
    """
    texto = str(source or "")
    casadas = [lever for lever in ORIGENS if texto.startswith(str(ORIGENS[lever]["fonte"]))]
    assert len(casadas) == 1, (
        f"a origem '{texto}' casa com {len(casadas)} alavancas {sorted(ORIGENS)}; "
        "as fontes precisam ser prefixos únicos (uma fonte prefixo de outra faria a "
        "resposta sair com o atraso da alavanca errada)"
    )
    return dict(ORIGENS[casadas[0]], origem=casadas[0])


def _esquema(alavanca: str, index: int) -> dict[str, object]:
    """Entrada fiel ao payload de `theme_import_esde.inspect`.

    O produto monta cada entrada com `{id, name, scheme, isMonochrome, sourceTags,
    derived, colors, assets, fidelity}` (`desktop_dashboard.py:1857-1873`); `scheme`
    é o campo canônico que o `Repeater` mostra (o texto `modelData.scheme`) e que o
    apply devolve (`applyEsdeImport()`, em `ThemeEditorPanel.qml`). O marcador da
    alavanca viaja em `scheme`/`id`/`name`
    porque é por ele que o harness distingue, na superfície, de qual pedido veio cada
    opção listada.
    """
    prefixo = str(ORIGENS[alavanca]["prefixo"])
    nome = f"{prefixo}{index:02d}"
    return {
        "id": nome,
        "name": nome,
        "scheme": nome,
        "isMonochrome": False,
        "sourceTags": 6 * index,
        "derived": ["background", "panel", "text"],
        "colors": {"background": "#101418", "panel": "#1a222c", "text": "#f2f6fb"},
        "assets": [],
        "fidelity": "palette-only",
    }


def _status_payload() -> dict[str, object]:
    """Um `/status` mínimo com a forma que o `Main.qml` consome.

    `uiContracts` é o catálogo VERDADEIRO de `desktop_contracts`, a mesma função que
    o produto publica — sem isso `requestAction` reprovaria por contrato ausente e o
    teste mediria outra coisa.
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
                "visualScale": _ESCALA,
            },
            "components": [],
            "steam": [],
            "sync": {"pending": 0, "conflicted": 0, "done": 0, "items": []},
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
                "contextLabel": "Corte ES-DE na shell",
                "platforms": [],
                "jobs": [],
            },
            "steamGameplay": {"schemaVersion": 1, "games": [], "environment": []},
            "uiContracts": handheld_ui_contracts(),
        },
    }


class _LateResponseState:
    """A ponte com memória: contadores, log ORDENADO e o atraso por alavanca."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.token = TOKEN
        self.status_calls = 0
        self.unauthorized = 0
        #: `(método, rota, origem)` na ordem em que a ponte ATENDEU — é esta lista,
        #: e não a narração do QML, que prova a inversão de ordem e a ausência de
        #: re-listagem depois do último `apply`.
        self.eventos: list[tuple[str, str, str]] = []
        #: Ordem em que cada origem foi RESPONDA DA (`served`), para o confronto
        #: direto com a ordem em que foi RECEBIDA (`received`).
        self.recebidas: list[str] = []
        self.respondidas: list[str] = []

    def registrar(self, metodo: str, rota: str, origem: str = "") -> None:
        with self.lock:
            self.eventos.append((metodo, rota, origem))

    def inspecionar(self, origem: str) -> dict[str, object]:
        alavanca = _alavanca(origem)
        time.sleep(int(str(alavanca["atraso_ms"])) / 1000)
        quantidade = int(str(alavanca["esquemas"]))
        return {
            "source": origem,
            "schemes": [
                _esquema(str(alavanca["origem"]), index) for index in range(1, quantidade + 1)
            ],
            #: Espelha `desktop_dashboard.py:1872`: `unsupported_slots()` devolve um
            #: dicionário slot→motivo (`theme_import_esde.py:195-204`). O QML não o
            #: lê, mas uma ponte com forma divergente do produto deixaria de provar
            #: a jornada real.
            "unsupportedSlots": {
                "logo": "temas ES-DE não declaram marca própria",
                "sidebar": "temas ES-DE não têm equivalente de barra lateral",
            },
        }

    def aplicar(self, origem: str, scheme: str, nome: str) -> dict[str, object]:
        alavanca = _alavanca(origem)
        time.sleep(int(str(alavanca["atraso_ms"])) / 1000)
        return {
            #: Mesmas chaves de `theme_import_esde_apply`
            #: (`desktop_dashboard.py:1908-1916`). O callback de sucesso do QML
            #: (`applyEsdeImport()`) não lê nenhuma delas; a ponte as
            #: publica para que a jornada exercite o contrato do produto, não um
            #: fantasma mais estreito.
            "themeId": f"org.steamzero.importado.{nome.lower().replace(' ', '-')}",
            "path": "/var/lib/steamzero/themes/org.steamzero.importado/theme.json",
            "scheme": scheme,
            "isMonochrome": False,
            "derived": ["background", "panel", "text"],
            "assets": [],
            "fidelity": "palette-only",
            "unsupportedSlots": {},
        }


class _LateResponseHandler(BaseHTTPRequestHandler):
    state: _LateResponseState

    def _autorizado(self) -> bool:
        # `request()` envia `X-SteamZero-Token` em toda requisição.
        return self.headers.get("X-SteamZero-Token") == self.state.token

    def do_GET(self) -> None:
        rota = self.path.split("?")[0]
        if rota == "/status":
            self.state.status_calls += 1
            self.state.registrar("GET", "/status")
            self._send(200, json.dumps(_status_payload()))
            return
        if rota == "/theme/list":
            self.state.registrar("GET", "/theme/list")
            self._send(
                200,
                json.dumps(
                    {"themes": [{"id": "org.steamzero.default", "name": "Padrão", "active": True}]}
                ),
            )
            return
        self._send(404, '{"error":{"code":"E-CENA","title":"rota fora da cena"}}')

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
        rota = self.path.split("?")[0]
        payload = self._body()
        origem = str(payload.get("source", ""))
        if rota == "/theme/import/esde/inspect":
            with self.state.lock:
                self.state.recebidas.append(origem)
            self.state.registrar("POST", rota, origem)
            corpo = self.state.inspecionar(origem)
            with self.state.lock:
                self.state.respondidas.append(origem)
            self._send(200, json.dumps(corpo))
            return
        if rota == "/theme/import/esde/apply":
            with self.state.lock:
                self.state.recebidas.append(origem)
            self.state.registrar("POST", rota, origem)
            corpo = self.state.aplicar(
                origem, str(payload.get("scheme", "")), str(payload.get("name", ""))
            )
            with self.state.lock:
                self.state.respondidas.append(origem)
            self._send(200, json.dumps(corpo))
            return
        self._send(404, '{"error":{"code":"E-CENA","title":"rota fora da cena"}}')

    def _body(self) -> dict[str, object]:
        try:
            tamanho = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            tamanho = 0
        bruto = self.rfile.read(tamanho) if tamanho else b"{}"
        try:
            lido = json.loads(bruto.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return {}
        return lido if isinstance(lido, dict) else {}

    def _send(self, codigo: int, corpo: str) -> None:
        dados = corpo.encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def log_message(self, fmt: str, *args: object) -> None:
        return


class _Bridge(ThreadingHTTPServer):
    """Multi-thread POR DESIGN: com uma thread só o atraso serializaria as
    requisições e a ordem jamais se inverteria — o teste mediria a ponte, não o
    produto."""

    daemon_threads = True
    allow_reuse_address = True

    #: Chama-se `porta` e não `server_port` porque `server_bind()` atribui
    #: `self.server_port` no `__init__`, e uma propriedade sem setter reprovaria a
    #: construção da ponte antes do teste.
    @property
    def porta(self) -> int:
        return int(self.server_address[1])

    def handle_error(self, request: object, client_address: object) -> None:
        pass


def _start_bridge() -> tuple[_Bridge, _LateResponseState]:
    state = _LateResponseState()

    class _Bound(_LateResponseHandler):
        pass

    _Bound.state = state
    bridge = _Bridge(("127.0.0.1", 0), _Bound)
    threading.Thread(target=bridge.serve_forever, daemon=True).start()
    return bridge, state


def _write_config(port: int) -> None:
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(
        json.dumps(
            {
                "apiUrl": f"http://127.0.0.1:{port}",
                "apiToken": TOKEN,
                "viewport": _VIEWPORT,
                "escala": _ESCALA,
                "origens": {
                    lever: {
                        "fonte": str(spec["fonte"]),
                        "esquemas": int(str(spec["esquemas"])),
                        "prefixo": str(spec["prefixo"]),
                    }
                    for lever, spec in ORIGENS.items()
                },
            }
        ),
        encoding="utf-8",
    )


def _log_path(label: str) -> Path:
    LOGS.mkdir(parents=True, exist_ok=True)
    return LOGS / f"shell-esde-late-{label}.txt"


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


def _gravar_eventos_da_ponte(state: _LateResponseState, label: str) -> str:
    """O log ORDENADO da ponte, gravado antes das asserções.

    As contagens que reprovam o produto precisam de um artefato que o leitor
    confira sem rodar nada: aqui estão os eventos na ordem em que a ponte atendeu,
    com a chegada e a saída de cada origem. `build/` é gitignored, então o lote
    copia este arquivo para a evidência canônica.
    """
    eventos = list(state.eventos)
    recebidas = list(state.recebidas)
    respondidas = list(state.respondidas)
    corpo = "\n".join(
        [
            f"# ponte da resposta tardia ES-DE — cena `{label}`",
            f"# status_calls={state.status_calls} unauthorized={state.unauthorized}",
            "",
            "--- atendidos (ordem em que a ponte recebeu; 0-indexado) ---",
            *(
                f"{i:02d} {metodo:<4} {rota:<32} {origem}"
                for i, (metodo, rota, origem) in enumerate(eventos)
            ),
            "",
            "--- chegadas das origens em POST ---",
            *(f"{i:02d} {origem}" for i, origem in enumerate(recebidas)),
            "",
            "--- saídas das origens em POST (depois do atraso) ---",
            *(f"{i:02d} {origem}" for i, origem in enumerate(respondidas)),
        ]
    )
    caminho = LOGS / f"shell-esde-late-{label}-ponte.txt"
    LOGS.mkdir(parents=True, exist_ok=True)
    caminho.write_text(corpo + "\n", encoding="utf-8")
    return str(caminho)


def _run_qmltestrunner(bridge: _Bridge, label: str) -> subprocess.CompletedProcess[str]:
    assert RUNNER is not None, "QML-VISUAL-ENVIRONMENT-001: qmltestrunner ausente"
    _write_config(bridge.porta)
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
    log = _gravar_log(_log_path(label), command, completed)
    completed.stdout += f"\n# log desta execucao: {log}\n"
    return completed


def _assert_qml_clean(completed: subprocess.CompletedProcess[str], label: str) -> None:
    forbidden = [m.text for m in parse_messages(completed.stderr) if m.forbidden]
    assert not forbidden, f"{label}: stderr proibido do Qt\n" + "\n".join(forbidden)


def _assert_denominador(stdout: str, label: str) -> None:
    """Cada função da suíte apareceu como `PASS` — nada encolheu em silêncio.

    A linha real é `PASS   : qmltestrunner::ShellEsdeImportLateResponse::test_01_…()`,
    com `()` no fim; compará-la crua com `FUNCTIONS` não achava nenhuma (fato da
    bancada do molde RetroFE).
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
        f"{label}: o padrão de PASS não casou nenhuma linha real; presentes = {sorted(presentes)}"
    )


_TOTAIS = re.compile(r"Totals:\s*(?P<pass>\d+) passed,\s*(?P<fal>\d+) failed")


def _assert_suite_concluida(returncode: int, stdout: str, label: str) -> None:
    """A suíte rodou até o fim; o código de saída é a contagem de falhas, não um abort.

    Medido na bancada do molde RetroFE: com o produto vermelho o `qmltestrunner`
    devolve o número de falhas e imprime `Totals: N passed, M failed`. Comparar o
    retorno com `0`/`1` reprovava pelo defeito do produto, não por quebra do
    processo, e passaria a esconder um abort de verdade (`-11`, sem `Totals:`).
    """
    casa = _TOTAIS.search(stdout)
    assert casa is not None, (
        f"{label}: a suíte não imprimiu fechamento — o runner foi morto no meio "
        f"(returncode={returncode}); o caminho do log está na própria saída, na linha "
        "`# log desta execucao:`"
    )
    falhas = int(casa.group("fal"))
    assert returncode == falhas, (
        f"{label}: returncode={returncode} não bate com as {falhas} falhas declaradas "
        f"em `Totals:`; o processo não terminou pelos próprios termos"
    )


_OBS = re.compile(r"OBS\|(?P<tag>[^|\n]+)\|(?P<campos>[^\n]*)")


def _observacoes(saida: str) -> dict[str, dict[str, str]]:
    """`OBS|<tag>|chave=valor|…` → dicionário por testemunho.

    É a ponte entre a narração do QML e as contagens da ponte: sem ler estas linhas,
    asserir "a cena chegou ao ponto de medir" seria confiar no código do teste.
    """
    lidas: dict[str, dict[str, str]] = {}
    for linha in saida.splitlines():
        casa = _OBS.search(linha)
        if not casa:
            continue
        campos = dict(
            parte.split("=", 1) for parte in casa.group("campos").split("|") if "=" in parte
        )
        lidas[casa.group("tag")] = campos
    return lidas


TESTEMUNHOS = (
    "antes-do-escape",
    "depois-da-resposta-tardia",
    "depois-do-mais-novo",
    "depois-do-anterior-tardio",
    "jornada-importada",
    "depois-do-apply-tardio",
    "instante-da-recusa-com-outro-pedido-resolvido",
    "instante-da-recusa-com-pedido-revogado",
    "raiz-jornada",
    "raiz-antes-do-escape",
    "raiz-depois-da-resposta-tardia",
    "raiz-antes-do-apply-da-jornada",
    "raiz-antes-do-escape-do-apply",
    "raiz-antes-do-apply-tardio",
    "raiz-depois-do-apply-tardio",
    "instante-da-recusa-na-raiz",
)

#: O testemunho `depois-da-resposta-do-recusado` (cena 05, depois da aterrissagem do
#: pedido recusado) NÃO entra nesta lista no estado vermelho da fatia: `verify()` do
#: QtTest interrompe a função, e a asserção vermelha da bandeira vive ANTES dele na
#: cena. Com o contrato de geração instalado a cena anda até ele; exigí-lo agora
#: trocaria o vermelho documentado por um vermelho de scaffolding.

#: O que cada testemunho da recusa tem de registrar no instante do clique recusado.
#: É a leitura de log independente do veredito do QtTest: o contrato da recusa é "o
#: clique que não disparou nada devolve a superfície ao que ela era antes do clique",
#: então `ocupado` tem de valer o que valia ANTES. Nos dois cenários ES-DE aquele
#: valor é `0`: a única forma de um clique recusado acontecer neste diálogo é depois
#: de o fechamento ter baixado a bandeira (`resetEsdeImport()`), porque os dois
#: botões despachantes (`themeImportEsdeInspect`, `themeImportEsdeApply`) são gated
#: por `esdeImportBusy` e não há segunda porta de teclado no campo de origem
#: (`themeImportEsdeSource`, ao contrário do campo RetroFE, que tem `onAccepted`).
#: Uma recusa que DEIXA a bandeira armada — o que o despacho fazia em `c4975979`, sem
#: rollback — é o vermelho lido aqui.
RECUSAS: dict[str, dict[str, str]] = {
    "instante-da-recusa-com-outro-pedido-resolvido": {"ocupado": "0"},
    "instante-da-recusa-com-pedido-revogado": {"ocupado": "0"},
    "instante-da-recusa-na-raiz": {"ocupado": "0"},
}

#: Por que cada valor é aquele, em uma linha, para a mensagem de falha não virar
#: adivinhação.
RECUSAS_DOC = {
    "instante-da-recusa-com-outro-pedido-resolvido": "o examine de payload diferente "
    "já respondeu e a bandeira vale `0` antes do clique; a recusa não pode armá-la "
    "sobre um pedido que a ponte nunca viu",
    "instante-da-recusa-com-pedido-revogado": "o fechamento revogou o único pedido em "
    "voo e baixou a bandeira; com rollback ausente ou com um falso `true` sempre, "
    "nada mais a abaixa e o diálogo congela em 'Importando…'",
    "instante-da-recusa-na-raiz": "a rota raiz arma `esdeImportBusy = true` antes de "
    "despachar (o `onClicked` de `esdeInspectButton`) e o fechamento já baixou a "
    "bandeira no `esdeImportDialog.onClosed`; sem rollback o clique recusado a "
    "rearma sobre um pedido que a ponte "
    "nunca viu, e nada mais a abaixa",
}

#: Os sufixos das origens pedidas nas cenas de recusa (ambos pela alavanca
#: `revogada`, composta como no harness: `<fonte>-<sufixo>`).
RECUSAS_DE_PONTE = (
    ("revogada", "recusada"),
    ("revogada", "revogada"),
    ("revogada", "raiz-recusada"),
)

#: O aviso de sucesso do apply raiz, lido como TRANSIÇÃO e não como nível. `1` só na
#: cena que exerce o apply com a superfície aberta (07, depois do `notify`); `0` nas
#: três leituras que o antecedem e na que sucede ao apply tardio (09). O nível isolado
#: já provou ser laranja: na corrida anterior `raiz-antes-do-escape` — cena 08, onde
#: nenhum apply acontece — registrou `toast=1`, carry do `notify` da cena 07, porque
#: `lastRequest` é estado global do shell e só o `feedbackTimer` de `Main.qml`
#: (`notify` → `feedbackTimer.restart()`) o limpa cinco segundos depois. Sem o chão
#: `0` antes do clique, o `0` depois do fechamento não afirmava nada sobre ESTE apply;
#: com ele, a cena 09 mede a ausência de um 0→1 que a cena 07 mostra ser possível.
TOAST: dict[str, str] = {
    "raiz-antes-do-apply-da-jornada": "0",
    "raiz-jornada": "1",
    "raiz-antes-do-apply-tardio": "0",
    "raiz-antes-do-escape-do-apply": "0",
    "raiz-depois-do-apply-tardio": "0",
}

#: A origem da jornada (composta como no harness). A ponte TEM de vê-la uma única
#: vez no examine e uma no apply — é o chão que mantém as contagens honestas.
JORNADA_INSPECT = f"{ORIGENS['curta']['fonte']}-jornada"


# ---------------------------------------------------------------------------
# Guardas de intenção — rodam sem Qt.
# ---------------------------------------------------------------------------


def _harness_source() -> str:
    assert HARNESS.is_file(), f"{HARNESS} não existe"
    return HARNESS.read_text(encoding="utf-8")


def test_o_harness_usa_cliques_reais_a_rota_autenticada_e_os_dois_dialogos_esde() -> None:
    fonte = _harness_source()
    for exiga in (
        "keyPress",
        "keyRelease",
        "Qt.Key_Escape",
        "shell.apiUrl",
        "shell.apiToken",
        'shell.sectionIndexOf("themes")',
        "shell.pendingRequests",
        "esdeImportDialogControl",
        "themeImportEsdeInspect",
        "themeImportEsdeApply",
        "function until(",
        "requestActivate",
        #: a segunda superfície do mesmo importador: o diálogo raiz do `Main.qml`,
        #: aberto pelo botão real da seção Sistema e lido no estado do shell.
        'shell.sectionIndexOf("system")',
        "shell.esdeImportDialogControl",
        "theme-import-esde-inspect",
        "theme-import-esde-apply",
        "shell.esdeImportSchemes",
    ):
        assert exiga in fonte, f"o harness perdeu {exiga!r}: sem isso a prova não é real"
    for nome in FUNCTIONS:
        assert f"function {nome}(" in fonte, (
            f"a função {nome} saiu do harness: o denominador encolheria em silêncio"
        )


def test_o_harness_nao_pode_stubear_a_ponte_nem_a_callback() -> None:
    """O shell fala por XHR; stub de `requestAction` provava o stub, não o produto.

    É exatamente a diferença desta fatia para as anteriores de ES-DE, que stubavam
    `requestAction` ou exercitavam o diálogo raiz de `Main.qml`.
    """
    fonte = _harness_source()
    for proibido in ("function requestAction", "function request(", "onClicked:"):
        assert proibido not in fonte, (
            f"o harness contém {proibido!r}: no shell a ação sai por XMLHttpRequest "
            "pela rota publicada"
        )
    #: Responder a um pedido chamando a callback à mão recriaria a sincronia que
    #: tornou as fatias anteriores incapazes de ver resposta tardia.
    #: A conferência é por substring do fonte inteiro, comentário incluído: citar
    #: o símbolo do produto numa nota do harness se faz sem o parêntese de chamada.
    assert "inspectEsdeImport(" not in fonte, (
        "o harness chama o importador direto: o pedido tem de sair pelo clique real "
        "(a guarda é substring e vale para comentário — cite o símbolo sem parêntese)"
    )
    assert "applyEsdeImport(" not in fonte, "mesmo motivo: importar por clique real"
    assert "shell.esdeImportGeneration" not in fonte, (
        "o harness escreve na geração do pedido: quem a move é o produto, e um harness "
        "que a manipula provaria o harness"
    )
    assert "resetEsdeImport()" in fonte, (
        "a limpeza controlada entre cenas é o que impede o vermelho de nascer da "
        "ordem do teste; sem ela a cena seguinte herda estado da anterior"
    )


def test_o_mutante_equivalente_do_apply_na_raiz_e_pino_por_reachability() -> None:
    """M9 sobreviveu à bateria, e a causa é do produto, não do gate.

    A bateria raiz trocou `root.esdeImportBusy = ocupadoAntes` do rollback do apply
    por `= true` e o gate ficou verde (`8 passed`, log `73-…raiz.log`). Não é
    asserção frouxa: é mutante EQUIVALENTE. Escrever `true` só difere de
    `ocupadoAntes` quando o clique encontra a bandeira ARMADA, e recusa por
    `actionIsPending` exige um segundo clique — que o próprio produto proíbe: o
    botão Importar só se habilita com a bandeira baixada, e o despacho a arma antes
    de pedir. Portanto `ocupadoAntes` vale `false` em todo clique alcançável.

    O pino abaixo é o que separa isso de "cobertura ausente": se a habilitação
    mudar, a equivalência cai e esta guarda quebra, exigindo a cena que hoje seria
    inatingível. O caso análogo do examine NÃO é equivalente (a cena 10 o alcança:
    lá `esdeImportSchemeIndex` não participa da habilitação), e a bateria detectou o
    rollback ausente do examine (M8, vermelho).
    """
    fonte = MAIN_QML.read_text(encoding="utf-8")
    #: O recorte é o botão Importar até o próximo `Dialog`. Procurar no arquivo inteiro
    #: seria satisfeito pelo handler do examine, que tem as MESMAS três linhas na MESMA
    #: ordem — a guarda precisaria falhar se só o apply mudasse.
    inicio = fonte.find("id: esdeApplyButton")
    fim = fonte.find("Dialog {\n        id: castPinDialog", inicio)
    assert inicio != -1 and fim > inicio, (
        "o botão Importar do diálogo raiz, ou o `Dialog` que o encerra, saiu do formato "
        "que esta guarda lê; a equivalência de M9 precisa ser reavaliada contra o texto "
        "atual"
    )
    trecho = fonte[inicio:fim]
    assert "!root.esdeImportBusy" in trecho, (
        "o Importar da raiz deixou de exigir a bandeira baixada: um segundo clique "
        "passa a ser alcançável, `ocupadoAntes` e `true` deixam de ser a mesma "
        "resposta, e M9 vira buraco de cobertura — a cena é devida"
    )
    assert (
        re.search(
            r"const ocupadoAntes = root\.esdeImportBusy\s*\n"
            r"\s*const geracao = root\.esdeImportGeneration \+ 1\s*\n"
            r"\s*root\.esdeImportGeneration = geracao\s*\n"
            r"\s*root\.esdeImportBusy = true",
            trecho,
        )
        is not None
    ), (
        "o clique do apply deixou de capturar `ocupadoAntes` antes de armar a "
        "bandeira: sem essa ordem a recusa não tem o que devolver, e o argumento de "
        "equivalência deixa de valer"
    )


def test_a_espera_e_observavel_e_a_limpeza_testa_quiescencia() -> None:
    fonte = _harness_source()
    assert "Qt.callLater" not in fonte, (
        "quem revela o foco é o produto (`restoreDialogFocus()`); o teste espera o efeito"
    )
    assert not re.search(r"wait\(\s*(?:[3-9]\d\d|\d{4,})\s*\)", fonte), (
        "o harness usa intervalo fixo grande em vez de condição observável"
    )
    assert "pendingRequests === 0" in fonte, (
        "a limpeza não espera as requisições terminarem: com uma resposta em voo a "
        "cena seguinte nasceria suja por culpa da ordem do teste"
    )
    assert "signature()" in fonte, (
        "o layout é estabilizado por observable, não por intervalo — a causa medida "
        "na 4ª fatia do gate ES-DE"
    )


def test_a_ponte_publica_o_contrato_verdadeiro_e_atrasa_de_verdade() -> None:
    fonte = Path(__file__).read_text(encoding="utf-8")
    assert "handheld_ui_contracts()" in fonte, (
        "sem os contratos reais `requestAction` reprova por contrato ausente e o "
        "teste mede outra coisa"
    )
    assert "/theme/import/esde/inspect" in fonte
    assert "/theme/import/esde/apply" in fonte
    assert "/theme/list" in fonte, (
        "a re-listagem é o único oráculo do terceiro efeito do apply tardio"
    )
    assert "ThreadingHTTPServer" in fonte, (
        "com uma thread só o atraso serializa as requisições e a ordem nunca se "
        "inverte: o teste mediria a ponte"
    )
    atrasos = {str(spec["atraso_ms"]) for spec in ORIGENS.values()}
    assert len(atrasos) >= 2, f"todas as alavancas com o mesmo atraso: {atrasos}"
    fontes = [str(spec["fonte"]) for spec in ORIGENS.values()]
    for origem in fontes:
        for outra in fontes:
            if origem is not outra:
                assert not outra.startswith(origem), (
                    f"a fonte {origem} é prefixo de {outra}: a resposta sairia com o "
                    "atraso da alavanca errada"
                )
    assert _ESCALA == 1.0 and _VIEWPORT == "1280x800", (
        "esta fatia não mede geometria; mudar o viewport pede reacender as cenas"
    )


def test_o_contrato_da_ponte_bate_com_a_leitura_do_produto() -> None:
    """A ponte não pode servir um contrato que o produto não publica.

    `backendAction()` resolve a ação por `uiContracts.byId`, e o catálogo é o que
    `handheld_ui_contracts()` publica em `/status`. Se o id, o método ou o endpoint
    divergir do produto, a jornada exercita a ponte e não o shell.
    """
    catalogo = handheld_ui_contracts()["byId"]
    for action_id, rota in (
        ("theme.import.esde.inspect", "/theme/import/esde/inspect"),
        ("theme.import.esde.apply", "/theme/import/esde/apply"),
    ):
        assert action_id in catalogo, f"o produto não publica {action_id}"
        contrato = catalogo[action_id]
        assert contrato["endpoint"] == rota, (
            f"{action_id} publica {contrato['endpoint']!r} no produto e {rota!r} na ponte"
        )
        assert contrato["method"] == "POST", (
            f"{action_id} é {contrato['method']} no produto; a ponte atende POST"
        )


def test_a_config_publica_cada_alavanca_que_o_harness_le() -> None:
    """Nenhuma alavanca lida no harness pode nascer de um default implícito.

    O harness acessa as origens de duas formas, e as duas são conferidas: por nome
    literal (`harness.cfg.origens.curta.esquemas`) e por variável
    (`harness.cfg.origens[alavanca].fonte`, onde `alavanca` vem das chamadas
    `examinar("lenta", …)`/`origem("curta", …)`). Os dois sentidos importam — uma
    alavanca pedida e não publicada seria respondida com atraso arbitrário pela
    ponte, e uma publicada e nunca pedida é atraso morto.
    """
    fonte = _harness_source()
    nomes = re.findall(r"harness\.cfg\.origens\.([A-Za-z]\w*)", fonte)
    nomes += re.findall(
        r"(?:examinar|origem|verificarCadaEsquemaComoOpcaoSelecionavel"
        r"|verificarCadaNomeTemMarcador)\(\"([a-z-]+)\"",
        fonte,
    )
    lidas = set(nomes)
    assert lidas, "o harness não lê nenhuma alavanca da configuração"
    assert lidas <= set(ORIGENS), (
        f"o harness pede alavancas que a ponte não publica: {sorted(lidas - set(ORIGENS))}"
    )
    assert set(ORIGENS) <= lidas, (
        f"alavancas configuradas e nunca exercitadas: {sorted(set(ORIGENS) - lidas)}"
    )
    #: `_write_config` serializa exatamente estes três campos; o acesso por variável
    #: (`origens[alavanca].X`) não é conferível por nome, então é conferido por campo.
    for campo in ("fonte", "esquemas", "prefixo"):
        assert f"].{campo}" in fonte, (
            f"o harness não lê ['{campo}'] e a ponte o publica: a cena deixaria de "
            "verificar a origem, a contagem ou o marcador que a distingue"
        )
    #: Atraso é mecanismo da PONTE. Lido pela superfície, o teste passaria a prever
    #: quando a resposta chega em vez de esperar pelo estado observável.
    assert "atraso_ms" not in fonte, (
        "o harness conhece o atraso da ponte: a espera deixaria de ser pelo estado"
    )
    for spec in ORIGENS.values():
        assert str(spec["fonte"]) not in fonte, (
            f"a fonte {spec['fonte']!r} está escrita no harness em vez de vir da configuração"
        )


# ---------------------------------------------------------------------------
# O portão: roda a suíte inteira uma vez, com a ponte de atraso real.
# ---------------------------------------------------------------------------


@pytest.mark.visual
def test_a_resposta_tardia_do_importador_esde_nao_reabre_estado() -> None:
    if RUNNER is None:
        pytest.fail(
            "QML-VISUAL-ENVIRONMENT-001: qmltestrunner ausente. A resposta tardia do "
            "importador ES-DE não pode ser verificada sem runtime QML; declarar verde "
            "sem renderizar é o defeito que a RC-01 combate."
        )
    bridge, state = _start_bridge()
    try:
        completed = _run_qmltestrunner(bridge, "jornada")
    finally:
        bridge.shutdown()
        bridge.server_close()
        _gravar_eventos_da_ponte(state, "jornada")

    saida = completed.stdout + completed.stderr
    observadas = _observacoes(saida)

    assert state.unauthorized == 0, (
        f"a ponte devolveu 401 por token {state.unauthorized}x: a jornada não passou "
        "pela rota autenticada de `Main.qml`"
    )
    assert state.status_calls >= 1, "a ponte nunca serviu /status"

    inspects = [evento for evento in state.eventos if evento[1].endswith("/inspect")]
    applies = [evento for evento in state.eventos if evento[1].endswith("/apply")]
    assert len(inspects) == ESPERADO_INSPECT, (
        f"a rota de examine foi exercitada {len(inspects)}x, esperado "
        f"{ESPERADO_INSPECT} (as recusas NÃO contam — `requestAction` devolve antes "
        f"do XHR): {inspects}"
    )
    assert len(applies) == ESPERADO_APPLY, (
        f"a rota de apply foi exercitada {len(applies)}x, esperado {ESPERADO_APPLY} "
        f"(jornada e cena tardia): {applies}"
    )
    for testemunho in TESTEMUNHOS:
        assert testemunho in observadas, (
            f"a cena nunca publicou o testemunho {testemunho!r}; sem ele a asserção "
            f"correspondente não foi medida. Lidos: {sorted(observadas)}"
        )

    #: As duas recusas, lidas no log em vez de narração: cada cena registra o estado
    #: da bandeira no instante imediatamente depois do clique recusado. É aqui que o
    #: rollback errado fica visível para quem audita o artefato, sem depender de
    #: contar falhas do `qmltestrunner`.
    for testemunho, esperado in TOAST.items():
        assert observadas[testemunho]["toast"] == esperado, (
            f"{testemunho}: o aviso de sucesso do apply raiz vale "
            f"{observadas[testemunho]['toast']!r}, esperado {esperado!r} — na cena 07 o "
            "apply aterrassa com a superfície ABERTA e o `notify` é o desfecho correto; "
            "na 09 a superfície fechou antes da resposta e o mesmo texto seria o defeito"
        )

    for testemunho, esperado in RECUSAS.items():
        lido = observadas[testemunho]
        assert lido["pendentes"] != "0", (
            f"{testemunho}: não havia nenhum pedido em voo no momento da recusa "
            f"(pendentes={lido['pendentes']}); sem voo não houve deduplicação, e a "
            "cena exerceitou outra coisa"
        )
        campo, valor = next(iter(esperado.items()))
        assert lido[campo] == valor, (
            f"{testemunho}: a bandeira no instante da recusa vale {lido[campo]!r}, "
            f"esperado {valor!r} — {RECUSAS_DOC[testemunho]}"
        )

    #: Não-vacuidade por origem: a segunda tentativa de cada cena de recusa foi
    #: absorvida no cliente, então cada uma dessas origens chega UMA vez à ponte. Sem
    #: esta leitura, "a recusa não travou nada" seria satisfeito por uma ponte que
    #: respondeu duas vezes e por um `Main.qml` que simplesmente não deduplica.
    contadas = [origem for _metodo, rota, origem in state.eventos if rota.endswith("/inspect")]
    for alavanca, sufixo in RECUSAS_DE_PONTE:
        origem = f"{ORIGENS[alavanca]['fonte']}-{sufixo}"
        vezes = contadas.count(origem)
        assert vezes == 1, (
            f"a origem {origem!r} da cena de recusa apareceu {vezes}x em /inspect, "
            "esperado 1: ou a repetição nunca foi clicada, ou ela chegou à ponte — e "
            "nesse caso não houve recusa local nenhuma"
        )
    assert contadas.count(JORNADA_INSPECT) == 1, (
        f"a origem {JORNADA_INSPECT!r} da jornada apareceu "
        f"{contadas.count(JORNADA_INSPECT)}x em /inspect, esperado 1 — sem a jornada "
        "unica e real, as contagens da suíte não têm chão"
    )

    #: Contrafactual da re-listagem: num apply cuja resposta chegou com a superfície
    #: ABERTA (a jornada do `test_01`), o `GET /theme/list` TEM de aparecer depois do
    #: `POST`. Sem esta leitura, "nenhum re-lista depois do apply tardio" poderia ser
    #: satisfeito por uma ponte que nunca listou nada.
    posicoes_list = [
        indexo for indexo, evento in enumerate(state.eventos) if evento[1] == "/theme/list"
    ]
    posicoes_apply = [
        indexo for indexo, evento in enumerate(state.eventos) if evento[1].endswith("/apply")
    ]
    assert posicoes_list, (
        "nenhum GET /theme/list na ponte: o painel nem lista temas ao abrir "
        "(`Component.onCompleted: refreshThemeList()`), então o produto não foi "
        "exercitado"
    )
    assert any(lista > aplica for aplica in posicoes_apply for lista in posicoes_list), (
        "nenhum GET /theme/list DEPOIS de nenhum POST de apply: o mecanismo de "
        f"re-listagem não disparou em cena alguma (eventos={state.eventos}) — a "
        "asserção seguinte seria uma alegação sobre ausência de medição"
    )

    #: O contrato: depois do apply TARDIO do painel (cena `test_04`), nenhum re-lista.
    #: Pinado pela ORIGEM, não por "o último apply do log": as cenas da rota raiz
    #: acrescentam applies depois dele, e o diálogo raiz nunca lista temas — se a
    #: asserção continuasse lida sobre "o último", ela passaria a medir uma superfície
    #: que não tem o mecanismo, e o vermelho de `test_04` viraria verde de ausência.
    tardio = f"{ORIGENS['lenta']['fonte']}-aplicar-tardio"
    posicoes_tardio = [
        i for i, e in enumerate(state.eventos) if e[1].endswith("/apply") and e[2] == tardio
    ]
    assert len(posicoes_tardio) == 1, (
        f"o apply tardio do painel ({tardio!r}) aparece {len(posicoes_tardio)}x no log, "
        "esperado 1: sem ele localizado a asserção seguinte não teria âncora"
    )
    ultimo = posicoes_tardio[0]
    tardios = [evento for evento in state.eventos[ultimo + 1 :] if evento[1] == "/theme/list"]
    assert not tardios, (
        f"a resposta tardia do apply re-listou temas depois de a superfície fechar "
        f"({len(tardios)} GET /theme/list após o último POST, "
        f"posição {ultimo} de {len(state.eventos)}): {state.eventos[ultimo:]}"
    )

    assert completed.returncode == 0, (
        f"a suíte reprovou (inspect={len(inspects)}, apply={len(applies)}, "
        f"status={state.status_calls}):\n{completed.stdout}\n{completed.stderr}"
    )
    _assert_denominador(completed.stdout, "jornada ES-DE tardia")
    _assert_qml_clean(completed, "jornada ES-DE tardia")


@pytest.mark.visual
def test_a_ordem_de_resposta_inverte() -> None:
    """A ponte serviu o lento DEPOIS do rápido, embora o lento tenha chegado antes.

    Sem esta leitura, o `test_03` poderia passar porque a ordem nunca se inverteu —
    a cena exercitaria atraso nenhum. É a testemunha de não-vacuidade do atraso,
    medida fora do QML.
    """
    if RUNNER is None:
        pytest.fail("QML-VISUAL-ENVIRONMENT-001: qmltestrunner ausente")
    bridge, state = _start_bridge()
    try:
        completed = _run_qmltestrunner(bridge, "ordem")
    finally:
        bridge.shutdown()
        bridge.server_close()
        _gravar_eventos_da_ponte(state, "ordem")

    lenta = CORRIDA["lenta"]
    rapida = CORRIDA["rapida"]
    chegadas = [origem for origem in state.recebidas if origem in (lenta, rapida)]
    saidas = [origem for origem in state.respondidas if origem in (lenta, rapida)]
    assert sorted(chegadas) == sorted([lenta, rapida]), (
        f"a corrida da ponte viu {chegadas!r}, esperado exatamente {lenta!r} e "
        f"{rapida!r} — ou o test_03 mudou de origem, ou a filtragem está medindo "
        "outra cena"
    )
    assert sorted(saidas) == sorted([lenta, rapida]), (
        f"a corrida respondeu {saidas!r}, esperado exatamente uma resposta de cada "
        f"origem ({lenta!r}, {rapida!r})"
    )
    # A testemunha de que o filtro exato está trabalhando: os examines de `test_02`
    # e `test_04` usam a MESMA alavanca lenta e passaram pela ponte, mas não
    # pertencem à corrida. Sem esta linha, um regresso ao `startswith` reescreveria
    # a história com a resposta de outra cena e continuaria "verde".
    intrusa = f"{ORIGENS['lenta']['fonte']}-tardia"
    assert intrusa in state.recebidas, (
        f"{intrusa!r} nunca chegou à ponte: o test_02 saiu do ar, então a corrida "
        "deixou de ter vizinha para excluir"
    )
    assert intrusa not in chegadas, (
        f"a corrida absorveu {intrusa!r}: a filtragem voltou a ser por prefixo"
    )
    assert chegadas[0] == lenta, (
        f"a primeira requisição da corrida foi {chegadas[0]!r}, esperado a lenta "
        f"({lenta!r}): o test_03 mudou de ordem e a cena não exercita mais a corrida"
    )
    assert saidas[0] == rapida, (
        f"ordem de resposta foi {saidas}: a rápida nunca respondeu antes da lenta, "
        "então nada aqui mediu resposta fora de ordem"
    )
    _assert_suite_concluida(completed.returncode, completed.stdout, "ordem de resposta invertida")
    _assert_qml_clean(completed, "ordem de resposta invertida")
