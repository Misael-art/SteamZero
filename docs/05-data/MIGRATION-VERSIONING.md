# MIGRATION-VERSIONING — versionamento de migrações

## Escopos versionados independentemente

1. **Schema do State Store** — inteiro monotônico (`PRAGMA user_version`); migrações SQL/py numeradas `NNNN_desc`, cada uma com `up` + teste com fixture do schema anterior; backup do state.db antes de migrar (é uma transação como qualquer outra); downgrade = restaurar backup (documentado, não SQL down).
2. **Configs de emulador geridas** — cada adapter declara `configSchemaVersion`; migrações por versão com preservação de comentários quando o formato permitir; dry-run mostra diff.
3. **Manifestos/lockfiles** — `schemaVersion`; leitor aceita N e N-1 com deprecações logadas.
4. **Formato de backup** — versão no manifesto do backup; restaurador suporta todas as versões já publicadas (compromisso de longo prazo).
5. **API/CLI** — ver 06-api (versionamento de contrato separado de dados).

## Regras

- Migração é sempre: detect versão → plan (o que muda) → backup → apply → verify → registro em `post_migration_log` (precedente conceitual: RetroDECK `post_update.sh` encadeia migrações por versão — aqui com dry-run e backup, que lá faltam).
- Migrações são idempotentes por guarda de versão (nunca reaplicam).
- Pular versões: migrações encadeiam N→N+1→...; testadas em cadeia completa no CI a partir de fixtures de cada release publicada.
- Dados do usuário nunca são "migrados no lugar" sem backup: USER-DATA-PRESERVATION.md governa.
