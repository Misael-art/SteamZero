# CAPABILITY-MATRIX — matriz de capacidades

Legenda de célula: ✔ implementado; ◐ parcial; ✖ ausente; (evidência entre parênteses).
"Melhor base" = de onde o Unified herda o **conceito**; código só é reutilizado conforme 11-legal/REUSE-POLICY.md.

| Capacidade | PhaseZero | EmuDeck | LinuxToys | RetroDECK | Melhor base | Lacunas | Riscos |
|---|---|---|---|---|---|---|---|
| Instalação de emuladores | ◐ (wrappers emudeck/eden/citron/hydra em `linux/emulation/`) | ✔ (31 EmuScripts, installEmuAI/FP/BI) | ◐ (scripts game/ genéricos) | ✔ (components manifest+recipe) | RetroDECK (modelo) + EmuDeck (cobertura) | Nenhum une manifesto verificado + rollback | Downloads "latest" sem pin (EmuDeck `getReleaseURLGH`) |
| Atualização | ◐ (updates/ p/ plataforma) | ◐ (update por reinstalação; sem canal) | ◐ (reinstala) | ✔ (canais main/cooker; component_update.sh) | RetroDECK | Rollback de update de componente inexistente nos 4 | Regressão sem volta |
| Desinstalação | ◐ (uninstall.sh global) | ◐ (uninstallEmuAI/FP; não preserva inventário) | ✖ | ◐ (appliance única) | PhaseZero (manifesto) | Inventário preciso pré-remoção | `rm -rf` amplo no EmuDeck |
| Reparação | ✔ (`-Audit -Repair`, flatpak audit --repair, retrodeck repair) | ◐ (autofix.sh, checkInstalledEmus) | ✖ | ✔ (repair_retrodeck_paths) | PhaseZero | Repair dirigido por verify formal | Repair que reaplica config e apaga custom |
| Configuração de emuladores | ◐ (ps1/ps2 configure; sed/jq) | ✔ (configEmuAI + templates configs/) | ✖ | ✔ (framework.sh presets; rd_assets) | EmuDeck (templates) + RetroDECK (presets) | Parsers estruturados, diff, migração versionada | `eval` no framework RetroDECK; sed denso |
| Launchers | ✔ (performance-launch.sh, wrappers) | ✔ (tools/launchers/*.sh por emulador) | ✖ | ✔ (component_launcher.sh) | EmuDeck | Launchers declarativos, não copiados por emulador | Duplicação massiva (31 variantes quase iguais) |
| ROMs (scan/organização) | ✔ (library scan/plan/apply/verify/rollback; romopt) | ◐ (estrutura roms/ + parsers SRM) | ✖ | ◐ (rebuild systems, clean empty) | **PhaseZero** | Indexação incremental performática | — |
| BIOS | ✔ (bios.sh; shared-content) | ✔ (checkBIOS.sh com hashes) | ✖ | ✔ (BIOS checker UI + json) | RetroDECK (UX) + PhaseZero (links seguros) | Compat por versão/região consolidada | Keys em log (mitigar por política) |
| Firmware/Keys | ◐ (ps3.sh import-pkg/rap; sony.sh) | ◐ (yuzu/citra firmware paths) | ✖ | ◐ | PhaseZero (import local auditado) | Store central única | Vazamento em logs |
| Saves (local) | ◐ (retrodeck integrate saves/states) | ◐ (setupSaves por emu) | ✖ | ✔ (paths centrais saves/states) | RetroDECK (layout) | Backups incrementais + timeline (nenhum tem) | Sobrescrita silenciosa |
| Cloud sync | ✖ | ✔ (cloudServicesManager, cloudSyncHealth, rclone) | ✖ | ◐ (cloud_sync.sh) | EmuDeck (referência de comportamento) | Fila offline, conflito não-destrutivo | Conflitos destrutivos hoje |
| Mídia/scraping | ✔ (media-index/media-gamelist.py, clean órfãos) | ✔ (generateGameLists.sh + store) | ✖ | ◐ (delega ao ES-DE) | PhaseZero (índice) + ES-DE adapter | Multi-provedor com rate limit/licença | ToS de provedores |
| Frontends (SRM/ES-DE) | ✔ (srm.sh, frontends.py, launchbox_import.py) | ✔ (runSRM, parsers SRM, ES-DE setup) | ✖ | ✔ (ES-DE embutido, SRM component) | PhaseZero (adapters finos) | Contrato de adapter formal | Acoplamento a formato interno dos frontends |
| Steam shortcuts | ✔ (steam-shortcut.py) | ✔ (via SRM) | ✖ | ✔ (via SRM) | PhaseZero | Dedupe de shortcuts | Corromper shortcuts.vdf |
| Desempenho (GameMode/Gamescope/MangoHUD/TDP) | ✔ (performance.sh, optimizers/, tuning/) | ◐ (flags por emulador) | ◐ (optimizers.lib, gamemode.sh) | ◐ (presets) | PhaseZero | Perfis por estado (LCD/OLED/dock/bateria) unificados | Mutação de TDP requer privilégio |
| Controles/Steam Input | ✔ (controllers.sh, input-actions.sh, hotkey-actions.sh) | ✔ (templates de perfil) | ✖ | ✔ (controller layouts install) | PhaseZero + EmuDeck templates | Ações semânticas universais | Quebra por update do Steam Client |
| Dock/display | ✔ (apply-docked-tv/monitor, display-session, dualscreen) | ✖ | ✖ | ✖ | **PhaseZero** | Fallback chain formalizada | Heterogeneidade de docks |
| Áudio | ◐ (dentro dos modos) | ✖ | ✖ | ✖ | PhaseZero | Perfis de áudio por modo | PipeWire/ALSA variação |
| MicroSD | ✔ (install-removable-mount, gating) | ◐ (paths em microSD) | ✖ | ◐ (move para microSD) | PhaseZero | Monitor I/O + UUID + integridade | Corrupção FS |
| Suspensão/retomada | ◐ (mode-watcher, display-session) | ✖ | ✖ | ✖ | PhaseZero (embrião) | Session Manager completo (§11.1) é novo | Comportamento por emulador varia |
| Backup | ✔ (boot backup bundle; changes manifest) | ✖ | ✖ | ✔ (backup userdata .tar) | PhaseZero + RetroDECK | Formato único versionado (05-data/BACKUP-FORMAT) | Backups infinitos sem GC |
| Rollback | ✔ (pz_rollback; library rollback; Invoke-BootstrapRollback) | ✖ | ✖ | ◐ (update via reinstalação de versão) | **PhaseZero** | Rollback verificado (compare estado) | Restore não-atômico atual (cp) |
| Diagnóstico | ✔ (-Doctor; runtime-diagnose; flatpak audit) | ◐ (cloudSyncHealth, checkInstalled) | ✖ | ◐ (logger níveis, api status) | PhaseZero | Doctor unificado + support bundle | — |
| Logging | ✔ (pz_log rotacionado 0600) | ◐ (echo + logs soltos) | ✖ | ✔ (logger.sh com níveis) | PhaseZero + RetroDECK níveis | Estruturado JSON + correlation IDs | Vazamento de segredo em log ad-hoc |
| API local | ◐ (linux/server; ui_native) | ✖ | ✖ | ✔ (api_server.sh + api_data_processing) | RetroDECK (existência) + contrato novo | AuthZ local, schemas | Bind não-local |
| CLI | ✔ (`pz` com dezenas de subcomandos + JSON) | ◐ (setup.sh flags) | ✖ (GUI-first) | ◐ (retrodeck CLI básico) | **PhaseZero** | Padronizar envelope v2 | — |
| UI Game Mode | ◐ (ui_native/pages) | ◐ (app Electron separado, fora deste repo) | ✖ | ✔ (Godot Configurator) | RetroDECK (Godot) | UI nova (Fase 5) | Godot acessibilidade (G10) |
| UI Desktop | ✔ (WPF via contrato JSON — padrão exemplar) | ◐ | ✔ (GTK python catálogo) | ◐ (zenity) | PhaseZero (contrato) + LinuxToys (simplicidade) | — | — |
| QAM/Decky | ✔ (install-plugins.sh opt-in, decky-ws-client.py) | ◐ (plugin hub) | ✖ | ✖ | PhaseZero (opcional por design) | Adapter QAM formal | Decky quebra a cada update |
| Build/distribuição | ◐ (packaging/, pkg Arch) | ◐ (install.sh curl|bash no site) | ✔ (pacotes multi-distro + flatpak, flake.nix) | ✔ (Flatpak + canais + builder) | **RetroDECK** | SBOM, assinaturas, repro builds | Supply chain |
| Testes | ✔ (122 arquivos Pester; CI parse+test) | ◐ (test.sh superficial) | ✖ | ◐ (post_build_check.sh, automation_tools) | **PhaseZero** | Testes bash/python novos; injeção de falha | — |
| Multi-distro | ✔ (capabilities/, pacman+flatpak) | ◐ (Deck-first, nonDeck.sh) | ✔ (`is_*` 8+ famílias) | ✔ (Flatpak = distro-agnóstico) | LinuxToys (detecção) + RetroDECK (isolamento) | rpm-ostree/ublue formal | Divergência de famílias |
| Offline | ◐ (operações locais funcionam) | ✖ (setup exige rede) | ✖ | ◐ (roda offline pós-instalação) | RetroDECK | Fila offline formal | — |
