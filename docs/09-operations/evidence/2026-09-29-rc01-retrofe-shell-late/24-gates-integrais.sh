#!/usr/bin/env bash
# Envoltório do checkpoint do corte "RetroFE na shell" (cortes 63-65): os cinco gates
# rápidos de AGENTS §6 primeiro (a lição do lote UX-04: lint de arquivo novo roda ANTES
# do checkpoint integral, não depois), e as duas suítes por último, uma por vez, sem
# mutar a árvore durante a execução. A identidade da árvore é impressa antes e depois de
# CADA passo.
#
# Chamado com um argumento: caminho do log. Neste lote o log cru é escrito FORA do
# checkout e só copiado para a pasta de evidência no fechamento: a pasta está em
# `scopePaths` de SZ-UI-DESKTOP-AUDIT, então escrever o log durante a execução
# envelheceria o digest renovado na véspera do checkpoint e o passo 1 reprovaria por
# culpa do próprio invólucro, não da árvore testada.
#
# Cópias pessoais deste arquivo vivem fora do checkout, com os caminhos reais
# substituídos; esta versão comitada tem os prefixos redigidos por AGENTS.md ("não
# redistribuir caminhos pessoais em logs públicos"). Nenhuma linha de resultado muda.
set -u
CHECKOUT="<checkout-canônico>"
LOG="${1:?uso: 24-gates-integrais.sh <caminho-do-log>}"
EVIDENCIA="docs/09-operations/evidence/2026-09-29-rc01-retrofe-shell-late"
cd "$CHECKOUT" || exit 99

identidade() {
    {
        echo "--- identidade $(date -Is) ---"
        echo "branch=$(git rev-parse --abbrev-ref HEAD)"
        echo "HEAD=$(git rev-parse HEAD)"
        echo "git status --short (esta pasta de evidência excluída: o log cresce durante a execução):"
        git status --short -- . ":!$EVIDENCIA"
        echo "sha256 src+tests+tools=$(git ls-files -s src tests tools | sha256sum | cut -c1-16)"
        echo "sha256 produto=sha256sum src/steamzero/ui/qml/ThemeEditorPanel.qml -> $(sha256sum src/steamzero/ui/qml/ThemeEditorPanel.qml | cut -c1-16)"
        echo "sha256 harness=sha256sum tests/qml/check_shell_retrofe_import_late_response.qml -> $(sha256sum tests/qml/check_shell_retrofe_import_late_response.qml | cut -c1-16)"
        echo "sha256 gate=sha256sum tests/integration/test_ui_shell_retrofe_import_late_response.py -> $(sha256sum tests/integration/test_ui_shell_retrofe_import_late_response.py | cut -c1-16)"
    } >>"$LOG" 2>&1
}

passo() {
    local n="$1" cmd="$2" tmo="$3"
    {
        echo
        echo "===== PASSO $n :: $cmd"
        echo "INICIO $(date -Is)"
    } >>"$LOG"
    identidade
    timeout "$tmo" bash -c "$cmd" >>"$LOG" 2>&1
    local rc=$?
    {
        echo "FIM $(date -Is) rc=$rc"
    } >>"$LOG"
    identidade
    echo "$n rc=$rc :: $cmd" >>"$LOG".rc
    return 0
}

: >"$LOG"
: >"$LOG".rc
{
    echo "CHECKPOINT — RetroFE na shell: gates rápidos + suíte integral única + gate visual na árvore congelada"
    echo "COMANDO-MAE: bash $0 $LOG"
    echo "INICIO $(date -Is)"
    echo "cwd=$CHECKOUT"
    echo "python=$(.venv/bin/python -V 2>&1)"
} >>"$LOG"

passo 1 ".venv/bin/ruff format --check src tests tools" 600
passo 2 ".venv/bin/ruff check src tests tools" 600
passo 3 ".venv/bin/mypy src" 1200
passo 4 "make independence boundaries" 600
passo 5 "make status-check" 600
passo 6 ".venv/bin/python tools/run_tests_isolated.py tests -q" 5400
passo 7 ".venv/bin/python tools/run_tests_isolated.py -m visual --tb=short -q" 3600

{
    echo
    echo "===== ROLLUP"
    cat "$LOG".rc
    echo "FIM TOTAL $(date -Is)"
} >>"$LOG"
touch "$LOG".concluido
