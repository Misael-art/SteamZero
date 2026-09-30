"""Bateria de mutações do nono elo — metade RAIZ (o diálogo de `Main.qml`).

Molde: `70-bateria-mutacoes-esde-geracao.py`, que atacou o painel. Aqui as cinco
alavancas são as mesmas cinco, instaladas na outra superfície de importação ES-DE
do produto: o diálogo raiz aberto pelo botão real da seção Sistema. Cada mutação é
aplicada por âncora exata, o gate INTEIRO roda contra ela (sem `-k`: as dez cenas
são o contrato, e um recorte poderia provar que uma mutação só mata a cena que já
se sabia ligada a ela), e o arquivo volta pela cópia salva. A restauração é
verificada por SHA-256 por mutação e no fim da corrida.

  M6 — callback de sucesso do examine raiz sem guarda: a resposta tardia reabre
       esquemas, seleção e aviso num diálogo fechado (cena 08);
  M7 — `onClosed` da raiz sem revoke: fechar deixa de revogar, então a guarda do
       callback nada tem com que contrastar e a cena 08 volta a ver o estado;
  M8 — examine raiz sem rollback da recusa: o clique recusado deixa a bandeira
       armada e o diálogo reaberto congela (cena 10);
  M9 — rollback do apply raiz escrevendo `true` em vez de `ocupadoAntes`: é o pino
       que distingue "pedido ainda vivo" de "pedido revogado pelo fechamento";
  M10 — callback de sucesso do apply raiz sem guarda: o apply tardio volta a
       anunciar sucesso numa superfície fechada (cena 09, testemunho `toast`).
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

ROOT = Path("/home/misael/Projects/Steam Zero/Canonical/2026-09-21")
ALVO = ROOT / "src/steamzero/ui/qml/Main.qml"
BACKUP = Path.home() / "steamzero-retrofe-tmp" / "mut-backup-esde-raiz"
GATE = "tests/integration/test_ui_shell_esde_import_late_response.py"

MUTACOES = [
    (
        "M6 — examine raiz sem guarda no sucesso (resposta tardia reabre o diálogo)",
        "                            function(response) {\n"
        "                                if (geracao !== root.esdeImportGeneration)\n"
        "                                    return\n"
        "                                root.esdeImportBusy = false\n"
        "                                const found = response && response.schemes\n",
        "                            function(response) {\n"
        "                                root.esdeImportBusy = false\n"
        "                                const found = response && response.schemes\n",
    ),
    (
        "M7 — onClosed da raiz sem revoke (fechar deixa de revogar o pedido)",
        "            root.esdeImportGeneration += 1\n"
        "            // Fechar por Escape, por Cancelar ou pelo botão B tem de deixar o\n",
        "            // Fechar por Escape, por Cancelar ou pelo botão B tem de deixar o\n",
    ),
    (
        "M8 — examine raiz sem rollback da recusa (clique recusado rearma a bandeira)",
        "                        if (!despachado) {\n"
        "                            root.esdeImportGeneration = geracao - 1\n"
        "                            root.esdeImportBusy = ocupadoAntes\n"
        "                        }\n",
        "",
    ),
    (
        "M9 — rollback do apply raiz escrevendo true em vez de ocupadoAntes",
        "                    if (!despachado) {\n"
        "                        root.esdeImportGeneration = geracao - 1\n"
        "                        root.esdeImportBusy = ocupadoAntes\n"
        "                    }\n",
        "                    if (!despachado) {\n"
        "                        root.esdeImportGeneration = geracao - 1\n"
        "                        root.esdeImportBusy = true\n"
        "                    }\n",
    ),
    (
        "M10 — apply raiz sem guarda no sucesso (anuncia sucesso em superfície fechada)",
        "                        function(response) {\n"
        "                            if (geracao !== root.esdeImportGeneration)\n"
        "                                return\n"
        "                            root.esdeImportBusy = false\n"
        '                            root.notify(qsTr("Tema ES-DE importado."), false)\n',
        "                        function(response) {\n"
        "                            root.esdeImportBusy = false\n"
        '                            root.notify(qsTr("Tema ES-DE importado."), false)\n',
    ),
]


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def _rodar(rotulo: str) -> int:
    comando = [str(ROOT / ".venv/bin/python"), "-m", "pytest", GATE, "-q"]
    print(f"    [{rotulo}] $ cd {ROOT} && {' '.join(comando)}", flush=True)
    completed = subprocess.run(comando, cwd=ROOT, capture_output=True, text=True, check=False)
    saida = (completed.stdout or "") + (completed.stderr or "")
    for line in saida.splitlines():
        limpa = line.strip()
        if limpa.startswith(("FAILED", "E ", "assert")) or " passed" in limpa or " failed" in limpa:
            print(f"      {limpa}", flush=True)
    if completed.returncode == 0:
        print("      RESULTADO: VERDE sob a mutação — a asserção NÃO morde", flush=True)
    else:
        print(f"      RESULTADO: vermelho rc={completed.returncode} — mutação detectada", flush=True)
    return completed.returncode


def main() -> int:
    BACKUP.mkdir(parents=True, exist_ok=True)
    original = _sha(ALVO)
    print("== SHA-256 da árvore antes da bateria (raiz) ==")
    print(f"  {original}  {ALVO.name}")
    rc_verdes = 0
    for rotulo, old, new in MUTACOES:
        print(f"\n== {rotulo} ==")
        texto = ALVO.read_text(encoding="utf-8")
        ocorrencias = texto.count(old)
        if ocorrencias != 1:
            print(f"  ANCORA AMBIGUA/AUSENTE ({ocorrencias} ocorrencia(s)) — mutação não aplicada")
            return 2
        copia = BACKUP / ALVO.name
        copia.write_text(texto, encoding="utf-8")
        antes = _sha(ALVO)
        ALVO.write_text(texto.replace(old, new), encoding="utf-8")
        print(f"  aplicada em {ocorrencias} ocorrencia; sha {antes} -> {_sha(ALVO)}")
        rc = _rodar("gate")
        rc_verdes += 1 if rc == 0 else 0
        ALVO.write_text(copia.read_text(encoding="utf-8"), encoding="utf-8")
        restaurado = _sha(ALVO)
        print(f"  restaurado: sha {restaurado} (esperava {antes}) "
              f"{'OK' if restaurado == antes else 'DIVERGENTE'}")
        if restaurado != antes:
            return 3
    atual = _sha(ALVO)
    print("\n== SHA-256 da árvore depois da bateria (raiz) ==")
    print(f"  {atual}  {ALVO.name}  {'OK' if atual == original else 'DIVERGENTE de ' + original}")
    print(f"\n== veredito == {len(MUTACOES) - rc_verdes}/{len(MUTACOES)} mutações detectadas "
          f"pelo gate; {rc_verdes} sobreviveram")
    return 0 if atual == original else 4


if __name__ == "__main__":
    raise SystemExit(main())
