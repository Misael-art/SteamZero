# Matriz de controles — ações publicadas e contratos

- contratos publicados: **130**
- ações nos read models: **211**
- veredito: `{'blocked-explained': 2, 'routed': 145, 'handled-locally': 64}`

| Superfície | Ação | Rótulo | Habilitada | Contrato | Endpoint | Veredito | Motivo |
|---|---|---|---|---|---|---|---|
| emulationWorkspace.platforms[0].areaData.keysFirmware.cards[0].action | `keys.import` | Importar keys | False | `keys.import` |   | **blocked-explained** | Importação pela interface ainda não está conectada ao serviço. |
| emulationWorkspace.platforms[0].areaData.keysFirmware.cards[1].action | `firmware.import` | Importar firmware | False | `firmware.import` |   | **blocked-explained** | Importação pela interface ainda não está conectada ao serviço. |
| emulationWorkspace.platforms[33].requirements.firmware.action | `firmware.download` | Baixar e instalar firmware oficial da Sony | True | `emulation.action.plan` |   | **routed** | None |
| emulationWorkspace.globalManagement.platformCards[0].action | `platform.open:switch` | Abrir plataforma | True | `platform.open:switch` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[1].action | `platform.open:nintendo-handheld` | Abrir plataforma | True | `platform.open:nintendo-handheld` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[2].action | `platform.open:nes-famicom` | Abrir plataforma | True | `platform.open:nes-famicom` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[3].action | `platform.open:snes` | Abrir plataforma | True | `platform.open:snes` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[4].action | `platform.open:mega-drive` | Abrir plataforma | True | `platform.open:mega-drive` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[5].action | `platform.open:arcade` | Abrir plataforma | True | `platform.open:arcade` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[6].action | `platform.open:playstation` | Abrir plataforma | True | `platform.open:playstation` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[7].action | `platform.open:geforce-now` | Abrir plataforma | True | `platform.open:geforce-now` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[8].action | `platform.open:xbox-cloud-gaming` | Abrir plataforma | True | `platform.open:xbox-cloud-gaming` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[9].action | `platform.open:amazon-luna` | Abrir plataforma | True | `platform.open:amazon-luna` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[10].action | `platform.open:nintendo-console` | Abrir plataforma | True | `platform.open:nintendo-console` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[11].action | `platform.open:master-system` | Abrir plataforma | True | `platform.open:master-system` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[12].action | `platform.open:game-gear` | Abrir plataforma | True | `platform.open:game-gear` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[13].action | `platform.open:pc-engine-turbografx` | Abrir plataforma | True | `platform.open:pc-engine-turbografx` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[14].action | `platform.open:atari-classics` | Abrir plataforma | True | `platform.open:atari-classics` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[15].action | `platform.open:neo-geo-pocket` | Abrir plataforma | True | `platform.open:neo-geo-pocket` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[16].action | `platform.open:wonderswan` | Abrir plataforma | True | `platform.open:wonderswan` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[17].action | `platform.open:msx` | Abrir plataforma | True | `platform.open:msx` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[18].action | `platform.open:zx-spectrum` | Abrir plataforma | True | `platform.open:zx-spectrum` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[19].action | `platform.open:commodore-64` | Abrir plataforma | True | `platform.open:commodore-64` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[20].action | `platform.open:amiga` | Abrir plataforma | True | `platform.open:amiga` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[21].action | `platform.open:colecovision` | Abrir plataforma | True | `platform.open:colecovision` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[22].action | `platform.open:intellivision` | Abrir plataforma | True | `platform.open:intellivision` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[23].action | `platform.open:virtual-boy` | Abrir plataforma | True | `platform.open:virtual-boy` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[24].action | `platform.open:three-do` | Abrir plataforma | True | `platform.open:three-do` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[25].action | `platform.open:sega-cd-32x` | Abrir plataforma | True | `platform.open:sega-cd-32x` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[26].action | `platform.open:nintendo-64` | Abrir plataforma | True | `platform.open:nintendo-64` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[27].action | `platform.open:playstation-2` | Abrir plataforma | True | `platform.open:playstation-2` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[28].action | `platform.open:playstation-portable` | Abrir plataforma | True | `platform.open:playstation-portable` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[29].action | `platform.open:dreamcast` | Abrir plataforma | True | `platform.open:dreamcast` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[30].action | `platform.open:nintendo-ds` | Abrir plataforma | True | `platform.open:nintendo-ds` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[31].action | `platform.open:nintendo-3ds` | Abrir plataforma | True | `platform.open:nintendo-3ds` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[32].action | `platform.open:wii-u` | Abrir plataforma | True | `platform.open:wii-u` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[33].firmwareStatus.action | `firmware.download` | Baixar e instalar firmware oficial da Sony | True | `emulation.action.plan` |   | **routed** | None |
| emulationWorkspace.globalManagement.platformCards[33].action | `platform.open:playstation-3` | Abrir plataforma | True | `platform.open:playstation-3` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[34].action | `platform.open:xbox` | Abrir plataforma | True | `platform.open:xbox` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[35].action | `platform.open:xbox-360` | Abrir plataforma | True | `platform.open:xbox-360` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[36].action | `platform.open:sega-saturn` | Abrir plataforma | True | `platform.open:sega-saturn` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[37].action | `platform.open:sg-1000` | Abrir plataforma | True | `platform.open:sg-1000` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[38].action | `platform.open:neo-geo-cd` | Abrir plataforma | True | `platform.open:neo-geo-cd` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[39].action | `platform.open:vectrex` | Abrir plataforma | True | `platform.open:vectrex` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[40].action | `platform.open:odyssey2` | Abrir plataforma | True | `platform.open:odyssey2` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[41].action | `platform.open:channelf` | Abrir plataforma | True | `platform.open:channelf` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[42].action | `platform.open:pc-engine-supergrafx` | Abrir plataforma | True | `platform.open:pc-engine-supergrafx` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[43].action | `platform.open:atari-st` | Abrir plataforma | True | `platform.open:atari-st` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[44].action | `platform.open:apple2` | Abrir plataforma | True | `platform.open:apple2` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[45].action | `platform.open:playstation-vita` | Abrir plataforma | True | `platform.open:playstation-vita` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[46].action | `platform.open:bbc-micro` | Abrir plataforma | True | `platform.open:bbc-micro` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[47].action | `platform.open:coco` | Abrir plataforma | True | `platform.open:coco` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[48].action | `platform.open:ti99` | Abrir plataforma | True | `platform.open:ti99` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[49].action | `platform.open:zx81` | Abrir plataforma | True | `platform.open:zx81` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[50].action | `platform.open:thomson` | Abrir plataforma | True | `platform.open:thomson` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[51].action | `platform.open:x68000` | Abrir plataforma | True | `platform.open:x68000` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[52].action | `platform.open:pc88` | Abrir plataforma | True | `platform.open:pc88` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[53].action | `platform.open:pc98` | Abrir plataforma | True | `platform.open:pc98` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[54].action | `platform.open:gameandwatch` | Abrir plataforma | True | `platform.open:gameandwatch` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[55].action | `platform.open:supervision` | Abrir plataforma | True | `platform.open:supervision` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[56].action | `platform.open:megaduck` | Abrir plataforma | True | `platform.open:megaduck` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[57].action | `platform.open:doom` | Abrir plataforma | True | `platform.open:doom` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[58].action | `platform.open:quake` | Abrir plataforma | True | `platform.open:quake` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[59].action | `platform.open:pico8` | Abrir plataforma | True | `platform.open:pico8` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[60].action | `platform.open:tic80` | Abrir plataforma | True | `platform.open:tic80` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[61].action | `platform.open:wasm4` | Abrir plataforma | True | `platform.open:wasm4` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[62].action | `platform.open:playstation-4` | Abrir plataforma | True | `platform.open:playstation-4` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.platformCards[63].action | `platform.open:playstation-5` | Abrir plataforma | True | `platform.open:playstation-5` |   | **handled-locally** | None |
| emulationWorkspace.globalManagement.emulators[0].action | `emulator.install:dolphin` | Instalar | True | `emulator.plan` | POST /emulation/emulator/plan | **routed** | None |
| emulationWorkspace.globalManagement.emulators[1].action | `emulator.launch:eden` | Abrir | True | `emulator.launch` | POST /emulation/emulator/launch | **routed** | None |
| emulationWorkspace.globalManagement.emulators[2].action | `emulator.repair:citron` | Reparar | True | `emulator.plan` | POST /emulation/emulator/plan | **routed** | None |
| emulationWorkspace.globalManagement.emulators[3].action | `emulator.stop:ryubing` | Fechar | True | `emulator.stop` | POST /emulation/emulator/stop | **routed** | None |
| system | `admin.health` | Ver saúde administrativa | True | `admin.health` | GET /system/admin/health | **routed** | None |
| emulators | `bios.audit` | Auditar store de BIOS | True | `bios.audit` | GET /bios/audit | **routed** | None |
| emulators | `bios.import.apply` | Confirmar importação de BIOS | True | `bios.import.apply` | POST /bios/import/apply | **routed** | None |
| emulators | `bios.import.plan` | Revisar importação de BIOS | True | `bios.import.plan` | POST /bios/import/plan | **routed** | None |
| emulators | `bios.rollback.apply` | Confirmar rollback de BIOS | True | `bios.rollback.apply` | POST /bios/rollback/apply | **routed** | None |
| emulators | `bios.rollback.plan` | Revisar rollback de BIOS | True | `bios.rollback.plan` | POST /bios/rollback/plan | **routed** | None |
| emulators | `bios.scan` | Selecionar e varrer BIOS | True | `bios.scan` | POST /bios/scan | **routed** | None |
| emulators | `bios.scan.status` | Consultar varredura de BIOS | True | `bios.scan.status` | POST /bios/scan/status | **routed** | None |
| emulators | `bios.sources` | Listar origens aprovadas de BIOS | True | `bios.sources` | GET /bios/sources | **routed** | None |
| emulators | `bios.status` | Consultar requisitos de BIOS | True | `bios.status` | GET /bios/status | **routed** | None |
| cast | `cast.discover` | Descobrir receptores | True | `cast.discover` | GET /cast/discover | **routed** | None |
| cast | `cast.pair` | Parear receptor | True | `cast.pair` | POST /cast/pair | **routed** | None |
| cast | `cast.sessions` | Sessões ativas | True | `cast.sessions` | GET /cast/sessions | **routed** | None |
| cast | `cast.start` | Iniciar transmissão | True | `cast.start` | POST /cast/start | **routed** | None |
| cast | `cast.status` | Status da transmissão | True | `cast.status` | GET /cast/status | **routed** | None |
| cast | `cast.stop` | Parar transmissão | True | `cast.stop` | POST /cast/stop | **routed** | None |
| emulators | `cloud.launch` | Abrir serviço cloud | True | `cloud.launch` | POST /cloud/launch | **routed** | None |
| overview | `collections.apply` | Aplicar alteração de coleção | True | `collections.apply` | POST /collections/apply | **routed** | None |
| overview | `collections.list` | Ver coleções | True | `collections.list` | GET /collections | **routed** | None |
| overview | `collections.plan` | Revisar alteração de coleção | True | `collections.plan` | POST /collections/plan | **routed** | None |
| emulators | `component.apply` | Aplicar componente | True | `component.apply` | POST /component/apply | **routed** | None |
| system | `component.history` | Consultar histórico do componente | True | `component.history` | POST /component/history | **routed** | None |
| emulators | `component.launch` | Abrir componente | True | `component.launch` | POST /component/launch | **routed** | None |
| emulators | `component.list` | Listar componentes | True | `component.list` | GET /component/list | **routed** | None |
| emulators | `component.matrix` | Consultar capacidades de componentes | True | `component.matrix` | GET /component/matrix | **routed** | None |
| emulators | `component.open-config` | Abrir configuração do componente | True | `component.open-config` | None None | **routed** | None |
| emulators | `component.open-config.matrix` | Consultar decisões de configuração | True | `component.open-config.matrix` | GET /component/open-config/matrix | **routed** | None |
| emulators | `component.plan` | Revisar instalação | True | `component.plan` | POST /component/plan | **routed** | None |
| system | `component.recover` | Recuperar componente | True | `component.recover` | None None | **routed** | None |
| system | `component.recovery.apply` | Confirmar recovery | True | `component.recovery.apply` | POST /component/recovery/apply | **routed** | None |
| system | `component.recovery.inspect` | Inspecionar recuperação de componentes | True | `component.recovery.inspect` | GET /component/recovery/inspect | **routed** | None |
| system | `component.recovery.plan` | Revisar recovery | True | `component.recovery.plan` | POST /component/recovery/plan | **routed** | None |
| system | `component.rollback` | Desfazer componente (legado) | True | `component.rollback` | None None | **routed** | None |
| system | `component.rollback.apply` | Confirmar reversão do componente | True | `component.rollback.apply` | POST /component/rollback/apply | **routed** | None |
| system | `component.rollback.plan` | Revisar reversão do componente | True | `component.rollback.plan` | POST /component/rollback/plan | **routed** | None |
| emulators | `component.status` | Consultar componente | True | `component.status` | POST /component/status | **routed** | None |
| emulators | `component.stop` | Revisar parada do componente | True | `component.stop` | POST /component/plan | **routed** | None |
| emulators | `component.verify` | Verificar componente | True | `component.verify` | POST /component/verify | **routed** | None |
| credentials | `credential.delete` | Remover credencial | True | `credential.delete` | POST /scraping/credential/delete | **routed** | None |
| credentials | `credential.save` | Salvar credencial | True | `credential.save` | POST /scraping/credential/save | **routed** | None |
| credentials | `credential.status` | Atualizar credenciais | True | `credential.status` | POST /scraping/credential/status | **routed** | None |
| credentials | `credential.test` | Testar credencial | True | `credential.test` | POST /scraping/credential/test | **routed** | None |
| overview | `desktop.conflict.apply` | Resolver conflito | True | `desktop.conflict.apply` | POST /conflict/apply | **routed** | None |
| overview | `desktop.conflict.plan` | Revisar conflito | True | `desktop.conflict.plan` | POST /conflict/plan | **routed** | None |
| profiles | `desktop.profile.apply` | Aplicar perfil | True | `desktop.profile.apply` | POST /apply | **routed** | None |
| profiles | `desktop.profile.plan` | Revisar perfil | True | `desktop.profile.plan` | POST /plan | **routed** | None |
| profiles | `desktop.profile.reset` | Aplicar modo seguro | True | `desktop.profile.reset` | POST /reset | **routed** | None |
| system | `desktop.recover` | Recuperar Desktop | True | `desktop.recover` | POST /recover | **routed** | None |
| overview | `desktop.status` | Atualizar central | True | `desktop.status` | GET /status | **routed** | None |
| system | `diagnostics.export.apply` | Confirmar exportação revisada | True | `diagnostics.export.apply` | POST /system/diagnostics/export/apply | **routed** | None |
| emulators | `emulation.action.apply` | Confirmar alteração | True | `emulation.action.apply` | POST /emulation/action/apply | **routed** | None |
| emulators | `emulation.action.plan` | Revisar alteração | True | `emulation.action.plan` | POST /emulation/action/plan | **routed** | None |
| system | `emulation.action.rollback` | Desfazer alteração | True | `emulation.action.rollback` | POST /emulation/action/rollback | **routed** | None |
| emulators | `emulator.apply` | Aplicar no emulador | True | `emulator.apply` | POST /emulation/emulator/apply | **routed** | None |
| emulators | `emulator.launch` | Abrir emulador | True | `emulator.launch` | POST /emulation/emulator/launch | **routed** | None |
| emulators | `emulator.plan` | Revisar emulador | True | `emulator.plan` | POST /emulation/emulator/plan | **routed** | None |
| emulators | `emulator.stop` | Parar emulador | True | `emulator.stop` | POST /emulation/emulator/stop | **routed** | None |
| library | `game.launch` | Jogar | True | `game.launch` | POST /emulation/game/launch | **routed** | None |
| steam | `hud.presets` | Consultar presets HUD | True | `hud.presets` | GET /hud/presets | **routed** | None |
| jobs | `job.cancel` | Cancelar tarefa | True | `job.cancel` | POST /emulation/job/cancel | **routed** | None |
| jobs | `job.retry` | Tentar novamente | True | `job.retry` | POST /emulation/job/retry | **routed** | None |
| jobs | `job.status` | Ver tarefa | True | `job.status` | POST /emulation/job/status | **routed** | None |
| jobs | `jobs.list` | Listar tarefas | True | `jobs.list` | GET /emulation/jobs | **routed** | None |
| system | `keyboard.settings` | Salvar conforto do teclado | True | `keyboard.settings` | POST /keyboard/settings | **routed** | None |
| overview | `keyboard.toggle` | Alternar teclado | True | `keyboard.toggle` | POST /keyboard | **routed** | None |
| overview | `library.health` | Ver saúde da coleção | True | `library.health` | GET /library/health | **routed** | None |
| overview | `library.health.apply` | Executar verificação anti-bitrot | True | `library.health.apply` | POST /library/health/apply | **routed** | None |
| overview | `library.health.plan` | Revisar verificação anti-bitrot | True | `library.health.plan` | POST /library/health/plan | **routed** | None |
| library | `library.scan` | Escanear biblioteca | True | `library.scan` | POST /emulation/library/scan | **routed** | None |
| system | `lsfg.apply` | Instalar LSFG | True | `lsfg.apply` | POST /system/lsfg/apply | **routed** | None |
| system | `lsfg.plan` | Revisar LSFG | True | `lsfg.plan` | POST /system/lsfg/plan | **routed** | None |
| system | `lsfg.rollback` | Desfazer LSFG | True | `lsfg.rollback` | POST /system/lsfg/rollback | **routed** | None |
| system | `operations.detail` | Ver detalhes da operação | True | `operations.detail` | POST /system/operations/show | **routed** | None |
| system | `operations.history` | Ver histórico de operações | True | `operations.history` | GET /system/operations | **routed** | None |
| system | `operations.rollback.apply` | Confirmar rollback da operação | True | `operations.rollback.apply` | POST /system/operations/rollback/apply | **routed** | None |
| system | `operations.rollback.plan` | Revisar rollback da operação | True | `operations.rollback.plan` | POST /system/operations/rollback/plan | **routed** | None |
| profiles | `panel.autohide` | Alternar painel | True | `panel.autohide` | POST /panel/autohide | **routed** | None |
| overview | `playtime.continue.emulation` | Continuar jogo emulado | True | `playtime.continue.emulation` | POST /emulation/game/launch | **routed** | None |
| overview | `playtime.continue.steam` | Continuar jogo Steam | True | `playtime.continue.steam` | POST /steam/game/launch | **routed** | None |
| overview | `playtime.recover.steam` | Recuperar sessão Steam | True | `playtime.recover.steam` | POST /steam/gameplay/recover | **routed** | None |
| steam | `profiles.history` | Ver histórico de perfis | True | `profiles.history` | None None | **routed** | None |
| credentials | `provider.link` | Abrir documentação do provider | True | `provider.link` | POST /scraping/provider-link | **routed** | None |
| system | `session.recovery` | Recuperar sessão de jogo | True | `session.recovery` | None None | **routed** | None |
| overview | `session.select` | Trocar sessão | True | `session.select` | POST /session/select | **routed** | None |
| system | `state.export` | Exportar estado | True | `state.export` | POST /system/diagnostics/export/plan | **routed** | None |
| library | `steam.game.launch` | Jogar jogo Steam | True | `steam.game.launch` | POST /steam/game/launch | **routed** | None |
| steam | `steam.gameplay.apply` | Aplicar perfil Steam | True | `steam.gameplay.apply` | POST /steam/gameplay/apply | **routed** | None |
| steam | `steam.gameplay.plan` | Revisar perfil Steam | True | `steam.gameplay.plan` | POST /steam/gameplay/plan | **routed** | None |
| steam | `steam.gameplay.recover` | Recuperar perfil Steam | True | `steam.gameplay.recover` | POST /steam/gameplay/recover | **routed** | None |
| steam | `steam.gameplay.rollback` | Desfazer perfil Steam | True | `steam.gameplay.rollback` | POST /steam/gameplay/rollback | **routed** | None |
| steam | `steam.input.open` | Configurar Steam Input | True | `steam.input.open` | POST /steam/input/open | **routed** | None |
| steam | `steam.launch-options.apply` | Aplicar opções de lançamento | True | `steam.launch-options.apply` | POST /steam/gameplay/launch-options/apply | **routed** | None |
| steam | `steam.launch-options.plan` | Revisar opções de lançamento | True | `steam.launch-options.plan` | POST /steam/gameplay/launch-options/plan | **routed** | None |
| system | `steam.launch-options.rollback` | Desfazer opções de lançamento | True | `steam.launch-options.rollback` | POST /steam/gameplay/launch-options/rollback | **routed** | None |
| steam | `steam.maintenance.apply` | Executar manutenção | True | `steam.maintenance.apply` | POST /steam/maintenance/apply | **routed** | None |
| steam | `steam.maintenance.plan` | Revisar manutenção | True | `steam.maintenance.plan` | POST /steam/maintenance/plan | **routed** | None |
| system | `steam.maintenance.recover` | Recuperar manutenção | True | `steam.maintenance.recover` | POST /steam/maintenance/recover | **routed** | None |
| credentials | `steam.media.apply` | Publicar mídia na Steam | True | `steam.media.apply` | POST /steam/media/apply | **routed** | None |
| credentials | `steam.media.plan` | Revisar publicação Steam | True | `steam.media.plan` | POST /steam/media/plan | **routed** | None |
| system | `steam.media.rollback` | Desfazer publicação Steam | True | `steam.media.rollback` | POST /steam/media/rollback | **routed** | None |
| steam | `steam.open` | Abrir Steam | True | `steam.open` | POST /steam/open | **routed** | None |
| system | `support.bundle` | Exportar pacote de suporte | True | `support.bundle` | POST /system/diagnostics/export/plan | **routed** | None |
| sync | `sync.status` | Ver fila de sincronização | True | `sync.status` | None None | **routed** | None |
| system | `terminal.open` | Abrir terminal | True | `terminal.open` | POST /ashyterm | **routed** | None |
| system | `theme.apply` | Aplicar tema | True | `theme.apply` | POST /theme/apply | **routed** | None |
| system | `theme.apply.confirm` | Confirmar aplicação de tema | True | `theme.apply.confirm` | POST /theme/apply/confirm | **routed** | None |
| system | `theme.apply.rollback` | Reverter aplicação de tema | True | `theme.apply.rollback` | POST /theme/apply/rollback | **routed** | None |
| system | `theme.catalog.install` | Instalar tema curado | True | `theme.catalog.install` | POST /theme/catalog/install | **routed** | None |
| system | `theme.catalog.list` | Listar temas ES-DE curados | True | `theme.catalog.list` | POST /theme/catalog/list | **routed** | None |
| system | `theme.catalog.rollback` | Desfazer instalação de tema | True | `theme.catalog.rollback` | POST /theme/catalog/rollback | **routed** | None |
| system | `theme.catalog.uninstall` | Remover tema instalado | True | `theme.catalog.uninstall` | POST /theme/catalog/uninstall | **routed** | None |
| system | `theme.editor.cancel` | Cancelar sessão de edição | True | `theme.editor.cancel` | POST /theme/editor/cancel | **routed** | None |
| system | `theme.editor.create` | Criar novo tema | True | `theme.editor.create` | POST /theme/editor/create | **routed** | None |
| system | `theme.editor.export` | Exportar tema como ZIP | True | `theme.editor.export` | POST /theme/editor/export | **routed** | None |
| system | `theme.editor.export.apply` | Confirmar exportação do tema | True | `theme.editor.export.apply` | POST /theme/editor/export/apply | **routed** | None |
| system | `theme.editor.load` | Carregar tema para edição | True | `theme.editor.load` | GET /theme/editor/load | **routed** | None |
| system | `theme.editor.preview` | Preview ao vivo do tema editado | True | `theme.editor.preview` | POST /theme/editor/preview | **routed** | None |
| system | `theme.editor.save` | Salvar tema editado | True | `theme.editor.save` | POST /theme/editor/save | **routed** | None |
| system | `theme.editor.set-layout` | Alterar geometria declarativa do tema | True | `theme.editor.set-layout` | POST /theme/editor/set-layout | **routed** | None |
| system | `theme.editor.set-metadata` | Alterar metadados de tema | True | `theme.editor.set-metadata` | POST /theme/editor/set-metadata | **routed** | None |
| system | `theme.editor.set-tokens` | Alterar tokens de tema | True | `theme.editor.set-tokens` | POST /theme/editor/set-tokens | **routed** | None |
| system | `theme.import.esde.apply` | Importar esquema de tema ES-DE | True | `theme.import.esde.apply` | POST /theme/import/esde/apply | **routed** | None |
| system | `theme.import.esde.inspect` | Examinar tema ES-DE antes de importar | True | `theme.import.esde.inspect` | POST /theme/import/esde/inspect | **routed** | None |
| system | `theme.import.package.apply` | Importar pacote de tema SteamZero | True | `theme.import.package.apply` | POST /theme/import/package/apply | **routed** | None |
| system | `theme.import.package.inspect` | Examinar pacote de tema antes de importar | True | `theme.import.package.inspect` | POST /theme/import/package/inspect | **routed** | None |
| system | `theme.import.retrofe.apply` | Importar cena RetroFE compilada | True | `theme.import.retrofe.apply` | POST /theme/import/retrofe/apply | **routed** | None |
| system | `theme.import.retrofe.inspect` | Examinar cena RetroFE antes de importar | True | `theme.import.retrofe.inspect` | POST /theme/import/retrofe/inspect | **routed** | None |
| system | `theme.list` | Listar temas disponíveis | True | `theme.list` | GET /theme/list | **routed** | None |
| system | `theme.scene.render` | Renderizar a cena do tema instalado | True | `theme.scene.render` | POST /theme/scene/render | **routed** | None |
| system | `theme.store.gc` | Recuperar espaço de assets sem dono | True | `theme.store.gc` | POST /theme/store/gc | **routed** | None |
| credentials | `credential.status` | Atualizar credenciais | True | `credential.status` | POST /scraping/credential/status | **routed** | None |
| handheld-drawer | `session.select` | Trocar sessão | True | `session.select` | POST /session/select | **routed** | None |
| jobs | `jobs.list` | Listar tarefas | True | `jobs.list` | GET /emulation/jobs | **routed** | None |
| notifications | `desktop.status` | Atualizar central | True | `desktop.status` | GET /status | **routed** | None |
| plan-dialogs | `desktop.profile.plan` | Revisar perfil | True | `desktop.profile.plan` | POST /plan | **routed** | None |
| recovery | `session.recovery` | Recuperar sessão de jogo | True | `session.recovery` | None None | **routed** | None |
| sidebar | `keyboard.toggle` | Alternar teclado | True | `keyboard.toggle` | POST /keyboard | **routed** | None |
| task-drawer | `jobs.list` | Listar tarefas | True | `jobs.list` | GET /emulation/jobs | **routed** | None |
| themes | `theme.catalog.list` | Listar temas ES-DE curados | True | `theme.catalog.list` | POST /theme/catalog/list | **routed** | None |
