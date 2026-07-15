# ADR-0013 — Licença do projeto (Q2)

**Status:** ACEITO (2026-07-15) — licença = **GPL-3.0-or-later**. Decisão do titular
registrada em `APPROVED_TO_IMPLEMENT` e no WORKLOG (Sessão 2). Libera reuso literal
de código GPL das referências sob a árvore de decisão da REUSE-POLICY.

## Contexto
EmuDeck/LinuxToys/RetroDECK: GPL-3.0. PhaseZero: sem licença (titular = autor). Ver 11-legal/LICENSE-MATRIX.md.

## Alternativas
1. **GPL-3.0-or-later (recomendada)** — prós: permite derivar dos três projetos; alinhamento com o ecossistema (emuladores majoritariamente GPL); reciprocidade protege o projeto; contras: obriga fonte aberta de derivados; incompatível com monetização proprietária futura.
2. Permissiva (MIT/Apache-2.0) — prós: flexibilidade; contras: **zero cópia** dos três projetos (só reimplementação por comportamento — custo alto na Fase 4 para templates EmuDeck); risco de forks proprietários.
3. Proprietária — idem 2 + fecha contribuição comunitária (o motor dos três projetos de referência).

## Riscos de não decidir
R-01 (exposição 15). Fase 1 pode começar limpa (código 100% novo), mas a Fase 4 (templates) trava.

## Decisão
**Opção 1 — GPL-3.0-or-later.** Escolhida pelo titular em 2026-07-15 junto da
aprovação formal de implementação. Q3 (licenciar o PhaseZero atual) permanece
recomendação aberta; não bloqueia, pois a fundação captura o comportamento e a
reimplementação limpa já é possível.

## Consequências (decidida)
- `LICENSE` na raiz = texto canônico GPLv3 (FSF), sha256 `3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986`.
- Cabeçalhos SPDX `GPL-3.0-or-later` em todo arquivo de código.
- `pyproject.toml` declara `license = "GPL-3.0-or-later"`.
- REUSE-POLICY: casos "derivação GPL" liberados (EmuDeck templates); casos "NÃO
  copiar" (eval/sem strict) permanecem por não atenderem SECURITY-REQUIREMENTS.

## Revisão
Fechado. Reabrir apenas se houver decisão de relicenciar (exigiria novo ADR).
