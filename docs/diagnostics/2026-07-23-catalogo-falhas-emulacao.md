# Catálogo de Falhas — Emulação (diagnóstico com direcionamento)

**Data:** 2026-07-23
**Branch de inspeção:** `codex/desktop-ergonomia-d0` (HEAD `43ec946`)
**Linha principal de desenvolvimento:** `codex/steam-gameplay-readiness-ui`
**Versão:** `0.1.0a33`
**Fonte de governança de expansão:** `codex/expansao-master-steamzero` → `docs/EXPANSION-LEDGER.md`

## Como ler este documento

Cada falha tem:
1. **Sintoma** (o que o operador vê);
2. **Causa raiz** (não hipótese — ponto exato do código);
3. **Estado real** (inexistente / código órfão / quebra de fiação / placeholder);
4. **Direcionamento** (o que construir e ONDE, com `arquivo:linha` de entrada);
5. **WI do Expansion Ledger** correspondente, quando existe.

## ⚠ Achado estrutural crítico (ler antes de tudo)

Três descobertas mudam o direcionamento geral:

1. **Há código órfão pronto e desconectado.** Mods, cheats e o pipeline de scraping
   **existem** como adapters de domínio completos (instaladores, catálogos terceiros,
   providers ScreenScraper/SteamGridDB), mas **não estão referenciados por nenhum
   controller**. Parte do que o operador relata como "só tem importador, falta o
   instalador" é na verdade **fiação ausente**, não construção do zero.

2. **O pipeline de scraping foi removido do trunk.** `src/steamzero/adapters/scraping/`
   hoje contém **apenas `.pyc`** — os 7 módulos `.py` foram apagados. As portas
   `MediaProviderPort`/`MediaCandidate`/`GameIdentity` também sumiram de `ports.py`.
   Por isso "não baixa nada": **não há chamada de rede alguma** para dar erro.

3. **Há divergência séria entre ramos.** A branch de inspeção
   (`codex/desktop-ergonomia-d0`) **não contém** os módulos `.py` de mods/cheats nem a
   área `modsCheats` na UI — só restam `.pyc` residuais. Eles vivem na linha de
   expansão (`codex/expansao-master-steamzero`). Antes de qualquer correção, o agente
   executor precisa definir a **base de trabalho** correta com o operador.

**Direcionamento geral:** consolidar a linha de expansão, reconectar código órfão e
preencher lacunas — **não** reconstruir do zero o que já existe. Antes de tocar em
emulador/grub/host, seguir os preflights do `AGENTS.md` (instalação no host exige
autorização explícita e os quatro gates da seção 6 em verde no commit instalado).

---

## F1 — Escopo global: "Emulador principal mesmo definido fica com não definido"

**Sintoma:** o emulador aparece como "não definido" mesmo depois de definido.

**Causa raiz (modelo de domínio, não bug de mapeamento):**
A string "emulador principal" **não existe no código**. O operador está descrevendo, com
suas palavras, um destes fallbacks reais:

- `Emulation.qml:82-86` → `selectedEmulator` fallback `"Nenhum emulador verificado"`,
  `state: "unsupported"`;
- `Emulation.qml:1087,1104` → bloco `"Nenhum emulador Switch foi verificado"`;
- `emulation.py:412-413` → `statusLabel: "Não instalado"` quando o AppImage não está no
  `StateStore`.

A noção de "emulador principal definido pelo usuário" **não existe no backend**. A
precedência real é `SwitchEmulatorCatalog.preferred()` (`switch_emulators.py:103-110`),
que retorna o primeiro emulador instalado — mas **esse valor nunca é serializado no
snapshot** nem lido pelo QML. Logo, qualquer "definição" feita pelo operador (instalação
manual no host, marcação de preferência) **não se propaga** para `emulators[].state`,
deixando a UI perpetuamente em "Não instalado" / "Nenhum emulador verificado".

**Estado real:** falta de conceito de domínio + não publicação de `preferred()`.

**Direcionamento:**
- Backend: `emulation.py:380-413` (`_emulator_rows`) — a fonte de `installed`. Incluir
  sinais além de `engine.status()` (probe no host via `which`, ou campo persistido de
  seleção do usuário).
- OU publicar `preferred()` em `emulation_workspace.py:73-105` como campo
  `selectedEmulator`/`primaryEmulator` na plataforma.
- Schema: `schemas/emulation-workspace-v1.schema.json` — hoje **proíbe** campos extras na
  plataforma (`additionalProperties: false`, linha 158). Qualquer novo campo exige editar
  este schema.
- UI: `Emulation.qml:82-86` (binding `selectedEmulator`) e `Emulation.qml:1087,1104`
  (bloco de fallback).
- **Confirmar com o operador a string exata que aparece na tela** (screenshot/copiar-colar)
  e em qual worktree está rodando, antes de implementar.

---

## F2 — Emulação/áreas: DLC e updates exibem zero

**Sintoma:** mesmo tendo DLC/updates, o card "Updates & DLC" exibe zero.

**Causa raiz:** o scan de biblioteca **nunca procura, classifica ou conta DLC/updates**.
O card conta `records` do `SwitchContentManager` (índice de blobs importados
**manualmente**), não arquivos no disco.

- `emulation.py:248-291` (`scan_library`) — itera `library_roots()` e chama
  `scanner.scan(root)`, mas o dict do jogo **não tem campo `contentType`** nem
  classificação base/DLC/update.
- `switch_library.py:117-144` (`SwitchLibraryScanner.scan`) — aceita por extensão
  (`nsp/nsz/xci/nro`) e extrai `title_id` do nome via regex, **sem classificação por
  padrão `[DLC]`/`v0`/title-id**.
- `emulation.py:471-472,537-567` — card conta `records` do store, não do filesystem.
- Importância: `library_roots()` (emulation.py:226-246) **já cobre pastas fora das ROMs**
  via `_custom_roots()`. O gargalo não é alcance — é classificação/contagem.

**Requisito do operador:** DLC/update podem estar em qualquer pasta apontada (dentro ou
fora das ROMs) e devem ser identificados na varredura; quando encontrados, os caminhos e
arquivos devem ser apontados nos emuladores.

**Estado real:** scanner cego para DLC/update; nenhuma projeção de path para config do
emulador.

**Direcionamento:**
- Classificação: `SwitchLibraryScanner.scan` (`switch_library.py:117-144`) por padrão de
  nome/title-id; novo campo `contentType` em `SwitchRomMatch` (dataclass
  `switch_library.py:91-108`) e no cache.
- Contagem: `_area_data`/`scan_library` em `emulation.py` (a partir do scan, não só do
  `SwitchContentManager`).
- Projeção para emulador: hoje **não existe**. `_emulator_game_directory_writes`
  (`emulation.py:966-991`) e `_merge_qsettings_game_dirs` (994-1016) só gravam roots de
  ROMs, nunca paths de DLC/update. Criar método análogo que, dado um `ContentRecord`
  ativo (kind update/dlc), escreva o path no formato de cada emulador (Citron
  `qt-config.ini`; Ryubing `Config.json` `GameDirs`).
- Adapter `rom_metadata/` está **vazio** — necessário um leitor de CNMT/title-id real.

---

## F3 — Emulação/áreas: Mods e cheats "só tem importador"

**Sintoma:** só há importador; faltaria instalador com soluções terceiras.

**Causa raiz (fiação, não construção):** o que o operador diz **não corresponde ao código
na linha de expansão**. Há **três** mecanismos, e o problema real é de fiação/exposição:

- **(a) Importador local (único visível na UI)** — `emulation.py` (expansão)
  `_plan_mod_import` (~2647) e `_plan_cheat_import` (~2678): copiam arquivo local para a
  pasta do emulador. A UI só tem botão "Importar" de arquivo local.
- **(b) Instalador de domínio JÁ EXISTE, órfão** —
  `adapters/mods/mod_installer.py::FilesystemModInstaller` (`install`/`remove`/`activate`
  via symlink `.active`/`deactivate`/`list_installed_mods`) e
  `adapters/cheats/cheat_installer.py::FsCheatInstaller` (`install`/`remove`/`enable`
  via `.txt.disabled`/`list_installed`/`edit_codes`). Fachada:
  `domain/switch_mods.py::SwitchModManager` e `domain/switch_cheats.py::SwitchCheatManager`
  com `download_and_install`/`enable`/`disable`/`remove`/`edit_codes`.
  **Nenhum é referenciado pelo `EmulationController`.**
- **(c) Catálogos terceiros JÁ EXISTEM, órfãos** — `adapters/mods/github_mod_source.py`
  (StevensND/Fl4sh9174/BoycottP), `semd_source.py` (theboy181),
  `ns_emu_mod_downloader.py` (wrapper do binário externo),
  `cheats/nsecm_source.py` (cheatslips/GBAtemp/tomad). **Jamais chamados por qualquer
  controller.**

**Estado real:** instalador e catálogos prontos, porém desconectados. Falta fiação
controller→manager→catálogo + UI de busca.

**Direcionamento:**
- Fiação: em `EmulationController` (expansão), instanciar `SwitchModManager`/
  `SwitchCheatManager` + `composite_catalog.py`.
- UI de busca/catálogo: `_area_data` (área `modsCheats`, ~2394) e `plan_action` (~974)
  para ações `mod.search`/`mod.catalog.install`/`cheat.catalog.install`.
- O catálogo composto já existe em `adapters/mods/composite_catalog.py`.
- **Atenção de governança:** a branch de inspeção **não contém** os `.py` — só `.pyc`.
  A base de trabalho precisa ser a linha de expansão.

---

## F4 — Emulação/áreas: Gráfico e performance só tem informações básicas

**Sintoma:** sem perfis, FPS, TDP, LFSP-VK para frame generation, MangoHud, upscaling,
resolução etc.

**Causa raiz:** praticamente tudo está ausente.

**O que existe (HUD informativo):**
- `Emulation.qml` área `graphicsPerformance` (`defaultAreas` linha 42; `defaultCards`
  linhas 277-283): três cards textuais ("Perfil conhecido bom", "Dock ↔ portátil",
  "LSFG-VK 30→60"), todos `state: "unknown"`.
- `emulation.py:592-606` (`_area_data` `graphicsPerformance`): um único card
  "Dock ↔ portátil" cujo único dado real é `"Dock" if dock else "Portátil"`. **Sem
  perfis, sliders ou escrita.**

**O que existe como código órfão:**
- `domain/emulator_config.py`: `KnownGoodProfileCatalog` (30), `EmulatorConfigurator`
  (159) com `preview`/`plan_apply`/`rollback`/`render_ini`. Mas `Settings` (linha 27) é
  genérico/seccionado — **sem campos nomeados** para TDP/MangoHud/upscaling/resolução/
  frame-gen. Não referenciado por controller.
- `adapters/lsfg.py::LsfgInstaller` (77-289): instala só o runtime Vulkan; não gera
  perfis por jogo.

**O que falta (zero ocorrências no `src/`):** `tdp`, `mangohud`, `upscal`, `frame_gen`,
`resolution`, perfis persistidos.

**Direcionamento:**
- UI: `Emulation.qml` área `graphicsPerformance` (defaultCards 277-283; `areaTitle` 235;
  `areaDescription` 251).
- Backend: `emulation.py` `_area_data` bloco `graphicsPerformance` (592) + `plan_action`
  (293) para novas ações.
- O `Settings` em `emulator_config.py:27` precisa de campos nomeados e o
  `EmulatorConfigurator` (159) precisa ser instanciado.
- Ledger correspondente: **G1** (MangoHud), **G3** (vkBasalt), **G4** (frame-gen LSFG/
  OptiScaler), **G6** (benchmark), **R0/R1/R2** (integer scaling/presets/upscaling) —
  todos `pending`.

---

## F5 — Emulação/áreas: Controles somente informativo

**Sintoma:** só informações; precisa construir a tela.

**Causa raiz:** área praticamente inexistente.

**O que existe:**
- `Emulation.qml` área `controls` (`defaultAreas` 43; `defaultCards` 284-290): três cards
  informativos ("Jogadores detectados 0/4", "Modo do console", "Perfil por emulador"),
  `state: "unknown"`.
- `emulation.py:607-618` (`_area_data` `controls`): um card "Controles" mostrando
  `f"{controllers} / 4"`, `primaryAction: emulation.refresh`.
- Única detecção real: `_controller_count()` (1057-1064) enumera
  `/dev/input/by-id/*-event-joystick`, `min(4, len(...))`. Mais `_physical_dock()` (1053).

**O que falta (zero ocorrências):** `controller` como conceito de domínio, `gamepad`,
`steam_input`, `sdl`, mapeamento de jogador, bind de botões, perfil por emulador/jogo.

**Direcionamento:**
- UI: `Emulation.qml` área `controls` (defaultCards 284-290; `areaTitle`/`areaDescription`
  230-251).
- Backend: `_area_data` `controls` (607), `plan_action` (293) e `_controller_count` (1057)
  — este é o seed natural para um futuro adapter de input.
- `domain/` não tem arquivo de input/controller (criar).
- Ledger correspondente: **F6** (perfis versionados/reversíveis de input) e **R6**
  (perfis automáticos de controles especializados), `pending`.

---

## F6 — Emulação/áreas: vSaves (print do save + playtime + contagem + lançar)

**Sintoma:** além do save, monitorar o diretório de save do jogo e, sempre que escrito,
capturar um print do jogo e armazenar junto com tempo de jogo, quantidade de vezes salvo
etc., exibidos na tela; o jogo pode ser lançado desta tela.

**Causa raiz:** o subsistema de saves hoje é um **store append-only por conteúdo (dedupe
por hash) + fila de sync offline**, sem captura, sem watcher, sem playtime agregado, sem
contador exposto. O termo "vSaves" **não existe no código**.

**O que existe:**
- `domain/saves.py`: `SavesStore.record_save` (56-84, blob por hash), `record_conflict`
  (133), `SaveEntry` (33-42 — sem coluna de screenshot/playtime/contador), `restore`/
  `plan_restore`/`apply_restore`/`rollback_restore` (96-131).
- `domain/sync.py`: `SyncManager.drain` (52-90) processa fila offline; `enqueue_upload`
  (40-50).
- `domain/session.py` + `m0004_game_session.py`: `game_session` tem `started_at`/
  `finished_at`/`exit_code`. **Playtime é derivável mas nunca computado/agregado.**
- `SessionPort` (`ports.py:75-83`): `launch`/`is_alive`/`flush_save`/`signal_close`/
  `terminate`/`kill`. **`flush_save` é Protocol sem implementação concreta observada.**
- `steam_launcher.py:391-448` (`SteamLauncher.run`): ciclo `start→wait→transition(closed)`
  — **este é o hook pós-exit claro** (entre `child.wait()` em 425 e `_transition_session`
  em 428-434), com `started_at`/`finished_at` disponíveis para playtime.
- `emulation.py:217-224` (`launch_emulator`): `_spawn_detached` fire-and-forget
  (subprocess.Popen, `start_new_session=True`). **Sem `wait()`, sem pós-exit hook.**
- UI: `Main.qml:2201-2251` ("Saves e Sync") é dashboard de sync (3 contadores da fila);
  `Emulation.qml:291-297` (área "saves") é placeholder estático. **Sem listagem por jogo,
  sem `Image`, sem playtime, sem botão "Jogar".**

**O que falta (ausência confirmada):**
1. **Captura de screenshot** — zero referências a `grim`/`spectacle`/`scrot`/`wlr-screencopy`
   /`dbus.*Screenshot`/`mss`/`PIL`. O único "screenshot" é `kind` de `media_item`
   (metadados de capa).
2. **FS watcher** — zero referências a `inotify`/`watchdog`/`Observer`. Nenhuma dep em
   `pyproject.toml`. `record_save` é API passiva.
3. **Playtime agregado** — zero ocorrências de `playtime`/`time_played`/`play_count`. Não
   há coluna `playtime_seconds` na tabela `game`.
4. **Contador de saves** — `timeline_seq` (`save_entry`) existe mas nunca é agregado/
   exposto.
5. **UI por-jogo** com prints/playtime/botão "Jogar".

**Direcionamento:**
- Screenshot: nova porta em `ports.py` (ao lado de `SessionPort`, 75) — ex.
  `ScreenshotPort.capture(game_id) -> Path`; adapter em `adapters/screenshot.py` (Wayland
  `grim`/`wlr-screencopy`; fallback X11 `scrot`/`spectacle`). Padrão: `which`/`runner`
  injetados de `steam_session.py:27-31`.
- FS watcher: novo adapter (`save_watcher.py`) com `watchdog` (dep a adicionar). Diretório
  a vigiar: resolver por emulador via `_emulator_game_directory_writes` (`emulation.py:966`)
  como ponto de partida. Sink: `SavesStore.record_save` + novo campo de screenshot.
  **Iniciar no launch, encerrar no exit.**
- Hook pós-exit:
  - Steam: `steam_launcher.py:391-448` — iniciar watcher após `child = ...processes.start`
    (408); capturar screenshot final entre `exit_code = child.wait()` (425) e
    `_transition_session(...closed)` (428-434).
  - Emulador: `emulation.py:217-224` precisa reter o `Popen` e fazer `wait()` em thread,
    ou delegar o ciclo a um `SessionPort` concreto.
- Playtime: migration adicionando `playtime_seconds`/`last_played`/`launch_count` na tabela
  `game` (`m0001_baseline.py:52-60`); agregação em `core/state.py` (ao lado de
  `transition_game_session`, 337).
- Contador: `SELECT COUNT(*) FROM save_entry WHERE game_id=?` (já suportado por
  `list_saves`, `state.py:552`); só expor/bindar.
- UI: substituir/complementar seção "Saves e Sync" (`Main.qml:2201`) ou em
  `SteamGameplay.qml`; bindings `Image`/playtime/contador/`Button` "Jogar".
- Ledger correspondente: **A1** (playtime/sessões interrompidas), **G5** (captura e
  galeria), `pending`.

---

## F7 — Emulação/áreas: Mídia — download impossível + SVGs default repetidos

**Sintoma A:** não conseguimos baixar nenhuma mídia.
**Sintoma B:** mídia default na pasta do emulador são SVGs repetidos; o correto seria um
único arquivo default e, por código, a ROM sem artwork ser representada conforme sua
plataforma.

**Causa raiz A (estrutural, não bug de rede):** o pipeline de download foi **removido** do
trunk. Não há nada para "dar erro".

- `adapters/steam_media.py:1-7`: docstring declara a política — "não faz scraping nem
  baixa mídia neste adapter". `snapshot()` (82) retorna `"source": "local-only"`.
- `adapters/scraping/` contém **apenas `.pyc`** — os 7 módulos `.py` foram apagados. Os
  `.pyc` revelam a especificação: `BaseMediaProvider`/`TokenBucket`/`RateLimiter`/
  `_fetch_url` (urllib), `screenscraper.py` (`_API_BASE screenscraper.fr/api2`, auth
  devid/devpassword + ssid/sspassword), `steamgriddb.py` (`_API_BASE
  steamgriddb.com/api/v2`), `dispatcher.py` (`ScrapingDispatcher`), `registry.py`
  (fallback por tipo), `cache.py` (SQLite).
- `ports.py` hoje **não define** `MediaProviderPort`/`MediaCandidate`/`GameIdentity` —
  mesmo restaurando os `.py`, a importação quebraria.
- `service/methods.py:99-131` (RPC fechado) e `adapters/desktop_ui.py:130-294` (roteador
  HTTP) **não têm** método/rota de scrape/download.
- `SteamGameplay.qml:1466-1530`: UI só tem conta Steam + pasta local + "Revisar pacote";
  linha 1502 declara "Fonte somente local".

**Conclusão A:** sem rede = sem erro. O download é impossível por design atual.

**Causa raiz B:** o fallback de UI é **um único** `steam.svg` em
`SteamGameplay.qml:658` (`source: page.selectedGame.coverUrl || "../assets/steam.svg"`).
Não há lógica que copie um SVG por ROM. "SVGs repetidos na pasta do emulador" provavelmente
refere-se a artefatos de runtime no grid Steam (`steam_media.py:98` escreve
`grid.png`/`portrait.png`/`hero.png`/`logo.png` por `game_id`), não a duplicação no
código. O fallback hoje é único, mas **não é por plataforma**.

**Estado real:** download = pipeline removido (recriar); SVG = falta parametrização por
plataforma.

**Direcionamento A:**
- Recriar `MediaProviderPort`/`MediaCandidate`/`GameIdentity`/`media_dir` em `ports.py`.
- Recriar `adapters/scraping/{base,cache,registry,screenscraper,steamgriddb,dispatcher}.py`
  (os `.pyc` são a especificação funcional; `_API_BASE` e auth já documentados neles).
- Adicionar método em `service/methods.py` e rota em `desktop_ui.py` (ex. `/media/scrape`,
  `/media/download`).
- UI de trigger (a área "Capas e metadados" hoje é placeholder em `Emulation.qml:308`).

**Direcionamento B:**
- Parametrizar o fallback por plataforma em `SteamGameplay.qml:658` (e equivalente em
  `Emulation.qml` para a grade de ROMs), em vez do `|| "../assets/steam.svg"` único.
- Manter **um único** arquivo default por plataforma no `assets/`.

---

## F8 — Emulação/áreas: Artwork da ROM + conversão na tela

**Sintoma:** poder colocar artwork da ROM e disponibilizar conversão da ROM nesta tela.

**Causa raiz:**
- **Artwork de ROM — inexistente.** Zero ocorrências de `artwork`/`custom.*cover`/
  `manual.*art`. A única UI de mídia (`SteamGameplay.qml:1466-1530`) aplica um pacote
  local de 4 arquivos fixos a um `game_id` Steam, não artwork arbitrário de ROM.
- **Conversão de ROM — backend pronto e órfão.** `domain/convert.py:32-136`
  (`ConversionManager.convert`) e `adapters/converters.py` (`NszToolConverter` ~347-396,
  `SwitchRomConversionService` 421-511, allowlist `_NSZ_CONVERSIONS` 38, hashes pinados
  43-59) + `emulation.py:1018` (`_nsz_conversion()`). **Mas não há rota UI nem CLI.**

**Estado real:** artwork = inexistente; conversão = backend órfão.

**Direcionamento:**
- Artwork: área "Capas e metadados" em `Emulation.qml:308`; nova rota em `desktop_ui.py`
  + método em `methods.py` reaproveitando `MediaLibrary` (`domain/media.py`, que já faz
  canonicalização/quarentena por magic bytes) + `SteamMediaManager`.
- Conversão: expor rota em `desktop_ui.py` + handler no card "Conversão NSZ"
  (`Emulation.qml:321`); ponto de entrada `SwitchRomConversionService.plan_convert`
  (`converters.py:421`).

---

## F9 — Emulação/armazenamento: só informações básicas + sem gestão linkada

**Sintoma:** ver tamanho da biblioteca/emuladores/cache/BIOS/mídias; gestão do espaço com
conversão de ROMs, limpeza de mídias, exclusão de ROMs de forma segura e **linkada** (se
apagar uma ROM, cache/mídia/cheats/DLC/update também são apagados).

**Causa raiz:**
- **UI mostra 3 cards estáticos** — `Emulation.qml:312-318` ("Conteúdo compartilhado",
  "Deduplicação", "Isolamento"), todos `state: "unknown"`. Sem contagem de bytes reais.
- **Domínio só enumera volumes por UUID** — `domain/storage.py:29-92` (`StorageMonitor`:
  `scan`/`volume_state`/`is_available`/`resolve_write_path`). `StoragePort.list_volumes`
  (`ports.py:68-71`) retorna capacidade/livre do volume inteiro, não por categoria.
- **Não existe cascata de exclusão** — schema `m0001_baseline.py:62-71` (`rom_file`
  referencia `game` e `storage_volume` **sem `ON DELETE CASCADE`**); `state.py:433-460`
  tem `save_rom`/`get_rom`/`list_roms` mas **nenhum `delete_rom`**; buscas por `def.*delete`/
  `DELETE FROM rom`/`DELETE FROM game` retornam zero. `SwitchContentManager` só faz import/
  link/set_active/recover/restore/invalidate_shader/migrate_saves — **nenhuma exclusão**.

**Estado real:** UI placeholder + domínio de enumeração; exclusão e agregação inexistentes.

**Direcionamento:**
- Agregação por categoria: novo serviço consumindo `library_roots()` + paths de cache/BIOS/
  mídia (`paths.py`) + `StorageMonitor`.
- UI: página "Armazenamento" em `Emulation.qml:312-318` com barras/contadores reais por
  categoria + ações (converter/limpar/excluir).
- Cascata de exclusão linkada: novo plano em `domain/switch_content.py` (que já conhece o
  índice de update/dlc/mod/shader-cache/save/keys/firmware por `titleId`) coordenado com
  `StateStore` (precisa de `ON DELETE CASCADE` ou delete explícito em `rom_file`/`game`/
  `save_entry`/`bios_item`) + `MediaLibrary`/`SteamMediaManager` + cache de emulador.
  Nova migration para `ON DELETE CASCADE` ou delete transacional explícito.

---

## F10 — Emulação/escopo: DLCs, shaders, FW, região indisponíveis (leitura)

**Sintoma:** informações de DLCs/shaders/FW/região indisponíveis; necessário implementar
leitura.

**Causa raiz (consolidada dos diagnósticos):**

| Item | Existe | Faltando |
|---|---|---|
| DLC/update | Import manual + índice interno (`switch_content.py`); scanner cego | Classificação no scan + projeção do path para config Citron/Ryubing |
| Shader cache | Invalidação (`switch_content.py:392-417`); card depende de import manual | Descoberta/leitura de caches nas pastas dos emuladores; fingerprint real |
| Firmware | Versão por input manual (`emulation.py:786`); `KeysFirmwareStore` em `keys_firmware.py:99` **não conectado**; controller duplica a lógica em `_requirements` (427-456) | Leitor de `SystemVersion`/NCAs; varredura de `Contents/registered` |
| Região | Campo no schema DAT e em `SwitchRomMatch`; `SwitchMediaMatcher` existe | Invocação no `scan_library`; empacotar/usar um DAT; ou leitor de CNMT |

**Direcionamento consolidado:**
- DLC/update: ver F2.
- Shader/FW/região: adapter em `adapters/rom_metadata/` (atualmente vazio) consumido por
  `EmulationController._requirements` e `_area_data`.
- Conectar `KeysFirmwareStore` (`keys_firmware.py:99`) no lugar da duplicação em
  `_requirements` (`emulation.py:427-456`).

---

## Mapeamento para o Expansion Ledger

O operador já tem governança formal destas falhas em `codex/expansao-master-steamzero` →
`docs/EXPANSION-LEDGER.md`. Mapeamento direto:

| Falha | WI(s) do ledger | Contrato | Estado |
|---|---|---|---|
| F1 Emulador principal | (fora do ledger — modelo de domínio) | — | — |
| F2 DLC/update scan+projeção | A4, A8, F5 | bitrot/patch/platform-manifest | pending |
| F3 Mods/cheats fiação | (código órfão a reconectar) | — | parcial |
| F4 Gráficos/performance | G1, G3, G4, G6, R0, R1, R2 | gtool-*/retro-experience | pending |
| F5 Controles | F6, R6 | retro-input-profile | pending |
| F6 vSaves | A1, G5 | feat-playtime/media-registry | pending |
| F7 Mídia download+SVG | A7, A12, F1 (core.net) | media-registry/core.net | parcial/pending |
| F8 Artwork+conversão | A7, A8 | media-registry/patch-operation | parcial |
| F9 Armazenamento+cascata | A4, A7 | bitrot/media-registry | pending |
| F10 DLC/shader/FW/região leitura | A4, A12, F5 | bitrot/media-registry/platform-manifest | pending |

**Recomendação de sequência (foco UX):** priorizar o que reduz confusão imediata e
desbloqueia o resto — (1) F1 (emulador principal) e F7-B (SVG default único por
plataforma) são correções de baixo custo e alto impacto na percepção; (2) reconectar
código órfão de F3 e F8-conversão (já prontos); (3) consolidar a linha de expansão como
base antes de qualquer work novo, para não duplicar o que existe.
