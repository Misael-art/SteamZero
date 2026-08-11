# Evidência de certificação M10 (VM descartável)

- **Commit de origem:** `1723cc82a259c05c5b6152549cdee6a71e48feb3`
- **Data:** 2026-08-10
- **Veredito geral:** REPROVADO
- **Protocolo:** minimal

## Resultado por emulador

| emulador | veredito | install | verify | rollback |
|---|---|---|---|---|

## Detalhe por etapa

## Falha da execução

```json
{
  "command": {
    "label": "SSH guest (env)",
    "returncode": 1,
    "stderr": "Warning: Permanently added '192.168.123.89' (ED25519) to the list of known hosts.\r\n",
    "stdout": "{\"ok\": false, \"contract\": \"2.0\", \"module\": \"component\", \"action\": \"apply\", \"status\": \"failed\", \"operationId\": null, \"jobId\": null, \"correlationId\": \"01KZMT7H9HVRZQFCENPSC3P711\", \"data\": {}, \"checks\": [], \"blockers\": [], \"error\": {\"code\": \"E-COMPONENT-UPDATE-ROLLEDBACK\", \"title\": \"Atualização revertida\", \"what\": \"A atualização falhou. A versão anterior foi restaurada.\", \"impact\": \"O componente continua na versão anterior, funcional.\", \"probableCause\": \"Falha em verify ou no smoke test da nova versão.\", \"autoAction\": \"deployment anterior restaurado\", \"manualAction\": \"Tente novamente mais tarde; reporte se persistir.\", \"action\": \"Tente novamente mais tarde; reporte se persistir.\", \"detail\": \"E-COMPONENT-DEGRADED: falha ao smoke test de net.pcsx2.PCSX2\\ncomando: flatpak run --user --die-with-parent --env=QT_QPA_PLATFORM=offscreen --env=QT_QPA_PLATFORMTHEME=none net.pcsx2.PCSX2 -nogui --version\\nretorno: 124\\nstdout:\\n\\nstderr:\\nCall to org.freedesktop.portal.Settings.ReadAll failed QDBusError(\\\"org.freedesktop.DBus.Error.UnknownMethod\\\", \\\"No such interface “org.freedesktop.portal.Settings” on object at path /org/freedesktop/portal/desktop\\\")\\nThis plugin does not support propagateSizeHints()\\nCall for getting org.freedesktop.portal.FileChooser version failed QDBusError(\\\"org.freedesktop.DBus.Error.InvalidArgs\\\", \\\"No such interface “org.freedesktop.portal.FileChooser”\\\")\\nqt.dbus.integration: QDBusConnection: name 'org.freedesktop.portal.Desktop' had owner '' but we thought it was ':1.8'\\n\", \"operationId\": \"01KZMT7HAXGBK35AEP76FSAGR4\", \"detailsRef\": null}, \"generatedAt\": \"2026-08-10T03:20:37.088731+00:00\"}\n"
  },
  "exception": {
    "message": "SSH guest (env) falhou: Warning: Permanently added '192.168.123.89' (ED25519) to the list of known hosts.",
    "type": "RequiredCommandError"
  },
  "expectedPins": {
    "pcsx2": "31307c3e9fa0fda4275433c053169dd231a7f921bb80bb51dd67b2ef95638f28",
    "ppsspp": "193bbe95656ed696c8e5a5e42831ee8017d53514e9e0e0acaa3e1235e22089d3",
    "retroarch": "d8644a97df3db3cdd46eff2f7aea7d429c40f7e1e7ed5788a191714cc29a74a8"
  },
  "stage": "certificação pcsx2 (minimal)"
}
```

## Restore do baseline Btrfs

- Confirmado: **NÃO — execução interrompida**
