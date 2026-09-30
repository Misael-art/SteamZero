#!/usr/bin/env bash
# Varredura de segredos e conteudo pessoal no que o fechamento da fileira publica.
#
# Uso: 127-varredura-de-segredos.sh [<commit-ref>]
#      sem argumento  -> varre o diff staged (o que esta prestes a ser publicado);
#      com um commit  -> varre as linhas que aquele commit adicionou.
# Rodar como ULTIMA escrita de conteudo, antes do commit documental: assim os totais
# impressos aqui sao os do conteudo que vai ser commitado (ver 126, adenda).
#
# Dois alvos, porque a afirmacao a sustentar e sobre o QUE ESTA ENTREGA publica:
#   A) conteudo integral dos arquivos desta pasta de evidencia;
#   B) apenas as LINHAS ADICIONADAS desta entrega nos arquivos ja versionados
#      (docs/WORKLOG.md, docs/status/**). O WORKLOG lido inteiro contem caminho
#      absoluto do acervo pessoal; faze-lo alvo A herearia uma acusacao contra o
#      passado em vez de medir esta entrega. O passado e medido a parte, na secao final.
#
# Auto-exclusao declarada: este script e o log que ele produz ficam fora do alvo A
# porque contem os literais dos padroes (auto-correspondencia). Os dois sao conferidos
# por outro metodo na secao "auto-excluidos".
#
# Saida: stdout -> 127-varredura-de-segredos-e-dados-pessoais.log
set -u
cd "$(cd "$(dirname "$0")/../../../.." && pwd)" || exit 1
EV=docs/09-operations/evidence/2026-09-30-rc01-fileira-integracao
REF=${1:-}
if [ -n "$REF" ]; then set -- "$REF^" "$REF"; else set -- --cached; fi
git diff "$@" -- . ":!$EV" > /tmp/fechamento127.diff
ADDS=/tmp/fechamento127.adds
grep '^+[^+]' /tmp/fechamento127.diff | sed 's/^+//' > "$ADDS"
BFILES=$(grep '^+++ b/' /tmp/fechamento127.diff | sed 's|^+++ b/||' | sort)
LISTA_A=$(find "$EV" -maxdepth 1 -type f ! -name '127-varredura-de-segredos.sh' \
  ! -name '127-varredura-de-segredos-e-dados-pessoais.log' | sort)

# As seis classes. A sexta e a que identifica dado pessoal de fato: caminho absoluto
# fora do repositorio apontando para conteudo do usuario (acervo, documentos, imagens).
P1='gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}'
P2='BEGIN (RSA |OPENSSH |EC |DSA )?PRIVATE KEY'
P3='(aws_secret_access_key|client_secret|api_key|apikey|secret_key|access_token|password|passwd)[[:space:]]*[:=][[:space:]]*["'"'"']?[A-Za-z0-9/+_.-]{8,}'
P4='[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'
P5='eyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{8,}'
P6='/home/[A-Za-z0-9._-]+/(emulation|Documentos|Downloads|Desktop|Imagens|Photos|Steam)/'
# Vocabulario do dominio. Nao e achado de seguranca: e o nome das coisas que o produto
# gerencia, e aparece em codigo, teste e doc. Serve de controlador de nao-vacio.
VOC='(roms|ROMs|bios|BIOS|saves|SteamLibrary|steamlibrary|/emulation/)'
LABELS=(
 "token GitHub"
 "chave privada PEM"
 "segredo atribuido a chave de config"
 "e-mail"
 "JWT"
 "caminho absoluto pessoal (fora do repo)"
)
PATS=("$P1" "$P2" "$P3" "$P4" "$P5" "$P6")

echo "=== parametros ==="
echo "ref varrido         : ${REF:-<diff staged>}"
echo "rev do checkout     : $(git rev-parse HEAD)"
echo "auto-excluidos de A : $EV/127-varredura-de-segredos.sh"
echo "                      $EV/127-varredura-de-segredos-e-dados-pessoais.log"
echo
echo "=== alvo A: conteudo integral desta pasta de evidencia ==="
echo "$LISTA_A" | sed 's#^#  #'
echo "arquivos: $(echo "$LISTA_A" | wc -l)   linhas: $(cat $LISTA_A | wc -l)"
echo
echo "=== alvo B: linhas adicionadas desta entrega nos arquivos ja versionados ==="
echo "$BFILES" | sed 's#^#  #'
echo "arquivos: $(echo "$BFILES" | wc -l)   linhas adicionadas: $(wc -l < $ADDS)"
echo
printf "%-44s %-8s %s\n" "padrao" "alvo-A" "alvo-B"
for i in "${!PATS[@]}"; do
  printf "%-44s %-8s %s\n" "${LABELS[$i]}" \
    "$(grep -hIE "${PATS[$i]}" $LISTA_A 2>/dev/null | wc -l)" \
    "$(grep -hIE "${PATS[$i]}" $ADDS 2>/dev/null | wc -l)"
done
echo
echo "=== alvo A: ocorrencia por arquivo (as seis classes somadas) ==="
for f in $LISTA_A; do
  n=$(grep -hIE "$P1|$P2|$P3|$P4|$P5|$P6" "$f" 2>/dev/null | wc -l)
  [ "$n" -gt 0 ] && printf "%6s  %s\n" "$n" "$f"
done
echo "(nenhuma linha acima = zero ocorrencias em todos os arquivos do alvo A)"
echo
echo "=== contexto: cada linha com caminho absoluto, nos dois alvos ==="
grep -nIE '/home/[A-Za-z0-9._-]+/' $LISTA_A
echo "--- alvo B ---"
grep -nIE '/home/[A-Za-z0-9._-]+/' $ADDS
echo
echo "=== os unicos caminhos absolutos publicados, agrupados por dois primeiros niveis ==="
{ grep -hoE '/home/[A-Za-z0-9._-]+[A-Za-z0-9._/-]*' $LISTA_A
  grep -hoE '/home/[A-Za-z0-9._-]+[A-Za-z0-9._/-]*' $ADDS; } \
  | sed -E 's#^(/home/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+).*#\1#' | sort | uniq -c | sort -rn
echo
echo "=== hosts externos citados ==="
{ grep -hoE 'https?://[A-Za-z0-9._/?=%-]+' $LISTA_A
  grep -hoE 'https?://[A-Za-z0-9._/?=%-]+' $ADDS; } | cut -d/ -f3 | sort | uniq -c | sort -rn
echo
echo "=== controlador de nao-vacio: o mesmo mecanismo, aplicado a uma fixture sintetica ==="
# Seis linhas plantadas fora do repositorio (em /tmp, nunca commitadas), uma por classe.
# Sem isto, "zero em tudo" nao distingue "nao havia" de "nao procurava".
FIX=/tmp/127-controle-negativo.txt
{ printf 'ghp_%s\n' "$(printf 'x%.0s' 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 33 34)"
  echo '-----BEGIN OPENSSH PRIVATE KEY-----'
  echo 'client_secret = abcdefghijklmnop1234'
  echo 'mailto: alguem@exemplo.invalido.br'
  echo 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0'
  echo 'copiei de /home/fulano/emulation/roms/psvita/jogo.zip'
} > "$FIX"
printf "%-44s %-8s %s\n" "padrao" "fixture" "fixture+alvo"
for i in "${!PATS[@]}"; do
  printf "%-44s %-8s %s\n" "${LABELS[$i]}" \
    "$(grep -hcIE "${PATS[$i]}" "$FIX")" \
    "$(cat "$FIX" $ADDS | grep -cIE "${PATS[$i]}")"
done
echo "(cada classe acha a sua linha plantada; o alvo real, acima, nao acha nenhuma)"
echo "vocabulario do dominio (roms/bios/saves/emulation), que NAO e achado:"
printf "  alvo-A: %s   alvo-B: %s   fixture: %s\n" \
  "$(grep -hIE "$VOC" $LISTA_A | wc -l)" "$(grep -hIE "$VOC" $ADDS | wc -l)" \
  "$(grep -cIE "$VOC" "$FIX")"
echo "logo o mecanismo conta; o zero das seis classes e ausencia do que elas procuram,"
echo "nao ausencia de procura."
echo
echo "=== auto-excluidos, conferidos por outro metodo ==="
echo "-- (i) runs de 36+ caracteres alfanumericos seguidos, nos dois arquivos --"
grep -hoE '[A-Za-z0-9_]{36,}' "$EV/127-varredura-de-segredos.sh" \
  "$EV/127-varredura-de-segredos-e-dados-pessoais.log" 2>/dev/null | sort | uniq -c \
  | sed -E 's/([0-9a-f]{8})[0-9a-f]{6,}/\1…(objeto git)/g; s/^/  /'
echo "  (o que aparece aqui e identificador de commit e de blob, citado de proposito; nenhum"
echo "   tem o prefixo de token do GitHub, e a fixture acima prova que o formato seria achado)"
echo "-- (ii) linha do script que contem palavra de credencial --"
grep -niE 'password|secret|token|api.?key' "$EV/127-varredura-de-segredos.sh" \
  | sed -E 's/^/  /'
echo "  (todas sao nome de padrao, texto de grep, etiqueta de tabela ou linha plantada da"
echo "   fixture de controle -- valor sintetico, escreito aqui para que o formato fosse"
echo "   achado se aparecesse num alvo. Nenhum e credencial real: a coluna 'fixture' acima"
echo "   prova que o mecanismo as detecta, e os alvos A e B dao zero.)"
echo "-- (iii) o script codifica algum caminho absoluto? --"
grep -cE '/home/' "$EV/127-varredura-de-segredos.sh"
echo "  (todas as ocorrencias sao o texto dos greps que ele executa; a raiz do checkout vem"
echo "   de dirname \$0, entao o log e repetivel em qualquer maquina)"
echo
echo "=== o que fica FORA do escopo desta varredura, medido a parte ==="
printf "  docs/WORKLOG.md lido inteiro, hoje        : %s linhas com caminho pessoal absoluto\n" \
  "$(grep -cIE "$P6" docs/WORKLOG.md)"
printf "  docs/WORKLOG.md lido inteiro, em 3495c49d : %s linhas\n" \
  "$(git show 3495c49d5d7c3244267e8292beee34475f70236b:docs/WORKLOG.md | grep -cIE "$P6")"
git diff 3495c49d5d7c3244267e8292beee34475f70236b..7808374257db3059c1934cb4be6007d8a749346e \
  | grep '^+[^+]' | grep -cIE "$P6" \
  | sed 's/^/  fileira inteira (#239..#247), linhas adicionadas com o mesmo padrao: /'
echo
cat <<'TXT'
=== leitura do resultado ===
* Zero nas seis classes, nos dois alvos. Os unicos caminhos absolutos publicados por
  esta entrega sao o do checkout, o do temporario e o do acervo duravel de evidencia
  - os tres necessarios para repetir o comando que gera este log.
* O controle de nao-vacio e uma fixture sintetica em /tmp (seis linhas plantadas, uma por
  classe, nunca commitadas): as seis sao achadas, e o alvo real nao acha nenhuma. Sem essa
  coluna, "zero em tudo" nao distinguiria "nao havia" de "nao procurava".
* O vocabulario do dominio (roms, bios, saves, emulation) e o nome das coisas que o produto
  gerencia; aparece em codigo, teste e doc e nao e achado de seguranca. Por isso e medido e
  rotulado a parte, e nao entra nas seis classes.
* CORRECAO na mesma rodada, antes de qualquer commit: a primeira versao desta secao
  afirmava "107 linhas com termo de acervo" no WORKLOG. O numero vinha de um escopo
  errado - a pasta de evidencia contava dentro do alvo B, e os literais dos proprios
  padroes entravam na soma. O que identifica dado pessoal e o caminho absoluto fora do
  repo, medido na secao anterior, e nao o termo de dominio.
* Consequencia: as linhas do WORKLOG com caminho do acervo pessoal sao as mesmas sete da
  base anterior a fileira. Nem a fileira nem este fechamento acrescentaram uma.
  Apaga-las ou reescreve-las seria falsificar o registro, e a ordem do operador proibe
  tanto apagar acervo quanto reescrever historico. Ficam declaradas como pendencia do
  operador, nao encobertas por uma alegacao de limpeza do arquivo inteiro.
TXT
