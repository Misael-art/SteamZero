#!/usr/bin/env bash
# Mescla UM elo da fileira, somente se o gate obrigatorio estiver verde no SHA exato.
# Recusa qualquer bypass: sem --admin, sem force, sem check pendente/vermelho/ausente.
# Uso: 118-merge-um-elo.sh <numero-pr>
set -euo pipefail
CK="/home/misael/Projects/Steam Zero/Canonical/2026-09-21"
REQ=("Python 3.11" "Python 3.12" "Python 3.14" "Wheel limpo, smoke e supply chain" \
     "Smoke Ubuntu 24.04" "Smoke Arch Linux" "Smoke Manjaro" "Gate visual QML (Linux)")
PR=$1
cd "$CK"
SHA=$(gh pr view "$PR" --json headRefOid -q .headRefOid)
STATE=$(gh pr view "$PR" --json state -q .state)
M=$(gh pr view "$PR" --json mergeable,mergeStateStatus --jq '[.mergeable,.mergeStateStatus]|@tsv')
read -r MERGEABLE MERGESTATE <<< "$M"
echo "gate PR #$PR head=$SHA state=$STATE mergeable=$MERGEABLE mergeState=$MERGESTATE"
ROLL=$(gh pr view "$PR" --json statusCheckRollup \
  --jq "[.statusCheckRollup[] | {n:(.name // .context), c:(.conclusion // .status)}]")
FAIL=0
for r in "${REQ[@]}"; do
  line=$(jq -r --arg r "$r" '.[] | select(.n==$r) | "\(.n) <- \(.c // "AUSENTE")"' <<< "$ROLL")
  [ -z "$line" ] && line="$r <- AUSENTE"
  echo "  $line"
  case "$line" in *"<- SUCCESS") ;; *) FAIL=1 ;; esac
done
if [ "$STATE" != "OPEN" ]; then echo "RECUSA: PR nao esta OPEN (state=$STATE)"; exit 3; fi
if [ "$MERGEABLE" != "MERGEABLE" ] || [ "$MERGESTATE" != "CLEAN" ]; then
  echo "RECUSA: composicao nao esta MERGEABLE/CLEAN ($MERGEABLE/$MERGESTATE)"; exit 4; fi
if [ "$FAIL" -ne 0 ]; then echo "RECUSA: gate obrigatorio nao esta 8/8 SUCCESS no SHA exato"; exit 5; fi
echo "gate OK -> gh pr merge $PR --merge"
gh pr merge "$PR" --merge
echo "merge solicitado para #$PR (sem --admin, sem --delete-branch)"
