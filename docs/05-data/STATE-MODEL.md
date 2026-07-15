# STATE-MODEL — modelo de estado

## Armazenamento

SQLite (WAL) em `$XDG_STATE_HOME/steamzero/state.db` (ADR-0005), com export/import JSON legível (`steamzero state export`). Schema versionado por migrações (MIGRATION-VERSIONING.md).

## Entidades principais (rascunho de schema lógico)

```
device(id, kind[deck-lcd|deck-oled|desktop], dmi_fingerprint, quirks_json)
storage_volume(id, uuid UNIQUE, label, fstype, role[internal|microsd|usb],
               state[mounted|missing|io-error], capacity, free, last_seen)
component(id, adapter_id, kind[emulator|frontend|tool], version, origin
          [flatpak|appimage|native], state[installed|degraded|missing|staged],
          verified_at, manifest_hash)
platform(id, name, esde_folder, extensions_json)
game(id, platform_id, title, canonical_path_id, multi_disc_group, state
     [ready|missing-bios|unavailable|quarantined|incomplete])
rom_file(id, game_id, volume_id, relpath, size, hash_blake2b, format,
         verified_at)
bios_item(id, platform_id, relpath, hash, region, version, state
          [present|missing|unknown|incompatible], last_validated)
firmware_key_item(id, kind[firmware|key], platform_id, hash_truncated, state)
save_entry(id, game_id, kind[save|state], timeline_seq, created_at, device_id,
           hash, size, origin[local|cloud|checkpoint], conflict_group)
media_item(id, game_id, kind[boxart|screenshot|video], provider, license,
           relpath, hash, state[ok|orphaned|quarantined])
profile(id, scope[game|platform|device|mode|desktop-experience],
        kind[performance|controls|display|desktop-plan|desktop-current|
             desktop-override|desktop-recovery|desktop-observation],
        payload_json, priority)
job(...ver JOB-LIFECYCLE)  ·  operation(id, journal_path, state, backup_path)
backup(id, operation_id, manifest_json, size, retained_until)
sync_queue(id, save_entry_id, direction, state[pending|in-flight|conflicted|done])
compat_fact(id, subject[steamos|steam-client|component], version, tested_with_json,
            verdict[ok|degraded|broken])
event_log(seq, ts, kind, entity, payload_json)   -- fonte dos eventos da UI
```

## Princípios

1. **Estado observado ≠ estado desejado:** `component.state` é o observado (por verify); o desejado vive nos manifests/perfis. Drift = `degraded` com diff.
2. **Nada de paths absolutos gravados:** `volume_id + relpath` — sobrevive à troca de mountpoint e à remoção do microSD (FM-06); paths absolutos só resolvidos em runtime.
3. **Timeline de saves é append-only**; GC por política, nunca por sobrescrita.
4. **`verified_at` obrigatório para status "ok"** (P10): status sem verificação recente aparece como "não verificado".
5. **Export/import:** JSON canônico com versão de schema; import valida schema + reconstrói índices; usado também por USER-DATA-PRESERVATION nas migrações.
6. Multi-usuário (Q9): chave `profile_owner` reservada desde v1, não exposta.
7. Desktop Experience usa a tabela de perfis na migração v2; planos têm TTL/token,
   recovery guarda snapshots e observation implementa estabilidade de hotplug.
8. Operações Flatpak mantêm um intent durável em
   `$XDG_STATE_HOME/steamzero/component-operations/<operationId>.json`; a tabela
   `operation` referencia o arquivo e espelha
   `applying|rolling-back|committed|rolled-back|recovery-required`.
   O snapshot registra somente deployment/ref/remote/commit, nunca dados do aplicativo.
