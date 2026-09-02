# Auditoria funcional e de experiência — matriz consolidada

Data da consolidação: 2026-09-02  
Base visual: captura fornecida pelo operador e reauditoria da release ativa registrada em `README.md`.  
Base técnica: testes focados de contexto de plataforma, read model de armazenamento e gestão transacional.

## Veredito

O produto tem contratos de domínio suficientes para continuar a jornada, mas a
experiência apresentada ainda não é certificável como central de jogos. O
problema dominante não é falta de decoração: é a quebra da relação entre
contexto selecionado, ação disponível, resultado observado e recuperação.

O backend agora separa jogos por plataforma no contexto do Switch e publica
atalhos transacionais para mover uma raiz, converter uma ROM e gerir runtime.
Isso não equivale à entrega visual: o frontend proprietário ainda precisa
fornecer o destino do movimento, esconder requisitos que não pertencem à
plataforma, mostrar progresso e corrigir navegação, contraste e foco.

## Matriz de achados

| ID | Área | Severidade | Observação e evidência | Estado | Critério de aceite |
|---|---|---:|---|---|---|
| UX-01 | Emulação / emuladores | P0 | A área mostra `100%` e, ao mesmo tempo, `Nenhum emulador definido`; a captura indica ROMs/core presentes, mas não há destino operacional coerente. A navegação deve responder pelo contexto da plataforma, não por um contador genérico. | Backend publica a composição por plataforma; lançamento físico e UI continuam abertos. | Para cada plataforma com ROM reconhecida, pelo menos um runtime compatível aparece com estado, origem, versão e ação de escolher/instalar; `100%` só aparece quando todos os pré-requisitos reais estão satisfeitos. |
| UX-02 | Saves e migração | P0 | A lista de saves do Switch mistura títulos de outras plataformas. Isso destrói confiança e torna perigosa uma migração. | Corrigido no backend: jogos, saves e mídia da área Switch usam identidade de plataforma exata; falta prova na release. | Biblioteca mista mantém cada save exclusivamente no seu contexto; o job e o resultado informam `platformId`; nenhum título estrangeiro aparece no card. |
| UX-03 | Keys/Firmware | P0 | Keys e Firmware aparecem como cards universais, inclusive onde a plataforma não declara esses requisitos. | Backend/composição preservam requisitos declarados; remoção do fallback visual pertence ao QML compartilhado. | A área genérica só mostra cards de requisitos presentes no manifesto; ausência de requisito não vira erro nem convite para importar arquivo irrelevante. |
| UX-04 | Armazenamento / estatísticas | P1 | A captura apresenta armazenamento compartilhado como `0 registro(s)` sem bytes por ROM, emulador, save, mídia, cache, espaço livre ou volume. | Read model publicado com buckets, bytes, arquivos, estado do volume e ações existentes. | Visão geral mostra total usado/livre e drill-down por categoria, com diretório, quantidade, bytes, estado e última leitura; erro de permissão ou diretório ausente é explícito. |
| UX-05 | Armazenamento / gestão | P1 | Não havia movimento de diretório, limpeza orientada, desinstalação contextual ou atalho claro para compactar ROMs. | Backend agora planeja movimento com precondições, rollback, configuração de raízes; NSZ e desinstalação aparecem como ações de card. | Usuário escolhe destino, vê conflito/bytes/arquivos, confirma uma operação reversível e recebe resultado; ROM original só é removida mediante ação explícita. |
| UX-06 | Armazenamento / interação | P1 | A API já aceita `path` como destino do plano, mas a captura não oferece seletor visual. Também falta compactação em lote e resumo de espaço recuperável. | Gap `GAP-STORAGE-MOVE-UI-DESTINATION` e `GAP-STORAGE-BATCH-COMPRESSION`. | Seletor de diretório com validação de árvore, espaço disponível, colisões e cancelamento; seleção por item/lote com estimativa antes de aplicar. |
| UX-07 | Rollback / operação longa | P0 | O modal tem grande área vazia, mostra `0 bytes` e não apresenta fases, duração estimada, arquivos em processamento ou progresso quando a operação é síncrona. | Pipeline transacional fornece preview, token, operação e jobs para ações longas; composição visual/progresso segue aberta. | Preview responde “o quê/onde/quanto/risco”; apply mostra fase, `atual/total` ou bytes reais, cancelar quando seguro, sucesso/erro e recuperação; o modal não fecha deixando operação órfã. |
| UX-08 | Mídia / organização | P1 | A tela é densa: diretórios duplicados, cards de ROM com muitos botões truncados, estados e estatísticas espalhados. | Escopo de plataforma foi corrigido no backend; hierarquia visual e layout QML continuam na frente compartilhada. | Separar “fontes”, “pipeline” e “biblioteca”; uma tabela/resumo por fonte e uma fila de pendências; ações secundárias em menu contextual sem truncamento. |
| UX-09 | Mídia / atualizar e verificar | P0 | Clicar em verificar não deixa claro se é auditoria, scraping ou publicação; o operador não consegue saber quais jogos serão atualizados. A captura não prova atualização para todas as ROMs do sistema. | Jobs globais carregam escopo de plataforma e filtram o conjunto; falta tornar escopo, denominador e resultado visíveis. | Antes de aplicar: “231 jogos do sistema X, 178 com mídia pendente”; durante: `jogo atual/total`; depois: atualizados, ignorados, falhos e motivo, com retry individual. |
| UX-10 | Assets únicos / filtros | P1 | Os filtros de imagem não demonstram aplicação às receitas de assets únicos do tema; há risco de editar derivados em vez de renderizar a partir da fonte. | Theme Engine possui receita declarativa e cache por hash/tier; aplicação física dos filtros nesta jornada não foi provada. | Preview de cada filtro muda o asset-fonte em runtime, preserva a receita, mostra tier/cache e exporta o mesmo resultado sem gerar coleção de derivados pré-editados. |
| UX-11 | Temas / launcher | P1 | Não há entrada evidente para um launcher de temas. A listagem de temas e o editor aparecem como capacidades separadas, sem explicar “aplicar”, “em uso” e “visualizar”. | Capacidades AURA Launcher, Theme Engine e Theme Studio estão separadas por contrato; a navegação integrada ainda é gap. | Temas tem uma rota única com instalar/importar, aplicar, em uso, duplicar/editar, exportar e remover; o launcher é identificado como superfície própria, não inferido da central. |
| UX-12 | Temas / importação | P1 | Não foi localizado botão visível de importar temas de ES-DE, RetroFE ou formatos equivalentes. | Contratos de importação existem para ES-DE; a rota visual e teste físico seguem abertos. | Botão Importar abre escolha de formato, faz inspect/preview, mostra incompatibilidades/licença, pede confirmação e permite reabrir o tema semanticamente igual. |
| UX-13 | Theme Studio / autoria | P1 | O editor observado oferece “ver somente leitura” e “duplicar e editar”, mas ações truncam e a superfície não comunica canvas, árvore, inspector, constraints, efeitos e timeline. | Contratos/canvas possuem testes; evidência física aponta truncamento e experiência incompleta. | Ações cabem em viewport handheld/desktop, têm foco e Accessible.name; o editor mostra seleção, propriedades, preview responsivo, acessibilidade e orçamento de performance. |
| UX-14 | Sistema / diagnóstico | P1 | A tela lista muitas verificações em sequência, com informação corrida e pouca priorização para recuperação; `jobs.stale` aparece como aviso sem ação contextual. | Diagnóstico fornece checks; layout e recuperação orientada continuam abertos. | Separar “estado atual”, “problemas que exigem ação” e “histórico”; cada aviso tem causa, impacto, ação segura, progresso e resultado verificável. |
| UX-15 | Shell / contraste e densidade | P1 | Banner de perfil desatualizado, botões escuros/desabilitados e rodapé de dicas têm contraste fraco; textos e labels são truncados. | Parte coberta pelos gates de UI, mas a captura da release ainda reprova a leitura em contexto real. | Contraste medido por tema, foco visível, targets mínimos, elide só quando há tooltip/detalhe e nenhum estado crítico depende apenas de cor. |
| UX-16 | Navegação / ação | P0 | Na reauditoria live, Return, clique e teclas testadas não ativaram o cartão do Launcher; tela e hash permaneceram iguais, sem processo de emulador. | Gap `GAP-UI-LIVE-LAUNCHER-ROUTING`; correção está na frente proprietária do Launcher/QML. | Return, Enter, Space, controle e clique acessível abrem uma única página de jogo, lançam o runtime correto, devolvem ao mesmo foco e deixam o estado do host íntegro. |

## Ordem recomendada de correção

1. Fechar UX-01, UX-03 e UX-16: sem destino de execução e navegação confiável,
   nenhuma estatística ou animação torna o produto jogável.
2. Fechar UX-07 e UX-09: operações destrutivas ou longas precisam explicar
   escopo, progresso e recuperação antes de receber mais capacidades.
3. Entregar UX-04 a UX-06 e UX-08: tornar armazenamento e mídia úteis para
   manutenção diária, mantendo a separação por plataforma.
4. Entregar UX-11 a UX-13 e UX-10: integrar importação, autoria, aplicação e
   renderização de temas sem misturar as quatro superfícies AURA.
5. Fechar UX-14 e UX-15 com captura na release instalada e repetir a matriz
   física por plataforma.

## Limites da execução atual

Foram executados testes focados de isolamento de plataforma e gestão de
armazenamento, além dos gates estáticos do repositório. A suíte completa foi
tentada com `TMPDIR=/tmp`, permaneceu sem saída em 17% e foi interrompida após
repetição do mesmo comportamento; não restaram processos de pytest nem socket
`core.sock`. Não houve instalação, publicação, rollback de host, push ou
lançamento físico nesta sessão.

