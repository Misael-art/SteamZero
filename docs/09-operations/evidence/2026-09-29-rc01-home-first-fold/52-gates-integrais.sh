#!/usr/bin/env bash
# Envoltório do checkpoint do corte "primeira dobra da Home" (oitavo elo): os cinco
# gates rápidos de AGENTS §6 primeiro e as duas suítes por último, uma por vez, sem
# mutar a árvore durante a execução. A identidade da árvore é impressa antes e depois
# de CADA passo.
#
# Chamado com um argumento: caminho do log. O log cru é escrito FORA do checkout e só
# copiado para a pasta de evidência no fechamento: a pasta está em `scopePaths` de
# SZ-UI-DESKTOP-AUDIT, então escrever o log durante a execução envelheceria o digest
# renovado na véspera do checkpoint e o `make status-check` do passo 5 reprovaria por
# culpa do próprio invólucro, não da árvore testada.
#
# Identidade por conteúdo, não por agregado: a lição do sétimo elo
# (31-identidade-da-arvore.md) é que `git ls-files -s` lê o ÍNDICE. Aqui a árvore está
# congelada e o status está vazio sob src/tests/tools, então índice, HEAD e árvore de
# trabalho coincidem; ainda assim as quatro leituras por arquivo são a prova primária,
# e a linha agregada entra rotulada como leitura de índice.
set -u
CHECKOUT="<checkout-canônico>"
LOG="${1:?uso: 52-gates-integrais.sh <caminho-do-log>}"
EVIDENCIA="docs/09-operations/evidence/2026-09-29-rc01-home-first-fold"
cd "$CHECKOUT" || exit 99

identidade() {
    {
        echo "--- identidade $(date -Is) ---"
        echo "branch=$(git rev-parse --abbrev-ref HEAD)"
        echo "HEAD=$(git rev-parse HEAD)"
        echo "git status --short (esta pasta de evidência excluída: o log cresce durante a execução):"
        git status --short -- . ":!$EVIDENCIA"
        echo "sha256 por conteudo (leitura da arvore de trabalho):"
        for f in src/steamzero/ui/qml/Main.qml src/steamzero/ui/qml/ErrorCard.qml \
                 tests/qml/check_home_first_fold_attention.qml \
                 tests/integration/test_ui_shell_home_first_fold.py; do
            echo "  $(sha256sum "$f" | cut -c1-16)  $f"
        done
        echo "agregado (leitura do INDICE, nao da arvore de trabalho): sha256 src+tests+tools=$(git ls-files -s src tests tools | sha256sum | cut -c1-16)"
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
    echo "CHECKPOINT — primeira dobra da Home: gates rápidos + suíte integral única + gate visual na árvore congelada"
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
