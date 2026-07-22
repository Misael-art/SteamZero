// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Window
import "../../src/steamzero/ui/qml"

Window {
    id: harness
    visible: false
    width: 1400
    height: 900
    property int failures: 0

    function check(condition, message) {
        if (condition)
            return
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
                "games": [{"id": "0100", "name": "Jogo de teste"}]
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
        object.scopeIndex = 4
        check(object.contextTitle() === "Modo dock", "escopo dock deve ser explícito")

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
                    {"id": "a", "path": "/roms/a.nsz", "name": "Mario", "titleId": "010000000000A000", "size": 10, "format": "nsz", "state": "ready", "statusLabel": "NSZ", "playAction": {"id": "game.launch:a", "label": "Jogar", "enabled": true}}
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
                    {"id": "eden", "name": "Eden", "state": "ready"},
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

    Component.onCompleted: {
        testHierarchy()
        testSafeFallback()
        testBackendArea()
        testGameLibraryJourney()
        testEmulatorMaintenanceListsEveryManagedEmulator()
        testResponsiveProfiles()
        if (failures === 0)
            console.log("PASS: hierarquia, fallback seguro e contrato de áreas")
        Qt.exit(failures === 0 ? 0 : 1)
    }
}
