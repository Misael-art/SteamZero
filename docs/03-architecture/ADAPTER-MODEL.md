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

## Apresentação declarada

Nome e ícone de cada adapter vivem no próprio manifesto, no bloco
`presentation`, versionado por `adapter-v1.schema.json`:

```json
"presentation": {
  "displayName": "Xenia Canary",
  "iconAsset": "../assets/xbox-360.svg"
}
```

Antes isso era um dicionário Python (`_EMULATOR_PRESENTATION`) paralelo ao
contrato, e essa duplicação tinha uma consequência silenciosa: um adapter
declarado em manifesto mas ausente do dicionário apareceria **sem nome e sem
ícone**, sem que nada falhasse. Apresentação hardcoded é allowlist implícita.

Regras:

- `iconAsset` precisa apontar para um asset **empacotado** e presente na
  allowlist de `PackagedAssets.qml`. O schema restringe o formato do caminho, e
  `tests/unit/test_packaged_assets.py` cruza as três listas — arquivos reais,
  allowlist do QML e manifestos — recusando qualquer divergência;
- `displayName` é o nome do produto. Vários coincidem com o id (`Azahar`,
  `Cemu`); o que denuncia id cru colado é separador de slug sobrevivendo no
  nome (`xenia-canary` em vez de `Xenia Canary`);
- alterar `presentation` muda o `manifestHash` e **exige atualizar
  `component-lock.json`**. É proposital: o lock existe para que nenhuma mudança
  de manifesto passe despercebida. Ao atualizar, confirme que apenas o hash
  mudou e que `source` (ref, versão, sha256) permanece intocada.

### Apresentação não é habilitação

Declarar `presentation` não torna o adapter operacional. A lista do que funciona
de ponta a ponta — instalação transacional, projeção de requisitos e launch
verificado — é `_MANAGED_EMULATORS`, e a ordem dessa tupla é a **ordem de
exibição** na central, decidida e não incidental.

Hoje o registry declara 16 adapters e três são operacionais. Mover um adapter
para `_MANAGED_EMULATORS` sem o lifecycle correspondente produz exatamente a
ação que termina em stub, proibida pelo `AGENTS.md`.

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

`retro-input-profile-v1` fica entre os dois contratos: o perfil define bindings
semânticos e rotação; o platform manifest lista quais perfis são aplicáveis; o
adapter traduz somente IDs semânticos conhecidos para sua configuração concreta.
Strings do perfil jamais escolhem código ou comandos. Ver
`05-data/RETRO-INPUT-PROFILE-V1.md`.

## Regras

1. Adapter **declara**, engine **executa**: download, checksum, staging, activate e rollback são do núcleo — o adapter nunca baixa nada por conta própria.
2. `versionPolicy: "pinned"` por padrão; "latest" só em canal dev e ainda com checksum publicado no lockfile do release da plataforma (corrige `getReleaseURLGH` latest-sem-pin).
3. Hooks Python rodam em contexto restrito: recebem API do núcleo (fs staging, config parsers, log), sem `subprocess` livre, sem rede.
4. Compat por distro declarada (`compat`) — herda o campo `# compat:` do LinuxToys.
5. Adapters de terceiros: ver PLUGIN-MODEL.md (assinatura obrigatória; fora do escopo v1 — N6).
