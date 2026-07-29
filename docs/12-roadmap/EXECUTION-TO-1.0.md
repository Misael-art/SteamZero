# Plano de execução até a 1.0

**Base:** commit `8e17159d`, host em `0.1.0a39-8e17159d5122`
(**certificação aprovada** — ver
`docs/09-operations/A39-CERTIFICATION-RESULT.md`).

Este documento não copia estado antigo. Cada linha foi conferida contra o
código, os testes ou o host nesta sessão; onde não foi possível verificar, está
dito.

## Namespaces de identificador — leia antes de citar um ID

Três documentos numeram trabalho com as MESMAS letras e significados
diferentes. A primeira versão deste plano misturou os três e produziu colisões
graves: `A6` era co-op por QR no ledger e "integrações externas" aqui; `A7` era
MediaHub lá e "M10 sem VM" aqui; `G5` era captura/galeria lá e "matriz física"
aqui.

Deste ponto em diante, **nenhum ID é citado sem prefixo**:

| prefixo | origem | governança | exemplo |
|---|---|---|---|
| `LEDGER-A*`, `LEDGER-G*` | `docs/EXPANSION-LEDGER.md` | prompt mestre de expansão, 2026-07-23 | `LEDGER-A7` = MediaHub |
| `GAP-G*` | `docs/KNOWN-GAPS.md` | lacunas descobertas em operação | `GAP-G18` = rollback stale |
| `DEBT-A*`, `DEBT-B*` | `IMPLEMENTATION-REPORT.md` §4 | dívidas técnicas classificadas | `DEBT-A0` = matriz de hardware |

Citar `A7` sem prefixo é ambíguo e não deve passar em revisão.

## Classificação de prioridade

| nível | critério |
|---|---|
| **P0** | pode causar perda, brick, falso verde, falha de segurança ou release incorreta |
| **P1** | bloqueia uma capacidade principal ou marco |
| **P2** | dívida relevante, com mitigação funcional em vigor |
| **P3** | melhoria sem impacto imediato de confiança |

## Tabela 1 — Roadmap executivo

| # | Entrega | Estado real (verificado) | Dependências | Definition of Done | Prio | Próxima ação |
|--:|---|---|---|---|---|---|
| 0 | Certificação física a39 | **concluída** — ciclo a39→a37→a39 convergido e idempotente; tag exata criada | — | ciclo completo com rollback convergido | — | preservar evidência |
| 1 | Fechar P0-03 | **parcial** — a fatia traduz 11 atributos de texto; corpus tem 388 propriedades | a39 certificada | 388 migradas, cobertura 100%, relatório | P1 | migrar corpus por família |
| 2 | Árvore de cena e texto avançado | **não iniciado** — `children` não existe no contrato (verificado: 0 ocorrências) | P0-03 | children, wrapping, elide, rich text, auto-fit com gates | P1 | especificar por slices |
| 3 | Acessibilidade real | **infraestrutura pronta, sem consumidor** (GAP-G15) | tipografia/layout | textScale, reducedMotion, highContrast consumidos de verdade | P1 | fechar GAP-G12 e GAP-G15 |
| 4 | Migração dos harnesses QML | **pendente** — 3 `skipif` restantes no arquivo legado | harness canônico | zero skip no gate visual | P2 | fechar GAP-G13 |
| 5 | Estabilidade operacional | **parcial** — GAP-G16/G23 intermitentes, GAP-G17 ausente; GAP-G18/G19 fechados | CI/host | causas dos flakes diagnosticadas, `service status` público | P1 | PRs isoladas |
| 6 | M10 — três emuladores | **parcial** — portas fake, sem mutação em VM | VM + origem DuckStation | install/update/rollback reais em VM | P1 | montar VM e matriz |
| 7 | M11 — frontends | **parcial** | M10 | Steam/SRM/ES-DE idempotentes, sem duplicação | P1 | terminar adapters |
| 8 | Hardware Deck completo | **parcial** | bancada recuperável | dock, hotplug, input, suspend, storage, TDP certificados | P0 | matriz física |
| 9 | M12 — Game Mode UI | **não iniciado** | motor de temas + frontends | navegação 100% por controle, focus graph verde | P1 | slices |
| 10 | P0-08 — máscaras e efeitos | **reservado no contrato**, nada implementado | scene tree | máscaras, hit test separado, transições, visual-rhi | P2 | só após base visual |
| 11 | M13 — adoção | **não iniciado** | M10–M12 | import EmuDeck/RetroDECK sem perda em máquina real | P1 | corpus e hashes |
| 12 | M14 — distribuição | **não iniciado** | host e canais estáveis | Flatpak, canais, update, rollback, downgrade | P1 | projetar canal |
| 13 | M15 — 1.0 | **não iniciado** | todos | SBOM, assinaturas, docs, matriz HW, checklist | P0 | release candidate |

## Tabela 2 — Dívidas técnicas

| ID | Dívida | Prio | Impacto real | Mitigação atual | Solução definitiva | Gate de encerramento |
|---|---|---|---|---|---|---|
| ~~GAP-G18~~ | ~~rollback deixa daemon stale, sem gate na release anterior~~ | — | **FECHADA pela certificação física a39→a37→a39** | — | — | convergência e idempotência provadas nas duas direções |
| ~~GAP-G19~~ | ~~códigos `E-HOST-*` fora do catálogo~~ | — | **FECHADA**: cinco códigos registrados e serializados pela CLI | — | — | testes atravessam `build_error` e `service refresh` |
| **GAP-G20** | `emulation workspace` não lê estado real | **P1** | chaves e 15 jogos válidos aparecem como ausentes | nenhuma | fazer a CLI reutilizar a composição do `EmulationController` | teste que impede uma segunda composição parcial |
| DEBT-A0 | matriz física incompleta | **P0** | impede rótulo `verified-hw` | operações read-only | validar Deck LCD/OLED/dock | matriz física verde |
| GAP-G7 | inventário fino de assets | **P1** | risco legal na redistribuição | não redistribuir | inventário item a item | notices completos |
| GAP-G11 | boot direto não certificado | **P0** | risco de boot no greeter | sessão manual + fallback Plasma | protocolo físico com recovery | ciclos de falha/recovery |
| GAP-G12 | escala de texto ignorada | **P1** | acessibilidade incompleta | fontes fixas | helper tipográfico central | layouts e foco verdes |
| GAP-G13 | 3 `skipif` no arquivo legado | **P2** | falso verde possível | não contam como gate | migrar para o harness canônico | zero skip visual |
| GAP-G14 | ~~baselines não versionadas~~ | — | **FECHADA** em `6fb2a75` | — | — | — |
| GAP-G15 | geração de acessibilidade sem consumidor | **P2** | invalidação seletiva não provada | infraestrutura pronta | consumidor real | recomputação seletiva medida |
| GAP-G16 | `test_controls_*` intermitente | **P2** | CI não determinístico | rerun (3× local passou) | diagnosticar a causa | 100 execuções sem falha |
| GAP-G17 | sem `service status --json` | **P2** | observabilidade incompleta | refresh + doctor + host status | comando público | contrato e testes |
| GAP-G21 | 46 warnings QML do Breeze | **P3** | polui coleta de warnings próprios | — | filtrar por origem | coleta só de QML nosso |
| GAP-G22 | benchmark de 10 mil arquivos usa teto de tempo de parede em runner compartilhado | **P2** | CI pode reprovar por carga do runner, não por regressão | asserções funcionais continuam fortes | entrega própria com medição comparável ou runner dedicado | repetição controlada sem falso vermelho |
| GAP-G23 | round-trip de perfil do daemon falhou uma vez no Python 3.12 | **P2** | CI não determinístico; leitura imediata retornou `active=None` | rerun passou no mesmo SHA | diagnosticar isolamento/visibilidade de estado | repetição controlada sem falha |
| GAP-G8 | matriz SteamOS/Steam Client | **P2** | compatibilidade desconhecida | estado observado | serviço de reconciliação | FM-10 verde |
| DEBT-A1 | ENOSPC mid-apply não testado | **P1** | rollback sob disco cheio incerto | preflight | loopback/quota | FI real verde |
| DEBT-A2 | dry-run sem `strace` | **P2** | ausência de writes não provada por syscall | asserção de estado | harness strace | zero writes observado |
| DEBT-A5 | compat reconciliation ausente | **P1** | drift SteamOS/Client | tabela `compat_fact` | serviço na inicialização | FM-10 verde |
| DEBT-A6 | integrações externas incompletas | **P1** | recursos não prontos para uso real | fakes e contratos | testes fim a fim | matriz externa verde |
| DEBT-A7 | M10 sem mutação em VM | **P1** | adapters não certificados | portas fake | VM real | três ciclos completos |
| DEBT-B1–B4 | observabilidade/UX/escala interna | **P3** | manutenção e UX | funcionalidade básica | incremental | testes específicos |

## Tabela 3 — Ondas de execução

| Onda | Objetivo | Entregas | Critério de saída |
|--:|---|---|---|
| 0 | Certificação física da a39 | GAP-G18 | **CONCLUÍDA** — rollback convergido e tag criada |
| 1 | Fundação de temas | 388 propriedades, fechamento P0-03 | cobertura 100%, nenhuma perda silenciosa |
| 2 | UI e acessibilidade | scene tree, texto avançado, GAP-G12/GAP-G13/GAP-G15 | gate visual completo, foco estável |
| 3 | Operação e adapters | GAP-G16, GAP-G17, GAP-G20, M10, M11 | três emuladores e frontends certificados |
| 4 | Hardware | Deck/dock/input/suspend/storage/TDP | rótulo `verified-hw` real |
| 5 | Game Mode | M12 + P0-08 necessário | navegação 100% por controle |
| 6 | Adoção e distribuição | M13, M14 | import sem perda, downgrade demonstrado |
| 7 | Estabilização | RCs, segurança, performance, docs | zero bloqueador aberto |
| 8 | Release 1.0 | M15 | checklist integral, SBOM, assinaturas |


## Tabela 4 — Matriz de rastreabilidade do Expansion Ledger

Reconciliada com `docs/EXPANSION-LEDGER.md` em 2026-07-29. A presença do nome
de um contrato não é usada como sinônimo de implementação: `LEDGER-A7`, por
exemplo, já tem `MediaRegistry` e o pipeline `masters → optimized → views`,
embora `media-registry-v1` ainda não exista como contrato público; `LEDGER-G4`
tem LSFG funcional, mas não OptiScaler nem o contrato multi-provider.

`requisito → implementação → contrato → teste → evidência → milestone`

### Fundações

| WI | Requisito | Implementação/contrato | Evidência | Destino | Estado reconciliado |
|---|---|---|---|---|---|
| `LEDGER-F0` | Baseline de qualidade | `error-v1` presente | `WI-F0.md` | transversal | verified-dev |
| `LEDGER-F1` | `core.net` seguro e limitado | `core.net` presente | `WI-F1.md` | transversal | verified-dev |
| `LEDGER-F2` | Hashes, assinatura e envelopes | `core.crypto` presente | `WI-F2.md` | M14/M15 | verified-dev |
| `LEDGER-F3` | Jobs/operações paginados e `--follow` | `event-v1` presente | `WI-F3.md` | M11/M12 | verified-dev |
| `LEDGER-F4` | Daemon persistente e CLI compatível | API local presente | `WI-F4.md` | M11 | verified-dev |
| `LEDGER-F5` | Registry de plataformas/capacidades | `platform-manifest-v1` presente | `WI-F5.md` | M10/M12 | verified-dev |
| `LEDGER-F6` | Perfis de input reversíveis | `retro-input-profile-v1` presente | `WI-F6.md` | M12 | verified-dev |

### Produto e gaming tools

| WI | Requisito | Implementação/contrato | Evidência | Destino | Estado reconciliado |
|---|---|---|---|---|---|
| `LEDGER-A1` | Playtime, sessões interrompidas, continuar jogando | `feat-playtime-v1` presente | `WI-A1.md` + testes | M8 | verified-dev |
| `LEDGER-A2` | Histórico e rollback contextual | `feat-operation-history-v1` presente | `WI-A2.md` + testes | M8 | verified-dev |
| `LEDGER-A3` | Tags, favoritos e coleções | `feat-collection-v1` presente | `WI-A3.md` + testes | M8 | verified-dev |
| `LEDGER-A4` | Anti-bitrot e estado `suspect` | `feat-bitrot-v1` presente | `WI-A4.md` + testes | M8 | verified-dev |
| `LEDGER-A5` | Plataformas cloud e atalhos reversíveis | `platform-manifest-v1` presente | `WI-A5.md` + testes | M11 | verified-dev |
| `LEDGER-A6` | Sessões co-op por QR | sem domínio, contrato ou teste | — | pós-M12 | backlog-protected |
| `LEDGER-A7` | MediaHub `masters → optimized → views` | pipeline e registry internos presentes; contrato público ausente | `media_pipeline.py`, `media_registry.py`, testes de mídia | M13 | partial |
| `LEDGER-A8` | Patches IPS/BPS/xdelta imutáveis | apenas sufixos de mods; operação de patch ausente | — | M13 | pending |
| `LEDGER-A9` | RetroAchievements offline/hardcore | domínio e contrato ausentes | — | M13 | pending |
| `LEDGER-A10` | Reserva compatível do catálogo | reserva no payload de capacidades | ledger | M14 | pending |
| `LEDGER-A11` | Ports/homebrew reproduzíveis | catálogo de produto ausente (`ports.py` contém Protocols, não ports) | — | M13 | pending |
| `LEDGER-A12` | Scraper hash-first/DAT/fuzzy/cache/seed | providers/cache existem; contrato MediaHub e fluxo completo faltam | testes de scraping | M13 | partial |
| `LEDGER-G0` | Evidência HUD 1280×800 | `gtool-hud-v1` presente | `WI-G0.md` | M12 | verified-offscreen |
| `LEDGER-G1` | MangoHud por jogo e rollback | presente | `WI-G1.md` + testes | M12 | verified-dev |
| `LEDGER-G2` | Ambiente de lançamento puro | `gtool-launch-environment-v1` presente | `WI-G2.md` + testes | M12 | verified-dev |
| `LEDGER-G3` | vkBasalt por jogo | presente | `WI-G3.md` + testes | M12 | verified-dev |
| `LEDGER-G4` | LSFG/OptiScaler multi-provider | LSFG pinado, reversível e testado; OptiScaler e `gtool-framegen-v1` ausentes | `lsfg.py`, launcher e testes | M12 | partial |
| `LEDGER-G5` | Captura, galeria e orçamento | screencast não satisfaz screenshot/replay/galeria; capacidade ausente | — | M12 | pending |
| `LEDGER-G6` | Benchmark por jogo/perfil | benchmark de produto e `benchmark-v1` ausentes | — | M12 | pending |

### Experiência retro

| WI | Requisito | Implementação/contrato | Evidência | Destino | Estado reconciliado |
|---|---|---|---|---|---|
| `LEDGER-R0` | Integer scaling e sharp-bilinear | `retro-integer-scaling-v1` presente | `WI-R0.md` | M12 | verified-dev |
| `LEDGER-R1` | Presets Como era/Equilibrado/Melhorado | três presets e contrato presentes; 4 políticas ready, 7 planned | WORKLOG sessão 57 + testes | M12 | verified-dev; ledger stale |
| `LEDGER-R2` | PAR, cores, shaders e RF→RGB | campos declarados como `planned`, sem aplicação | `retro_experience.py` | M12 | partial |
| `LEDGER-R3` | Timing, DRC, PAL/NTSC e overclock | campos declarados como `planned`, sem aplicação | `retro_experience.py` | M12 | partial |
| `LEDGER-R4` | TATE transacional e recovery | ausente | — | M12 | pending |
| `LEDGER-R5` | Áudio por dispositivo/chip/EQ | ausente | — | M12 | pending |
| `LEDGER-R6` | Controles especializados automáticos | perfis base existem; automação especializada incompleta | input profiles | M12 | partial |
| `LEDGER-R7` | Latência/torneio/netplay/3D | ausente | — | M12 | pending |
| `LEDGER-R8` | Registry compartilhado de shaders/bezels | contrato MediaHub ausente | — | M13 | pending |

### Compartilhamento de tela

| WI | Requisito | Implementação/contrato | Evidência | Destino | Estado reconciliado |
|---|---|---|---|---|---|
| `LEDGER-S0` | Fundação multi-provider | `screen-cast-v1` presente | `WI-S0.md` | M12 | verified-dev |
| `LEDGER-S1` | Game-stream local reversível | `GameStreamProvider`, receiver web e testes presentes | WORKLOG WI-S1 | M12 | verified-dev; ledger stale |
| `LEDGER-S2` | Motor fora do processo e comandos idempotentes | `CastEngine` IPC presente; `WI-S2.md` hoje descreve internet/TURN e precisa de novo ID | testes IPC | M12 | partial + docs conflict |
| `LEDGER-S3` | UI de um toque por gamepad/overlay | rotas e cartões existem; jornada física por controle não certificada | QML/offscreen | M12 | partial |
| `LEDGER-S4` | Steam Remote Play | somente enum de protocolo | — | pós-M12 | pending |
| `LEDGER-S5` | Screen mirror | somente enum de protocolo | — | pós-M12 | pending |
| `LEDGER-S6` | Media cast | somente enum de protocolo | — | pós-M12 | pending |
| `LEDGER-S7` | Retorno de gamepad e monitor virtual | ausente | — | pós-M12 | pending |
| `LEDGER-B0` | Web UI LAN/família/comunidade | explicitamente não implementar | ledger | pós-1.0/ADR | backlog-protected |

### Resolução dos dez achados de emulação

| WI | Estado do ledger | Destino protegido |
|---|---|---|
| `LEDGER-D1` | verified-dev | emulador principal e fallback por plataforma |
| `LEDGER-D2` | pending | DLC/update: F5 + A4 + A8 |
| `LEDGER-D3` | verified-dev | mods/cheats e conversão já conectados |
| `LEDGER-D4` | pending | G1/G3/G4/G6 + R0–R2 |
| `LEDGER-D5` | in-progress | F6 + R6 |
| `LEDGER-D6` | in-progress | A1 + G5 |
| `LEDGER-D7` | in-progress | F1/F5 + A7/A12 |
| `LEDGER-D8` | in-progress | A7 + A8 |
| `LEDGER-D9` | pending | A4 + A7 |
| `LEDGER-D10` | pending | F5/A4/A12 |

### O que a reconciliação revelou

O ledger não perdeu apenas nomes: ele ficou **stale** onde o código avançou.
`LEDGER-R1` e `LEDGER-S1` já têm entrega verificável; `LEDGER-A7`,
`LEDGER-A12`, `LEDGER-G4`, `LEDGER-R2/R3/R6` e `LEDGER-S2/S3` são parciais,
não ausentes. Em sentido oposto, enums de `LEDGER-S4/S5/S6` não constituem
providers funcionais.

Os contratos públicos ainda ausentes são `co-op-session-v1`,
`media-registry-v1`, `patch-operation-v1`, `achievement-v1`,
`port-catalog-v1`, `gtool-framegen-v1` e `benchmark-v1`. A ausência do contrato
não apaga código parcial já existente, mas impede declarar o WI concluído.

### Ordem de retomada funcional

Com `GAP-G18` e `GAP-G19` fechados e a a39 certificada, a próxima correção
funcional é `GAP-G20`. Depois dela:

| onda | WIs |
|---|---|
| verdade operacional e adapters | `GAP-G16`, `GAP-G17`, M10, M11, `DEBT-A5`, `DEBT-A7` |
| mídia, scraping, patches, achievements | `LEDGER-A7`, `LEDGER-A12`, `LEDGER-A8`, `LEDGER-A9` |
| retro, performance, captura, controles | `LEDGER-R2`–`LEDGER-R8`, `LEDGER-G4`–`LEDGER-G6`, `LEDGER-A11` |
| P0-03, scene tree, acessibilidade, M12 | corpus 388, `GAP-G12`, `GAP-G13`, `GAP-G15`, `LEDGER-S2`–`LEDGER-S7` |
| matriz física e boot | `DEBT-A0`, `GAP-G11` |
| adoção e distribuição | M13, M14, `LEDGER-A10`, `LEDGER-A6` |
| 1.0 | M15 |

## Detalhamento das próximas três entregas

### PR 2 — `fix/host-rollback-convergence` (P0, fecha GAP-G18) — **implementado e certificado**

**Correção de rota.** A primeira versão deste plano propunha "convergir antes de
trocar `current`". Está errado, e a revisão pegou: o `ExecStart` da unit é
`/opt/steamzero/current/venv/bin/steamzero-core`, então reiniciar antes da troca
sobe **de novo a release antiga**. Verificado no host:

```
ExecStart = /opt/steamzero/current/venv/bin/steamzero-core --systemd
```

Foi selecionada a estratégia compatível com esse contrato:

**Verificador independente da release ativa.** O gerenciador
`/usr/local/sbin/steamzero-host`, já publicado pelo instalador fora de `current`,
ganha o comando user-scoped `converge`. Ele pergunta ao daemon quem está
executando e compara com o alvo. Não depende da CLI da release ativa — que é
justamente o que falta na a37.

Releases modernas comprovam `releaseId` e `sourceCommit`; a a37, anterior à
identidade completa, comprova `daemonVersion`, PID e o executável real em
`/proc/<pid>/exe`. A implementação passou na repetição física
`a39→a37→a39`: uma tentativa em cada direção e zero tentativas nas repetições
idempotentes.

- **Exclui:** motor de temas, UI, wheelhouse.
- **Testes:** encenar rollback a38→a37 com daemon a38 vivo e exigir detecção
  **por um caminho que não seja a CLI da a37**; provar que o verificador
  funciona quando a release ativa não tem o comando.
- **Testes de falha:** daemon que não morre; unit que sobe o binário errado;
  `current` trocado sem restart; verificador ausente.
- **Evidência:** `pgrep -af steamzero-core`, `readlink -f current`, JSON do gate.
- **Risco de regressão:** alto — mexe na ordem de ativação. Mitigar com
  encenação sem systemd, como o HOST-ACTIVATION-01 já faz.
- **Rollback:** a a37 permanece instalada e ativável.
- **Dependência satisfeita:** PR 1 (GAP-G19). Os caminhos de falha agora são
  observáveis e testáveis pelos códigos públicos do catálogo.

### PR 1 — `fix/host-error-catalog` (P1, fecha GAP-G19) — **implementado**

- **Inclui:** registrar `E-HOST-RELEASE-MISMATCH`, `E-HOST-DAEMON-PENDING`,
  `E-HOST-CONVERGENCE-TIMEOUT`, `E-HOST-RESTART-FAILED`,
  `E-HOST-CURRENT-UNREADABLE` no catálogo.
- **Exclui:** mudar a lógica de convergência.
- **Testes:** um por código, atravessando a CLI e `build_error` — não só
  `converge()`. Foi exatamente essa lacuna que deixou o defeito passar.
- **Testes de falha:** código novo sem registro deve reprovar o build.
- **Risco de regressão:** baixo.

### PR 3 — `fix/emulation-workspace-reads-host` (P1, fecha GAP-G20)

O diagnóstico ficou mais preciso: **não é argumento faltando, são duas
implementações do mesmo read model.** `EmulationController` já compõe a versão
completa — `keys`, `firmware`, `games`, `emulator_facts`, `core_present`, mais
merge de plataformas de nuvem, linhas de emulador e resolução do emulador
padrão. A CLI mantém uma segunda, parcial, com só `probe`.

- **Inclui:** a CLI passa a **reusar a composição do `EmulationController`**.
  Acrescentar argumentos à segunda implementação só adiaria a próxima
  divergência.
- **Exclui:** mudar o contrato do read model ou a UI.
- **Testes:** com chaves e biblioteca presentes, o workspace precisa refletir;
  teste que **falha se a CLI voltar a compor por conta própria** — a forma como
  o defeito nasceu. Cobrir explicitamente `keys`, `firmware`, `games`,
  `emulator_capabilities`, `emulator_facts` e `core_present`.
- **Evidência:** comparar antes/depois com `prod-*.keys` e 15 jogos em cache.
- **Risco de regressão:** médio — muda o que a página de emulação mostra.
- **Rollback:** trivial, o handler é isolado.

## Bloqueadores abertos

| # | Bloqueador | Prio | Impede |
|---|---|---|---|
| GAP-G20 | workspace não lê o host | P1 | página de emulação utilizável |
| DEBT-A0, GAP-G11 | matriz física e boot direto | P0 | `verified-hw` e M15 |

## O que NÃO pode ser declarado

Com M10–M15 pendentes e a matriz física incompleta, o projeto **não** é
"completo", **não** está em "produção" e **não** tem rótulo `verified-hw`. A
a39 tem a mecânica de release certificada nas duas direções. Isso fecha o risco
operacional G18, mas não substitui os marcos funcionais e físicos ainda abertos.
