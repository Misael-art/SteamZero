# PHASEZERO-MIGRATION — importação legada offline e opcional

## Regra de independência

O SteamZero não detecta, importa, chama, inicia, para ou monitora PhaseZero em runtime.
Não compartilha estado, código, serviço, lock, configuração nem mecanismo de rollback.
Uma instalação limpa deve oferecer todas as capacidades sem qualquer artefato legado.

Referências ao projeto pesquisado são permitidas apenas em pesquisa, atribuição legal e
neste protocolo de importação. O gate `make independence` protege o pacote padrão.

## Ferramenta separada

`tools/import_phasezero_snapshot.py` não é empacotado nem registrado como entrypoint do
SteamZero. Ele:

1. recebe um diretório de snapshot explicitamente escolhido pelo usuário;
2. lê somente arquivos JSON regulares, com containment, limite de quantidade/tamanho e
   rejeição de symlinks;
3. produz em stdout um bundle `steamzero.offline-legacy-import` autocontido;
4. nunca executa `pz`, scripts, serviços ou comandos contidos no snapshot;
5. não aplica o bundle automaticamente.

Depois da conversão, apagar a origem não pode alterar o bundle nem o SteamZero. A
importação futura do bundle seguirá scan→plan→preview→confirm→apply, copiando o estado
aceito para estruturas nativas.

## Ownership e conflito

Não existe coexistência coordenada. Antes de assumir entrada/display, o SteamZero usa
detecção genérica de concorrência por recurso. Estado instável ou dispositivo já
capturado resulta em `E-DESKTOP-OWNER-CONFLICT` e modo observador; não há tentativa de
identificar ou controlar o processo externo.

O desligamento de qualquer serviço legado é uma ação externa e explícita do usuário,
fora do runtime SteamZero. Nenhum rollback SteamZero depende de reativá-lo.
