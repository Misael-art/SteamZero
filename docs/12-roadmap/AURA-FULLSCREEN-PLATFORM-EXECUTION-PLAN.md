# AURA Fullscreen e Plataforma — parecer e plano de execução

**Data:** 2026-09-08  
**Estado:** plano aprovado para decomposição; nenhuma implementação nova é declarada por este documento  
**Item de governança:** SZ-AURA-PLATFORM-EXECUTION-PLAN

## 1. Parecer registrado

O SteamZero possui uma fundação de plataforma acima da média: núcleo transacional,
jobs persistentes, rollback, diagnóstico, adapters, biblioteca canônica em evolução,
Theme Engine declarativa e uma fatia funcional do AURA Launcher. A release atual,
porém, ainda é uma RC técnica/beta interna. A experiência de consumidor não está no
nível do Big Picture, PS5, Xbox ou Nintendo Switch porque a integração física,
artwork, onboarding, operações longas e acabamento visual ainda são incompletos.

O investimento recomendado não é ampliar indiscriminadamente a lista de emuladores.
É transformar o que já existe em uma jornada coerente:

    ligar → descobrir biblioteca → corrigir requisitos → escolher jogo → jogar
          → pausar/retomar → salvar → voltar ao mesmo foco → manter tudo recuperável

O produto deve ser posicionado como uma plataforma Linux/Steam Deck segura,
reversível e console-like para jogos e emulação. A promessa visual será forte, mas
subordinada a três invariantes: não bloquear o usuário quando a arte falhar, não
falsificar estado e não sacrificar desempenho/controle por efeitos.

O estado vigente consultado para este plano registra 15 itens completos, 36 parciais
e 5 planejados; 17 sem verificação suficiente, 19 degradados e 31 ainda não
empacotados. Esses números são o baseline de planejamento, não uma aprovação de
release.

## 2. Decisão visual do produto

### 2.1 Tema default: AURA Cinema

O tema default fullscreen será uma implementação independente inspirada nos
conceitos visuais compartilhados pelo Aura original, RetroFE e BigBox:

- arte do jogo como protagonista;
- fanart de fundo em baixa opacidade e blur;
- capa central ou dominante, com vizinhos reduzidos;
- navegação horizontal com destaque seletivo;
- metadados discretos em área secundária;
- paleta derivada da arte selecionada;
- neutros escuros e acentos adaptativos;
- transições suaves, curtas e reversíveis;
- sensação cinematográfica sem excesso de ornamentos;
- modo sem arte que continua legível e jogável.

O resultado não copiará código, assets, layout proprietário, marca, XML específico
ou pacote de terceiros. Será um tema SteamZero baseado no scene graph e nas receitas
declarativas próprias. A referência estética é uma direção, não uma dependência
operacional.

### 2.2 Composição do AURA Cinema

| Região | Conteúdo | Fallback obrigatório |
|---|---|---|
| Fundo | fanart blur, vignette e cor extraída | fundo sólido por tier e tema seguro |
| Centro | cover, logo derivado e foco | ícone de sistema + título |
| Laterais | capas adjacentes com escala/opacidade/blur | cards tipográficos |
| Rodapé | ano, gênero, jogadores, rating, playtime | somente campos disponíveis |
| Cabeçalho | marca, coleção, relógio e estado de conexão | cabeçalho estático mínimo |
| Detalhe | screenshots, descrição, ações e requisitos | página textual navegável |
| Overlay | pause, saves, controles, manual e estado | menu sem mídia e sem processo auxiliar |

### 2.3 Tiers de renderização

- low: sem vídeo, sem glass pesado, sem partículas, blur reduzido, imagens
  pré-dimensionadas e foco de alta legibilidade.
- balanced: blur, paleta dinâmica, parallax leve, transições e screenshots.
- cinematic: efeitos avançados allowlisted, vídeo quando medido, reflexo e
  composição multicamada.

O tema nunca poderá deixar o usuário sem foco, sem ação de retorno ou em tela preta.
reducedMotion, highContrast, escala de texto e falha do backend prevalecem sobre
qualquer escolha estética.

## 3. Escopo consolidado por capacidade

| ID | Capacidade | Prioridade | Entrega mínima | Dependências |
|---|---|---:|---|---|
| AURA-01 | Shell fullscreen e navegação | P0 | home, coleções, busca, página, foco, launch/return | biblioteca canônica, input |
| AURA-02 | Metadados canônicos e import/export | P0 | schema, proveniência, ES-DE, RetroFE, Pegasus, LaunchBox, Playnite, Steam e RetroArch | biblioteca |
| AURA-03 | Pipeline de imagem | P0 | ingestão, crop, escala, cache, JPEG/PNG/WebP/SVG seguro | metadados, Theme Engine |
| AURA-04 | Effect graph e movimento | P1 | blur, cor, máscara, sombra, transições e tiers | pipeline, performance |
| AURA-05 | Paleta, glass e composição Aura | P1 | cor dinâmica, fanart blur, highlight, cover flow e fallback | AURA-03/04 |
| AURA-06 | Biblioteca automatizada | P0 | watcher, scan, integridade, dedupe, conversão e fila | metadados, jobs |
| AURA-07 | Hardware e perfis | P1 | GPU/RAM/display/input, handheld/desktop/dock e presets | diagnóstico, lifecycle |
| AURA-08 | BIOS, firmware e keys | P0 | requirements por plataforma, hash, região, orientação e estado visual | manifests, biblioteca |
| AURA-09 | Lifecycle e shadPS4 | P1 | install/update/verify/rollback e inclusão governada do PS4 | manifests, supply chain |
| AURA-10 | Enhancement registry | P1 | IDs, registry curado, dry-run, apply/revert e filtro anti-cheat | AURA-02, adapters |
| AURA-11 | Pause menu e OSD | P0 | pausa, volume, screenshot, save/load, controles e retorno seguro | sessão, input |
| AURA-12 | Saves e save-state gallery | P0 | thumbnail, timestamp, playtime, slots, backup e restauração | adapters de sessão |
| AURA-13 | Cards, fade, bezels e multi-game | P1 | cards de instrução, fade, overlays, discos e manuais | pause, mídia |
| AURA-14 | Marquee e multi-monitor | P2 | display secundário seguro e degradável | display context |
| AURA-15 | Notificações e emergência | P1 | toasts, hotkeys globais, kill seguro e Central de Controle | daemon, sessão |
| AURA-16 | Sync, achievements e netplay | P2 | providers opcionais, offline-first, consentimento e conflito | saves, rede |
| AURA-17 | Theme Studio | P1 | canvas, árvore, inspector, efeitos, timeline, validação e pacote | Theme Engine |
| AURA-18 | Desempenho e certificação | P0 | FPS, frame time, VRAM, startup, input latency e evidência física | todas as superfícies |

## 4. Modelo canônico de dados

O SteamZero deve manter um modelo interno único e adapters de importação/exportação.
Nenhum formato externo deve virar o modelo dominante.

### 4.1 Entidade GameRecord

Campos básicos:

- id estável do SteamZero, title, sortTitle e aliases;
- platformId, systemId, family, region e language;
- path, container, discSet, size e hashes;
- developer, publisher, releaseDate, genres, series e franchise;
- description, rating, ageRating, players e features;
- media com cover, fanart, screenshot, marquee, video e ícones;
- runtime, core, launchProfile e emulatorId;
- biosRequirements, firmwareRequirements e keyRequirements;
- controlsProfile, enhancementProfile, mods e texturePacks;
- saves, saveStates, playtime, lastPlayed, favorites e collections;
- provenance, confidence, warnings, availability e updatedAt.

Cada campo terá origem, timestamp, confiança e política de conflito. O importador não
pode apagar informação mais rica por causa de um formato mais pobre.

### 4.2 Adapters de metadados

| Fonte | Entrada principal | Saída |
|---|---|---|
| ES-DE/EmulationStation | gamelist.xml | GameRecord + media |
| RetroFE | meta.txt/XML | GameRecord + coleção |
| Pegasus | metadata.pegasus.txt | GameRecord |
| LaunchBox | XML/Data Storage | GameRecord + launch profile |
| Playnite | JSON/SQLite export | GameRecord |
| Steam | AppManifest/shortcuts | GameRecord nativo ou shortcut |
| RetroArch | playlists .lpl | GameRecord + core |

Exportação será opcional, idempotente e sempre precedida por plan/preview/backup.

## 5. Plano de ondas

### Onda 0 — contrato, governança e protótipo visual

1. Congelar o baseline do projeto e separar AURA UI, AURA Launcher, Theme Engine e
   Theme Studio.
2. Criar fixtures sintéticas com jogos, arte ausente, múltiplos discos, erro de
   BIOS, save conflitante e operação longa.
3. Definir GameRecord, media roles, IDs e provenance.
4. Criar wireframe navegável do AURA Cinema em 1280×800, 1920×1080 e 2560×1080.
5. Aprovar budget: startup até 2 s com cache quente, 60 FPS em 1280×800, p95 de
   frame time até 16,7 ms e VRAM até 512 MB no tier balanceado.

### Onda 1 — biblioteca e metadados

1. Implementar o modelo canônico e os importadores.
2. Fazer watcher opcional em inbox, nunca em toda a biblioteca sem consentimento.
3. Executar scan read-only, hash incremental, CRC/SHA1 quando DAT licenciado estiver
   disponível e estado unknown quando não houver fonte.
4. Gerar plano de organização, deduplicação e conversão.
5. Aplicar somente após confirmação, com staging, rollback e preservação original.
6. Atualizar a biblioteca canônica e playlists sem duplicação.

### Onda 2 — Theme Engine e AURA Cinema

1. Pipeline de imagem seguro e cache por digest/recipe/tier.
2. Paleta dinâmica, fanart blur, capa central, vizinhos, metadata rail e foco.
3. Efeitos allowlisted: blur, cor, sombra, glow, máscara, vignette, parallax leve.
4. Transições com interrupção/reversão e reducedMotion.
5. Fallback de ausência de arte, vídeo, GPU ou plugin Qt.
6. Integrar o shell fullscreen somente depois de o contrato estar estável.

### Onda 3 — hardware, requisitos e lifecycle

1. Detectar GPU, RAM, tela, escala, orientação, handheld/dock/desktop e input.
2. Gerar presets recomendados, sempre com diff e confirmação.
3. Expandir o store de BIOS/firmware/keys por manifesto.
4. Adicionar shadPS4 apenas com manifesto, origem, checksum, licença, executor,
   verify, rollback e prova de compatibilidade.
5. Validar todos os estados visualmente: pronto, ausente, incompatível,
   permissionDenied, unknown, degraded e recovery.

### Onda 4 — enhancements por jogo

1. Criar resolver de identificadores por plataforma.
2. Criar registry versionado e assinado ou com checksum verificável.
3. Permitir somente performance, compatibilidade e qualidade visual.
4. Rejeitar cheats de gameplay por parser e política, não apenas por convenção.
5. Aplicar configuração por jogo em staging, gerar diff e permitir revert.
6. Começar por DuckStation, Dolphin e PCSX2; depois RPCS3 e Cemu; shadPS4 fica
   separado até seu contrato ser conhecido.

### Onda 5 — experiência dentro do jogo

1. Pause menu como adapter de sessão, não como código específico de tema.
2. OSD de volume, screenshot, save/load, fast-forward, controle, rede e achievement.
3. Save-state gallery com thumbnail real, timestamp, playtime e compatibilidade.
4. Cards de instrução, controles e manuais sem bloquear o jogo em caso de erro.
5. Fade de entrada e retorno com estado real, nunca progresso inventado.
6. Bezels/overlays por sistema/jogo com proporção preservada.
7. Multi-disc e troca de cartucho por contrato do adapter.

### Onda 6 — integração e produto

1. Notificações amigáveis e Central de Controle.
2. Perfis handheld/desktop/dock.
3. Hotkeys globais com allowlist, confirmação e recuperação.
4. Sync local/cloud opcional, achievements e netplay apenas como providers.
5. Theme Studio completo.
6. Certificação física por cenário e publicação apenas após todos os P0.

## 6. Divisão multiagente

### Regras de paralelização

- Cada agente cria sua própria branch codex/... a partir da base indicada.
- Cada agente registra um workstream e um item de status antes de editar.
- Caminhos exclusivos não podem se sobrepor.
- Main.qml, desktop_dashboard.py, desktop_contracts.py, contratos centrais
  e manifests compartilhados ficam sob custódia do agente integrador.
- Agentes de domínio entregam contratos, fixtures e testes; não alteram o shell
  compartilhado para mostrar a capacidade.
- Nenhum agente instala no host, publica release ou faz push sem autorização
  explícita da sessão.
- Cada entrega termina com os cinco gates do projeto e evidência proporcional.

### Agentes e escopos

| Agente | Frente | Escopo exclusivo principal | Pode iniciar |
|---|---|---|---|
| A0 | Product/contract lead | plano, ADRs, fixtures, matriz e status | imediatamente |
| A1 | Canonical metadata | domain/library, schemas e adapters de import/export | após A0 |
| A2 | Image pipeline | theme_assets, cache, codecs e recipes | após A0 |
| A3 | Effects/motion | theme_effects, scene motion e render contracts | após A2 |
| A4 | AURA Cinema shell | ui/qml/launcher e testes próprios | após A1/A3 |
| A5 | Library operations | watcher, dedupe, converter, jobs e planos | após A1 |
| A6 | Hardware/profiles | probe de hardware, contexto e presets | após A0 |
| A7 | BIOS/keys/firmware | manifests, validator e stores | após A1 |
| A8 | Lifecycle/shadPS4 | manifesto, executor, lock e rollback | após A0 |
| A9 | Enhancement registry | registry, ID resolver, policy e aplicação | após A1/A8 |
| A10 | Session/Pause/OSD | sessão, overlay, input semântico e save-state contract | após A1 |
| A11 | Media/cards/fade | cards, manuais, bezels, multi-game e fade | após A10 |
| A12 | Studio | canvas, inspector, graph, timeline e package | após A2/A3 |
| A13 | Providers | notificações, sync, achievements e netplay | após A10 |
| A14 | Integration/QA | integração do shell, performance, hardware e release evidence | por último |

## 7. Prompts estruturados para os agentes

Todos os prompts abaixo começam com as regras de AGENTS.md. O coordenador deve
substituir BASE pelo commit atual aprovado e registrar o workstream antes de
disparar o agente.

### PROMPT A0 — Product/Contract Lead

Você é o agente A0 do SteamZero. Leia AGENTS.md, ACTIVE-WORK, STATUS, AURA-SURFACES,
THEME-ENGINE-AND-STUDIO e a auditoria UX atual. Transforme a especificação anexada
em contratos implementáveis sem ampliar silenciosamente o escopo.

Entregue:
1. ADR do AURA Cinema com inspiração, independência, licença, tiers, fallback e
   budget de desempenho.
2. Schema de GameRecord, MediaRole, Provenance e EnhancementEntry.
3. Fixtures para arte ausente, conflito, multi-disc, BIOS ausente, save-state e
   operação interrompida.
4. Matriz de dependências AURA-01..AURA-18 e critérios P0/P1/P2.
5. Atualização do status sem declarar capacidade implementada.

Não edite o shell QML nem o daemon. Prove com testes de schema, compatibilidade,
migração e limites. Rode ruff, format-check, mypy, boundaries, independence e
testes isolados. Não faça build de release, instalação ou push.

### PROMPT A1 — Biblioteca canônica e metadados

Você é o agente A1. Implemente o modelo canônico e adapters de ES-DE, RetroFE,
Pegasus, LaunchBox, Playnite, Steam e RetroArch.

Escopo exclusivo: domain/library, schemas novos, adapters próprios e testes.
Não edite Main.qml, desktop_dashboard.py ou o shell do Launcher.

Preserve campos ricos e provenance/confidence; normalize data, rating, jogadores,
gênero, série, região e idioma; mantenha platformId, runtime, core, launchProfile,
media e requirements. Conflitos geram estado explícito. Import/export é idempotente,
seguro contra traversal/symlink e não apaga metadado interno.

Entregue parser, normalizer, export plan/apply/verify quando aplicável, testes
positivos/negativos e nota de compatibilidade. Não faça scraping real.

### PROMPT A2 — Image Pipeline

Você é o agente A2. Implemente o pipeline declarativo de imagens.

Escopo exclusivo: theme_assets, recipes, cache, limites e testes. Não edite o shell.

Suporte inicial seguro: PNG, JPEG, WebP e SVG sanitizado; registre formatos futuros
como planned se o backend não os consumir. Implemente aspect-ratio lock, crop
determinístico, filtros, cache LRU por digest/recipe/tier, mipmap/atlas somente
quando medidos. Toda derivação aponta para um asset-fonte e receita.

Rejeite SVG com script, eventos, foreignObject, URL externa, path absoluto ou payload
excessivo. Prove cache, limites, fallback e geração de cover, silhouette, outline e
variações de cor sem alterar o original. Não alegue GPU/FPS sem hardware.

### PROMPT A3 — Effects, palette e motion

Você é o agente A3. Implemente cor, efeitos e movimento declarativos.

Escopo exclusivo: theme_effects, dynamic palette, glass panels, scene motion,
allowlist e testes. Não edite Main.qml nem o launcher final.

Priorize blur, grayscale, sepia, invert, hue/saturation/brightness/contrast,
duotone, matrix 4x5, shadow, glow, stroke, mask, vignette, parallax leve,
crossfade, dissolve, wipe e cover-flow offset. Cada efeito precisa de tier, limite,
fallback e reducedMotion. Interrupção preserva estado e permite reversão.

Palette produz primary, secondary, tertiary, accent, background e text com contraste
validável. Glass degrada para painel opaco. Entregue testes de determinismo,
acessibilidade e fallback. Harness offscreen não prova performance física.

### PROMPT A4 — AURA Cinema Launcher

Você é o agente A4. Construa o fullscreen default AURA Cinema.

Escopo exclusivo: ui/qml/launcher, modelos específicos e tests/qml/launcher.
Não toque Main.qml, desktop_dashboard.py ou Theme Studio.

Implemente home por coleções, busca, rail/cover-flow, jogo selecionado, página de
jogo, ações, retorno e estados loading/empty/offline/error. Fanart blur ocupa fundo,
capa central recebe highlight, vizinhos têm escala/opacidade/blur e metadata só
aparece quando disponível.

Entrada obrigatória: teclado, D-pad, Enter, Return, Space, toque/clique acessível.
Não use forceActiveFocus ou mouse sintético nos harnesses. Foco inicial deve existir
na cena real; duplo disparo e retorno órfão são proibidos. Inclua sem arte, high
contrast, reduced motion, visualScale e 1280x800/1920x1080/ultrawide.

### PROMPT A5 — Biblioteca automatizada

Você é o agente A5. Implemente ingestão e manutenção segura da biblioteca.

Escopo exclusivo: watcher/inbox, scanner, hashing, DAT adapters, dedupe, converter,
jobs e planos. Não edite o shell.

Watcher é opt-in e limitado a raízes escolhidas. Scan é read-only. Sem DAT confiável,
integridade vira unknown. Dedupe mostra candidatos e preferências antes de aplicar.
CHD/RVZ/CSO/NSZ exigem staging, espaço reservado, timeout, original preservado e
rollback. Playlists só são atualizadas após verify.

Cubra kill, ENOSPC, parcial, symlink, volume removido, cancelamento e reexecução.
Use fixtures; não opere uma biblioteca real.

### PROMPT A6 — Hardware e perfis

Você é o agente A6. Implemente detecção read-only de GPU, RAM, display, escala,
orientação, input e contexto handheld/desktop/dock.

Escopo exclusivo: probes, capability models, profile planner, fixtures e testes.
Não aplique sysctl, clock, TDP, compositor ou configuração de terceiros.

O planner produz contexto, recomendação, diff, risco e ação reversível. AMD/NVIDIA/
Intel, Vulkan/OpenGL, tela interna/externa e Steam Deck devem ter unknown e
permissionDenied. Presets só serão consumidos depois do contrato de lifecycle.

Prove docking/undocking, monitor ausente, permissão negada e input parcial.
Falha de probe deve degradar para preset seguro.

### PROMPT A7 — BIOS, firmware e keys

Você é o agente A7. Implemente o validador visual e transacional de requisitos.

Escopo exclusivo: catalogs, manifest requirements, hashes, região, compatibilidade,
guidance e testes.

Cada plataforma declara exatamente o que precisa. Não publique cards universais.
Estados: valid, missing, wrongHash, wrongRegion, incompatible, permissionDenied e
unknown. Não baixe material protegido nem exponha segredos em log ou screenshot.
Links são allowlisted e toda ação tem orientação segura.

Prove plataformas, migração, hash e fallback. Não altere arquivos do usuário sem
plano, ownership e confirmação.

### PROMPT A8 — Lifecycle e shadPS4

Você é o agente A8. Avalie e, se houver contrato suficiente, implemente a inclusão
governada do shadPS4.

Escopo exclusivo: manifestos, lockfile, source adapters, executor, verify, rollback,
recovery e testes.

Antes de código, produza análise de fonte, licença, distribuição, identificador,
versão, checksum, dependências e riscos. Não use “jogos jogáveis” como promessa.
Se um dado não puder ser provado, mantenha planned/degraded.

O ciclo precisa de plan/confirm/apply/verify/rollback, operação persistente,
cancelamento, recuperação e preservação de dados. Não use latest sem pin/digest.
Prove no harness/VM; host real exige autorização.

### PROMPT A9 — Enhancement Registry

Você é o agente A9. Implemente a engine de melhorias por jogo.

Escopo exclusivo: registry schema, ID resolvers, verificação de fonte, policy,
appliers e testes. Não edite UI.

Comece por DuckStation, Dolphin e PCSX2; depois RPCS3 e Cemu. Cada entrada relaciona
platformId, serial/titleId/GameID/CRC, versão do emulador, fonte, checksum, licença,
categoria, settings, incompatibilidades e rollback.

Categorias permitidas: performance, compatibility, quality e accessibility. Cheats
de gameplay são rejeitados por parser e allowlist. Patches RPCS3, graphic packs Cemu,
profiles DuckStation, pnach PCSX2 e GameINI Dolphin usam staging, diff e revert.

Entregue CLI dry-run e missing-only e testes de parser, anti-cheat, versão, região,
rollback e falha de rede. Não faça download real nem modifique emuladores do host.

### PROMPT A10 — Pause, OSD, sessão e saves

Você é o agente A10. Implemente o contrato de sessão para Pause Menu, OSD e saves.

Escopo exclusivo: session adapters, semantic actions, overlay protocol, save-state
model e testes. Não crie um segundo gerenciador no QML.

Pause abre por hotkey, preserva o processo, mostra ações allowlisted e retorna ao
mesmo foco. OSD cobre volume, mute, screenshot, pause, fast-forward, rewind,
controller, rede e achievement. Save-state gallery mostra slot, thumbnail real,
timestamp, playtime, compatibilidade e fallback.

Save/load exige confirmação segura, erro visível e nunca falsifica sucesso. A
capacidade varia por adapter. Cubra crash, timeout, estado ausente e retorno.

### PROMPT A11 — Cards, fade, bezels e multi-game

Você é o agente A11. Implemente recursos visuais dentro do jogo como adapters
declarativos e degradáveis.

Escopo exclusivo: instruction cards, manuals/guides, fade, bezels/overlays,
multi-disc/cartridge e testes.

Cards mostram controles do jogo atual. Manuais aceitam fontes locais/permitidas e
não bloqueiam a sessão. Fade usa estado real de launch/session, sem progresso
inventado. Bezels preservam aspect ratio e têm tiers. Multi-game só aparece quando
o adapter declarar troca segura de mídia. Multi-monitor/marquee fica declarado se
não houver backend provado.

Entregue fixtures por plataforma, validação de asset, foco, fallback e reducedMotion.

### PROMPT A12 — Theme Studio

Você é o agente A12. Transforme o editor parcial em Theme Studio.

Escopo exclusivo: theme_editor, studio_graph, ThemeStudioCanvas, inspector,
timeline, package import/export e testes. Não altere Launcher nem Central
compartilhada.

O Studio permite criar, editar, visualizar, validar, exportar, importar e reabrir
sem editor externo. Inclua canvas, árvore, seleção, constraints, tokens, effects
graph, keyframes/easing, breakpoints, states, preview Deck/FullHD/ultrawide,
high contrast, reduced motion e budget de FPS/VRAM/textura/draw calls.

Pacotes são declarativos, sanitizados, licenciados, versionados e reproduzíveis.
Undo/redo e recuperação são obrigatórios. Prove que o pacote roda na Theme Engine.

### PROMPT A13 — Providers e notificações

Você é o agente A13. Implemente providers opcionais de notificações, sync,
RetroAchievements e netplay sem tornar a plataforma dependente da rede.

Escopo exclusivo: provider contracts, outbox, credentials, notifications,
sync conflicts, achievement events, netplay descriptors e testes.

Notificações são acionáveis e honestas. Segredos ficam no keyring. Offline usa
fila limitada, retry/backoff e estado explícito. Sync preserva ambos os lados em
conflito. Achievements e netplay exigem consentimento, modo offline e revogação.

Não declare cast internet, netplay ou achievements prontos sem adapter real e
prova física proporcional.

### PROMPT A14 — Integration, QA e release evidence

Você é o agente A14 e só integra frentes com contratos e testes aprovados.

Escopo: arquivos compartilhados autorizados, testes de integração, visual QA,
performance probes, hardware matrix e evidência. Não reescreva domínio para
encobrir falhas.

Integre AURA Cinema ao entry point correto, conecte biblioteca, Theme Engine, sessão
e diagnóstico. Valide 1280x800, Deck LCD, dock, Full HD e ultrawide. Meça startup,
FPS, frame p95, VRAM, memória, input latency, troca de cena e retorno.

Verifique foco sem mouse, arte ausente, provider offline, operação longa, rollback,
BIOS missing, save conflict e recovery. Cada etapa física deve ter baseline,
entrega funcional e recuperação quando aplicável, sem segredos. Não instale nem
publique sem autorização. Gere relatório item→commit→teste→evidência.

## 8. Critérios de aceite do produto final

O AURA Cinema e a plataforma só podem ser promovidos quando:

1. a primeira tela abre com foco válido e navegação completa sem mouse;
2. uma biblioteca canônica apresenta títulos, capas, fanart e fallback sem
   identificadores técnicos expostos;
3. jogar abre o runtime correto, sem duplicar processos, e retorna ao mesmo foco;
4. ausência de BIOS, emulator, artwork, credencial ou rede produz explicação e
   próximo passo, não tela vazia;
5. toda operação mutável mostra plano, risco, progresso real, cancelamento seguro,
   resultado e recuperação;
6. save-state, Pause, OSD, cards e fade existem somente onde o adapter declara;
7. o tema externo é seguro, reproduzível, acessível e não executa código;
8. low/balanced/cinematic degradam sem perda de jogabilidade;
9. performance é medida no hardware e na release citados;
10. todos os P0 estão integrados, empacotados e fisicamente validados.

## 9. Sequência recomendada de execução

1. A0 congela contratos e fixtures.
2. A1 e A2 trabalham em paralelo.
3. A3 inicia após A2 estabilizar receitas de imagem.
4. A5 inicia após A1; A6 e A7 trabalham em paralelo com A2/A3.
5. A4 começa quando A1 e A3 tiverem contratos consumíveis.
6. A8 e A9 trabalham separados; enhancements não bloqueiam launch até passar policy
   e rollback.
7. A10 começa em paralelo com A4 usando fixtures, depois conecta à sessão real.
8. A11 e A12 entram após A2/A3/A10.
9. A13 entra após saves e credenciais estarem estáveis.
10. A14 integra, mede e certifica; qualquer falha física reabre o item responsável.

## 10. Fora da primeira entrega fullscreen

Ficam explicitamente posteriores ao primeiro release console-like:

- cast pela internet;
- netplay completo com descoberta social;
- marketplace remoto de temas;
- suporte universal a PSD/AVIF/TIFF quando o backend não provar consumo;
- partículas, hologramas, glitch e efeitos caros sem medição;
- todos os emuladores e plataformas sem jornada de lançamento validada.

Esses itens podem possuir contrato e protótipo, mas não devem bloquear a entrega do
fluxo principal nem aparecer como prontos.

