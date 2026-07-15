# FOUNDATION-READINESS-REPORT — SteamZero

**Data:** 2026-07-15 · **Fase:** 0 (fundação documental) · **Classificação: `READY FOR PROTOTYPE`**

---

## 1. Resumo executivo

A fundação documental da plataforma consolidada de jogos e emulação para Steam Deck/Linux está completa: 99 documentos em `docs/` (visão, produto, pesquisa com evidências, arquitetura, segurança, dados, contratos de API, UX, testes, operações, migrações, legal, roadmap, 18 ADRs, glossário). Os quatro projetos foram auditados com evidência arquivo:linha. A síntese: **execução transacional do PhaseZero + plataforma/distribuição do RetroDECK + modularidade declarativa do LinuxToys + domínio/templates do EmuDeck**, tudo reimplementado sob o padrão defensivo do prompt mestre. Nenhum código de produção foi escrito; nenhum repositório de origem foi modificado.

A classificação **não** é `READY FOR IMPLEMENTATION` por dois bloqueadores documentais que só o responsável pode resolver (licença e aprovação formal) e duas lacunas declaradas (hardware de teste; clone integral do RetroDECK/components). Tudo o mais está definido em nível suficiente para iniciar a Fase 1 imediatamente após a aprovação.

## 2. Repositórios analisados

| Projeto | Fonte usada | Estado |
|---|---|---|
| PhaseZero | local `/mnt/sdcard/Projects/PhaseZero` @ `a0468ba` (pós v1.8.4) | completo; sem LICENSE |
| EmuDeck | **ausente localmente** → clone declarado `reference/EmuDeck` @ `71d4cdc` | completo (main) |
| LinuxToys | tarball local 6.4.3 + clone declarado `reference/linuxtoys` @ `89856ef` (6.4.4-prep) | completo |
| RetroDECK | **ausente localmente** → clone declarado `reference/RetroDECK` @ `d7c02e8` | completo (main) |
| RetroDECK/components | árvore via API (6.799 paths) + 5 arquivos representativos | **parcial** (G1) |

Detalhe: `docs/02-research/SOURCE-REPOSITORIES.md`.

## 3. Escopo coberto

Todas as capacidades do §6.2 do prompt mestre mapeadas (`CAPABILITY-MATRIX.md`, 30 linhas de capacidade × 4 projetos com evidências); jornadas J1–J9; contratos CLI/API/eventos/erros; modelo transacional, jobs, state, adapters, privilégio; UX Game Mode/Desktop/QAM com wireframes; plano de testes incluindo injeção de 20 falhas e protocolo de rollback do §13.6; operações (logs, doctor, bundle, canais, recovery); migrações (PhaseZero/EmuDeck/RetroDECK, preservação de dados); legal (matriz GPL, política de reuso).

## 4. Lacunas (todas classificadas em `docs/KNOWN-GAPS.md`)

G1 components parcial · G2 EmuDeck não-Linux não auditado (fora de escopo) · G3 PhaseZero-Windows por amostragem+doc interna · G4 zero testes dinâmicos (restrição da Fase 0) · G5 **zero validação em hardware** · G6 cloud sync não exercitado · G7 licenças de assets não inventariadas · G8 versões SteamOS da matriz · G9 PhaseZero sem LICENSE · G10 acessibilidade Godot não provada.

## 5. Matriz de capacidades — conclusão

Scores de robustez ponderados (critérios e pesos em `ROBUSTNESS-SCORE.md`): PhaseZero-linux **72**, RetroDECK **49**, LinuxToys **41**, EmuDeck **25**. Nenhum projeto entrega: job manager persistente, state store consultável, session manager de jogo, timeline de saves, conflito não-destrutivo, fila offline, transação generalizada, catálogo de erros — os 14 gaps estruturais estão em `GAP-ANALYSIS.md` e definem o valor novo do produto.

## 6. Arquitetura recomendada

Daemon Python por usuário (`steamzero-core`) com API JSON-RPC/UNIX socket em allowlist; núcleo transacional (scan→plan(confirmToken)→preview→backup→stage→apply→verify→activate→test→commit) com journal WAL; State SQLite + export JSON; adapters manifest-driven com engine única; helper privilegiado enum+polkit; Game Mode UI Godot 4 (condicionada a protótipo — ADR-0002); distribuição Flatpak híbrida (ADR-0003); Decky opcional (ADR-0008). Decisões com alternativas/prós/contras/riscos nos ADRs 0001–0018.

## 7. Riscos críticos (topo do RISK-REGISTER)

R-02 inflação de escopo (16) · R-01 licença indefinida (15) · R-03 atualizações Valve quebrando integrações (15) · R-04 Godot/acessibilidade (12) · R-05 sem hardware (12) · R-06 licenças upstream mudando (12, caso DuckStation) · R-07 sync corromper saves (10, mitigação por timeline preservadora).

## 8. Licenças

EmuDeck/LinuxToys/RetroDECK: GPL-3.0. PhaseZero: sem licença (titular = autor — Q3). **Bloqueio operativo:** zero cópia de código até ADR-0013 decidido; recomendação: GPL-3.0-or-later. Reimplementação por comportamento já é possível com esta fundação (REUSE-POLICY).

## 9. Backlog

`FEATURE-CATALOG.md` (52 features com origem conceitual e fase) + `ACCEPTANCE-CRITERIA.md` (28 ACs) + gaps GA-01..14.

## 10. Roadmap

Fases 0–6 (`IMPLEMENTATION-ROADMAP.md`) com critérios de saída objetivos e 15 marcos verificáveis (`MILESTONES.md`).

## 11. Estimativa de complexidade

Por marcos (T-shirt): 2×XL (engine de adapters; Game Mode UI), 7×L, 5×M, 1×S — concentração de risco técnico em M1 (kill-proof core) e M10 (adapters fim-a-fim). Estimativa em tempo depende de equipe/dedicação (definir na aprovação).

## 12. Dependências

Decisórias: Q1 (nome), **Q2 (licença — bloqueante)**, Q6 (hardware), Q10 (cadência) — `OPEN-QUESTIONS.md`. Técnicas: `DEPENDENCY-PLAN.md`.

## 13. Critérios de aprovação (§17) — autoavaliação

| Critério | Estado |
|---|---|
| Repositórios inventariados + ausências registradas | ✔ |
| Capacidades mapeadas | ✔ |
| Licenças analisadas | ✔ (decisão Q2 pendente — é decisão, não análise) |
| Arquitetura com limites claros | ✔ (verificáveis por lint) |
| Ameaças documentadas | ✔ (12 ameaças, mitigação+verificação) |
| Modelos transacional/jobs/adapters definidos | ✔ |
| Contratos CLI/API/schemas definidos | ✔ (rascunhos normativos; congelam em M2) |
| Erros com códigos estáveis | ✔ (catálogo inicial + governança) |
| UI com fluxos e wireframes | ✔ (6 wireframes-padrão + IA completa) |
| Acessibilidade especificada | ✔ (com risco G10 declarado) |
| Plano de testes completo | ✔ (20 FIs, 14 RTs, matriz HW/SW) |
| Matriz Steam Deck definida | ✔ definida / ✖ nenhuma célula verificada (G5) |
| Roadmap priorizado | ✔ |
| Riscos com responsáveis | ◐ papéis definidos; nomes na aprovação |
| ADRs das decisões | ✔ 18 (1 deliberadamente pendente: licença) |
| Pendências classificadas | ✔ (OPEN-QUESTIONS/ASSUMPTIONS/KNOWN-GAPS) |

## 14. Itens bloqueadores para `READY FOR IMPLEMENTATION`

1. **Q2/ADR-0013 (licença)** — decisão do titular.
2. **Aprovação formal** — `APPROVED_TO_IMPLEMENT` (arquivo) ou `APPROVED_TO_IMPLEMENT=true` (texto).
3. Q6 (hardware) — não bloqueia Fases 1/3 (VM-verificáveis), bloqueia release stable (M15).
4. G1 (clone components) — bloqueia apenas kickoff da Fase 4.

## 15. Recomendação

**Prosseguir**, na seguinte ordem: (1) decidir Q2 e Q1; (2) conceder aprovação formal; (3) iniciar Fase 1 (núcleo mínimo) + protótipos do ADR-0002 em paralelo; (4) providenciar hardware (Q6) até o fim da Fase 2. A fundação captura o comportamento dos quatro projetos com evidência suficiente para implementar mesmo no cenário de licença mais restritivo (reimplementação limpa).

---

*Nenhuma implementação será iniciada sem a aprovação formal descrita no item 14.2 — conforme §3.1 do prompt mestre.*
