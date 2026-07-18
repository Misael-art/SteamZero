# STEAM-SESSION-ROADMAP — fechamento operacional da sessão Steam

Este roadmap filtra o catálogo original para tudo que inicia, observa, protege ou
apresenta uma sessão Steam, tanto na sessão gráfica Game Mode quanto no lifecycle
de cada jogo. Emuladores, BIOS, ROMs e scraping genérico ficam fora deste recorte.

## Regra de verdade

Uma capacidade só pode ser marcada `done` quando seu estado real converge entre
`desired`, `applied` e `observed`. Código de domínio exercitado apenas por portas
fake permanece `verified-dev`; VM não vira `verified-hw`; uma mutação física exige
snapshot restaurável, console de recuperação e rollback verificado.

## Pendências consolidadas

| Bloco | IDs do catálogo | Baseline | Critério de fechamento |
|---|---|---|---|
| Lifecycle e suspend | F-SD-01, SZ-SD-01..03, SZ-SV-05..06 | parcial | hooks reais de logind, flush/checkpoint e retomada por camada |
| Modos, dock e display | F-SD-02, SZ-SD-04..08 | parcial | reconciliador DRM/KScreen, hotplug e fallback verificado |
| microSD | F-SD-03, SZ-SD-09..13 | `verified-dev` | adapter Linux, monitor, I/O health e bloqueio real de escrita |
| Offline, bateria e gameplay | F-SD-04, SZ-SD-14..15, SZ-JB-07..08 | parcial | providers reais e fila remota persistente retomável |
| Compatibilidade | F-SD-05, SZ-SD-16 | pendente | matriz executável Steam/SteamOS/Gamescope/Decky/plugin |
| Desempenho | F-PF-01..03, SZ-PF-01..09 | parcial | TDP/GPU por helper e restauração G-STATE observada |
| Privilégio | F-PL-05, SZ-PR-01..08 | dry only | transporte Polkit, efetores host e audit root |
| Steam Input | F-CT-01/03, SZ-CT-01..11 | parcial | layouts próprios, apply real, hot-swap, conflitos e glyphs |
| Frontends Steam | F-FE-01..02, SZ-FE-01..02/08 | parcial | shortcuts.vdf/SRM idempotentes e launcher genérico |
| Game Mode UI e QAM | F-UI-01/03/04, SZ-UI-01/02/04/06/09..14/16 | parcial | superfície Game Mode, QAM fino e focus graph certificado |
| Watchdogs e suporte | SZ-OP-06..07 | pendente | healthchecks, recovery e bundle anonimizado revisável |
| Hardware | SZ-QA-10..11 | read-only | matriz LCD/OLED/dock/suspend/storage/input/TDP por release |

## Ordem obrigatória

### R1 — adapters Linux reais, somente leitura

Implementar identificação multi-sinal do Deck, inventário de volumes por UUID,
energia, rede, sessão logind e displays DRM/KScreen. Compor no daemon sem criar
watchers concorrentes. Saída: snapshots reais, schemas estáveis e testes com
fixtures de `/proc`, `/sys` e mountinfo.

### R2 — reconciliador user-scoped

Observar suspend/resume, hotplug, mount e sessão de jogo; reconciliar apenas a
camada divergente; emitir eventos persistentes e nunca aplicar perfil durante
owner externo. Saída: dock→undock e remove→reinsert reproduzíveis em VM.

Estado atual: a observação periódica, o digest material, o snapshot SQLite v5,
os eventos atômicos e a detecção pós-resume por relógios do kernel estão
implementados. Dock→undock e remoção→reinserção possuem cenários determinísticos
locais; sua execução mutável em VM, o hook pré-suspend e a aplicação por camada
permanecem pendentes.

### R3 — fronteira privilegiada real

Empacotar `steamzero-admin`, política Polkit e efetores allowlisted. Cada ação
captura o valor anterior, aplica, verifica e restaura. Saída: fuzzing, VM e
recovery após SIGKILL; nenhuma string arbitrária atravessa a fronteira.

Estado atual: entry point, policy Polkit gerenciada, audit root e health check
read-only estão implementados. O efetor host declara `mutationsEnabled=false` e
recusa as ações mutáveis até seus protocolos G-STATE serem implementados. A CLI
interativa atravessa o transporte Polkit fechado para `admin.health`, com argv
fixo, timeout, limite de resposta e validação estrita do envelope. O host provou
que essa autenticação não deve ser delegada ao daemon user-scoped.

O inventário privilegiado read-only já observa as duas rails PPT, seus valores
atuais/default/máximos e o range SCLK do AMDGPU. Isso substitui faixas presumidas
por capability real do host, sem ainda escrever em sysfs.

O motor TDP G-STATE está implementado atrás do gate: journal anterior à escrita,
duas rails, verify, rollback idempotente, lock de pending e recovery pós-interrupção.
Testes usam sysfs descartável e simulam morte entre as rails. O transporte host
permanece desabilitado até repetir essas provas em VM com o driver apropriado.

O motor de clock GPU G-STATE também está implementado atrás do gate. Ele limita o
pedido ao `OD_RANGE` observado, captura os dois extremos SCLK e o performance level,
aplica a sequência AMDGPU manual/`s 0`/`s 1`/commit, verifica e restaura tudo em falha
ou recovery pós-interrupção. A prova instalada usa sysfs descartável; a certificação
em VM com driver AMDGPU e o transporte Polkit mutável continuam pendentes.

O motor sysctl allowlisted está implementado atrás do mesmo gate para
`vm.swappiness` e `vm.compaction_proactiveness`. Ele usa path compilado, snapshot,
verify e recovery, sem aceitar path do chamador. Os três motores agora compartilham
lock não bloqueante de processo, eliminando a corrida entre dois applies simultâneos.
O smoke instalado foi feito em `/proc/sys` descartável; os valores reais do host
foram apenas observados.

### R4 — lifecycle Steam fim a fim

Unificar `steamzero-launch` e Session Manager com hooks de jobs, saves, áudio,
input, display e storage. Saída: launching→running→suspended→running→closed em
jogo real, com estado interrompido recuperável.

Estado atual: o launcher e o Session Manager já usam o mesmo vocabulário e tabela
canônica, exclusividade por owner, eventos atômicos, propagação SIGTERM/SIGINT e
recovery explícito. A identidade agora é verificada em todos os estados ativos:
wrapper+AppID durante `launching` e marcadores AppID+digest no filho nas demais fases.
PID reutilizado não mantém o owner bloqueado e nunca recebe sinal durante recovery.
Ainda faltam integrar ao launcher real os hooks de saves/jobs/input/display/storage e
executar suspend/resume com um jogo de bancada.

### R5 — desempenho aplicado e reversível

Aplicar TDP/GPU por modelo, escopos de energia/device e restauração ao sair.
Gamescope, GameMode, MangoHud e LSFG permanecem no mesmo plano observado. Saída:
divergência vira `degraded`/`stale`, nunca sucesso.

### R6 — Steam Input e frontends

Criar layouts próprios ou licenciados, instalação por jogo, hot-swap e glyphs;
implementar shortcuts.vdf e SRM com parser, dedupe e rollback. Saída: segunda
aplicação é no-op verificado.

### R7 — Compat Matrix

Registrar combinações testadas de Steam, SteamOS/distro, Gamescope, Decky e
plugin. Saída: combinação incompatível é bloqueada antes de mutação.

### R8 — Game Mode UI e QAM

Levar o design gerencial escolhido à superfície Game Mode, com QAM opcional,
jobs, recovery, acessibilidade e navegação integral por controle em 1280×800.

### R9 — certificação física

Executar a matriz em Deck LCD e OLED, docks, displays, microSD, controles,
suspend e desempenho. Evidência vive em `test-reports/hw/<release>/` e distingue
explicitamente `verified-vm` de `verified-hw`.

### R10 — sessão padrão com recuperação

O responsável autorizou a ativação no Deck LCD após o boot legado reproduzir a queda
silenciosa para KDE. O SteamZero agora possui entrada GRUB, preparador SDDM e Session
Manager próprios: `Relogin=false`, sessão ausente retorna ao greeter e três falhas retornam
ao Plasma. O marcador legado é somente uma ponte de migração e não introduz dependência de
runtime. O fechamento permanece parcial até reboot físico confirmar Game Mode, retorno ao
Desktop, greeter por sessão ausente e desativação reversível com console de recuperação.

## Gates por incremento

Todo incremento exige Ruff, formato, mypy, fronteiras, independência, pytest,
`qmllint`, wheel+proveniência e smoke host proporcional ao risco. Versões não são
reempacotadas: qualquer correção descoberta no host recebe versão nova e commit
exato no release ledger.
