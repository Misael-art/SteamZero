#!/usr/bin/env bash
# Conferencia pos-merge de um elo da fileira #239..#247.
# Uso: 117-pos-merge.sh <numero-pr> <head-esperada-40> <proxima-pr-ou-none>
# Leitura apenas: git fetch/rev-parse/merge-base/diff/rev-list + gh pr view.
set -euo pipefail
CK="/home/misael/Projects/Steam Zero/Canonical/2026-09-21"
PR=$1; HEAD=$2; NEXT=${3:-none}
cd "$CK"
git fetch origin main --quiet
MAIN=$(git rev-parse origin/main)
V=$(gh pr view "$PR" --json state,mergedAt,mergeCommit,baseRefName,headRefOid \
      --jq '[(.state),(.mergedAt // "-"),(.mergeCommit.oid // "-"),.baseRefName,(.headRefOid[0:12])]|@tsv')
IFS=$'\t' read -r STATE MERGEDAT MERGECOMMIT BASE PRHEAD <<< "$V"
echo "PR #$PR  state=$STATE  mergedAt=$MERGEDAT  mergeCommit=${MERGECOMMIT:0:12}  base=$BASE  head=$PRHEAD"
echo "origin/main = $MAIN"
if [ "$MERGECOMMIT" != "-" ]; then
  NPARENTS=$(git cat-file -p "$MERGECOMMIT" | grep -c '^parent')
  echo "merge commit ${MERGECOMMIT:0:12} tem $NPARENTS pai(s): $(git cat-file -p "$MERGECOMMIT" | awk '$1=="parent"{print substr($2,1,12)}' | tr '\n' ' ')"
  TM=$(git rev-parse "$MERGECOMMIT^{tree}"); TH=$(git rev-parse "$HEAD^{tree}")
  echo "arvore integrada = ${TM:0:12} | arvore da cabeca testada no CI = ${TH:0:12} | IGUAIS? $( [ "$TM" = "$TH" ] && echo 'SIM (a composicao que landed e a mesma que o CI validou)' || echo 'NAO — composicao nova, verde NAO transfere' )"
fi
echo "main acima desta cabeca (rev-list HEAD..main): $(git rev-list --count "$HEAD..$MAIN")"
if git merge-base --is-ancestor "$HEAD" "$MAIN"; then
  echo "ancestralidade: head $HEAD acima de main? SIM"
else
  echo "ancestralidade: head $HEAD acima de main? NAO  <<< INTERROMPER"
  exit 7
fi
echo "main acima desta cabeca (rev-list HEAD..main): $(git rev-list --count "$HEAD..$MAIN")"
if [ "$NEXT" != "none" ]; then
  NH=$(gh pr view "$NEXT" --json headRefOid -q .headRefOid)
  NB=$(gh pr view "$NEXT" --json baseRefOid -q .baseRefOid)
  echo "proxima PR #$NEXT head=${NH:0:12} base=$(gh pr view "$NEXT" --json baseRefName -q .baseRefName)@${NB:0:12}"
  echo "  diff exclusivo vs main: $(git diff --shortstat "$MAIN...$NH" | sed 's/^ *//')"
  echo "  proprios (main..head): $(git rev-list --count "$MAIN..$NH")"
  echo "  mergeable=$(gh pr view "$NEXT" --json mergeable -q .mergeable) mergeStateStatus=$(gh pr view "$NEXT" --json mergeStateStatus -q .mergeStateStatus)"
fi
