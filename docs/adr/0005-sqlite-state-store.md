# ADR-0005 — SQLite como State Store (com export/import JSON)

**Status:** aceito

## Contexto
§9.3 pede avaliação de SQLite. PhaseZero usa JSONs por operação (operations/*.json) + logs; RetroDECK usa cfg+jsons; EmuDeck usa settings.sh + jsonToBashVars. Consultas do produto (dashboard, "jogos afetados pelo volume X", timeline) são relacionais por natureza.

## Alternativas
1. **SQLite WAL** (escolhida) — prós: transações ACID locais, consultas, um arquivo, backup simples, stdlib; contras: dado não-legível diretamente (mitigado por export/import JSON canônico e `steamzero state export`); riscos: corrupção por I/O (mitigado: WAL + integrity_check no doctor + backup diário + R2 reconstrução por rescan).
2. Árvore de JSONs — prós: legibilidade/git-friendly; contras: sem atomicidade entre arquivos, consultas O(n), locks manuais (a classe de problema que o PhaseZero contorna com jq por todo lado).
3. Postgres/embedded outros — over-kill local.

## Decisão
SQLite (WAL, foreign_keys=ON, busy_timeout) com **writer único no daemon**; migrações versionadas (user_version); export/import JSON legível como contrato de primeira classe; journal transacional fica FORA do SQLite (arquivos JSONL por operação — sobrevive a corrupção do db e é a fonte do recovery R2/R3).

## Consequências
STATE-MODEL normativo; testes de migração em cadeia; doctor verifica integridade.

## Revisão futura
Se multi-processo writer se tornar necessidade (improvável), reavaliar.
