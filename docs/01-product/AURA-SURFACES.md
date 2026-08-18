# AURA-SURFACES — contrato de nomenclatura do produto

## Regra obrigatória

“AURA” sozinho é ambíguo e não deve ser usado em status, roadmap, relatório de
release ou evidência. Toda afirmação precisa nomear uma destas capacidades:

| Nome | O que é | Prova mínima | O que não prova |
|---|---|---|---|
| **AURA UI** | Sistema visual da central SteamZero: tema, tokens, componentes, foco, contraste, escala e preview | central real renderizada com o tema aplicado, versão ativa e navegação observada | existência de home fullscreen, biblioteca console-like ou ciclo de lançamento |
| **AURA Launcher** | Produto fullscreen de biblioteca e lançamento por controle, comparável em categoria a Big Picture, ES-DE, RetroFE ou BigBox | home e biblioteca reais, página de jogo, lançamento, jogo ativo e retorno ao launcher, com captura da release instalada | conclusão da central administrativa, editor de temas ou adapters externos |
| **Theme Engine** | Runtime declarativo de cenas, layouts, assets, bindings, efeitos e animações GPU-first | uma cena externa válida renderizada em múltiplas resoluções; variantes derivadas de um único asset; fallback e orçamento medidos | existência de editor visual ou conclusão do Launcher |
| **Theme Studio** | Ferramenta visual de autoria, preview, timeline, validação e empacotamento | criar, editar, visualizar, exportar, importar e reabrir um tema sem perda e sem editor de imagens externo | completude da engine, certificação do Launcher ou marketplace remoto |

## Fronteiras

- AURA UI pode ser consumida pela central Desktop e pelo AURA Launcher.
- AURA Launcher não é “um tema”: possui shell, navegação, estado de biblioteca,
  busca, coleções, página de jogo, ciclo launch/return e recuperação próprios.
- Theme Engine é infraestrutura compartilhada. Seu estado é parcial enquanto
  apenas tokens, cenas ou efeitos isolados existirem.
- Theme Studio é mais amplo que o editor atual de tokens. Exige canvas, árvore da
  cena, inspector, grafo de efeitos, timeline, preview responsivo e validadores.
- A central SteamZero atual continua sendo **AURA UI**, mesmo quando aberta em
  tela cheia ou publicada como atalho no Steam.
- Abrir a central pelo Big Picture não a transforma no AURA Launcher.
- Integrações Steam/SRM/ES-DE/RetroFE são frontends/adapters independentes; sua
  existência também não implementa o AURA Launcher.

## Linguagem permitida em reportes

- “AURA UI instalada; validação visual pendente.”
- “AURA Launcher planejado; nenhum artefato instalado.”
- “AURA Launcher certificado na release X pelo ciclo físico Y.”

São proibidas alegações como “AURA está pronta” ou “tema AURA prova o launcher”.

A especificação integral da plataforma criativa está em
[THEME-ENGINE-AND-STUDIO](THEME-ENGINE-AND-STUDIO.md).

## Definition of Done do AURA Launcher

1. baseline físico e wireflow aprovados;
2. home fullscreen, biblioteca, busca/coleções e página de jogo implementadas;
3. navegação integral por controle, toque opcional e foco sem becos;
4. lançamento de jogo real e retorno ao mesmo contexto do launcher;
5. processo do launcher reiniciável sem derrubar o jogo;
6. estados vazio, offline, carregando, erro e recuperação acionáveis;
7. testes focados, gates integrais e ciclo instalado idempotente;
8. evidência PNG da home, página de jogo e retorno, ligada à versão ativa;
9. status `installed` somente após instalação real e `certified` somente após
   hardware, vídeo, áudio, controles, jogo e retorno aprovados.
