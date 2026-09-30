#!/usr/bin/env bash
# Revalidação proporcional pós-correção de citações (oitavo elo, árvore e7167080 + um
# commit documental). AGENTS §6: "Não repita suíte integral, build de release,
# status-check ou gates remotos entre microalterações." As quatro correções são
# docstring, comentário QML, linha de README e texto de evidência em cartão:
# nenhuma asserção executável foi tocada (diff inspecionado em 55-correcao-de-citacoes.md).
# Portanto: as três portas de estática, o gate AFETADO por extensão (o harness QML roda
# dentro dele) e o status-check. A integral e o gate visual largos do checkpoint 52
# permanecem anexados a e7167080 e não são reatribuídos a este commit.
#
# Log FORA do checkout, por motivo já declarado no 52: a pasta de evidência está em
# scopePaths de SZ-UI-DESKTOP-AUDIT.
set -u
CHECKOUT="<checkout-canônico>"
LOG="${1:?uso: 55-revalidacao-proporcional.sh <caminho-do-log>}"
cd "$CHECKOUT" || exit 99

identidade() {
    {
        echo "--- identidade $(date -Is) ---"
        echo "branch=$(git rev-parse --abbrev-ref HEAD)"
        echo "HEAD=$(git rev-parse HEAD)"
        echo "git status --short:"
        git status --short
        echo "sha256 por conteudo (arvore de trabalho):"
        for f in tests/integration/test_ui_shell_home_first_fold.py \
                 tests/qml/check_home_first_fold_attention.qml \
                 docs/09-operations/evidence/2026-09-29-rc01-home-first-fold/README.md \
                 docs/status/items/ui-desktop-audit.json; do
            echo "  $(sha256sum "$f" | cut -c1-16)  $f"
        done
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
    echo "FIM $(date -Is) rc=$rc" >>"$LOG"
    echo "$n rc=$rc :: $cmd" >>"$LOG".rc
    return 0
}

: >"$LOG"
: >"$LOG".rc
{
    echo "REVALIDAÇÃO PROPORCIONAL — correção de quatro citações falsas (oitavo elo)"
    echo "COMANDO-MAE: bash $0 $LOG"
    echo "INICIO $(date -Is)"
    echo "python=$(.venv/bin/python -V 2>&1)"
} >>"$LOG"

passo 1 ".venv/bin/ruff format --check src tests tools" 600
passo 2 ".venv/bin/ruff check src tests tools" 600
passo 3 ".venv/bin/mypy src" 1200
passo 4 ".venv/bin/python -m pytest tests/integration/test_ui_shell_home_first_fold.py -q" 900
passo 5 "make status-check" 600

{
    echo
    echo "===== ROLLUP"
    cat "$LOG".rc
    echo "FIM TOTAL $(date -Is)"
} >>"$LOG"
touch "$LOG".concluido
