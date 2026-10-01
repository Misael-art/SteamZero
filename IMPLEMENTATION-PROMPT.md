# Prompt de continuidade — produto visual e Theme Studio

Revisão de 01/10/2026 baseada nas rodadas B_VISUAL 133/134. Este arquivo é o prompt canônico para A_CODIGO. A ordem e os critérios estão em `docs/12-roadmap/IMPLEMENTATION-ROADMAP.md`, prioridade V1–V4; o estado está no catálogo. Não criar outro roadmap ou editor paralelo.

---

Você é A_CODIGO. Retome o SteamZero para entregar um avanço funcional substancial: interface consistente, tema que efetivamente executa e Theme Studio com autoria básica completa. Conclua a missão abaixo com testes e evidência, sem encerrar após uma microcorreção, suíte disparada ou PR aberto.

## 1. Retomada e fatos

Use exclusivamente `/home/misael/Projects/Steam Zero/Canonical/2026-09-21`, a `.venv` e as estruturas existentes. Um checkout, um lote funcional ativo; nenhum clone/worktree/diretório `v2` ou ambiente duplicado. Prefixe comandos shell por `rtk`, conforme `/home/misael/.codex/RTK.md`.

Leia `AGENTS.md`, `docs/status/README.md`, `docs/ACTIVE-WORK.md`, o roadmap, `docs/01-product/AURA-SURFACES.md`, `THEME-ENGINE-AND-STUDIO.md` e os itens envolvidos. Confira branch/HEAD/status/remotos/claims/processos antes de editar. Preserve documentos locais desta revisão e qualquer trabalho herdado; não use reset/clean/stash automático.

Baseline da revisão: main `5715d7962691efedef0f1b63e71adff1ad5ba801`; release observada por B_VISUAL `2.0.0rc1-5715d7962691`; #239–#248 integradas segundo o fechamento anterior. Reconfira antes de usar como fato atual. Não reimplemente as correções já integradas.

Acervo físico:
`/home/misael/steamzero-evidencia-integracao-2026-09-30/integracao-2026-09-30/`

Leia `133-b_visual-rc01-fisico` e principalmente `134-b_visual-rc01-fisico-2` (README, ACHADOS, TAREFAS-A-CODIGO, RC01 e MATRIZ). A 134 amplia a 133: importação ES-DE/RetroFE, prontidão e unidades foram exercitadas, com ressalvas. Round-trip do Studio, teclado/gamepad, seletor nativo completo e Launcher/Cinema não certificados. Reconcile divergências entre adendos mais recentes e tabelas antigas; não transforme “não testado” em “quebrado”.

As capturas mostram modais cinza fora do tema, componentes com contraste insuficiente e mensagens inadequadas. A opinião do usuário sobre precariedade orienta prioridade, mas a causa de cada defeito exige reprodução.

## 2. Missão com entregas completas

### V1 — apresentação e interação consistentes

Corrija AC-134-01–09 em uma entrega coerente de componentes e jornadas:

- pares texto/fundo de botões, abas, chips, status e CTA pelo sistema de tokens; contraste essencial ≥7:1 salvo política equivalente já aprovada; estados distinguíveis sem depender só de cor;
- paleta e estados loading/vazio/erro dos modais do Studio; espaço vazio precisa informar o próximo passo;
- tab Temas/Studio com semântica, nome e ativação acessíveis, foco/teclado e alvos mínimos; medir coordenadas lógicas/físicas com escala comprovada;
- conflito de ID comunicado como conflito local, com orientação dentro do modal e hash da cena original preservado;
- erros contextuais e detalhes acessíveis, agrupando repetição sem apagar falha crítica por timer;
- memória no formatter/locale correto, confirmando a unidade de origem antes de converter;
- nomes dos ícones, título de preview com cena real e pontuação corrigida;
- paleta inicial previsível e perfil do custo de carregamento antes de otimizar.

Reuse os componentes atuais. Não faça troca arbitrária de estilo nem crie infraestrutura genérica sem necessidade. Se o problema está na herança do Popup ou na composição efetiva do tema, corrija ali, não em dezenas de cores fixas por página.

### V2 — importar e executar o tema correto

Entregue importar→inspecionar cobertura/perdas→selecionar cena→preview→usar explicitamente no consumidor apropriado→restaurar.

Use AURA Cinema builtin e um fixture seguro/licenciado de cada origem ES-DE e RetroFE. Consuma dados sintéticos com isolamento explícito: não juntar biblioteca Steam privada ao fixture e não ativar ações de produção nesse modo.

Preview e runtime usam o mesmo contrato/resolver de cena. Bindings, título, arte e layouts devem resolver; erro/asset ausente tem diagnóstico e fallback acionável. Não mostre um demo builtin no lugar do tema escolhido e alegue fidelidade. Importar não ativa automaticamente; aplicar informa se altera central, Engine ou Launcher.

Não reescreva a engine ou o launcher. Corrija a costura necessária nos caminhos existentes. Pacote inválido/pesado não perde foco nem derruba a aplicação. AURA Cinema não é certificado por um modal de preview.

### V3 — autoria básica realmente completa

Conclua pela UI:
criar documento → selecionar elemento no canvas/árvore → editar layout e receita/arte → preview → undo/redo → salvar → fechar/reabrir → exportar → importar sob cópia explícita → renderizar o resultado no runtime de V2.

Reutilize a sessão, o grafo e os endpoints autenticados existentes. Confirme o que hoje é apenas observável e implemente operações reais de edição/validação/persistência. Não basta alterar um objeto de preview ou expor EffectSpec como texto.

No recorte básico, cumpra os requisitos pertinentes de orientação, contain/cover/fill/crop, alinhamento/ponto focal e regras por slot. Fonte e derivados seguem “renderize, não edite”: uma fonte + receita, sem cópias pré-transformadas no pacote. Undo/redo e recuperação não podem deixar preview e documento divergentes.

Round-trip preserva semântica do documento e assets; compare campos relevantes, não bytes de timestamps/nome do namespace. Sobrescrita exige confirmação; original permanece íntegro. V3 não declara o Studio completo antes do DoD restante.

### V4 — evolução após a base utilizável

Com V1–V3 consolidados, implemente effect graph/timeline/keyframes, bindings/states, preview por resolução/tier e profiler conforme a spec. Faça recortes inteiros de criar→editar→persistir→reabrir→executar para cada capacidade. Efeito declarativo sem código/shader arbitrário; reducedMotion, limites e fallback.

Meça startup, p95/frame e memória no hardware/release identificados pelo instrumento canônico. Ritmo do render loop não prova FPS apresentado. Não reserve vários dias a efeitos novos se o ciclo básico ainda não funciona.

## 3. Método, coordenação e autorização

Registre workstream antes de editar e concilie claims. A_CODIGO altera código; B_VISUAL avalia jornadas e evidências com dados sintéticos em passe serial, sem trocar a branch ou editar os mesmos arquivos. Não inicie subagentes automaticamente; use a coordenação disponível quando solicitada.

Conserve uma PR funcional por entrega coerente quando possível; integre conforme autorização antes de acumular elos dependentes. Divisão adicional só por risco/tamanho arquitetural real. Não criar um PR por comentário, cor, log ou consulta de CI.

Durante a implementação, testes focados verificam regressões e resultado da jornada. Faça revisão visual e estados de erro antes do checkpoint. Atualize a governança e renderize views antes da integral para não repetir uma falha previsível de catálogo. Uma suíte por vez, árvore congelada durante a corrida; gates de AGENTS.md no fechamento funcional estável, não a cada microedição.

Se houver alteração apenas documental posterior, preserve a identidade da árvore funcional testada e revalide os gates aplicáveis. Falha histórica permanece falha; status-check posterior não muda seu resultado. CI terminal no SHA final quando houver publicação autorizada. Não crie commits recursivos apenas para anotar o resultado do CI.

Testes não substituem uso: bateria de mutações e hash de PNG são apoio, sem impor contagem arbitrária. Verifique edição real, persistência, binding e render, não cópias da implementação. Captura vazia deve reprovar por conteúdo/contrato, sem gate de tamanho do arquivo.

Esta instrução define implementação e revisão. Push/merge/build de release/instalação respeitam a autorização específica vigente de AGENTS.md. Autorizações históricas de outra release não se transferem. Sem autorização externa, termine implementação, gates, commits locais permitidos e preparação revisável; peça somente a operação concreta indispensável e avance no recorte independente elegível.

Não alterar host, boot, serviços de terceiros, ROMs, BIOS ou saves para obter passe visual. Não instalar uinput/compositor para contornar limitação de ferramenta. Input AT-SPI, teclado, mouse e gamepad têm evidências distintas; organize passe assistido se o instrumento não funcionar.

Uma pasta de evidências por entrega na estrutura existente, reutilizada. Fixture licenciado no local de testes apropriado; sem segredos, caminhos pessoais ou acervo público indevido. Remover somente resíduos/processos comprovadamente próprios depois de preservar a evidência necessária. Backups/bundles/trabalho não integrado não são lixo.

## 4. Condição de saída e continuidade

A primeira missão cobre V1–V3 até um tema editado, salvo/reaberto e executado pelo runtime. Não encerre somente porque V1 foi publicado ou um teste ficou verde. Continue até satisfazer essa jornada ou até restar uma dependência externa concreta, com tudo independente já entregue.

Não tente concluir todos os efeitos da spec em um PR monolítico. Se a base estiver consolidada e a autorização abranger a sequência, siga para o próximo recorte completo de V4. RC-02/03/04/07 permanecem no roadmap; não foram abandonados nem certificados por este trabalho.

Mantenha atualizações curtas, sem “posso continuar?” entre passos autorizados. Respeite pausas do operador. Relate o bloqueio de uma prova física sem suspender implementação/testes independentes.

Ao finalizar: entrega → jornada disponível → commit/PR → testes → prova visual/release → limites → próxima ação. Entregue o pacote de demonstração e os passos para B_VISUAL repetir criar/editar/reabrir/renderizar. Atualize somente critérios comprovados no catálogo, nextAction curto, views pela ferramenta e WORKLOG append-only.
