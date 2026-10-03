// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts

Rectangle {
    id: panel

    property var requestAction: function(_id, _payload, _cb, _ecb) { return false }
    property color backgroundColor: "#071019"
    property color surfaceColor: "#0d1924"
    property color raisedColor: "#122131"
    property color borderColor: "#2a3a49"
    property color textColor: "#f2f6fb"
    property color mutedColor: "#9eabba"
    property color accentColor: "#13bdf2"
    property color amberColor: "#ffbf47"
    property color errorColor: "#ff6b73"
    property real visualScale: 1.0
    property bool compactLayout: false
    property bool busy: false
    property bool bridgeAvailable: false
    property string notice: ""
    property bool noticeIsError: false
    property int requestGeneration: 0
    property var journeyList: []
    property var catalog: ({readModels: [], themes: []})
    property var session: null
    property string selectedMenuId: ""
    property string selectedTab: "menus"
    property var previewResult: null
    property var coverageResult: null
    property var themePreviewObject: null
    property var themePreviewManifest: null
    property string themePreviewThemeId: ""
    property string themePreviewMode: ""
    property string themePreviewError: ""
    property bool themePreviewLoading: false
    property int themePreviewGeneration: 0
    property var importDependencies: []
    property string filterField: ""
    property string filterOperator: "equals"
    property string filterValue: ""
    property string selectedThemeId: ""
    property string selectedImportUrl: ""
    property string routeSourceKind: "menu"
    property string routeEvent: "select"
    property var exportPlan: null
    property string organizationParentId: ""
    property string pendingDeleteMenuId: ""
    property string pendingReplacementMenuId: ""
    property string compactPane: "tree"
    signal closeRequested()
    property alias importControl: importDialog
    property alias importNameControl: importNameField
    property alias deleteMenuDialogControl: deleteMenuDialog
    property alias deleteImpactControl: deleteImpactLabel
    property alias replacementMenuControl: replacementMenuPicker
    property alias deleteMenuConfirmControl: deleteMenuConfirmButton
    property alias exportConfirmDialogControl: exportConfirmDialog
    property bool componentReady: false
    property bool refreshStartedWhileVisible: false
    readonly property int minimumInteractiveTarget: 48
    readonly property var journeyDocument: session && session.document
        ? session.document : ({})
    readonly property var menus: journeyDocument.menus || []
    readonly property var connections: journeyDocument.connections || []
    readonly property var currentMenu: {
        for (let i = 0; i < menus.length; ++i) {
            if (menus[i].id === selectedMenuId)
                return menus[i]
        }
        return menus.length ? menus[0] : null
    }
    readonly property var currentFields: {
        const models = catalog.readModels || []
        const modelId = currentMenu && currentMenu.source
            ? String(currentMenu.source.readModelId || "") : ""
        for (let i = 0; i < models.length; ++i) {
            if (String(models[i].id) === modelId)
                return models[i].fields || []
        }
        return []
    }
    readonly property var routeTargetFields: {
        const target = routeTargetPicker.currentIndex >= 0
            ? panel.menus[routeTargetPicker.currentIndex] : null
        const models = catalog.readModels || []
        const modelId = target && target.source ? String(target.source.readModelId || "") : ""
        for (let i = 0; i < models.length; ++i) {
            if (String(models[i].id) === modelId)
                return models[i].fields || []
        }
        return []
    }
    readonly property string currentThemeId: {
        if (currentMenu && currentMenu.appearance
                && currentMenu.appearance.mode === "custom")
            return String(currentMenu.appearance.themeId || "")
        return "org.steamzero.default"
    }
    readonly property var sessionStages: [
        {id: "entryFade", label: qsTr("Fade de entrada")},
        {id: "gameplay", label: qsTr("Jogo")},
        {id: "pause", label: qsTr("Pausa")},
        {id: "saves", label: qsTr("Saves")},
        {id: "bezel", label: qsTr("Bezel")},
        {id: "osd", label: qsTr("Avisos na tela")},
        {id: "exitFade", label: qsTr("Fade de saída")},
        {id: "loading", label: qsTr("Carregando")},
        {id: "empty", label: qsTr("Sem resultados")},
        {id: "error", label: qsTr("Erro")},
        {id: "offline", label: qsTr("Offline")}
    ]

    color: panel.backgroundColor

    function selectedJourneyId() {
        const item = journeyPicker.currentIndex >= 0
            ? journeyList[journeyPicker.currentIndex] : null
        return item ? String(item.id || "") : ""
    }

    function publicFieldName(field) {
        return String(field && (field.name || field.label) || field && field.id
            || qsTr("Campo sem nome"))
    }

    function applySnapshot(value) {
        const snapshot = value && value.snapshot ? value.snapshot : value
        if (!snapshot || !snapshot.document)
            return false
        const changedSession = !panel.session
            || panel.session.sessionId !== snapshot.sessionId
            || panel.session.generation !== snapshot.generation
        panel.session = snapshot
        if (changedSession)
            panel.clearPreview()
        if (!menus.some(function(item) { return item.id === panel.selectedMenuId }))
            panel.selectedMenuId = snapshot.document.entryMenuId
        panel.notice = ""
        panel.noticeIsError = false
        return true
    }

    function invoke(actionId, payload, onSuccess, onFailure) {
        panel.busy = true
        const generation = ++panel.requestGeneration
        const dispatched = panel.requestAction(actionId, payload || {}, function(result) {
            if (generation !== panel.requestGeneration)
                return
            panel.busy = false
            if (onSuccess)
                onSuccess(result || ({}))
        }, function(error) {
            if (generation !== panel.requestGeneration)
                return
            panel.busy = false
            if (actionId === "journey.studio.list"
                    || actionId === "journey.studio.catalog")
                panel.bridgeAvailable = false
            panel.notice = typeof error === "string" ? error
                : (error && error.detail ? String(error.detail) : qsTr("A operação falhou"))
            panel.noticeIsError = true
            if (onFailure)
                onFailure(error)
        })
        if (dispatched === false) {
            panel.busy = false
            panel.bridgeAvailable = false
            panel.notice = qsTr("As ações de Jornada não estão disponíveis nesta sessão. O rascunho atual foi preservado; volte ao Studio ou tente atualizar.")
            panel.noticeIsError = true
        }
        return dispatched !== false
    }

    function refresh() {
        panel.notice = ""
        invoke("journey.studio.list", {}, function(result) {
            panel.bridgeAvailable = true
            panel.journeyList = result.journeys || []
            invoke("journey.studio.catalog", {}, function(catalogResult) {
                panel.catalog = catalogResult || ({readModels: [], themes: []})
            })
        })
    }

    function createJourney() {
        invoke("journey.studio.create", {name: journeyNameField.text || qsTr("Minha jornada")},
            function(result) {
                panel.applySnapshot(result)
                journeyNameField.text = ""
                panel.refreshListAfterSave()
            })
    }

    function refreshListAfterSave() {
        invoke("journey.studio.list", {}, function(result) {
            panel.journeyList = result.journeys || []
            const selected = panel.journeyDocument.id
            for (let i = 0; i < journeyList.length; ++i) {
                if (journeyList[i].id === selected) {
                    journeyPicker.currentIndex = i
                    break
                }
            }
        })
    }

    function loadJourney(journeyId) {
        if (!journeyId)
            return
        ++panel.requestGeneration
        panel.clearPreview()
        panel.invoke("journey.studio.load", {journeyId: journeyId}, function(result) {
            panel.applySnapshot(result)
        })
    }

    function transact(operation, payload, onSuccess) {
        if (!session || !session.sessionId || busy)
            return
        const body = Object.assign({}, payload || {}, {
            sessionId: session.sessionId,
            expectedGeneration: session.generation
        })
        invoke("journey.studio.transact", {operation: operation, payload: body}, function(result) {
            panel.applySnapshot(result)
            if (onSuccess)
                onSuccess(result)
        })
    }

    function saveJourney() {
        if (!session || !journeyDocument.id || busy)
            return
        invoke("journey.studio.save", {
            sessionId: session.sessionId,
            overwrite: session.isNew === false
        }, function(result) {
            panel.applySnapshot(result.snapshot || result)
            panel.session.isNew = false
            panel.refreshListAfterSave()
            panel.notice = qsTr("Jornada salva. Temas referenciados continuam como dependências separadas.")
        })
    }

    function closeJourney() {
        ++panel.requestGeneration
        panel.clearPreview()
        panel.busy = false
        panel.closeRequested()
    }

    function historyAction(actionId) {
        if (!session || busy)
            return
        invoke(actionId, {sessionId: session.sessionId}, function(result) {
            panel.applySnapshot(result)
        })
    }

    function clearPreview() {
        ++panel.themePreviewGeneration
        panel.previewResult = null
        panel.coverageResult = null
        panel.themePreviewObject = null
        panel.themePreviewManifest = null
        panel.themePreviewThemeId = ""
        panel.themePreviewMode = ""
        panel.themePreviewError = ""
        panel.themePreviewLoading = false
    }

    function previewViewId() {
        if (!currentMenu || !currentMenu.source)
            return "gamelist"
        const readModelId = String(currentMenu.source.readModelId || "")
        return readModelId.endsWith(".platforms") || readModelId === "library.platforms"
            ? "system" : "gamelist"
    }

    function journeyRuntimeModel() {
        const rows = previewResult && Array.isArray(previewResult.rows)
            ? previewResult.rows.slice(0, 64).map(function(row) {
                return Object.assign({}, row)
            }) : []
        const selected = rows.length > 0 ? rows[0] : ({})
        return {
            items: rows,
            selectedIndex: 0,
            selected: selected,
            system: {id: "journey", name: currentMenu ? String(currentMenu.name) : "Jornada"},
            status: {label: previewResult && previewResult.resultState
                ? String(previewResult.resultState) : "preview", state: "preview"},
            actions: [qsTr("Selecionar"), qsTr("Detalhes"), qsTr("Jogar")]
        }
    }

    function preview() {
        if (!session || !currentMenu || busy)
            return
        const menuId = String(currentMenu.id)
        const generation = ++panel.themePreviewGeneration
        panel.themePreviewLoading = true
        panel.themePreviewError = ""
        invoke("journey.studio.engine-preview", {
            sessionId: session.sessionId,
            menuId: menuId,
            expectedGeneration: session.generation
        }, function(result) {
            if (generation !== panel.themePreviewGeneration)
                return
            const query = result && result.query ? result.query : null
            const preview = result && result.preview ? result.preview : null
            const manifest = result && result.manifest ? result.manifest : ({})
            const declared = result && result.declared ? result.declared : ({})
            const themeId = result && result.themeId
                ? String(result.themeId) : panel.currentThemeId
            if (!query || !preview) {
                panel.themePreviewLoading = false
                panel.themePreviewError = qsTr("A Jornada ou o Theme Engine não devolveu a composição solicitada.")
                return
            }
            panel.previewResult = query
            panel.coverageResult = result.coverage || null
            const diagnostics = []
            if (query.diagnosticMessage)
                diagnostics.push(String(query.diagnosticMessage))
            if (result.themeResolutionDiagnostic)
                diagnostics.push(String(result.themeResolutionDiagnostic))
            panel.notice = diagnostics.join(" · ")
            panel.noticeIsError = query.resultState === "invalid-filter"
                || query.resultState === "source-unavailable"
                || query.resultState === "budget-exceeded"
                || result.themeResolutionState === "missing-reference"
            panel.themePreviewObject = preview
            panel.themePreviewManifest = manifest
            panel.themePreviewThemeId = themeId
            const nativeLayouts = declared.sceneLayouts && declared.sceneLayouts.layouts
                ? declared.sceneLayouts.layouts : ({})
            const assets = manifest.assets || ({})
            const hasEsdeScene = Object.keys(assets).some(function(name) {
                return String(name).toLowerCase().endsWith(".xml")
            })
            panel.themePreviewMode = Object.keys(nativeLayouts).length > 0
                ? "native" : (hasEsdeScene ? "esde" : "identity")
            panel.themePreviewLoading = false
            panel.inspectCoverage()
        }, function(error) {
            if (generation !== panel.themePreviewGeneration)
                return
            panel.themePreviewLoading = false
            panel.themePreviewError = typeof error === "string" ? error
                : (error && error.detail ? String(error.detail)
                    : qsTr("Não foi possível consultar os dados públicos deste menu."))
        })
    }

    function setEntryMenu() {
        if (!currentMenu)
            return
        transact("set-entry-menu", {menuId: currentMenu.id})
    }

    function clearMenuFilters() {
        if (!currentMenu || !currentMenu.filters || currentMenu.filters.length === 0)
            return
        transact("set-filters", {menuId: currentMenu.id, values: []})
    }

    function inspectCoverage(onSuccess, onFailure) {
        if (!session || busy)
            return
        invoke("journey.studio.coverage", {
            sessionId: session.sessionId,
            usedStages: usedCoverageStages()
        }, function(result) {
            panel.coverageResult = result
            if (onSuccess)
                onSuccess(result)
        }, onFailure)
    }

    function selectMenu(menuId) {
        const nextMenuId = String(menuId || "")
        if (nextMenuId !== panel.selectedMenuId)
            panel.clearPreview()
        panel.selectedMenuId = nextMenuId
        if (panel.compactLayout)
            panel.compactPane = "inspector"
    }

    function addMenu() {
        if (!catalog.readModels || catalog.readModels.length === 0) {
            panel.notice = qsTr("Nenhum read model público foi publicado para criar um menu.")
            panel.noticeIsError = true
            return
        }
        const menuId = "menu-" + String(Date.now()).slice(-8)
        const selected = catalog.readModels[0]
        transact("add-menu", {
            menu: {
                id: menuId,
                name: qsTr("Novo menu"),
                source: {readModelId: String(selected.id)},
                filters: [],
                sort: [],
                groupBy: []
            },
            parentId: panel.organizationParentId || null
        }, function() {
            panel.selectedMenuId = menuId
        })
    }

    function duplicateSelectedMenu() {
        if (!currentMenu)
            return
        const sourceNode = (journeyDocument.organization || []).find(function(node) {
            return node.kind === "menu" && node.menuId === currentMenu.id
        })
        const copyId = "menu-copy-" + String(Date.now()).slice(-8)
        transact("duplicate-menu", {
            menuId: currentMenu.id,
            newId: copyId,
            name: currentMenu.name + qsTr(" (cópia)"),
            parentId: sourceNode ? sourceNode.parentId : null
        }, function() {
            panel.selectedMenuId = copyId
        })
    }

    function organizationDepth(node) {
        const nodes = journeyDocument.organization || []
        let parentId = node.parentId
        let depth = 0
        const seen = {}
        while (parentId !== null && parentId !== undefined && depth < nodes.length) {
            const key = String(parentId)
            if (seen[key])
                break
            seen[key] = true
            const parent = nodes.find(function(candidate) { return candidate.id === key })
            if (!parent)
                break
            parentId = parent.parentId
            depth += 1
        }
        return depth
    }

    function menuDisplayName(menuId) {
        for (let i = 0; i < menus.length; ++i) {
            if (menus[i].id === menuId)
                return String(menus[i].name)
        }
        for (let i = 0; i < sessionStages.length; ++i) {
            if (sessionStages[i].id === menuId)
                return String(sessionStages[i].label)
        }
        return String(menuId || qsTr("Origem"))
    }

    function endpointLabel(endpoint) {
        if (!endpoint)
            return qsTr("sem destino")
        if (endpoint.kind === "history")
            return qsTr("contexto de origem")
        if (endpoint.kind === "stage")
            return menuDisplayName(endpoint.id)
        if (endpoint.kind === "menu")
            return menuDisplayName(endpoint.id)
        return String(endpoint.id || qsTr("desconhecido"))
    }

    function menuHasReferences(menuId) {
        if (!menuId)
            return false
        if (journeyDocument.entryMenuId === menuId)
            return true
        if (connections.some(function(connection) {
                return [connection.from, connection.to].some(function(endpoint) {
                    return endpoint.kind === "menu" && endpoint.id === menuId
                })
            }))
            return true
        const organization = journeyDocument.organization || []
        const nodeIds = organization.filter(function(node) {
            return node.kind === "menu" && node.menuId === menuId
        }).map(function(node) { return String(node.id) })
        return organization.some(function(node) {
            return node.parentId !== null && node.parentId !== undefined
                && nodeIds.indexOf(String(node.parentId)) >= 0
        })
    }

    function menuDeleteImpact(menuId) {
        const affected = connections.filter(function(connection) {
            return [connection.from, connection.to].some(function(endpoint) {
                return endpoint.kind === "menu" && endpoint.id === menuId
            })
        }).map(function(connection) {
            return String(connection.label || connection.id) + " · "
                + endpointLabel(connection.from) + " → " + endpointLabel(connection.to)
        })
        if (journeyDocument.entryMenuId === menuId)
            affected.unshift(qsTr("Menu de entrada da jornada"))
        const organization = journeyDocument.organization || []
        const nodeIds = organization.filter(function(node) {
            return node.kind === "menu" && node.menuId === menuId
        }).map(function(node) { return String(node.id) })
        organization.forEach(function(node) {
            if (node.parentId !== null && node.parentId !== undefined
                    && nodeIds.indexOf(String(node.parentId)) >= 0)
                affected.push(qsTr("Menu filho: %1").arg(menuDisplayName(node.menuId)))
        })
        return affected
    }

    function beginRemoveSelectedMenu() {
        if (!currentMenu)
            return
        panel.pendingDeleteMenuId = String(currentMenu.id)
        panel.pendingReplacementMenuId = ""
        deleteMenuDialog.open()
    }

    function confirmRemoveSelectedMenu() {
        const menuId = panel.pendingDeleteMenuId
        const referenced = panel.menuHasReferences(menuId)
        const replacement = panel.pendingReplacementMenuId
            ? menus.find(function(menu) { return menu.id === panel.pendingReplacementMenuId }) : null
        if (referenced && !replacement) {
            panel.notice = qsTr("Escolha um menu de substituição para conservar as conexões e a entrada.")
            panel.noticeIsError = true
            return false
        }
        const payload = {menuId: menuId}
        if (replacement)
            payload.replacementMenuId = String(replacement.id)
        const nextMenuId = replacement ? String(replacement.id)
            : (menus.find(function(menu) { return menu.id !== menuId }) || {}).id || ""
        panel.transact("remove-menu", payload, function() {
            panel.selectedMenuId = nextMenuId
            deleteMenuDialog.close()
            panel.pendingDeleteMenuId = ""
            panel.pendingReplacementMenuId = ""
        })
        return true
    }

    function moveSelectedMenu(delta) {
        if (!currentMenu)
            return
        const order = menus.map(function(menu) { return menu.id })
        const index = order.indexOf(currentMenu.id)
        const destination = Math.max(0, Math.min(order.length - 1, index + delta))
        if (index < 0 || destination === index)
            return
        const moved = order.splice(index, 1)[0]
        order.splice(destination, 0, moved)
        transact("reorder-menus", {menuIds: order})
    }

    function addConnection() {
        if (menus.length < 1)
            return
        const eventDefinition = eventPicker.currentIndex >= 0
            ? eventPicker.model[eventPicker.currentIndex] : null
        if (!eventDefinition)
            return
        const event = String(eventDefinition.id)
        const source = panel.routeSourceKind === "stage"
            ? {kind: "stage", id: String(routeStagePicker.model[routeStagePicker.currentIndex].id)}
            : {kind: "menu", id: String(currentMenu ? currentMenu.id : menus[0].id)}
        let target
        let action = eventDefinition.action
        if (event === "select") {
            const targetMenu = routeTargetPicker.currentIndex >= 0
                ? menus[routeTargetPicker.currentIndex] : null
            if (!targetMenu || (source.kind === "menu" && targetMenu.id === source.id))
                return
            target = {kind: "menu", id: targetMenu.id}
        } else if (event === "back") {
            target = {kind: "history"}
        } else {
            const stageTargets = {
                play: "entryFade", pause: "pause", resume: "gameplay",
                "open-saves": "saves", save: "saves", load: "saves",
                exit: "exitFade", retry: "loading"
            }
            target = {kind: "stage", id: stageTargets[event]}
        }
        const connectionId = "route-" + String(Date.now()).slice(-8)
        const bindings = []
        if (event === "select" && source.kind === "menu"
                && bindingSourcePicker.currentIndex >= 0
                && bindingTargetPicker.currentIndex >= 0) {
            bindings.push({
                sourceFieldId: String(currentFields[bindingSourcePicker.currentIndex].id),
                targetFieldId: String(routeTargetFields[bindingTargetPicker.currentIndex].id)
            })
        }
        transact("add-connection", {
            connection: {
                id: connectionId,
                from: source,
                event: event,
                when: String(whenPicker.currentValue),
                action: action,
                to: target,
                label: event === "select"
                    ? qsTr("Selecionar → %1").arg(target.id)
                    : eventDefinition.name,
                bindings: bindings
            }
        })
    }

    function addFilter() {
        if (!currentMenu || !filterField)
            return
        const field = currentFields.find(function(item) { return item.id === filterField })
        if (!field) {
            panel.notice = qsTr("Escolha um campo publicado pela fonte deste menu.")
            panel.noticeIsError = true
            return
        }
        function parseValue(raw) {
            const text = String(raw).trim()
            if (field.type === "integer") {
                if (!/^[+-]?\d+$/.test(text) || !Number.isSafeInteger(Number(text)))
                    return {ok: false}
                return {ok: true, value: Number(text)}
            }
            if (field.type === "number") {
                const number = Number(text)
                return Number.isFinite(number) ? {ok: true, value: number} : {ok: false}
            }
            if (field.type === "boolean") {
                if (text.toLowerCase() === "true")
                    return {ok: true, value: true}
                if (text.toLowerCase() === "false")
                    return {ok: true, value: false}
                return {ok: false}
            }
            return {ok: true, value: text}
        }
        let value = filterValueField.text
        if (filterOperator === "oneOf") {
            const rawParts = String(value).split(",").map(function(item) { return item.trim() })
                .filter(function(item) { return item !== "" })
            if (rawParts.length === 0) {
                panel.notice = qsTr("oneOf exige pelo menos um valor.")
                panel.noticeIsError = true
                return
            }
            const parsedParts = rawParts.map(parseValue)
            if (parsedParts.some(function(item) { return !item.ok })) {
                panel.notice = qsTr("Os valores precisam corresponder ao tipo publicado %1.")
                    .arg(field.type)
                panel.noticeIsError = true
                return
            }
            value = parsedParts.map(function(item) { return item.value })
        } else if (filterOperator === "greaterThanOrEqual"
                || filterOperator === "lessThanOrEqual") {
            if (field.type !== "integer" && field.type !== "number" && field.type !== "any") {
                panel.notice = qsTr("Este operador exige um campo numérico publicado.")
                panel.noticeIsError = true
                return
            }
            if (String(value).trim() === "") {
                panel.notice = qsTr("Informe um valor numérico; vazio não equivale a zero.")
                panel.noticeIsError = true
                return
            }
            const parsedNumber = parseValue(value)
            if (!parsedNumber.ok) {
                panel.notice = qsTr("Informe um número válido para comparar.")
                panel.noticeIsError = true
                return
            }
            value = parsedNumber.value
        } else if (filterOperator === "equals") {
            const parsedEqual = parseValue(value)
            if (!parsedEqual.ok) {
                panel.notice = qsTr("Informe um valor compatível com o tipo publicado %1.")
                    .arg(field.type)
                panel.noticeIsError = true
                return
            }
            value = parsedEqual.value
        } else if (filterOperator === "contains"
                && field.type !== "string" && field.type !== "string[]" && field.type !== "any") {
            panel.notice = qsTr("‘Contém’ exige texto ou uma lista pública de textos.")
            panel.noticeIsError = true
            return
        }
        const filters = (currentMenu.filters || []).slice()
        const filter = {fieldId: filterField, operator: filterOperator}
        if (filterOperator !== "isKnown" && filterOperator !== "isUnknown")
            filter.value = value
        filters.push(filter)
        transact("set-filters", {menuId: currentMenu.id, values: filters})
        filterValueField.text = ""
    }

    function setMenuAppearance() {
        if (!currentMenu)
            return
        if (!selectedThemeId) {
            panel.notice = qsTr("Escolha um tema publicado antes de atribuí-lo ao menu.")
            panel.noticeIsError = true
            return
        }
        const appearance = {mode: "custom", themeId: selectedThemeId}
        transact("set-menu-appearance", {menuId: currentMenu.id, appearance: appearance})
    }

    function setStageAppearance(stageId) {
        const appearance = selectedThemeId
            ? {mode: "custom", themeId: selectedThemeId} : {mode: "inherit-aura"}
        transact("set-stage-appearance", {stageId: stageId, appearance: appearance})
    }

    function localPath(url) {
        const value = String(url || "")
        return value.startsWith("file://")
            ? decodeURIComponent(value.replace(/^file:\/\/(?:localhost)?/, "")) : ""
    }

    function dependencyDescription(item) {
        const themeId = String(item && item.themeId || qsTr("tema sem ID"))
        const state = String(item && item.state || "unknown")
        if (state === "missing")
            return themeId + " (tema ausente; etapa usa AURA até instalar ou ajustar a referência)"
        if (state === "available-unpinned")
            return themeId + qsTr(" (versão do pacote não fixada; instalada: %1)")
                .arg(item.installedVersion || qsTr("desconhecida"))
        if (item && item.version)
            return themeId + " (" + item.version + "; " + state + ")"
        return themeId + " (dependência: " + state + ")"
    }

    function beginImport() {
        if (!selectedImportUrl) {
            importFileDialog.open()
            return
        }
        invoke("journey.studio.import", {
            source: panel.localPath(selectedImportUrl),
            copyName: importNameField.text || qsTr("Cópia da jornada")
        }, function(result) {
            panel.applySnapshot(result)
            panel.importDependencies = result.dependencies || []
            const unresolved = panel.importDependencies.map(panel.dependencyDescription)
            panel.notice = qsTr("Cópia importada; o ZIP contém somente experience.json. Dependências: %1")
                .arg(unresolved.length ? unresolved.join(", ") : qsTr("nenhuma referência personalizada"))
            panel.refreshListAfterSave()
            importDialog.close()
        })
    }

    function beginExport(destination) {
        if (!session || !destination)
            return
        invoke("journey.studio.export.prepare", {
            sessionId: session.sessionId,
            destination: panel.localPath(destination)
        }, function(result) {
            panel.exportPlan = result
            exportConfirmDialog.open()
        })
    }

    function confirmExport() {
        if (!exportPlan || !exportPlan.planId || !exportPlan.confirmToken)
            return
        invoke("journey.studio.export.apply", {
            planId: exportPlan.planId,
            confirmToken: exportPlan.confirmToken
        }, function() {
            exportConfirmDialog.close()
            panel.notice = qsTr("Pacote exportado. O ZIP contém apenas experience.json.")
            panel.exportPlan = null
        })
    }

    function appearanceFor(stageId) {
        for (let i = 0; i < (journeyDocument.sessionStages || []).length; ++i) {
            const stage = journeyDocument.sessionStages[i]
            if (stage.stageId === stageId)
                return stage.appearance || null
        }
        return null
    }

    function usedCoverageStages() {
        const usedStages = []
        function include(stageId) {
            const value = String(stageId || "")
            if (value !== "" && usedStages.indexOf(value) < 0)
                usedStages.push(value)
        }
        menus.forEach(function(menu) { include("menu:" + menu.id) })
        const configuredStages = journeyDocument.sessionStages || []
        configuredStages.forEach(function(stage) { include(stage.stageId) })
        connections.forEach(function(connection) {
            const endpoints = [connection.from, connection.to]
            endpoints.forEach(function(endpoint) {
                if (endpoint && endpoint.kind === "stage")
                    include(endpoint.id)
            })
        })
        return usedStages
    }

    function appearanceForCoverageStage(stageId) {
        const value = String(stageId || "")
        if (value.indexOf("menu:") === 0) {
            const menuId = value.slice(5)
            const menu = menus.find(function(item) { return item.id === menuId })
            return menu ? menu.appearance || null : null
        }
        return appearanceFor(value)
    }

    function implicitAuraStageIds() {
        return usedCoverageStages().filter(function(stageId) {
            return appearanceForCoverageStage(stageId) === null
        })
    }

    function appearanceLabel(appearance) {
        if (appearance && appearance.mode === "custom")
            return String(appearance.themeId || qsTr("tema não identificado"))
        if (appearance && appearance.mode === "inherit-aura")
            return qsTr("AURA · escolha explícita")
        return qsTr("AURA · herança padrão")
    }

    Component.onCompleted: {
        panel.componentReady = true
        if (visible && !panel.refreshStartedWhileVisible) {
            panel.refreshStartedWhileVisible = true
            refresh()
        }
    }
    onVisibleChanged: {
        if (!visible) {
            panel.refreshStartedWhileVisible = false
        } else if (panel.componentReady && !panel.refreshStartedWhileVisible) {
            panel.refreshStartedWhileVisible = true
            refresh()
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Math.round(16 * panel.visualScale)
        spacing: 10

        RowLayout {
            Layout.fillWidth: true
            Label {
                text: qsTr("Jornadas")
                color: panel.textColor
                font.pixelSize: Math.round(22 * panel.visualScale)
                font.weight: Font.Bold
                Layout.fillWidth: true
            }
            Button {
                objectName: "journeyClose"
                text: qsTr("Voltar ao Studio")
                Accessible.name: text
                Layout.minimumHeight: panel.minimumInteractiveTarget
                onClicked: panel.closeJourney()
            }
        }

        Flow {
            objectName: "journeyToolbar"
            Layout.fillWidth: true
            spacing: 8
            Button {
                objectName: "journeyUndo"
                text: qsTr("Desfazer")
                enabled: !panel.busy && !!panel.session
                    && !!panel.session.history && panel.session.history.canUndo === true
                Accessible.name: text
                implicitHeight: panel.minimumInteractiveTarget
                onClicked: panel.historyAction("journey.studio.undo")
            }
            Button {
                objectName: "journeyRedo"
                text: qsTr("Refazer")
                enabled: !panel.busy && !!panel.session
                    && !!panel.session.history && panel.session.history.canRedo === true
                Accessible.name: text
                implicitHeight: panel.minimumInteractiveTarget
                onClicked: panel.historyAction("journey.studio.redo")
            }
            Button {
                objectName: "journeySave"
                text: panel.session && panel.session.dirty ? qsTr("Salvar · não salvo") : qsTr("Salvar")
                enabled: !panel.busy && !!panel.session && panel.session.dirty === true
                Accessible.name: text
                implicitHeight: panel.minimumInteractiveTarget
                onClicked: panel.saveJourney()
            }
            Button {
                objectName: "journeyExport"
                text: qsTr("Exportar")
                enabled: !panel.busy && !!panel.session
                Accessible.name: qsTr("Exportar pacote de Jornada")
                implicitHeight: panel.minimumInteractiveTarget
                onClicked: exportFileDialog.open()
            }
            Button {
                objectName: "journeyImport"
                text: qsTr("Importar cópia")
                enabled: !panel.busy && panel.bridgeAvailable
                Accessible.name: qsTr("Importar Jornada como cópia")
                implicitHeight: panel.minimumInteractiveTarget
                onClicked: importDialog.open()
            }
        }

        RowLayout {
            Layout.fillWidth: true
            ComboBox {
                id: journeyPicker
                objectName: "journeyPicker"
                Layout.fillWidth: true
                Layout.minimumHeight: panel.minimumInteractiveTarget
                model: panel.journeyList
                textRole: "name"
                Accessible.name: qsTr("Jornada salva")
                onActivated: panel.loadJourney(panel.journeyList[currentIndex].id)
            }
            TextField {
                id: journeyNameField
                objectName: "journeyName"
                placeholderText: qsTr("Nome da nova jornada")
                Accessible.name: placeholderText
                Layout.fillWidth: true
                Layout.minimumHeight: panel.minimumInteractiveTarget
            }
            Button {
                objectName: "journeyCreate"
                text: qsTr("Criar")
                enabled: !panel.busy && panel.bridgeAvailable
                Accessible.name: qsTr("Criar jornada")
                Layout.minimumHeight: panel.minimumInteractiveTarget
                onClicked: panel.createJourney()
            }
        }

        Label {
            objectName: "journeyNotice"
            text: panel.notice
            visible: panel.notice !== ""
            color: panel.noticeIsError ? panel.errorColor : panel.amberColor
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        Rectangle {
            visible: !panel.bridgeAvailable
            Layout.fillWidth: true
            Layout.minimumHeight: 64
            radius: 8
            color: panel.raisedColor
            border.color: panel.amberColor
            RowLayout {
                anchors.fill: parent
                anchors.margins: 10
                Label {
                    text: qsTr("A autoria já tem um componente e serviço transacional preparados. Esta sessão ainda não publica os contratos journey.studio.*; por isso, nenhuma gravação é tentada fora da bridge allowlisted.")
                    color: panel.textColor
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                Button {
                    text: qsTr("Verificar novamente")
                    Accessible.name: text
                    Layout.minimumHeight: panel.minimumInteractiveTarget
                    onClicked: panel.refresh()
                }
            }
        }

        Flow {
            objectName: "journeyCompactPaneSelector"
            visible: panel.compactLayout && panel.session !== null
            Layout.fillWidth: true
            spacing: 8
            Button {
                objectName: "journeyShowTree"
                text: qsTr("Árvore de menus")
                Accessible.name: text
                checked: panel.compactPane === "tree"
                implicitHeight: panel.minimumInteractiveTarget
                Layout.minimumHeight: panel.minimumInteractiveTarget
                onClicked: panel.compactPane = "tree"
            }
            Button {
                objectName: "journeyShowInspector"
                text: qsTr("Detalhes e preview")
                Accessible.name: text
                checked: panel.compactPane === "inspector"
                implicitHeight: panel.minimumInteractiveTarget
                Layout.minimumHeight: panel.minimumInteractiveTarget
                onClicked: panel.compactPane = "inspector"
            }
        }

        RowLayout {
            visible: panel.session !== null
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 12

            ColumnLayout {
                visible: !panel.compactLayout || panel.compactPane === "tree"
                Layout.preferredWidth: panel.compactLayout ? 150 : 220
                Layout.minimumWidth: 128
                Layout.fillWidth: panel.compactLayout
                Layout.fillHeight: true
                Label {
                    text: qsTr("Árvore")
                    color: panel.mutedColor
                    font.weight: Font.DemiBold
                }
                Button {
                    objectName: "journeyAddMenu"
                    text: qsTr("Adicionar menu")
                    enabled: !panel.busy && !!panel.catalog.readModels
                        && panel.catalog.readModels.length > 0
                    Accessible.name: text
                    Layout.fillWidth: true
                    Layout.minimumHeight: panel.minimumInteractiveTarget
                    onClicked: panel.addMenu()
                }
                ComboBox {
                    id: organizationParentPicker
                    objectName: "journeyOrganizationParent"
                    Layout.fillWidth: true
                    Layout.minimumHeight: panel.minimumInteractiveTarget
                    model: [{id: "", label: qsTr("No nível principal")}] +
                        (panel.journeyDocument.organization || []).filter(function(node) {
                            return node.kind === "menu"
                        }).map(function(node) {
                            return {
                                id: String(node.id),
                                label: panel.menuDisplayName(node.menuId)
                            }
                        })
                    textRole: "label"
                    Accessible.name: qsTr("Menu pai na árvore de organização")
                    onActivated: panel.organizationParentId = String(model[currentIndex].id || "")
                }
                RowLayout {
                    Layout.fillWidth: true
                    Button {
                        text: qsTr("↑")
                        Accessible.name: qsTr("Mover menu para cima")
                        enabled: !panel.busy && panel.currentMenu !== null
                        Layout.fillWidth: true
                        Layout.minimumHeight: panel.minimumInteractiveTarget
                        onClicked: panel.moveSelectedMenu(-1)
                    }
                    Button {
                        text: qsTr("↓")
                        Accessible.name: qsTr("Mover menu para baixo")
                        enabled: !panel.busy && panel.currentMenu !== null
                        Layout.fillWidth: true
                        Layout.minimumHeight: panel.minimumInteractiveTarget
                        onClicked: panel.moveSelectedMenu(1)
                    }
                }
                Flow {
                    Layout.fillWidth: true
                    spacing: 6
                    Button {
                        objectName: "journeyDuplicateMenu"
                        text: qsTr("Duplicar")
                        Accessible.name: qsTr("Duplicar menu selecionado")
                        enabled: !panel.busy && panel.currentMenu !== null
                        implicitHeight: panel.minimumInteractiveTarget
                        onClicked: panel.duplicateSelectedMenu()
                    }
                    Button {
                        objectName: "journeyRemoveMenu"
                        text: qsTr("Excluir…")
                        Accessible.name: qsTr("Excluir menu selecionado e revisar referências")
                        enabled: !panel.busy && panel.currentMenu !== null && panel.menus.length > 1
                        implicitHeight: panel.minimumInteractiveTarget
                        onClicked: panel.beginRemoveSelectedMenu()
                    }
                }
                ListView {
                    id: menuTree
                    objectName: "journeyMenuTree"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: panel.journeyDocument.organization || []
                    delegate: Button {
                        required property var modelData
                        objectName: "journeyMenu_" + modelData.menuId
                        visible: modelData.kind === "menu"
                        height: Math.max(panel.minimumInteractiveTarget, 48)
                        text: (panel.journeyDocument.entryMenuId === modelData.menuId
                            ? "◆ " : "　") + panel.menuDisplayName(modelData.menuId)
                        Accessible.name: qsTr("Menu %1%2").arg(text).arg(
                            panel.journeyDocument.entryMenuId === modelData.menuId
                                ? qsTr(", entrada da jornada") : "")
                        highlighted: modelData.menuId === panel.selectedMenuId
                        x: panel.organizationDepth(modelData) * 14
                        width: Math.max(48, menuTree.width - x)
                        onClicked: {
                            panel.selectMenu(modelData.menuId)
                        }
                    }
                }
                Label {
                    text: panel.session ? qsTr("%1 menus · recurso máx. %2").arg(panel.menus.length)
                        .arg(panel.session.budgets.maxMenus) : ""
                    color: panel.mutedColor
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }

            ColumnLayout {
                visible: !panel.compactLayout || panel.compactPane === "inspector"
                Layout.fillWidth: true
                Layout.fillHeight: true
                RowLayout {
                    Layout.fillWidth: true
                    Repeater {
                        model: [
                            {id: "menus", label: qsTr("Composição")},
                            {id: "routes", label: qsTr("Conexões")},
                            {id: "stages", label: qsTr("Etapas")}
                        ]
                        delegate: Button {
                            required property var modelData
                            text: modelData.label
                            checked: panel.selectedTab === modelData.id
                            Accessible.name: text
                            Layout.minimumHeight: panel.minimumInteractiveTarget
                            onClicked: panel.selectedTab = modelData.id
                        }
                    }
                    Item { Layout.fillWidth: true }
                    Button {
                        objectName: "journeyPreviewButton"
                        text: qsTr("Pré-visualizar")
                        enabled: !panel.busy && panel.session !== null
                        Accessible.name: text
                        Layout.minimumHeight: panel.minimumInteractiveTarget
                        onClicked: panel.preview()
                    }
                }

                ScrollView {
                    objectName: "journeyInspectorScroll"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    contentWidth: availableWidth
                    ColumnLayout {
                        width: parent.availableWidth
                        spacing: 10

                        ColumnLayout {
                            visible: panel.selectedTab === "menus" && panel.currentMenu !== null
                            Layout.fillWidth: true
                            Label {
                                text: qsTr("Menu: %1").arg(panel.currentMenu ? panel.currentMenu.name : "")
                                color: panel.textColor
                                font.pixelSize: Math.round(18 * panel.visualScale)
                                font.weight: Font.DemiBold
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                TextField {
                                    id: menuNameField
                                    objectName: "journeyMenuName"
                                    text: panel.currentMenu ? panel.currentMenu.name : ""
                                    placeholderText: qsTr("Nome legível")
                                    Accessible.name: qsTr("Nome do menu")
                                    Layout.fillWidth: true
                                    Layout.minimumHeight: panel.minimumInteractiveTarget
                                }
                                Button {
                                    objectName: "journeyRenameMenu"
                                    text: qsTr("Renomear")
                                    Accessible.name: text
                                    enabled: !panel.busy && panel.currentMenu !== null
                                    Layout.minimumHeight: panel.minimumInteractiveTarget
                                    onClicked: panel.transact("rename-menu", {
                                        menuId: panel.currentMenu.id, name: menuNameField.text
                                    })
                                }
                                ComboBox {
                                    id: readModelPicker
                                    objectName: "journeyReadModelPicker"
                                    Layout.fillWidth: true
                                    Layout.minimumHeight: panel.minimumInteractiveTarget
                                    model: panel.catalog.readModels || []
                                    textRole: "name"
                                    Accessible.name: qsTr("Read model público")
                                    currentIndex: {
                                        if (!panel.currentMenu || !panel.currentMenu.source)
                                            return -1
                                        const models = panel.catalog.readModels || []
                                        for (let i = 0; i < models.length; ++i) {
                                            if (models[i].id === panel.currentMenu.source.readModelId)
                                                return i
                                        }
                                        return -1
                                    }
                                    onActivated: {
                                        if (panel.currentMenu && panel.catalog.readModels[currentIndex])
                                            panel.transact("set-source", {
                                                menuId: panel.currentMenu.id,
                                                readModelId: panel.catalog.readModels[currentIndex].id
                                            })
                                    }
                                }
                            }
                            Label {
                                text: panel.currentMenu && panel.currentMenu.source
                                    ? qsTr("Fonte: %1").arg(panel.currentMenu.source.readModelId) : ""
                                color: panel.mutedColor
                                Layout.fillWidth: true
                            }

                            Label {
                                text: qsTr("Filtros de metadados")
                                color: panel.textColor
                                font.weight: Font.DemiBold
                            }
                            Label {
                                text: qsTr("Filtros são combinados em conjunto; vínculos da seleção só restringem a lista e não removem estes critérios.")
                                color: panel.mutedColor
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                ComboBox {
                                    id: filterFieldPicker
                                    objectName: "journeyFilterField"
                                    Layout.fillWidth: true
                                    Layout.minimumHeight: panel.minimumInteractiveTarget
                                    model: panel.currentFields
                                    textRole: "name"
                                    Accessible.name: qsTr("Campo publicado")
                                    onActivated: panel.filterField = String(
                                        panel.currentFields[currentIndex].id || "")
                                    delegate: ItemDelegate {
                                        required property var modelData
                                        width: filterFieldPicker.width
                                        text: panel.publicFieldName(modelData)
                                            + " · " + modelData.type
                                    }
                                }
                                ComboBox {
                                    id: filterOperatorPicker
                                    objectName: "journeyFilterOperator"
                                    Layout.minimumWidth: 180
                                    Layout.minimumHeight: panel.minimumInteractiveTarget
                                    model: [
                                        {id: "equals", name: qsTr("igual a")},
                                        {id: "oneOf", name: qsTr("um destes")},
                                        {id: "contains", name: qsTr("contém")},
                                        {id: "greaterThanOrEqual", name: qsTr("maior ou igual")},
                                        {id: "lessThanOrEqual", name: qsTr("menor ou igual")},
                                        {id: "isKnown", name: qsTr("conhecido")},
                                        {id: "isUnknown", name: qsTr("desconhecido")}
                                    ]
                                    textRole: "name"
                                    Accessible.name: qsTr("Operador do filtro")
                                    onActivated: panel.filterOperator = String(
                                        model[currentIndex].id)
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    TextField {
                                        id: filterValueField
                                        objectName: "journeyFilterValue"
                                        visible: panel.filterOperator !== "isKnown"
                                            && panel.filterOperator !== "isUnknown"
                                        placeholderText: qsTr("Valor")
                                        Accessible.name: qsTr("Valor do filtro")
                                        Layout.fillWidth: true
                                        Layout.minimumHeight: panel.minimumInteractiveTarget
                                        onTextChanged: panel.filterValue = text
                                    }
                                    Button {
                                        objectName: "journeyFilterAdd"
                                        text: qsTr("Adicionar filtro")
                                        enabled: !panel.busy && panel.filterField !== ""
                                        Accessible.name: text
                                        implicitHeight: panel.minimumInteractiveTarget
                                        Layout.minimumHeight: panel.minimumInteractiveTarget
                                        onClicked: panel.addFilter()
                                    }
                                }
                            }
                            Repeater {
                                model: panel.currentMenu ? panel.currentMenu.filters || [] : []
                                delegate: Rectangle {
                                    required property var modelData
                                    required property int index
                                    Layout.fillWidth: true
                                    Layout.minimumHeight: 48
                                    color: panel.surfaceColor
                                    radius: 6
                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.margins: 8
                                        Label {
                                            text: modelData.fieldId + " · " + modelData.operator
                                                + (modelData.value !== undefined
                                                   ? " · " + String(modelData.value) : "")
                                            color: panel.textColor
                                            Layout.fillWidth: true
                                            elide: Text.ElideRight
                                        }
                                        Button {
                                            text: qsTr("Remover")
                                            Accessible.name: qsTr("Remover filtro %1").arg(modelData.fieldId)
                                            implicitHeight: panel.minimumInteractiveTarget
                                            Layout.minimumHeight: panel.minimumInteractiveTarget
                                            onClicked: {
                                                const next = panel.currentMenu.filters.slice()
                                                next.splice(index, 1)
                                                panel.transact("set-filters", {
                                                    menuId: panel.currentMenu.id, values: next
                                                })
                                            }
                                        }
                                    }
                                }
                            }
                            Flow {
                                Layout.fillWidth: true
                                spacing: 8
                                Button {
                                    objectName: "journeySetEntryMenu"
                                    text: panel.currentMenu
                                        && panel.journeyDocument.entryMenuId === panel.currentMenu.id
                                        ? qsTr("Menu de entrada") : qsTr("Definir como entrada")
                                    Accessible.name: panel.currentMenu
                                        ? qsTr("Definir %1 como menu de entrada").arg(panel.currentMenu.name)
                                        : qsTr("Definir menu de entrada")
                                    enabled: !!panel.currentMenu && !panel.busy
                                        && panel.journeyDocument.entryMenuId
                                        !== panel.currentMenu.id
                                    implicitHeight: panel.minimumInteractiveTarget
                                    Layout.minimumHeight: panel.minimumInteractiveTarget
                                    onClicked: panel.setEntryMenu()
                                }
                                Button {
                                    objectName: "journeyClearFilters"
                                    text: qsTr("Limpar filtros")
                                    Accessible.name: text
                                    enabled: !!panel.currentMenu && !panel.busy
                                        && !!panel.currentMenu.filters
                                        && panel.currentMenu.filters.length > 0
                                    implicitHeight: panel.minimumInteractiveTarget
                                    Layout.minimumHeight: panel.minimumInteractiveTarget
                                    onClicked: panel.clearMenuFilters()
                                }
                            }

                            Label {
                                text: qsTr("Ordenação e facetas")
                                color: panel.textColor
                                font.weight: Font.DemiBold
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                ComboBox {
                                    id: menuThemePicker
                                    objectName: "journeyMenuThemePicker"
                                    Layout.fillWidth: true
                                    Layout.minimumWidth: 160
                                    Layout.preferredWidth: 280
                                    Layout.maximumWidth: 360
                                    Layout.minimumHeight: panel.minimumInteractiveTarget
                                    model: panel.catalog.themes || []
                                    textRole: "name"
                                    Accessible.name: qsTr("Tema para este menu")
                                    onActivated: panel.selectedThemeId = String(
                                        panel.catalog.themes[currentIndex].id)
                                }
                                Button {
                                    objectName: "journeyApplyMenuTheme"
                                    text: qsTr("Aplicar ao menu")
                                    Accessible.name: text
                                    enabled: !panel.busy && panel.currentMenu !== null
                                        && panel.selectedThemeId !== ""
                                    Layout.minimumHeight: panel.minimumInteractiveTarget
                                    onClicked: panel.setMenuAppearance()
                                }
                                Button {
                                    text: qsTr("Herdar AURA")
                                    Accessible.name: qsTr("Herdar AURA neste menu")
                                    enabled: !panel.busy && panel.currentMenu !== null
                                    Layout.minimumHeight: panel.minimumInteractiveTarget
                                    onClicked: panel.transact("set-menu-appearance", {
                                        menuId: panel.currentMenu.id,
                                        appearance: {mode: "inherit-aura"}
                                    })
                                }
                            }
                            Flow {
                                Layout.fillWidth: true
                                spacing: 8
                                Repeater {
                                    model: panel.currentFields
                                    delegate: CheckBox {
                                        id: groupFieldCheck
                                        required property var modelData
                                        text: qsTr("Agrupar por %1")
                                            .arg(panel.publicFieldName(modelData))
                                        Accessible.name: text
                                        implicitHeight: panel.minimumInteractiveTarget
                                        Layout.minimumHeight: panel.minimumInteractiveTarget
                                        contentItem: Text {
                                            text: groupFieldCheck.text
                                            font: groupFieldCheck.font
                                            color: panel.textColor
                                            leftPadding: groupFieldCheck.indicator.width
                                                + groupFieldCheck.spacing
                                            verticalAlignment: Text.AlignVCenter
                                            wrapMode: Text.WordWrap
                                        }
                                        checked: panel.currentMenu
                                            && (panel.currentMenu.groupBy || []).indexOf(modelData.id) >= 0
                                        onToggled: {
                                            let next = (panel.currentMenu.groupBy || []).slice()
                                            if (checked && next.indexOf(modelData.id) < 0)
                                                next.push(modelData.id)
                                            else if (!checked)
                                                next = next.filter(function(id) { return id !== modelData.id })
                                            panel.transact("set-group-by", {
                                                menuId: panel.currentMenu.id, values: next
                                            })
                                        }
                                    }
                                }
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                ComboBox {
                                    id: sortFieldPicker
                                    Layout.fillWidth: true
                                    Layout.minimumHeight: panel.minimumInteractiveTarget
                                    model: panel.currentFields
                                    textRole: "name"
                                    Accessible.name: qsTr("Ordenar por campo publicado")
                                }
                                ComboBox {
                                    id: sortDirectionPicker
                                    Layout.minimumHeight: panel.minimumInteractiveTarget
                                    model: [qsTr("Crescente"), qsTr("Decrescente")]
                                    Accessible.name: qsTr("Direção da ordenação")
                                }
                                Button {
                                    text: qsTr("Aplicar ordem")
                                    Accessible.name: text
                                    Layout.minimumHeight: panel.minimumInteractiveTarget
                                    enabled: !panel.busy && panel.currentMenu !== null
                                    onClicked: {
                                        if (sortFieldPicker.currentIndex < 0)
                                            return
                                        const field = panel.currentFields[sortFieldPicker.currentIndex]
                                        panel.transact("set-sort", {
                                            menuId: panel.currentMenu.id,
                                            values: [{fieldId: field.id,
                                                direction: sortDirectionPicker.currentIndex === 1
                                                    ? "descending" : "ascending"}]
                                        })
                                    }
                                }
                            }
                        }

                        ColumnLayout {
                            visible: panel.selectedTab === "routes"
                            Layout.fillWidth: true
                            Label {
                                text: qsTr("Mapa de conexões")
                                color: panel.textColor
                                font.pixelSize: Math.round(18 * panel.visualScale)
                                font.weight: Font.DemiBold
                            }
                            Label {
                                text: qsTr("Cada rota é declarativa. Vínculos transportam apenas campos públicos e filtros fixos continuam restringindo o destino.")
                                color: panel.mutedColor
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                ComboBox {
                                    id: routeSourceKindPicker
                                    objectName: "journeyRouteSourceKind"
                                    Layout.minimumHeight: panel.minimumInteractiveTarget
                                    model: [
                                        {id: "menu", name: qsTr("A partir do menu selecionado")},
                                        {id: "stage", name: qsTr("A partir de uma etapa")}
                                    ]
                                    textRole: "name"
                                    Accessible.name: qsTr("Origem da conexão")
                                    onActivated: panel.routeSourceKind = String(model[currentIndex].id)
                                }
                                ComboBox {
                                    id: routeStagePicker
                                    objectName: "journeyRouteSourceStage"
                                    visible: panel.routeSourceKind === "stage"
                                    Layout.fillWidth: true
                                    Layout.minimumHeight: panel.minimumInteractiveTarget
                                    model: panel.sessionStages
                                    textRole: "label"
                                    Accessible.name: qsTr("Etapa de origem")
                                }
                                ComboBox {
                                    id: eventPicker
                                    objectName: "journeyRouteEvent"
                                    Layout.fillWidth: true
                                    Layout.minimumHeight: panel.minimumInteractiveTarget
                                    model: [
                                        {id: "select", action: "navigate", name: qsTr("Selecionar")},
                                        {id: "back", action: "back", name: qsTr("Voltar")},
                                        {id: "play", action: "launch", name: qsTr("Jogar")},
                                        {id: "pause", action: "pause", name: qsTr("Pausar")},
                                        {id: "resume", action: "resume", name: qsTr("Retomar")},
                                        {id: "open-saves", action: "open-saves", name: qsTr("Abrir saves")},
                                        {id: "save", action: "save", name: qsTr("Salvar estado")},
                                        {id: "load", action: "load", name: qsTr("Carregar estado")},
                                        {id: "exit", action: "exit", name: qsTr("Sair")},
                                        {id: "retry", action: "retry", name: qsTr("Tentar novamente")}
                                    ]
                                    textRole: "name"
                                    Accessible.name: qsTr("Evento semântico")
                                    onActivated: panel.routeEvent = String(model[currentIndex].id)
                                }
                                ComboBox {
                                    id: whenPicker
                                    objectName: "journeyRouteWhen"
                                    Layout.minimumHeight: panel.minimumInteractiveTarget
                                    model: ["user-input", "operation-success", "operation-failure", "timeout"]
                                    Accessible.name: qsTr("Quando executar a conexão")
                                }
                            }
                            RowLayout {
                                visible: panel.routeEvent === "select"
                                Layout.fillWidth: true
                                ComboBox {
                                    id: routeTargetPicker
                                    objectName: "journeyRouteTargetMenu"
                                    Layout.fillWidth: true
                                    Layout.minimumHeight: panel.minimumInteractiveTarget
                                    model: panel.menus
                                    textRole: "name"
                                    Accessible.name: qsTr("Menu de destino")
                                    currentIndex: {
                                        for (let i = 0; i < panel.menus.length; ++i) {
                                            if (panel.menus[i].id !== panel.selectedMenuId)
                                                return i
                                        }
                                        return -1
                                    }
                                }
                                ComboBox {
                                    id: bindingSourcePicker
                                    objectName: "journeyBindingSourceField"
                                    Layout.fillWidth: true
                                    Layout.minimumHeight: panel.minimumInteractiveTarget
                                    model: panel.currentFields
                                    textRole: "name"
                                    Accessible.name: qsTr("Campo público da seleção")
                                    delegate: ItemDelegate {
                                        required property var modelData
                                        width: bindingSourcePicker.width
                                        text: panel.publicFieldName(modelData)
                                            + " · " + modelData.type
                                    }
                                }
                                ComboBox {
                                    id: bindingTargetPicker
                                    objectName: "journeyBindingTargetField"
                                    Layout.fillWidth: true
                                    Layout.minimumHeight: panel.minimumInteractiveTarget
                                    model: panel.routeTargetFields
                                    textRole: "name"
                                    Accessible.name: qsTr("Campo público filtrado no destino")
                                    delegate: ItemDelegate {
                                        required property var modelData
                                        width: bindingTargetPicker.width
                                        text: panel.publicFieldName(modelData)
                                            + " · " + modelData.type
                                    }
                                }
                            }
                            Button {
                                objectName: "journeyConnectionAdd"
                                text: qsTr("Adicionar conexão declarada")
                                enabled: !panel.busy && panel.menus.length > 0
                                Accessible.name: text
                                Layout.minimumHeight: panel.minimumInteractiveTarget
                                onClicked: panel.addConnection()
                            }
                            Repeater {
                                model: panel.connections
                                delegate: Rectangle {
                                    required property var modelData
                                    required property int index
                                    Layout.fillWidth: true
                                    Layout.minimumHeight: 64
                                    color: panel.surfaceColor
                                    border.color: panel.borderColor
                                    radius: 8
                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.margins: 10
                                        Label {
                                            text: panel.endpointLabel(modelData.from) + "  →  "
                                                + panel.endpointLabel(modelData.to)
                                                + " · " + modelData.event + " / " + modelData.when
                                            color: panel.textColor
                                            wrapMode: Text.WordWrap
                                            Layout.fillWidth: true
                                        }
                                        Label {
                                            text: modelData.action
                                            color: panel.accentColor
                                        }
                                        Button {
                                            text: qsTr("Remover")
                                            Accessible.name: qsTr("Remover conexão %1").arg(modelData.label)
                                            Layout.minimumHeight: panel.minimumInteractiveTarget
                                            onClicked: panel.transact("remove-connection", {
                                                connectionId: modelData.id
                                            })
                                        }
                                    }
                                }
                            }
                        }

                        ColumnLayout {
                            visible: panel.selectedTab === "stages"
                            Layout.fillWidth: true
                            Label {
                                text: qsTr("Tema por etapa e capacidades operacionais")
                                color: panel.textColor
                                font.pixelSize: Math.round(18 * panel.visualScale)
                                font.weight: Font.DemiBold
                            }
                            Label {
                                text: qsTr("A aparência é independente da operação. O contrato da sessão decide se pausar, salvar ou retomar está disponível.")
                                color: panel.mutedColor
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                            ComboBox {
                                id: stageThemePicker
                                objectName: "journeyStageThemePicker"
                                Layout.fillWidth: true
                                Layout.minimumHeight: panel.minimumInteractiveTarget
                                model: panel.catalog.themes || []
                                textRole: "name"
                                Accessible.name: qsTr("Tema personalizado para a etapa selecionada")
                                onActivated: panel.selectedThemeId = String(
                                    panel.catalog.themes[currentIndex].id)
                            }
                            Repeater {
                                model: panel.sessionStages
                                delegate: RowLayout {
                                    required property var modelData
                                    Layout.fillWidth: true
                                    Layout.minimumHeight: 56
                                    Label {
                                        text: modelData.label
                                        color: panel.textColor
                                        Layout.fillWidth: true
                                    }
                                    Label {
                                        objectName: "journeyStageAppearance_" + modelData.id
                                        text: panel.appearanceLabel(panel.appearanceFor(modelData.id))
                                        color: panel.mutedColor
                                        Layout.fillWidth: true
                                        elide: Text.ElideRight
                                    }
                                    Button {
                                        text: qsTr("Herdar AURA")
                                        Accessible.name: qsTr("Herdar AURA em %1").arg(modelData.label)
                                        implicitHeight: panel.minimumInteractiveTarget
                                        Layout.minimumHeight: panel.minimumInteractiveTarget
                                        onClicked: panel.transact("set-stage-appearance", {
                                            stageId: modelData.id,
                                            appearance: {mode: "inherit-aura"}
                                        })
                                    }
                                    Button {
                                        text: qsTr("Usar tema")
                                        visible: panel.selectedThemeId !== ""
                                        Accessible.name: qsTr("Usar tema selecionado em %1").arg(modelData.label)
                                        implicitHeight: panel.minimumInteractiveTarget
                                        Layout.minimumHeight: panel.minimumInteractiveTarget
                                        onClicked: panel.setStageAppearance(modelData.id)
                                    }
                                }
                            }
                            Button {
                                text: qsTr("Conferir cobertura antes da prévia")
                                Accessible.name: text
                                Layout.minimumHeight: panel.minimumInteractiveTarget
                                onClicked: panel.inspectCoverage()
                            }
                            Label {
                                objectName: "journeyImplicitAuraNotice"
                                visible: panel.implicitAuraStageIds().length > 0
                                text: qsTr("%1 menu(s)/etapa(s) usarão AURA por herança padrão. Revise a cobertura antes da prévia.")
                                    .arg(panel.implicitAuraStageIds().length)
                                color: panel.amberColor
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                            Label {
                                visible: panel.coverageResult !== null
                                text: panel.coverageResult && panel.coverageResult.summary
                                    ? panel.coverageResult.summary.label : ""
                                color: panel.amberColor
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                            Repeater {
                                model: panel.coverageResult && panel.coverageResult.stages
                                    ? panel.coverageResult.stages : []
                                delegate: Label {
                                    required property var modelData
                                    Layout.fillWidth: true
                                    text: modelData.stageId + " · " + modelData.appearance
                                        + " · " + modelData.reason
                                        + " · origem: " + modelData.sourceThemeId
                                        + " @ " + modelData.sourceVersion
                                        + (modelData.providedSceneElements
                                           && modelData.providedSceneElements.length
                                            ? " · slots: " + modelData.providedSceneElements.join(", ") : "")
                                        + (modelData.missingSceneElements
                                           && modelData.missingSceneElements.length
                                            ? " · elementos ausentes: "
                                                + modelData.missingSceneElements.join(", ") : "")
                                        + (modelData.missingThemeCapabilities
                                           && modelData.missingThemeCapabilities.length
                                            ? " · requisitos visuais ausentes: "
                                                + modelData.missingThemeCapabilities.join(", ") : "")
                                        + (modelData.operationCapability
                                           ? " · operação: " + modelData.operationCapability : "")
                                        + (modelData.missingOperationCapabilities
                                           && modelData.missingOperationCapabilities.length
                                            ? " · operações ausentes: "
                                                + modelData.missingOperationCapabilities.join(", ") : "")
                                    color: modelData.appearance === "custom"
                                        ? panel.textColor : panel.amberColor
                                    wrapMode: Text.WordWrap
                                    Layout.minimumHeight: 48
                                }
                            }
                        }

                        ColumnLayout {
                            visible: panel.previewResult !== null
                                || panel.themePreviewError !== ""
                                || panel.themePreviewLoading
                            Layout.fillWidth: true
                            spacing: 8
                            Label {
                                text: panel.currentMenu
                                    ? qsTr("Prévia de %1 · %2").arg(panel.currentMenu.name)
                                        .arg(panel.themePreviewThemeId || panel.currentThemeId)
                                    : qsTr("Prévia da jornada")
                                color: panel.textColor
                                font.weight: Font.DemiBold
                                Layout.fillWidth: true
                                wrapMode: Text.WordWrap
                            }
                            Rectangle {
                                Layout.fillWidth: true
                                Layout.minimumHeight: 240
                                Layout.preferredHeight: panel.compactLayout ? 300 : 360
                                color: "#000000"
                                border.color: panel.borderColor
                                clip: true
                                ThemeBridge {
                                    id: journeyPreviewBridge
                                    _source: panel.themePreviewObject
                                        ? {"resolved": panel.themePreviewObject} : null
                                }
                                ThemeStudioCanvas {
                                    objectName: "journeyNativeThemePreview"
                                    anchors.fill: parent
                                    visible: panel.themePreviewMode === "native"
                                    graph: journeyPreviewBridge.studioGraph
                                    scene: journeyPreviewBridge.sceneLayoutPreview
                                    readOnly: true
                                    visualScale: panel.visualScale
                                    inspectorTextColor: panel.textColor
                                    inspectorMutedColor: panel.mutedColor
                                    inspectorWarningColor: panel.amberColor
                                }
                                ThemeScenePreview {
                                    objectName: "journeyEsdeThemePreview"
                                    anchors.fill: parent
                                    visible: panel.themePreviewMode === "esde"
                                    themeId: panel.themePreviewThemeId
                                    viewId: panel.previewViewId()
                                    runtimeModelOverride: panel.journeyRuntimeModel()
                                    requestAction: panel.requestAction
                                    surfaceColor: panel.surfaceColor
                                    borderColor: panel.borderColor
                                    textColor: panel.textColor
                                    mutedColor: panel.mutedColor
                                    focusColor: panel.accentColor
                                    synthetic: true
                                }
                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: 16
                                    visible: panel.themePreviewMode === "identity"
                                    Label {
                                        text: panel.themePreviewThemeId
                                        color: journeyPreviewBridge.text
                                        font.weight: Font.DemiBold
                                        Layout.fillWidth: true
                                    }
                                    Label {
                                        text: qsTr("Este tema não declara uma cena de menu. A identidade resolvida abaixo vem do mesmo tema usado pelo Theme Engine.")
                                        color: journeyPreviewBridge.textMuted
                                        wrapMode: Text.WordWrap
                                        Layout.fillWidth: true
                                    }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        Repeater {
                                            model: [
                                                {label: qsTr("Fundo"), color: journeyPreviewBridge.background},
                                                {label: qsTr("Superfície"), color: journeyPreviewBridge.surface},
                                                {label: qsTr("Selecionado"), color: journeyPreviewBridge.surfaceSelected},
                                                {label: qsTr("Acento"), color: journeyPreviewBridge.accent}
                                            ]
                                            delegate: Rectangle {
                                                required property var modelData
                                                Layout.fillWidth: true
                                                Layout.preferredHeight: 64
                                                radius: 6
                                                color: modelData.color
                                                border.color: journeyPreviewBridge.border
                                                Text {
                                                    anchors.centerIn: parent
                                                    text: modelData.label
                                                    color: journeyPreviewBridge.text
                                                    font.pixelSize: Math.round(11 * panel.visualScale)
                                                }
                                            }
                                        }
                                    }
                                }
                                Label {
                                    objectName: "journeyThemePreviewLoading"
                                    anchors.centerIn: parent
                                    visible: panel.themePreviewLoading
                                    text: qsTr("Resolvendo composição…")
                                    color: panel.textColor
                                }
                                Label {
                                    objectName: "journeyThemePreviewError"
                                    anchors.fill: parent
                                    anchors.margins: 12
                                    visible: panel.themePreviewError !== ""
                                    text: panel.themePreviewError
                                    color: panel.errorColor
                                    wrapMode: Text.WordWrap
                                    verticalAlignment: Text.AlignVCenter
                                    horizontalAlignment: Text.AlignHCenter
                                }
                            }
                            Label {
                                objectName: "journeyPreviewResultCount"
                                text: panel.previewResult
                                    ? qsTr("%1 resultados de %2 itens na fonte · exibindo %3")
                                        .arg(panel.previewResult.resultCount)
                                        .arg(panel.previewResult.totalCount)
                                        .arg(panel.previewResult.returnedCount) : ""
                                color: panel.mutedColor
                                Layout.fillWidth: true
                            }
                            Label {
                                objectName: "journeyPreviewDiagnostic"
                                visible: panel.previewResult !== null
                                    && panel.previewResult.diagnosticMessage !== ""
                                text: panel.previewResult
                                    ? String(panel.previewResult.diagnosticMessage || "")
                                    + (panel.previewResult.recoveryAction
                                        ? qsTr(" · Recuperação: %1")
                                            .arg(panel.previewResult.recoveryAction) : "")
                                    : ""
                                color: panel.previewResult
                                    && panel.previewResult.resultState === "results"
                                    ? panel.mutedColor : panel.amberColor
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                            Label {
                                objectName: "journeyPreviewUnknownValues"
                                visible: panel.previewResult !== null
                                    && Object.keys(panel.previewResult.unknownValueCounts || {}).length > 0
                                text: {
                                    if (!panel.previewResult)
                                        return ""
                                    const counts = panel.previewResult.unknownValueCounts || ({})
                                    return Object.keys(counts).map(function(fieldId) {
                                        return fieldId + ": " + counts[fieldId] + " sem valor"
                                    }).join(" · ")
                                }
                                color: panel.amberColor
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                            ListView {
                                objectName: "journeyPreviewRows"
                                Layout.fillWidth: true
                                Layout.preferredHeight: 128
                                clip: true
                                model: panel.previewResult ? panel.previewResult.rows || [] : []
                                delegate: Label {
                                    required property var modelData
                                    width: ListView.view.width
                                    height: Math.max(panel.minimumInteractiveTarget, 48)
                                    text: String(modelData.title || modelData.name || modelData.id || "")
                                    color: panel.textColor
                                    verticalAlignment: Text.AlignVCenter
                                    elide: Text.ElideRight
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    Dialog {
        id: deleteMenuDialog
        objectName: "journeyDeleteMenuDialog"
        title: qsTr("Excluir menu e revisar destinos")
        modal: true
        standardButtons: Dialog.NoButton
        contentItem: ColumnLayout {
            Label {
                id: deleteImpactLabel
                objectName: "journeyDeleteImpact"
                Layout.fillWidth: true
                text: {
                    const menu = panel.menus.find(function(item) {
                        return item.id === panel.pendingDeleteMenuId
                    })
                    const impact = panel.menuDeleteImpact(panel.pendingDeleteMenuId)
                    return qsTr("Excluir %1? Referências que precisam de decisão:\n%2")
                        .arg(menu ? menu.name : panel.pendingDeleteMenuId)
                        .arg(impact.length ? impact.join("\n") : qsTr("Nenhuma conexão ou filho será alterado."))
                }
                color: panel.textColor
                wrapMode: Text.WordWrap
            }
            ComboBox {
                id: replacementMenuPicker
                objectName: "journeyReplacementMenu"
                Layout.fillWidth: true
                Layout.minimumHeight: panel.minimumInteractiveTarget
                model: panel.menus.filter(function(menu) {
                    return menu.id !== panel.pendingDeleteMenuId
                })
                textRole: "name"
                Accessible.name: qsTr("Menu que receberá conexões e filhos")
                currentIndex: {
                    for (let i = 0; i < replacementMenuPicker.count; ++i) {
                        if (replacementMenuPicker.model[i].id === panel.pendingReplacementMenuId)
                            return i
                    }
                    return -1
                }
                onActivated: panel.pendingReplacementMenuId = String(model[currentIndex].id)
            }
            Label {
                Layout.fillWidth: true
                text: panel.menuHasReferences(panel.pendingDeleteMenuId)
                    ? qsTr("Este menu é usado pela entrada, uma conexão ou a árvore. Selecione uma substituição para conservar essas referências.")
                    : qsTr("Este menu não tem referências; pode removê-lo sem substituir outro destino.")
                color: panel.amberColor
                wrapMode: Text.WordWrap
            }
            RowLayout {
                Layout.fillWidth: true
                Button {
                    text: qsTr("Cancelar")
                    Accessible.name: text
                    Layout.minimumHeight: panel.minimumInteractiveTarget
                    onClicked: {
                        deleteMenuDialog.close()
                        panel.pendingDeleteMenuId = ""
                        panel.pendingReplacementMenuId = ""
                    }
                }
                Item { Layout.fillWidth: true }
                Button {
                    id: deleteMenuConfirmButton
                    objectName: "journeyDeleteMenuConfirm"
                    text: replacementMenuPicker.currentIndex >= 0
                        ? qsTr("Substituir e excluir") : qsTr("Excluir menu")
                    Accessible.name: text
                    enabled: !panel.busy
                        && (!panel.menuHasReferences(panel.pendingDeleteMenuId)
                            || panel.pendingReplacementMenuId !== "")
                    Layout.minimumHeight: panel.minimumInteractiveTarget
                    onClicked: panel.confirmRemoveSelectedMenu()
                }
            }
        }
    }

    Dialog {
        id: importDialog
        title: qsTr("Importar cópia de Jornada")
        modal: true
        standardButtons: Dialog.Cancel
        contentItem: ColumnLayout {
            TextField {
                id: importNameField
                objectName: "journeyImportName"
                placeholderText: qsTr("Nome da cópia")
                Accessible.name: placeholderText
                Layout.minimumHeight: panel.minimumInteractiveTarget
            }
            Label {
                text: panel.selectedImportUrl
                    ? panel.localPath(panel.selectedImportUrl) : qsTr("Nenhum pacote selecionado")
                color: panel.mutedColor
                wrapMode: Text.WrapAnywhere
                Layout.fillWidth: true
            }
            Button {
                text: qsTr("Escolher pacote ZIP")
                Accessible.name: text
                Layout.minimumHeight: panel.minimumInteractiveTarget
                onClicked: importFileDialog.open()
            }
        }
    }

    FileDialog {
        id: importFileDialog
        title: qsTr("Selecionar pacote de Jornada")
        fileMode: FileDialog.OpenFile
        nameFilters: [qsTr("Pacotes de Jornada (*.zip)")]
        onAccepted: {
            panel.selectedImportUrl = selectedFile.toString()
            panel.beginImport()
        }
    }

    FileDialog {
        id: exportFileDialog
        title: qsTr("Exportar pacote de Jornada")
        fileMode: FileDialog.SaveFile
        nameFilters: [qsTr("Pacotes de Jornada (*.zip)")]
        onAccepted: panel.beginExport(selectedFile.toString())
    }

    Dialog {
        id: exportConfirmDialog
        objectName: "journeyExportConfirmDialog"
        title: qsTr("Confirmar exportação")
        modal: true
        standardButtons: Dialog.Cancel | Dialog.Save
        onAccepted: panel.confirmExport()
        contentItem: Label {
            text: panel.exportPlan
                ? qsTr("Exportar %1 (%2 bytes)? O ZIP inclui experience.json e referências não incorporadas aos temas.")
                    .arg(panel.exportPlan.filename || qsTr("jornada.zip"))
                    .arg(panel.exportPlan.size || 0)
                : ""
            color: panel.textColor
            wrapMode: Text.WordWrap
        }
    }
}
