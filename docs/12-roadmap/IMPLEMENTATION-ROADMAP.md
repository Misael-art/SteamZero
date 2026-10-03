# Roadmap de implementação — revisão após diagnóstico físico de 01/10/2026

## Autoridade, objetivo e ponto de partida

Este é o plano canônico de **ordem de execução**. `docs/status/items/*.json` continua sendo a fonte do **estado** de cada capacidade; `docs/ACTIVE-WORK.md` identifica os responsáveis. A auditoria [AUDIT.md](../09-operations/evidence/2026-09-26-project-design-audit/AUDIT.md) e sua [matriz](../09-operations/evidence/2026-09-26-project-design-audit/capability-matrix.md) preservam o diagnóstico, não certificam automaticamente a versão seguinte. O [prompt raiz](../../IMPLEMENTATION-PROMPT.md) operacionaliza este plano e o [handoff](../09-operations/AGENT-HANDOFF.md) informa o ponto de retomada.

Objetivo: concluir jornadas úteis de ponta a ponta com integridade de dados, foco por controle, recuperação e experiência AURA consistente. Continuar o código existente; não reiniciar as fases históricas nem implementar novamente capacidades já presentes. Aprovações históricas de implantação não são autorização transferível para instalar no host.

## Prioridade vigente — produto visual e autoria de temas

Esta revisão substitui a fila inicial de RC-01 e antecipa os recortes elegíveis de RC-05/06. Os demais lotes e seus contratos continuam abaixo. Não é necessário resolver todo o acervo de ROMs para criar, editar e executar um tema sobre dados sintéticos. Dependências reais de contrato/runtime continuam obrigatórias.

Base conferida no checkout em 01/10: `main` em `5715d7962691efedef0f1b63e71adff1ad5ba801`, um worktree e árvore limpa antes desta revisão documental. A integração de #239–#248 está relatada no fechamento anterior. A instalação da release `2.0.0rc1-5715d7962691` é sustentada pelos logs 131/132 e pelos relatórios visuais; esta revisão não reinstalou nem fez nova medição dos serviços.

Fonte física mais recente: `134-b_visual-rc01-fisico-2`, que amplia `133-b_visual-rc01-fisico`, em:

`/home/misael/steamzero-evidencia-integracao-2026-09-30/integracao-2026-09-30/`

Leia `README.md`, `ACHADOS.md`, `TAREFAS-A-CODIGO.md`, `RC01.md` e `MATRIZ.md` das duas rodadas. São evidências locais: não enviar capturas/acervo privado a um PR sem revisão de privacidade e licença. Não copiar indiscriminadamente o acervo inteiro para o repositório.

### Estado demonstrado e limites

| Área | O que a rodada 134 demonstrou | O que ainda exige trabalho/prova |
|---|---|---|
| Central | Loading próprio; prontidão com estados/dimensões; quatro vistas de unidades | Primeira leitura em 7,6–8,3 s no arranque frio com daemon quente; flash de paleta; exceção `memoryGb`; carga/erro/retry completos não certificados |
| Importação | ES-DE/RetroFE: exame, erro/recuperação, publicação gerenciada, reset e duplicata bloqueada sem sobrescrita | Conflito local chamado de download; modal não herda aparência; alvos; seletor nativo e ordem de respostas inconclusivos |
| Design | Texto sobre superfícies navy legível; medições de componentes e modais abaixo da política essencial | Corrigir pares texto/fundo e estados no sistema de componentes; informação de erro acessível na própria jornada |
| Studio | Painel e controles mapeados; código contém canvas/árvore/inspector e contratos de efeitos | Ciclo de autoria/reabertura não comprovado. Parte do grafo é observável, não editável. Falha da ação AT-SPI não prova impossibilidade de edição humana |
| Temas/Launcher | Pacotes importados sem ativação automática; infraestrutura de cenas existente | Execução, correspondência preview/runtime, AURA Cinema atual e desempenho sem prova física. `--library` não ofereceu isolamento do catálogo privado nesta rodada |
| Input | Ativações semânticas AT-SPI e rolagem por Value/Increment funcionaram em parte | Teclado sintético recusado/sem efeito; gamepad, escalas e seletor nativo precisam de passe próprio. Não atribuir automaticamente essas limitações ao produto |

`RC01.md` ainda apresenta “seletor não aberto”, enquanto o adendo de `ACHADOS.md` relata abertura e desaparecimento inconclusivo. Reconciliar essa divergência no item/evidência mais recente; nenhum desses relatos certifica o round-trip do seletor.

### Entregas significativas, em ordem

`V1–V4` são recortes executivos do roadmap, não um catálogo concorrente. Um executor reserva os IDs existentes e conclui jornadas revisáveis. Não abrir uma cadeia longa de PRs dependentes: integrar o lote aprovado conforme a autorização e desenvolver a próxima entrega sobre a base consolidada. PRs adicionais só quando houver divisão arquitetural necessária, com dependência explícita.

| Entrega | Resultado útil para o usuário | Escopo principal | Critério de saída |
|---|---|---|---|
| **V1 — Central e Studio com apresentação consistente** | Ações e estados legíveis; modais pertencem ao tema; erro informa causa e recuperação sem esconder a tela | RC-01; tokens/controles/paleta de Popup, navegação Temas/Studio, erros, locale e a11y | Resolver AC-134-01–09 como conjunto coerente: contraste essencial ≥7:1 salvo política equivalente formalmente aprovada; alvos/foco coerentes; duplicata aponta ID existente e conserva hash; erros locais com detalhe no modal; memória formatada conforme unidade real; ícones/abas nomeados e ativáveis; erros críticos preservados sem dominar todas as rotas |
| **V2 — Tema importado que efetivamente executa** | Escolher uma cena, visualizar com dados válidos, aplicar explicitamente e voltar ao estado anterior | RC-05 + runtime RC-06; catálogo, resolver, read model, render e Launcher/Cinema | Builtin AURA Cinema e um fixture licenciado de ES-DE e RetroFE percorrem importar→resolver→preview→uso no consumidor correto→restaurar. Mídia/textos resolvidos, sem corpo vazio ou fallback silencioso; degradações informadas. Isolamento sintético explícito impede mistura com biblioteca pessoal; pacote inválido recupera superfície segura sem perder foco |
| **V3 — Theme Studio útil de ponta a ponta** | Criar uma composição, alterar arte/layout/receita, desfazer/refazer e usar o pacote produzido | RC-06; sessão/documento, canvas/árvore/inspector, layout/receitas, persistência/export | Pela UI: criar→selecionar elemento→editar propriedades→preview→undo/redo→salvar→fechar/reabrir→exportar/importar→executar no runtime de V2. Conteúdo preservado semanticamente; não depende de editar JSON ou imagem fora do Studio; origem protegida, namespace de cópia e confirmação de sobrescrita |
| **V4 — Autoria avançada e jornadas executáveis** | Criar menus conectados, navegar por metadados, personalizar cada etapa e preservar o retorno; avançar autoria de efeitos/movimento | RC-06; sidecar `experience-journey-v2` com migração v1, grafo/contexto, read models públicos, herança AURA, Theme Engine, Launcher/Cinema, sessão por capability; effect graph/timeline, tiers e receitas | Pela UI: criar pelo menos 3 menus, conectar/reordenar, compartilhar destinos, filtrar por campos publicados e completar round-trip. Antes de aplicar, listar cada etapa AURA herdada. O mesmo documento salvo/reaberto precisa alterar Preview, Engine e Launcher; launch/pause/save/load/exit seguem resultado de adapter e restauram filtros, seleção, rolagem e foco. Ciclo manual válido; referência inválida, ciclo automático, campo desconhecido, erro e capability ausente recuperáveis. Efeitos, movimento, reducedMotion e fallback passam testes próprios. p95 ≤16,7 ms e VRAM ≤512 MB somente com cena, hardware e release identificados; FPS apresentado apenas com instrumento adequado |

V1 não é uma troca indiscriminada de aparência. Preservar a linguagem AURA, tornar hierarquia/estado/ação legíveis e corrigir causas compartilhadas. Medir o par efetivo após composição/opacity; controles desabilitados devem explicar indisponibilidade sem apagar informação essencial. Registrar dimensões lógicas e físicas/escala, sem tratar extents AT-SPI como unidades conhecidas por suposição.

V2 diferencia **tema da central**, **pacote/cena da Engine** e **cena do Launcher**. Botões de aplicar/preview identificam consumidor, resultado e escopo. Importação bem-sucedida não equivale a cena ativa ou gameplay. Resolver referência e binding faltantes com diagnóstico; não substituir um pacote portado por um demo builtin e alegar fidelidade. A cobertura/loss report acompanha as capacidades realmente consumidas.

V3 começa pelo documento e pelas operações que já existem. Concluir sessão→ação autenticada→validação→persistência→render; não criar editor paralelo. A fatia básica inclui orientação `none/auto/portrait/landscape`, enquadramento/alinhamento/ponto focal e receitas por slot conforme a spec, implementando o recorte necessário completo. Não basta mostrar effect/timeline como texto ou desenhar canvas sem salvar. A declaração de Studio completo aguarda também V4 e o DoD integral.

V4 usa o sidecar `experience-journey-v2`, com leitura migrável de v1;
`theme-manifest-v1` continua estrito e não recebe campos de jornada ad hoc.
Nesta branch, a bridge allowlisted consulta o catálogo público e o painel de
Jornadas faz operações transacionais de criação/edição/histórico/arquivo pelo
servidor real de loopback. O round-trip da UI é exercitado com três menus e um
destino compartilhado. `journey.studio.engine-preview` entrega os resultados
públicos filtrados ao resolver native e confirma a composição do documento
salvo/reaberto no Theme Engine em fixture sintética. Isso fecha a dependência
local entre bridge, read model e `sceneLayouts`; não demonstra pixels/tempo em
release, nem consumo pelo Launcher/Cinema. O aceite V4 permanece pendente até o
Launcher consumir a jornada, a sessão publicar e executar capabilities reais,
e o roteiro B_VISUAL ocorrer em candidata instalada. Sessões sintéticas e
animações não provam launch, pausa, save/load ou exit reais.

### Relação com os achados e trabalho restante

| Origem | Destino | Observação de aceite |
|---|---|---|
| AC-134-01, AC-134-03, AC-134-04, AC-134-05, AC-134-07, AC-134-08 | V1 | Erro próprio/contrato existente adequado, componentes/modal, alvos, a11y e mensagens |
| AC-134-02 | V1 | Confirmar se `memoryGb` significa GB ou GiB antes de converter; valores ausentes não viram zero |
| AC-134-06 | V1 | Resumo/agrupamento contextual com detalhe acessível; nenhuma falha crítica apagada por timer |
| AC-134-09 | V1 + desempenho | Paleta inicial segura ou preferência validada; evitar salto visual sem bloquear abertura pela consulta completa |
| AC-134-10 | B_VISUAL por entrega | Passe real de teclado/gamepad e portal nativo; ferramenta limitada não gera resultado `passed` |
| AC-134-11 | V2 | Biblioteca de demonstração explicitamente isolada; ações e catálogo de produção não vazam para ela |
| Autoria parcial e execução precária relatadas pelo usuário | V2–V4 | Referência aceita: tema produzido pelo Studio realmente consumido pelo runtime, com arte e layout verificáveis |
| Arranque/consulta lenta | Perfil em V1, recorte completo na entrega pertinente | Separar tempo até UI útil, tempo até dados mínimos e consulta total. Não equiparar arranque frio da central com orçamento de home aquecida do Launcher |
| Conteúdo/sessão/componentes/integrações | RC-02/03/04/07 após esta prioridade ou por bloqueio independente | Preservação, launch/return, save/load, bezel, fade, multidisco e runtimes mantêm DoD próprio; não foram certificados pela rodada visual |

### Trabalho entre A_CODIGO e B_VISUAL

**A_CODIGO** reproduz/implementa/testa em ambiente isolado, prepara commits e PRs conforme autorização e entrega o artefato identificável. **B_VISUAL** recebe uma jornada com dados sintéticos/licenciados e passos exatos, inspeciona a experiência e retorna aceites/defeitos. Input AT-SPI, teclado, mouse e gamepad são provas distintas. Input recusado exige operador ou mecanismo autorizado; não instalar uinput/compositor para encobrir a limitação.

Um agente altera código; o passe visual não troca branches nem edita os mesmos arquivos. Coordenação por item/workstream; nenhuma suíte concorrente durante o guard. O relatório visual existente é o baseline, não motivo para repetir todas as telas a cada correção. Passe focado por entrega e revisão integrada final.

Antes da integral de fechamento, concluir governança aplicável e renderizar views para evitar falha de catálogo previsível. Conservar comandos, exit codes, capturas originais e hashes; comparação por bytes/contagem de mutações é apoio, não avaliação da experiência. Não criar gate por tamanho mínimo de PNG.

**Objetivo da primeira missão de continuidade:** entregar V1 e percorrer V2/V3 até um tema editado e reaberto realmente renderizar, com limites físicos explícitos. V4 segue em recortes completos se a base estiver consolidada. Nenhuma decisão de instalar/publicar/mergear é transferida implicitamente de sessões anteriores; preparar o resultado revisável antes de solicitar a operação necessária e continuar trabalho independente elegível.

## Fotografia histórica de 26/09/2026

A tabela abaixo preserva o diagnóstico inicial; a revisão de 01/10 acima orienta a próxima entrega. Não usar os números de 26/09 como medição atual do acervo.

| Recorte | Feito / evidência existente | Parcial / próximo trabalho |
|---|---|---|
| Centralização | Sete frentes reconciliadas seletivamente; PR #237 integrado em `1ffafa648b3d4b0ac2691c11fd300b7e66d0c95e`; um worktree conferido em 26/09 | Preservar arquivos locais da auditoria e deste plano até integração; refs e bundles não são lixo |
| Código e host | Base documental `3495c49d5d7c3244267e8292beee34475f70236b`; release observada `2.0.0rc1-e2af2562ebba`; instalação/UI verificadas | Release instalada e checkout não são o mesmo SHA; gameplay completo e doctor sem degradações não certificados |
| Biblioteca/BIOS | 1.163 registros reconhecidos, 27 plataformas; 1.145 entradas de emulação publicadas como lançáveis; 7 Steam; BIOS 6/9 | “Lançável” é preflight, não gameplay. 18 arquivos reconhecidos retidos e 15 candidatos multidisco pendentes; conjuntos podem se sobrepor |
| AURA UI e Launcher | Central, contratos de ações, cenas, sessão e evidências históricas físicas | Contraste, loading, viewport e recertificação da jornada atual; 211 contratos não equivalem a 211 ações exercitadas |
| Theme Engine e Studio | Render, importadores, canvas/árvore/inspector e provas parciais | DoD de autoria e runtime completos não satisfeitos; AURA Cinema é cena do Launcher, distinta da central |
| Sessão | Provas históricas de pausa, save/load, bezel; troca de disco por adapter real | Fade, OSD pausado atual, troca pelo Launcher e durabilidade de saves ainda exigem prova específica |
| Verificação | Testes de temas 183; sessão 208; QML 3; persistência 36 passaram | Integral auditada: 1 falha documental, 6.293 aprovados, 47 ignorados; não declarar verde após somente corrigir views. Nos 208 testes houve escrita concorrente do daemon e atribuição degradada |

A fotografia da matriz contém 78 capacidades e 12 agregadores: 31 capacidades declaradas completas, 42 parciais e 5 planejadas. Esses números não são um novo selo de qualidade nem devem ser fixados como expectativa de testes. Novos itens de governança podem mudar a contagem.

## Método de entrega e diretório único

- Usar somente `/home/misael/Projects/Steam Zero/Canonical/2026-09-21`. Não criar outro clone, worktree, árvore `final`, `v2`, backup de código ou segunda `.venv`. Trocar branches sequencialmente no mesmo checkout somente depois de preservar e integrar/registrar o trabalho pendente.
- Um lote funcional ativo por vez. Reutilizar os itens de capacidade e workstreams correspondentes; reconciliar claims antigos contra Git e evidência antes de reservá-los. Não apagar um claim porque a branch parece velha. Arquivos compartilhados têm edição serial.
- Escolher o primeiro lote elegível de maior impacto; dependência bloqueada permite avançar em outro lote independente. Não parar após apenas escrever testes ou planos quando a implementação estiver autorizada e viável.
- Uma entrega significativa fecha uma jornada ou remove um bloqueio mensurável: contrato → domínio → adapter → UI → erro/recuperação → testes. Dividir lotes grandes nesses recortes, com PRs coerentes; não fazer um PR por microedição nem um PR gigante para todo o roadmap.
- Usar testes focados durante desenvolvimento; executar os gates integrais de `AGENTS.md` no checkpoint funcional estável. Registrar comando, exit code, SHA e limites. CI verde em SHA anterior não valida o atual.
- Evidências em **um diretório por lote** sob a estrutura existente, reutilizado durante iterações. Temporários em uma pasta identificada fora do checkout; remover somente arquivos/processos criados pelo lote após promover evidências necessárias. Sem limpeza global de `/tmp`, caches, backups ou acervo.
- Nenhuma capacidade é promovida por screenshot, existência de processo, manifesto ou teste com mock. Conservar cinco eixos de status, critérios não satisfeitos e diferenças de release/hardware.

## Sequência de lotes

Identificadores `RC-*` são índices deste plano, não novos IDs de capacidade. Cada executor deve vincular seu recorte aos IDs reais do catálogo e seus critérios de aceite. Os gates comuns de fechamento estão abaixo; a tabela acrescenta a prova específica de cada entrega.

| Lote / prioridade | Entrega e escopo | Dependências | Critério específico de saída |
|---|---|---|---|
| RC-00 / primeiro | Integrar documentação da auditoria e plano; conferir main/branch/host, resolver claims ativos obsoletos com evidência; mapear cada capacidade parcial/planejada ao lote responsável | Árvore local preservada; leitura de AGENTS/status | Nenhum arquivo pendente perdido; views/digests válidos; cada item da matriz tem destino, dependência ou decisão explícita. Não transformar esta etapa em nova auditoria integral |
| RC-01 / P1 | Central legível e responsiva: contraste, loading/erro/vazio explícitos, custo da consulta de status; readiness explicado, tamanho humano, foco/scroll e modal RetroFE compacto | RC-00; contratos atuais da central | Reproduzir UX-01/02; medir antes/depois com mesmo catálogo. Home utilizável no orçamento aplicável; sem tela vazia enganosa; contraste essencial conforme política; controles alcançáveis em viewport compacto e escala de texto; timeout/retry sem corrida |
| RC-02 / P1 | Biblioteca acionável: fila de arquivos/sets, extração segura, projeções multidisco, derivados vinculados ao original, preview de espaço, scan assíncrono/cancelável onde ainda faltar | RC-00; scanner/job/store atuais; G48/G51/G55–59 reavaliados | Classificar os 18 arquivos/15 candidatos sem somar conjuntos sobrepostos. Demonstrar plan→apply→reexecução→cancel/recovery→rollback em cópias controladas, hashes de origens iguais, recusa por espaço insuficiente e ausência de duplicidade. Resolver cobertura 3DS/Wii U pelos contratos próprios |
| RC-03 / P1 | Sessão jogável consistente: controle→jogo→pausa→save/load→retorno, OSD acessível, fade/reducedMotion, bezel e multidisco; saves normais/checkpoints tratados separadamente de save-state | RC-01 para UI; RC-02 para sets pendentes; adapter/runtime compatível | Release/SHA identificados; capturas running/suspended, razões visíveis de indisponibilidade, foco restaurado, troca 1→2→1 pelo Launcher, save/load com resultado verificável. AC-SV-02 por falha controlada isolada/VM antes da prova autorizada no host; nunca desligar abruptamente o host para testar |
| RC-04 / P1 | Componentes e primeira execução: aquisição/verify/update/rollback, BIOS/firmware/keys, first-run, portais Flatpak/PCSX2, input, handheld/dock/offline/suspend; doctor com remediação | RC-00; integração com RC-02/03 para prova fim a fim | Reproduzir G49/G50 e estado atual dos runtimes; instalar só pelo fluxo governado autorizado. Runtime ausente/incompatível produz causa acionável; provar launch e retorno por perfil suportado com conteúdo autorizado; sem alegar gameplay PS4/PS5/Vita por catálogo |
| RC-05 / P2 | Mídia e frontends: providers/cache/licenças, ES-DE com dados reais, RetroFE import→ativação, Steam/SRM idempotentes; AURA Cinema consistente e mensurado | RC-01; catálogo RC-02; RC-04 quando runtime necessário | G52/G54 reavaliados; bindings resolvidos, arte estabilizada sem sleeps arbitrários, import/reimport sem duplicação, fallback offline. Cinema a 1280×800: 60 FPS, p95 ≤16,7 ms e orçamento VRAM conforme spec, com hardware/release e tiers registrados |
| RC-06 / P2 | Theme Engine e Studio completos por fatias de autoria descritas abaixo | RC-05 para dados/consumo; contratos de tema seguros | Criar→editar→preview→undo/redo→salvar→exportar→importar→reabrir→usar no runtime sem perda, com input físico; cumprir DoD separado da Engine e do Studio, sem promover Launcher por arrasto |
| RC-07 / P2–P3 | Restante de plataforma/integrações: sync e conflitos, adoção/migração, melhorias de emuladores, casting, serviços online e capacidades planejadas | Lotes de domínio anteriores; dependências específicas do catálogo | Cada capacidade restante tem recorte com aceite de sucesso/erro/recuperação; protocolos, privacidade, credenciais e licença resolvidos antes de ativar rede. Cast orquestrado não equivale a receiver ativo |
| RC-08 / qualificação | Release candidata, matriz física completa, instalação/update/rollback, distribuição/SBOM/assinaturas, documentação de usuário e limpeza final | Todos os critérios obrigatórios do escopo de release; decisões de adiamento explícitas | Gates no SHA candidato, CI terminal, instalação autorizada e prova física por plataforma/jornada; resíduos próprios removidos, checkout limpo, main integrado e catálogo coerente. M14/M15 só promovidos com seus critérios completos |

Não adiar toda validação física até RC-08: fazê-la por entrega quando necessária e autorizada. RC-08 consolida compatibilidade e regressões entre entregas. Se depender do operador, preparar a entrega revisável e continuar testes/implementações independentes; registrar exatamente a prova pendente.

### RC-06: fatias completas de Theme Studio e Engine

Seguir [THEME-ENGINE-AND-STUDIO](../01-product/THEME-ENGINE-AND-STUDIO.md), inclusive os critérios não enumerados aqui. Antes de implementar, comparar a spec com código atual: descrições históricas de “inexistente” podem estar superadas.

1. **Autoria básica reproduzível:** canvas/árvore/inspector, seleção/constraints, orientação `none/auto/portrait/landscape`, contain/cover/fill/crop/alinhamento/ponto focal, regras por slot; undo/redo, recovery e round-trip. Reutilizar implementações existentes.
2. **Receitas e layouts:** asset único→variantes de logo, graph/repeaters/bindings/breakpoints, cores dinâmicas, efeitos allowlisted/glass por tier; cache com orçamento e fallback. Nenhum asset derivado duplicado no pacote nem shader/código arbitrário de tema.
3. **Tempo e estados:** editor de effect graph/timeline/keyframes, interrupção/reversão, estados loading/erro/offline/playing, reducedMotion; preview e pacote consumem os mesmos contratos.
4. **Ferramentas e qualidade:** dados demonstrativos, múltiplas resoluções, profiler/validadores, acessibilidade, licença, schema/migração, pacote inválido/pesado com fallback; completar §§4–20 da spec. Prova física e métricas ligadas à release para cada DoD.
5. **Jornada de experiência:** autoria de menus e mapa de links compartilhados, filtros por qualquer campo público tipado, herança AURA visível, persistência/export/import e consumo da mesma jornada na Engine e no Launcher. Preservar contexto real e respeitar cada capability de sessão; não promover por contrato/API ou preview isolado.

### Cobertura do restante e planos especializados

RC-00 deve conferir **todos** os itens da matriz, inclusive os declarados completos com evidência antiga. Agregadores são custódia de arquivos, não funcionalidades certificadas. Atualizar `nextAction` dos itens efetivamente trabalhados e manter um destino explícito para os demais, sem criar catálogo concorrente.

- Conteúdo, BIOS, saves, conversões, cloud e migração: RC-02/03/07; consultar [plano de conteúdo real](../01-product/REAL-CONTENT-COVERAGE-PLAN.md).
- Device/mode, Steam Input, sessões e distribuição: RC-04/08; executar critérios do [STEAM-SESSION-ROADMAP](STEAM-SESSION-ROADMAP.md), não substituir por prova em desktop genérico.
- `SZ-AURA-PLATFORM-EXECUTION-PLAN`: conciliar seu plano especializado com RC-01/03/05/06. “Plano implementado” não certifica as capacidades que ele descreve.
- `SZ-FRONTEND-LAUNCHBOX`, cast internet, online P2P e RetroAchievements: RC-07; validar dependências e escopo normativo, entregar contratos + UX + falhas/offline reais. Não omitir por serem planejados nem inventar integração sem API/credenciais disponíveis.
- G48–G59 são identificadores históricos de investigação. Conferir um a um no catálogo e registrar confirmado aberto, já resolvido com prova ou decisão de escopo. G56 tem evidência de catálogo fechado; isso não prova launch Vita. Não reabrir trabalho concluído só porque o documento antigo o lista.

## Rastreabilidade integral dos achados

| Achados da auditoria | Responsável neste plano | Verificação exigida |
|---|---|---|
| UX-01, UX-02 | RC-01 | Contraste medido; loading/erro real e latência antes/depois |
| UX-03, UX-04, UX-05, UX-07 | RC-01 | Semântica de readiness, unidades humanas, viewport/foco/scroll e modal completo |
| DATA-01 | RC-02 | Fila acionável com integridade, espaço, rollback e sets sem duplicação |
| UX-06 | RC-07 | Separar configuração, receiver, sessão conectada e falha recuperável |
| UX-08, UX-09 | RC-03 | Reproduzir OSD pausado atual; conferir também a ativação da ação indisponível antes de afirmar que razão nunca é mostrada; localização e erro legível |
| CAP-01 | RC-06 + RC-03/05 | DoD independente de Studio, Engine e Launcher |
| CAP-02 | RC-05 | Cinema atual a 1280×800; não reutilizar aprovação a 948×593 |
| CAP-03, CAP-04 | RC-03 | Fade observado na transição e reducedMotion; discos trocados pela UI instalada |
| CAP-05 | RC-03 | Confirmar escopo de seleção de bezel; padrão físico já existe. Só criar picker se requisito/decisão de produto o exigir |
| EVID-01, EVID-02 | RC-01/03/05/06 conforme superfície | Capturas de diálogos/overlays e ativação dos sete controles não sondados; prova por input real |
| EVID-03, EVID-04 | RC-01/05 | Classificador distingue recursos KDE de warnings próprios; captura espera estado de mídia, sem concluir ausência a partir de 650 ms |
| EVID-05 | RC-05 | ES-DE com fixture/read model real; placeholder anterior não prova defeito |
| EVID-06 | RC-03 | Checkpoint/flush/restore e conflito preservador; falha após resume controlada, sem confundir save normal com save-state |

## Fechamento de cada lote

1. Reproduzir a lacuna na base atual e declarar impacto, contrato, critérios e dependências no item existente; registrar workstream antes de editar.
2. Implementar a jornada com testes de regressão que falhem pelo comportamento errado, incluindo falha/recuperação e idempotência quando aplicável. Medir experiência e não só sucesso da API.
3. Executar os gates exigidos por `AGENTS.md` no tip estável. Uma falha local permanece registrada até resolução; não classificá-la como flake sem reprodução/causa medida.
4. Prova física identifica SHA fonte, wheel/release, hardware, conteúdo, ação observada, resultado e limites. Testes usam XDG isolado; escrita concorrente de daemon degrada a atribuição do guard, não é “host intacto”.
5. Atualizar item, evidências, gaps, digest pela ferramenta e views; WORKLOG append-only no fechamento. Alteração documental isolada recebe validação documental adequada, sem reexecutar suíte longa por reflexo.
6. Commits e PR coerentes, sem force-push; resolver divergência na branch preservando histórico. Validar CI no SHA final e respeitar a autorização de merge vigente. Fechamento integrado registra o SHA efetivamente em main.
7. Limpar apenas temporários/processos próprios e caches comprovadamente regeneráveis do lote; não apagar backup, bundle, ROM, BIOS, save ou alteração não integrada. Entregar tabela item→commit→teste→prova física→gap e próximo lote elegível.

## Mapa arquitetural histórico (fases 0–6)

As fases abaixo preservam a organização original e as dependências arquiteturais. **Não são a fila atual nem uma declaração de ausência de código**. A ordem executiva é RC-00–08 acima; [MILESTONES](MILESTONES.md) mantém os critérios dos marcos. Autorizações/licenças pendentes são verificadas no escopo afetado, sem ressuscitar um bloqueio global de bootstrap.

## Fase 0 — Fundação documental (mapa histórico)

Inventário, matriz de capacidades, licenças, PRD, arquitetura, threat model, UX, contratos de API, schemas, plano de testes, roadmap, riscos. Nenhum código de produção.

## Fase 1 — Núcleo mínimo (base de tudo)

Entregas: repositório estruturado (MODULE-BOUNDARIES aplicado por lint), `core.fs` (atomic/staging/containment), núcleo transacional + journal + locks + quarentena, State Store + migrações numeradas (0001 baseline; 0002 Desktop Experience), Job Manager (fila, pausa/resume/cancel, recovery pós-crash), CLI `steamzero` (envelope v2), catálogo de erros inicial, logging estruturado, doctor mínimo, suíte: unit + FI-04/06/15 + RTs do núcleo + golden files de contrato.
Critério de saída: AC-TX-01..04 verdes; kill em cada etapa do pipeline recuperável.

## Fase 2 — Steam Deck Core

O fechamento operacional desta fase e das integrações Steam das fases 4–5 é
detalhado em [STEAM-SESSION-ROADMAP](STEAM-SESSION-ROADMAP.md), com baseline
honesta, ordem R1–R10 e gates de hardware.

Entregas: Device/Mode Manager (handheld/docked-*/desktop + fallback de display), Session Manager (§11.1) com hooks suspend/resume, monitor de volumes por UUID (microSD), modo offline + fila, Compat Matrix inicial, helper privilegiado `steamzero-admin` (TDP/sysctl/udev allowlist) + polkit, perfis de desempenho básicos (aplicar/restaurar).
Critério: AC-SD-01/02, AC-OF-01, AC-PR-01/02 em VM; checklist HW iniciado (Q6).

## Fase 3 — Conteúdo

Entregas: Library (scan/plan/apply incremental, dedupe, `MULTIDISC-DESCRIPTOR-RECONCILIATION`, quarentena), import de dumps (safezip), conversões (CHD/RVZ/CSO/NSZ) com staging/espaço/timeout e atualização transacional dos descritores derivados, BIOS/firmware/keys store central (hash db + links), Saves store + timeline + checkpoints + backups incrementais, cloud sync com fila e conflito não-destrutivo, mídia/scraping com cache e rate limit, migração SSD↔microSD.
Critério: AC-LB-*, AC-BI-*, AC-SV-*; RT-06..11.

O plano de cobertura por conteúdo real, com as lacunas atuais de Nintendo 3DS e
Wii U e a separação entre classificação, preflight e prova física, está em
[REAL-CONTENT-COVERAGE-PLAN](../01-product/REAL-CONTENT-COVERAGE-PLAN.md). A fonte de estado e
conclusão continua sendo o catálogo `docs/status/items/`.

## Fase 4 — Emuladores e frontends

Entregas: engine de adapters + schema adapter.json + lockfile de componentes; adapters núcleo (lista PRD §7); templates de config (derivação EmuDeck conforme REUSE-POLICY); adapters de frontend Steam/SRM/ES-DE/RetroArch/RetroDECK/Heroic; ações semânticas de controle + perfis Steam Input; launcher genérico com perfis por jogo.
Critério: instalar/atualizar/verify/rollback de cada adapter em VM; matriz de licenças por componente validada.

Registro histórico M10 (não representa inventário atual): engine portátil, três manifests, lockfile anti-drift e executor Flatpak
user-scoped recuperável estão `verified-dev`; a demonstração mutável em VM e a fonte
substituta do DuckStation EOL ainda bloqueiam o fechamento do marco.

### M10-H — Handheld Desktop Foundation

Submarco prioritário dentro da Fase 4: BigLinux/KDE como plataforma de referência sem
exclusividade de distro; contexto de hardware/capabilities; perfis
`handheld-desktop`/`docked-desktop`/`safe`; ownership único; teclado em fallback;
snapshot G-STATE; recovery pós-crash; CLI e central Qt/QML. InputPlumber permanece
opcional e só vira owner após validação em hardware. Este submarco não renumera M11–M15.

## Fase 5 — UI

Entregas separadas: **AURA UI** na central de gerenciamento (dashboard, BIOS
center, jobs, saves/conflitos, configurações, lote, imports, logs/journal e
manutenção) e **AURA Launcher** fullscreen (home, biblioteca, busca, coleções,
página do jogo, launch/return e recuperação por controle). O Launcher consome o
sistema visual, mas possui item, gates e certificação próprios. A fase também
fecha a **Theme Engine** declarativa e o **Theme Studio** visual definidos em
`01-product/THEME-ENGINE-AND-STUDIO.md`; tokens ou editor de paleta isolados não
satisfazem esses marcos. Inclui ainda QAM opcional e testes de UI (focus graph,
escalas e erros).
Critério: AC-UI-01..03; jornadas J1–J9 automatizadas onde possível.

## Fase 6 — Distribuição

Entregas: Flatpak (manifest + portais) + helper host instalável, canais stable/beta/dev + lockfiles, update/rollback da plataforma (RT-14), SBOM+assinaturas+CI de release, documentação de usuário, migração de instalação beta→stable.
Critério: FOUNDATION §17 operacional → release 1.0 stable.

## Ordenação e dependências

1→2→3→4→5→6 com sobreposição controlada: 3 pode iniciar quando 1 estiver estável (2 em paralelo); 5 exige contratos de 1 congelados e consome 2–4 por trás de feature flags. Detalhe de dependências externas em DEPENDENCY-PLAN.md.
