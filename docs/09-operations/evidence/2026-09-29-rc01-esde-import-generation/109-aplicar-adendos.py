"""Aplica os adendos gerados pelo `103` na árvore, trocando apenas o corpo desta sessão.

Os dois alvos têm situações diferentes e o script trata cada um pelo que ele é:

* `docs/09-operations/evidence/…/README.md` é deste lote e está fora do controle de
  versão: o adendo que ele carrega foi gerado por este mesmo `103`, então trocar o
  corpo é regeneração, não reescrita de histórico.
* `docs/WORKLOG.md` é rastreado e append-only: o prefixo tem de continuar sendo, byte
  a byte, o `docs/WORKLOG.md` da cabeça + a entrada do nono elo que esta sessão já
  escreveu. A troca acontece SÓ dentro do bloco de adendo desta sessão, localizado por
  marcador único — se o marcador aparecer duas vezes, nada é escrito.

O corpo substituído vai para o tmp com sufixo `.rodada-anterior` antes de qualquer
escrita: a rodada anterior fica recuperável, e o diff das duas versões é impresso.
"""

from __future__ import annotations

import difflib
import hashlib
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path("/home/misael/Projects/Steam Zero/Canonical/2026-09-21")
TMP = pathlib.Path("/home/misael/steamzero-retrofe-tmp")
EVIDENCIA = RAIZ / "docs/09-operations/evidence/2026-09-29-rc01-esde-import-generation"

ALVOS = [
    {
        "nome": "README da pasta de evidência",
        "arquivo": EVIDENCIA / "README.md",
        "corpo": TMP / "103-adendo-readme.md",
        "guardado": TMP / "103-adendo-readme.rodada-anterior.md",
        "marcador": "\n## Adendo — checkpoint integral",
    },
    {
        "nome": "WORKLOG",
        "arquivo": RAIZ / "docs/WORKLOG.md",
        "corpo": TMP / "103-adendo-worklog.md",
        "guardado": TMP / "103-adendo-worklog.rodada-anterior.md",
        "marcador": "\n## 2026-09-29 — RC-01 / nono elo, adendo:",
    },
]

PROBLEMAS: list[str] = []


def sha(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16]


def aplica(alvo: dict) -> tuple[str, int, int]:
    texto = alvo["arquivo"].read_text(encoding="utf-8")
    novo = alvo["corpo"].read_text(encoding="utf-8")
    if not novo.strip():
        PROBLEMAS.append(f"{alvo['nome']}: corpo gerado vazio — nada escrito")
        return (alvo["nome"], 0, 0)
    if texto.count(alvo["marcador"]) != 1:
        PROBLEMAS.append(f"{alvo['nome']}: marcador do adendo desta sessão aparece "
                         f"{texto.count(alvo['marcador'])}x — não é para adivinhar o corte")
        return (alvo["nome"], 0, 0)
    inicio = texto.index(alvo["marcador"])
    prefixo, antigo = texto[:inicio], texto[inicio:]
    if not novo.startswith(alvo["marcador"]):
        # O corpo gerado tem de COMEÇAR no marcador; se começar antes dele, a troca
        # jogaria texto duplicado no arquivo.
        PROBLEMAS.append(f"{alvo['nome']}: o corpo gerado não começa no marcador desta sessão "
                         "— o corte não foi feito onde o texto começa")
        return (alvo["nome"], 0, 0)
    alvo["guardado"].write_text(antigo, encoding="utf-8")
    diff = sum(1 for l in difflib.unified_diff(antigo.splitlines(), novo.splitlines(),
                                               lineterm="", n=0)
               if l[:1] in "+-" and l[1:2] not in "+-")
    alvo["arquivo"].write_text(prefixo + novo, encoding="utf-8")
    relido = alvo["arquivo"].read_text(encoding="utf-8")
    if not relido.startswith(prefixo) or not relido.endswith(novo):
        PROBLEMAS.append(f"{alvo['nome']}: escrita divergente do pretendido após o rename")
    return (alvo["nome"], diff, len(novo) - len(antigo))


def main() -> int:
    worklog = next(a for a in ALVOS if a["nome"] == "WORKLOG")
    head = subprocess.run(["git", "show", "HEAD:docs/WORKLOG.md"], cwd=RAIZ,
                          capture_output=True, text=True).stdout
    if head and not worklog["arquivo"].read_text(encoding="utf-8").startswith(head):
        PROBLEMAS.append("WORKLOG: o prefixo da árvore não começa com o WORKLOG da cabeça — "
                         "isto é reescrita de histórico, e append-only não é adjective")

    for alvo in ALVOS:
        nome, dif, delta = aplica(alvo)
        print(f"{nome}: {dif} linha(s) de diff no corpo, delta {delta:+d} bytes, "
              f"sha256 agora {sha(alvo['arquivo'].read_text(encoding='utf-8'))}")

    if PROBLEMAS:
        print("PROBLEMAS — nada mais foi escrito:")
        for problema in PROBLEMAS:
            print(f"  - {problema}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
