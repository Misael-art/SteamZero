# Evidência de certificação M10 (VM descartável)

- **Commit de origem:** `10704a795fdc47a985d8404eed9b8fc44d325b05`
- **Data:** 2026-08-11
- **Veredito geral:** APROVADO
- **Protocolo:** minimal

## Resultado por emulador

| emulador | veredito | install | verify | rollback |
|---|---|---|---|---|
| retroarch | OK | installed (ok) | — (ok) | missing (ok) |

## Detalhe por etapa

### retroarch

```json
[
  {
    "step": "baseline",
    "status": "missing",
    "ok": true
  },
  {
    "step": "install",
    "operationId": "01KZQG6HKQ3AM870Q4NB8BYQGT",
    "status": "installed",
    "commit": "d8644a97df3db3cdd46eff2f7aea7d429c40f7e1e7ed5788a191714cc29a74a8",
    "expectedCommit": "d8644a97df3db3cdd46eff2f7aea7d429c40f7e1e7ed5788a191714cc29a74a8",
    "ok": true
  },
  {
    "step": "verify",
    "id": "retroarch",
    "state": "installed",
    "installed": true,
    "installable": true,
    "executor": "flatpak",
    "sourceType": "flatpak",
    "version": "d8644a97df3db3cdd46eff2f7aea7d429c40f7e1e7ed5788a191714cc29a74a8",
    "targetVersion": "d8644a97df3db3cdd46eff2f7aea7d429c40f7e1e7ed5788a191714cc29a74a8",
    "origin": "flatpak",
    "detail": null,
    "endOfLife": false,
    "verified": true,
    "repairable": false,
    "ok": true
  },
  {
    "step": "rollback",
    "operationId": "01KZQG6HKQ3AM870Q4NB8BYQGT",
    "rollback": {
      "status": "rolled-back",
      "operationId": "01KZQG6HKQ3AM870Q4NB8BYQGT",
      "adapterId": "retroarch",
      "executor": "flatpak"
    },
    "status": "missing",
    "ok": true
  }
]
```

## Restore do baseline Btrfs

- Confirmado: **SIM**
