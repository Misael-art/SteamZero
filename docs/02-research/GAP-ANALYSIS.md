# GAP-ANALYSIS — o que nenhum dos quatro projetos entrega

## Lacunas de plataforma (ninguém tem)

| # | Lacuna | Mais próximo existente | Distância |
|---|---|---|---|
| GA-01 | Job Manager persistente (fila, prioridade, pausa/resume, recuperação pós-reboot, limites de CPU/IO, política de bateria, bloqueio durante jogo) | PhaseZero checkpoint/resume (Windows) é por-pipeline, não fila genérica | Componente novo |
| GA-02 | State Store consultável (SQLite) com export/import legível | PhaseZero: JSONs por operação; RetroDECK: `retrodeck.cfg` + jsons | Componente novo (ADR-0005) |
| GA-03 | Session Manager de jogo (launching→running→pre-suspend→suspended→resuming→recovering→closing→failed) com hooks de flush/checkpoint | PhaseZero display-session.sh e mode-watcher cobrem display/modo, não sessão de jogo | Componente novo |
| GA-04 | Backups incrementais de saves com linha do tempo e restauração por jogo | RetroDECK backup = tar único de userdata; EmuDeck = cloud espelho | Componente novo |
| GA-05 | Conflito de save não-destrutivo com preservação de ambos | EmuDeck cloud sync sobrescreve por heurística de timestamp | Política + engine novos |
| GA-06 | Fila offline de operações remotas | Nenhum | Novo |
| GA-07 | Transação generalizada para TODA mutação (não só biblioteca) | PhaseZero library pipeline é o molde; resto dos módulos usa backup+log sem plan/verify formal | Generalizar padrão existente |
| GA-08 | Catálogo de erros com códigos estáveis + tradução erro→impacto→ação | PhaseZero envelope tem blockers/logs, sem códigos estáveis | Novo (06-api/ERROR-CATALOG) |
| GA-09 | Manifests de componente com checksum/versão/licença obrigatórios + SBOM | RetroDECK recipe aproxima; EmuDeck resolve latest sem pin | Endurecer modelo RetroDECK |
| GA-10 | UI Game Mode nativa da plataforma (dashboard, BIOS center, jobs, timeline de saves) 100% gamepad | RetroDECK Configurator Godot é o precedente, mas acoplado ao RetroDECK | Novo (Fase 5) |
| GA-11 | Helper privilegiado com allowlist formal e parâmetros schemados | PhaseZero admin bridge delega a phasezero-admin/bigsudo (allowlist implícita) | Formalizar |
| GA-12 | Testes de injeção de falha (rede, disco cheio, SIGKILL, microSD removido, symlink malicioso, zip bomb, lock órfão) | PhaseZero tem resilience.tests.ps1 (Windows); safezip.py trata zip | Suíte nova (08-testing/FAILURE-INJECTION) |
| GA-13 | Máquina de compatibilidade SteamOS/Steam Client/plugin | Nenhum (todos quebram e consertam reativamente) | Novo |
| GA-14 | Acessibilidade formal (escala, contraste, redução de movimento, labels) | Nenhum | Novo |

## Duplicações a eliminar (evidências)

| Duplicação | Evidência | Consolidação |
|---|---|---|
| 31 EmuScripts quase idênticos (install/update/uninstall variando URL+paths) | `emuDeckDuckStation.sh` vs demais: mesmo esqueleto, ~80% igual | Adapter manifest-driven: 1 engine + N manifests |
| Launchers por emulador repetidos | `EmuDeck/tools/launchers/*.sh` e RetroDECK `component_launcher.sh` por componente | Launcher genérico parametrizado |
| Lógica shell duplicada em Python e Bash no PhaseZero | `frontends.sh`+`frontends.py`, `heroic.sh`+`heroic.py`, `launchbox.sh`+`launchbox*.py` | Núcleo Python, shell só como shim fino (ADR-0001) |
| Detecção de distro reimplementada | LinuxToys `is_*`, PhaseZero `capabilities/`, EmuDeck `nonDeck.sh` | Adapter de sistema único |
| Configuração INI por sed/eval em 3 projetos | RetroDECK framework.sh (eval), EmuDeck configEmuAI (rsync bruto), PhaseZero (jq/sed pontual) | Biblioteca de parsers estruturados (F-CF-01) |
| Instalação Flatpak repetida | LinuxToys pkg_flat, PhaseZero lib/flatpak.sh, RetroDECK manifest | Adapter Flatpak único |

## Não-idempotências e efeitos colaterais observados (a corrigir por design)

- EmuDeck `DuckStation_install`: migração move config e desinstala Flatpak imediatamente — reexecução em estado intermediário perde referência; sem backup (evidência: `emuDeckDuckStation.sh:24-30`).
- EmuDeck: reinstalar recopia templates sobre config do usuário quando `overwrite=true` em `configEmuAI` — acumula/duplica customizações perdidas.
- PhaseZero `pz_rollback`: restaura arquivo com `cp` (não-atômico) e apaga o manifesto inteiro mesmo se uma entrada falhou (common.sh:532-556) — rollback parcial fica invisível. O Unified exige rollback verificado (§13.6).
- PhaseZero `pz_write_managed_file`: backups `.bak.<ts>` ilimitados — backups infinitos sem GC (common.sh:63,78).
- RetroDECK `post_update.sh`: cadeia de migrações por versão sem dry-run.
