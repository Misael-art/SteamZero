# Radiografia consultiva de UX — rerun da release ativa

Data: 2026-09-01. Objetivo: substituir a evidência anterior, que descrevia a
release `2.0.0rc1-0920e785d174`, pela observação da release ativa
`2.0.0rc1-db59992ba514`, após a correção do primeiro P0 de IDs hexadecimais.

Nenhum código, host, instalação, publicação, push ou rollback foi alterado.

## Resultado executivo

O P0 de IDs hexadecimais foi realmente superado, mas a jornada real ainda está
bloqueada por um segundo P0: o Launcher rejeita a home com 13 seções quando o
limite é 12. A Central continua visualmente utilizável, mas apresenta uma
divergência importante entre a janela instalada (`0 títulos publicados`) e o
runner de auditoria com bridge live (`246 títulos`). Isso impede declarar a
proveniência do catálogo como confiável sem uma validação adicional.

Em termos de produto, a situação melhorou no diagnóstico — o erro avançou de
identidade de item para composição da home —, mas não melhorou ainda na jornada
do usuário: ele continua sem chegar ao primeiro cartão do catálogo real.

## Evidência e proveniência

- `01-central-active-800x1280.png`: captura da Central instalada na sessão
  gráfica ativa; estado observado com zero títulos.
- `launcher-failure.txt`: reprodução do erro real da release ativa.
- `02-launcher-fixture-active-db59992b.png`: shell fullscreen abriu com três
  itens temporários, foco ciano e placeholders honestos.
- `03-launcher-search-attempt-db59992b.png`: tentativa de busca por evento
  sintético; campo não abriu e o resultado é não validado.
- `MANIFEST.json` e demais PNGs: 55 capturas do runner on-screen, com
  `dataOrigin=bridge-live`, QML return code 0, em 1280×800, 1600×1000,
  1920×1080, 2560×1080 e 949×593.
- `release-state.txt`: versão ativa, sessão, origem e divergência de dados.

O runner foi executado enquanto a branch tinha apenas o workstream documental
novo não commitado. Por isso o manifesto informa worktree dirty; suas imagens
não são artefato de release. A prova física do binário instalado é a captura da
Central e a reprodução do Launcher real.

## Veredito atualizado

| Área | Nota | Diagnóstico |
|---|---:|---|
| AURA Launcher | 1/10 | O P0 de ID foi substituído por `home excede 12 seções`; a home real continua inacessível. Fixture visual abre, mas não certifica o catálogo. |
| Big Picture | 1/10 validado | Atalho, navegação por controle, busca, lançamento e retorno continuam não validados. |
| Central/AURA UI | 6/10 | Abre e mantém hierarquia visual, mas o estado físico de zero títulos e o banner “Nenhum perfil foi aplicado” reduzem confiança. |
| Tema/runtime | 6/10 | Quatro temas continuam listados; `asset-recipes-demo` ativo, com tokens e fallback declarativo. A troca completa por tema e AA renderizado continuam sem certificação. |
| Theme Studio | 4/10 | O canvas/árvore/inspector continuam legíveis no runner, mas a ferramenta ainda parece inspector de leitura, sem autoria direta observada. |
| Biblioteca/mídia | 4/10 | Runner mostra modos de biblioteca e estados de mídia, mas o catálogo físico não está coerente com a captura live; provider, quota e aplicação permanecem incompletos. |
| Acessibilidade | 5/10 | Foco é visível no fixture e na Central, mas rodapé de dicas e controles muted permanecem fracos; busca e controle físico não foram provados. |
| Fluidez percebida | 5/10 | 55 capturas concluíram com QML rc=0, porém o bloqueio antes da home e a divergência 0/246 quebram a percepção de confiabilidade. |

## O que mudou desde a auditoria anterior

- **Corrigido:** IDs hexadecimais do catálogo não derrubam mais a montagem do
  item individual.
- **Novo P0:** 13 plataformas/sections excedem o teto de 12 e encerram o
  Launcher antes da home.
- **Permanece:** jogar → fechar → restaurar foco, busca, coleções e atalho
  Big Picture não foram validados com dados reais.
- **Permanece:** Central aberta com aviso de perfil não aplicado; dicas de
  controle e estados disabled têm contraste visual baixo.
- **Novo risco de confiança:** janela instalada e bridge-live apresentam
  cardinalidades distintas (`0` contra `246`). A diferença pode ser de fonte,
  processo, momento ou harness, mas o produto precisa torná-la explicável.
- **Permanece:** avisos do KDE Breeze (`TextArea.qml` e `ProgressBar.qml`)
  aparecem durante o runner. Não há atribuição segura ao QML SteamZero, mas são
  um sinal de acabamento a investigar.

## P0 — bloqueios de experiência

1. **Home real não monta com 13 seções.** Reproduzir executando
   `steamzero-launcher` na release ativa. O usuário não alcança biblioteca,
   busca, coleções, detalhe, jogar ou retorno. O próximo teste deve provar uma
   política de overflow/paginação/agrupamento que mantenha todas as plataformas
   navegáveis, sem simplesmente perder a 13ª.
2. **Catálogo físico não tem uma verdade visível única.** Reproduzir abrindo a
   Central instalada e comparando com o runner live: a primeira mostra zero; o
   segundo 246. Até explicar a origem e o momento de cada read model, não se
   deve declarar o catálogo pronto para a jornada.

## P1/P2 atualizados

### P1

- **P1 — busca não validada:** a tentativa com `xdotool F` não abriu o campo;
  isso não prova defeito, mas também não permite declarar a busca funcional.
- **P1 — collections:** estado de dados ainda mostra favoritos persistidos,
  mas coleção Favoritos sem membros; o usuário pode interpretar isso como perda
  de organização.
- **P1 — mídia:** o fluxo visual continua sem uma narrativa única de provider,
  plano, progresso em bytes, quota, retry e capa aplicada.
- **P1 — Theme Studio:** a captura mostra a cena e inspector, não edição direta,
  constraints, timeline e undo/redo.

### P2

- Rodapé “STEAM MENU / A SELECIONAR / B VOLTAR” continua quase ilegível.
- Banner de perfil não aplicado ocupa posição de destaque e domina telas de
  conteúdo.
- Handheld ainda corta conteúdo sem indicador de continuação.
- Grid/lista alterna entre arte, placeholder e grandes vazios; o usuário não
  sabe se está aguardando mídia ou se ela não existe.
- Nomes longos de plataformas são truncados sem contexto suficiente.

## Mercado e recomendação

Contra Steam Deck/Big Picture, Playnite, LaunchBox e ES-DE, o SteamZero continua
à frente na honestidade de diagnósticos operacionais e na explicação de
prontidão de emulação. Continua atrás na resiliência da home, na jornada de
sofá, na descoberta/busca, na previsibilidade de artwork e na autoria visual do
tema.

Recomendação: tratar o limite de seções como correção de produto de primeira
ordem e repetir imediatamente o binário instalado com o catálogo completo. A
aceitação mínima deve ser: home abre com todas as 13 plataformas, foco inicial
determinístico, busca, coleção, detalhe, launch/return e captura do mesmo
catálogo antes/depois. Em paralelo, tornar explícita a origem do read model da
Central para eliminar a divergência 0/246. Só depois retomar polimento do
Theme Studio, contraste e efeitos premium.

## Anomalias de checkout desta sessão

O mecanismo continua ativo, mas não reproduzi as três anomalias no fechamento
desta rodada: `origin` está identificado para fetch/push; a branch de auditoria
foi criada a partir do tip atual; a captura foi feita antes do commit do
workstream e o manifesto registrou `dirty`, de forma transparente. Nenhum push
foi feito e nenhum commit de outro agente foi criado nesta branch.
