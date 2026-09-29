#!/usr/bin/env bash
# Envoltório do checkpoint UX-04: uma suíte integral + os cinco gates AGENTS §6,
# com identidade da árvore impressa antes e depois de CADA passo.
# Chamado com um argumento: caminho do log (dentro da pasta de evidência do lote).
set -u
CHECKOUT="<checkout-canônico>"
LOG="${1:?uso: gates_ux04.sh <caminho-do-log>}"
cd "$CHECKOUT" || exit 99

identidade() {
    {
        echo "--- identidade $(date -Is) ---"
        echo "branch=$(git rev-parse --abbrev-ref HEAD)"
        echo "HEAD=$(git rev-parse HEAD)"
        echo "git status --short:"
        git status --short -- . ':!docs/09-operations/evidence/2026-09-28-rc01-storage-units'
        echo "sha256 src+tests+tools=$(git ls-files -s src tests tools | sha256sum | cut -c1-16)"
        echo "sha256 harness=sha256sum tests/qml/check_storage_units.qml -> $(sha256sum tests/qml/check_storage_units.qml | cut -c1-16)"
        echo "sha256 matriz=sha256sum tests/integration/test_storage_units_locale_matrix.py -> $(sha256sum tests/integration/test_storage_units_locale_matrix.py | cut -c1-16)"
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
    echo "CHECKPOINT UX-04 — suite integral unica + cinco gates AGENTS §6 na arvore congelada"
    echo "COMANDO-MAE: bash $0 $LOG"
    echo "INICIO $(date -Is)"
    echo "cwd=$CHECKOUT"
    echo "python=$(.venv/bin/python -V 2>&1)"
} >>"$LOG"

passo 1 ".venv/bin/python tools/run_tests_isolated.py tests -q" 5400
passo 2 ".venv/bin/python tools/run_tests_isolated.py -m visual --tb=short -q" 3600
passo 3 ".venv/bin/ruff check src tools tests" 600
passo 4 ".venv/bin/ruff format --check src tools tests" 600
passo 5 ".venv/bin/mypy src" 1200
passo 6 "make independence boundaries" 600
passo 7 "make status-check" 600

{
    echo
    echo "===== ROLLUP"
    cat "$LOG".rc
    echo "FIM TOTAL $(date -Is)"
} >>"$LOG"
touch "$LOG".concluido
