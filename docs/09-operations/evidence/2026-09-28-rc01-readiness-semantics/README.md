# Evidência do lote RC-01 / UX-03 — prontidão semanticamente correta (2026-09-28)

Frente: `WS-2026-09-RC01-READINESS-SEMANTICS`, branch
`codex/rc01-readiness-semantics-2026-09-28`, base `5d95034b` (ponta do PR #242),
quinto elo da pilha #239 → #240 → #241 → #242, publicado como PR #243. CI
terminal lido em `ba2ec0a8` (conteúdo funcional = `ec86c228` + harness
`041139e9`); a passada documental desta rodada não muda conteúdo funcional, e o
veredito do run correspondente à cabeça final é lido antes de qualquer fecho.
Item normativo: `SZ-UI-DESKTOP-AUDIT`.

Esta pasta é o único lugar onde os resultados deste lote existem fora do Git.
Nada aqui foi resumido de chat: todo log abaixo foi gravado pelo comando que o
produziu, e os comandos estão impressos nos próprios arquivos.

## Índice

| Arquivo | O que prova |
| --- | --- |
| `00-preflight-e-mapa-medido.log` | Pré-voos (checkout único, o mesmo venv do projeto, claims lidos no código e não nos relatórios) e o mapa medido dos nove produtores de `readiness.percent`, com a grandeza que cada um publicava e a regra única `>= 80` dos consumidores |
| `01-vermelho-produtores.log` | Vermelho por produtor, antes de qualquer conversão: fixtures sintéticas por origem (20/45/35/100 por categoria, obrigatórios misturados com opcionais, existência de jogos, launchability, `xdg-open`) |
| `02-schema-v2-vermelho-e-verde.log` | Contrato v2 no schema `emulation-workspace-v1.schema.json`: vermelho, depois verde, com denominador zero e dado ausente produzindo traço — nunca 100 nem 0 |
| `03-vermelho-gameplay-e-dashboard.log` | `steam_gameplay` e `desktop_dashboard` convertidos, com a proporção real de requisitos obrigatórios |
| `04-criterio-de-obrigatoriedade.log` | O critério de obrigatoriedade separado do que falta: opcional desatualizado não drena o denominador de obrigatório |
| `05-consumidores-qml.log` | Páginas lendo o módulo compartilhado `readiness.js`; §5 registra as seis capturas promovidas e o defeito de harness achado na inspeção (objeto mutado no lugar = sem change no QML) |
| `05-mutacoes-rodada-1.log` | Bateria de mutação rodada 1: cinco de seis pegas; a sexta escapou e virou pino próprio |
| `05-mutacoes-rodada-2-fundo-cartao.log` | O pino do fundo do cartão escrito como vermelho primeiro, depois verde |
| `06-*` | **Removido deste registro.** Congelou uma árvore anterior à rodada 4 e a suíte interrompida aos 26% não tem veredito. Explicado em `10-checkpoint-10-suite-integral-e-causa.md` §1 |
| `07-mutacoes-rodada-3-pinos-requisito.md` | Pinos de hex literal reescritos como requisitos (contraste, tinta por estado, elipse da causa) e provados por 8/8 mutações |
| `08-reachability-cor-de-tinta-guard-e-empacotamento.md` | Alcance medido do painel de contexto (só abre ≥ 1500 não compacto fora da biblioteca), o guard `READY_BASES` declarado como fechamento de buraco **latente**, e a prova de empacotamento de `readiness.js` re-registrada como **PENDENTE** com o wheel do CI lido entrada a entrada |
| `09-mutacoes-rodada-4-variantlist-e-tinta-do-painel.md` | Os três defeitos de produção que a inspeção visual achou: lista de bloqueios perdida na fronteira `QVariantList`/`Array.isArray`, cabeçalho e glifo pintando `blocked` com âmbar da paleta da plataforma contra o vermelho do contrato, e a próxima ação duplicada como bloqueio. Bateria 6/6, mais uma mutação recusada (código 1 sem linha FAIL não é prova) e refeita |
| `10-checkpoint-header.txt` | Identidade da árvore antes da suíte: branch, HEAD, árvore git e contagem de arquivos |
| `10-congelamento-lista.txt`, `10-congelamento-sha256.txt` | Os 29 arquivos congelados e a soma de cada um |
| `10-suite-integral.log` | A suíte integral única na árvore congelada, com anotação de quem executou no topo (o `CODIGO_DE_SAIDA 0` impresso é do envoltório, não do pytest) |
| `10-gates.log` | ruff check, ruff format --check, mypy e `make independence boundaries` na mesma árvore, todos verdes |
| `10-catalogo-status-check.log` | A única falha da integral, saída bruta do gate |
| `10-atribuicao-digests.log` | Atribuição medida: 33 de 33 itens obsoletos contêm arquivo desta frente; 0 de 33 por obsolescência alheia |
| `11-passada-documental.md` | A passada documental depois do checkpoint: cartão, 33 digests renovados com o valor impresso pela própria ferramenta, visões regeradas, sessão de WORKLOG acrescentada (e o incidente do `sed` global, corrigido e confessado no arquivo) |
| `12-isolamento-mainqml.md` | Rodada de processo depois do checkpoint: `Main.qml` (claim exclusivo de outra frente) sai do commit das páginas e vai para commit próprio, com o pino que faltava no fallback do shell — vermelho e verde medidos, conteúdo da árvore provado idêntico |
| `12-comandos-e-saidas.log` | Saídas cruas da rodada 12: pilha, identidade entre as duas pontas, vermelho/verde do pino, gates focados e os gates de §6 re-rodados na ponta reconstruída |
| `13-wheel-do-ci-contem-readiness-js.md` + `.log` | Fecho da pendência de empacotamento: o wheel produzido pela pipeline governada (run 36475422213) baixado, conferido contra o `SHA256SUMS` do próprio CI, verificado pelo `release_provenance.py verify-wheel` do projeto, e `readiness.js` lido byte a byte dentro dele — `sha256` idêntico ao blob enviado. Registra também a nuance do merge ref, a cobertura medida no CI (85,4897 %) e o erro de processo do `gh run download` |
| `14-geometria-transitoria-vs-assentada-e-mutacoes.md` | Causa **medida** do vermelho do gate visual no CI (PR #243): os Qt Quick Layouts assentam num frame posterior, e a asserção lia `width`/`contentWidth` no mesmo tick da atribuição do modelo (76 px de coluna contra 786 px assentados). Recusa de baixar limiar, espera por condição em vez de tempo, a quebra demonstrada no menor tamanho suportado (720×480, folga de 2,2×) e a bateria de mutações rodada 5 |
| `14-bateria-mutacoes-rodada-5.log` | Saída crua das seis cenas, executadas sobre **cópia** do QML fora do checkout: cinco mutações pegas, um controle negativo deliberado (M2 verde por construção correta) e as limitações que a bateria obriga a registrar — nada na geometria detecta corte por elipse |
| `15-checkpoint-13-gates-integrais.md` | O checkpoint da árvore com o harness corrigido: suíte integral única (1 failed, 6484 passed, 47 skipped), gate visual do CI verde no runner real (356 passed), ruff/format/mypy/independence verdes, identidade reimpressa **depois de cada passo**, a única falha atribuída por inteiro (1 item, desta frente, por construção) e a declaração do que foi mudado depois (só documento). §7 verifica os consumidores do contrato v2 sub-item por sub-item do operador, com o teste citado pelo nome |
| `15-comandos-e-saidas.log` | Saída crua dos sete passos acima, com o `real-state before/after` do executor isolado em cada suíte |
| `15-gates-focados-pos-documental.log` | A reconfirmação depois da passada documental, com o comando impresso no arquivo: 70 passed (13 do gate de catálogo + os 57 harnesses parametrizados, soma conferida em `--collect-only`), ruff check, ruff format, mypy, independence e status-check verdes, e o `sha256` do harness inalterado — o conteúdo funcional testado é o conteúdo enviado |
| `16-ci-terminal-e-wheel-no-sha-final.md` + `.log` | O veredito terminal lido, não prometido: run `36497630184` em `ba2ec0a8` com oito jobs `completed success` (gate visual 21m30s), PR `MERGEABLE`/`CLEAN`; o wheel **desse mesmo run** baixado e lido (`624` entradas, um único `.js` = `steamzero/ui/qml/readiness.js`, sha256 `7d76be27…` idêntico ao blob da cabeça, `verify-wheel` exit 0 concordando com `subject.sha256` da proveniência); cobertura do mesmo artefato (`85,4881 %`) com a diferença de 3 linhas em relação ao run anterior **atribuída por arquivo** a dois módulos que esta frente não toca; a lacuna de captura visual confirmada por contagem (59 arquivos / 41 PNG, só três famílias de diálogo) e mantida aberta; e as três alegações envelhecidas do corpo do PR corrigidas antes de publicar |
| `captures/` | Sete PNGs inspecionados um a um, com `SHA256SUMS.txt` e as dimensões lógicas de cada viewport |

## O que este lote não prova

- **Empacotamento: provado, com o resto declarado.** `readiness.js` foi lido
  dentro do wheel construído pela pipeline governada e é byte a byte o blob
  enviado (`13-…md`). O que **não** está provado aqui, e não pode estar: o wheel
  nomeado pelo SHA *integrado*, depois do merge — esse é artefato do fluxo de
  release do operador (AGENTS.md §4), e em run `pull_request` o artefato existe
  sob o merge ref, não sob a cabeça enviada.
- **Física do gate visual.** O vermelho do PR #243 foi corrigido por medição de
  harness, não por mudança de produto; a causa está em `14-…md`, a verificação no
  runner em `15-…md`, e o job verde no run terminal em `16-…md`. O que continua
  sem prova é a aparência em escala de texto real (100/125/150 %), fora do
  offscreen: `GAP-UI-VISUAL-CAPTURE-NOT-CERTIFIED-IN-CI` segue **aberto** — o
  run terminal publica 41 PNG e nenhum deles é da dobra de prontidão
  (`16-…md` §4).
- **Release instalada.** Todo o verde QML aqui é offscreen no runtime Qt 6.11 do
  projeto. A release `2.0.0rc1-e2af2562ebba` no host não foi tocada: prova física
  segue autorização específica do operador.
- **Integração.** Nada aqui alega merge. A ordem de integração e os bloqueios
  estão em `10-…causa.md`, em `15-…md` e no `nextAction` do workstream.
