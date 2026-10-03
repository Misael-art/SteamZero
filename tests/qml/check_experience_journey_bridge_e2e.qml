// SPDX-License-Identifier: GPL-3.0-or-later
// Criação, edição, preview e round-trip pela UI conectada à DesktopControlServer real.

import QtQuick
import QtQuick.Controls
import QtTest
import "../../src/steamzero/ui/qml"

Item {
    id: harness
    width: 1600
    height: 1200
    property var bridgeConfig: ({})
    property var contracts: ({byId: ({})})
    property var actionCalls: []
    property bool bridgeReady: false

    function readConfig() {
        const request = new XMLHttpRequest()
        request.open("GET", Qt.resolvedUrl("../../build/journey-studio-bridge-e2e.json"), false)
        request.send()
        if (request.status !== 0 && request.status !== 200)
            throw new Error("configuração da bridge de Jornada não foi lida")
        return JSON.parse(request.responseText)
    }

    function fetchContracts() {
        const request = new XMLHttpRequest()
        request.onreadystatechange = function() {
            if (request.readyState !== XMLHttpRequest.DONE)
                return
            if (request.status !== 200)
                return
            harness.contracts = JSON.parse(request.responseText)
            harness.bridgeReady = true
        }
        request.open("GET", bridgeConfig.apiUrl + "/contracts", true)
        request.setRequestHeader("X-SteamZero-Token", bridgeConfig.apiToken)
        request.send()
    }

    function requestAction(actionId, payload, success, failure) {
        harness.actionCalls = harness.actionCalls.concat([String(actionId)])
        const action = contracts.byId ? contracts.byId[actionId] : null
        if (!action || action.applicability !== "applicable" || action.enabled !== true
                || !action.endpoint || !action.method)
            return false
        const request = new XMLHttpRequest()
        request.onreadystatechange = function() {
            if (request.readyState !== XMLHttpRequest.DONE)
                return
            let value = ({})
            try {
                value = request.responseText ? JSON.parse(request.responseText) : ({})
            } catch (_error) {
                value = ({detail: "resposta da bridge não era JSON"})
            }
            if (request.status >= 200 && request.status < 300) {
                success(value)
            } else if (failure) {
                const error = value && value.error ? value.error : value
                failure(error && (error.detail || error.message)
                    ? String(error.detail || error.message) : "Ação recusada pela bridge")
            }
        }
        request.open(String(action.method).toUpperCase(), bridgeConfig.apiUrl + action.endpoint, true)
        request.setRequestHeader("X-SteamZero-Token", bridgeConfig.apiToken)
        request.setRequestHeader("Content-Type", "application/json")
        request.send(String(action.method).toUpperCase() === "GET"
            ? null : JSON.stringify(payload || ({})))
        return true
    }

    ExperienceJourneyPanel {
        id: journey
        objectName: "journeyBridgePanel"
        anchors.fill: parent
        visible: harness.bridgeReady
        compactLayout: false
        requestAction: harness.requestAction
    }

    TestCase {
        name: "ExperienceJourneyProductionBridge"
        when: windowShown

        function initTestCase() {
            harness.bridgeConfig = harness.readConfig()
            harness.fetchContracts()
            tryVerify(function() { return harness.bridgeReady }, 4000,
                      "contratos reais da DesktopControlServer não chegaram")
            tryVerify(function() {
                return journey.bridgeAvailable && journey.catalog.readModels.length > 0
            }, 5000, "o painel não carregou lista e read models pela bridge")
        }

        function find(root, name) {
            if (!root)
                return null
            if (root.objectName === name)
                return root
            const objects = root.childItems !== undefined ? root.childItems : root.children
            for (let i = 0; i < (objects || []).length; ++i) {
                const hit = find(objects[i], name)
                if (hit)
                    return hit
            }
            return null
        }

        function byName(name) {
            const result = find(journey, name)
            verify(result !== null, "controle QML ausente: " + name)
            return result
        }

        function reveal(item) {
            const scroll = byName("journeyInspectorScroll")
            const flickable = scroll.contentItem
            const point = item.mapToItem(flickable, 0, 0)
            if (point.y < 0)
                flickable.contentY = Math.max(0, flickable.contentY + point.y)
            else if (point.y + item.height > flickable.height)
                flickable.contentY = Math.min(flickable.contentHeight - flickable.height,
                    flickable.contentY + point.y + item.height - flickable.height)
            wait(40)
        }

        function isInInspector(item) {
            let current = item
            while (current) {
                if (current.objectName === "journeyInspectorScroll")
                    return true
                current = current.parent
            }
            return false
        }

        function click(item) {
            if (isInInspector(item))
                reveal(item)
            mouseClick(item)
        }

        function choose(combo, index) {
            combo.currentIndex = index
            combo.activated(index)
        }

        function modelIndex(model, id) {
            for (let i = 0; i < model.length; ++i) {
                if (String(model[i].id) === id)
                    return i
            }
            return -1
        }

        function menuIdNamed(name) {
            const menu = journey.menus.find(function(item) { return item.name === name })
            return menu ? String(menu.id) : ""
        }

        function renameSelected(name) {
            byName("journeyMenuName").text = name
            click(byName("journeyRenameMenu"))
            tryVerify(function() {
                return journey.currentMenu && journey.currentMenu.name === name && !journey.busy
            }, 4000, "a bridge não confirmou o renomear de " + name)
        }

        function addMenuNamed(name, readModelId) {
            const before = journey.menus.length
            click(byName("journeyAddMenu"))
            tryVerify(function() { return journey.menus.length === before + 1 && !journey.busy },
                      4000, "Adicionar menu não foi aplicado pela bridge")
            const sourcePicker = byName("journeyReadModelPicker")
            const sourceIndex = modelIndex(sourcePicker.model, readModelId)
            verify(sourceIndex >= 0, "read model não publicado: " + readModelId)
            choose(sourcePicker, sourceIndex)
            tryVerify(function() {
                return journey.currentMenu.source.readModelId === readModelId && !journey.busy
            }, 4000, "a fonte selecionada não foi persistida")
            renameSelected(name)
        }

        function addEqualsFilter(fieldId, value, operatorId) {
            const fieldPicker = byName("journeyFilterField")
            const fieldIndex = modelIndex(fieldPicker.model, fieldId)
            verify(fieldIndex >= 0, "campo público não publicado: " + fieldId)
            choose(fieldPicker, fieldIndex)
            const operatorPicker = byName("journeyFilterOperator")
            const operatorIndex = modelIndex(operatorPicker.model, operatorId || "equals")
            verify(operatorIndex >= 0, "operador ausente: " + (operatorId || "equals"))
            choose(operatorPicker, operatorIndex)
            byName("journeyFilterValue").text = value
            const before = journey.currentMenu.filters.length
            click(byName("journeyFilterAdd"))
            tryVerify(function() {
                return journey.currentMenu.filters.length === before + 1 && !journey.busy
            }, 4000, "o filtro público não foi aplicado")
        }

        function selectMenu(menuId) {
            click(byName("journeyMenu_" + menuId))
            compare(journey.currentMenu.id, menuId)
        }

        function addSelectConnection(targetId, sourceField, targetField) {
            journey.selectedTab = "routes"
            const targetPicker = byName("journeyRouteTargetMenu")
            const targetIndex = modelIndex(targetPicker.model, targetId)
            verify(targetIndex >= 0, "destino não publicado no inspetor: " + targetId)
            targetPicker.currentIndex = targetIndex
            if (sourceField && targetField) {
                const sourcePicker = byName("journeyBindingSourceField")
                const sourceIndex = modelIndex(sourcePicker.model, sourceField)
                const destinationPicker = byName("journeyBindingTargetField")
                const destinationIndex = modelIndex(destinationPicker.model, targetField)
                verify(sourceIndex >= 0 && destinationIndex >= 0,
                       "binding não está disponível nos campos publicados")
                sourcePicker.currentIndex = sourceIndex
                destinationPicker.currentIndex = destinationIndex
            }
            const before = journey.connections.length
            click(byName("journeyConnectionAdd"))
            tryVerify(function() {
                return journey.connections.length === before + 1 && !journey.busy
            }, 4000, "a conexão não foi aplicada pela bridge")
        }

        function test_create_three_metadata_paths_shared_menu_history_and_roundtrip() {
            verify(harness.contracts.byId["journey.studio.create"] !== undefined)
            const expectedName = "Jornada UI contra bridge real"
            const name = byName("journeyName")
            name.text = expectedName
            click(byName("journeyCreate"))
            tryVerify(function() {
                return journey.session && journey.journeyDocument.name === expectedName
                    && !journey.busy
            }, 4000, "Criar não chegou ao JourneyStudioService")

            renameSelected("Jogos")
            addMenuNamed("Plataformas", "library.platforms")
            const platformsId = String(journey.currentMenu.id)

            addMenuNamed("Por gênero", "library.games")
            const genreId = String(journey.currentMenu.id)
            addEqualsFilter("genre", "Platformer", "equals")

            addMenuNamed("Por ano", "library.games")
            const yearId = String(journey.currentMenu.id)
            addEqualsFilter("year", "1992", "greaterThanOrEqual")

            const gamesId = menuIdNamed("Jogos")
            verify(gamesId !== "")
            selectMenu(platformsId)
            addSelectConnection(gamesId, "id", "platformId")
            selectMenu(genreId)
            addSelectConnection(gamesId, "genre", "genre")
            selectMenu(yearId)
            addSelectConnection(gamesId, "year", "year")

            const shared = journey.connections.filter(function(item) {
                return item.from.kind === "menu" && item.to.kind === "menu"
                    && item.to.id === gamesId && item.event === "select"
            })
            compare(shared.length, 3, "os três percursos devem reutilizar o mesmo menu Jogos")
            compare(JSON.stringify(shared[0].bindings),
                    JSON.stringify([{sourceFieldId: "id", targetFieldId: "platformId"}]))

            selectMenu(genreId)
            journey.selectedTab = "menus"
            click(byName("journeyPreviewButton"))
            tryVerify(function() {
                return journey.previewResult && journey.previewResult.menuId === genreId
            }, 5000, "o preview da faceta de gênero não respondeu")
            compare(journey.previewResult.resultCount, 1)
            compare(journey.previewResult.rows[0].genre, "Platformer")
            tryVerify(function() { return !journey.busy }, 5000,
                      "a inspeção de cobertura do caminho por gênero não terminou")

            selectMenu(yearId)
            click(byName("journeyPreviewButton"))
            tryVerify(function() {
                return journey.previewResult && journey.previewResult.menuId === yearId
            }, 5000, "o preview da faceta de ano não respondeu")
            compare(journey.previewResult.resultCount, 1)
            compare(journey.previewResult.rows[0].year, 1992)
            tryVerify(function() { return !journey.busy }, 5000,
                      "a inspeção de cobertura do caminho por ano não terminou")

            selectMenu(genreId)
            journey.selectedTab = "menus"
            const themePicker = byName("journeyMenuThemePicker")
            const themeIndex = modelIndex(themePicker.model, "org.steamzero.asset-recipes-demo")
            verify(themeIndex >= 0, "o tema nativo de cena não chegou pelo catálogo real")
            choose(themePicker, themeIndex)
            compare(themePicker.displayText, "Theme Engine — asset único")
            compare(journey.selectedThemeId, "org.steamzero.asset-recipes-demo")
            const applyTheme = byName("journeyApplyMenuTheme")
            verify(applyTheme.enabled && applyTheme.visible && applyTheme.width > 0
                    && applyTheme.height >= 48,
                   "o CTA de tema não está disponível: enabled=" + applyTheme.enabled
                       + " visible=" + applyTheme.visible + " size="
                       + applyTheme.width + "x" + applyTheme.height)
            verify(applyTheme.x + applyTheme.width <= applyTheme.parent.width + 0.5,
                   "CTA Aplicar ao menu está fora do inspetor")
            const callsBeforeTheme = harness.actionCalls.length
            click(applyTheme)
            wait(100)
            if (harness.actionCalls.length === callsBeforeTheme) {
                applyTheme.forceActiveFocus()
                keyClick(Qt.Key_Space)
            }
            tryVerify(function() { return harness.actionCalls.length > callsBeforeTheme },
                      1500, "mouse/teclado não chegou ao CTA de tema")
            tryVerify(function() {
                return journey.currentMenu.appearance
                    && journey.currentMenu.appearance.themeId
                        === "org.steamzero.asset-recipes-demo"
                    && !journey.busy
            }, 4000, "a aparência do menu não foi salva no documento: busy="
                + journey.busy + " selectedTheme=" + journey.selectedThemeId
                + " notice=" + journey.notice + " current="
                + JSON.stringify(journey.currentMenu) + " actions="
                + JSON.stringify(harness.actionCalls.slice(-8)) + " rect="
                + JSON.stringify(applyTheme.mapToItem(harness, 0, 0)) + " size="
                + applyTheme.width + "x" + applyTheme.height + " inspectorY="
                + byName("journeyInspectorScroll").contentItem.contentY)

            const savedDocument = JSON.parse(JSON.stringify(journey.journeyDocument))
            const savedSessionId = String(journey.session.sessionId)
            verify(journey.session.history.canUndo === true,
                   "ações de edição não publicaram undo: " + JSON.stringify(journey.session.history))
            click(byName("journeyUndo"))
            tryVerify(function() { return !journey.busy && journey.session.history.canRedo },
                      4000, "Desfazer não atualizou o histórico: "
                          + JSON.stringify(journey.session.history) + " notice=" + journey.notice
                          + " actions=" + JSON.stringify(harness.actionCalls))
            click(byName("journeyRedo"))
            tryVerify(function() { return !journey.busy && journey.connections.length === 3 },
                      4000, "Refazer não restaurou as conexões")

            click(byName("journeySave"))
            tryVerify(function() {
                return !journey.busy && journey.session.dirty === false
            }, 5000, "Salvar não persistiu o documento")
            const savedId = String(journey.journeyDocument.id)
            const savedPicker = byName("journeyPicker")
            const savedIndex = modelIndex(savedPicker.model, savedId)
            verify(savedIndex >= 0, "a lista salva não foi atualizada")
            choose(savedPicker, savedIndex)
            tryVerify(function() {
                return !journey.busy && journey.session.sessionId !== savedSessionId
                    && journey.journeyDocument.id === savedId
            }, 5000, "Reabrir não criou uma nova sessão do documento salvo")
            compare(JSON.stringify(journey.journeyDocument.menus),
                    JSON.stringify(savedDocument.menus))
            compare(JSON.stringify(journey.journeyDocument.connections),
                    JSON.stringify(savedDocument.connections))
            compare(JSON.stringify(journey.journeyDocument.menus.find(function(item) {
                return item.id === genreId
            }).filters), JSON.stringify([{fieldId: "genre", operator: "equals",
                value: "Platformer"}]))

            selectMenu(genreId)
            click(byName("journeyPreviewButton"))
            tryVerify(function() {
                return journey.previewResult && journey.previewResult.menuId === genreId
                    && journey.themePreviewMode === "native" && !journey.busy
            }, 6000, "o Journey reaberto não chegou ao renderer nativo do Theme Engine")
            compare(journey.themePreviewThemeId, "org.steamzero.asset-recipes-demo")
            compare(journey.previewResult.resultCount, 1)
            const nativeEntries = journey.themePreviewObject.sceneLayoutPreview.layouts
                .previewTitles.entries
            compare(nativeEntries.length, 1)
            compare(nativeEntries[0].text, "Synthetic Platformer")
            verify(nativeEntries.every(function(entry) { return entry.text !== "Axiom Verge" }),
                "o renderer usou o fixture estático em vez dos dados filtrados da Jornada")

            journey.beginExport("file://" + harness.bridgeConfig.exportPath)
            tryVerify(function() {
                return journey.exportPlan !== null
                    && journey.exportConfirmDialogControl.visible
            }, 4000, "Exportar não preparou um plano de escrita confirmado")
            compare(JSON.stringify(journey.exportPlan.packageContents),
                    JSON.stringify(["experience.json"]))
            journey.exportConfirmDialogControl.accept()
            tryVerify(function() {
                return !journey.busy && journey.exportPlan === null
                    && journey.notice.indexOf("ZIP contém apenas experience.json") >= 0
            }, 5000, "a confirmação da exportação não concluiu o pacote")

            journey.selectedImportUrl = "file://" + harness.bridgeConfig.exportPath
            journey.importNameControl.text = "Cópia importada pela UI"
            journey.beginImport()
            tryVerify(function() {
                return !journey.busy && journey.journeyDocument.name === "Cópia importada pela UI"
                    && journey.importDependencies.length === 1
            }, 5000, "Importar cópia não carregou o pacote e suas dependências")
            compare(journey.importDependencies[0].state, "available-unpinned")
            verify(journey.notice.indexOf("versão do pacote não fixada") >= 0, journey.notice)
            verify(journey.notice.indexOf("1.0.0") >= 0, journey.notice)
            compare(JSON.stringify(journey.journeyDocument.menus),
                    JSON.stringify(savedDocument.menus))
            compare(JSON.stringify(journey.journeyDocument.connections),
                    JSON.stringify(savedDocument.connections))
            click(byName("journeySave"))
            tryVerify(function() { return !journey.busy && !journey.session.dirty },
                      5000, "a cópia importada não pôde ser salva como Jornada própria")
        }
    }

}
