# SOURCE-REPOSITORIES — repositórios analisados

Regra desta análise: fontes locais são a referência primária; ausências registradas; clones de referência declarados (não silenciosos), somente leitura, nunca modificados.

## 1. PhaseZero (fonte local primária)

- **Caminho:** `/mnt/sdcard/Projects/PhaseZero/`
- **Git:** HEAD `a0468ba` ("feat(linux-ai): dedicated Proxies IA control-center page"), pós-tag v1.8.4; remote `https://github.com/Misael-art/PhaseZero.git`
- **Natureza:** orquestrador pós-instalação. Lado Windows: monólitos PowerShell 5.1 (`bootstrap-tools.ps1` ~16k linhas/430 funções; `bootstrap-ui.ps1` WPF; 493 arquivos .ps1; 122 arquivos de teste Pester). Lado Linux: CLI `linux/pz` + 128 scripts bash + módulos Python.
- **Áreas relevantes ao Unified:**
  - `linux/lib/common.sh` — strict mode, umask 077, log rotacionado, `pz_admin_run` (bridge de privilégio com fallbacks), `pz_write_managed_file` (escrita atômica com backup), `pz_rollback_register`/`pz_rollback` (manifesto JSON por operação em `$XDG_STATE_HOME/phasezero/operations/`), guards de path traversal em scripts de profile (linhas 748–764), preflights de GRUB com backup bundle.
  - `linux/lib/json-envelope.sh` — envelope `{ok,module,status,checks,actions,blockers,logs,generatedAt}`.
  - `linux/emulation/library/` — pipeline transacional Python: `scan.py`, `plan.py` (emite `confirmToken`), `apply.py` (recusa sem token — linha 76), `state.py`, `safezip.py`, `registry.py`.
  - `linux/emulation/` — 38 módulos (bios, controllers, dualscreen, frontends, heroic, launchbox, media, nsz, optimizers, performance, ps3, retrodeck, romopt, shared-content, srm, steam-shortcut...).
  - `linux/steamdeck/` — modos (apply-handheld/docked-tv/docked-monitor, detect-mode, mode-watcher.service), hotkeys, plugins Decky (opt-in), privileged controls, removable mount, display-session.
- **Estado:** completo e íntegro. Sem arquivo LICENSE (ver 11-legal).

## 2. EmuDeck (referência clonada — ausente localmente)

- **Ausência local registrada:** nenhum clone em `/mnt/sdcard/Projects/`; vestígios: `PhaseZero/linux/emulation/emudeck.sh` (instalador do AppImage oficial) e `~/Downloads/EmuDeck.desktop`.
- **Referência:** `Port_Steam/reference/EmuDeck`, commit `71d4cdc` (2026-07-09), upstream `dragoonDorise/EmuDeck`, licença GPL-3.0.
- **Natureza:** backend bash do instalador EmuDeck. 228 scripts. `functions/EmuScripts/` com 31 emuladores no padrão `<Emu>_{install,init,update,uninstall,setEmulationFolder,setupSaves...}`; `functions/` com helpers (`safeDownload`, `getReleaseURLGH`, `configEmuAI`, `installEmuAI/FP/BI`, `checkBIOS`, `cloudServicesManager`); `roms/` e `configs/` como templates; `tools/launchers/`.
- **Estado:** completo (ramo main). Subáreas `android/`, `darwin/`, `chimeraOS/` não auditadas em profundidade (KNOWN-GAPS G2).

## 3. LinuxToys (referência clonada — repo ausente; artefatos locais presentes)

- **Artefatos locais:** `PhaseZero/linuxtoys-bin/linuxtoys-6.4.3.tar.xz` (fonte empacotada) + pacote Arch + extração em `linuxtoys-bin/src/linuxtoys-6.4.3/usr/`.
- **Referência:** `Port_Steam/reference/linuxtoys`, commit `89856ef` ("prep 6.4.4", 2026-07-14), upstream `psygreg/linuxtoys`, licença GPL-3.0.
- **Natureza:** app GTK em Python (`p3/linuxtoys.py`) que renderiza catálogo de scripts bash. 264 scripts em `p3/scripts/<categoria>/` com metadados de cabeçalho (`# name/version/description/icon/compat/repo`); bibliotecas `p3/libs/{linuxtoys.lib,helpers.lib,optimizers.lib,translator.lib}` (compat zenity→CLI, `sudo_rq`, `pkg_install`, `pkg_flat`, detecção `is_arch/is_fedora/is_ostree/...`); i18n em `p3/libs/lang/`.
- **Estado:** completo.

## 4. RetroDECK (referência clonada — ausente localmente)

- **Ausência local registrada:** apenas `PhaseZero/linux/emulation/retrodeck.sh` (integrador). Flatpak não instalado no host.
- **Referência:** `Port_Steam/reference/RetroDECK`, commit `d7c02e8` (2026-05-29), upstream `RetroDECK/RetroDECK`, licença GPL-3.0 + `other_licenses.txt`.
- **Natureza:** appliance Flatpak (`net.retrodeck.retrodeck.yml`). `functions/` (framework.sh de presets/configuração, api_server.sh, cloud_sync.sh, compression.sh, multi_user.sh, logger.sh, post_update.sh); `config/retrodeck/`; `automation_tools/`; `developer_toolbox/`; Configurator Godot.
- **Estado:** completo no ramo main.

## 5. RetroDECK/components (referência parcial)

- **Tentativa de clone integral:** falhou por timeout (blobs pesados). **Registrado como lacuna (G1).**
- **Obtido:** árvore completa via API GitHub (6.799 paths, `truncated=false`) em `reference/RetroDECK-components-index/tree.json` + arquivos representativos: `framework/{README.md,component_manifest.json,component_recipe.json}`, `duckstation/{component_manifest.json,component_functions.sh}`.
- **Modelo observado:** cada componente = diretório com `component_manifest.json` (identidade, menus declarativos do Configurator, opções de first-init), `component_recipe.json` (build/obtenção), `component_prepare.sh`, `component_update.sh`, `component_launcher.sh`, `component_functions.sh`, `rd_assets/rd_config/` (configs padrão). 27 componentes ativos + `archive_later/` (5.516 paths legados).
