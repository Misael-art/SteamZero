# ADR-0011 — Logs estruturados JSONL com correlation IDs

**Status:** aceito

## Contexto
PhaseZero: log textual rotacionado 0600 (bom em higiene, fraco em estrutura). RetroDECK: níveis configuráveis. §14 exige campos estruturados e proibições de conteúdo.

## Alternativas
1. **JSONL próprio + `steamzero logs`** (escolhida) — greppável, schema simples, zero dependência.
2. syslog/journald — prós: infra pronta; contras: conteúdo sai do controle do produto (bundle/anonimização mais difíceis), disponibilidade varia; decisão: **espelhar avisos críticos no journald** quando presente, fonte de verdade é o JSONL.
3. Banco de logs — over-kill.

## Decisão
Conforme LOGGING.md (campos obrigatórios, rotação, 0600, correlationId fim-a-fim, canary tests de segredos).

## Consequências
Event bus ≠ logs (UI não parseia log); suporte usa correlationId.

## Revisão
Volume real em campo pode pedir sampling de debug.
