# ADR-0006 — Adapters manifest-driven com engine única

**Status:** aceito

## Contexto
EmuDeck: 31 scripts quase-clones por emulador (cobertura excelente, manutenção O(n)). RetroDECK components: manifest+recipe+scripts por componente (declarativo parcial). LinuxToys: metadados em cabeçalho + libs comuns (mínimo viável). PhaseZero: wrappers por ferramenta.

## Problema
Cada emulador novo não pode custar um script de 400 linhas copiado; e nenhum dado externo pode escolher código a executar (§5.1).

## Alternativas
1. **Engine única + adapter.json declarativo + hooks Python restritos** (escolhida).
2. Scripts por emulador "bem escritos" — contras: duplicação eterna, drift, auditoria O(n).
3. Tudo 100% declarativo sem hooks — contras: casos reais (migração DuckStation flatpak→appimage, RetroArch cores) não cabem em dados puros; acabaria gerando um DSL pior que Python.

## Prós
Auditoria concentrada na engine; adapter novo ≈ dados; segurança uniforme (checksums, staging, rollback de graça); capacidades declaradas viram UI automaticamente.

## Contras / Riscos
Schema do manifesto precisa evoluir bem (versionado); risco de "hooks crescerem" — mitigação: API de hook restrita (sem subprocess/rede) e revisão obrigatória.

## Decisão
Conforme ADAPTER-MODEL.md + MANIFEST-SCHEMAS.md. Dispatch sempre por registro em código; dados nunca nomeiam funções (anti-padrão RetroDECK/EmuDeck documentado).

## Consequências
Fase 4 = engine + manifests; suíte de contrato genérica que todo adapter passa.

## Revisão futura
Após 10 adapters reais: medir % declarativo vs hooks; se hooks >30% dos adapters, redesenhar o schema.
