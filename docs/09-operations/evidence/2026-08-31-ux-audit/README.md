# Radiografia consultiva de UX — SteamZero

Data do registro: 2026-08-31. Auditoria observacional, sem alteração de código,
host, release ou instalação.

## Escopo e método

Foram percorridas a Central desktop, as áreas de Emuladores, Steam, Perfis,
Saves, Sync, Sistema, Biblioteca e Tema, além das variantes handheld, desktop e
full-HD do runner visual existente. Também foram observados os estados de mídia,
chaves/firmware, coleções, diagnóstico e o canvas do Theme Studio.

A Central real foi aberta na sessão gráfica ativa e capturada em
`01-baseline-central-window-1600x1000.png`. O runner on-screen produziu as
capturas `deck-*`, `handheld-*`, `fullhd-*`, `studio-*`, `steam-area-*`,
`emulation-area-*`, `library-*` e `overlay-*`; o inventário e a origem estão em
`MANIFEST.json`.

O AURA Launcher real foi tentado contra o catálogo canônico. Ele encerrou antes
de renderizar por ID de item inválido; a reprodução está em
`launcher-failure.txt`. A captura `02-launcher-fixture-1600x1000.png` é uma
sondagem visual isolada com três IDs temporários válidos, sem capas, e não deve
ser confundida com uma validação do launcher instalado.

O canvas em `03-theme-studio-canvas-1280x720.png` foi renderizado por um
harness QML temporário, usando os componentes do produto. Ele prova que a cena,
árvore e inspector aparecem; não prova edição direta no canvas nem desempenho
físico da release instalada.

Estado do host observado: release `2.0.0rc1-0920e785d174`, catálogo canônico com
231 jogos, 13 plataformas; `steamzero desktop status` reportou estado stale
(`docked-desktop` desejado, `handheld-desktop` aplicado); `doctor` teve apenas o
aviso de permissão para inspecionar boot direto. Não foram expostos segredos,
keys ou credenciais.

## Veredito por área

Notas são consultivas, de 1 a 10, baseadas no que foi possível experimentar.
Não equivalem a certificação WCAG, FPS ou compatibilidade de hardware.

| Área | Nota | Veredito e sensação do usuário |
|---|---:|---|
| Central/AURA UI | 7/10 | Hierarquia, cartões, estados verde/âmbar e mensagens de prontidão são bons e honestos (`fullhd-overview.png`, `fullhd-steam.png`). A Central parece produto real, mas o banner de perfil stale e os rodapés de dicas competem com o conteúdo. |
| AURA Launcher | 2/10 | O shell não abre com o catálogo real (`launcher-failure.txt`): bloqueio P0. Com fixture, foco ciano e placeholder por inicial são promissores, porém a tela fica vazia e sem contexto com poucos itens (`02-launcher-fixture-1600x1000.png`). Busca, coleções e retorno após jogo ficaram não validados. |
| Tema/runtime | 6/10 | Quatro temas aparecem de forma compreensível em `studio-themes.png` e a troca/aplicação tem affordance clara. A qualidade percebida ainda varia por superfície, com texto desabilitado e foco pedindo prova de contraste renderizado por tema. |
| Theme Studio | 4/10 | A cena realmente é desenhada pelo mesmo SceneRepeater e a árvore/inspector ajudam a entender o grafo (`03-theme-studio-canvas-1280x720.png`). Parece um inspector somente leitura: não há edição direta, handles, guias, timeline ou undo visíveis. Isso frustra quem espera um estúdio visual. |
| Mídia/metadados | 5/10 | Diretórios, acessibilidade, contagem e ações de varredura são comunicados (`emulation-area-media.png`). Não ficou visível o fluxo completo provider → plano → progresso por bytes → quota → capa aplicada; a operação recente registrou quota excedida e zero atualizações. |
| Emulação e prontidão | 7/10 | Keys/firmware, controles e estados “pronto” são legíveis (`emulation-area-keysFirmware.png`, `emulation-area-controls.png`). A matriz é técnica e densa; perfis com `0x0`/`0/0` e botões cinza podem parecer defeito. |
| Launch/return | 1/10 validado | O lançamento Switch e o retorno ao mesmo foco não puderam ser testados porque o Launcher real falhou antes da home. Não se deve inferir jogabilidade ponta a ponta a partir do estado de prontidão. |
| Big Picture | 1/10 validado | Não houve prova física do atalho no Steam Big Picture nem de voltar ao Big Picture; `shortcuts.vdf` não estava disponível e os frontends externos estavam ausentes. Este eixo permanece não validado. |
| Acessibilidade | 5/10 | Há foco visível, alvos declarados e estados honestos. Nas capturas, dicas inferiores e controles desabilitados têm baixo contraste; alto contraste, movimento reduzido, leitor de tela e gamepad literal não foram certificados em hardware. |
| Fluidez/performance percebida | 6/10 | A composição é responsiva e há LOD/placeholder, mas telas handheld cortam conteúdo sem affordance de scroll (`handheld-overview.png`, `handheld-emulation.png`) e a biblioteca sem capa vira blocos vazios (`library-games-grid.png`). O runner também emitiu avisos do KDE Breeze, sem impedir a captura. |

## O que está funcionando bem

- Mensagens de prontidão e impedimento são diretas: keys, firmware, GameMode,
  perfil e sync não fingem sucesso (`fullhd-steam.png`,
  `emulation-area-keysFirmware.png`, `fullhd-sync.png`). O usuário entende
  melhor o que está pronto e o que ainda depende dele.
- O placeholder de capa por inicial no shell temporário é honesto; não inventa
  arte (`02-launcher-fixture-1600x1000.png`).
- A tela de controles é uma das mais claras: estado pronto, padrão selecionado
  e ação alternativa estão próximos (`emulation-area-controls.png`).
- A Biblioteca tem boas variações semânticas de sistemas, grade, lista e
  carrossel. A lista é a opção mais eficiente para catálogo grande
  (`library-systems.png`, `library-games-list.png`).
- O Theme Studio não mente sobre custo: mostra orçamento declarado e “sem
  medição física” (`03-theme-studio-canvas-1280x720.png`).

## Ganhos rápidos — baixo esforço, alto impacto

1. Escurecer menos as dicas de rodapé e elevar contraste de estados disabled.
   Evidência: `deck-overview.png`, `deck-steam.png`, `library-games-list.png`.
   Ajuda porque o usuário de controle deixa de perder comandos essenciais.
2. Rebaixar o banner “Perfil do Desktop desatualizado” para um aviso compacto,
   com ação primária inequívoca. Evidência: `fullhd-overview.png` e
   `studio-profiles.png`. Ajuda porque a home volta a comunicar jogos antes de
   comunicar manutenção.
3. Trocar “Ver (somente leitura)” por uma ação explicitamente chamada
   “Abrir preview” e marcar “Duplicar e editar” como caminho de autoria.
   Evidência: `studio-themes.png`. Ajuda a alinhar expectativa com o Studio
   atualmente parcial.
4. Mostrar um contador/indicador de scroll nas áreas handheld. Evidência:
   `handheld-overview.png` e `handheld-emulation.png`. Ajuda a pessoa a saber
   que os cartões cortados continuam acessíveis.
5. Preservar a primeira letra, mas adicionar plataforma e estado em uma linha
   consistente no placeholder de capa. Evidência: `02-launcher-fixture-1600x1000.png`.
   Ajuda a reduzir ambiguidade quando várias capas faltam.
6. Nas telas de mídia, expor provider selecionado, etapa atual, bytes,
   candidatos, quota e ação de retry mesmo quando o plano é zero. Evidência:
   `emulation-area-media.png` e o histórico `media.global` degradado. Ajuda a
   transformar “varrer” em uma operação previsível.
7. Explicar a divergência de coleções: favoritos persistidos apareceram sem
   membros na coleção “Favoritos”. Ajuda a evitar que o usuário conclua que
   perdeu sua biblioteca.
8. Reservar uma área de detalhe contextual para o item focado no launcher. A
   fixture mostra o foco, mas também grande espaço morto e nenhuma confirmação
   visual de “o que acontece ao selecionar”.

## Melhorias estruturais

- Fechar o contrato de identidade entre biblioteca canônica e Launcher antes de
  qualquer polimento visual. IDs de ingestão não podem derrubar a home; deve
  existir mapeamento estável, fallback por item e erro recuperável.
- Transformar a home em uma jornada Big Picture completa: foco inicial,
  busca, coleções, detalhe, lançar, aguardar, fechar e restaurar o mesmo foco.
  Cada transição precisa de loading, erro acionável e retorno verificável.
- Evoluir o Theme Studio de inspector para autoria: selecionar no canvas,
  editar bounds/spacing/tokens, constraints, efeitos e estados; oferecer
  undo/redo, preview de resolução e acessibilidade. A árvore deve continuar
  sendo o caminho técnico, não o único caminho.
- Criar um modelo único de estados para mídia: descoberta, plano, aplicação,
  progresso, quota, parcial, retry, cancelamento e resultado por item. O
  usuário deve ver onde a capa entrou na Biblioteca/Home.
- Definir uma gramática de densidade: uma coluna de contexto, uma ação primária,
  métricas secundárias e scroll explícito. Hoje Emuladores/Sistema/Steam têm
  boa informação, mas frequentemente pedem leitura de painel técnico.
- Provar acessibilidade em pixels renderizados por tema e em controle real:
  contraste AA, foco, escala, alto contraste, movimento reduzido, Accessible
  names, gamepad literal e touch mínimo. A existência de tokens não é prova da
  experiência.

## Fricções e dores priorizadas

### P1

- **Launcher não abre com o catálogo real.** Reprodução: executar
  `steamzero-launcher` na sessão gráfica ativa com o catálogo instalado.
  Resultado: encerramento antes da UI por `ValueError` de ID inválido. Sensação:
  “a biblioteca existe, mas o produto não sabe carregá-la”. Evidência:
  `launcher-failure.txt`.
- **Jornada jogar → fechar → retornar não comprovada.** Reprodução: não é
  possível selecionar o Switch na home real porque ela não abre. Sensação:
  incerteza sobre perder contexto e foco. Resultado: não validado, não um falso
  “pass”.
- **Big Picture/atalho Steam sem prova física.** Reprodução: verificar o
  atalho no Big Picture e acionar `desktop ui`; não havia `shortcuts.vdf` nem
  frontend externo disponível no host. Sensação: o SteamZero pode parecer uma
  ferramenta desktop, não uma experiência alcançável do sofá.
- **Theme Studio promete autoria, entrega inspeção.** Reprodução: abrir Tema →
  canvas; selecionar nós na árvore. A cena aparece, mas não há edição direta.
  Sensação: “posso olhar, mas não criar”. Evidência:
  `03-theme-studio-canvas-1280x720.png`.
- **Mídia não fecha o ciclo de confiança.** Reprodução: abrir a área de capas e
  seguir a varredura; o capture mostra diretórios e ações, mas não provider,
  progresso por bytes, quota ou resultado aplicado. Sensação: “apertei varrer;
  não sei o que mudou”.

### P2

- Dicas de controle quase somem contra o fundo; a navegação parece menos
  acessível do que a hierarquia principal.
- Nomes longos de plataformas são truncados em cartões sem contexto suficiente;
  a pessoa precisa adivinhar o restante (`library-systems.png`).
- Grid sem arte produz grandes blocos vazios (`library-games-grid.png`),
  reduzindo sensação de catálogo vivo.
- A tela handheld corta o final dos cartões e não sinaliza continuação
  (`handheld-overview.png`).
- Botões cinza e métricas `0x0`/`0/0` podem parecer indisponibilidade não
  explicada, mesmo quando o estado é apenas inativo (`fullhd-emulators.png`).
- Avisos de carregamento do KDE Breeze apareceram no runner on-screen. A captura
  terminou e não há atribuição segura ao QML SteamZero; ainda assim, o sinal
  merece triagem porque degrada a percepção de acabamento.

## Bloqueios P0

1. **AURA Launcher/Big Picture indisponível com dados reais.** A falha é antes
   da renderização e impede home, busca, coleções, jogar e retorno. Este é o
   bloqueio que deve ser resolvido antes de avaliar “fluidez” do launcher.
2. **Jornada principal de console não pode ser declarada entregue.** Sem o shell
   real, não há prova de lançar Switch, fechar e restaurar foco. O estado de
   prontidão do Switch é evidência de configuração, não de jornada completa.

## Comparativo de mercado

Critério: completar a jornada sofá (abrir → encontrar → focar → lançar → voltar),
clareza de metadados e capacidade de personalização visual no primeiro contato.

| Referência | SteamZero hoje | Leitura |
|---|---|---|
| Steam Deck / Big Picture | Atrás | SteamZero tem mensagens de estado mais explícitas em várias telas, mas perde no requisito básico de launcher real, busca, retorno e controles verificados. |
| Playnite | Atrás em biblioteca/mídia; empate em gestão desktop | A Central oferece diagnóstico mais operacional; artwork, coleções e fluxo de atualização ainda não têm a previsibilidade visual de um frontend maduro. |
| LaunchBox | Atrás em onboarding e catálogo editorial | Cards e modos de biblioteca existem, mas faltam o ciclo de detalhe/ação/resultado e a resiliência do catálogo real. |
| ES-DE | Atrás na experiência de sofá; à frente na honestidade operacional | Placeholder e matriz de prontidão são honestos, porém o launcher não suporta hoje a comparação básica de abrir, navegar e lançar. |
| PS5 UI / referência premium | Atrás em foco, densidade e continuidade | A Central tem hierarquia promissora; rodapés pouco legíveis, telas cortadas e ausência de transições comprovadas deixam a sensação menos polida. |

## Recomendação consultiva final

Mudar primeiro a percepção de confiança, não a decoração: fazer o AURA Launcher
abrir de forma resiliente com o catálogo real, mostrar imediatamente foco, busca,
coleções, detalhe, loading e retorno; em seguida fechar o ciclo de mídia com
progresso e resultado observáveis. Só depois investir em efeitos e “premium feel”.

Na mesma onda, tratar o Theme Studio como uma promessa de autoria: manter árvore e
inspector, mas entregar uma primeira edição direta pequena e verificável (por
exemplo, espaçamento, cor e estado focado) com undo/redo e preview por resolução.
Por fim, fazer uma passada de acessibilidade renderizada — rodapés, disabled,
foco, escala e controle físico — e reduzir a densidade técnica com contexto e
scroll explícitos.

O produto já tem uma base valiosa: estados honestos, uma Central visualmente
coerente e uma engine declarativa que consegue renderizar a cena real. O salto
para amigável, fluido e moderno depende de conectar esses bons fundamentos à
jornada que um usuário realmente tenta completar.
