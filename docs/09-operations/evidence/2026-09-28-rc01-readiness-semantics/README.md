# Evidência do lote RC-01 / UX-03 — prontidão semanticamente correta (2026-09-28)

Frente: `WS-2026-09-RC01-READINESS-SEMANTICS`, branch
`codex/rc01-readiness-semantics-2026-09-28`, base `5d95034b` (ponta do PR #242),
quinto elo da pilha #239 → #240 → #241 → #242. Item normativo:
`SZ-UI-DESKTOP-AUDIT`.

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
| `captures/` | Sete PNGs inspecionados um a um, com `SHA256SUMS.txt` e as dimensões lógicas de cada viewport |

## O que este lote não prova

- **Empacotamento.** `readiness.js` dentro do wheel ainda não foi lido de um
  artefato construído no SHA deste lote. Registrado como pendência
  (`GAP-UI-QML-JS-NAO-PROVADO-DENTRO-DO-WHEEL-DO-CI`), com o procedimento de
  fechamento em `08-…md` §5.
- **Release instalada.** Todo o verde QML aqui é offscreen no runtime Qt 6.11 do
  projeto. A release `2.0.0rc1-e2af2562ebba` no host não foi tocada: prova física
  segue autorização específica do operador.
- **Integração.** Nada aqui alega merge. A ordem de integração e os bloqueios
  estão em `10-…causa.md` e no `nextAction` do workstream.
