"""Gate visual (-m visual) na arvore do nono elo, DEPOIS da correcao de governanca.

Por que existe: o checkpoint 100 fechou VERMELHO por um unico motivo — 11
scopeDigest envelhecidos mais tres visoes geradas, todos atribuiveis a arquivos
que este proprio elo tocou. AGENTS 6 da o remedio proporcional para esse caso
("se so uma visao ou digest gerado ficou obsoleto, regenere-o e rode apenas a
validacao de status aplicavel"), e ele foi aplicado pelo 105. O 102 se recusou a
rodar com o checkpoint vermelho, e essa recusa esta certa: nao se certifica
superficie sobre checkpoint aberto.

Este driver nao relaxa a guarda do 102; ele a substitui por uma mais forte, lida
da arvore e do log, nao da memoria:
  1. nenhuma outra suite rodando (a arvore precisa estar quieta);
  2. o unico FAILED do 100 e o gate de governanca, e so ele;
  3. `make status-check` rc=0 agora (gate de AGENTS 6 que o 100 omite);
  4. o teste que caiu passa agora;
  5. os nove arquivos funcionais hash por hash sao os mesmos que o 100 testou —
     e isso, e nao uma afirmativa, que liga esta corrida ao verde de 6 528 testes.
"""

from __future__ import annotations

import hashlib
import pathlib
import re
import subprocess
import sys
import time

RAIZ = pathlib.Path("/home/misael/Projects/Steam Zero/Canonical/2026-09-21")
TMP = pathlib.Path("/home/misael/steamzero-retrofe-tmp")
LOG = TMP / "110-gate-visual-apos-governanca.log"
LOG_100 = TMP / "100-checkpoint-integral-nono-elo.log"
LOG_105 = TMP / "105-renovar-digests.log"

FUNCIONAIS = [
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
COMANDO = [".venv/bin/python", "tools/run_tests_isolated.py", "-m", "visual",
           "--tb=short", "-q"]
GUARDA_ESPERADA = "test_committed_catalog_and_generated_views_are_consistent"


def escreve(linha: str = "") -> None:
    with LOG.open("a", encoding="utf-8") as arq:
        arq.write(linha + "\n")
        arq.flush()


def roda(argv: list[str]) -> tuple[int, str]:
    proc = subprocess.run(argv, cwd=RAIZ, capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def identidade(rotulo: str) -> dict[str, str]:
    escreve(f"### IDENTIDADE {rotulo} {time.strftime('%Y-%m-%dT%H:%M:%S%z')}")
    _, branch = roda(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    _, cabeca = roda(["git", "rev-parse", "HEAD"])
    escreve(f"branch={branch.strip()} HEAD={cabeca.strip()}")
    hashes: dict[str, str] = {}
    for relativo in FUNCIONAIS:
        dados = (RAIZ / relativo).read_bytes()
        h = hashlib.sha256(dados).hexdigest()
        hashes[relativo] = h
        escreve(f"  sha256 {h}  {relativo}  ({len(dados)} bytes)")
    escreve("")
    return hashes


def hashes_do_100() -> dict[str, str]:
    texto = LOG_100.read_text(encoding="utf-8")
    achados: dict[str, str] = {}
    for h, p in re.findall(r"sha256 ([0-9a-f]{64})  (\S+)  \(\d+ bytes\)", texto):
        if p in FUNCIONAIS:
            achados.setdefault(p, set()).add(h)
    # o 100 grava ANTES e DEPOIS; se divergissem, o checkpoint nao seria de uma arvore so
    return {p: next(iter(v)) for p, v in achados.items() if len(v) == 1}


def main() -> int:
    LOG.write_text("", encoding="utf-8")
    escreve("GATE VISUAL — nono elo, apos a renovacao de governanca (105)")
    escreve("")
    bloqueios: list[str] = []

    ocupados = [l.strip() for l in roda(["ps", "-eo", "cmd"])[1].splitlines()
                if "run_tests_isolated" in l and "grep" not in l]
    escreve(f"1) suites em execucao: {len(ocupados)} "
            f"{'— ok, arvore quieta' if not ocupados else ocupados}")
    if ocupados:
        bloqueios.append("ha outra suite rodando; a arvore nao esta quieta")

    texto_100 = LOG_100.read_text(encoding="utf-8")
    falhas = re.findall(r"^FAILED (\S+)", texto_100, re.M)
    resumo = re.search(r"^(\d+) failed, (\d+) passed, (\d+) skipped in .*$",
                       texto_100, re.M)
    escreve(f"2) 100: veredito={[l for l in texto_100.splitlines() if l.startswith('VEREDITO:')]}")
    escreve(f"   resumo bruto: {resumo.group(0) if resumo else '(nao li)'}")
    escreve(f"   FAILED ({len(falhas)}): {falhas}")
    if len(falhas) != 1 or GUARDA_ESPERADA not in falhas[0]:
        bloqueios.append("o vermelho do 100 nao e apenas o gate de governanca")
    if not resumo or int(resumo.group(2)) < 6000:
        bloqueios.append("nao consegui ler a contagem de verdes do 100")

    rc, antes_check = roda(["make", "status-check"])
    escreve(f"3) `make status-check` rc={rc}: "
            f"{[l for l in antes_check.splitlines() if 'STATUS-CHECK' in l]}")
    if rc != 0:
        bloqueios.append("status-check segue vermelho")
    escreve("   (este gate integra a lista de AGENTS 6 e o driver 100 nao o incluiu; "
            "roda aqui, e o limite fica declarado no lote)")

    rc, teste = roda([".venv/bin/python", "-m", "pytest",
                      "tests/unit/test_project_status.py", "-q"])
    escreve(f"4) teste que caiu no 100, agora: rc={rc} "
            f"{[l for l in teste.splitlines() if 'passed' in l or 'failed' in l][-1:]}")
    if rc != 0:
        bloqueios.append("o teste de governanca continua vermelho")

    do_100 = hashes_do_100()
    escreve(f"5) arquivos funcionais medidos no 100: {len(do_100)} de {len(FUNCIONAIS)} "
            f"(com ANTES==DEPOIS iguais)")
    if len(do_100) != len(FUNCIONAIS):
        bloqueios.append("o 100 nao gravou par identico para todos os funcionais")

    if bloqueios:
        escreve("")
        escreve("PARADA — premissas nao atendidas:")
        for b in bloqueios:
            escreve(f"  - {b}")
        escreve("VEREDITO: BLOQUEADO")
        return 1

    hashes = identidade("ANTES")
    divergentes = [p for p in FUNCIONAIS if hashes.get(p) != do_100.get(p)]
    if divergentes:
        escreve("PARADA: arvore funcional mudou desde o checkpoint 100: "
                f"{divergentes}")
        escreve("VEREDITO: BLOQUEADO")
        return 1
    escreve("   os nove hashes coincidem com os do checkpoint 100 — a superficie "
            "testada aqui e a mesma dos 6 528 testes verdes.\n")

    texto_105 = LOG_105.read_text(encoding="utf-8") if LOG_105.exists() else ""
    renovados = re.findall(r"^  (SZ-[A-Z0-9-]+): ([0-9a-f]{12}) -> ([0-9a-f]{12}) "
                           r"\(dupla leitura ok\)$", texto_105, re.M)
    escreve(f"6) renovacao aplicada (105): {len(renovados)} digest, "
            f"dupla leitura em todos; check pos-renovacao "
            f"{'rc=0' if 'check pos-renovacao rc=0' in texto_105 else 'NAO LIDO'}")
    escreve("")

    inicio = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    escreve(f"INICIO {inicio}")
    escreve("$ " + " ".join(COMANDO))
    proc = subprocess.run(COMANDO, cwd=RAIZ, capture_output=True, text=True)
    escreve((proc.stdout + proc.stderr).rstrip())
    escreve(f"FIM {time.strftime('%Y-%m-%dT%H:%M:%S%z')} rc={proc.returncode}")
    depois = identidade("DEPOIS")
    moveram = [p for p in FUNCIONAIS if depois.get(p) != hashes.get(p)]
    escreve(f"arquivos funcionais que se moveram durante a corrida: {moveram or 'nenhum'}")
    ok = proc.returncode == 0 and not moveram
    escreve(f"VEREDITO: {'PASSOU' if ok else 'VERMELHO'} rc={proc.returncode}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
