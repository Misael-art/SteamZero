# Plano de execução até a 1.0

**Base:** commit `3c43f25a`, host em `0.1.0a38-48f4034dfe36` (certificação
**parcial** — ver `docs/09-operations/A38-CERTIFICATION-RESULT.md`).

Este documento não copia estado antigo. Cada linha foi conferida contra o
código, os testes ou o host nesta sessão; onde não foi possível verificar, está
dito.

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
| 0 | Certificação física a38 | **parcial** — instala, converge, roll-forward ok; rollback deixa daemon stale | G18, G19 | ciclo completo com rollback convergido | P0 | fechar G18 e G19 |
| 1 | Fechar P0-03 | **parcial** — a fatia traduz 11 atributos de texto; corpus tem 388 propriedades | a38 certificada | 388 migradas, cobertura 100%, relatório | P1 | migrar corpus por família |
| 2 | Árvore de cena e texto avançado | **não iniciado** — `children` não existe no contrato (verificado: 0 ocorrências) | P0-03 | children, wrapping, elide, rich text, auto-fit com gates | P1 | especificar por slices |
| 3 | Acessibilidade real | **infraestrutura pronta, sem consumidor** (G15) | tipografia/layout | textScale, reducedMotion, highContrast consumidos de verdade | P1 | fechar G12 e G15 |
| 4 | Migração dos harnesses QML | **pendente** — 3 `skipif` restantes no arquivo legado | harness canônico | zero skip no gate visual | P2 | fechar G13 |
| 5 | Estabilidade operacional | **parcial** — G16 intermitente, G17 ausente, G19 novo | CI/host | causa do flake diagnosticada, `service status` público | P1 | PRs isoladas |
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
| **G18** | rollback deixa daemon stale, sem gate na release anterior | **P0** | reproduz a regressão da a37; release "revertida" continua servindo código novo | nenhuma | convergir ANTES de trocar `current`, ou verificador independente de release | rollback com daemon convergido |
| **G19** | códigos `E-HOST-*` fora do catálogo | **P1** | falha do gate vira erro interno genérico | nenhuma | registrar os cinco códigos | teste que atravessa `build_error` |
| **G20** | `emulation workspace` não lê estado real | **P1** | chaves e 15 jogos válidos aparecem como ausentes | nenhuma | ligar o handler ao estado XDG | teste que falha se um argumento sumir |
| G5/A0 | matriz física incompleta | **P0** | impede rótulo `verified-hw` | operações read-only | validar Deck LCD/OLED/dock | matriz física verde |
| G7 | inventário fino de assets | **P1** | risco legal na redistribuição | não redistribuir | inventário item a item | notices completos |
| G11 | boot direto não certificado | **P0** | risco de boot no greeter | sessão manual + fallback Plasma | protocolo físico com recovery | ciclos de falha/recovery |
| G12 | escala de texto ignorada | **P1** | acessibilidade incompleta | fontes fixas | helper tipográfico central | layouts e foco verdes |
| G13 | 3 `skipif` no arquivo legado | **P2** | falso verde possível | não contam como gate | migrar para o harness canônico | zero skip visual |
| G14 | ~~baselines não versionadas~~ | — | **FECHADA** em `6fb2a75` | — | — | — |
| G15 | geração de acessibilidade sem consumidor | **P2** | invalidação seletiva não provada | infraestrutura pronta | consumidor real | recomputação seletiva medida |
| G16 | `test_controls_*` intermitente | **P2** | CI não determinístico | rerun (3× local passou) | diagnosticar a causa | 100 execuções sem falha |
| G17 | sem `service status --json` | **P2** | observabilidade incompleta | refresh + doctor + host status | comando público | contrato e testes |
| G21 | 46 warnings QML do Breeze | **P3** | polui coleta de warnings próprios | — | filtrar por origem | coleta só de QML nosso |
| G8 | matriz SteamOS/Steam Client | **P2** | compatibilidade desconhecida | estado observado | serviço de reconciliação | FM-10 verde |
| A1 | ENOSPC mid-apply não testado | **P1** | rollback sob disco cheio incerto | preflight | loopback/quota | FI real verde |
| A2 | dry-run sem `strace` | **P2** | ausência de writes não provada por syscall | asserção de estado | harness strace | zero writes observado |
| A5 | compat reconciliation ausente | **P1** | drift SteamOS/Client | tabela `compat_fact` | serviço na inicialização | FM-10 verde |
| A6 | integrações externas incompletas | **P1** | recursos não prontos para uso real | fakes e contratos | testes fim a fim | matriz externa verde |
| A7 | M10 sem mutação em VM | **P1** | adapters não certificados | portas fake | VM real | três ciclos completos |
| B1–B4 | observabilidade/UX/escala interna | **P3** | manutenção e UX | funcionalidade básica | incremental | testes específicos |

## Tabela 3 — Ondas de execução

| Onda | Objetivo | Entregas | Critério de saída |
|--:|---|---|---|
| 0 | Fechar a certificação da a38 | G18, G19 | rollback com daemon convergido; tag criada |
| 1 | Fundação de temas | 388 propriedades, fechamento P0-03 | cobertura 100%, nenhuma perda silenciosa |
| 2 | UI e acessibilidade | scene tree, texto avançado, G12/G13/G15 | gate visual completo, foco estável |
| 3 | Operação e adapters | G16, G17, G20, M10, M11 | três emuladores e frontends certificados |
| 4 | Hardware | Deck/dock/input/suspend/storage/TDP | rótulo `verified-hw` real |
| 5 | Game Mode | M12 + P0-08 necessário | navegação 100% por controle |
| 6 | Adoção e distribuição | M13, M14 | import sem perda, downgrade demonstrado |
| 7 | Estabilização | RCs, segurança, performance, docs | zero bloqueador aberto |
| 8 | Release 1.0 | M15 | checklist integral, SBOM, assinaturas |

## Detalhamento das próximas três entregas

### PR 1 — `fix/host-rollback-convergence` (P0, fecha G18)

- **Inclui:** convergência verificável em rollback. A ordem correta é convergir
  o daemon **antes** de trocar `current`, ou publicar um verificador que não
  dependa da CLI da release ativa.
- **Exclui:** qualquer mudança no motor de temas, na UI ou no wheelhouse.
- **Testes:** encenar rollback a38→a37 com daemon a38 vivo e exigir detecção;
  provar que a release anterior consegue ser verificada por um caminho que não
  seja a CLI dela.
- **Testes de falha:** daemon que não morre; unit que reinicia no binário
  errado; `current` trocado sem restart.
- **Evidência:** `pgrep -af steamzero-core`, `readlink -f current`, JSON do gate.
- **Risco de regressão:** alto — mexe na ordem de ativação. Mitigar com
  encenação sem systemd, como o HOST-ACTIVATION-01 já faz.
- **Rollback:** a a37 permanece instalada e ativável.

### PR 2 — `fix/host-error-catalog` (P1, fecha G19)

- **Inclui:** registrar `E-HOST-RELEASE-MISMATCH`, `E-HOST-DAEMON-PENDING`,
  `E-HOST-CONVERGENCE-TIMEOUT`, `E-HOST-RESTART-FAILED`,
  `E-HOST-CURRENT-UNREADABLE` no catálogo.
- **Exclui:** mudar a lógica de convergência.
- **Testes:** um por código, atravessando a CLI e `build_error` — não só
  `converge()`. Foi exatamente essa lacuna que deixou o defeito passar.
- **Testes de falha:** código novo sem registro deve reprovar o build.
- **Risco de regressão:** baixo.

### PR 3 — `fix/emulation-workspace-reads-host` (P1, fecha G20)

- **Inclui:** ligar `_cmd_emulation_workspace` ao estado XDG real — chaves,
  firmware, biblioteca, capabilities.
- **Exclui:** mudar o contrato do read model ou a UI.
- **Testes:** com chaves e biblioteca presentes, o workspace precisa refletir;
  teste que **falha se um argumento for removido** da chamada, que é a forma
  como o defeito nasceu.
- **Evidência:** comparar antes/depois com `prod-*.keys` e 15 jogos em cache.
- **Risco de regressão:** médio — muda o que a página de emulação mostra.
- **Rollback:** trivial, o handler é isolado.

## Bloqueadores abertos

| # | Bloqueador | Prio | Impede |
|---|---|---|---|
| G18 | rollback deixa daemon stale | P0 | tag `v0.1.0a38` |
| G19 | códigos fora do catálogo | P1 | diagnóstico confiável do gate |
| G20 | workspace não lê o host | P1 | página de emulação utilizável |
| G5/A0, G11 | matriz física e boot direto | P0 | `verified-hw` e M15 |

## O que NÃO pode ser declarado

Com M10–M15 pendentes e a matriz física incompleta, o projeto **não** é
"completo", **não** está em "produção" e **não** tem rótulo `verified-hw`. A
a38 tem mecânica de release certificada pela metade: instalação e roll-forward
provados, rollback não.
