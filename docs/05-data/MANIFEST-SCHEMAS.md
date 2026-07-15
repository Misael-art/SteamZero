# MANIFEST-SCHEMAS — schemas de manifestos

Todos os manifestos têm `schemaVersion` e são validados por JSON Schema publicado em `docs/06-api/JSON-SCHEMAS.md` (índice). Rascunhos normativos:

## 1. Adapter manifest (`adapter.json`) — ver exemplo em ADAPTER-MODEL.md

Campos obrigatórios: `schemaVersion, id (slug [a-z0-9-]{1,63} — regex herdada de pz_boot_valid_id), kind, capabilities[], sources[] (cada uma com type + version pinada + sha256 p/ artefatos), license, upstream`.
Campos opcionais: `platforms[], paths{}, configFormat, semanticActions{}, bios[], verify{}, compat[] (famílias de distro — herda # compat: do LinuxToys), conflicts[], requires[]`.

Validações semânticas além do schema:
- `sources[].sha256` obrigatório quando `type != flatpak` (Flatpak delega ao commit OSTree do remote).
- Fonte Flatpak exige `ref`, `remote` seguros e `version` como commit OSTree hexadecimal
  completo de 64 caracteres; `endOfLife:true` impede novos planos.
- `capabilities` ⊇ {detect, status}; `install` exige `verify.smokeTest`.
- IDs de `requires`/`conflicts` devem existir no registry no momento do build do lockfile.

## 2. Component lockfile (por release da plataforma, canal stable)

O artefato empacotado `component-lock.json`, validado por `component-lock-v1`, contém
para cada adapter `{id, manifestHash, source{...}}`; `source` reutiliza exatamente o
schema de origem do manifesto e suporta Flatpak/AppImage/native sem resolução `latest`.
O registry recusa inicialização se faltar uma entrada, houver órfão ou qualquer campo
divergir do manifesto canônico. Assim, editar um manifesto sem atualizar/revisar o
lockfile falha como `E-SUPPLY-CHECKSUM`.

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

Para Flatpak, `component-plan-v1` especializa o contrato com `adapterId`, `ref`,
`remote`, `targetCommit`, snapshot `before`, ação `install|update|noop`, TTL/token e
`rollbackGuarantee:G-DEPLOYMENT`. O executor persiste intent antes do primeiro comando;
recovery de operação sem commit lógico restaura o snapshot anterior.

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
