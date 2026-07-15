# ADR-0013 — Licença do projeto (Q2)

**Status:** PENDENTE DE DECISÃO DO TITULAR (bloqueia reuso de código; não bloqueia reimplementação)

## Contexto
EmuDeck/LinuxToys/RetroDECK: GPL-3.0. PhaseZero: sem licença (titular = autor). Ver 11-legal/LICENSE-MATRIX.md.

## Alternativas
1. **GPL-3.0-or-later (recomendada)** — prós: permite derivar dos três projetos; alinhamento com o ecossistema (emuladores majoritariamente GPL); reciprocidade protege o projeto; contras: obriga fonte aberta de derivados; incompatível com monetização proprietária futura.
2. Permissiva (MIT/Apache-2.0) — prós: flexibilidade; contras: **zero cópia** dos três projetos (só reimplementação por comportamento — custo alto na Fase 4 para templates EmuDeck); risco de forks proprietários.
3. Proprietária — idem 2 + fecha contribuição comunitária (o motor dos três projetos de referência).

## Riscos de não decidir
R-01 (exposição 15). Fase 1 pode começar limpa (código 100% novo), mas a Fase 4 (templates) trava.

## Decisão
Aguardando `APPROVED_TO_IMPLEMENT` + escolha explícita. Recomendação técnica registrada: opção 1, com Q3 (licenciar PhaseZero atual, ao menos dual-license do `linux/` para o titular reusar formalmente).

## Consequências (quando decidida)
Atualizar LICENSE, SPDX headers, ATTRIBUTION-PLAN, REUSE-POLICY casos classificados.

## Revisão
Na aprovação da fundação.
