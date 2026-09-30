"""Reconcilio da RC-01 na cabeca do nono elo, com medidas feitas agora (104).

Modelo: 61-reconcilio-rc01-oito-elos.md, mesmo conjunto de criterios e as cinco
camadas do operador (I interface · C contrato offscreen · G integrado · P
empacotado · H release instalada). Diferenca de metodo: nenhum numero e copiado
de 61. Cada grandeza e remedida aqui e a tabela so e escrita se as premissas
baterem; se alguma escrita de `esdeImportBusy = false` estiver incondicional, o
script aborta em vez de escrever "contrato testado".
"""

import importlib.util
import json
import pathlib
import re
import subprocess
import sys

RAIZ = pathlib.Path("/home/misael/Projects/Steam Zero/Canonical/2026-09-21")
VENV_PY = RAIZ / ".venv/bin/python"
PAINEL = RAIZ / "src/steamzero/ui/qml/ThemeEditorPanel.qml"
RAIZ_QML = RAIZ / "src/steamzero/ui/qml/Main.qml"
TMP = pathlib.Path("/home/misael/steamzero-retrofe-tmp")
LOG_101 = TMP / "101-reconcilio-entrega-acumulada.log"
LOG_107 = TMP / "107-conta-de-commits-da-fileira.log"
LOG_100 = TMP / "100-checkpoint-integral-nono-elo.log"
LOG_110 = TMP / "110-gate-visual-apos-governanca.log"
LOG_105 = TMP / "105-renovar-digests.log"
# A unica obsolescencia tolerada nesta escrita: o digest do cartao desta frente,
# envelhecido pelo README e pelas evidencias que este proprio lote ainda vai
# escrever. Renovar por ultimo e a regra do ponto fixo, nao uma falha.
OBSOLETA = re.compile(r"^- (SZ-[A-Z0-9-]+): evidencia obsoleta; scopeDigest esperado "
                      r"[0-9a-f]{64}, atual [0-9a-f]{64}$", re.M)

# A leitura da conta de commits, dos logs do checkpoint e da fileira de PRs vem do
# MESMO modulo que gera os adendos do README/WORKLOG (103). reconcilio e adendo nao
# podem ter duas interpretacoes do mesmo log — foi exatamente isso que produziu o
# "74, quatro a mais que 61". O 103 so define funcoes em nivel de modulo.
_espec = importlib.util.spec_from_file_location("adendos_do_checkpoint",
                                                TMP / "103-gerar-adendos-checkpoint.py")
assert _espec and _espec.loader, "103 nao esta disponivel para ser lido"
adendos = importlib.util.module_from_spec(_espec)
_espec.loader.exec_module(adendos)

GOVERNANCA_TEST = adendos.GOVERNANCA_TEST
FUNCIONAIS = adendos.FUNCIONAIS

SAIDA = RAIZ / "docs/09-operations/evidence/2026-09-29-rc01-esde-import-generation/104-reconcilio-rc01-nono-elo.md"
MUT = RAIZ / "docs/09-operations/evidence/2026-09-29-rc01-esde-import-generation"
# O cartão desta frente nomeia o diretório `src/steamzero/ui` no escopo: escrever
# evidência aqui envelhece o digest dele. É o item que o ponto fixo renova por último.
CARTAO_DESTE_ELO = "SZ-UI-DESKTOP-AUDIT"
# As três visões que `tools/project_status.py render --write` produz na última
# renovação. Conferidas na árvore: o texto diz que elas mudaram, então quem muda.
VISOES = ("docs/STATUS.md", "docs/ACTIVE-WORK.md", "docs/status/COVERAGE.md")

PROBLEMAS: list[str] = []


def git(*args: str) -> str:
    proc = subprocess.run(("git", *args), cwd=RAIZ, capture_output=True, text=True)
    if proc.returncode:
        PROBLEMAS.append(f"git {' '.join(args)} rc={proc.returncode}: {proc.stderr.strip()[:120]}")
    return proc.stdout.strip()


def escritas_busy(caminho: pathlib.Path, prefixo: str) -> list[tuple[int, str, int]]:
    """Classifica cada `…Busy = false` pela janela de 8 linhas acima dela.

    Guarda de geracao = ha uma comparacao com `<prefixo>ImportGeneration` no
    caminho ate a escrita. Revogacao = o bloco incrementa a geracao antes de
    limpar (fechar o dialogo / reset). Incondicional = nenhuma das duas, e e o
    defeito que este elo veio fechar; se aparecer, o reconcilio nao e escrito.
    """
    linhas = caminho.read_text(encoding="utf-8").splitlines()
    achados: list[tuple[int, str, int]] = []
    for indice, linha in enumerate(linhas):
        if f"{prefixo}ImportBusy = false" not in linha:
            continue
        janela = "\n".join(linhas[max(0, indice - 8):indice])
        if f"{prefixo}ImportGeneration += 1" in janela:
            classe = "revogacao"
        elif f"{prefixo}ImportGeneration" in janela:
            classe = "guarda"
        else:
            classe = "INCONDICIONAL"
        achados.append((indice + 1, classe, len(linha.strip())))
    return achados


def veredito_baterias() -> dict[str, str]:
    saida: dict[str, str] = {}
    for nome in ("70-bateria-mutacoes-esde.log", "73-bateria-mutacoes-esde-raiz.log"):
        texto = (MUT / nome).read_text(encoding="utf-8")
        pego = re.search(r"== veredito ==\s*(.+)", texto)
        saida[nome] = pego.group(1).strip() if pego else "(sem veredito no log)"
    return saida


# Lido pelo interpretador do próprio projeto: `project_status` importa `jsonschema`,
# que só existe no venv da árvore. Rodar esta leitura com o python do sistema produz
# um ImportError que o reconcílio reportaria como "não sei o atraso" — e ele precisa
# saber. Os três caminhos chegam por argv para a ordem não ser duplicada aqui.
_VISTORIAS = r"""
import difflib, json, sys
sys.path.insert(0, "tools")
import project_status as ferramenta
nomes = sys.argv[1:4]
catalogo = ferramenta.load_catalog()
status_view, active_view = ferramenta.render_catalog(catalogo)
geradas = dict(zip(nomes, (status_view, active_view,
                           ferramenta.render_coverage(catalogo)), strict=True))
saida = {}
for relativo, gerado in geradas.items():
    atual = open(relativo, encoding="utf-8").read().splitlines()
    # Os dois lados têm de ser LISTA DE LINHAS. Fatiar a string devolve caracteres, e
    # um bloco de uma linha casaria com uma letra — foi o que aconteceu aqui antes
    # desta linha existir.
    gerado = gerado.splitlines()
    trocas, outros = [], []
    for etiqueta, i1, i2, j1, j2 in difflib.SequenceMatcher(
            None, atual, gerado).get_opcodes():
        if etiqueta == "replace":
            trocas += [[a, b] for a, b in zip(atual[i1:i2], gerado[j1:j2], strict=True)]
        elif etiqueta in ("insert", "delete"):
            outros.append(f"{etiqueta} de {max(i2 - i1, j2 - j1)} linha(s)")
    if trocas or outros:
        saida[relativo] = {"trocas": trocas, "outros": outros}
print(json.dumps(saida, ensure_ascii=False))
"""


def deriva_de_views() -> dict[str, list[tuple[str, str]]]:
    """O que cada visão gerada teria se a ferramenta a escrevesse agora, sem escrever.

    `render_coverage` imprime a contagem de arquivos do escopo de cada cartão: cada
    evidência escrita neste lote move essa linha. Ler o atraso pela própria ferramenta
    é o que permite dizer *qual* linha está atrás e por quê, em vez de aceitar o
    vermelho da visão como "gerado, tanto faz".
    """
    proc = subprocess.run((str(VENV_PY), "-c", _VISTORIAS, *VISOES), cwd=RAIZ,
                          capture_output=True, text=True)
    if proc.returncode:
        PROBLEMAS.append(f"views: a leitura do gerador falhou rc={proc.returncode}: "
                         f"{proc.stderr.strip()[:160]}")
        return {}
    atraso: dict[str, list[tuple[str, str]]] = {}
    for relativo, corpo in json.loads(proc.stdout).items():
        for outro in corpo["outros"]:
            # Troca de valor é "a visão está atrás do número". Linha que só some ou só
            # aparece é outra coisa, e este reconcílio não a sabe explicar.
            PROBLEMAS.append(f"views: {relativo} tem {outro} frente ao gerador — "
                             "atraso não é troca de valor")
        if corpo["trocas"]:
            atraso[relativo] = [(a, b) for a, b in corpo["trocas"]]
            for a, b in atraso[relativo]:
                # Uma troca de valor em tabela gerada troca a MESMA linha: o primeiro
                # token é a chave da linha. Se diferir, o que foi comparado não são
                # duas linhas da mesma visão — foi exatamente assim que um fatiamento
                # de string entrou aqui uma vez.
                if not a.split() or not b.split() or a.split()[0] != b.split()[0]:
                    PROBLEMAS.append(f"views: {relativo} trocou {a[:40]!r} por {b[:40]!r} — "
                                     "não é a mesma linha da tabela; a leitura do atraso "
                                     "está comparando coisas diferentes")
    return atraso


def visoes_na_arvore() -> list[str]:
    """Quais visões geradas este lote deixou pendentes de commit na árvore.

    O `104` afirma no texto que o `render --write` atualizou as visões; conferir isso
    é ler o `git status` delas, não lembrar quantas são.
    """
    dito = git("status", "--porcelain", "--", *VISOES)
    achadas = sorted(l.split(None, 1)[1].strip() for l in dito.splitlines() if l.strip())
    faltando = sorted(set(VISOES) - set(achadas))
    if faltando:
        PROBLEMAS.append(f"visoes geradas sem alteração na árvore: {faltando} — o texto deste "
                         "reconcílio diz que o `render --write` as atualizou")
    return achadas


def linha_log(texto: str, onde: str) -> str:
    candidatas = [
        l.strip("= ").strip() for l in texto.splitlines()
        if re.search(r"\d+ (passed|failed)", l) and " in " in l
    ]
    if not candidatas:
        PROBLEMAS.append(f"{onde}: sem linha-terminal de suite")
        return "(não encontrada)"
    return candidatas[-1]


def main() -> int:
    origin_main = git("rev-parse", "origin/main")
    cabeca = git("rev-parse", "HEAD")
    ramo = git("rev-parse", "--abbrev-ref", "HEAD")

    ls_tree = git("ls-tree", "-r", "--name-only", "origin/main", "--",
                  "src/steamzero/ui/qml/sizes.js", "src/steamzero/ui/qml/readiness.js")
    if ls_tree:
        PROBLEMAS.append(f"formatadores ja existem em main? {ls_tree!r} — a linha P mudaria")

    contagens = {
        caminho.name: {
            simbolo: subprocess.run(["grep", "-c", simbolo, str(caminho)],
                                    capture_output=True, text=True).stdout.strip() or "0"
            for simbolo in ("esdeImportGeneration", "retrofeImportGeneration")
        }
        for caminho in (PAINEL, RAIZ_QML)
    }

    painel_escritas = escritas_busy(PAINEL, "panel.esde")
    raiz_escritas = escritas_busy(RAIZ_QML, "root.esde")
    incondicionais = [e for e in painel_escritas + raiz_escritas if e[1] == "INCONDICIONAL"]
    if incondicionais:
        PROBLEMAS.append(f"{len(incondicionais)} escrita(s) incondicional de Busy=false: {incondicionais}")

    texto_101 = LOG_101.read_text(encoding="utf-8")
    commits_246 = re.search(r"#246: main eh ancestral da cabeca: SIM; commits acima de main: (\d+)",
                            texto_101)
    if not commits_246:
        PROBLEMAS.append("101: nenhuma linha de contagem de #246 — o reconcilio nao pode afirmar 74")

    texto_107 = LOG_107.read_text(encoding="utf-8")
    conta = adendos.conta_de_107(texto_107)
    d61 = adendos.derivacao_de_61(texto_107)
    PROBLEMAS.extend(f"107/103: {p}" for p in adendos.PROBLEMAS)
    adendos.PROBLEMAS.clear()
    deltas_str = " + ".join(str(v) for v in conta.get("delta_lista", []))
    soma_deltas = conta.get("soma_incrementos", -1)
    soma_por_base = conta.get("soma_por_base", -1)
    acima_61 = d61.get("acima_61", "?")
    cabeca_61 = d61.get("cabeca_61", "?")
    base_61 = d61.get("base_61", "?")
    proprios_61 = d61.get("proprios_61", "?")
    len_depois = d61.get("n_depois", "?")
    deps_str = ", ".join(f"`{sha}`" for sha, _ in d61.get("depois", []))
    dirs_61 = "/".join(d61.get("dirs", [])) or "?"
    incrementos = conta.get("incrementos", {})
    proprios_246 = incrementos.get("#246", "?")
    if commits_246 and soma_deltas != int(commits_246.group(1)):
        PROBLEMAS.append(f"107: os incrementos somam {soma_deltas} e 101 mede "
                         f"{commits_246.group(1)} acima de main em #246")

    texto_100 = LOG_100.read_text(encoding="utf-8")
    texto_110 = LOG_110.read_text(encoding="utf-8")
    # O checkpoint 100 fechou VERMELHO com um unico FAILED, o gate de catalogos gerados.
    # O adendo e este reconcilio dizem O QUE envelheceu ali; isso nao e lembrado, e lido
    # dos cartoes (conta_escopos) e conferido na ferramenta (deriva_de_views). Aceitar a
    # prova exige que seja exatamente isso, e que a arvore funcional dos dois logs seja
    # a mesma — nao declarar o verde.
    falhas_100 = re.findall(r"^FAILED (\S+)", texto_100, re.M)
    if falhas_100 != [GOVERNANCA_TEST]:
        PROBLEMAS.append(f"100: falha(s) inesperada(s) {falhas_100}; so o gate de "
                         f"governanca seria aceitavel aqui")
    if "VEREDITO: VERMELHO" not in texto_100:
        PROBLEMAS.append("100: nao encontro o veredito vermelho — a leitura deste "
                         "reconcilio pressupoe o registro honesto do que aconteceu")
    status = subprocess.run(["make", "status-check"], cwd=RAIZ,
                            capture_output=True, text=True)
    saida_status = status.stdout + status.stderr
    # Duas classes de vermelho são aceitas aqui, enumeradas e medidas — não
    # flexibilizadas. (1) O cartão desta frente como evidência obsoleta: este lote
    # escreve README, WORKLOG e este reconcilio dentro do escopo dele, então o digest
    # renova por ÚLTIMO. (2) Uma visão gerada listada como desatualizada, e só quando
    # a leitura direta da ferramenta mostra exatamente quantas linhas dela estão
    # atrás. Cobrar rc=0 neste ponto equivaleria a exigir que a evidência não fosse
    # escrita; qualquer OUTRA linha é um vermelho real e aborta o reconcílio.
    obsoletos = OBSOLETA.findall(saida_status)
    visoes_atraso = deriva_de_views() if status.returncode else {}
    esperadas = {f"- {v} esta desatualizado; execute tools/project_status.py render --write"
                 for v in visoes_atraso}
    outras = [l for l in saida_status.splitlines()
              if l.startswith("- ") and not OBSOLETA.match(l) and l not in esperadas]
    if status.returncode == 0:
        status_desc = "o `make status-check` desta leitura está **OK**"
    elif obsoletos == [CARTAO_DESTE_ELO] and not outras:
        def detalhe(linhas: list[tuple[str, str]]) -> str:
            # O `|` da tabela gerada precisa de escape: este texto vive dentro de uma
            # linha de tabela do próprio reconcílio.
            a, b = linhas[0]
            mais = f" (+{len(linhas) - 1} outra(s))" if len(linhas) > 1 else ""
            return (f"{len(linhas)} linha(s) de valor: `{a.replace('|', chr(92) + '|')}` → "
                    f"`{b.replace('|', chr(92) + '|')}`{mais}")
        motivo = "; ".join(f"`{v}` — {detalhe(l)}" for v, l in visoes_atraso.items())
        status_desc = (f"o `make status-check` desta leitura (rc={status.returncode}) traz "
                       f"**somente** `{CARTAO_DESTE_ELO}` como evidência obsoleta" +
                       (f", mais o atraso de visão gerada — {motivo}" if visoes_atraso else "") +
                       " — o ponto fixo em trânsito: o cartão desta frente tem a pasta de "
                       "evidência dentro do próprio escopo, cada arquivo escrito aqui muda a "
                       "contagem que a visão imprime, e a renovação de digest com "
                       "`render --write` é a última escrita do lote na árvore. Não é vermelho "
                       "de contrato nem catálogo desalinhado com o código: é geração atrás da "
                       "árvore")
    else:
        PROBLEMAS.append(f"status-check rc={status.returncode}: obsoletos={obsoletos}, "
                         f"outras linhas={outras[:3]} — esperava rc=0, ou exatamente o "
                         f"obsoleto {CARTAO_DESTE_ELO} mais visões cujo atraso a ferramenta "
                         "confere linha a linha")
    if "VEREDITO: PASSOU" not in texto_110:
        PROBLEMAS.append("110: gate visual sem veredito verde; o reconcilio nao pode cita-lo")

    def pares_de_hashes(texto: str) -> dict[str, str]:
        vistos: dict[str, set[str]] = {}
        for h, p, _n in re.findall(r"sha256 ([0-9a-f]{64})  (\S+)  \((\d+) bytes\)", texto):
            vistos.setdefault(p, set()).add(h)
        instaveis = {p: next(iter(v)) for p, v in vistos.items() if len(v) == 1}
        if len(instaveis) != len(vistos):
            PROBLEMAS.append("hashes divergentes entre ANTES e DEPOIS em "
                             f"{sorted(set(vistos) - set(instaveis))}")
        return instaveis

    h100, h110 = pares_de_hashes(texto_100), pares_de_hashes(texto_110)
    # só a árvore funcional é comparável: o cartão e as visoes mudaram DE PROPÓSITO
    # na renovacao de governanca, e essa mudanca e o objeto do 105, nao do checkpoint.
    funcionais = sorted(set(FUNCIONAIS) & set(h100) & set(h110))
    divergem = sorted(p for p in funcionais if h100[p] != h110[p])
    if divergem:
        PROBLEMAS.append(f"100/110: arvore funcional divergente em {divergem}")
    if len(funcionais) != len(FUNCIONAIS):
        PROBLEMAS.append(f"100/110: esperava {len(FUNCIONAIS)} arquivos funcionais "
                         f"nos dois logs, achei {len(funcionais)}")

    renovados = adendos.renovados_de_105(LOG_105.read_text(encoding="utf-8"))
    esc = adendos.conta_escopos([item for item, _a, _b in renovados])
    PROBLEMAS.extend(f"105/103: {p}" for p in adendos.PROBLEMAS)
    adendos.PROBLEMAS.clear()
    if len(renovados) != len(esc["uniao"]):
        PROBLEMAS.append(f"escopos: {len(renovados)} itens renovados, uniao dos dois QML em "
                         f"{len(esc['uniao'])}")
    ambos_str = ", ".join(f"`{i}`" for i in esc["ambos"]) or "nenhum"
    visoes = visoes_na_arvore()

    baterias = veredito_baterias()

    if PROBLEMAS:
        print("PROBLEMAS — reconcilio nao escrito:")
        for problema in PROBLEMAS:
            print(f"  - {problema}")
        return 1

    def descreve(lista: list[tuple[int, str, int]]) -> str:
        return ", ".join(f":{linha} ({classe})" for linha, classe, _ in lista)

    texto = f"""# 104 — RC-01 reconciliada critério a critério com os nove elos (2026-09-29)

Remede o documento-fonte `61-reconcilio-rc01-oito-elos.md` (pasta do oitavo elo) contra a
cabeçada deste nono elo. **Nenhum número foi copiado de 61**: as grandezas abaixo são saída de
comando rodado agora, e o texto só existe porque as premissas bateram — o script que gera este
arquivo (`104-reconcilio-rc01-nono-elo.py`) aborta se qualquer escrita de `…esdeImportBusy =
false` estiver incondicional, se os formatadores já estiverem em `main`, se o `make
status-check` de hoje apontar qualquer obsolescência que não seja a do cartão desta
frente, se alguma das visões geradas não estiver modificada na árvore, ou se os logs do
checkpoint (`100`) e do gate visual (`110`) não trouxerem exatamente o que este documento
lhes atribui.

Enunciado normativo: `docs/12-roadmap/IMPLEMENTATION-ROADMAP.md` (lote RC-01 / P1): "Home
utilizável no orçamento aplicável; sem tela vazia enganosa; contraste essencial conforme
política; controles alcançáveis em viewport compacto e escala de texto; timeout/retry sem
corrida".

Camadas: **I** interface implementada · **C** contrato testado offscreen · **G** código integrado
em `main` · **P** artefato empacotado · **H** experiência comprovada na release instalada.

## Fundo re-medido nesta cabeça

| grandeza | valor medido agora | como conferir |
|---|---|---|
| `origin/main` | `{origin_main}` | `git fetch origin main && git rev-parse origin/main` |
| cabeça do elo (branch `__RAMO__`) | `{cabeca}` + o que este lote acrescenta por cima | `git rev-parse HEAD` |
| elos abertos da fileira | #239…#246, todos `OPEN`; **8/8 checks obrigatórios em `SUCCESS`** nas oito cabeças, `mergeStateStatus=CLEAN`, nenhum review pendente exigido | `106-preparar-integracao-da-cadeia.py` → `106-preparar-integracao-da-cadeia.log` |
| ancestralidade | linear, par a par (`merge-base --is-ancestor`): #239 → #240 → … → #246, todas descendentes de `origin/main` | mesmo log, seção de cada elo |
| commits de `#246` acima de `main` | **{commits_246.group(1)}** | `git rev-list --count origin/main..c4975979` |
| conta da fileira, por elo | incrementos `{deltas_str}` = **{soma_deltas}**, cada um medido contra a cabeça do elo anterior, fechando com o acumulado da última cabeça; a coluna "acima da base" de `107`, somando **{soma_por_base}**, NÃO é tamanho da fileira — em #239…#244 (base `main`) ela já é acumulado e a soma aninha o mesmo trecho | `107-conta-de-commits-da-fileira.log` |
| deriva entre 61 e agora | `61` é um **documento**, não uma contagem: ele media **{acima_61}** e estava certo na rodada em que foi escrito — `#246` estava em `{cabeca_61}`, com **{proprios_61}** commits sobre a base `{base_61}`. A diferença de **{len_depois}** é a rodada de reconcílio posterior ({deps_str}), apenas `{dirs_61}/`, que levou aquela cabeça aos {proprios_246} commits próprios de hoje | `git rev-list --count origin/main..{cabeca_61}` · `git log --oneline {cabeca_61}..c4975979` |
| `sizes.js` / `readiness.js` em `main` | `git ls-tree -r --name-only origin/main -- …` devolve **vazio** | os formatadores ainda não existem em `main` |
| contrato de geração ES-DE | `grep -c esdeImportGeneration` → painel **{contagens['ThemeEditorPanel.qml']['esdeImportGeneration']}**, raiz **{contagens['Main.qml']['esdeImportGeneration']}** (61 media **0** no painel); RetroFE no painel segue em **{contagens['ThemeEditorPanel.qml']['retrofeImportGeneration']}** | os dois arquivos, nesta cabeça |
| escrita da bandeira ES-DE | painel: {descreve(painel_escritas)} · raiz: {descreve(raiz_escritas)} — **zero incondicionais** | `104-reconcilio-rc01-nono-elo.py`, janela de 8 linhas acima de cada escrita |
| checkpoint deste elo | suíte: **{linha_log(texto_100, '100')}** · visual: **{linha_log(texto_110, '110')}** | `100-checkpoint-integral-nono-elo.log`, `110-gate-visual-apos-governanca.log` |
| o vermelho do checkpoint, e só ele | `{falhas_100[0] if falhas_100 else '(nada lido)'}` — {len(renovados)} `scopeDigest` envelheceram, e todos são atribuíveis a arquivos deste elo por leitura dos cartões, não de memória: `Main.qml` está no escopo de {len(esc['main'])} dos {len(renovados)}, `ThemeEditorPanel.qml` no de {len(esc['panel'])}, os dois em {ambos_str} ({len(esc['ambos'])}), e a união fecha {len(esc['main'])} + {len(esc['panel'])} − {len(esc['ambos'])} = {len(esc['uniao'])} — exatamente o conjunto renovado, sem sobra ({len(esc['fora'])} fora). As {len(visoes)} visões geradas do catálogo (`{'`, `'.join(visoes)}`) estão modificadas na árvore por este lote. Remédio proporcional de AGENTS §6 aplicado pelo `105`: renovar no valor impresso pela ferramenta (dupla leitura `check` + `digest --item`) e `render --write`; {status_desc}. Os {len(funcionais)} arquivos funcionais são byte a byte os mesmos dos dois logs | `105-renovar-digests.log`, `110-gate-visual-apos-governanca.log` |
| limite que este lote abriu e não tapou | `100` rodou cinco dos seis gates integrais de AGENTS §6 e **omite** `make status-check`; ele foi executado à parte, antes do `110`, e é o que está citado acima. Não se chama de "checkpoint §6 completo" o que não rodou os seis na mesma corrida | `100-checkpoint-integral-nono-elo.py`, linha dos passos |
| bateria de mutações | painel (M1–M5): {baterias['70-bateria-mutacoes-esde.log']} · raiz (M6–M10): {baterias['73-bateria-mutacoes-esde-raiz.log']} | os dois logs nesta pasta |
| release instalada | `2.0.0rc1-e2af2562ebba` (26/09), valor registrado em `HOST-INSTALL.md`; **não re-medido** nesta sessão porque o host físico não foi acessado | leitura anterior, declarada como anterior |

Consequência fixa, igual à de 61: **G = não** e **H = não** para todas as linhas abaixo, sem
exceção. Nenhum SHA desta fileira está em `main` nem no artefato instalado.

## Tabela

| critério | I | C | G | P | H | situação nesta cabeça | evidência |
|---|---|---|---|---|---|---|---|
| Contraste essencial conforme política | sim | sim | **não** | não | não | **parcial — travado por decisão de produto (4,5:1 vs ≥7:1)**, não por falta de teste | `2026-09-26-rc01-central-loading/14-contraste-politica-normativa.log` |
| Loading/erro/vazio explícitos, sem tela vazia enganosa | sim | sim | **não** | não | não | **parcial** — falta integrar e provar na release | `#240`, `check_central_loading.qml` + `check_status_refresh_coalesced.qml` |
| `timeout/retry` sem corrida | sim | sim | **não** | não | não | **parcial** | `2026-09-26-rc01-central-loading/09-refresh-coercido.log` |
| Custo da consulta de status (latência) | parcial | sim, medido antes/depois | **não** | não | não | **parcial — cauda de ~11,4 s em `emulation` segue aberta**, backend, fora das fatias de UI | `01/02-baseline-e-final-status-probe.log` |
| Semântica da prontidão (UX-03) | sim | sim | **não** | sim (`readiness.js` no wheel de `af6a5c6e`) | não | **parcial — F-1 (`memoryGb`) ainda não implementado**; F-2 é de outra frente | `#243`; `2026-09-28-rc01-readiness-semantics/` |
| Unidades de armazenamento (UX-04) | sim | sim (matriz de locales, 8/8 mutações) | **não** | **sim** (`sizes.js` 2 377 bytes, `6d5ca418…` idêntico ao blob) | não | **parcial** — empacotado no CI, não integrado | `#244`; varredura 619/619 do wheel |
| Primeira dobra da Home | sim | sim, pior caso corrigido (alvo 48 px, primeiro alvo 449/468 px) | **não** | não | não | **parcial** — gap funcional (a) fechado em contrato offscreen no oitavo elo; resta G/P/H | oitavo elo: `38`, `39`, `40`, `46`, `47`, `48`, `52` |
| Foco, escala e alcance (UX-05/UX-07) | sim | sim, **só nas superfícies exercitadas** | **não** | sim | não | **parcial — cinco superfícies roláveis seguem não medidas** | `#241`, `#242` |
| **ES-DE dentro do shell — resposta tardia** | **sim** (painel e rota raiz) | **sim, agora com contrato de geração**: dez cenas com atraso real, bridge sem stub, 9/10 mutantes mortos (M9 declarado equivalente e pinado por teste de reachability) | **não** | **não** (sem varredura de wheel desta cabeça) | não | **gap funcional (b) FECHADO em C** — era a pendência nomeada pelo sétimo elo; as cinco escritas incondicionais de 61 viraram {len(painel_escritas) + len(raiz_escritas)} escritas guardadas/revogadas | este lote: `70`, `73`, `74`, `98`, `100`, `105`, `110`, README |
| RetroFE dentro do shell | sim | sim (9 cenas, 10 testemunhos, mutações) | **não** | **não ainda** — CI lido em `2d6a8957`, wheel deste elo não varrido | não | **parcial — falta a prova P** | sétimo elo, `2026-09-29-rc01-retrofe-shell-late/` |
| Respostas tardias, reabertura, erro e recuperação | **sim nas duas frentes** | **sim nas duas frentes** | **não** | não | não | **parcial — o par (b) deixou de ser exceção**: ES-DE e RetroFE obedecem ao mesmo contrato, com a mesma classe de gate | limite declarado: o pedido em voo não é cancelado; descarta-se o efeito |
| Seletor nativo de diretório | existe na árvore (`FolderDialog`) | **não dirigível por evento sob offscreen** (medido) | **não** | não | não | **PENDENTE** — a rota por Enter funciona e não promove a rota não testada | `06-medida-seletor-nativo-offscreen.md`, `17-sonda-qmltestrunner-dialogo-nativo.log` |
| Captura visual certificada em CI | — | parcial (9 capturas byte-idênticas no run 36341332344) | **não** | — | não | **parcial — `GAP-UI-VISUAL-CAPTURE-NOT-CERTIFIED-IN-CI` aberto também para este elo**: nenhuma PNG é alegada | `2026-09-27-gate-visual-causa-e-contrato/` |

## O que mudou desde 61, e o que não mudou

1. **Moveu uma linha e meia.** "ES-DE dentro do shell" passou de `C = não (sem contrato de
   geração)` para `C = sim`, com vermelho antes, gate novo, dez cenas, duas baterias de mutação e
   checkpoint integral + gate visual nesta árvore — com a ressalva devida: o checkpoint integral
   fechou com **um** falho, o gate de governanca (`100`), regenerado pelo `105` conforme o remedio
   proporcional de AGENTS §6, e o visual foi corrido depois disso pelo `110`, sobre os mesmos
   hashes funcionais. Não se escreve "suíte integral verde nesta árvore" a partir daqui; escreve-se
   "6 528 testes de comportamento verdes, o único vermelho era gerado e está regenerado". A meia linha é "Respostas tardias": ES-DE deixou de
   ser a exceção declarada.
2. **Nenhuma coluna G, P ou H se moveu** — integration é decisão do operador e nada foi varrido
   ou instalado.
3. **Remedio explícita onde 61 podia ter envelhecido:** contagem de commits da fileira (70 → {commits_246.group(1)}),
   `grep -c esdeImportGeneration` (0 → {contagens['ThemeEditorPanel.qml']['esdeImportGeneration']} no painel) e a lista das escritas da bandeira,
   agora com classe por escrita.

## O que falta para a RC-01, em ordem de dependência

* **G** — mergear a fileira na ordem de ancestralidade (#239 → … → #246 → PR deste elo). Nada
  aqui depende desta frente. **Mas a ordem sozinha não basta**, e isso foi medido agora e não em
  `61`: `#245` tem base no ramo de `#244` e `#246` no ramo de `#245`. Um merge nesses dois
  entregaria no **ramo de base**, não em `main`; é preciso recolocar a base em `main`
  (`gh pr edit N --base main`) no ponto em que o elo anterior já estiver integrado — só aí o
  diff volta a ser o delta daquele elo. Sequência completa, com o que reler depois de cada
  merge, em `106-preparar-integracao-da-cadeia.log`.
* **P** — varrer os artefatos dos elos 7, 8 e 9 (procedimento provado no `#244`: baixar o wheel,
  comparar `sha256` de cada QML com o blob da cabeça).
* **H** — validação física **preparada** em `62-preparacao-de-validacao-fisica.md`, sujeita à
  autorização específica de instalação.
* **Funcional executável dentro do escopo desta frente**: F-1 (`memoryGb` → bytes via `sizes.js`).
* **Funcional fora do escopo desta frente**: F-2 vive em `adapters/emulation.py`, dono exclusivo
  `WS-2026-09-LIBRARY-GOVERNED-MANAGEMENT` — declarado, não editado.
* **Decisão de produto**: contraste. **Limitação de plataforma**: seletor nativo fora do
  offscreen. Nenhum dos dois se resolve com teste.
"""
    texto = texto.replace("__RAMO__", ramo)
    SAIDA.write_text(texto, encoding="utf-8")
    print(f"OK: reconcilio escrito em {SAIDA.relative_to(RAIZ)}")
    print(f"  cabeca={cabeca[:8]} ramo={ramo} main={origin_main[:8]} commits_246={commits_246.group(1)}")
    print(f"  escritas painel={len(painel_escritas)} raiz={len(raiz_escritas)} incondicionais=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
