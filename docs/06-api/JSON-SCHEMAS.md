# JSON-SCHEMAS — índice e exemplos de schemas

Schemas JSON (draft 2020-12) versionados em `schemas/` no repositório (Fase 1); este documento é o índice normativo e traz exemplos-chave.

| Schema | Cobre | Referência |
|---|---|---|
| `envelope-v2.schema.json` | Saída CLI/API | CLI-CONTRACT |
| `plan-v1.schema.json` | Plano transacional | MANIFEST-SCHEMAS §4 |
| `desktop-plan-v1.schema.json` | Plano G-STATE do Desktop Experience | MANIFEST-SCHEMAS §7 |
| `desktop-conflict-plan-v1.schema.json` | Plano confirmado para liberar owner externo | MANIFEST-SCHEMAS §7 |
| `desktop-status-v1.schema.json` | Contexto/status Desktop | MANIFEST-SCHEMAS §7 |
| `session-environment-v1.schema.json` | Ambiente Linux read-only da sessão | STEAM-SESSION-ROADMAP R1 |
| `adapter-v1.schema.json` | adapter.json | ADAPTER-MODEL |
| `platform-manifest-v1.schema.json` | registry de plataformas e capacidades | PLATFORM-MANIFEST-V1 |
| `component-lock-v1.schema.json` | lockfile empacotado de componentes | MANIFEST-SCHEMAS §2 |
| `component-plan-v1.schema.json` | plano Flatpak pinado | MANIFEST-SCHEMAS §4 |
| `backup-manifest-v1.schema.json` | manifesto de backup | BACKUP-FORMAT |
| `bios-db-v1.schema.json` | banco de hashes | MANIFEST-SCHEMAS §5 |
| `profile-v1.schema.json` | presets/perfis | MANIFEST-SCHEMAS §6 |
| `event-v1.schema.json` | eventos/progresso | EVENTS-AND-PROGRESS |
| `error-v1.schema.json` | objeto de erro | ERROR-CATALOG |
| `job-v1.schema.json` | job serializado | JOB-LIFECYCLE |
| `state-export-v1.schema.json` | export do State Store | STATE-MODEL |
| `config-platform-v1.schema.json` | config.toml (via taplo/JSON Schema) | CONFIGURATION-SCHEMAS |
| `support-bundle-v1.schema.json` | índice do bundle | SUPPORT-BUNDLE |

## Exemplo: `event-v1.schema.json` (núcleo)

```json
{ "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["seq","ts","kind","correlationId"],
  "properties": {
    "seq": {"type":"integer","minimum":0},
    "ts": {"type":"string","format":"date-time"},
    "kind": {"enum":["job.progress","job.state","session.state","session.environment","entity.changed","alert"]},
    "jobId": {"type":"string"}, "correlationId": {"type":"string"},
    "progress": {"type":"object","properties":{
      "stage":{"type":"string"}, "current":{"type":"number"},
      "total":{"type":["number","null"]}, "unit":{"enum":["bytes","items","steps"]},
      "rate":{"type":["number","null"]}, "currentItem":{"type":["string","null"]}}},
    "state": {"type":"string"}, "error": {"$ref":"error-v1.schema.json"}
  }, "additionalProperties": false }
```

## Regras

1. `additionalProperties:false` em todo schema de **entrada** (rejeitar campos desconhecidos); saídas permitem evolução aditiva com `additionalProperties:true` + campos documentados.
2. IDs: ULID (`^[0-9A-HJKMNP-TV-Z]{26}$`); slugs: `^[a-z0-9][a-z0-9-]{0,62}$` (mesma regex do `pz_boot_valid_id`, common.sh:346).
3. Todo schema tem suíte de exemplos válidos/inválidos versionada (golden tests).
