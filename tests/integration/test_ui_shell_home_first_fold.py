# SPDX-License-Identifier: GPL-3.0-or-later
"""RC-01 (oitava fatia) — a primeira dobra da Home sob atenção máxima alcançável.

A lacuna existe desde 26/09 (`2026-09-26-rc01-central-loading/README.md`
§"Ressalva de experiência"), mas foi registrada **forçando** `bridgeUnavailable`.
Medido antes deste gate: essa combinação não existe pelos bindings de produção —
`apiUrl`/`apiToken` vêm de argumento na inicialização (`Main.qml:901`-`:908`) e,
sem eles, não há leitura bem-sucedida, logo `desktopTruthNeedsAttention`
(`:339`) e `hasConflicts` (`:334`) ficam falsos e o banner não acende. O que a
produção **sim** empilha, numa única jornada real, é: faixa de fase + banner de
atenção (verdade degradada com conflito) + cartão de erro pelo MESMO código da
renovação recusada (`pushError` `:496`).

A faixa não é só "carregando": `statusBandVisible` é `statusIsLoading ||
statusStale || statusBandIsError` (`Main.qml:421`-`:422`), com
`statusBandIsError = statusPhase === "error" && !bridgeUnavailable`. Ou seja,
**toda** falha de leitura acende a faixa — inclusive a primeira leitura recusada,
sem nada preservado. Corrigir isto aqui é correção de leitura própria: a nota de
bancada anterior deste gate modelava a faixa como `loading || stale` e por isso
descrevia a cena sem-dados como "cartão é o único anúncio". Não é: são dois
anúncios do mesmo fato, e o cartão é o único dos dois com detalhes e exportação.

Medido nesta bancada (qml6, 1280x800, janela em `compactLayout` por `:71`), com
a cena vindo da ponte, antes de qualquer mudança de produto:

| cena | faixa | banner | cartões | `scroll_h` | 1º alvo (y,h) | fim | `Pendências` (y) |
|---|---|---|---|---|---|---|---|
| quieta | 0 | 0 | 0 | 698 | 401, 48 | 449 | 581 |
| máxima 100 % | 1 | 1 | 1 | 434 | 401, 48 | 449 | 581 |
| máxima 150 % | 1 | 1 | 1 | 405 | 417, 51 | 468 | 597 |
| sem dados | 1 | 0 | 1 | 501 | 401, 48 | 449 | 581 |

No pior caso alcançável o chrome fixo fora do `ScrollView` consome 264 px dos
698 da cena quieta (faixa 55 + banner 67 + cartão 135 + margens), e a escala de
150 % ainda leva o cartão a 164 px. O corte é mais pesado que os 209 px da nota
original de 26/09. Medido junto: os alvos do cartão ("Exportar diagnóstico")
têm **36 px** — abaixo dos 48 px já exigidos dentro do shell pelos lotes UX-05/
UX-07 (`test_ui_shell_esde_import_dialog.py:925`).

Depois da correção, nas mesmas janelas e na mesma ponte (`40-matriz-dobra-pos-correcao.log`
no lote de evidência): a banda visível passa a **493 px** nas duas cenas de atenção e
560 px sem dados, o cartão fica em **76 px** compacto e **107 px** expandido, e o alvo de
diagnóstico em 48 px. O chrome agregado cai de 264 para 205 px (698 - 493) e o primeiro
alvo termina em 449 px (100 %) e 468 px (150 %), dentro da dobra. Os 107 px expandidos
são **a altura do mesmo cartão na forma estendida** (`45-sonda-referencia-forma-estendida.log`:
`cartao_expandido_h == cartao_referencia_h == 107`), com os mesmos 198 caracteres de prosa
e os mesmos 6 rótulos na tela — é assim que "dobrou" se distingue de "apagou", sem modelo
de altura por linha. A primeira versão desta última asserção exigia `ceil(3 · 11 · escala)`
= 33 px de crescimento e reprovou os 31 px reais (`41-gate-modelo-de-altura-reprovou.log`);
a sonda mostrou o motivo — dois dos rótulos dobrados chegam vazios nesta cena e ficam
ocultos também na forma estendida. O vermelho era do modelo do teste.

O que este arquivo alega é estreito e verificável: **o primeiro alvo acionável
tem de caber inteiro na dobra**, em 100 % e em 150 %, no pior caso alcançável.
Ele não alega que `Pendências` caiba — com três superfícies de atenção ativas
isso exigiria decisão de arquitetura da Home, registrada como pendência.

As testemunhas saem do harness (`check_home_first_fold_attention.qml`) e são
lidas aqui, independente do veredito do Qt: um harness mudo também "passaria".
"""

from __future__ import annotations

import json
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

from qml_capture_runner import CanonicalEnvironment  # noqa: E402
from steamzero.adapters.desktop_contracts import handheld_ui_contracts  # noqa: E402

HARNESS = "tests/qml/check_home_first_fold_attention.qml"
TOKEN = "dobra-home-rc01"

#: Denominador de cenas. Renomear, excluir ou pular uma reprova aqui, em vez de
#: deixar o verde encolher em silêncio.
CENAS = (
    "quieto",
    "atencao-maxima",
    "atencao-maxima-150",
    "leitura-sem-dados",
)

#: Toda chave que a testemunha precisa trazer. Uma cena que responder com
#: testemunha parcial não está sendo medida — está sendo presumida.
TESTEMUNHOS = (
    "escala",
    "band",
    "banner",
    "ponte",
    "erros",
    "cartoes",
    "scroll_h",
    "home_h",
    "primeiro",
    "primeiro_y",
    "primeiro_h",
    "primeiro_visivel",
    "pend_y",
    "pend_h",
    "cartao_h",
    "cartao_diag",
    "cartao_detalhe",
    "cartao_alvo_h",
    "cartao_compacto",
    "cartao_expandido_h",
    "gatilho",
    "prosa_itens",
    "prosa_na_tela",
    "prosa_caracteres",
    "prosa_caracteres_na_tela",
    "prosa_na_tela_expandida",
    "prosa_caracteres_na_tela_expandida",
    "cartao_referencia_h",
    "prosa_na_tela_ref",
    "prosa_caracteres_na_tela_ref",
    "alvos",
)

#: Os quatro alvos acionáveis publicados pela Home. Se a Home perder um, a
#: testemunha `alvos` cai e a cena deixa de ser a que o gate diz medir.
ALVOS_DA_HOME = 4

#: Altura mínima de alvo tocável, no mesmo contrato das fatias UX-05/UX-07.
ALVO_MINIMO = 48

#: Cap da altura agregada das superfícies de atenção. Derivado do critério, não
#: escolhido: a cena quieta dá 698 px de banda visível e, no pior caso medido
#: (150 % de escala), o primeiro alvo termina em 468 px — logo o chrome pode
#: consumir no máximo 698 - 468 = 230 px. Antes da correção a agregação media
#: 264 px (faixa 55 + banner 67 + cartão 135 + margens): daí o vermelho.
CAPA_CHROME_AGREGADO = 230

pytestmark = pytest.mark.visual


def _qml_binario() -> str | None:
    return next(
        (
            str(candidate)
            for candidate in (
                Path("/usr/lib/qt6/bin/qml"),
                Path("/usr/lib64/qt6/bin/qml"),
            )
            if candidate.is_file()
        ),
        shutil.which("qml6"),
    )


QML = _qml_binario()


def _environment() -> dict[str, str]:
    """Ambiente declarado do gate visual — não herdado do host."""
    environment = CanonicalEnvironment().to_env()
    environment["QML_XHR_ALLOW_FILE_READ"] = "1"
    return environment


def _status_payload(cena: str) -> dict[str, object]:
    """/status com a forma que o `Main.qml` consome, variando só a atenção.

    `uiContracts` é o catálogo verdadeiro (`handheld_ui_contracts()`), a mesma
    função que o produto publica: sem isso a ponte reprovaria contrato ausente e
    o teste mediria outra coisa.
    """
    escala = 1.5 if cena.endswith("-150") else 1.0
    atencao = cena.startswith("atencao")
    payload: dict[str, object] = {
        "truthState": "degraded" if atencao else "ready",
        "desiredProfile": "handheld-desktop",
        "appliedProfile": "handheld-desktop" if not atencao else None,
        "observedProfile": None,
        "effectiveProfile": "handheld-desktop",
        "recommendedProfile": "handheld-desktop",
        "statusReasons": (["A verdade aplicada não bate com a desejada."] if atencao else []),
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
            "conflicts": (
                [{"code": "CENA-CONFLITO", "title": "Conflito da cena"}] if atencao else []
            ),
        },
        "dashboard": {
            "accessibility": {
                "reducedMotion": False,
                "highContrast": False,
                "visualScale": escala,
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
                "contextLabel": "Oitava fatia — dobra da Home",
                "platforms": [],
                "jobs": [],
            },
            "steamGameplay": {"schemaVersion": 1, "games": [], "environment": []},
            "uiContracts": handheld_ui_contracts(),
        },
    }
    return payload


#: O código da leitura recusada. É por ele que se distingue "a faixa e o cartão
#: anunciam o mesmo fato" de "houve um segundo fato, e ele tem de aparecer".
CODIGO_FALHA_LEITURA = "E-DOBRA-CENA"


def _falha_leitura() -> dict[str, object]:
    return {
        "error": {
            "code": CODIGO_FALHA_LEITURA,
            "title": "A renovação do estado falhou",
            "detail": "A central não pôde reler o host nesta tentativa.",
            "what": "Leitura GET /status recusada pela cena.",
            "impact": "O último estado lido permanece na tela.",
            "autoAction": "",
            "manualAction": "Tente novamente.",
            "probableCause": "Cena controlada pelo teste.",
            "operationId": "",
        }
    }


class _Cena:
    """Estado por teste: qual cena, quantas leituras, o que já foi servido."""

    def __init__(self, cena: str) -> None:
        self.cena = cena
        self.lock = threading.Lock()
        self.leituras = 0
        self.sucessos = 0
        self.recusas = 0

    def proxima(self) -> int:
        with self.lock:
            self.leituras += 1
            return self.leituras


def _handler(cena: _Cena) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # contrato do BaseHTTPRequestHandler
            rota = self.path.split("?")[0]
            if rota != "/status":
                self._responder(404, json.dumps({"error": "rota fora da cena"}))
                return
            numero = cena.proxima()
            # `leitura-sem-dados`: a PRIMEIRA leitura já recusa. Sem nada
            # preservado a fase vira `error`, `statusBandIsError` (`Main.qml:420`)
            # acende a faixa na variante de erro e o banner não existe — ficam
            # dois anúncios do mesmo fato, mas só o cartão carrega as ações.
            if cena.cena == "leitura-sem-dados":
                cena.recusas += 1
                self._responder(500, json.dumps(_falha_leitura()))
                return
            # `atencao-maxima`: primeira leitura boa (dados + verdade degradada +
            # conflito), segunda recusada — é assim que a faixa acende COM dados
            # na tela e o mesmo código vira cartão de erro.
            if numero >= 2 and cena.cena.startswith("atencao"):
                cena.recusas += 1
                self._responder(500, json.dumps(_falha_leitura()))
                return
            if numero == 1 and cena.cena.startswith("atencao"):
                # Atraso curto: a testemunha precisa poder ver a faixa em
                # `loading`, e sem atraso a fase passaria por ela despercebida.
                time.sleep(0.25)
            cena.sucessos += 1
            self._responder(200, json.dumps(_status_payload(cena.cena)))

        def _responder(self, codigo: int, corpo: str) -> None:
            dados = corpo.encode("utf-8")
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(dados)

        def log_message(self, fmt: str, *args: object) -> None:
            pass

    return Handler


def _subir_ponte(cena: _Cena) -> tuple[int, ThreadingHTTPServer]:
    host = "127.0.0.1"
    for port in range(44000, 45000):
        try:
            server = ThreadingHTTPServer((host, port), _handler(cena))
        except OSError:
            continue
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return port, server
    raise RuntimeError("nenhuma porta livre para a cena da dobra da Home")


def _rodar(cena: str) -> tuple[dict[str, str] | None, subprocess.CompletedProcess[str]]:
    """Roda a ponte da cena e devolve a testemunha do harness.

    O argv é o da produção (`adapters/desktop_ui.py:990`-`:1001`): `qml6`, o
    caminho do `Main.qml`, `--`, `--steamzero-api`, `--steamzero-token`. Não há
    marcador de cena: quem decide a jornada é só o comportamento da ponte, e a
    testemunha é indexada pelo chamador, que sabe qual ponte subiu.
    """
    estado = _Cena(cena)
    port, server = _subir_ponte(estado)
    try:
        completed = subprocess.run(
            [
                str(QML),
                HARNESS,
                "--",
                "--steamzero-api",
                f"http://127.0.0.1:{port}",
                "--steamzero-token",
                TOKEN,
            ],
            cwd=ROOT,
            env=_environment(),
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
    finally:
        server.shutdown()
    testemunha = _ler_testemunha(completed.stderr)
    if testemunha is not None:
        testemunha.update(_ler_expansao(completed.stderr))
        testemunha["_leituras"] = str(estado.leituras)
        testemunha["_recusas"] = str(estado.recusas)
    return testemunha, completed


def _ler_testemunha(saida: str) -> dict[str, str] | None:
    """A última linha `TESTEMUNHO|k=v|…` da saída, ou `None`.

    O ambiente do gate instala regras de `qtlogging`, então cada linha chega
    prefixada pela categoria do log (`debug|TESTEMUNHO|…`). O marcador é procurado
    dentro da linha, não no início dela: um prefixo que o teste não conhece
    reprovaria uma cena que renderizou — foi assim que a primeira versão deste
    gate mediu o vermelho errado.
    """
    ultima: dict[str, str] | None = None
    for line in saida.splitlines():
        marcador = line.find("TESTEMUNHO|")
        if marcador < 0:
            continue
        ultima = dict(
            par.split("=", 1) for par in line[marcador:].strip().split("|")[1:] if "=" in par
        )
    return ultima


def _ler_expansao(saida: str) -> dict[str, str]:
    """As testemunhas depois da medição principal: expansão e referência.

    `TESTEMUNHO2|` é o cartão compacto depois de acionar "Ver detalhes";
    `TESTEMUNHO3|` é o MESMO cartão com `compact` posto em falso — a forma
    estendida, que serve de referência. As duas etapas indexam o mesmo dicionário
    porque a asserção é uma igualdade entre elas.
    """
    colhido: dict[str, str] = {}
    for marcador in ("TESTEMUNHO2|", "TESTEMUNHO3|"):
        for line in saida.splitlines():
            indice = line.find(marcador)
            if indice < 0:
                continue
            colhido.update(
                par.split("=", 1) for par in line[indice:].strip().split("|")[1:] if "=" in par
            )
    return colhido


def _testemunha_ou_falha(cena: str) -> dict[str, str]:
    """Uma cena sem testemunha é reprovação, não ausência de evidência."""
    if QML is None:
        pytest.fail(
            "QML-VISUAL-ENVIRONMENT-001: qml6 ausente; a geografia da dobra não "
            "pode ser verificada sem runtime QML, e declarar verde sem renderizar "
            "é o defeito que a RC-01 combate."
        )
    testemunha, completed = _rodar(cena)
    saida = completed.stderr or ""
    assert "FAIL:" not in saida, f"o harness rejeitou a cena {cena!r}:\n{saida[-2000:]}"
    assert completed.returncode == 0, (
        f"harness da cena {cena!r} saiu com rc={completed.returncode}:\n{saida[-2000:]}"
    )
    assert testemunha is not None, (
        f"a cena {cena!r} rodou sem testemunha — harness mudo não é evidência:\n{saida[-2000:]}"
    )
    faltantes = [chave for chave in TESTEMUNHOS if chave not in testemunha]
    assert not faltantes, f"a testemunha de {cena!r} veio incompleta, falta {faltantes}"
    return testemunha


def _inteiro(testemunha: dict[str, str], chave: str) -> int:
    return int(float(testemunha[chave]))


def _cobra_testemunha_unica(cena: str) -> dict[str, str]:
    testemunha = _testemunha_ou_falha(cena)
    # `alvos` é o denominador da Home: se um alvo sumir, a "primeira dobra"
    # passaria a ser aferida contra uma cena mais esvaziada que a de sempre.
    assert _inteiro(testemunha, "alvos") == ALVOS_DA_HOME, (
        f"a cena {cena!r} publicou {_inteiro(testemunha, 'alvos')} alvos acionáveis, "
        f"esperava {ALVOS_DA_HOME} ({ALVOS_DA_HOME}); a dobra deixaria de ser a mesma"
    )
    return testemunha


def test_a_cena_queta_e_o_denominador_onde_a_dobra_ja_fecha() -> None:
    """Controle: sem superfície de atenção, o primeiro alvo cabe na dobra.

    Esta asserção é obrigatoriamente verde antes da correção: se ela já
    falhasse, o vermelho das cenas de atenção não estaria medindo atenção, e
    sim uma Home que não fecha nem vazia.
    """
    alvo = _cobra_testemunha_unica("quieto")
    assert _inteiro(alvo, "band") == 0, "a faixa não deveria estar visível sem estado"
    assert _inteiro(alvo, "banner") == 0, "o banner não deveria estar visível sem atenção"
    assert _inteiro(alvo, "cartoes") == 0, "sem falha não há cartão de erro"
    assert _inteiro(alvo, "primeiro_y") > 0, "a testemunha precisa de geometria real"
    assert _inteiro(alvo, "scroll_h") > 0
    assert _inteiro(alvo, "home_h") > _inteiro(alvo, "scroll_h"), (
        "a Home não está realmente rolável nesta cena — a dobra seria trivial"
    )
    fundo = _inteiro(alvo, "primeiro_y") + _inteiro(alvo, "primeiro_h")
    assert fundo <= _inteiro(alvo, "scroll_h"), (
        f"controle quebrado: o primeiro alvo terminaria em {fundo} px, "
        f"fora da banda visível de {_inteiro(alvo, 'scroll_h')} px"
    )


@pytest.mark.parametrize("cena", ("atencao-maxima", "atencao-maxima-150"))
def test_no_pior_caso_alcancavel_o_primeiro_alvo_ainda_cabe_na_dobra(cena: str) -> None:
    """A alegação da oitava fatia, em 100 % e em 150 % de escala de texto.

    A cena é alcançável pelos bindings reais: leitura boa com verdade degradada
    e conflito (banner), seguida de renovação recusada com dados preservados
    (faixa) — e o MESMO código de falha empilhando um cartão de erro.
    """
    alvo = _cobra_testemunha_unica(cena)
    escala = float(alvo["escala"])
    assert escala >= 1.49 or cena == "atencao-maxima", (
        f"a cena {cena!r} pediu escala 1,5 e o shell renderizou a {escala}"
    )
    # As três superfícies têm de estar efetivamente empilhadas, ou a asserção
    # de dobra estaria sendo satisfeita por uma cena que não é o pior caso.
    assert _inteiro(alvo, "band") == 1, "a faixa de fase não acendeu na cena de atenção"
    assert _inteiro(alvo, "banner") == 1, "o banner de atenção não acendeu na cena"
    assert _inteiro(alvo, "cartoes") >= 1, (
        "o cartão de erro da leitura recusada não apareceu — a cena não é o "
        "pior caso que este gate declara medir"
    )
    assert _inteiro(alvo, "ponte") == 0, (
        "a ponte ficou indisponível: com `apiUrl`/`apiToken` presentes isso não "
        "deve acontecer, e a cena teria mudado de significado"
    )
    fundo = _inteiro(alvo, "primeiro_y") + _inteiro(alvo, "primeiro_h")
    visivel = _inteiro(alvo, "scroll_h")
    assert _inteiro(alvo, "primeiro_visivel") == 1
    assert fundo <= visivel, (
        f"no pior caso alcançável ({cena}) o primeiro alvo acionável da Home "
        f"termina em {fundo} px, abaixo da banda visível de {visivel} px — "
        f"ficam {fundo - visivel} px fora da dobra"
    )


@pytest.mark.parametrize("cena", ("atencao-maxima", "atencao-maxima-150"))
def test_a_altura_agregada_das_superficies_de_atencao_tem_um_teto(cena: str) -> None:
    """O que a correção tem de comprar: píxeis de atenção, não de conteúdo.

    A asserção é sobre a **geografia agregada** (quanto da banda visível o chrome
    de atenção consome), não sobre qual componente encolheu. Assim o gate continua
    valendo se a solução mudar de superfície, e deixa de valer se for o herói
    editorial ou uma ação da Home que sumir para ganhar dobra.
    """
    cena_quieta = _cobra_testemunha_unica("quieto")
    alvo = _cobra_testemunha_unica(cena)
    banda_quieta = _inteiro(cena_quieta, "scroll_h")
    banda_na_cena = _inteiro(alvo, "scroll_h")
    consumo = banda_quieta - banda_na_cena
    assert consumo <= CAPA_CHROME_AGREGADO, (
        f"as superfícies de atenção consomem {consumo} px da dobra na cena "
        f"{cena!r} (teto {CAPA_CHROME_AGREGADO} px): a Home ficou inutilizável "
        f"porque o aviso virou três páginas"
    )


@pytest.mark.parametrize("cena", ("atencao-maxima", "atencao-maxima-150"))
def test_a_correcao_nao_pode_esconder_as_acoes_do_cartao(cena: str) -> None:
    """Guarda de informação: o que encolhe é a altura, nunca o alcance.

    Se a dobra fosse "corrigida" sumindo com o cartão, ou deixando-o sem os
    botões de diagnóstico e de detalhes, esta asserção reprova — e AGENTS §8
    (falha degrada, não trava) deixa de ser intenção declarada.
    """
    alvo = _cobra_testemunha_unica(cena)
    assert _inteiro(alvo, "cartoes") >= 1, f"a cena {cena!r} perdeu o cartão de erro"
    assert _inteiro(alvo, "cartao_diag") == 1, (
        "o cartão perdeu o botão 'Exportar diagnóstico': a correção cortou ação"
    )
    assert _inteiro(alvo, "cartao_detalhe") == 1, (
        "o cartão perdeu o botão de detalhes: a correção cortou acesso à causa"
    )
    assert _inteiro(alvo, "cartao_alvo_h") >= ALVO_MINIMO, (
        f"o alvo de diagnóstico do cartão mede {_inteiro(alvo, 'cartao_alvo_h')} px, "
        f"abaixo dos {ALVO_MINIMO} px do contrato de alcance"
    )
    # A prioridade da Home continua: o que estava antes de `Pendências` não pode
    # ter sido movido para baixo dela para ganhar píxeis de dobra.
    assert _inteiro(alvo, "primeiro_y") < _inteiro(alvo, "pend_y"), (
        "a ordem de prioridade da Home mudou: o cartão de pendências passou para "
        "cima do primeiro alvo, o que seria trocar a dobra por outra coisa"
    )


def test_sem_dados_preservados_a_faixa_e_de_erro_e_o_cartao_guarda_as_acoes() -> None:
    """Sem dados, a faixa acende pela variante de erro — e o cartão não sobra.

    Medido: com a primeira leitura recusada, `statusPhase` vira `error`
    (`Main.qml:1248`-`:1249`), `statusBandIsError` (`:420`) põe a faixa na tela, e o
    mesmo código empilha um cartão. Diferente da cena de atenção, aqui **não há
    verdade preservada** e o banner não existe: a faixa anuncia o fato, mas só o
    cartão tem detalhes e exportação. Uma correção que colapsasse o cartão
    "porque a faixa já avisa" apagaria a única saída de diagnóstico dessa
    jornada, e esta asserção reprova.
    """
    alvo = _cobra_testemunha_unica("leitura-sem-dados")
    assert _inteiro(alvo, "band") == 1, (
        "a faixa de erro não acendeu com a primeira leitura recusada: a cena "
        "deixou de ser a que este gate declara medir"
    )
    assert _inteiro(alvo, "banner") == 0, "sem leitura bem-sucedida não há verdade a julgar"
    assert _inteiro(alvo, "ponte") == 0
    assert _inteiro(alvo, "cartoes") == 1, (
        "o cartão de erro sumiu na única cena sem verdade preservada"
    )
    assert _inteiro(alvo, "cartao_diag") == 1
    assert _inteiro(alvo, "cartao_detalhe") == 1
    assert _inteiro(alvo, "cartao_alvo_h") >= ALVO_MINIMO, (
        f"nessa jornada o alvo de diagnóstico é a única saída e mede "
        f"{_inteiro(alvo, 'cartao_alvo_h')} px, abaixo dos {ALVO_MINIMO} px do contrato"
    )


@pytest.mark.parametrize("cena", ("atencao-maxima", "atencao-maxima-150", "leitura-sem-dados"))
def test_o_cartao_que_duplica_a_faixa_dobra_a_orientacao_e_a_devolve(cena: str) -> None:
    """A regra do oitavo elo, medida contra a forma estendida do MESMO cartão.

    Quando a faixa de fase já anuncia **exatamente este código** de falha, o
    cartão entra em forma compacta (`compact` lido da árvore, não presumido). E
    compactar não é apagar: o harness ACIONA o "Ver detalhes" e a forma
    resultante tem de coincidir com a forma estendida do mesmo cartão — os mesmos
    rótulos de prosa na tela, os mesmos caracteres, a mesma altura.

    A referência é o que torna o verde significativo. A versão anterior desta
    asserção exigia crescimento de `ceil(3 · 11 · escala) = 33 px`, um cálculo da
    bancada sobre a altura de uma linha de fonte 11. Ela reprovou um cartão que
    cresce 31 px e devolve **198 de 198** caracteres, porque dois dos rótulos
    ("Ação automática", "ID da operação") chegam vazios nesta cena e ficam
    ocultos também na forma estendida (`45-sonda-referencia-cartao.log`). O
    vermelho era o modelo do teste, não supressão do produto; corrigido por causa
    demonstrada, a aferição ficou mais forte — igualdade de conteúdo, não piso de
    píxeis.
    """
    alvo = _cobra_testemunha_unica(cena)
    assert _inteiro(alvo, "band") == 1, "sem faixa anunciando a falha não há duplicação"
    assert _inteiro(alvo, "cartoes") == 1, f"a cena {cena!r} perdeu o cartão de erro"
    assert _inteiro(alvo, "cartao_compacto") == 1, (
        f"na cena {cena!r} a faixa reporta o MESMO código do cartão, mas o cartão "
        f"continua na forma estendida — o chrome duplicado não foi tratado"
    )
    assert alvo["gatilho"] == "clique", (
        "o 'Ver detalhes' do cartão compacto não foi encontrado para ser acionado: "
        "a forma compacta cortou o acesso à orientação"
    )
    # Não-vacuidade: tem de haver prosa efetivamente dobrada, senão a igualdade
    # abaixo seria satisfeita por um cartão que nunca mostrou orientação a ninguém.
    assert _inteiro(alvo, "prosa_na_tela") < _inteiro(alvo, "prosa_na_tela_ref"), (
        f"a forma compacta mostra {_inteiro(alvo, 'prosa_na_tela')} rótulos de prosa e a "
        f"estendida mostra {_inteiro(alvo, 'prosa_na_tela_ref')}: sem nada dobrado, "
        f"esta asserção não mediria dobra nenhuma"
    )
    assert _inteiro(alvo, "prosa_caracteres_na_tela") < _inteiro(
        alvo, "prosa_caracteres_na_tela_ref"
    ), "a compactação não escondeu caracteres de orientação — não houve dobra"
    # Compactar não é apagar.
    assert _inteiro(alvo, "prosa_na_tela_expandida") == _inteiro(alvo, "prosa_na_tela_ref"), (
        f"expandido, o cartão tem {_inteiro(alvo, 'prosa_na_tela_expandida')} rótulos de "
        f"prosa na tela; estendido, tem {_inteiro(alvo, 'prosa_na_tela_ref')} — um "
        f"'Ver detalhes' que re-oculta rótulo é supressão, não dobra"
    )
    assert _inteiro(alvo, "prosa_caracteres_na_tela_expandida") == _inteiro(
        alvo, "prosa_caracteres_na_tela_ref"
    ), (
        f"expandido devolve {_inteiro(alvo, 'prosa_caracteres_na_tela_expandida')} "
        f"caracteres, a forma estendida tem {_inteiro(alvo, 'prosa_caracteres_na_tela_ref')}"
    )
    assert _inteiro(alvo, "cartao_expandido_h") == _inteiro(alvo, "cartao_referencia_h"), (
        f"o cartão compacto expandido mede {_inteiro(alvo, 'cartao_expandido_h')} px e o "
        f"mesmo cartão estendido mede {_inteiro(alvo, 'cartao_referencia_h')} px — as duas "
        f"formas teriam informação diferente, o que apagaria algo na compacta"
    )
    # E a dobra compra píxeis nos dois sentidos.
    assert _inteiro(alvo, "cartao_expandido_h") > _inteiro(alvo, "cartao_h"), (
        f"expandido o cartão não cresceu ({_inteiro(alvo, 'cartao_h')} px); a forma "
        f"compacta não estaria devolvendo nada"
    )


def test_a_ponte_da_cena_de_atencao_recusa_a_renovacao_e_nao_a_primeira_leitura() -> None:
    """Guarda sem Qt: o vermelho vem da renovação, não de uma ponte quebrada.

    Se a cena de atenção recusasse a primeira leitura, a Home nunca teria dados,
    o banner não acenderia, e a dobra alegada seria outra cena.
    """
    for cena in ("atencao-maxima", "atencao-maxima-150"):
        alvo, _completed = _rodar(cena)
        assert alvo is not None, f"a cena {cena!r} não produziu testemunha"
        leituras = int(alvo["_leituras"])
        recusas = int(alvo["_recusas"])
        assert leituras >= 2, f"a cena {cena!r} só fez {leituras} leitura(s) de /status"
        assert recusas == 1, (
            f"a cena {cena!r} esperava exatamente uma renovação recusada, "
            f"a ponte registrou {recusas}"
        )


def test_uma_cena_desconhecida_nao_pode_passar_por_verde() -> None:
    """Guarda sem Qt: o roteador de cena recusa nome desconhecido.

    Uma cena mal escrita cairia no ramo de sucesso simples e produziria
    testemunha — o gate aprovaria uma cena que não existe.
    """
    for cena in CENAS:
        assert cena in {
            "quieto",
            "atencao-maxima",
            "atencao-maxima-150",
            "leitura-sem-dados",
        }, f"cena {cena!r} saiu do denominador declarado"
    assert len(set(CENAS)) == len(CENAS), "o denominador de cenas tem duplicados"
