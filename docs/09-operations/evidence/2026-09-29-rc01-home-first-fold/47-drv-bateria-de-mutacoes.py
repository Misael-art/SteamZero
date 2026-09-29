"""Bateria de mutações da oitava fatia (dobra da Home).

Cada mutação é aplicada por âncora exata, o gate roda contra ela, e o arquivo é
restaurado a partir da cópia salva. A restauração é verificada por SHA-256: sem
isto a bateria provaria pouco, porque uma restauração parcial deixaria o verde
seguinte medindo outra árvore.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path("<checkout-canônico>")  # caminho pessoal redigido por AGENTS.md
ERRORCARD = ROOT / "src/steamzero/ui/qml/ErrorCard.qml"
MAIN = ROOT / "src/steamzero/ui/qml/Main.qml"
BACKUP = Path.home() / "steamzero-retrofe-tmp" / "mut-backup"
GATE = "tests/integration/test_ui_shell_home_first_fold.py"
K = "primeiro_alvo or agregada or acoes or devolve or dobra_ja_fecha"

MUTACOES = [
    (
        "M1 — cardDuplicaAFaixa sempre falso (Main.qml): nenhuma compactação",
        MAIN,
        '        return code !== "" && code === statusBandFailureCode',
        "        return false",
    ),
    (
        "M2 — prosa compacta nunca volta (ErrorCard.qml): 'Ver detalhes' não reexibe",
        ERRORCARD,
        "(!card.compact || card.detailed)",
        "(!card.compact)",
    ),
    (
        "M3 — alvo do cartão a 36 px (ErrorCard.qml): contrato de alcance",
        ERRORCARD,
        "Layout.minimumHeight: 48",
        "Layout.minimumHeight: 36",
    ),
    (
        "M4 — 'Ver detalhes' some em compacto (ErrorCard.qml): corta o acesso",
        ERRORCARD,
        "            Button {\n                id: detailButton\n",
        "            Button {\n                id: detailButton\n                visible: !card.compact\n",
    ),
]


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def _rodar(comando: list[str], rotulo: str, verboso: bool = False, veredito: bool = True) -> int:
    print(f"    [{rotulo}] $ {' '.join(comando)}", flush=True)
    completed = subprocess.run(
        comando, cwd=ROOT, capture_output=True, text=True, check=False
    )
    saida = (completed.stdout or "") + (completed.stderr or "")
    for line in saida.splitlines():
        limpa = line.strip()
        if verboso or limpa.startswith(("FAILED", "assert")) or " passed" in limpa \
                or " failed" in limpa or "erro" in limpa.lower() and "error" in limpa.lower():
            print(f"      {limpa}", flush=True)
    if not veredito:
        print(f"      (passo de medição: rc={completed.returncode}, sem veredito de gate)",
              flush=True)
    elif completed.returncode == 0:
        print("      RESULTADO: VERDE sob a mutação — a asserção NÃO morde", flush=True)
    else:
        print(f"      RESULTADO: vermelho rc={completed.returncode} — mutação detectada", flush=True)
    return completed.returncode


def main() -> int:
    BACKUP.mkdir(parents=True, exist_ok=True)
    arquivos = {p: _sha(p) for p in (ERRORCARD, MAIN)}
    print("== SHA-256 da árvore antes da bateria ==")
    for p, sha in arquivos.items():
        print(f"  {sha}  {p.name}")
    for rotulo, arquivo, old, new in MUTACOES:
        print(f"\n== {rotulo} ==")
        texto = arquivo.read_text(encoding="utf-8")
        ocorrencias = texto.count(old)
        if ocorrencias == 0:
            print(f"  ANCORA AUSENTE — mutação não aplicada: {old!r}")
            return 2
        copia = BACKUP / arquivo.name
        copia.write_text(texto, encoding="utf-8")
        antes = _sha(arquivo)
        arquivo.write_text(texto.replace(old, new), encoding="utf-8")
        print(f"  aplicada em {ocorrencias} ocorrencia(s); sha {antes} -> {_sha(arquivo)}")
        _rodar(
            [str(ROOT / ".venv/bin/python"), "-m", "pytest", GATE, "-q", "-k", K],
            "gate",
        )
        if rotulo.startswith("M1"):
            _rodar(
                [str(ROOT / ".venv/bin/python"), str(Path(__file__).parent / "drv_testemunha2.py")],
                "sonda de atribuição",
                verboso=True,
                veredito=False,
            )
        arquivo.write_text(copia.read_text(encoding="utf-8"), encoding="utf-8")
        restaurado = _sha(arquivo)
        print(f"  restaurado: sha {restaurado} (esperava {antes}) "
              f"{'OK' if restaurado == antes else 'DIVERGENTE'}")
        if restaurado != antes:
            return 3
    print("\n== SHA-256 da árvore depois da bateria ==")
    divergiu = False
    for p, sha in arquivos.items():
        atual = _sha(p)
        ok = atual == sha
        divergiu = divergiu or not ok
        print(f"  {atual}  {p.name}  {'OK' if ok else 'DIVERGENTE de ' + sha}")
    return 4 if divergiu else 0


if __name__ == "__main__":
    raise SystemExit(main())
