"""Bateria de mutações do nono elo (contrato de geração ES-DE na shell).

Molde: `bateria_mutacoes_dobra.py` (oitavo elo). Cada mutação é aplicada por
âncora exata, o gate INTEIRO roda contra ela (sem `-k`: as cinco cenas são o
contrato, e um recorte poderia provar que uma mutação só mata a cena que já se
sabia ligada a ela), e o arquivo volta pela cópia salva. A restauração é
verificada por SHA-256 por mutação e no fim da corrida: sem isto a bateria
provaria pouco, porque uma restauração parcial deixaria o verde seguinte medir
outra árvore.

As cinco mutações cobrem as cinco alavancas do contrato, cada uma uma frase:
  M1 — a callback de sucesso de `inspectEsdeImport` sem guarda: a resposta tardia
       volta a escrever por cima da superfície fechada;
  M2 — `resetEsdeImport` sem revoke: fechar o diálogo deixa de revogar o pedido;
  M3 — `inspectEsdeImport` sem rollback de recusa: o clique recusado rearma a
       bandeira que encontrou;
  M4 — rollback escrevendo `true` em vez de `ocupadoAntes`: é exatamente o pino
       da cena 06, que distingue recusa com pedido vivo de recusa com pedido
       revogado;
  M5 — a callback de sucesso de `applyEsdeImport` sem guarda: o apply tardio volta
       a anunciar sucesso e a re-listar temas depois do fechamento.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

ROOT = Path("/home/misael/Projects/Steam Zero/Canonical/2026-09-21")
PANEL = ROOT / "src/steamzero/ui/qml/ThemeEditorPanel.qml"
BACKUP = Path.home() / "steamzero-retrofe-tmp" / "mut-backup-esde"
GATE = "tests/integration/test_ui_shell_esde_import_late_response.py"

MUTACOES = [
    (
        "M1 — callback de sucesso do inspect sem guarda (resposta tardia reabre estado)",
        'panel.requestAction("theme.import.esde.inspect", {source: source},\n'
        "            function(response) {\n"
        "                if (geracao !== panel.esdeImportGeneration)\n"
        "                    return\n",
        'panel.requestAction("theme.import.esde.inspect", {source: source},\n'
        "            function(response) {\n",
    ),
    (
        "M2 — resetEsdeImport sem revoke (fechar deixa de revogar o pedido em voo)",
        "        panel.esdeImportGeneration += 1\n        panel.esdeImportSource = \"\"",
        "        panel.esdeImportSource = \"\"",
    ),
    (
        "M3 — inspectEsdeImport sem rollback da recusa (clique recusado rearma a bandeira)",
        "        if (!despachado) {\n"
        "            panel.esdeImportGeneration = geracao - 1\n"
        "            panel.esdeImportBusy = ocupadoAntes\n"
        "        }\n"
        "    }\n"
        "\n"
        "    function applyEsdeImport()",
        "    }\n"
        "\n"
        "    function applyEsdeImport()",
    ),
    (
        "M4 — rollback escrevendo true em vez de ocupadoAntes (pino da cena 06)",
        "            panel.esdeImportBusy = ocupadoAntes\n"
        "        }\n"
        "    }\n"
        "\n"
        "    function applyEsdeImport()",
        "            panel.esdeImportBusy = true\n"
        "        }\n"
        "    }\n"
        "\n"
        "    function applyEsdeImport()",
    ),
    (
        "M5 — callback de sucesso do apply sem guarda (apply tardio anuncia e re-lista)",
        "        }, function(response) {\n"
        "            if (geracao !== panel.esdeImportGeneration)\n"
        "                return\n"
        "            panel.esdeImportBusy = false\n"
        "            panel.refreshThemeList()\n",
        "        }, function(response) {\n"
        "            panel.esdeImportBusy = false\n"
        "            panel.refreshThemeList()\n",
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
    original = _sha(PANEL)
    print("== SHA-256 da árvore antes da bateria ==")
    print(f"  {original}  {PANEL.name}")
    rc_verdes = 0
    for rotulo, old, new in MUTACOES:
        print(f"\n== {rotulo} ==")
        texto = PANEL.read_text(encoding="utf-8")
        ocorrencias = texto.count(old)
        if ocorrencias != 1:
            print(f"  ANCORA AMBIGUA/AUSENTE ({ocorrencias} ocorrencia(s)) — mutação não aplicada")
            return 2
        copia = BACKUP / PANEL.name
        copia.write_text(texto, encoding="utf-8")
        antes = _sha(PANEL)
        PANEL.write_text(texto.replace(old, new), encoding="utf-8")
        print(f"  aplicada em {ocorrencias} ocorrencia; sha {antes} -> {_sha(PANEL)}")
        rc = _rodar("gate")
        rc_verdes += 1 if rc == 0 else 0
        PANEL.write_text(copia.read_text(encoding="utf-8"), encoding="utf-8")
        restaurado = _sha(PANEL)
        print(f"  restaurado: sha {restaurado} (esperava {antes}) "
              f"{'OK' if restaurado == antes else 'DIVERGENTE'}")
        if restaurado != antes:
            return 3
    atual = _sha(PANEL)
    print("\n== SHA-256 da árvore depois da bateria ==")
    print(f"  {atual}  {PANEL.name}  {'OK' if atual == original else 'DIVERGENTE de ' + original}")
    print(f"\n== veredito == {len(MUTACOES) - rc_verdes}/{len(MUTACOES)} mutações detectadas "
          f"pelo gate; {rc_verdes} sobreviveram")
    return 0 if atual == original else 4


if __name__ == "__main__":
    raise SystemExit(main())
