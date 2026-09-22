# MILESTONES — marcos verificáveis

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

## Estado real dos marcos após a auditoria do host — 2026-09-22

| Marco | Estado real | Bloqueio que governa a próxima ação |
|---|---|---|
| M10 | parcial / instalado | Componentes e rotas foram exercitados, mas first-run e handoff PCSX2 ainda impedem lançamento confiável (G49/G50). |
| M11 | parcial / degradado | ES-DE e SRM não estão instalados; RetroFE não tem pacote lançável no host (G54). |
| M12-E | parcial / degradado | Tokens, receitas e cenas existem; a superfície ativa não prova todas as capacidades dinâmicas nem medição física de custo. |
| M12-S | parcial / degradado | Theme Studio salva/exporta tokens e layout; `EffectSpec` ainda é somente observável e o preview tem timeout (G53). |
| M12 | bloqueado pela jornada | O catálogo completo excede 512 itens, a ativação reduzida não produz launch e fade/retorno físico permanecem sem prova (G48). |
| M13 | não promovível | Scan identifica o acervo, mas extração, renomeação, normalização, conversão e resolução de duplicidades ainda não foram aplicadas em ROM real (G51). |
| M14/M15 | não promover | A instalação governada existe, mas a certificação funcional exige fechar os gates acima e repetir a matriz física completa. |

O progresso acima é um retrato de fechamento, não substitui os cinco eixos dos
itens de status. Os relatórios detalhados permanecem apenas como evidência
operacional; novas decisões devem atualizar o item canônico e o workstream
correspondente.
