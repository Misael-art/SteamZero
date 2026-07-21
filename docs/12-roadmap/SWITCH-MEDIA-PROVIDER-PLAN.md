# Plano de provedores de mídia para jogos Switch

Status: planejado; nenhum scraping externo faz parte do runtime atual.

## Objetivo

Obter capas, banners, hero, logo e ícones com boa qualidade sem tornar a
biblioteca, o lançamento ou a publicação na Steam dependentes de um serviço
externo. O pacote validado será entregue ao `SteamMediaManager`, que já aplica
arquivos locais com preview, confirmação e rollback G-FULL.

## Decisão conservadora atual

A base LaunchBox é uma referência visual desejável, mas não oferece hoje uma
API pública oficial documentada. Automação por HTML, engenharia reversa de
endpoints ou redistribuição de imagens não será incorporada. Um provider só
será habilitado depois de aprovação explícita de termos, licença, autenticação
e limites de uso. Até lá, a jornada aceita pacotes locais fornecidos pelo
usuário e nunca bloqueia Play, varredura ou sincronização da Steam.

## Contrato proposto

`MediaProviderPort.search()` recebe plataforma, Title ID, nome normalizado e
região. Ele retorna candidatos com URL HTTPS, tipo de arte, dimensões, idioma,
licença, atribuição, hash quando disponível e confiança do match. O provider
não escreve na Steam nem na biblioteca; apenas baixa para staging privado.

O fluxo será:

1. correspondência exata por Title ID; fallback por nome/região somente com
   preview e confiança visível;
2. consentimento opt-in e credencial no keyring, nunca em logs ou snapshots;
3. fila com limite de concorrência, rate limit, jitter e backoff exponencial;
4. download HTTPS com limite por arquivo e por lote, timeout e cancelamento;
5. validação de magic bytes, tipo real, dimensões, decompression bomb e hash;
6. cache endereçado por conteúdo com proveniência, licença e validade;
7. revisão do usuário e aplicação pelo adapter local existente;
8. rollback byte-idêntico e limpeza segura do staging.

## Gates de entrega

- G1 — parecer de termos/licença e autorização para cada tipo de arte;
- G2 — API oficial estável ou pacote local do usuário; HTML scraping reprova;
- G3 — testes de rate limit, 429, 5xx, timeout, conteúdo truncado e offline;
- G4 — corpus adversarial de imagens, limites de tamanho e nenhum parser ativo;
- G5 — match incorreto nunca é aplicado sem preview explícito;
- G6 — falha do provider degrada para mídia local sem afetar o lançamento;
- G7 — provenance/attribution exportável e remoção por origem;
- G8 — integração Steam testada com cliente encerrado e rollback G-FULL;
- G9 — cache e credenciais não aparecem em telemetria nem no WORKLOG;
- G10 — revisão de acessibilidade e navegação por controle no Game Mode.

## Entregas incrementais

- M1: importador de pacote local por jogo e preview das cinco classes de arte;
- M2: interface de providers e provider de fixture/offline para testes;
- M3: provider externo somente após G1/G2, inicialmente opt-in e um jogo por vez;
- M4: lote selecionável com orçamento, pausa, retomada e relatório de falhas;
- M5: curadoria de múltiplos candidatos e política por região/idioma.

## Rollback e observabilidade

Cada aplicação registra operação, hashes anteriores/novos e provider, sem URL
assinada nem segredo. Downloads parciais ficam fora da árvore Steam. Em crash,
o recovery descarta staging incompleto; uma falha repetida abre o circuito do
provider e mantém a última mídia local válida.
