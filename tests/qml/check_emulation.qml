// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Window
import "../../src/steamzero/ui/qml"

Window {
    id: harness
    visible: true
    width: 1400
    height: 900
    property int failures: 0
    property int checks: 0
    property int firstFailure: 0

    function check(condition, message) {
        checks += 1
        if (condition)
            return
        if (firstFailure === 0)
            firstFailure = checks
        failures += 1
        console.error("FAIL: " + message)
    }

    function makePage(payload) {
        const object = pageComponent.createObject(harness, {"emulation": payload})
        check(object !== null, "Emulation.qml deve ser instanciável")
        return object
    }

    function testHierarchy() {
        const object = makePage({
            "platforms": [{
                "id": "switch",
                "name": "Nintendo Switch",
                "iconKey": "switch",
                "state": "ready",
                "statusLabel": "Pronto",
                "readiness": {"percent": 75, "title": "Quase pronto", "blockers": []},
                "emulators": [{"id": "eden", "name": "Eden", "state": "ready", "iconAsset": "../assets/eden.svg"}],
                "games": [{"id": "0100", "name": "Jogo de teste"}],
                "runtimeProfiles": {
                    "activeScope": "handheld",
                    "observedScope": "handheld",
                    "desiredScope": null,
                    "diverged": null,
                    "autoTransition": {"supported": false, "reason": "Sem executor"},
                    "handheld": {
                        "resolution": {"width": 1280, "height": 720},
                        "renderScale": 1.0,
                        "controllers": {"activePlayers": 1, "maximumPlayers": 4},
                        "tdp": {"value": null, "source": "steam-game-profile"},
                        "fps": {"value": null, "source": "steam-game-profile"}
                    },
                    "dock": {
                        "resolution": {"width": 1920, "height": 1080},
                        "renderScale": 1.0,
                        "controllers": {"activePlayers": 2, "maximumPlayers": 4},
                        "tdp": {"value": null, "source": "steam-game-profile"},
                        "fps": {"value": null, "source": "steam-game-profile"}
                    }
                }
            }]
        })
        if (!object)
            return
        check(object.selectedPlatform.id === "switch", "Switch deve ser a plataforma inicial")
        check(object.readinessPercent() === 75, "prontidão deve ser normalizada")
        check(object.scopes.length === 5, "devem existir cinco escopos")
        check(object.areas.length === 11, "devem existir onze áreas especializadas")
        object.scopeIndex = 1
        check(object.scopeId() === "emulator", "escopo Emulador deve ser selecionável")
        check(object.contextTitle() === "Eden", "emulador deve definir o contexto")
        object.scopeIndex = 2
        check(object.contextTitle() === "Jogo de teste", "jogo deve definir o contexto")
        object.scopeIndex = 3
        check(object.contextTitle() === "Modo portátil", "escopo portátil deve ser explícito")
        check(object.scopedRuntimeProfile().resolution.width === 1280,
              "perfil portátil deve consumir a resolução publicada")
        check(object.inheritedValue("tdp", "perfil Steam/jogo").indexOf("herdado") === 0,
              "TDP sem valor observado deve ser identificado como herdado")
        object.scopeIndex = 4
        check(object.contextTitle() === "Modo dock", "escopo dock deve ser explícito")
        check(object.scopedRuntimeProfile().controllers.activePlayers === 2,
              "perfil dock deve consumir controles observados")

        object.scopeIndex = 1
        object.areaIndex = object.areaIndexById("controls")
        object.emulation = {
            "platforms": [{
                "id": "switch",
                "name": "Nintendo Switch",
                "state": "ready",
                "selectedScope": "global",
                "selectedArea": "overview",
                "readiness": {"percent": 80, "title": "Pronto", "blockers": []},
                "emulators": [{"id": "eden", "name": "Eden", "state": "ready", "iconAsset": "../assets/eden.svg"}],
                "games": []
            }]
        }
        object.syncPublishedSelection()
        check(object.scopeId() === "emulator", "refresh da mesma plataforma deve preservar escopo local")
        check(object.selectedArea.id === "controls", "refresh deve preservar a área local")
        check(object.localPath("file:///tmp/keys%20de%20teste.keys") === "/tmp/keys de teste.keys",
              "URL de arquivo deve chegar ao backend como caminho local")
        object.destroy()
    }

    function testSafeFallback() {
        const object = makePage({})
        if (!object)
            return
        check(object.selectedPlatform.id === "switch", "fallback deve permanecer na plataforma Switch")
        check(object.readinessPercent() === 0, "fallback não pode alegar prontidão")
        check(object.emulators.length === 0, "fallback não pode inventar emulador")
        check(object.games.length === 0, "fallback não pode inventar jogo")
        check(object.primaryAction().enabled === false, "ação sem backend deve ficar bloqueada")
        check(object.primaryAction().requiresConfirmation === true, "ação mutável deve exigir confirmação")
        object.destroy()
    }

    function testBackendArea() {
        const object = makePage({
            "platforms": [{
                "id": "switch",
                "name": "Nintendo Switch",
                "state": "degraded",
                "selectedScope": "emulator",
                "selectedArea": "keysFirmware",
                "readiness": {"percent": 20, "title": "Preparação", "blockers": ["Keys"]},
                "areaData": {
                    "keysFirmware": {
                        "cards": [{
                            "title": "Firmware",
                            "state": "compatible",
                            "statusLabel": "18.0.1",
                            "detail": "Validado",
                            "count": 2
                        }],
                        "primaryAction": {
                            "id": "keys-import",
                            "label": "Importar",
                            "enabled": true,
                            "requiresConfirmation": true
                        }
                    }
                }
            }]
        })
        if (!object)
            return
        object.syncPublishedSelection()
        check(object.scopeId() === "emulator", "seleção de escopo publicada deve ser restaurada")
        check(object.selectedArea.id === "keysFirmware", "seleção de área publicada deve ser restaurada")
        check(object.cards().length === 1, "cards do backend devem substituir o fallback")
        check(object.cards()[0].statusLabel === "18.0.1", "status do backend deve ser preservado")
        check(object.cardMetric(object.cards()[0]) === "2", "contagem do backend deve ser apresentada")
        check(object.primaryAction().id === "keys-import", "ação versionada deve ser consumida")
        check(object.primaryAction().enabled === true, "capacidade confirmada pode liberar a ação")
        object.width = 949
        object.height = 593
        check(object.compactPrimaryActionControl.contentItem.color === object.textColor,
              "CTA primário compacto habilitado deve preservar contraste claro")
        object.destroy()
    }

    function testGameLibraryJourney() {
        const object = makePage({
            "platforms": [{
                "id": "switch",
                "name": "Nintendo Switch",
                "state": "ready",
                "selectedScope": "game",
                "selectedArea": "overview",
                "readiness": {"percent": 100, "title": "Pronto", "blockers": []},
                "emulators": [{"id": "eden", "name": "Eden", "state": "ready"}],
                "games": [
                    {"id": "b", "path": "/roms/b.nsp", "name": "Zelda", "titleId": "010000000000B000", "size": 20, "format": "nsp", "state": "ready", "statusLabel": "NSP", "steamSelected": true, "steamPublished": true},
                    {"id": "a", "path": "/roms/a.nsz", "name": "Mario", "titleId": "010000000000A000", "size": 10, "format": "nsz", "state": "ready", "statusLabel": "NSZ", "coverUrl": "file:///tmp/cover.png", "playAction": {"id": "game.launch:a", "label": "Jogar", "enabled": true}}
                ]
            }]
        })
        if (!object)
            return
        object.syncPublishedSelection()
        check(object.isGameLibrary(), "escopo Por jogo deve abrir a biblioteca estruturada")
        check(object.filteredGames()[0].name === "Mario", "ordenação inicial deve usar o nome")
        object.gameSearchText = "zelda"
        check(object.filteredGames().length === 1, "busca deve filtrar pelo nome")
        check(object.filteredGames()[0].id === "b", "busca deve preservar o jogo correspondente")
        object.gameSearchText = "010000000000A000"
        check(object.filteredGames()[0].id === "a", "busca deve aceitar Title ID")
        object.gameSearchText = ""
        object.setGameSort("size")
        check(object.filteredGames()[0].id === "a", "ordenação crescente deve aceitar tamanho")
        object.setGameSort("size")
        check(object.filteredGames()[0].id === "b", "segunda seleção deve inverter a ordenação")
        object.selectGame(object.games[1])
        check(object.selectedGame.id === "a", "seleção da linha deve atualizar o painel do jogo")
        check(object.compatibilityState(object.selectedGame, "eden") === "unknown",
              "compatibilidade ausente não pode ser inventada")
        check(object.gamePlayAction(object.selectedGame).enabled === true,
              "Jogar deve consumir a ação publicada pelo backend")
        object.pendingEmulatorGameId = object.selectedGame.id
        object.pendingEmulatorId = "eden"
        check(object.gamePlayAction(object.selectedGame).enabled === false,
              "Jogar deve bloquear enquanto a troca de emulador não foi confirmada")
        object.cancelPendingEmulatorSelection()
        check(object.gamePlayAction(object.selectedGame).enabled === true,
              "cancelar a troca deve restaurar a ação persistida")
        check(object.steamSelectedCount() === 1, "seleção Steam deve ser contada")
        check(object.steamPublishedCount() === 1, "atalho Steam publicado deve ser contado")
        check(object.coverCount() === 1, "contagem de capas deve refletir apenas mídia publicada")
        object.width = 949
        object.height = 593
        object.selectGame(object.games[1])
        check(!object.libraryListControl.visible,
              "ajustes compactos devem substituir a lista sem sobreposição")
        check(object.gameDetailsControl.visible,
              "ajustes do jogo devem ocupar a largura handheld")
        object.gameDetailsOpen = false
        check(object.libraryListControl.visible,
              "fechar ajustes deve restaurar a biblioteca")
        object.destroy()
    }

    function testEmulatorMaintenanceListsEveryManagedEmulator() {
        const object = makePage({
            "platforms": [{
                "id": "switch",
                "name": "Nintendo Switch",
                "state": "ready",
                "selectedScope": "emulator",
                "selectedArea": "overview",
                "readiness": {"percent": 100, "title": "Pronto", "blockers": []},
                "emulators": [
                    {"id": "eden", "name": "Eden", "state": "ready", "isDefault": true, "running": true, "version": "0.0.3", "targetVersion": "0.0.3", "libraryRootCount": 1, "health": {"versionCurrent": true, "keysReady": true}},
                    {"id": "citron", "name": "Citron", "state": "ready"},
                    {"id": "ryubing", "name": "Ryubing", "state": "ready"}
                ],
                "games": []
            }]
        })
        if (!object)
            return
        object.syncPublishedSelection()
        check(object.emulatorMaintenanceCount === 3,
              "a aba Emulador deve exibir os três emuladores")
        check(object.emulators[0].isDefault === true,
              "emulador padrão publicado deve permanecer identificável")
        check(object.emulators[0].running === true,
              "estado em execução publicado deve permanecer identificável")
        object.destroy()
    }

    function testLibraryRootManagementIsScrollableAndTouchSafe() {
        const actions = [
            "Abrir pasta", "Varrer agora", "Auditar/higienizar",
            "Corrigir nomes", "Remover da biblioteca", "Adicionar mídia para um jogo"
        ].map(function(label, index) {
            return {
                "id": "library.root.test:" + index,
                "label": label,
                "enabled": true,
                "reason": null,
                "requiresConfirmation": index > 0
            }
        })
        const object = makePage({
            "platforms": [{
                "id": "switch",
                "name": "Nintendo Switch",
                "state": "ready",
                "selectedScope": "global",
                "selectedArea": "media",
                "readiness": {"percent": 100, "title": "Pronto", "blockers": []},
                "emulators": [],
                "games": [{"id": "game", "name": "Jogo", "state": "ready"}],
                "areaData": {
                    "media": {
                        "cards": [{
                            "id": "library-root-test",
                            "title": "Diretório de ROMs",
                            "state": "ready",
                            "statusLabel": "Acessível",
                            "detail": "~/Games/ROMs · 10 bases · última varredura agora",
                            "actions": actions
                        }],
                        "primaryAction": {
                            "id": "library.root.add",
                            "label": "Adicionar diretório",
                            "enabled": true,
                            "reason": null,
                            "requiresConfirmation": true
                        }
                    }
                }
            }]
        })
        if (!object)
            return
        object.syncPublishedSelection()
        const viewports = [
            {"width": 949, "height": 593},
            {"width": 1280, "height": 800}
        ]
        for (let viewportIndex = 0; viewportIndex < viewports.length; viewportIndex++) {
            object.width = viewports[viewportIndex].width
            object.height = viewports[viewportIndex].height
            check(object.contentScrollControl && object.contentScrollControl.contentItem,
                  "gestão de diretórios deve usar ScrollView real")
            check(object.contentScrollControl.contentItem.contentWidth
                  <= object.contentScrollControl.availableWidth + 1,
                  "diretórios não podem produzir overflow horizontal")
            const card = object.cardsRepeaterControl.itemAt(0)
            check(card && card.actionRepeaterControl.count === 6,
                  "cada root deve manter seis ações isoladas")
            if (card) {
                object.setActionMessage(actions[2].id, "E-TEST: auditoria recusada")
                check(object.cardActionMessage(object.cards()[0])
                      === "E-TEST: auditoria recusada",
                      "erro deve permanecer junto ao card da ação")
                for (let actionIndex = 0;
                        actionIndex < card.actionRepeaterControl.count; actionIndex++) {
                    const button = card.actionRepeaterControl.itemAt(actionIndex)
                    check(button.height >= 48 && button.width >= 120,
                          "ação de root deve manter alvo legível e 48×48")
                }
                const last = card.actionRepeaterControl.itemAt(5)
                last.forceActiveFocus(Qt.TabFocusReason)
                object.revealFocusedItem(last)
                const bottom = last.mapToItem(
                    object.contentScrollControl.contentItem, 0, last.height).y
                check(bottom <= object.contentScrollControl.contentItem.contentY
                      + object.contentScrollControl.height + 1,
                      "última ação do root deve permanecer acima da borda inferior")
            }
        }
        object.destroy()
    }

    function testResponsiveProfiles() {
        const object = makePage({})
        if (!object)
            return
        object.width = 1208
        object.height = 650
        check(object.compactLayout, "Deck deve ativar o perfil compacto")
        check(!object.showAreaSidebar, "Deck deve substituir a sub-sidebar de áreas")
        check(!object.showContextPanel, "Deck não deve disputar largura com contexto lateral")
        check(object.compactPrimaryActionControl.visible,
              "ação primária compacta deve permanecer visível")
        check(object.minimumTouchTarget >= 48,
              "ação primária compacta deve manter alvo mínimo de 48 px")

        object.width = 1656
        object.height = 950
        check(!object.compactLayout, "Full HD deve preservar o perfil desktop")
        check(object.showAreaSidebar, "Full HD deve manter navegação de áreas")
        check(object.showContextPanel, "Full HD deve aproveitar o painel contextual")

        object.width = 2296
        object.height = 950
        check(object.ultrawideLayout, "21:9 deve ativar contenção ultrawide")
        check(object.contentMaxWidth === 1400,
              "conteúdo ultrawide deve limitar-se a 1400 px")
        object.destroy()
    }

    function testPublishedStateFixtures() {
        const states = ["ready", "empty", "degraded", "offline"]
        for (let index = 0; index < states.length; ++index) {
            const state = states[index]
            const object = makePage({
                "platforms": [{
                    "id": "switch", "name": "Nintendo Switch", "state": state,
                    "statusLabel": state,
                    "readiness": {"percent": state === "ready" ? 100 : 0,
                        "title": state, "blockers": []},
                    "emulators": [], "games": []
                }]
            })
            if (!object)
                continue
            check(object.selectedPlatform.state === state,
                  "fixture " + state + " deve permanecer distinta na UI")
            check(object.stateIcon(state).length > 0,
                  "fixture " + state + " deve ter ícone não dependente apenas de cor")
            object.destroy()
        }
    }

    Component {
        id: pageComponent
        Emulation {
            width: 1360
            height: 820
            backgroundColor: "#071019"
            sidebarColor: "#09131d"
            surfaceColor: "#0d1924"
            raisedColor: "#122131"
            borderColor: "#2a3a49"
            textColor: "#f2f6fb"
            mutedColor: "#9eabba"
            cyanColor: "#13bdf2"
            cyanDarkColor: "#0a5f85"
            greenColor: "#59d35d"
            amberColor: "#ff9f1a"
            redColor: "#ff6b73"
        }
    }

    Timer {
        interval: 100
        running: true
        onTriggered: {
            testHierarchy()
            testSafeFallback()
            testBackendArea()
            testGameLibraryJourney()
            testEmulatorMaintenanceListsEveryManagedEmulator()
            testLibraryRootManagementIsScrollableAndTouchSafe()
            testResponsiveProfiles()
            testPublishedStateFixtures()
            if (failures === 0)
                console.log("PASS: hierarquia, fallback seguro e contrato de áreas")
            Qt.exit(failures === 0 ? 0 : firstFailure)
        }
    }
}
