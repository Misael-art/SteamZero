# ADAPTER-MODEL — modelo de adapters

Síntese: manifesto declarativo (RetroDECK components + LinuxToys headers) + engine única (elimina os 31 quase-clones do EmuDeck) + execução transacional (PhaseZero).

## Anatomia de um adapter de emulador

```
adapters/emulators/duckstation/
  adapter.json          # manifesto (identidade, capacidades, fontes, compat)
  config.templates/     # templates de configuração (equivalente EmuDeck configs/)
  hooks.py              # SÓ quando declarativo não basta; API restrita, sem shell cru
```

### adapter.json (schema em 05-data/MANIFEST-SCHEMAS.md)

```json
{
  "id": "duckstation",
  "kind": "emulator",
  "platforms": ["psx"],
  "capabilities": ["detect","status","install","update","configure",
                    "verify","repair","uninstall","backup","restore"],
  "sources": [
    {"type":"flatpak","ref":"org.duckstation.DuckStation","remote":"flathub","priority":1},
    {"type":"appimage","releases":"github:stenzek/duckstation",
     "versionPolicy":"pinned","version":"v0.1-9xxx",
     "sha256":"<obrigatório>","priority":2}
  ],
  "paths": {"config":"{XDG_DATA_HOME}/duckstation/settings.ini"},
  "configFormat": "ini",
  "semanticActions": {"save_state":"hotkey:F1","load_state":"hotkey:F3", "...":"..."},
  "bios": [{"platform":"psx","required":true,"knownHashes":"ref:bios-db/psx.json"}],
  "verify": {"smokeTest":["--version"],"configSchema":"schemas/duckstation.ini.json"},
  "license": "GPL-3.0", "upstream": "https://github.com/stenzek/duckstation"
}
```

## Contrato de capacidades

Interface única; adapter declara o que implementa (nem todos implementam tudo — capacidade ausente = ação indisponível na UI, não erro em runtime):

| Operação | Semântica | Obrigatória? |
|---|---|---|
| detect | existe? versão? origem (flatpak/appimage/nativo)? | sim |
| status | saúde detalhada (config válida, BIOS ok, paths ok) | sim |
| install / update / uninstall | via núcleo transacional; nunca escreve direto | se instalável |
| configure | aplica template/preset via parsers estruturados; diff antes | opcional |
| verify | pós-condições objetivas | sim p/ instaláveis |
| repair | corrige só a camada quebrada apontada pelo verify | opcional |
| backup / restore | dados do próprio componente (configs; nunca saves — Saves é domínio central) | opcional |

## Famílias de adapters

- **Emuladores** (manifest-driven, ~1 diretório por emulador).
- **Frontends**: Steam (shortcuts.vdf com backup + dedupe — precedente `steam-shortcut.py`), SRM (gera parsers — precedentes `srm.sh` e EmuDeck `runSRM`), ES-DE (es_systems/es_settings), RetroArch (cores/playlists), RetroDECK (interop de paths compartilhados — precedente `retrodeck.sh integrate`), Heroic, LaunchBox (import somente-leitura — precedente `launchbox_import.py`).
- **Sistema**: package (flatpak/appimage/pacman/dnf/apt/rpm-ostree — detecção herda conceito `is_*` do LinuxToys `helpers.lib`), storage (UUID, mounts, espaço), display, áudio, input, steamdeck (DMI + quirks LCD/OLED).
- **Cloud**: provedores de sync (comportamento de referência: EmuDeck `cloudServicesManager.sh`), sempre atrás da fila offline.

## Registry de plataformas

`platform-manifest-v1` é distinto de `adapter-v1`: plataforma descreve sistemas,
áreas da UI, capacidades, candidatos de emulação, mídia, controles, timing e
presets; adapter descreve uma implementação instalável/detectável. A associação
é somente por `adapterId` validado nos testes do registry. Capacidade ausente ou
planejada remove/bloqueia a ação na UI com causa, sem fallback por nome de
plataforma. Ver `05-data/PLATFORM-MANIFEST-V1.md`.

## Regras

1. Adapter **declara**, engine **executa**: download, checksum, staging, activate e rollback são do núcleo — o adapter nunca baixa nada por conta própria.
2. `versionPolicy: "pinned"` por padrão; "latest" só em canal dev e ainda com checksum publicado no lockfile do release da plataforma (corrige `getReleaseURLGH` latest-sem-pin).
3. Hooks Python rodam em contexto restrito: recebem API do núcleo (fs staging, config parsers, log), sem `subprocess` livre, sem rede.
4. Compat por distro declarada (`compat`) — herda o campo `# compat:` do LinuxToys.
5. Adapters de terceiros: ver PLUGIN-MODEL.md (assinatura obrigatória; fora do escopo v1 — N6).
