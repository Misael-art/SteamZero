# Evidência de certificação M10 (VM descartável)

- **Commit de origem:** `9379963792ff36ae03d15e00f154bdaa01f5b850`
- **Data:** 2026-08-09
- **Veredito geral:** REPROVADO
- **Protocolo:** minimal

## Resultado por emulador

| emulador | veredito | install | verify | rollback |
|---|---|---|---|---|

## Detalhe por etapa

## Falha da execução

```json
{
  "component": {
    "action": "rollback",
    "envelope": {
      "action": "rollback",
      "blockers": [],
      "checks": [],
      "contract": "2.0",
      "correlationId": "01KZJ8WPSTCGE3ZVY1FWR4E3FY",
      "data": {
        "adapterId": "retroarch",
        "executor": "flatpak",
        "operationId": "01KZJ7NHER7WF4M9E0QA3SAA97",
        "status": "rolled-back"
      },
      "error": null,
      "generatedAt": "2026-08-09T03:26:50.094027+00:00",
      "jobId": null,
      "module": "component",
      "ok": false,
      "operationId": "01KZJ7NHER7WF4M9E0QA3SAA97",
      "status": "rolled-back"
    }
  },
  "exception": {
    "message": "component rollback falhou: {\"adapterId\": \"retroarch\", \"executor\": \"flatpak\", \"operationId\": \"01KZJ7NHER7WF4M9E0QA3SAA97\", \"status\": \"rolled-back\"}",
    "type": "GuestComponentError"
  },
  "stage": "certificação retroarch (minimal)"
}
```

## Restore do baseline Btrfs

- Confirmado: **NÃO — execução interrompida**
