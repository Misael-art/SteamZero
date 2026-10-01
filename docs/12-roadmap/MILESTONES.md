# MILESTONES — marcos verificáveis

A execução atual segue [IMPLEMENTATION-ROADMAP](IMPLEMENTATION-ROADMAP.md), lotes RC-00–08 com prioridade V1–V4 após B_VISUAL 133/134 (01/10/2026). Os marcos abaixo são critérios de produto, não autorização para reimplementar fundações existentes. O estado atual está nos cinco eixos do catálogo.

Complexidade em T-shirt (S/M/L/XL) — sem datas (dependem de Q6/Q10 e capacidade de equipe; estimar em sprints na aprovação).

| # | Marco | Fase | Complexidade | Demonstração objetiva |
|---|---|---|---|---|
| M1 | "Kill-proof core": pipeline transacional sobrevive a SIGKILL em toda etapa | 1 | L | suíte FI-04 verde em CI |
| M2 | CLI contratada: `steamzero` com envelope v2 + golden files | 1 | M | `steamzero doctor --json` validado por schema |
| M3 | Jobs resilientes: pausa/resume/cancel/reboot-recovery | 1 | L | demo gravável de reboot no meio de job |
| M4 | Deck-aware: modos + fallback de display + microSD UUID em VM | 2 | L | FI-07/12 verdes |
| M5 | Helper privilegiado auditado | 2 | M | ST-01 fuzzing verde |
| M6 | Sessão segura: suspend/resume com checkpoint (VM) | 2 | L | FI-09 verde |
| M7 | Biblioteca transacional: scan→plan→apply→rollback com 10k fixtures | 3 | L | RT-06/07 + benchmark funcional (tempo publicado via JUnit, não como gate) |
| M8 | BIOS center backend + saves timeline | 3 | M | AC-BI/SV verdes |
| M9 | Sync não-destrutivo com conflito preservador | 3 | L | J6 automatizada |
| M10 | Engine de adapters + 3 emuladores núcleo fim-a-fim | 4 | XL | instalar/atualizar/rollback DuckStation/RetroArch/Dolphin em VM |
| M10-H | Handheld Desktop BigLinux/KDE autônomo e resiliente | 4 | L | status/plan/apply/recovery no Deck; zero dependência legada; UI QML navegável |
| M11 | Frontends: Steam shortcuts + SRM + ES-DE sem duplicação | 4 | L | idempotência 2× verificada |
| M12-E | Theme Engine declarativa e GPU-first | 5 | XL | um asset gera variantes e cenas responsivas a 60 FPS medidos no Deck, com fallback seguro |
| M12-S | Theme Studio visual e reproduzível | 5/6 | XL | criar→preview→exportar→importar→reabrir sem perda, com validação e sem editor externo |
| M12 | AURA Launcher fullscreen navegável 100% por controle (home+biblioteca+jogo+retorno) | 5 | XL | focus graph verde + ciclo físico controle→jogo→retorno com capturas da release instalada |
| M13 | Adoção EmuDeck/RetroDECK em máquina real de teste | 5 | L | relatório de import sem perda (hashes) |
| M14 | Flatpak + canais + update/rollback da plataforma | 6 | L | RT-14 verde; downgrade demonstrado |
| M15 | Release 1.0 stable com SBOM/assinaturas + docs de usuário | 6 | M | checklist §17 completo com hardware (Q6) |

## Fotografia histórica — 2026-09-22 (não usar como estado atual)

| Marco | Estado real | Bloqueio que governa a próxima ação |
|---|---|---|
| M10 | parcial / instalado | Componentes e rotas foram exercitados, mas first-run e handoff PCSX2 ainda impedem lançamento confiável (G49/G50). |
| M11 | parcial / degradado | ES-DE e SRM não estão instalados; RetroFE não tem pacote lançável no host (G54). |
| M12-E | parcial / degradado | Tokens, receitas e cenas existem; a superfície ativa não prova todas as capacidades dinâmicas nem medição física de custo. |
| M12-S | parcial / degradado | Theme Studio salva/exporta tokens e layout; `EffectSpec` ainda é somente observável e o preview tem timeout (G53). |
| M12 | bloqueado pela jornada | A release anterior aborta com um catálogo Vita supercontado (684 falsos assets); o scanner foi corrigido localmente para reconhecer os 5 ZIPs reais, mas release, ativação e fade/retorno físicos permanecem sem prova (G48). |
| M13 | não promovível | Scan da release anterior mistura jogos e assets internos Vita; após a correção, extração, renomeação, normalização, conversão e resolução de duplicidades ainda não foram aplicadas em ROM real (G51). |
| M14/M15 | não promover | A instalação governada existe, mas a certificação funcional exige fechar os gates acima e repetir a matriz física completa. |

O progresso acima é um retrato de fechamento, não substitui os cinco eixos dos
itens de status. Os relatórios detalhados permanecem apenas como evidência
operacional; novas decisões devem atualizar o item canônico e o workstream
correspondente.

## Continuidade após auditoria — 2026-09-26

| Marcos | Entregas atuais | Condição para promoção |
|---|---|---|
| M1–M3 | RC-02/03 e regressões transacionais | Preservar fundações existentes; comprovar cancelamento, crash/recovery e integridade nas novas jornadas |
| M4–M6, M10-H | RC-04 e plano Steam Session | Prova no dispositivo/modo exigido, ownership e restauração; desktop genérico não certifica Deck |
| M7–M9, M13 | RC-02/03/07 | Catálogo, BIOS, extração, multidisco, saves, sync e migração com origens preservadas |
| M10–M11 | RC-04/05 | Runtime/frontend real, first-run e portal, launch/return e reexecução idempotente |
| M12 | RC-01/03/05 | Controle→jogo→retorno na release atual; OSD pausado, fade, disco/save e foco; Cinema medido no alvo |
| M12-E/M12-S | RC-06 | DoD separado de Engine e Studio, autoria física e round-trip reproduzível |
| M14–M15 | RC-08 | Gates completos, distribuição, atualização/rollback e certificação física do escopo aprovado |

O scan de 26/09 reconheceu 1.163 registros; a antiga descrição de bloqueio Vita
não deve orientar uma nova implementação sem reprodução. A instalação observada
é `2.0.0rc1-e2af2562ebba`, posterior à fotografia acima. Não há promoção global
dos marcos neste ajuste documental. Evidência histórica de pausa/bezel/save-state
continua válida para sua release; não certifica automaticamente o tip atual.


## Próximas demonstrações de produto — 01/10/2026

A fila detalhada está no roadmap; os critérios originais de M12/M12-E/M12-S
continuam obrigatórios. Nenhum marco é promovido nesta revisão.

| Entrega vigente | Marco relacionado | Demonstração útil |
|---|---|---|
| V1 | AURA UI / recorte de M12 | Componentes e modais legíveis, foco/alvos consistentes, conflito explicado e recuperação na própria jornada |
| V2 | M12-E + consumidor M12 | Cena builtin/portada resolve dados e renderiza no consumidor correto, com isolamento sintético e fallback |
| V3 | Recorte de M12-S | Usuário cria/edita, desfaz/refaz, salva/reabre e exporta/importa pacote que executa em V2 |
| V4 | DoD restante M12-E/M12-S | Efeitos/timeline/bindings e tiers editáveis/persistentes, validadores e medição de custo no hardware |

A medição de ritmo do render loop não certifica FPS apresentado. Aplicar os
métodos atuais do item de Theme Engine e registrar qualquer divergência de
instrumentação com a spec. Gameplay/retorno, saves, bezel e multidisco exigem
provas próprias de M12/RC-03, não apenas uma cena bem renderizada.
