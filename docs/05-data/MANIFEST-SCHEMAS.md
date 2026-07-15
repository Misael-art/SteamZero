# MANIFEST-SCHEMAS — schemas de manifestos

Todos os manifestos têm `schemaVersion` e são validados por JSON Schema publicado em `docs/06-api/JSON-SCHEMAS.md` (índice). Rascunhos normativos:

## 1. Adapter manifest (`adapter.json`) — ver exemplo em ADAPTER-MODEL.md

Campos obrigatórios: `schemaVersion, id (slug [a-z0-9-]{1,63} — regex herdada de pz_boot_valid_id), kind, capabilities[], sources[] (cada uma com type + version pinada + sha256 p/ artefatos), license, upstream`.
Campos opcionais: `platforms[], paths{}, configFormat, semanticActions{}, bios[], verify{}, compat[] (famílias de distro — herda # compat: do LinuxToys), conflicts[], requires[]`.

Validações semânticas além do schema:
- `sources[].sha256` obrigatório quando `type != flatpak` (Flatpak delega ao commit OSTree do remote).
- `capabilities` ⊇ {detect, status}; `install` exige `verify.smokeTest`.
- IDs de `requires`/`conflicts` devem existir no registry no momento do build do lockfile.

## 2. Component lockfile (por release da plataforma, canal stable)

```json
{ "schemaVersion": 1, "platformVersion": "1.0.0", "channel": "stable",
  "components": [ {"id":"duckstation","source":"appimage",
    "version":"v0.1-9xxx","sha256":"...","testedOn":["steamos-3.7","bazzite-42"]} ] }
```

## 3. Backup manifest — ver BACKUP-FORMAT.md.

## 4. Plan (saída do `plan`, consumida pelo `apply`)

```json
{ "schemaVersion": 1, "planId": "ULID", "confirmToken": "...",
  "operation": "component.update", "params": {"componentId": "duckstation"},
  "preconditions": [{"path":"...","hash":"..."},{"stateRow":"component:duckstation","fingerprint":"..."}],
  "actions": [{"seq":1,"kind":"fetch","args":{...},"undo":{...}}, ...],
  "requirements": {"diskBytes": 123, "network": true, "privileged": []},
  "risks": ["..."], "rollbackGuarantee": "G-FULL",
  "expiresAt": "ISO8601" }
```

## 5. BIOS/hash database (dat)

```json
{ "schemaVersion": 1, "platform": "psx",
  "entries": [{"name":"scph5501.bin","sha256":"...","region":"US","required":true,
               "usedBy":[{"adapter":"duckstation","min":"any"}]}] }
```
(Contém apenas hashes/metadados — nunca conteúdo. Precedentes: EmuDeck checkBIOS, RetroDECK reference_lists.)

## 6. Profile/preset manifest

`{schemaVersion, scope, kind, matches{platform|game|device|mode}, values{}, priority}` — merge determinístico documentado em CONFIGURATION-SCHEMAS.

## 7. Desktop Experience

`desktop-plan-v1` contém `requestedProfile`, perfil alvo completo, fingerprint do
contexto, mudanças, blockers, TTL, `confirmToken` e `rollbackGuarantee: G-STATE`.
`desktop-status-v1` expõe contexto/capabilities, recomendação, override, estado atual,
recovery pendente e `independentRuntime: true`. Ambos são aditivos dentro da versão 1.
