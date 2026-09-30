"""Medida de commits da fileira com o lado esquerdo de cada conta (107).

Motivo: a frase "74, quatro a mais que 61" do resumo nao fechava, e o corpo do PR
#246 e este log chamam "proprios" de coisas diferentes. `git rev-list --count` tem
dois refs; o numero diz respeito ao da esquerda. Aqui cada coluna traz o comando
completo e ha tres colunas, nomeadas pelo lado esquerdo:

  acima_da_base              = git rev-list --count <base informada pelo GitHub>..<cabeca>
  acima_de_main              = git rev-list --count origin/main..<cabeca>
  incremento_do_elo_anterior = git rev-list --count <cabeca do elo anterior>..<cabeca>

Para #239..#244 a base e main, entao as duas primeiras colunas coincidem e somar a
primeira conta o mesmo trecho varias vezes (as cabeças sao aninhadas). A soma que
significa "tamanho da fileira" so pode ser a terceira, e ela so vale se cada cabeca
for ancestral da seguinte — o que e conferido par a par antes de somar, nao
presumido.
"""

import json
import subprocess
import sys

RAIZ = "/home/misael/Projects/Steam Zero/Canonical/2026-09-21"
URL = subprocess.run(["git", "-C", RAIZ, "config", "--get", "remote.origin.url"],
                     capture_output=True, text=True).stdout.strip()
REPO = URL.split("github.com/")[-1].removesuffix(".git")
FILEIRA = [239, 240, 241, 242, 243, 244, 245, 246]

FALHAS: list[str] = []


def git(*args: str) -> str:
    proc = subprocess.run(("git", *args), cwd=RAIZ, capture_output=True, text=True)
    return (proc.stdout + proc.stderr).strip()


def conta(esq: str, dir_: str) -> int:
    return int(git("rev-list", "--count", f"{esq}..{dir_}"))


def pr(numero: int) -> dict:
    proc = subprocess.run(
        ["gh", "pr", "view", str(numero), "--repo", REPO, "--json",
         "headRefName,headRefOid,baseRefName,baseRefOid,state,mergeable"],
        capture_output=True, text=True)
    return json.loads(proc.stdout)


def main() -> int:
    origin_main = git("rev-parse", "origin/main")
    print(f"origin/main = {origin_main}")
    print("comando de tudo: git -C '/home/misael/Projects/Steam Zero/Canonical/2026-09-21' ...\n")
    soma_base = 0
    soma_inc = 0
    incrementos: list[int] = []
    anterior = origin_main
    ult = ""
    for numero in FILEIRA:
        dados = pr(numero)
        cabeca = dados["headRefOid"]
        base_cabeca = dados["baseRefOid"]
        acima_da_base = conta(base_cabeca, cabeca)
        acima_de_main = conta(origin_main, cabeca)
        incremento = conta(anterior, cabeca)
        diff = git("diff", "--shortstat", f"{base_cabeca}...{cabeca}")
        ancestral = subprocess.run(
            ["git", "merge-base", "--is-ancestor", anterior, cabeca],
            cwd=RAIZ, capture_output=True, text=True).returncode == 0
        soma_base += acima_da_base
        soma_inc += incremento
        incrementos.append(incremento)
        print(f"#{numero}  {dados['headRefName']}")
        print(f"   cabeca={cabeca}  base={dados['baseRefName']}@{base_cabeca[:8]}"
              f"  state={dados['state']} mergeable={dados['mergeable']}")
        print(f"   acima_da_base              = {acima_da_base}"
              f"   `git rev-list --count {base_cabeca[:8]}..{cabeca[:8]}`")
        print(f"   acima_de_main              = {acima_de_main}"
              f"   `git rev-list --count origin/main..{cabeca[:8]}`")
        print(f"   incremento_do_elo_anterior = {incremento}"
              f"   `git rev-list --count {anterior[:8]}..{cabeca[:8]}`")
        print(f"   diff exclusivo vs a base: {diff or '(vazio)'}")
        print(f"   elo anterior eh ancestral deste (merge-base --is-ancestor): "
              f"{'SIM' if ancestral else 'NAO'}")
        if not ancestral:
            FALHAS.append(f"#{numero}: {anterior[:8]} nao e ancestral de {cabeca[:8]} — "
                          f"o incremento desta linha nao e um elo da fileira")
        if base_cabeca not in {anterior, origin_main}:
            FALHAS.append(f"#{numero}: a base informada ({base_cabeca[:8]}) nao e nem main nem a "
                          f"cabeca do elo anterior ({anterior[:8]}) — as colunas acima comparam "
                          f"coisas que esta conta nao nomeia")
        print(f"   base == cabeca do elo anterior? {'SIM' if base_cabeca == anterior else 'NAO'}"
              f"  (base==main => a coluna por base conta de novo o trecho ja somado no elo anterior)")
        anterior = cabeca
        ult = cabeca
    acumulado_final = conta(origin_main, ult)
    print(f"\nsoma de acima_da_base              = {soma_base}   (nao e tamanho de fileira: "
          f"#239..#244 contam todos a partir de main, entao a coluna se aninha)")
    print(f"soma de incremento_do_elo_anterior = {soma_inc}   (esta e a conta da fileira)")
    print(f"acima_de_main na ultima cabeca     = {acumulado_final}   "
          f"`git rev-list --count origin/main..{ult[:8]}`")
    if soma_inc != acumulado_final:
        FALHAS.append(f"a soma dos incrementos {soma_inc} nao bate com {acumulado_final} "
                      f"medido direto contra main: ha commit duplicado, perdido, ou a "
                      f"fileira nao e linear")
    if soma_base == acumulado_final:
        FALHAS.append(f"colunas anomalas: acima_da_base somou {soma_base}, igual ao acumulado "
                      f"— esperado apenas se todas as bases ja fossem main (o que a tabela "
                      f"acima desmente para #245 e #246)")
    CABECA_ESPERADA = "c4975979b93a03e661294b6854146e76f22fa8c3"
    if ult != CABECA_ESPERADA:
        FALHAS.append(f"a fileira medida nao termina na cabeca deste lote ({ult[:8]} != "
                      f"{CABECA_ESPERADA[:8]}): a conta abaixo nao descreve esta arvore")

    # A frase "74, quatro a mais que 61" so fecha se o 70 que o documento do oitavo elo
    # media for medido de novo, e nao reescrito de memoria. 61 é arquivo, nao coluna.
    print("\n### derivacao do 70 que `61-reconcilio-rc01-oito-elos.md` media")
    CABECA_61 = "22773047"
    BASE_61 = "2d6a8957"  # cabeca de #245, base informada de #246
    acima_61 = conta(origin_main, CABECA_61)
    proprios_61 = conta(BASE_61, CABECA_61)
    depois = git("log", "--oneline", f"{CABECA_61}..{CABECA_ESPERADA}").splitlines()
    dirs = sorted({linha.split("/")[0] for linha in
                   git("diff", "--name-only", f"{CABECA_61}..{CABECA_ESPERADA}").splitlines()})
    print(f"   `git rev-list --count origin/main..{CABECA_61}` = {acima_61}"
          f"   <- o numero que o documento de 61 registrou, na cabeza daquela rodada")
    print(f"   `git rev-list --count {BASE_61}..{CABECA_61}`   = {proprios_61}"
          f"   <- commits proprios de #246 naquela cabeca")
    print(f"   `git rev-list --count {CABECA_61}..{CABECA_ESPERADA[:8]}` = {len(depois)}"
          f"   <- rodada de reconcilio posterior, so `docs/`: {dirs}")
    for linha in depois:
        print(f"      {linha}")
    if (acima_61, proprios_61, len(depois)) != (70, 12, 4):
        FALHAS.append(f"derivacao de 61 nao bate: acumulado={acima_61} proprios={proprios_61} "
                      f"depois={len(depois)} (esperado 70/12/4)")
    if dirs != ["docs"]:
        FALHAS.append(f"os {len(depois)} commits posteriores tocariam {dirs}, e o texto diz "
                      f"que sao so documentais")
    expressao = " + ".join(str(i) for i in incrementos)
    for falha in FALHAS:
        print(f"FALHA: {falha}")
    print(f"\nVEREDITO: {'CONFERIDA' if not FALHAS else 'NAO CONFERIDA'} — tamanho da fileira = "
          f"{soma_inc} = {expressao} (incrementos por elo, cada um contra a cabeca anterior), "
          f"igual ao {acumulado_final} medido direto contra origin/main. "
          f"A coluna por base somaria {soma_base} e nao e tamanho de nada.")
    return 0 if not FALHAS else 1


if __name__ == "__main__":
    sys.exit(main())
