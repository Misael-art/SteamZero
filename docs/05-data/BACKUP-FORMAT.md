# BACKUP-FORMAT — formato de backup

## Layout por operação

```
backups/<operationId>/
  manifest.json
  payload/            # árvore espelhada dos itens salvos (ou blobs por hash)
```

### manifest.json

```json
{ "schemaVersion": 1,
  "operationId": "ULID", "operation": "component.update",
  "createdAt": "ISO8601", "platformVersion": "x.y.z",
  "reason": "pre-apply",
  "entries": [
    { "kind": "file", "originalVolumeUuid": "…", "originalRelpath": "…",
      "payloadPath": "payload/…", "size": 123, "blake2b": "…",
      "mode": "0644", "mtime": "…" },
    { "kind": "state-row", "table": "component", "id": "duckstation",
      "snapshot": { … } },
    { "kind": "privileged-value", "action": "set-tdp", "previous": 15 }
  ],
  "retainedUntil": "ISO8601|policy",
  "sealed": true, "manifestHash": "…" }
```

## Regras

1. Manifesto selado (hash do próprio manifesto) — restauração recusa manifesto adulterado/incompleto (T-09).
2. Restauração verifica hash de cada entrada após restaurar (RB-4) e usa escrita atômica.
3. Backups de saves são **incrementais por conteúdo** (dedupe por hash — blobs compartilhados entre versões da timeline) para viabilizar a linha do tempo sem explosão de espaço.
4. Diretório 0700; entradas de conteúdo sensível (keys) marcadas e nunca listadas em relatórios com nome completo.
5. GC conforme ROLLBACK-GUARANTEES (retenção mínima + teto de disco); GC nunca quebra uma cadeia incremental retida.
6. Backup "exportável" (usuário quer levar para outro dispositivo): mesmo formato, empacotado em tar + manifest na raiz — é o que RETRODECK-IMPORT/EMUDECK-IMPORT também produzem ao adotar dados existentes.

## Backup completo do usuário (feature "Backup RetroDECK"-like)

`steamzero backup create --full` = saves timeline + configs geridas + state export + inventário (hashes) de ROMs/BIOS (conteúdo de ROMs/BIOS opcional por flag e espaço). Precedente: RetroDECK `configurator_retrodeck_backup_dialog` (tar de userdata), evoluído com manifesto verificável.
