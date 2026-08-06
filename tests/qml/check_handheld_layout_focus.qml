// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Controls
import QtQuick.Window
import "../../src/steamzero/ui/qml"

Window {
    id: harness
    visible: true
    width: 949
    height: 593

    property int failures: 0
    property int checks: 0
    property int firstFailure: 0
    property int mutations: 0
    property int viewportIndex: 0
    property int phase: 0
    property int scopeCursor: 0
    property int areaCursor: 0
    property var drawerInvoker: null
    readonly property var viewports: [
        {"width": 949, "height": 593},
        {"width": 1280, "height": 800}
    ]

    function check(condition, message) {
        checks += 1
        if (condition)
            return
        if (firstFailure === 0)
            firstFailure = checks
        failures += 1
        console.error("FAIL: " + message)
    }

    function isInteractive(item) {
        return item instanceof AbstractButton
            || item instanceof TextField
            || item instanceof TextArea
            || item instanceof Slider
    }

    function auditTargets(item, context) {
        if (!item || !item.visible)
            return
        if (item.enabled && isInteractive(item)) {
            check(item.width + 0.5 >= 48,
                  context + ": alvo interativo deve ter largura mínima de 48 px")
            check(item.height + 0.5 >= 48,
                  context + ": alvo interativo deve ter altura mínima de 48 px")
        }
        const children = item.children || []
        for (let index = 0; index < children.length; ++index)
            auditTargets(children[index], context)
    }

    function auditHorizontalBounds(item, viewport, context) {
        if (!item || !item.visible)
            return
        if (item.width > 0 && item.height > 0 && isInteractive(item)) {
            const point = item.mapToItem(viewport, 0, 0)
            check(point.x >= -0.5,
                  context + ": controle interativo não pode começar fora da viewport")
            check(point.x + item.width <= viewport.width + 0.5,
                  context + ": controle interativo não pode exceder a viewport")
        }
        const children = item.children || []
        for (let index = 0; index < children.length; ++index)
            auditHorizontalBounds(children[index], viewport, context)
    }

    function deepestInteractive(item, flickable, current) {
        if (!item || !item.visible)
            return current
        let result = current
        if (item.enabled && isInteractive(item)) {
            const point = item.mapToItem(flickable.contentItem, 0, 0)
            const bottom = point.y + item.height
            if (!result || bottom > result.bottom)
                result = {"item": item, "bottom": bottom}
        }
        const children = item.children || []
        for (let index = 0; index < children.length; ++index)
            result = deepestInteractive(children[index], flickable, result)
        return result
    }

    function auditScrollEnd(scroll, context) {
        check(scroll && scroll.contentItem, context + ": área deve publicar Flickable")
        if (!scroll || !scroll.contentItem)
            return
        const flickable = scroll.contentItem
        check(flickable.contentWidth <= scroll.availableWidth + 1,
              context + ": ScrollView não pode ter overflow horizontal")
        const last = deepestInteractive(flickable.contentItem, flickable, null)
        if (!last)
            return
        flickable.contentY = Math.max(
            0, flickable.contentHeight - flickable.height)
        const point = last.item.mapToItem(scroll, 0, 0)
        check(point.y + last.item.height <= scroll.height + 0.5,
              context + ": último controle deve subir integralmente acima do rodapé")
    }

    function auditEmulationSelectors() {
        check(emulationPage.scopeControlRepeater.count === 5,
              "Emulação deve publicar os cinco escopos")
        for (let index = 0; index < emulationPage.scopeControlRepeater.count; ++index) {
            const control = emulationPage.scopeControlRepeater.itemAt(index)
            check(control !== null, "escopo de Emulação deve ser alcançável")
            if (control) {
                check(control.width >= 48 && control.height >= 48,
                      "escopo de Emulação deve manter alvo 48×48")
            }
        }
        check(emulationPage.compactAreaControl.count === 11,
              "Emulação deve publicar todas as onze áreas")
        check(emulationPage.compactAreaControl.width >= 48
              && emulationPage.compactAreaControl.height >= 48,
              "seletor de área de Emulação deve manter alvo 48×48")
        check(emulationPage.platformControl.width >= 48
              && emulationPage.platformControl.height >= 48,
              "seletor de plataforma deve manter alvo 48×48")
    }

    function auditCurrentEmulationArea() {
        const context = "Emulação escopo " + scopeCursor + " área " + areaCursor
        check(emulationPage.scopeIndex === scopeCursor,
              context + ": escopo deve permanecer selecionado")
        check(emulationPage.areaIndex === areaCursor,
              context + ": área deve permanecer selecionada")
        auditTargets(emulationPage, context)
        auditHorizontalBounds(emulationPage, emulationPage, context)
        auditScrollEnd(emulationPage.libraryListControl, context)
    }

    function advanceEmulationArea() {
        areaCursor += 1
        if (areaCursor >= 11) {
            areaCursor = 0
            scopeCursor += 1
        }
        if (scopeCursor >= 5) {
            phase = 2
            emulationPage.scopeIndex = 2
            emulationPage.areaIndex = 0
            emulationPage.gameDetailsOpen = false
            return
        }
        emulationPage.scopeIndex = scopeCursor
        emulationPage.areaIndex = areaCursor
        emulationPage.gameDetailsOpen = false
    }

    function auditCompactGameLibrary() {
        check(emulationPage.compactGameRepeaterControl.count === 2,
              "biblioteca compacta deve renderizar cards por jogo")
        const card = emulationPage.compactGameRepeaterControl.itemAt(0)
        check(card !== null, "primeiro card compacto deve existir")
        if (!card)
            return
        check(card.width <= emulationPage.libraryListControl.availableWidth + 0.5,
              "card compacto não pode exigir rolagem horizontal")
        check(card.titleControl.visible && card.titleControl.text.length > 0,
              "card compacto deve manter nome do jogo")
        check(card.emulatorControl.visible,
              "card compacto deve manter emulador e requisitos visíveis")
        const titlePoint = card.titleControl.mapToItem(
            emulationPage.libraryListControl, 0, 0)
        check(titlePoint.y < emulationPage.libraryListControl.height,
              "metadados do primeiro jogo devem surgir antes do rodapé")
        check(card.adjustControl.width >= 48 && card.adjustControl.height >= 48,
              "Ajustes do card deve manter alvo 48×48")
        const search = emulationPage.gameSearchControl
        check(search instanceof TextField && !search.readOnly,
              "busca deve manter foco editável para o InputMethod do Qt")
        check(search.activeFocusOnTab && search.focusPolicy === Qt.StrongFocus,
              "busca deve aceitar foco por toque, Enter e navegação direcional")
        search.forceActiveFocus(Qt.TabFocusReason)
        search.text = "mario"
        Qt.inputMethod.hide()
        check(search.activeFocus && search.text === "mario",
              "fechar teclado virtual deve preservar texto e foco da busca")
        const filteredCard = emulationPage.compactGameRepeaterControl.itemAt(0)
        check(filteredCard !== null,
              "busca deve preservar o card correspondente")
        if (!filteredCard)
            return
        drawerInvoker = filteredCard.adjustControl
        drawerInvoker.forceActiveFocus(Qt.TabFocusReason)
        emulationPage.selectGame(emulationPage.games[0], drawerInvoker)
    }

    function auditGameDrawer() {
        check(emulationPage.gameDetailsControl.visible,
              "drawer de jogo compacto deve abrir sobre a biblioteca")
        check(emulationPage.gameDetailsCloseControl.activeFocus,
              "drawer deve mover foco inicial para Fechar")
        check(emulationPage.gameDetailsCloseControl.width >= 48
              && emulationPage.gameDetailsCloseControl.height >= 48,
              "Fechar do drawer deve manter alvo 48×48")
        check(emulationPage.motionDuration === 0,
              "movimento reduzido deve zerar animação do drawer")
        auditTargets(emulationPage.gameDetailsControl, "drawer de jogo")
        auditHorizontalBounds(
            emulationPage.gameDetailsControl,
            emulationPage.gameDetailsControl,
            "drawer de jogo")
        auditScrollEnd(emulationPage.gamePanelScrollControl, "drawer de jogo")
        emulationPage.closeGameDetails()
    }

    function auditDrawerFocusReturn() {
        check(!emulationPage.gameDetailsOpen,
              "fechar drawer deve restaurar a biblioteca")
        check(harness.activeFocusItem === drawerInvoker,
              "fechar drawer deve devolver foco ao Ajustes/item invocador")
        emulationPage.gameSearchControl.text = ""
    }

    function auditGameplaySelectors() {
        check(gameplayPage.scopeControlRepeater.count === 4,
              "Steam deve publicar quatro escopos")
        check(gameplayPage.areaControlRepeater.count === 4,
              "Steam deve publicar quatro áreas")
        for (let index = 0; index < 4; ++index) {
            const scope = gameplayPage.scopeControlRepeater.itemAt(index)
            const area = gameplayPage.areaControlRepeater.itemAt(index)
            check(scope && scope.width >= 48 && scope.height >= 48,
                  "escopo Steam deve manter alvo 48×48")
            check(area && area.width >= 48 && area.height >= 48,
                  "área Steam deve manter alvo 48×48")
        }
        check(gameplayPage.gamePickerControl.height >= 48,
              "seletor de jogo Steam deve manter alvo 48×48")
    }

    function auditCurrentGameplayArea() {
        const context = "Steam escopo " + scopeCursor + " área " + areaCursor
        check(gameplayPage.scopeIndex === scopeCursor,
              context + ": escopo deve permanecer selecionado")
        check(gameplayPage.workspaceIndex === areaCursor,
              context + ": área deve permanecer selecionada")
        auditTargets(gameplayPage, context)
        auditHorizontalBounds(gameplayPage, gameplayPage, context)
        auditScrollEnd(gameplayPage.gameplayScrollControl, context)
        if (areaCursor === 0) {
            check(gameplayPage.fpsControlRepeater.count === 3,
                  "Steam deve manter as três opções de FPS")
            for (let index = 0;
                 index < gameplayPage.fpsControlRepeater.count; ++index) {
                const control = gameplayPage.fpsControlRepeater.itemAt(index)
                check(control && control.height >= 48,
                      "opção de FPS deve ser visível e ter alvo 48×48")
            }
        } else if (areaCursor === 3) {
            check(gameplayPage.desktopModeControl.profileControlRepeater.count === 4,
                  "Modo Desktop deve manter os quatro perfis revisáveis")
        }
    }

    function advanceGameplayArea() {
        areaCursor += 1
        if (areaCursor >= 4) {
            areaCursor = 0
            scopeCursor += 1
        }
        if (scopeCursor >= 4) {
            phase = 8
            return
        }
        gameplayPage.scopeIndex = scopeCursor
        gameplayPage.workspaceIndex = areaCursor
    }

    function nextViewportOrFinish() {
        viewportIndex += 1
        if (viewportIndex >= viewports.length) {
            check(mutations === 0,
                  "harness geométrico não pode disparar ação mutável")
            Qt.exit(failures === 0 ? 0 : firstFailure)
            return
        }
        const viewport = viewports[viewportIndex]
        width = viewport.width
        height = viewport.height
        phase = 0
        scopeCursor = 0
        areaCursor = 0
        emulationPage.visible = true
        gameplayPage.visible = false
        emulationPage.scopeIndex = 0
        emulationPage.areaIndex = 0
        emulationPage.gameDetailsOpen = false
    }

    function runPhase() {
        if (phase === 0) {
            check(emulationPage.compactLayout,
                  "viewport handheld deve ativar Emulação compacta")
            check(emulationPage.reducedMotion
                  && emulationPage.motionDuration === 0,
                  "Emulação deve respeitar movimento reduzido")
            auditEmulationSelectors()
            scopeCursor = 0
            areaCursor = 0
            emulationPage.scopeIndex = 0
            emulationPage.areaIndex = 0
            phase = 1
            return
        }
        if (phase === 1) {
            auditCurrentEmulationArea()
            advanceEmulationArea()
            return
        }
        if (phase === 2) {
            auditCompactGameLibrary()
            phase = 3
            return
        }
        if (phase === 3) {
            auditGameDrawer()
            phase = 4
            return
        }
        if (phase === 4) {
            auditDrawerFocusReturn()
            emulationPage.visible = false
            gameplayPage.visible = true
            scopeCursor = 0
            areaCursor = 0
            gameplayPage.scopeIndex = 0
            gameplayPage.workspaceIndex = 0
            phase = 5
            return
        }
        if (phase === 5) {
            check(gameplayPage.compactLayout,
                  "viewport handheld deve ativar Steam compacta")
            check(gameplayPage.reducedMotion
                  && gameplayPage.motionDuration === 0,
                  "Steam deve respeitar movimento reduzido")
            auditGameplaySelectors()
            phase = 6
            return
        }
        if (phase === 6) {
            auditCurrentGameplayArea()
            advanceGameplayArea()
            return
        }
        if (phase === 8)
            nextViewportOrFinish()
    }

    Emulation {
        id: emulationPage
        anchors.fill: parent
        visible: true
        reducedMotion: true
        globalManagementActive: false
        emulation: ({
            "platforms": [{
                "id": "switch",
                "name": "Nintendo Switch",
                "iconKey": "switch",
                "state": "ready",
                "statusLabel": "Pronto",
                "selectedScope": "global",
                "selectedArea": "overview",
                "readiness": {
                    "percent": 75,
                    "title": "Atenção publicada",
                    "detail": "Dados sintéticos de layout",
                    "blockers": ["Aviso sintético"]
                },
                "emulators": [{
                    "id": "eden",
                    "name": "Eden",
                    "state": "ready",
                    "statusLabel": "Pronto",
                    "health": {"reason": "Sem ação necessária"},
                    "actions": []
                }],
                "games": [{
                    "id": "mario",
                    "path": "/tmp/steamzero-qa/mario.nsp",
                    "name": "Mario de teste",
                    "titleId": "010000000000A000",
                    "size": 1073741824,
                    "format": "nsp",
                    "state": "ready",
                    "statusLabel": "Pronto",
                    "emulatorId": "eden",
                    "region": "US",
                    "requiresFirmware": {"required": "18.0.0"},
                    "steamSelected": false,
                    "steamPublished": false,
                    "playAction": {
                        "id": "synthetic.play",
                        "label": "Jogar",
                        "enabled": true
                    }
                }, {
                    "id": "zelda",
                    "path": "/tmp/steamzero-qa/zelda.nsz",
                    "name": "Zelda de teste",
                    "titleId": "010000000000B000",
                    "size": 2147483648,
                    "format": "nsz",
                    "state": "degraded",
                    "statusLabel": "Revisar",
                    "emulatorId": "eden",
                    "steamSelected": true,
                    "steamPublished": true
                }],
                "runtimeProfiles": {
                    "activeScope": "handheld",
                    "observedScope": "handheld",
                    "autoTransition": {
                        "supported": false,
                        "reason": "Transição sintética indisponível"
                    },
                    "handheld": {
                        "resolution": {"width": 1280, "height": 800},
                        "controllers": {"activePlayers": 1, "maximumPlayers": 4}
                    },
                    "dock": {
                        "resolution": {"width": 1920, "height": 1080},
                        "controllers": {"activePlayers": 2, "maximumPlayers": 4}
                    }
                }
            }]
        })
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
        onActionRequested: harness.mutations += 1
        onComponentActionRequested: harness.mutations += 1
    }

    SteamGameplay {
        id: gameplayPage
        anchors.fill: parent
        visible: false
        reducedMotion: true
        gameplay: ({
            "games": [{
                "id": "synthetic-game",
                "name": "Jogo Steam sintético",
                "coverUrl": ""
            }],
            "environment": [{
                "id": "steam",
                "name": "Steam",
                "state": "ready",
                "statusLabel": "Pronto",
                "detail": "Fixture sintética",
                "owner": "Steam"
            }, {
                "id": "gamescope",
                "name": "Gamescope",
                "state": "ready",
                "statusLabel": "Pronto",
                "detail": "Fixture sintética",
                "owner": "Sistema"
            }, {
                "id": "gamemode",
                "name": "GameMode",
                "state": "ready",
                "statusLabel": "Pronto",
                "detail": "Fixture sintética",
                "owner": "Sistema"
            }],
            "readiness": {"percent": 100, "title": "Pronto"},
            "hardware": {
                "tdpMin": 3,
                "tdpMax": 15,
                "gpuMin": 400,
                "gpuMax": 1600,
                "refreshHz": 60,
                "withinSafeLimits": true
            },
            "currentProfile": {
                "gameId": "synthetic-game",
                "scope": "game",
                "profile": "balanced",
                "fps": 40
            },
            "maintenance": {
                "totalBytes": 1024,
                "categories": [{
                    "id": "shader-cache",
                    "sizeBytes": 1024
                }],
                "excluded": []
            },
            "media": {"accounts": [], "steamRunning": false},
            "sessionManager": {
                "state": "ready",
                "statusLabel": "Pronto",
                "directBoot": {"state": "available", "configured": false}
            }
        })
        desktopStatus: ({
            "truthState": "ready",
            "context": {
                "capabilities": ["steam-keyboard"],
                "conflicts": [],
                "displays": [{
                    "name": "eDP-1",
                    "internal": true,
                    "width": 1280,
                    "height": 800,
                    "refreshHz": 60
                }]
            },
            "dashboard": {
                "inputMethod": {
                    "state": "available",
                    "keyboardLayout": "br",
                    "detail": "Fixture sintética"
                }
            }
        })
        backgroundColor: "#071019"
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
        onPlanRequested: harness.mutations += 1
        onApplyRequested: harness.mutations += 1
        onSteamInputRequested: harness.mutations += 1
        onMaintenancePlanRequested: harness.mutations += 1
        onMaintenanceApplyRequested: harness.mutations += 1
        onMediaPlanRequested: harness.mutations += 1
        onMediaApplyRequested: harness.mutations += 1
    }

    Timer {
        interval: 20
        repeat: true
        running: true
        onTriggered: harness.runPhase()
    }
}
