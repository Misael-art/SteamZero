# SteamZero — implementação rigorosa da estabilização a42

Você é o agente implementador do SteamZero. Outro agente atuará como supervisor
técnico e revisará cada checkpoint. Sua função não é declarar progresso: é
produzir evidência verificável, preservar todas as features existentes e parar
quando a verdade observada divergir do plano.

## Base e regras iniciais

1. Leia integralmente:
   - AGENTS.md e todos os arquivos por ele referenciados;
   - /home/misael/.codex/RTK.md;
   - docs/KNOWN-GAPS.md;
   - docs/12-roadmap/EXECUTION-TO-1.0.md;
   - docs/EXPANSION-LEDGER.md;
   - docs/09-operations/A41-CERTIFICATION-RESULT.md;
   - docs/diagnostics/2026-07-30-a41-host-real-operational-diagnosis.md.

2. Todo comando shell deve começar com `rtk`.

3. Sincronize com `origin/main` e registre:
   - SHA completo da base;
   - status da worktree;
   - release instalada no host;
   - identidade do daemon e symlink `current`.

4. Trabalhe em uma branch `codex/` por PR. Não empilhe PRs sem autorização do
supervisor. Não faça force-push, reset destrutivo ou limpeza do estado real.

5. Nunca:
   - exponha keys, credenciais, tokens ou conteúdo de ROMs;
   - delete staging, backups, journals ou planos do host sem autorização humana;
   - altere grupo do usuário, Polkit, systemd, boot ou release instalada sem
     autorização explícita;
   - marque algo como `verified-hw` usando teste unitário, CI, VM ou offscreen;
   - troque silenciosamente o emulador padrão do usuário;
   - reconstrua do zero código já existente no ledger.

6. A a42 é uma release de estabilização. Nenhuma feature do backlog entra nela.

## Verdade já comprovada no host

- a41 instalada e convergida:
  `0.1.0a41-31b30211ba85`.
- Rollback físico a41→a40→a41 aprovado.
- Doctor atual dá falso verde porque ignora jobs stale.
- Dois jobs `media.global` permanecem `running` desde 2026-07-26.
- `JobManager.recover()` existe, mas não é chamado no bootstrap.
- O cancelamento de job stale não possui runner para consumir o pedido.
- State home contém aproximadamente:
  - 1.893 journals;
  - 3.248 planos;
  - 1.900 backups;
  - 651 MB de staging;
  - 353 MB de backups;
  - 1,1 GB no total.
- 1.829 journals terminam em rollback. A maioria vem de testes:
  - 1.551 `media.reconcile`;
  - 209 `switch-library.rename`;
  - 67 `media.prune-orphan-cache`.
- Testes usam `tmp_path` para seus payloads, mas algumas transações continuam
  escrevendo journal/backups no XDG real.
- Citron possui payload e metadata AppImage, mas está `degraded` por drift de
  manifesto. A UI o chama incorretamente de “não instalado”.
- Citron continua configurado como default, enquanto a plataforma aparece
  100% pronta e Eden/Ryubing estão saudáveis.
- `component list/status` usa `FlatpakExecutor` para adapters AppImage e falha.
- O refresh de mídia:
  - processou 15 jogos;
  - levou aproximadamente 177 segundos;
  - atualizou zero;
  - persistiu `screenscraper: E-SCRAPE-QUOTA-EXCEEDED`;
  - obteve zero correspondências úteis de SteamGridDB;
  - terminou como completed;
  - foi projetado na UI com `providerErrors: {}`.
- Eden e Ryubing foram abertos com sucesso. Isso foi “abrir emulador”, não prova
  de lançamento canônico de ROM; playtime zero ainda não é defeito comprovado.
- GameMode foi invocado, mas governor, split_lock e ioprio falharam.
- O usuário não pertence ao grupo `gamemode`, exigido pela policy instalada.
- O escopo systemd SteamZero atingiu 5,7 GB de memória e 662 MB de swap, mas
  agregava UI e emuladores. Não atribua isso automaticamente a vazamento da UI.
- Não houve OOM, reset de GPU, erro de filesystem ou crash da UI.
- Quatro processos qml6 terminaram em SIGABRT durante gates.
  `check_runtime_version()` não verifica o return code de `qml6 --version`.
  A relação é hipótese forte, não causa definitivamente provada.
- O serviço externo `9router` está em restart storm por EADDRINUSE. Não pertence
  ao SteamZero, mas invalida benchmark de CPU enquanto permanecer assim.

## Sequência obrigatória de PRs

### PR 0 — docs/a41-host-truth

Somente governança e registro.

- Criar o diagnóstico canônico.
- Registrar GAP-G25–G31.
- Atualizar roadmap para base a41 e a42 de estabilização.
- Adicionar adendo pós-certificação sem falsificar a história.
- Reconciliar ledger e documentos stale.
- Registrar, sem executar:
  - main sem proteção/ruleset;
  - scanners GitHub desabilitados;
  - releases duráveis ausentes;
  - a37 aparecendo incorretamente como latest;
  - IMPLEMENTATION-REPORT e NON-GOALS divergentes do código.

Gate:
- links válidos;
- namespaces não colidem;
- cada afirmação possui fonte;
- nenhum estado futuro é descrito como concluído.

Pare e entregue o diff ao supervisor.

### PR 1 — fix/test-state-isolation-g26

Objetivo: nenhuma suíte pode tocar o estado real do usuário.

- Criar runner canônico que defina XDG_STATE_HOME, XDG_DATA_HOME,
  XDG_CONFIG_HOME, XDG_CACHE_HOME e XDG_RUNTIME_DIR temporários antes de iniciar
  pytest.
- Adicionar fixture autouse como defesa em profundidade.
- Corrigir diretamente testes transacionais que dependam implicitamente dos
  paths globais.
- Fotografar antes/depois:
  contagem, bytes e mtimes do state home real.
- Reprovar o gate se qualquer arquivo real mudar.
- Não limpar o 1,1 GB existente neste PR.

Aceite:
- suíte integral verde;
- zero novo journal/plan/backup/staging no host real;
- testes de media, rename e prune isolados;
- G23 reavaliado sob ambiente realmente isolado.

Pare e entregue evidência ao supervisor.

### PR 2 — fix/job-recovery-doctor-g25

Objetivo: nenhum job pode sobreviver falsamente como running.

- Chamar recuperação exatamente uma vez no bootstrap.
- Job interrompido com operação usa recovery transacional.
- Job idempotente sem operação volta a `queued`, marcado como recuperado, mas
  não reinicia rede automaticamente.
- Cancelar job sem runner precisa produzir resultado terminal ou erro público
  específico; nunca pedido inerte.
- Doctor deve verificar:
  - jobs stale;
  - operação/journal inconsistente;
  - staging órfão;
  - journal ou backup sem referência.
- Criar `state audit`.
- Criar cleanup em duas fases: `cleanup-plan` e `cleanup-apply`.
- Cleanup deve usar quarentena recuperável; aplicação no host fica bloqueada
  até autorização humana.

Aceite:
- kill no meio de media.global;
- restart do daemon;
- zero job stale em running;
- doctor degradado antes da recuperação e limpo depois;
- idempotência em dois restarts;
- nenhum artifact pertencente a operação ativa removido.

Pare e entregue evidência ao supervisor.

### PR 3 — fix/component-lifecycle-truth-g27

Objetivo: CLI, workspace e QML publicam a mesma verdade.

- Rotear lifecycle pela origem declarada:
  AppImage → AdapterEngine;
  Flatpak → FlatpakExecutor.
- `component list` agrega falhas por componente e não aborta no primeiro.
- Preservar estado `degraded` e detalhe do drift.
- Nunca converter deployment degradado em “não instalado”.
- Configured default degradado deve:
  - permanecer configurado;
  - reduzir prontidão;
  - bloquear lançamento por default;
  - oferecer reparar ou selecionar outro emulador.
- Não mudar o default automaticamente.
- Criar plano explícito de repair/update para Citron.

Aceite:
- matrizes missing/installed/degraded para AppImage e Flatpak;
- Citron real projetado como degraded;
- Eden/Ryubing permanecem ready;
- workspace, CLI e QML concordam;
- nenhum lançamento usa fallback silencioso.

Pare e entregue evidência ao supervisor.

### PR 4 — fix/media-provider-truth-g28

Objetivo: a mídia falha de forma explicável, rápida e recuperável.

- Persistir saúde e última falha dos providers.
- Propagar `provider_errors` do resultado do job para workspace e UI.
- Tratar quota excedida como degradação visível.
- Após o primeiro quota-exceeded, não consultar ScreenScraper novamente no
  mesmo job.
- Separar:
  erro do provider,
  credencial configurada mas não validada,
  zero candidatos,
  fallback local.
- Job pode finalizar tecnicamente, mas envelope/UI ficam degraded quando zero
  mídia foi atualizada por falha remota.
- Não registrar credenciais ou respostas sensíveis.

Aceite:
- 15 jogos + quota excedida geram no máximo uma tentativa ScreenScraper;
- SteamGridDB com zero resultados não vira erro inventado;
- card mostra causa, última tentativa e ação de validar credencial;
- providerErrors nunca volta vazio quando o resultado persistido possui erro;
- cancelamento e restart cobertos.

Pare e entregue evidência ao supervisor.

### PR 5 — fix/gamemode-readiness-g29

Objetivo: não declarar performance pronta apenas porque o binário existe.

Publicar separadamente:
- binaryPresent;
- daemonAvailable;
- privilegedHelpersAuthorized;
- activeEffects.

- Detectar ausência do usuário no grupo gamemode.
- Expor plano administrativo, sem aplicá-lo automaticamente.
- Após eventual autorização humana, exigir nova sessão e revalidar.
- Falha dos helpers degrada performance, mas não precisa impedir abrir jogo.

Aceite:
- usuário fora do grupo → degraded com ação correta;
- grupo autorizado → pass após nova sessão;
- helper recusado → diagnóstico específico;
- nenhuma alteração Polkit feita pelo teste.

Pare e entregue evidência ao supervisor.

### PR 6 — harden/resource-qml-g30-g31

Objetivo: atribuir recursos e remover falso verde visual.

- Medir separadamente UI, job de mídia e processos filhos dos emuladores.
- Não persistir command lines, ROM paths ou informação privada.
- Corrigir probe de versão Qt:
  retorno diferente de zero é falha;
  usar ferramenta de versão que termine com sucesso;
  output de processo abortado não vale como evidência.
- Verificar ausência de novos coredumps no gate.

Aceite no mesmo host:
- UI ociosa por 15 min: PSS no minuto 15 ≤ 1,2× PSS no minuto 5;
- após media job: memória volta a até 1,2× baseline em 60 s;
- consumo de Eden/Ryubing aparece separado da UI;
- nenhum OOM/reset de GPU;
- zero novo SIGABRT criado pelo probe de versão.

Pare e entregue evidência ao supervisor.

## Certificação a42

Não preparar release antes de todos os PRs P0/P1 estarem mesclados e verdes.

Exige nova autorização humana para:
- preparar artifacts;
- instalar a42;
- alterar grupo gamemode;
- aplicar cleanup;
- executar ciclo físico.

Ciclo:
a42 → a41 → a42.

Verificar:
- hashes e proveniência;
- convergência e idempotência;
- doctor sem false green;
- zero jobs stale;
- state audit consistente;
- component truth consistente;
- quota mostrada corretamente;
- GameMode honesto;
- UI física;
- lançamento canônico de uma ROM base;
- sessão/playtime/encerramento;
- rollback preservando jogos, keys, firmware, configurações e saves.

Não criar tag se qualquer gate obrigatório falhar.

## Formato obrigatório de cada retorno

1. Branch e SHA base.
2. Arquivos alterados.
3. Causa raiz provada.
4. O que foi implementado.
5. Testes executados e resultados exatos.
6. O que não foi testado.
7. Riscos e dados preservados.
8. Estado do host antes/depois.
9. Gaps fechados, ainda abertos e novos gaps.
10. Pedido explícito de revisão ao supervisor.

Nunca use “concluído”, “produção”, “ready” ou “verified-hw” sem evidência
compatível com o nível alegado.
