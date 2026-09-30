"""Reconciliacao da entrega acumulada (passo 5 do operador), somente leitura.

Produz a tabela curta que o operador precisa para decidir o merge: PR aberto de
fato, cabeca, base, ancestralidade real entre cabecas, checks obrigatorios e o
que ainda bloqueia. Nada aqui escreve na arvore do repositorio.
"""

import json
import subprocess

RAIZ = "/home/misael/Projects/Steam Zero/Canonical/2026-09-21"
URL = subprocess.run(["git", "-C", RAIZ, "config", "--get", "remote.origin.url"],
                     capture_output=True, text=True).stdout.strip()
REPO = URL.split("github.com/")[-1].removesuffix(".git")
PRS = [239, 240, 241, 242, 243, 244, 245, 246]


def git(*args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True)
    return (proc.stdout + proc.stderr).strip()


def gh_pr(numero: int) -> dict:
    proc = subprocess.run(
        ["gh", "pr", "view", str(numero), "--repo", REPO, "--json",
         "number,state,baseRefName,headRefName,headRefOid,mergeable,isDraft,title"],
        capture_output=True, text=True)
    return json.loads(proc.stdout) if proc.returncode == 0 else {"number": numero, "erro": proc.stderr.strip()}


def gh_checks(cabeca: str) -> tuple[str, int, int, int]:
    """Contagem por check-run da cabeça: success+skipped / total, e o que falta."""
    proc = subprocess.run(
        ["gh", "api", f"/repos/{REPO}/commits/{cabeca}/check-runs", "--paginate",
         "--jq", '.check_runs[] | [.status, .conclusion // "-"] | @tsv'],
        capture_output=True, text=True)
    linhas = [line for line in proc.stdout.splitlines() if line.strip()]
    total = len(linhas)
    ok = sum(1 for line in linhas
             if line.split("\t")[0] == "completed"
             and line.split("\t")[1] in {"success", "skipped"})
    pendentes = total - ok
    return (f"{ok}/{total}", pendentes, total, ok)


def main() -> None:
    print(f"{'PR':>4} {'estado':>6} {'base':<44} {'cabeça':<10} {'checks':>7} mergeável")
    cabecas: dict[int, str] = {}
    for numero in PRS:
        dados = gh_pr(numero)
        if "erro" in dados:
            print(f"#{numero}: ERRO {dados['erro']}")
            continue
        cabecas[numero] = dados["headRefOid"]
        resumo, restante, total, ok = gh_checks(dados["headRefOid"])
        print(f"#{numero:>3} {dados['state']:>6} {dados['baseRefName']:<44} "
              f"{dados['headRefOid'][:8]:<10} {resumo:>7} {dados['mergeable']}"
              f"{' (restam %d, incluindo falhas)' % restante if restante else ''}")
    print("\n### ancestralidade (git merge-base --is-ancestor)")
    ordem = [239, 240, 241, 242, 243, 244, 245, 246]
    for anterior, seguinte in zip(ordem, ordem[1:]):
        a, b = cabecas.get(anterior), cabecas.get(seguinte)
        if not a or not b:
            continue
        proc = subprocess.run(["git", "merge-base", "--is-ancestor", a, b],
                              cwd="/home/misael/Projects/Steam Zero/Canonical/2026-09-21")
        print(f"#{anterior} ({a[:8]}) eh ancestral de #{seguinte} ({b[:8]}): "
              f"{'SIM' if proc.returncode == 0 else 'NAO'}")
    origin_main = git("rev-parse", "origin/main")
    print(f"\norigin/main = {origin_main}")
    for numero in ordem:
        c = cabecas.get(numero)
        if not c:
            continue
        proc = subprocess.run(["git", "merge-base", "--is-ancestor", origin_main, c],
                              cwd="/home/misael/Projects/Steam Zero/Canonical/2026-09-21")
        count = git("rev-list", "--count", f"{origin_main}..{c}")
        print(f"#{numero}: main eh ancestral da cabeca: "
              f"{'SIM' if proc.returncode == 0 else 'NAO'}; commits acima de main: {count}")


if __name__ == "__main__":
    main()
