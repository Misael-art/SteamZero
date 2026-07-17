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

### R4 — lifecycle Steam fim a fim

Unificar `steamzero-launch` e Session Manager com hooks de jobs, saves, áudio,
input, display e storage. Saída: launching→running→suspended→running→closed em
jogo real, com estado interrompido recuperável.

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

Somente após R9: snapshot Btrfs restaurável, TTY, console remoto, watchdog e
contador de falhas permitem configurar a sessão SDDM como padrão/autologin. O
GRUB não escolhe uma sessão gráfica; três falhas precisam retornar ao login ou
Plasma automaticamente.

## Gates por incremento

Todo incremento exige Ruff, formato, mypy, fronteiras, independência, pytest,
`qmllint`, wheel+proveniência e smoke host proporcional ao risco. Versões não são
reempacotadas: qualquer correção descoberta no host recebe versão nova e commit
exato no release ledger.
