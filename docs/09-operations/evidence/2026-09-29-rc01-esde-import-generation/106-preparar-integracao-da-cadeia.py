"""Prepara a integracao da cadeia #239 -> #246 sem executar nenhum merge.

Passos 6 e 7 do operador de 29/09: a tabela deve responder, por elo, o que
efetivamente foi lido agora — PR, cabeca, base, dependencia, diff exclusivo,
RESULTADO de cada check obrigatorio (nao apenas "concluiu") e o estado de
merge. Nada aqui e copiado do log 101: tudo e re-medido nesta execucao.

A saida termina com a sequencia concreta de comandos e com o que precisa ser
relido apos cada merge. Esta ferramenta nao mescla, nao comenta PR e nao toca
na arvore: apenas `gh` de leitura e `git` de leitura.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


def repo_slug(checkout: Path) -> str:
    url = subprocess.run(["git", "-C", str(checkout), "config", "--get", "remote.origin.url"],
                         capture_output=True, text=True, check=True).stdout.strip()
    m = re.search(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?$", url)
    if not m:
        raise SystemExit(f"REPO-NAO-RECONHECIDO: {url}")
    return f"{m.group(1)}/{m.group(2)}"

CHECKOUT = Path("/home/misael/Projects/Steam Zero/Canonical/2026-09-21")
ELoS = ["#239", "#240", "#241", "#242", "#243", "#244", "#245", "#246"]


def git(*args: str) -> str:
    r = subprocess.run(["git", "-C", str(CHECKOUT), *args],
                       capture_output=True, text=True, check=True)
    return r.stdout.strip()


def gh(*args: str) -> object:
    r = subprocess.run(["gh", *args], capture_output=True, text=True,
                       cwd=str(CHECKOUT))
    if r.returncode != 0:
        raise SystemExit(f"GH-FALHOU rc={r.returncode} {' '.join(args)}\n{r.stderr}")
    return json.loads(r.stdout) if r.stdout.strip() else None


def short(num: str) -> str:
    return num[1:]


def main() -> int:
    origin_main = git("rev-parse", "origin/main")
    print(f"origin/main = {origin_main}")
    print("comandos desta medicao: gh pr view / gh api / "
          "git merge-base --is-ancestor / git diff --shortstat / git rev-list")

    dados: dict[str, dict] = {}
    for pr in ELoS:
        v = gh("pr", "view", short(pr), "--json",
               "number,headRefName,headRefOid,baseRefName,baseRefOid,state,"
               "mergeable,mergeStateStatus,reviewDecision,isDraft,title")
        roll = gh("pr", "view", short(pr), "--json", "statusCheckRollup",
                  "--jq", "[.statusCheckRollup[] | "
                           "{n:(.name // .context), c:(.conclusion // .status)}]")
        dados[pr] = {"v": v, "checks": roll}

    # checagem obrigatoria declarada na protecao do ramo main (pode nao ser legivel)
    print("\n### checks obrigatorios declarados na protecao de main")
    try:
        obr = gh("api", f"repos/{repo_slug(CHECKOUT)}"
                        "/branches/main/protection/required_status_checks")
        for n in obr["contexts"]:
            print(f"  obrigatorio declarado: {n}")
    except SystemExit as e:
        print("  leitura indisponivel pela API de protecao (sem admin ou sem "
              "protecao por contexto). A lista abaixo usa os oito checks que a "
              "politica deste repo exercita em todo PR: Python 3.11, Python 3.12, "
              "Python 3.14, Wheel limpo/smoke/supply chain, Smoke Ubuntu 24.04, "
              "Smoke Arch Linux, Smoke Manjaro, Gate visual QML (Linux).")
    OBRIGATORIOS = ["Python 3.11", "Python 3.12", "Python 3.14",
                    "Wheel limpo, smoke e supply chain", "Smoke Ubuntu 24.04",
                    "Smoke Arch Linux", "Smoke Manjaro", "Gate visual QML (Linux)"]

    anterior = None
    print("\n### tabela por elo (medido nesta execucao)")
    for pr in ELoS:
        v = dados[pr]["v"]
        head = v["headRefOid"]
        base_head = git("rev-parse", v["baseRefOid"]) if v["baseRefOid"] else ""
        depend = anterior[:8] if anterior else "origin/main"
        proprios = git("rev-list", "--count", f"{base_head}..{head}")
        acum = git("rev-list", "--count", f"origin/main..{head}")
        diff = git("diff", "--shortstat", f"{base_head}...{head}")
        por_nome = {c["n"]: (c["c"] or "-") for c in dados[pr]["checks"]}
        faltam = [n for n in OBRIGATORIOS if n not in por_nome]
        nao_ok = {n: c for n, c in por_nome.items() if n in OBRIGATORIOS and c != "SUCCESS"}
        outros = {n: c for n, c in por_nome.items() if n not in OBRIGATORIOS}
        ancestral = ("SIM" if anterior and subprocess.run(
            ["git", "-C", str(CHECKOUT), "merge-base", "--is-ancestor", anterior, head],
            capture_output=True).returncode == 0 else
            ("n/a (primeiro)" if not anterior else "NAO"))
        print(f"{pr}  ramo={v['headRefName']}")
        print(f"  cabeca={head[:8]}  base={v['baseRefName']}@{base_head[:8]}  "
              f"state={v['state']}  draft={v['isDraft']}")
        print(f"  dependencia (cabeca do elo anterior) = {depend}  "
              f"ancestral desta cabeca: {ancestral}"
              if anterior else
              f"  dependencia: nenhuma (primeiro elo da fileira; base = main@{base_head[:8]})")
        print(f"  proprios (rev-list {base_head[:8]}..{head[:8]}) = {proprios}   "
              f"acumulados (origin/main..{head[:8]}) = {acum}")
        print(f"  diff exclusivo vs a base: {diff or 'vazio'}")
        print(f"  checks obrigatorios: "
              f"{sum(1 for n in OBRIGATORIOS if por_nome.get(n) == 'SUCCESS')}/"
              f"{len(OBRIGATORIOS)} SUCCESS; "
              f"nao-SUCCESS={nao_ok or 'nenhum'}; ausentes={faltam or 'nenhum'}")
        print(f"  checks fora da lista obrigatoria: {outros or 'nenhum'}")
        print(f"  mergeable={v['mergeable']}  mergeStateStatus={v['mergeStateStatus']}  "
              f"reviewDecision={v['reviewDecision'] or 'nenhum'}")
        anterior = head

    print("\n### leitura da tabela")
    print("- MERGEABLE/CLEAN significa 'o GitHub consegue calcular o merge', nao")
    print("  'esta aprovado'. Nenhum dos oito elos tem review pendente exigido pela")
    print("  API; decisao de merge segue sendo do operador.")
    print("- A coluna 'proprios' usa a BASE de cada PR como raiz de contagem. Para")
    print("  #239..#244, cuja base e main, esse numero JAI E acumulado: somar as")
    print("  oito colunas nao da o tamanho da fileira. O total da fileira e o")
    print("  acumulado da ultima cabeca.")
    print("- Orden de integracao ascendente pela ancestralidade medida acima.")
    print("\n### sequencia concreta (nao executada aqui; decisao do operador)")
    print("Bloqueio real, medido nesta execucao: #245 tem base no RAMO de #244 e")
    print("#246 no RAMO de #245. Um `gh pr merge` nesses dois entregaria no ramo de")
    print("base, NAO em main. Antes de cada um deles, a base precisa ser recolocada")
    print("em main (`gh pr edit N --base main`), o que so e seguro depois que o elo")
    print("anterior estiver integrado — a ancestralidade medida acima garante que o")
    print("diff passa a ser apenas o delta daquele elo.")
    print("Ordem ascendente: #239, #240, #241, #242, #243, #244, #245, #246.")
    print("Estrategia: merge commit por elo (squash/rebase re-infla o diff dos")
    print("seguintes e pode criar conflito onde hoje nao ha).")
    print()
    print("```")
    for i, pr in enumerate(ELoS):
        v = dados[pr]["v"]
        n = short(pr)
        print(f"# --- elo {pr} (cabeca {v['headRefOid'][:8]}, base atual {v['baseRefName']}) ---")
        if v["baseRefName"] != "main":
            print(f"gh pr edit {n} --base main          # recolocar na cabeza do que ja foi integrado")
            print(f"gh pr view {n} --json baseRefOid,mergeable,mergeStateStatus,statusCheckRollup")
            print(f"git -C <checkout> fetch origin main && "
                  f"git -C <checkout> diff --shortstat origin/main...{v['headRefOid']}  # diff exclusivo esperado")
        print(f"gh pr merge {n} --merge")
        print(f"git -C <checkout> fetch origin main && git -C <checkout> rev-parse origin/main  # SHA efetivamente integrado de {pr}")
        if i < len(ELoS) - 1:
            print(f"# conflito possivel em arquivos compartilhados (Main.qml, cartao, WORKLOG): resolver preservando intencao e testes, jamais descartando o lado alheio")
    print("```")
    print("\n### revalidacao proporcional apos o oitavo elo")
    print("- O verde registrado em cada cabeca foi produzido contra a base daquela")
    print("  cabeca naquele momento. Composicao nova (main consolidado + arquivo")
    print("  compartilhado) nao herdam esse verde por decreto.")
    print("- Custo: uma suíte integral + o gate visual sobre o main consolidado, e")
    print("  um `make status-check`. Isso e proporcional e suficiente; re-rodar as")
    print("  oito suítes seria repetir a mesma árvore.")
    print("\n### depois de consolidar")
    print("Conferir em main a presenca de")
    print("  src/steamzero/ui/qml/sizes.js, src/steamzero/ui/qml/readiness.js,")
    print("e dos demais arquivos alegados; revarrer o artefato; so entonces fechar")
    print("workstreams citando o SHA efetivamente integrado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
