# Matriz de controles — árvore QML viva

- contexto: `1600x1000` · tema `org.steamzero.default` · alto contraste `False` · dados `fallback-qml`
- controles inventariados: **341** em **12** superfícies
- veredito: `{'handled-locally': 268, 'blocked-explained': 15, 'decorative': 31, 'not-probed': 7, 'routed': 20}`

| Tela | Controle | Label | AccessibleName | Enabled | ActionId | Efeito observável | Resultado |
|---|---|---|---|---|---|---|---|
| overview | button | Explorar sistemas | Explorar sistemas | True | `—` | mudou estado | **handled-locally** |
| overview | button | Ver biblioteca | Ver biblioteca | True | `—` | mudou estado | **handled-locally** |
| overview | button | Coleções indisponíveis | — | False | `—` | — | **blocked-explained** |
| overview | button | Abrir sistema | Abrir sistema | True | `—` | mudou estado | **handled-locally** |
| overview | button | Abrir recentes | Abrir recentes | True | `—` | mudou estado | **handled-locally** |
| overview | button | Todos os sistemas | Todos os sistemas | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Steam, 0 jogo(s), Nenhum jogo Steam publicado | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Emuladores: Nenhuma pendência publicada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Saves e sync: Nenhuma fila pendente publicada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Diagnóstico e mídia: Estado detalhado disponível no Sistema | True | `—` | mudou estado | **handled-locally** |
| emulators | combobox | Gestão geral | Selecionar plataforma de emulação | False | `—` | — | **blocked-explained** |
| emulators | button | — | — | False | `—` | — | **decorative** |
| steam | combobox | — | Selecionar jogo | False | `—` | — | **blocked-explained** |
| steam | button | — | — | False | `—` | — | **decorative** |
| steam | toggle | Global | Global | True | `—` | mudou estado | **handled-locally** |
| steam | toggle | Por jogo | Por jogo | True | `—` | mudou estado | **handled-locally** |
| steam | toggle | Portátil | Portátil | True | `—` | mudou estado | **handled-locally** |
| steam | toggle | Dock | Dock | True | `—` | mudou estado | **handled-locally** |
| steam | toggle | Desempenho e LSFG | Abrir área Desempenho e LSFG | True | `—` | mudou estado | **handled-locally** |
| steam | toggle | Controles | Abrir área Controles | True | `—` | mudou estado | **handled-locally** |
| steam | toggle | Biblioteca | Abrir área Biblioteca | True | `—` | mudou estado | **handled-locally** |
| steam | toggle | Modo Desktop | Abrir área Modo Desktop | True | `—` | mudou estado | **handled-locally** |
| steam | toggle | Economia 30 FPS | Economia 30 FPS | True | `—` | mudou estado | **handled-locally** |
| steam | toggle | Equilibrado 40 FPS Recomendado | Equilibrado 40 FPS Recomendado | True | `—` | mudou estado | **handled-locally** |
| steam | toggle | Desempenho 60 FPS | Desempenho 60 FPS | True | `—` | mudou estado | **handled-locally** |
| steam | toggle | 30 | 30 FPS | True | `—` | mudou estado | **handled-locally** |
| steam | toggle | 40 | 40 FPS | True | `—` | mudou estado | **handled-locally** |
| steam | toggle | 60 | 60 FPS | True | `—` | mudou estado | **handled-locally** |
| steam | slider | — | TDP | False | `—` | — | **blocked-explained** |
| steam | toggle | Automático | Automático | True | `—` | mudou estado | **handled-locally** |
| steam | toggle | Manual | Manual | False | `—` | — | **blocked-explained** |
| steam | toggle | — | Ativar Gamescope | False | `—` | — | **blocked-explained** |
| steam | toggle | — | Ativar Feral GameMode | False | `—` | — | **blocked-explained** |
| steam | toggle | Desligado | Desligado | True | `—` | mudou estado | **handled-locally** |
| steam | toggle | Básico | Básico | False | `—` | — | **blocked-explained** |
| steam | toggle | Detalhado | Detalhado | False | `—` | — | **blocked-explained** |
| steam | combobox | Desligado | Pós-processamento vkBasalt por jogo | False | `—` | — | **blocked-explained** |
| steam | button | — | — | False | `—` | — | **decorative** |
| steam | combobox | FSR 2 · Qualidade | Selecionar upscaling | True | `—` | tipo combobox exige gesto, não clique | **not-probed** |
| steam | button | — | — | False | `—` | — | **decorative** |
| steam | combobox | Desligado | Geração de quadros LSFG por jogo | True | `—` | tipo combobox exige gesto, não clique | **not-probed** |
| steam | button | — | — | False | `—` | — | **decorative** |
| steam | button | Configurações avançadas | Configurações avançadas | False | `—` | — | **blocked-explained** |
| steam | button | — | — | False | `—` | — | **decorative** |
| steam | button | — | — | False | `—` | — | **decorative** |
| steam | button | — | — | False | `—` | — | **decorative** |
| steam | button | — | — | False | `—` | — | **decorative** |
| steam | button | Restaurar perfil seguro | Restaurar perfil seguro | True | `steam.gameplay.plan` | mudou estado | **routed** |
| steam | button | Revisar e aplicar perfil | Revisar e aplicar perfil | False | `—` | — | **blocked-explained** |
| profiles | toggle | — | Automático. Recomendado sim. Aplicado não | True | `—` | mudou estado | **handled-locally** |
| profiles | toggle | — | Portátil. Recomendado não. Aplicado sim | True | `—` | mudou estado | **handled-locally** |
| profiles | toggle | — | Dock. Recomendado não. Aplicado não | True | `—` | mudou estado | **handled-locally** |
| profiles | toggle | — | Seguro. Recomendado não. Aplicado não | True | `—` | mudou estado | **handled-locally** |
| profiles | combobox | Automático | Selecionar perfil | True | `—` | tipo combobox exige gesto, não clique | **not-probed** |
| profiles | button | — | — | False | `—` | — | **decorative** |
| profiles | button | Revisar alterações | Revisar alterações | True | `desktop.profile.plan` | mudou estado | **routed** |
| sync | button | Atualizar status | Atualizar status | True | `—` | mudou estado | **handled-locally** |
| cast | button | Descobrir receptores | Descobrir receptores | True | `cast.discover` | mudou estado | **routed** |
| cast | button | Parear receptor | Parear receptor | False | `—` | — | **blocked-explained** |
| cast | combobox | Monitor | Origem da captura | True | `—` | tipo combobox exige gesto, não clique | **not-probed** |
| cast | button | Iniciar transmissão | Iniciar transmissão | False | `—` | — | **blocked-explained** |
| cast | button | Parar transmissão | Parar transmissão | True | `cast.stop` | mudou estado | **routed** |
| cast | button | Status | Status | True | `cast.status` | mudou estado | **routed** |
| cast | button | Sessões ativas | Sessões ativas | True | `cast.sessions` | mudou estado | **routed** |
| system | button | — | — | False | `—` | — | **decorative** |
| system | button | Abrir biblioteca | Abrir biblioteca Steam para Lossless Scaling | True | `steam.open` | mudou estado | **routed** |
| system | button | — | — | False | `—` | — | **decorative** |
| system | button | Exportar estado | Exportar estado | True | `—` | mudou estado | **handled-locally** |
| system | button | Pacote de suporte | Pacote de suporte | True | `—` | abre FileDialog nativo; indisponível na plataforma offscreen | **not-probed** |
| system | button | Importar tema ES-DE | Importar tema ES-DE | True | `—` | mudou estado | **handled-locally** |
| system | button | Saúde administrativa | Saúde administrativa | True | `admin.health` | mudou estado | **routed** |
| system | button | Executar verificação | Executar verificação | True | `—` | mudou estado | **handled-locally** |
| system | button | Abrir teclado virtual | Abrir teclado virtual | True | `keyboard.toggle` | mudou estado | **routed** |
| themes | toggle | Obter temas | Obter temas | True | `—` | mudou estado | **handled-locally** |
| themes | toggle | Editar aparência | Editar aparência | True | `—` | mudou estado | **handled-locally** |
| themes | button | Atualizar | Atualizar | False | `—` | — | **blocked-explained** |
| themes | button | Verificar | Verificar | True | `theme.store.gc` | mudou estado | **routed** |
| library | button | — | Steam, 0 jogos, Nenhum jogo Steam instalado foi publicado | True | `—` | mudou estado | **handled-locally** |
| sidebar | button | Visão geral | Visão geral | True | `—` | mudou estado | **handled-locally** |
| sidebar | button | — | — | False | `—` | — | **decorative** |
| sidebar | button | Emulação | Emulação | True | `—` | mudou estado | **handled-locally** |
| sidebar | button | — | — | False | `—` | — | **decorative** |
| sidebar | button | Steam | Steam | True | `—` | mudou estado | **handled-locally** |
| sidebar | button | — | — | False | `—` | — | **decorative** |
| sidebar | button | Perfis | Perfis | True | `—` | mudou estado | **handled-locally** |
| sidebar | button | — | — | False | `—` | — | **decorative** |
| sidebar | button | Saves e Sync | Saves e Sync | True | `—` | mudou estado | **handled-locally** |
| sidebar | button | — | — | False | `—` | — | **decorative** |
| sidebar | button | Transmissão | Transmissão | True | `—` | mudou estado | **handled-locally** |
| sidebar | button | — | — | False | `—` | — | **decorative** |
| sidebar | button | Sistema | Sistema | True | `—` | mudou estado | **handled-locally** |
| sidebar | button | — | — | False | `—` | — | **decorative** |
| sidebar | button | Temas | Temas | True | `—` | mudou estado | **handled-locally** |
| sidebar | button | — | — | False | `—` | — | **decorative** |
| sidebar | button | Biblioteca | Biblioteca | True | `—` | mudou estado | **handled-locally** |
| sidebar | button | — | — | False | `—` | — | **decorative** |
| sidebar | button | Tarefas | Abrir central de tarefas | True | `—` | mudou estado | **handled-locally** |
| sidebar | button | Quick Reset | Quick Reset | True | `desktop.profile.plan` | mudou estado | **routed** |
| sidebar | button | Cloud Sync | Cloud Sync | True | `—` | mudou estado | **handled-locally** |
| sidebar | button | steamzero doctor | steamzero doctor | True | `—` | mudou estado | **handled-locally** |
| handheld-drawer | button | Fechar | Fechar navegação | True | `—` | mudou estado | **handled-locally** |
| handheld-drawer | button | Visão geral | Visão geral | True | `—` | mudou estado | **handled-locally** |
| handheld-drawer | button | Emulação | Emulação | True | `—` | mudou estado | **handled-locally** |
| handheld-drawer | button | Steam | Steam | True | `—` | mudou estado | **handled-locally** |
| handheld-drawer | button | Perfis | Perfis | True | `—` | mudou estado | **handled-locally** |
| handheld-drawer | button | Saves e Sync | Saves e Sync | True | `—` | mudou estado | **handled-locally** |
| handheld-drawer | button | Transmissão | Transmissão | True | `—` | mudou estado | **handled-locally** |
| handheld-drawer | button | Sistema | Sistema | True | `—` | mudou estado | **handled-locally** |
| handheld-drawer | button | Temas | Temas | True | `—` | mudou estado | **handled-locally** |
| handheld-drawer | button | Biblioteca | Biblioteca | True | `—` | mudou estado | **handled-locally** |
| task-drawer | button | Atualizar | Atualizar | True | `—` | — | **handled-locally** |
| task-drawer | button | Fechar | Fechar central de tarefas | True | `—` | mudou estado | **handled-locally** |
| system | button | — | — | False | `—` | — | **decorative** |
| system | button | Abrir biblioteca | Abrir biblioteca Steam para Lossless Scaling | True | `steam.open` | mudou estado | **routed** |
| system | button | — | — | False | `—` | — | **decorative** |
| system | button | Exportar estado | Exportar estado | True | `—` | mudou estado | **handled-locally** |
| system | button | Pacote de suporte | Pacote de suporte | True | `—` | abre FileDialog nativo; indisponível na plataforma offscreen | **not-probed** |
| system | button | Importar tema ES-DE | Importar tema ES-DE | True | `—` | mudou estado | **handled-locally** |
| system | button | Saúde administrativa | Saúde administrativa | True | `admin.health` | mudou estado | **routed** |
| system | button | Executar verificação | Executar verificação | True | `—` | mudou estado | **handled-locally** |
| system | button | Abrir teclado virtual | Abrir teclado virtual | True | `keyboard.toggle` | mudou estado | **routed** |
| sidebar | button | Estado degradado | Estado degradado | True | `—` | mudou estado | **handled-locally** |
| sidebar | button | — | — | False | `—` | — | **decorative** |
| overview | button | — | Nintendo Switch, 0 jogo(s), Verificação pendente | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Game Boy, Game Boy Color e Game Boy Advance, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Nintendo Entertainment System e Famicom, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Super Nintendo Entertainment System, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Sega Mega Drive e Genesis, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Arcade, CPS, Neo Geo e MAME, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Sony PlayStation, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | NVIDIA GeForce NOW, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Xbox Cloud Gaming, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Amazon Luna, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Nintendo GameCube e Wii, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Sega Master System, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Sega Game Gear, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | NEC PC Engine e TurboGrafx-16, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Atari 2600, 5200, 7800, Lynx e Jaguar, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | SNK Neo Geo Pocket e Pocket Color, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Bandai WonderSwan e WonderSwan Color, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | MSX e MSX2, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Sinclair ZX Spectrum, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Commodore 64, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Commodore Amiga e Amiga CD32, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | ColecoVision, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Mattel Intellivision, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Nintendo Virtual Boy, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | 3DO Interactive Multiplayer, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Sega CD e Sega 32X, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Nintendo 64, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Sony PlayStation 2, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Sony PlayStation Portable, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Sega Dreamcast, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Nintendo DS, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Nintendo 3DS, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Nintendo Wii U, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Sony PlayStation 3, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Microsoft Xbox, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Microsoft Xbox 360, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Sega Saturn, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | SG-1000, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Neo Geo CD, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Vectrex, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Magnavox Odyssey², 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Fairchild Channel F, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | PC Engine SuperGrafx, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Atari ST, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Apple II, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Sony PlayStation Vita, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | BBC Micro, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Tandy Color Computer, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | TI-99/4A, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | ZX81, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Thomson MO5/TO8, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Sharp X68000, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | PC-8800 Series, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | PC-9800 Series, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Game & Watch, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Watara Supervision, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Creatronic Mega Duck, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | DOOM, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Quake, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | PICO-8, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | TIC-80, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | WASM-4, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Sony PlayStation 4, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Sony PlayStation 5, 0 jogo(s), Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Emuladores: 2 item(ns) exigem atenção | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Instalar | Dolphin: Instalar | True | `emulator.plan` | mudou estado | **routed** |
| emulators | button | Abrir | Eden: Abrir | True | `emulator.launch` | mudou estado | **routed** |
| emulators | button | Reparar | Citron: Reparar | True | `emulator.plan` | mudou estado | **routed** |
| emulators | button | Fechar | Ryubing: Fechar | True | `emulator.stop` | mudou estado | **routed** |
| emulators | button | Abrir plataforma | Nintendo Switch: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Ver emuladores | Ver emuladores | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Game Boy, Game Boy Color e Game Boy Advance: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Nintendo Entertainment System e Famicom: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Super Nintendo Entertainment System: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Sega Mega Drive e Genesis: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Arcade, CPS, Neo Geo e MAME: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Sony PlayStation: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | NVIDIA GeForce NOW: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Xbox Cloud Gaming: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Amazon Luna: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Nintendo GameCube e Wii: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Sega Master System: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Sega Game Gear: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | NEC PC Engine e TurboGrafx-16: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Atari 2600, 5200, 7800, Lynx e Jaguar: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | SNK Neo Geo Pocket e Pocket Color: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Bandai WonderSwan e WonderSwan Color: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | MSX e MSX2: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Sinclair ZX Spectrum: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Commodore 64: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Commodore Amiga e Amiga CD32: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | ColecoVision: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Mattel Intellivision: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Nintendo Virtual Boy: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | 3DO Interactive Multiplayer: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Sega CD e Sega 32X: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Nintendo 64: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Sony PlayStation 2: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Sony PlayStation Portable: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Sega Dreamcast: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Nintendo DS: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Nintendo 3DS: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Nintendo Wii U: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Sony PlayStation 3: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Microsoft Xbox: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Microsoft Xbox 360: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Sega Saturn: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | SG-1000: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Neo Geo CD: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Vectrex: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Magnavox Odyssey²: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Fairchild Channel F: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | PC Engine SuperGrafx: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Atari ST: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Apple II: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Sony PlayStation Vita: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | BBC Micro: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Tandy Color Computer: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | TI-99/4A: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | ZX81: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Thomson MO5/TO8: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Sharp X68000: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | PC-8800 Series: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | PC-9800 Series: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Game & Watch: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Watara Supervision: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Creatronic Mega Duck: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | DOOM: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Quake: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | PICO-8: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | TIC-80: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | WASM-4: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Sony PlayStation 4: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| emulators | button | Abrir plataforma | Sony PlayStation 5: Abrir plataforma | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Nintendo Switch, 0 jogos, Verificação pendente | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Game Boy, Game Boy Color e Game Boy Advance, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Nintendo Entertainment System e Famicom, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Super Nintendo Entertainment System, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Sega Mega Drive e Genesis, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Arcade, CPS, Neo Geo e MAME, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Sony PlayStation, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | NVIDIA GeForce NOW, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Xbox Cloud Gaming, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Amazon Luna, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Nintendo GameCube e Wii, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Sega Master System, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Sega Game Gear, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | NEC PC Engine e TurboGrafx-16, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Atari 2600, 5200, 7800, Lynx e Jaguar, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | SNK Neo Geo Pocket e Pocket Color, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Bandai WonderSwan e WonderSwan Color, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | MSX e MSX2, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Sinclair ZX Spectrum, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Commodore 64, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Commodore Amiga e Amiga CD32, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | ColecoVision, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Mattel Intellivision, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Nintendo Virtual Boy, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | 3DO Interactive Multiplayer, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Sega CD e Sega 32X, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Nintendo 64, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Sony PlayStation 2, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Sony PlayStation Portable, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Sega Dreamcast, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Nintendo DS, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Nintendo 3DS, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Nintendo Wii U, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Sony PlayStation 3, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Microsoft Xbox, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Microsoft Xbox 360, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Sega Saturn, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | SG-1000, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Neo Geo CD, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Vectrex, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Magnavox Odyssey², 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Fairchild Channel F, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | PC Engine SuperGrafx, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Atari ST, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Apple II, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Sony PlayStation Vita, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | BBC Micro, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Tandy Color Computer, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | TI-99/4A, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | ZX81, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Thomson MO5/TO8, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Sharp X68000, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | PC-8800 Series, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | PC-9800 Series, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Game & Watch, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Watara Supervision, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Creatronic Mega Duck, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | DOOM, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Quake, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | PICO-8, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | TIC-80, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | WASM-4, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Sony PlayStation 4, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Sony PlayStation 5, 0 jogos, Integração planejada | True | `—` | mudou estado | **handled-locally** |
| overview | button | — | Nintendo Switch, 0 jogo(s), Pronto | True | `—` | mudou estado | **handled-locally** |
| library | button | — | Nintendo Switch, 0 jogos, Pronto | True | `—` | mudou estado | **handled-locally** |
| task-drawer | button | Cancelar | Cancelar emulator.install | True | `job.cancel` | mudou estado | **routed** |
| task-drawer | button | Tentar novamente | Tentar novamente emulator.install | True | `job.retry` | mudou estado | **routed** |
| steam | button | — | — | False | `—` | — | **decorative** |
| steam | button | — | — | False | `—` | — | **decorative** |
| steam | button | — | — | False | `—` | — | **decorative** |
| steam | button | Ver instruções | Ver instruções | True | `—` | mudou estado | **handled-locally** |
| steam | button | — | — | False | `—` | — | **decorative** |
| steam | button | — | — | False | `—` | — | **decorative** |
| steam | button | — | — | False | `—` | — | **decorative** |
| steam | button | — | — | False | `—` | — | **decorative** |
| steam | button | Abrir Sistema | Abrir Sistema | True | `—` | mudou estado | **handled-locally** |
| steam | combobox | Nativo | Selecionar upscaling | True | `—` | tipo combobox exige gesto, não clique | **not-probed** |
| profiles | toggle | — | Portátil. Recomendado não. Aplicado não | True | `—` | mudou estado | **handled-locally** |
| sidebar | button | Estado não aplicado | Estado não aplicado | True | `—` | mudou estado | **handled-locally** |
| system | button | Restaurar estado seguro | Restaurar estado seguro | True | `—` | mudou estado | **handled-locally** |
| sidebar | button | Recuperação pendente | Recuperação pendente | True | `—` | mudou estado | **handled-locally** |
| sidebar | button | Estado desatualizado | Estado desatualizado | True | `—` | mudou estado | **handled-locally** |
| task-drawer | button | Tentar novamente | Tentar carregar tarefas novamente | True | `—` | — | **handled-locally** |
