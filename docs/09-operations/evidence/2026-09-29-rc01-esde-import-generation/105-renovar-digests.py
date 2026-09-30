"""Renova os scopeDigest envelhecidos pelo nono elo, no valor impresso pela ferramenta.

Dupla leitura obrigatoria: o `check` imprime `atual <hex>` e o `digest --item`
imprime o mesmo hex por outro caminho de codigo. Só escreve quando os dois
batem, e so na arvore congelada (nada mais roda em paralelo). O log pos-renovacao
fica FORA do checkout: arquivar dentro da pasta de evidencia envelheceria o
digest que ele certifica — precedente dos elos 7 e 8 (52, 56).
"""

import json
import pathlib
import re
import subprocess
import sys

RAIZ = pathlib.Path("/home/misael/Projects/Steam Zero/Canonical/2026-09-21")
TMP = pathlib.Path("/home/misael/steamzero-retrofe-tmp")
ITENS = RAIZ / "docs/status/items"
# Sufixo de nome de log. A segunda passada — a que roda depois de toda a evidencia
# estar escrita na arvore — escreve `-final` para NAO sobrescrever os logs da primeira,
# que vao arquivados dentro da pasta de evidencia. Os da passada final ficam fora do
# checkout por definicao: guarda-los la dentro envelheceria o digest que eles certificam.
SUFIXO = sys.argv[1] if len(sys.argv) > 1 else ""
assert not SUFIXO or SUFIXO.startswith("-"), f"sufixo deve vir como `-final`: {SUFIXO!r}"
LOG_ANTES = TMP / f"105-status-check-antes-da-renovacao{SUFIXO}.log"
LOG_DEPOIS = TMP / f"105b-status-check-depois-da-renovacao{SUFIXO}.log"
OBSOLETA = re.compile(
    r"^- (SZ-[A-Z0-9-]+): evidencia obsoleta; scopeDigest esperado ([0-9a-f]{64}), "
    r"atual ([0-9a-f]{64})$"
)


def roda(argv: list[str]) -> tuple[int, str]:
    proc = subprocess.run(argv, cwd=RAIZ, capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def arvore_quieta() -> list[str]:
    """O docstring promete renovação em árvore congelada; a promessa é verificada.

    Um `ps` com a linha do próprio script não conta: o que envelhece o digest
    durante a renovação é outra suíte escrevendo no checkout em paralelo.
    """
    proc = subprocess.run(["ps", "-eo", "cmd"], capture_output=True, text=True)
    ocupados = [l for l in proc.stdout.splitlines()
                if "run_tests_isolated" in l and "grep" not in l]
    return ocupados


def main() -> int:
    ocupados = arvore_quieta()
    if ocupados:
        print("RECUSADO: ha suíte rodando nesta maquina; renova em arvore congelada")
        for linha in ocupados:
            print(f"  {linha.strip()[:120]}")
        return 1
    rc, antes = roda([".venv/bin/python", "tools/project_status.py", "check"])
    LOG_ANTES.write_text(antes, encoding="utf-8")
    obsoletas = [OBSOLETA.match(l) for l in antes.splitlines() if OBSOLETA.match(l)]
    outras = [l for l in antes.splitlines()
              if l.strip() and not OBSOLETA.match(l) and "STATUS-CHECK" not in l]
    print(f"renovacao{SUFIXO or ''}: check rc={rc}; digest envelhecidos={len(obsoletas)}; outras linhas={len(outras)}")
    if rc != 0 and not obsoletas and "evidencia obsoleta" in antes:
        # um no-op silencioso aqui jA aconteceu: o prefixo "- " da lista nao estava
        # no padrao, nada foi renovado e o script ainda assim seguiu adiante.
        print("RECUSADO: o check reclama de evidencia obsoleta mas o padrao nao casou "
              "nenhuma linha; o analisador esta cego, nao renove nothing e chame de verde.")
        return 1
    for linha in outras:
        print(f"  outra: {linha}")
    if rc == 0:
        print("nada a renovar — o catalogo ja esta batendo")
        return 0

    escritos: list[tuple[str, str]] = []
    for correspondencia in obsoletas:
        identificador, esperado, atual = correspondencia.groups()
        rc_dig, impresso = roda([".venv/bin/python", "tools/project_status.py",
                                 "digest", "--item", identificador])
        valor = impresso.strip().splitlines()[-1] if impresso.strip() else ""
        if rc_dig or valor != atual:
            print(f"  {identificador}: RECUSADO — check diz {atual[:12]}, digest diz {valor[:12]!r}")
            return 1
        arquivo = _arquivo_do_item(identificador)
        if arquivo is None:
            print(f"  {identificador}: RECUSADO — nao localizei o JSON do item")
            return 1
        _grava_digest(arquivo, identificador, esperado, atual)
        escritos.append((identificador, atual))
        print(f"  {identificador}: {esperado[:12]} -> {atual[:12]} (dupla leitura ok)")

    rc_render, saida_render = roda([".venv/bin/python", "tools/project_status.py", "render", "--write"])
    print(f"render rc={rc_render}: {saida_render.strip()[:200]}")
    rc_final, depois = roda([".venv/bin/python", "tools/project_status.py", "check"])
    LOG_DEPOIS.write_text(depois, encoding="utf-8")
    print(f"check pos-renovacao rc={rc_final}")
    if rc_final:
        print(depois[-1500:])
        return 1
    print(f"OK: {len(escritos)} digest renovados no valor impresso pela ferramenta")
    return 0


def _arquivo_do_item(identificador: str) -> pathlib.Path | None:
    for arquivo in sorted(ITENS.glob("*.json")):
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
        if dados.get("id") == identificador:
            return arquivo
    return None


def _grava_digest(arquivo: pathlib.Path, identificador: str, esperado: str, atual: str) -> None:
    """Troca um hex por outro, sem tocar no restante do arquivo.

    Escrita textual e nao por json.dumps: o cartao tem uma linha com \\uXXXX e o
    round-trip do parser a reformataria, envelhecendo o digest por um motivo que
    nao e conteudo. Exijo exatamente uma ocorrencia do valor antigo.
    """
    texto = arquivo.read_text(encoding="utf-8")
    alvo = f'"scopeDigest": "{esperado}"'
    if texto.count(alvo) != 1:
        raise SystemExit(f"{identificador}: espera {alvo!r} exatamente uma vez, "
                         f"achei {texto.count(alvo)}")
    arquivo.write_text(texto.replace(alvo, f'"scopeDigest": "{atual}"', 1), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
