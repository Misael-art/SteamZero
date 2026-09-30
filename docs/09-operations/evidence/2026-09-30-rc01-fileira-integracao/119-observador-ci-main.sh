#!/usr/bin/env bash
# Observador do CI na composicao final do main (SHA pinado).
# Correcao do falso-positivo de 29/09: so sai TERMINAL quando os oito checks
# obrigatorios tem conclusao NAO-VAZIA. Leitura em andamento jamais conta como terminal.
set -uo pipefail
CK="/home/misael/Projects/Steam Zero/Canonical/2026-09-21"
SHA=${1:-7808374257db3059c1934cb4be6007d8a749346e}
LOG=${2:-/home/misael/steamzero-retrofe-tmp/119-ci-terminal-main-consolidado.log}
MAX=${3:-40}
REQ=("Python 3.11" "Python 3.12" "Python 3.14" "Wheel limpo, smoke e supply chain" \
     "Smoke Ubuntu 24.04" "Smoke Arch Linux" "Smoke Manjaro" "Gate visual QML (Linux)")
cd "$CK"
echo "=== observador CI main consolidado  SHA=$SHA  inicio $(date -Is)  (max $MAX leituras, 90s entre elas)" | tee -a "$LOG"
for i in $(seq 1 "$MAX"); do
  ROLL=$(gh api "repos/Misael-art/SteamZero/commits/$SHA/check-runs" \
          --jq '[.check_runs[] | {n:(.name), c:(.conclusion // ""), s:(.status)}]' 2>/dev/null || echo "[]")
  MISSING=""; NONSUCC=""
  for r in "${REQ[@]}"; do
    raw=$(jq -r --arg r "$r" '[.[] | select(.n==$r)] | if length==0 then "AUSENTE" else "\(.[0].c);\(.[0].s)" end' <<< "$ROLL" 2>/dev/null)
    [ -z "$raw" ] && raw="ERRO-JQ"
    concl=$(tr '[:lower:]' '[:upper:]' <<< "${raw%%;*}"); status=${raw#*;}
    case "$concl" in
      AUSENTE) MISSING="$MISSING $r=AUSENTE";;
      ERRO-JQ) MISSING="$MISSING $r=ERRO-JQ";;
      SUCCESS) : ;;
      "") if [ -z "$concl" ]; then
           MISSING="$MISSING $r=PENDENTE($status)"
         fi;;
      *) MISSING="$MISSING $r=CONCLUSAO($concl)";;
    esac
  done
  TOTAL=$(jq -r 'length' <<< "$ROLL" 2>/dev/null)
  echo "leitura $i $(date -Is): check-runs=$TOTAL pendentes/falhos:${MISSING:-nenhum}" | tee -a "$LOG"
  if [ -z "$MISSING" ]; then
    echo "TERMINAL de verdade apos $i leitura(s): os oito obrigatorios estao SUCCESS em $SHA" | tee -a "$LOG"
    jq -r '.[] | "  \(.n)\t\(.c)\t\(.s)"' <<< "$ROLL" | tee -a "$LOG"
    exit 0
  fi
  sleep 90
done
echo "SAIU POR MAXIMO ($MAX leituras) sem terminal. Estado acima e o ultimo medido." | tee -a "$LOG"
exit 2
