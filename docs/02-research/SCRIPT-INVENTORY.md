# SCRIPT-INVENTORY — inventário de artefatos por repositório

Contagens obtidas por `find`/`grep` em 2026-07-14 (comandos reproduzíveis anotados).

## PhaseZero (`/mnt/sdcard/Projects/PhaseZero`)

| Classe | Quantidade/local | Observações |
|---|---|---|
| Bash (linux/) | 128 `.sh` + entrypoint `linux/pz` (812 linhas) | 100% dos módulos `linux/lib` e amostras auditadas usam `set -euo pipefail`; `eval`: 0 ocorrências em `linux/` |
| Python (linux/) | `emulation/library/*` (1.401 linhas), `frontends.py`, `heroic.py`, `launchbox*.py`, `media-*.py`, `pc-games.py`, `steam-shortcut.py`, `capabilities/`, `steamdeck/decky-ws-client.py`, `ui/`, `ui_native/` | Pipeline transacional em `library/` |
| PowerShell | 493 `.ps1` (monólitos bootstrap-tools/ui + assets steamdeck) | Referência conceitual (checkpoint/rollback/audit); não é alvo de porte |
| UI | `linux/ui` (templates web), `linux/ui_native` (+admin-bin), WPF Windows | Contrato JSON UI↔orchestrator documentado em CLAUDE.md |
| Serviços | `linux/steamdeck/mode-watcher.service` (user service) | — |
| Config/profiles | `profiles/*.json` (extends, packages.linux.{pacman,yay,flatpak}, scripts, systemd, sysctl) | Validação de schema via jq em `pz_run_profile` |
| Testes | 122 arquivos em `tests/` (Pester 3.4), incl. `linux-*.sh` | CI: parse de todos os .ps1 + Pester |
| Docs | `docs/` (adr/0001, capabilities.md, planos), CLAUDE.md, AGENTS.md, README | ADR practice já existente |
| Downloads externos | `linuxtoys-bin/` (tarball+pkg), `gemini-cli/` | Vendorizados no repo |
| Comandos privilegiados | via `pz_admin_run` (phasezero-admin→bigsudo→sudo -n gated) e `steamdeck/install-privileged-controls.sh` | Padrão de bridge |
| Estado persistido | `$XDG_STATE_HOME/phasezero/` (pz.log 0600, operations/*.json) | umask 077 |

## EmuDeck (`reference/EmuDeck`, GPL-3.0)

| Classe | Quantidade/local | Observações |
|---|---|---|
| Bash | 228 `.sh` | **0 com `set -euo pipefail`** (`grep -rl` = 0/228); `eval`: 1 |
| EmuScripts | 31 emuladores (`functions/EmuScripts/emuDeck*.sh`) | Padrão por convenção de nomes `<Emu>_install/_init/_update` — chamados dinamicamente |
| Helpers | `functions/*.sh` (~40): safeDownload (staging `.temp`, SHA256 **opcional** — param 10 raramente usado), getReleaseURLGH (resolve latest da API GH, sem pin), configEmuAI (rsync de templates), jsonToBashVars, dialogBox (zenity) | Download sem verificação por padrão |
| Templates | `configs/` (por emulador), `roms/` (estrutura ES-DE + media), `tools/launchers/` | Ativo mais valioso do projeto |
| Cloud | cloudServicesManager.sh, cloudSyncHealth.sh (rclone) | Referência de comportamento |
| Instalação | `install.sh` e variantes early/beta/unstable — padrão `curl ... | bash` no site upstream | Anti-padrão a não repetir |
| Testes | `test.sh` superficial | Sem suíte real |
| CI/CD | `.github/` (build do AppImage) | — |

## LinuxToys (`reference/linuxtoys`, GPL-3.0, v6.4.4-prep)

| Classe | Quantidade/local | Observações |
|---|---|---|
| Python GUI | `p3/linuxtoys.py` + `p3/app/`, `p3/helpers/` | GTK; renderiza catálogo a partir dos metadados dos scripts |
| Scripts | 264 `.sh` em `p3/scripts/{chat,devs,drivers,edu,extra,game,office,repos,...}` | Cabeçalho declarativo: `# name/version/description/icon/compat/repo`; 1/264 com strict mode |
| Bibliotecas | `p3/libs/linuxtoys.lib` (zenity compat + fallback TTY), `helpers.lib` (sudo_rq, pkg_install, pkg_flat, is_arch/is_fedora/is_ostree/is_suse/is_solus/is_rhel/is_cachy, multilib_chk), `optimizers.lib`, `translator.lib` + `lang/*.json` | Núcleo do valor: modularidade mínima |
| Build | `src/buildfiles/` (deb/rpm/pkgbuild/flatpak), `flake.nix` | Multi-formato exemplar |
| Manifesto | `p3/manifest.txt`, `packages.json` | — |

## RetroDECK (`reference/RetroDECK`, GPL-3.0)

| Classe | Quantidade/local | Observações |
|---|---|---|
| Flatpak | `net.retrodeck.retrodeck.yml` (manifest), desktop files, metainfo | Appliance isolado |
| Bash | 39 `.sh`; `functions/` (20 módulos) | `eval`: 26 (framework.sh — indireção de variáveis de preset); 1 c/ strict mode |
| Framework | framework.sh (get/set_setting_value multi-formato INI/JSON/XML por eval), presets.sh, checks.sh, post_update.sh (migrações por versão), multi_user.sh, compression.sh (chd/rvz), cloud_sync.sh, logger.sh (níveis), api_server.sh | Conceitos fortes, implementação frágil |
| Config | `config/retrodeck/` (defaults, reference_lists json) | Listas de referência de sistemas/BIOS em JSON |
| Automação | `automation_tools/`, `developer_toolbox/`, `retrodeck_builder.sh`, `tools/` | Build/CI maduros |
| UI | Configurator Godot (godot-configurator.sh; menus declarativos vêm do component_manifest.json) | Precedente de Godot em Game Mode |

## RetroDECK/components (índice parcial — G1)

- 27 componentes ativos (retroarch: 590 paths; primehack: 202; gzdoom: 98; demais 7–22) + `framework/` + `automation-tools/` + `archive_later/` (5.516) e `archive_old/` (64).
- Padrão por componente: `component_manifest.json` (identidade, menus declarativos, finit_options), `component_recipe.json`, `component_prepare.sh`, `component_update.sh`, `component_launcher.sh`, `component_functions.sh`, `rd_assets/rd_config/`.
- Evidência lida: `framework/component_manifest.json` (263 linhas — menus do Configurator declarativos, comandos nomeados, sem código na UI), `duckstation/component_functions.sh` (687 bytes — fino).
