"""Sonda: testemunhas das cenas de atenção, nas três etapas do harness.

Usada pela bateria de mutações para atribuir píxeis por arquivo: a mesma testemunha
diz o que a reorganização do cartão compra e o que a compactação compra.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path("<checkout-canônico>")  # caminho pessoal redigido por AGENTS.md
sys.path.insert(0, str(ROOT / "tests" / "integration"))

import test_ui_shell_home_first_fold as gate  # noqa: E402

CHAVES = (
    "escala",
    "band",
    "banner",
    "cartoes",
    "scroll_h",
    "primeiro",
    "primeiro_y",
    "primeiro_h",
    "pend_y",
    "cartao_h",
    "cartao_alvo_h",
    "cartao_compacto",
    "gatilho",
    "prosa_itens",
    "prosa_na_tela",
    "prosa_caracteres",
    "cartao_expandido_h",
    "prosa_na_tela_expandida",
    "prosa_caracteres_na_tela_expandida",
    "cartao_referencia_h",
    "prosa_na_tela_ref",
    "prosa_caracteres_na_tela_ref",
)

CENAS = sys.argv[1:] or ("atencao-maxima", "atencao-maxima-150", "leitura-sem-dados")

for cena in CENAS:
    testemunha, completed = gate._rodar(cena)
    print(f"### {cena} rc={completed.returncode}")
    if testemunha is None:
        print("SEM TESTEMUNHA")
        print(completed.stderr[-1500:])
        continue
    valores = {chave: testemunha.get(chave) for chave in CHAVES}
    print("  " + " ".join(f"{chave}={valor}" for chave, valor in valores.items()))
    compacto = int(float(valores["cartao_h"] or -1))
    expandida = int(float(valores["cartao_expandido_h"] or -1))
    referencia = int(float(valores["cartao_referencia_h"] or -1))
    fundo = int(float(valores["primeiro_y"] or 0)) + int(float(valores["primeiro_h"] or 0))
    banda = int(float(valores["scroll_h"] or 0))
    print(
        f"  ganho={expandida - compacto}px compacto={compacto} expandido={expandida} "
        f"referencia={referencia} dobra_fundo={fundo} banda_visivel={banda} "
        f"cabe={'SIM' if fundo <= banda else 'NAO'}"
    )
    for line in completed.stderr.splitlines():
        if "PROSA|" in line and "estagio=compacto" in line:
            print("   ", line)
