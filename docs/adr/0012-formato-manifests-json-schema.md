# ADR-0012 — Manifests em JSON com JSON Schema (config humana em TOML)

**Status:** aceito

## Contexto
Manifests (adapter, lockfile, plan, backup) são lidos/escritos por máquina e validados; config da plataforma é editada por humanos. RetroDECK components usam JSON (manifest/recipe); LinuxToys usa headers de comentário (humano, mas não validável); PhaseZero valida profiles JSON com jq.

## Alternativas
1. **JSON+JSON Schema para manifests; TOML para config humana** (escolhida).
2. YAML para tudo — contras: ambiguidades (norway problem), parsers com histórico de CVE; prós: comentários (resolvido pelo TOML no lado humano).
3. Headers de comentário estilo LinuxToys — não validável/aninhável.

## Decisão
Conforme MANIFEST-SCHEMAS/CONFIGURATION-SCHEMAS: JSON draft 2020-12, `additionalProperties:false` em entrada, `schemaVersion` em tudo; TOML com schema espelhado para config.toml.

## Consequências
Golden files; geração de docs de schema; validação na carga com erros apontando campo.

## Revisão
Se adapters comunitários (v2) exigirem comentários, avaliar JSON5/JSONC apenas para `adapters.d/`.
