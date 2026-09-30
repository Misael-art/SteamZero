"""Gate visual (markers -m visual) na mesma arvore congelada do checkpoint 100.

O nono elo edita Main.qml e ThemeEditorPanel.qml, duas superficies desenhadas.
O gate nao esta na lista de AGENTS 6, mas o precedente do oitavo elo (52, PASSO 7)
rodou-o localmente exatamente por isso: quem mexe em QML entregue confere as 375
capturas antes de afirmar que a superficie continua de pe. Espera o driver 100
terminar para nao disputar CPU com as portas de atraso real.
"""

import hashlib
import pathlib
import subprocess
import sys
import time

RAIZ = pathlib.Path("/home/misael/Projects/Steam Zero/Canonical/2026-09-21")
LOG = pathlib.Path("/home/misael/steamzero-retrofe-tmp/102-gate-visual-nono-elo.log")
DRIVER = pathlib.Path("/home/misael/steamzero-retrofe-tmp/100-checkpoint-integral-nono-elo.log")
ARQUIVOS = [
    "src/steamzero/ui/qml/Main.qml",
    "src/steamzero/ui/qml/ThemeEditorPanel.qml",
    "tests/integration/test_ui_shell_esde_import_late_response.py",
    "tests/qml/check_shell_esde_import_late_response.qml",
]
COMANDO = [".venv/bin/python", "tools/run_tests_isolated.py", "-m", "visual", "--tb=short", "-q"]


def escreve(linha: str) -> None:
    with LOG.open("a", encoding="utf-8") as arq:
        arq.write(linha + "\n")
        arq.flush()


def identidade(rotulo: str) -> None:
    escreve(f"--- identidade {rotulo} {time.strftime('%Y-%m-%dT%H:%M:%S%z')} ---")
    for argv, rotulo_cmd in ((["git", "rev-parse", "--abbrev-ref", "HEAD"], "branch"),
                             (["git", "rev-parse", "HEAD"], "HEAD")):
        proc = subprocess.run(argv, cwd=RAIZ, capture_output=True, text=True)
        escreve(f"{rotulo_cmd}={proc.stdout.strip()}")
    for relativo in ARQUIVOS:
        caminho = RAIZ / relativo
        digest = hashlib.sha256(caminho.read_bytes()).hexdigest()[:16]
        escreve(f"  sha256 {digest}  {relativo}")
    escreve("")


def espera_100(limite: int = 75 * 60) -> str:
    """Aguarda o checkpoint 100 encerrar; devolve o veredito dele ou o motivo da espera."""
    inicio = time.time()
    while time.time() - inicio < limite:
        texto = DRIVER.read_text(encoding="utf-8") if DRIVER.exists() else ""
        if "VEREDITO:" in texto:
            return [ln for ln in texto.splitlines() if ln.startswith("VEREDITO:")][0]
        alive = subprocess.run(["pgrep", "-f", "100-checkpoint-integral-nono-elo.py"],
                               capture_output=True, text=True).stdout.strip()
        if not alive and DRIVER.exists():
            return "driver 100 sumiu sem veredito (verificar log)"
        time.sleep(30)
    return "espera de 75 min esgotada sem veredito do 100"


def main() -> int:
    LOG.write_text("", encoding="utf-8")
    escreve("GATE VISUAL — nono elo (375 capturas offscreen), mesma arvore do checkpoint 100")
    veredito_100 = espera_100()
    escreve(f"checkpoint 100: {veredito_100}")
    if "PASSO" not in veredito_100:
        escreve("PARADA: o gate visual so roda se o checkpoint integral passou na mesma arvore.")
        return 1
    identidade("ANTES")
    inicio = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    escreve(f"INICIO {inicio}")
    escreve("$ " + " ".join(COMANDO))
    proc = subprocess.run(COMANDO, cwd=RAIZ, capture_output=True, text=True)
    escreve((proc.stdout + proc.stderr).rstrip())
    escreve(f"FIM {time.strftime('%Y-%m-%dT%H:%M:%S%z')} rc={proc.returncode}")
    identidade("DEPOIS")
    escreve(f"VEREDITO: {'PASSOU' if proc.returncode == 0 else 'VERMELHO'} rc={proc.returncode}")
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
