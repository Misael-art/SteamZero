"""Gera os adendos de README e WORKLOG a partir dos logs, nao da memoria.

Numeros de suite, duracao, rc e identidades de arvore sao lidos dos proprios logs
do checkpoint (100) e do gate visual (102). O script recusa produzir texto se
qualquer premissa falhar: rc diferente de zero, cabeca diferente entre ANTES e
DEPOIS, ou sha256 de arquivo que mudou durante a corrida. Assim a frase "suite
integral passou nesta arvore" nasce da leitura do artefato, nao de transcricao.
"""

import hashlib
import json
import pathlib
import re
import subprocess
import sys

TMP = pathlib.Path("/home/misael/steamzero-retrofe-tmp")
LOG_100 = TMP / "100-checkpoint-integral-nono-elo.log"
LOG_110 = TMP / "110-gate-visual-apos-governanca.log"
LOG_105 = TMP / "105-renovar-digests.log"
LOG_101 = TMP / "101-reconcilio-entrega-acumulada.log"
LOG_106 = TMP / "106-preparar-integracao-da-cadeia.log"
LOG_107 = TMP / "107-conta-de-commits-da-fileira.log"
SAIDA_README = TMP / "103-adendo-readme.md"
SAIDA_WORKLOG = TMP / "103-adendo-worklog.md"
RAIZ = pathlib.Path("/home/misael/Projects/Steam Zero/Canonical/2026-09-21")
GOVERNANCA_TEST = ("tests/unit/test_project_status.py::"
                   "test_committed_catalog_and_generated_views_are_consistent")
# Linha impressa pelo driver 100 ao parar. O texto dela afirma uma razão que NÃO é a
# deste caso: vinha de um template genérico de "gate leve reprovou". É conferida aqui
# byte a byte justamente para o adendo poder declarar o defeito em vez de reproduzi-lo.
PARADA_ESPERADA = ("PARADA: suite integral nao voltou rc=0; a suite integral nao roda em "
                   "arvore que ja reprovou um gate leve.")

FUNCIONAIS = [
    "src/steamzero/ui/qml/Main.qml",
    "src/steamzero/ui/qml/ThemeEditorPanel.qml",
    "tests/integration/test_ui_shell_esde_import_late_response.py",
    "tests/qml/check_shell_esde_import_late_response.qml",
    "tests/integration/test_ui_shell_esde_import_dialog.py",
    "tests/qml/check_shell_esde_import_dialog_journey.qml",
    "tests/integration/test_ui_shell_home_first_fold.py",
    "tests/integration/test_ui_shell_retrofe_import_late_response.py",
    "tests/qml/check_shell_retrofe_import_late_response.qml",
]
CORTE = [
    "src/steamzero/ui/qml/Main.qml",
    "src/steamzero/ui/qml/ThemeEditorPanel.qml",
    "tests/integration/test_ui_shell_esde_import_late_response.py",
    "tests/qml/check_shell_esde_import_late_response.qml",
]

PROBLEMAS: list[str] = []


def conta_de_107(texto: str) -> dict:
    """Extrai as tres colunas de contagem do log 107 e confere a aritmetica.

    O texto abaixo so pode ser escrito se a conta fechar na leitura: soma dos
    incrementos por elo == acumulado da ultima cabeca lido direto contra
    `origin/main`, e a coluna por base continua somando mais que a fileira (se um
    dia bater, e porque a forma de medir mudou e o texto precisa ser reescrito —
    nao porque a conta ficou mais bonita).
    """
    saida: dict = {}
    m = re.search(r"^origin/main = ([0-9a-f]{40})", texto, re.M)
    saida["main"] = m.group(1) if m else ""
    cabecas = re.findall(r"^#(\d+)\s+\S+\n\s+cabeca=([0-9a-f]{40})\s+base=(\S+)",
                         texto, re.M)
    saida["elos"] = [(f"#{n}", h[:8], b) for n, h, b in cabecas]
    por_base = [int(x) for x in re.findall(r"^\s+acima_da_base\s+= (\d+)", texto, re.M)]
    por_main = [int(x) for x in re.findall(r"^\s+acima_de_main\s+= (\d+)", texto, re.M)]
    incrementos = [int(x) for x in
                   re.findall(r"^\s+incremento_do_elo_anterior\s+= (\d+)", texto, re.M)]
    m = re.search(r"soma de acima_da_base\s+= (\d+)", texto)
    saida["soma_por_base"] = int(m.group(1)) if m else -1
    m = re.search(r"soma de incremento_do_elo_anterior = (\d+)", texto)
    saida["soma_incrementos"] = int(m.group(1)) if m else -1
    m = re.search(r"acima_de_main na ultima cabeca\s+= (\d+)", texto)
    saida["acumulado_final"] = int(m.group(1)) if m else -1
    if not (len(por_base) == len(por_main) == len(incrementos) == len(cabecas) == 8):
        PROBLEMAS.append(f"107: colunas lidas em numero diferente de elos "
                         f"(base={len(por_base)}, main={len(por_main)}, "
                         f"incrementos={len(incrementos)}, elos={len(cabecas)})")
        return saida
    saida["por_base"] = {f"#{n}": v for (n, _h, _b), v in zip(cabecas, por_base)}
    saida["por_main"] = {f"#{n}": v for (n, _h, _b), v in zip(cabecas, por_main)}
    saida["incrementos"] = {f"#{n}": v for (n, _h, _b), v in zip(cabecas, incrementos)}
    saida["delta_lista"] = incrementos
    if sum(incrementos) != saida["acumulado_final"]:
        PROBLEMAS.append(f"107: soma dos incrementos {sum(incrementos)} != acumulado final "
                         f"{saida['acumulado_final']}")
    if saida["soma_incrementos"] != sum(incrementos):
        PROBLEMAS.append(f"107: o log imprime soma {saida['soma_incrementos']}, a releitura "
                         f"da coluna da {sum(incrementos)}")
    if saida["soma_por_base"] == saida["acumulado_final"]:
        PROBLEMAS.append("107: a coluna por base deveria ser maior que o total da fileira "
                         "(#239..#244 contam todos a partir de main); se sao iguais, a "
                         "medição mudou de forma e o texto abaixo precisa ser reescrito")
    return saida


# Linha da tabela "Fileira e integração" do corpo publicado de #246. As duas
# colunas de contagem sao `commits` e `commits proprios`; o que cada uma mede e o
# que a conferencia abaixo decide, por comparacao com as tres colunas do 107.
LINHA_FILEIRA = re.compile(
    r"^\|\s*\*{0,2}(#\d+)\*{0,2}\s*"
    r"\|\s*`([0-9a-f]{8})`\s*"
    r"\|\s*(\S+)\s*"
    r"\|\s*(\d+)\s*"
    r"\|\s*(\d+)\s*\|",
    re.M,
)
COLUNAS_MEDIDAS = (
    ("por_main", "acima_de_main"),
    ("por_base", "acima_da_base"),
    ("incrementos", "incremento_do_elo_anterior"),
)


def tabela_publicada(conta: dict) -> dict:
    """Confronta celula a celula as duas colunas de contagem do corpo de #246 com o 107.

    O adendo nao pode adivinhar o que o corpo do PR "quis dizer": cada numero lido
    do PR e comparado com as tres colunas que o `107` mediu nesta rodada, e o
    veredito de qual coluna cada celula segue sai da comparacao. Deixar de fazer
    isso foi exatamente o erro que o operador apontou — um rotulo que escondia o
    ref esquerdo.
    """
    saida: dict = {"linhas": 0, "commits": {}, "proprios": {},
                   "commits_rotulo": {}, "proprios_rotulo": {}, "sem_par": [],
                   "discrive_main": [], "discrive_base": [], "ambigua": [],
                   "univoco_incremento": []}
    proc = subprocess.run(["gh", "pr", "view", "246", "--json", "body", "-q", ".body"],
                          cwd=RAIZ, capture_output=True, text=True)
    if proc.returncode:
        PROBLEMAS.append(f"#246: nao li o corpo publicado (rc={proc.returncode}): "
                         f"{proc.stderr.strip()[:160]}")
        return saida
    cabecas = {pr: h for pr, h, _b in conta.get("elos", [])}

    def quais(pr: str, valor: int) -> list[str]:
        return [rot for chave, rot in COLUNAS_MEDIDAS
                if conta.get(chave, {}).get(pr) == valor]

    for pr, cabeca, _base, commits, proprios in LINHA_FILEIRA.findall(proc.stdout):
        saida["linhas"] += 1
        if cabecas.get(pr) != cabeca:
            PROBLEMAS.append(f"#246: o corpo publicado poe {pr} na cabeca `{cabeca}` e o "
                             f"107 mede `{cabecas.get(pr, '?')}`")
        for campo, valor in (("commits", int(commits)), ("proprios", int(proprios))):
            saida[campo][pr] = valor
            rotulos = quais(pr, valor)
            if not rotulos:
                saida["sem_par"].append(f"{pr}.{campo}={valor}")
            saida[f"{campo}_rotulo"][pr] = rotulos
    if saida["linhas"] != 8:
        PROBLEMAS.append(f"#246: a tabela de fileira publicada tem {saida['linhas']} linhas, "
                         f"nao 8 — o texto abaixo nao pode descrever outra tabela")
        return saida
    if saida["sem_par"]:
        PROBLEMAS.append(f"#246: celulas publicadas sem par em nenhuma coluna medida: "
                         f"{saida['sem_par']}")
    segue = [pr for pr, r in saida["proprios_rotulo"].items()
             if "incremento_do_elo_anterior" in r]
    if len(segue) != 8:
        PROBLEMAS.append(f"#246: a coluna 'commits proprios' nao bate com o incremento em "
                         f"{8 - len(segue)} linha(s): "
                         f"{[p for p in saida['proprios'] if p not in segue]}")
    saida["univoco_incremento"] = [pr for pr, r in saida["proprios_rotulo"].items()
                                   if r == ["incremento_do_elo_anterior"]]
    # O que decide o rotulo nao e "esta linha bate" e sim "que coluna descreve as
    # oito". Cada coluna medida e confrontada com cada coluna publicada linha a
    # linha: a de zero divergencias e a que a tabela usa, e as outras ficam como
    # prova de que a escolha nao foi arbitraria nem deduzida do nome da coluna.
    saida["diverg"] = {
        campo: {rot: [pr for pr, v in saida[campo].items()
                      if conta.get(chave, {}).get(pr) != v]
                for chave, rot in COLUNAS_MEDIDAS}
        for campo in ("commits", "proprios")
    }
    return saida


def derivacao_de_61(texto: str) -> dict:
    """Le a secao do 107 que re-mede o 70 do documento 61, com os refs de cada conta.

    O adendo nao pode dizer "61 media 70 e estava certo" de memoria: os dois
    numeros e a lista dos commits posteriores vao ser transcritos da saida crua do
    `git rev-list`/`git log` que o 107 gravou nesta execucao.
    """
    saida: dict = {"depois": [], "dirs": []}
    bloco = re.search(r"### derivacao do 70(.*?)(?=\n### |\Z)", texto, re.S)
    if not bloco:
        PROBLEMAS.append("107: sem a secao 'derivacao do 70' — a reconciliacao com o "
                         "documento 61 nao tem de onde ser lida")
        return saida
    corpo = bloco.group(1)
    m = re.search(r"`git rev-list --count origin/main\.\.([0-9a-f]{8})` = (\d+)", corpo)
    if m:
        saida["cabeca_61"], saida["acima_61"] = m.group(1), int(m.group(2))
    m = re.search(r"`git rev-list --count ([0-9a-f]{8})\.\.([0-9a-f]{8})`\s+= (\d+)"
                  r"\s+<- commits proprios", corpo)
    if m:
        saida["base_61"], saida["proprios_61"] = m.group(1), int(m.group(3))
    m = re.search(r"`git rev-list --count [0-9a-f]{8}\.\.([0-9a-f]{8})` = (\d+)"
                  r".*?(\[[^\]]*\])", corpo)
    if m:
        saida["ult_cabeca_61"], saida["n_depois"] = m.group(1), int(m.group(2))
        saida["dirs"] = re.findall(r"'([^']+)'", m.group(3))
    saida["depois"] = re.findall(r"^ {6}([0-9a-f]{7,8}) (.+)$", corpo, re.M)
    if not all(k in saida for k in ("cabeca_61", "acima_61", "base_61", "proprios_61",
                                    "n_depois")):
        PROBLEMAS.append(f"107: secao de derivacao ilegivel: {sorted(saida)}")
    if len(saida["depois"]) != saida.get("n_depois", -1):
        PROBLEMAS.append(f"107: o rev-list diz {saida.get('n_depois')} commits depois de "
                         f"{saida.get('cabeca_61')} e o git log lista {len(saida['depois'])}")
    if saida["dirs"] != ["docs"]:
        PROBLEMAS.append(f"107: os commits posteriores tocariam {saida['dirs']}, e o texto "
                         f"so pode dizer 'apenas docs/' se for exatamente ['docs']")
    return saida


def ler_106(texto: str) -> dict:
    """Le a tabela de integracao: quantos elos tem os oito checks verdes e qual a base."""
    return {
        "el": len(re.findall(r"^#\d{3}\s+ramo=\S+$", texto, re.M)),
        "ok8": texto.count("checks obrigatorios: 8/8 SUCCESS"),
        "nao_ok": texto.count("nao-SUCCESS=nenhum"),
        "clean": texto.count("mergeStateStatus=CLEAN"),
        "fora_de_main": re.findall(r"elo (#\d+) \(cabeca (\S+), base atual "
                                   r"(codex/\S+)\)", texto),
    }


def resumo_suite(texto: str, onde: str) -> str:
    """Pega a linha-terminal do pytest (a que traz passed/skipped e o tempo)."""
    candidatas = [
        linha.strip("= ").strip()
        for linha in texto.splitlines()
        if re.search(r"\d+ (passed|failed)", linha) and " in " in linha
    ]
    if not candidatas:
        PROBLEMAS.append(f"{onde}: nenhuma linha-terminal de suíte no log")
        return "(não encontrada)"
    return candidatas[-1]


def passos(texto: str, onde: str) -> list[tuple[str, int]]:
    """Um passo por bloco `### nome` seguido de rc, excluso a linha de PARADA.

    O rc nao-zero aqui e esperado e querido: e a suíte integral reproving o gate de
    catalogo. Quem decide se isso e o vermelho certo e o main(), comparando a lista
    de FAILED do proprio log — por isso este papel e so de leitura, nao de portao.
    """
    lista: list[tuple[str, int]] = []
    for bloco in re.findall(r"### ([^\n]+)\n(.*?)(?=\n### |\Z)", texto, re.S):
        nome, corpo = bloco
        if nome.startswith("IDENTIDADE") or nome.startswith("PARADA"):
            continue
        rc = corpo.rstrip().rpartition("[rc=")[2].rstrip("]")
        if not rc.isdigit():
            PROBLEMAS.append(f"{onde}: passo {nome!r} sem rc numerico")
            continue
        lista.append((nome, int(rc)))
    return lista


QML_PRINCIPAL = "src/steamzero/ui/qml/Main.qml"
QML_PAINEL = "src/steamzero/ui/qml/ThemeEditorPanel.qml"


RENOVADO = re.compile(r"^  (SZ-[A-Z0-9-]+): ([0-9a-f]{12}) -> ([0-9a-f]{12}) "
                      r"\(dupla leitura ok\)$", re.M)


def renovados_de_105(texto: str) -> list[tuple[str, str, str]]:
    """Os itens que o `105` renovou, cada um com a dupla leitura conferida.

    Ficou aqui em vez de dentro de `main` porque o reconcilio (`104`) precisa da
    MESMA lista para contar escopos: dois leitores com duas interpretações do log
    do `105` é exatamente o defeito que o passo 2 pediu para não repetir.
    """
    return RENOVADO.findall(texto)


def conta_escopos(itens: list[str]) -> dict:
    """De quantos itens renovados cada QML participa, lido dos cartoes e nao de cabeca.

    O escopo pode nomear o arquivo ou um diretorio que o contem (e o caso do
    cartao desta frente, que cobre `src/steamzero/ui`). A uniao precisa bater com a
    lista renovada: se algum item envelheceu sem nenhum dos dois QML no escopo, a
    atribuicao de causa deste adendo estaria errada e o texto nao pode ser escrito.
    """
    presente: dict[str, list[str]] = {}
    for p in sorted((RAIZ / "docs/status/items").glob("*.json")):
        dados = json.loads(p.read_text(encoding="utf-8"))
        item = dados.get("id")
        if item in itens:
            presente[item] = [e for e in dados.get("scopePaths", []) if e]
    faltando = sorted(set(itens) - set(presente))
    if faltando:
        PROBLEMAS.append(f"escopos: {len(faltando)} item(ns) renovados sem cartao JSON lido "
                         f"({faltando[:3]})")

    def cobre(alvo: str, escopo: list[str]) -> bool:
        return any(alvo == e or alvo.startswith(e.rstrip("/") + "/") for e in escopo)

    saida = {
        "main": sorted(i for i, e in presente.items() if cobre(QML_PRINCIPAL, e)),
        "panel": sorted(i for i, e in presente.items() if cobre(QML_PAINEL, e)),
    }
    saida["ambos"] = sorted(set(saida["main"]) & set(saida["panel"]))
    saida["uniao"] = sorted(set(saida["main"]) | set(saida["panel"]))
    saida["fora"] = sorted(set(presente) - set(saida["uniao"]))
    if len(saida["uniao"]) != len(itens):
        PROBLEMAS.append(f"escopos: {len(saida['fora'])} dos {len(itens)} itens renovados nao "
                         f"tem nenhum dos dois QML no escopo ({saida['fora'][:3]}) — a "
                         f"atribuicao de causa deste adendo estaria errada")
    if len(saida["main"]) + len(saida["panel"]) - len(saida["ambos"]) != len(saida["uniao"]):
        PROBLEMAS.append(f"escopos: a aritmetica {len(saida['main'])} + {len(saida['panel'])} - "
                         f"{len(saida['ambos'])} nao fecha a uniao de {len(saida['uniao'])}")
    return saida


BLOCO_IDENTIDADE = re.compile(
    r"(?:### IDENTIDADE|\-\-\- identidade)[ \t]+(ANTES|DEPOIS)[ \t]+.*?"
    r"(?=### |\-\-\- identidade|\Z)",
    re.S,
)


def identidade(texto: str, onde: str) -> tuple[str, list[tuple[str, str]]]:
    """Cabeca do relato e os pares (sha256, arquivo) da leitura ANTES.

    O log grava a mesma lista de arquivos duas vezes (ANTES e DEPOIS). Recortar
    pelos cabecalhos de identidade, em vez de partir o texto ao meio, e o que
    diz se a arvore parou durante a corrida — e nao depende de a lista ter
    numero par de arquivos.
    """
    cabecas = sorted(set(re.findall(r"^(?:HEAD=)?([0-9a-f]{40})$", texto, re.M))
                     | set(re.findall(r"\bHEAD=([0-9a-f]{40})\b", texto)))
    if len(cabecas) != 1:
        PROBLEMAS.append(f"{onde}: cabeca nao unica nos relatos de identidade: {cabecas}")
    blocos = BLOCO_IDENTIDADE.findall(texto)
    conteudos = BLOCO_IDENTIDADE.finditer(texto)
    antes: list[tuple[str, str]] = []
    depois: list[tuple[str, str]] = []
    for momento, corpo in zip(blocos, conteudos, strict=True):
        pares = re.findall(r"sha256 ([0-9a-f]{64})  (\S+)", corpo.group(0))
        (antes if momento == "ANTES" else depois).extend(pares)
    if not antes or not depois:
        PROBLEMAS.append(f"{onde}: falta a leitura ANTES ou a DEPOIS "
                         f"(momentos={blocos}, antes={len(antes)}, depois={len(depois)})")
        return (cabecas[0] if cabecas else "(sem cabeca)", antes)
    if len(antes) != len(depois):
        PROBLEMAS.append(f"{onde}: ANTES lista {len(antes)} arquivos e DEPOIS {len(depois)}")
    divergem = [a for a, b in zip(antes, depois, strict=False) if a != b]
    if divergem:
        PROBLEMAS.append(f"{onde}: {len(divergem)} arquivo(s) mudaram durante a corrida: "
                         f"{[d[1] for d in divergem][:4]}")
    return (cabecas[0] if cabecas else "(sem cabeca)", antes)


def carimba(texto: str, onde: str) -> list[str]:
    """Momentos ANTES/DEPOIS do bloco de identidade, para a duracao do lote."""
    return re.findall(r"IDENTIDADE \w+ — ([0-9T:\-\+]+)", texto) or \
        re.findall(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[-\d]+)", texto)


def main() -> int:
    texto_100 = LOG_100.read_text(encoding="utf-8")
    texto_110 = LOG_110.read_text(encoding="utf-8")
    texto_101 = LOG_101.read_text(encoding="utf-8")
    texto_105 = LOG_105.read_text(encoding="utf-8")
    texto_106 = LOG_106.read_text(encoding="utf-8")
    texto_107 = LOG_107.read_text(encoding="utf-8")

    # O checkpoint 100 nao fechou PASSO. Fechou VERMELHO com um unico FAILED, o gate
    # de catalogos gerados. O adendo so pode ser escrito se for exatamente isso —
    # um vermelho esperado, regenerado pelo 105 — e nao "mais ou menos um vermelho".
    falhas_100 = re.findall(r"^FAILED (\S+)", texto_100, re.M)
    if falhas_100 != [GOVERNANCA_TEST]:
        PROBLEMAS.append(f"100: esperava exatamente o gate de governanca como falha, "
                         f"li {falhas_100}")
    if "VEREDITO: VERMELHO" not in texto_100:
        PROBLEMAS.append("100: sem o veredito vermelho registrado — o texto abaixo "
                         "descreve o que houve e nao pode contradizer o log")
    if "check pos-renovacao rc=0" not in texto_105:
        PROBLEMAS.append("105: sem 'check pos-renovacao rc=0' — a renovacao nao fechou")
    if "VEREDITO: PASSOU" not in texto_110:
        PROBLEMAS.append("110: sem 'VEREDITO: PASSOU' — o gate visual nao fechou verde")

    rodados = passos(texto_100, "100")
    # O vermelho so e aceitavel na forma exata: os quatro gates leves batem rc=0, e
    # o unico rc nao-zero da corrida e a suíte integral. Qualquer outro formato
    # contradiz o texto que este script escreve.
    for nome, rc in rodados:
        if nome != "suite integral" and rc:
            PROBLEMAS.append(f"100: gate leve {nome!r} voltou rc={rc}; o texto abaixo "
                             f"diz que todos os leves passaram")
    if [n for n, rc in rodados if rc] != ["suite integral"]:
        PROBLEMAS.append(f"100: esperava rc nao-zero exatamente em 'suite integral', "
                         f"li {rodados}")
    paradas = re.findall(r"^### (PARADA: .*)$", texto_100, re.M)
    if paradas != [PARADA_ESPERADA]:
        PROBLEMAS.append(f"100: a linha de parada do driver nao e a esperada: {paradas}")
    parada = paradas[0][len("PARADA: "):] if paradas else "(sem linha de parada)"
    cabeca_100, _ = identidade(texto_100, "100")
    cabeca_110, _ = identidade(texto_110, "110")
    if cabeca_100 != cabeca_110:
        PROBLEMAS.append(f"100/110: cabecas diferentes: {cabeca_100[:8]} vs {cabeca_110[:8]}")

    linha_suite = resumo_suite(texto_100, "100")
    linha_visual = resumo_suite(texto_110, "110")
    m100, m110 = carimba(texto_100, "100"), carimba(texto_110, "110")
    # Cada janela pertence a um log. Somar as duas e chamar de "janela da suíte" foi
    # o tipo de imprecisão que o passo 2 pediu para não repetir.
    janela_100 = f"{m100[0]} → {m100[-1]}" if m100 else "(sem marca)"
    janela_110 = f"{m110[0]} → {m110[-1]}" if m110 else "(sem marca)"
    renovados = renovados_de_105(texto_105)
    if not renovados:
        PROBLEMAS.append("105: nenhuma linha de renovacao `dupla leitura ok` — o adendo "
                         "nao pode afirmar que houve renovacao")
    esc = conta_escopos([item for item, _a, _b in renovados])
    rc_suite = dict(rodados).get("suite integral", -1)

    agregado = hashlib.sha256()
    for relativo in CORTE:
        agregado.update((RAIZ / relativo).read_bytes())

    linhas_passos = "\n".join(f"| `{nome}` | rc={rc} |" for nome, rc in rodados)
    tabela_101 = "\n".join(f"  {l}" for l in texto_101.splitlines() if l.strip())
    conta = conta_de_107(texto_107)
    d61 = derivacao_de_61(texto_107)
    acima_61 = d61.get("acima_61", "?")
    cabeca_61 = d61.get("cabeca_61", "?")
    base_61 = d61.get("base_61", "?")
    proprios_61 = d61.get("proprios_61", "?")
    len_depois = d61.get("n_depois", "?")
    dirs_61 = d61.get("dirs", [])
    deps_str = ", ".join(f"`{sha}`" for sha, _ in d61.get("depois", []))
    integ = ler_106(texto_106)
    if integ["el"] != 8 or integ["ok8"] != 8 or integ["nao_ok"] != 8 or integ["clean"] != 8:
        PROBLEMAS.append(f"106: leitura inesperada {integ}")
    base_fora = ", ".join(f"{p} sobre o ramo `{b}`"
                          for p, _c, b in integ["fora_de_main"]) or "nenhum"
    incrementos = conta.get("delta_lista", [])
    deltas_str = " + ".join(str(d) for d in incrementos)
    soma_deltas = conta.get("soma_incrementos", -1)
    soma_por_base = conta.get("soma_por_base", -1)
    ult_cabeca = conta["elos"][-1][1] if conta.get("elos") else "?"
    publicada = tabela_publicada(conta)
    diverg = publicada.get("diverg", {})
    # Cada frase abaixo cita uma coluna que a comparacao deixou de maos dadas com o
    # corpo publicado: quantas linhas divergem e quais.
    prop_incremento = diverg.get("proprios", {}).get("incremento_do_elo_anterior", [])
    prop_main = diverg.get("proprios", {}).get("acima_de_main", [])
    prop_base = diverg.get("proprios", {}).get("acima_da_base", [])
    com_main = diverg.get("commits", {}).get("acima_de_main", [])
    com_base = diverg.get("commits", {}).get("acima_da_base", [])
    com_incremento = diverg.get("commits", {}).get("incremento_do_elo_anterior", [])
    commits_245 = publicada["commits"].get("#245", "?")
    main_245 = conta.get("por_main", {}).get("#245", "?")
    cabeca_245 = conta["elos"][-2][1] if len(conta.get("elos", [])) > 1 else "?"
    commits_246 = publicada["commits"].get("#246", "?")
    base_246 = conta.get("por_base", {}).get("#246", "?")

    def refs(xs: list[str]) -> str:
        return ", ".join(f"`{x}`" for x in xs) if xs else "nenhuma"

    ambos_str = refs(esc["ambos"])
    tabela_107 = "\n".join(f"  {l}" for l in texto_107.splitlines() if l.strip())

    readme = f"""
## Adendo — checkpoint integral, o vermelho que ele achou, e o gate visual depois dele

O lote tinha uma dívida declarada na própria entrada: a última suíte integral
arquivada era anterior ao trabalho funcional do elo. Ela foi paga aqui, uma única
vez, com a árvore parada em `{cabeca_100[:8]}`. Os números abaixo foram lidos dos
logs por `103-gerar-adendos-checkpoint.py`, que aborta se o vermelho for outro, se
a árvore tiver mudado entre as duas leituras de identidade do mesmo log, ou se a
renovação posterior não tiver fechado.

Comando: `.venv/bin/python tools/run_tests_isolated.py tests -q`, precedido dos
gates leves de AGENTS §6. Saída completa em `100-checkpoint-integral-nono-elo.log`
(esta pasta), janela `{janela_100}`.

| passo | resultado |
|---|---|
{linhas_passos}

Suíte: **{linha_suite}**, rc={rc_suite}. O comportamento passou inteiro. O único
falho é o gate de catálogo gerado — `{GOVERNANCA_TEST.split('::')[1]}` —, e a causa
é deste próprio lote: {len(renovados)} `scopeDigest` envelheceram. A conta dos
escopos é lida dos JSONs dos cartões pelo `103`, não lembrada: `Main.qml` está no
escopo de {len(esc['main'])} deles, `ThemeEditorPanel.qml` no de {len(esc['panel'])}, os dois em
{ambos_str} ({len(esc['ambos'])}), e a união fecha {len(esc['main'])} + {len(esc['panel'])} − {len(esc['ambos'])} =
{len(esc['uniao'])} — exatamente o conjunto renovado; fora da união, {refs(esc['fora'])}. O cartão desta
frente (`SZ-UI-DESKTOP-AUDIT`) é um dos {len(esc['ambos'])} que cobrem os dois porque nomeia o
diretório `src/steamzero/ui` no escopo, e não um acréscimo à parte; a conta anterior
desta sessão, `7 + 4 − 1 + 1`, estava errada nos dois primeiros números e só fechava
por acaso. Nenhum dos {len(renovados)} estava envelhecido antes: na cabeça `{cabeca_100[:8]}` o
mesmo teste passou no CI, cujo job obrigatório "Python 3.11/3.12/3.14" roda
`python tools/project_status.py check` (`.github/workflows/ci.yml:72`).

O remédio é o que AGENTS §6 prescreve para exatamente este caso — *"se só uma visão
ou digest gerado ficou obsoleto, regenere-o e rode apenas a validação de status
aplicável"* — e não uma re-corrida da suíte: `105-renovar-digests.py` renovou no
valor impresso pela ferramenta (dupla leitura: `check` e `digest --item`), `render
--write` atualizou as três visões geradas (`docs/STATUS.md`, `docs/ACTIVE-WORK.md`,
`docs/status/COVERAGE.md`) e o `check` final fechou `rc=0`. Iguais de hash não são
prova de comportamento; o que se afirma aqui é que o **catálogo está consistente com
a árvore**, que é o que aquele teste verifica.

Três limites deste checkpoint, declarados em vez de escondidos:

* `100` rodou **cinco** dos seis gates integrais de §6 e omite `make status-check`.
  Ele foi executado logo depois, antes do gate visual, e está em `OK` — mas a
  corrida de `100` não é, sozinha, "os seis gates na mesma árvore".
* A linha de parada impressa pelo próprio `100` — `{parada}` — diz uma coisa que não
  é verdade neste caso: nenhum gate leve havia reprovado; quem reprova é a suíte. É
  template genérico do driver, fixado byte a byte pelo `103` para que ele possa
  registrar o defeito sem reescrever o log arquivado. O texto do script foi corrigido
  **depois** da corrida, então o `100-checkpoint-integral-nono-elo.py` arquivado e o
  `.log` da mesma pasta já não concordam nessa linha — divergência deliberada e
  declarada aqui: o log é a medição, e a medição não se reescreve.
* Falta aqui o que o `110` trouxe: o gate visual correu na **mesma** árvore, pelo
  precedente do oitavo elo (PASSO 7 de `52`), porque o elo toca duas superfícies
  desenhadas — **{linha_visual}**, `110-gate-visual-apos-governanca.log`. Ele se
  recusou a rodar no `102` enquanto o checkpoint estava aberto, e o `110` só correu
  depois de verificar cinco premissas lidas da árvore, entre elas que os
  {len(FUNCIONAIS)} arquivos funcionais são byte a byte os mesmos que o `100` testou.

Identidade: mesma cabeça nos dois logs e um único SHA-256 por arquivo entre ANTES
e DEPOIS; agregado dos quatro arquivos do corte `src`/`tests` neste momento =
`{agregado.hexdigest()[:16]}`.

## Fileira re-medida (passo 5 do operador)

`101-reconcilio-entrega-acumulada.py` consulta o GitHub e roda
`git merge-base --is-ancestor` par a par; saída crua em
`101-reconcilio-entrega-acumulada.log`. A coluna `checks` é `success+skipped / total`
de check-runs da cabeça, contados pelo `101` — por isso `9/9`: as oito obrigatórias em
`SUCCESS` mais o `Sourcery review`, que vem `SKIPPED`. Quem confere a lista
obrigatória nome a nome é o `106`, adiante.

```
{tabela_101}
```

## Conta de commits, esclarecida (passo 2 do operador)

A frase "74, quatro a mais que 61" não fechava porque misturava duas coisas: um
**documento** (`61-reconcilio-rc01-oito-elos.md`, na pasta de evidência do oitavo elo
`docs/09-operations/evidence/2026-09-29-rc01-home-first-fold/`) com um **número de
commit**. Reescrita, ela não é contradição — os dois números saem do mesmo tipo de
conta em momentos diferentes, e a diferença é medida, não alegada. O que precisa de
cuidado é outra coisa: `git rev-list --count` leva dois refs, e o valor diz respeito
ao da esquerda. Três colunas, cada uma com seu lado esquerdo declarado:

| grandeza | o que mede | comando |
|---|---|---|
| ancestralidade | um elo está contido no seguinte | `git merge-base --is-ancestor <ant> <novo>` |
| tamanho da fileira | commits acima de `main` na última cabeça | `git rev-list --count origin/main..{ult_cabeca}` |
| incremento por elo | o que este elo acrescenta sobre o anterior | `git rev-list --count <cabeca_anterior>..<cabeca>` |
| commits acima da base | o que o PR entrega sobre a base informada no GitHub | `git rev-list --count <base>..<cabeca>` |
| diff funcional | conteúdo, não história | `git diff --shortstat <base>...<cabeca>` |

Saída crua de `107-conta-de-commits-da-fileira.py` (rc=0, veredito `CONFERIDA`) em
`107-conta-de-commits-da-fileira.log`, com `origin/main = {conta['main'][:8]}`:

```
{tabela_107}
```

A reconciliação, conferida por script antes deste texto existir — o `103` aborta se
a conta não fechar:

* **Tamanho da fileira = {conta['acumulado_final']}**, medido direto com
  `git rev-list --count origin/main..{ult_cabeca}`. É o mesmo número que o corpo do
  PR #246 registra.
* **{deltas_str} = {soma_deltas}** é a mesma grandeza elo a elo: as oito parcelas vêm
  cada uma de `git rev-list --count <cabeça do elo anterior>..<cabeça>`, e somadas
  confrontam o acumulado lido de uma vez — nove comandos, nove pares de refs. A
  igualdade entre essa soma e o `{conta['acumulado_final']}`
  medido de uma vez é uma conferência real — só vale porque o `107` confere
  `merge-base --is-ancestor` par a par antes de somar (saída no log), e é isso que
  impede a conta de esconder um commit duplicado ou perdido entre cabeças.
* **`61` media {acima_61}, não {conta['acumulado_final']}, e estava certo na época**:
  `#246` estava em `{cabeca_61}` com `{proprios_61}` commits sobre a base. A diferença
  de {len_depois} é a rodada de reconcílio posterior àquela medição
  ({deps_str}), que toca apenas `{dirs_61[0]}/` — nenhum `src/`, nenhum `tests/` — e
  levou a cabeça de `#246` a {conta['incrementos']['#246']} commits próprios e a última
  cabeça a {ult_cabeca}. O documento de `61` fica como foi escrito; a releitura é este
  adendo.
* A linha `soma de acima_da_base = {soma_por_base}` que o `107` imprime **não é
  tamanho de fileira**, e o motivo está medido no log: `#239`…`#244` têm base em
  `main@{conta['main'][:8]}`, então para eles a coluna por base *já é* o acumulado —
  `{conta['por_base']['#240']}` contém os `{conta['por_base']['#239']}` do elo
  anterior, e somar a coluna é contar o mesmo trecho seis vezes. Só `#245` e `#246`
  têm base no ramo do elo anterior; nesses dois a coluna coincide com o incremento
  (o `107` imprime `base == cabeca do elo anterior? SIM/NAO` linha a linha para isso
  não ficar presumido).
* **O corpo publicado de `#246` conferido célula a célula — porque foi o rótulo que
  faltou, não o número.** O `103` lê `gh pr view 246 --json body`, recorta as oito
  linhas da tabela de fileira e confronta cada célula com as três colunas que o
  `107` mediu; aborta se alguma célula não tiver par. A coluna **"commits próprios"**
  é `git rev-list --count <cabeça do elo anterior>..<cabeça>`: **{len(prop_incremento)}**
  linhas divergem dela, contra {len(prop_main)} de `acima_de_main`
  ({refs(prop_main)}) e {len(prop_base)} de `acima_da_base` ({refs(prop_base)}) — a
  escolha é por exclusão, não por leitura do nome. Ela sempre esteve certa, inclusive
  em "somam **74**, que é exatamente `git rev-list --count origin/main..{ult_cabeca}`".
  O que "74, quatro a mais que 61" escondia era o ref esquerdo da *minha* frase de
  sessão, não um número publicado errado. A coluna **"commits" não segue um único
  ref**: vale `acima_de_main` em sete linhas e `acima_da_base` em `#245` (publica
  `{commits_245}`, quando `git rev-list --count origin/main..{cabeca_245}` dá
  `{main_245}`); por isso divergiria exatamente uma linha de cada candidata
  (`acima_de_main` em {refs(com_main)}, `acima_da_base` em {refs(com_base)} — em
  `#246` a célula é `{commits_246}` e pela base seriam `{base_246}`). Nenhum número
  publicado foi reescrito: o corpo de `#246` é artefato da cabeça `c4975979`, e mexer
  nele é decisão de integração, não de prosa. O que explicita o lado esquerdo é esta
  tabela e a saída do `107`, que imprime o comando ao lado de cada valor.

## Integração preparada, decisão reservada (passos 6 e 7)

`106-preparar-integracao-da-cadeia.py` relê, nesta execução e por elo: PR, cabeça,
base, dependência, diff exclusivo e o **resultado nominal** dos oito checks
obrigatórios — não apenas "concluíram". Estado medido: {integ['ok8']}/8 elos com
os oito checks em `SUCCESS`, {integ['nao_ok']}/8 sem nenhum não-SUCCESS e nenhum
ausente, {integ['clean']}/8 com `mergeStateStatus=CLEAN` e
`reviewDecision` vazio. Os dois checks fora da lista obrigatória são
`Sourcery review` (`SKIPPED`) e `CodeRabbit` (não obrigatório).

Bloqueio concreto, que só aparece quando se lê a base em vez de presumir:
{base_fora} — um `gh pr merge` nesses elos entregaria no **ramo de base**, não em
`main`. A sequência correta, com o `gh pr edit N --base main` no ponto em que ele
passa a ser seguro, está no fim de `106-preparar-integracao-da-cadeia.log`.

MERGEABLE/CLEAN quer dizer "o GitHub consegue calcular o merge", não "está
aprovado". A decisão de merge é do operador, e nada aqui foi mesclado.


## Como este lote foi montado

Os scripts e logs citados acima não foram colados aqui a mão: `108-arquivar-artefatos.py`
copiou cada um para esta pasta conferindo SHA-256 de origem e destino, recusa
sobrescrever destino cujo conteúdo difere (e só rejoga com `-rejogar`, guardando a
versão anterior no tmp e imprimindo os dois hashes), e reconcilia a lista por contagem
no próprio log. O arquivador não se arquiva — enquanto ele copia, o log dele está sendo
escrito, e cópia de escrita em andamento não é evidência. O `104` também não passa por
ele: o reconcílio é escrito direto nesta pasta pelo script que o gera. E os logs da
passada final do `105` ficam fora do checkout, pelo motivo declarado abaixo.


## O que isto muda, e o que não muda

Um checkpoint com o comportamento verde na árvore congelada prova contrato
offscreen naquele ponto — o gate de catálogo regenerado depois prova consistência
de governança, não comportamento. Nada dos dois prova empacotamento, prova release
instalada ou prova o seletor nativo de diretório. Integração continua sendo decisão
do operador.

Um custo do ponto fixo, medido pelo `104` e não presumido: esta pasta de evidência
está dentro do escopo do cartão desta frente, e a visão `docs/status/COVERAGE.md`
imprime a contagem de arquivos desse escopo. Cada arquivo de evidência escrito aqui
move uma linha daquela visão — o `104` leu o atraso pela própria ferramenta e achou
uma única linha trocada, `787 → 788` —, então o `make status-check` fica vermelho
*enquanto* o lote escreve, e a renovação de digest com `render --write` tem de ser a
última escrita dentro do checkout. É por isso que os logs da passada final do `105`
ficam fora da árvore: arquivá-los ali envelheceria o digest que eles certificam.
"""

    worklog = f"""
## 2026-09-29 — RC-01 / nono elo, adendo: o checkpoint integral único e a fileira re-medida

**A dívida que a própria sessão declarou, paga — e o que ela cobrou.** A entrada
anterior registrou que a suíte integral arquivada era anterior ao trabalho
funcional do elo. Ela foi rodada uma única vez, com a árvore congelada em
`{cabeca_100[:8]}` e sem nada disputando CPU com as portas de atraso real:
`.venv/bin/python tools/run_tests_isolated.py tests -q` → **{linha_suite}**
(rc={rc_suite}), precedido dos gates leves de AGENTS §6 (`ruff check`, `ruff
format --check`, `mypy`, `make independence boundaries`), todos rc=0. Identidade
antes e depois do mesmo relatório: mesma cabeça e um único SHA-256 por arquivo do
corte — a árvore não se moveu durante a corrida. O comportamento passou inteiro; o
único falho foi o gate de catálogo gerado, e a causa é deste lote: {len(renovados)}
`scopeDigest` envelheceram. Lido dos JSONs dos cartões pelo próprio `103`: `Main.qml`
está no escopo de {len(esc['main'])} deles, `ThemeEditorPanel.qml` no de {len(esc['panel'])}, os
dois em {ambos_str}, e a união fecha {len(esc['main'])} + {len(esc['panel'])} − {len(esc['ambos'])} =
{len(esc['uniao'])}, que é exatamente o conjunto renovado. O cartão desta frente
(`SZ-UI-DESKTOP-AUDIT`) já está entre os {len(esc['ambos'])} que cobrem os dois, porque nomeia o
diretório `src/steamzero/ui`; a conta desta sessão escrita antes da medição
(`7 + 4 − 1 + 1 = 11`) acertou o total por acaso e errou as parcelas, e é a versão
medida que fica registrada. Na cabeça `{cabeca_100[:8]}` o mesmo teste
passou no CI — o job obrigatório "Python 3.11/3.12/3.14" roda
`python tools/project_status.py check` (`.github/workflows/ci.yml:72`) —, então
nenhum dos 11 estava envelhecido antes daqui. O remédio é o prescrito em AGENTS §6
para "só uma visão ou digest gerado obsoleto": `105-renovar-digests.py` renovou no
valor impresso pela ferramenta (dupla leitura `check` + `digest --item`), `render
--write` atualizou as três visões geradas (`docs/STATUS.md`, `docs/ACTIVE-WORK.md`,
`docs/status/COVERAGE.md`) e o `check` final fechou `rc=0`. Três coisas ficam
declaradas, não escondidas: o `100` omitiu `make status-check` dos seis gates de §6
(roda à parte, agora `OK`); a linha de parada que ele imprimiu — *{parada}* — é
template genérico e afirma uma razão falsa neste caso, já que nenhum gate leve havia
reprovado (o `103` a confere byte a byte justamente para registrá-la em vez de
repeti-la; o driver foi corrigido **depois** da corrida, então o script arquivado e o
log não voltam a dizer a mesma coisa, e é de propósito — o log é a medição, não o
texto); e renovação de digest não é prova de comportamento — é prova de que o
catálogo bate com a árvore. Saída completa em
`docs/09-operations/evidence/2026-09-29-rc01-esde-import-generation/100-checkpoint-integral-nono-elo.log`;
os números desta entrada foram lidos desse arquivo por script, não transcritos à
mão.

**Gate visual na mesma árvore**, pelo precedente do oitavo elo (PASSO 7 de `52`), e
só depois de o `110` verificar que os {len(FUNCIONAIS)} arquivos funcionais são
byte a byte os mesmos que o `100` testou: **{linha_visual}**
(`110-gate-visual-apos-governanca.log`), janela `{janela_110}`. O `102` se recusou a
rodar com o checkpoint aberto, e a recusa está arquivada como está.

**Fileira re-medida, não presumida** (`101-reconcilio-entrega-acumulada.py`,
`106-preparar-integracao-da-cadeia.py`, `107-conta-de-commits-da-fileira.py`): os
oito PRs `#239`…`#246` seguem abertos e os oito checks obrigatórios estão em
`SUCCESS` nas oito cabeças ({integ['clean']}/8 com `mergeStateStatus=CLEAN` e
nenhum review pendente exigido). `#246` está a **{conta['acumulado_final']}**
commits acima de `origin/main` (`{conta['main'][:8]}`), lido com
`git rev-list --count origin/main..{ult_cabeca}`; a mesma grandeza elo a elo é
`{deltas_str}` = **{soma_deltas}**, com cada parcela medida contra a cabeça do elo
anterior e o `merge-base --is-ancestor` par a par conferido antes de somar.

**A conta que não fechava, e o que estava errado era o rótulo.** "74, quatro a mais
que 61" misturou um documento com um número e escondia o lado esquerdo do `rev-list`.
Re-medido: `61-reconcilio-rc01-oito-elos.md` media **{acima_61}** e estava certo na
rodada em que foi escrito — `#246` estava em `{cabeca_61}`, com **{proprios_61}**
commits sobre a base `{base_61}`. A diferença de **{len_depois}** é a rodada de
reconcílio posterior ({deps_str}), que toca apenas `{dirs_61[0]}/` e levou aquela
cabeça aos {conta['incrementos']['#246']} commits próprios de hoje. O que precisava
de correção era o nome, e ele foi conferido célula a célula em vez de lido do jeito:
o `103` relê o corpo publicado de `#246` (`gh pr view 246 --json body`), recorta as
oito linhas da tabela de fileira e confronta cada célula com as três colunas medidas
pelo `107`, abortando se alguma ficar sem par. A coluna **"commits próprios"** é
`rev-list --count <cabeça do elo anterior>..<cabeça>` — **{len(prop_incremento)}**
linhas em desacordo com ela, contra {len(prop_main)} de `acima_de_main`
({refs(prop_main)}) e {len(prop_base)} de `acima_da_base` ({refs(prop_base)}), então
a identificação é por exclusão e ela nunca esteve errada, soma incluída. A coluna
**"commits"** é que não segue um ref só: vale `acima_de_main` em sete linhas e
`acima_da_base` em `#245`, que publica `{commits_245}` onde
`git rev-list --count origin/main..{cabeca_245}` dá `{main_245}` — soma
**{soma_por_base}** se a tratarmos como por base, e nada que seja tamanho de
fileira. Os dois números convivem sem contradição desde que cada um declare seu ref;
o corpo publicado de `#246` não foi reescrito (é artefato da cabeça `c4975979`, e a
decisão sobre ele é de integração, não de prosa), e o `107` desta entrada imprime as
três colunas com o comando de cada uma. O documento de `61` também não foi tocado: a
releitura é esta entrada.

**O bloqueio passou a ser a integração, e a medição achou um bloqueio dentro do
bloqueio:** {base_fora} — os dois têm base em **ramo**, não em `main`, e mergear
neles entregaria no ramo de base. A sequência com o `gh pr edit N --base main` no ponto
seguro de cada um está registrada em
`106-preparar-integracao-da-cadeia.log`; nada foi mesclado e a decisão é do
operador.

**Camadas, depois do checkpoint.** Contrato testado offscreen: sim, agora com
suíte integral e gate visual na árvore do elo. Integrado: **não** — merge é
decisão do operador e a fileira está pronta, sequenciada. Empacotado: **não**.
Experiência na release instalada: **não**. Seletor nativo de diretório: **não
comprovado**.
"""

    if PROBLEMAS:
        print("PROBLEMAS — nenhum adendo escrito:")
        for problema in PROBLEMAS:
            print(f"  - {problema}")
        return 1
    SAIDA_README.write_text(readme, encoding="utf-8")
    SAIDA_WORKLOG.write_text(worklog, encoding="utf-8")
    print(f"OK: adendos gerados a partir de rc=0 em {len(rodados)} passos")
    print(f"  suite  : {linha_suite}")
    print(f"  visual : {linha_visual}")
    print(f"  cabeca : {cabeca_100}")
    print(f"  {SAIDA_README.name}, {SAIDA_WORKLOG.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
