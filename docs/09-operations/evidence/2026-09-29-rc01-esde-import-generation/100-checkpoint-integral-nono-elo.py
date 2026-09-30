"""Checkpoint integral unico do nono elo (AGENTS.md 6), com a arvore congelada.

Ordem deliberada: identidade da arvore antes e depois, gates leves primeiro e a
suite integral por ultimo, sozinha, sem nada mais concorrendo por CPU (as portas
QML de resposta tardia medem atraso real e um concorrente poderia mascarar um
vermelho). Saida completa preservada: este log e a evidencia, nao um resumo.
"""

import hashlib
import pathlib
import subprocess
import sys
import time

RAIZ = pathlib.Path("/home/misael/Projects/Steam Zero/Canonical/2026-09-21")
LOG = pathlib.Path("/home/misael/steamzero-retrofe-tmp/100-checkpoint-integral-nono-elo.log")
ARQUIVOS = [
    "src/steamzero/ui/qml/Main.qml",
    "src/steamzero/ui/qml/ThemeEditorPanel.qml",
    "tests/integration/test_ui_shell_esde_import_late_response.py",
    "tests/qml/check_shell_esde_import_late_response.qml",
    "tests/integration/test_ui_shell_esde_import_dialog.py",
    "tests/qml/check_shell_esde_import_dialog_journey.qml",
    "tests/integration/test_ui_shell_home_first_fold.py",
    "tests/integration/test_ui_shell_retrofe_import_late_response.py",
    "tests/qml/check_shell_retrofe_import_late_response.qml",
]
PASSOS = [
    ("ruff check", [".venv/bin/ruff", "check", "src", "tools", "tests"]),
    ("ruff format --check", [".venv/bin/ruff", "format", "--check", "src", "tools", "tests"]),
    ("mypy src", [".venv/bin/mypy"]),
    ("independence", ["make", "independence", "boundaries"]),
    ("suite integral", [".venv/bin/python", "tools/run_tests_isolated.py", "tests", "-q"]),
]


def identidade(rotulo: str) -> None:
    escreve(f"### IDENTIDADE {rotulo} — {time.strftime('%Y-%m-%dT%H:%M:%S%z')}")
    escreve("$ git rev-parse --abbrev-ref HEAD")
    escreve(comando(["git", "rev-parse", "--abbrev-ref", "HEAD"]))
    escreve("$ git rev-parse HEAD")
    escreve(comando(["git", "rev-parse", "HEAD"]))
    escreve("$ git status --porcelain=v1 (contagem e lista completa)")
    status = comando(["git", "status", "--porcelain=v1"])
    escreve(status)
    escreve(f"  entradas: {len([l for l in status.splitlines() if l.strip()])}")
    for relativo in ARQUIVOS:
        caminho = RAIZ / relativo
        if caminho.exists():
            digest = hashlib.sha256(caminho.read_bytes()).hexdigest()
            escreve(f"  sha256 {digest}  {relativo}  ({caminho.stat().st_size} bytes)")
        else:
            escreve(f"  AUSENTE {relativo}")
    escreve("")


def comando(argv: list[str]) -> str:
    proc = subprocess.run(argv, cwd=RAIZ, capture_output=True, text=True)
    saida = proc.stdout + proc.stderr
    return f"{saida.rstrip()}\n[rc={proc.returncode}]"


def escreve(linha: str) -> None:
    with LOG.open("a", encoding="utf-8") as arq:
        arq.write(linha + "\n")


def main() -> int:
    LOG.write_text("", encoding="utf-8")
    escreve("CHECKPOINT INTEGRAL — nono elo (contrato de geracao do importador ES-DE na shell)")
    escreve("Comando base: AGENTS.md 6, execucao unica nesta arvore antes do commit de fechamento.")
    escreve("")
    identidade("ANTES")
    rc_geral = 0
    for rotulo, argv in PASSOS:
        escreve(f"### {rotulo}")
        escreve("$ " + " ".join(argv))
        saida = comando(argv)
        escreve(saida)
        escreve("")
        if "[rc=0]" not in saida.rpartition("\n")[-1]:
            rc_geral = 1
            # Mensagem especifica ao passo: um template unico já mentiu uma vez, quando a
            # propria suite reprovou e a linha alegou culpa de um gate leve.
            motivo = ("a suite integral nao roda em arvore que ja reprovou um gate leve"
                      if rotulo != "suite integral" else
                      "os gates posteriores a suíte estao suspensos nesta arvore; o veredito "
                      "e a contagem de FAILED acima")
            escreve(f"### PARADA: {rotulo} nao voltou rc=0; {motivo}.")
            break
        time.sleep(2)
    identidade("DEPOIS")
    escreve(f"VEREDITO: {'PASSO' if rc_geral == 0 else 'VERMELHO'}")
    return rc_geral


if __name__ == "__main__":
    sys.exit(main())
