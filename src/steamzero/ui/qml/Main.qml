// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts

ApplicationWindow {
    id: root
    width: Math.min(1600, Screen.desktopAvailableWidth)
    height: Math.min(1000, Screen.desktopAvailableHeight)
    minimumWidth: 720
    minimumHeight: 480
    visible: true
    title: qsTr("SteamZero — Central de jogos")
    color: backgroundColor
    palette.window: backgroundColor
    palette.windowText: textColor
    palette.base: surfaceColor
    palette.alternateBase: raisedColor
    palette.text: textColor
    palette.button: raisedColor
    palette.buttonText: textColor
    palette.highlight: cyanDarkColor
    palette.accent: cyanColor
    palette.highlightedText: textColor
    palette.toolTipBase: raisedColor
    palette.toolTipText: textColor
    palette.disabled.buttonText: "#667481"
    palette.disabled.text: "#667481"

    readonly property color backgroundColor: "#071019"
    readonly property color sidebarColor: "#09131d"
    readonly property color surfaceColor: "#0d1924"
    readonly property color raisedColor: "#122131"
    readonly property color borderColor: "#2a3a49"
    readonly property color textColor: "#f2f6fb"
    readonly property color mutedColor: "#9eabba"
    readonly property color cyanColor: "#13bdf2"
    readonly property color cyanDarkColor: "#0a5f85"
    readonly property color amberColor: "#ff9f1a"
    readonly property color greenColor: "#59d35d"
    readonly property color redColor: "#ff6b73"
    readonly property bool compactLayout: width <= 1366 || height <= 850
    readonly property bool handheldLayout: width <= 1024 || height <= 640
    readonly property bool reducedMotion: desktopStatus.dashboard
        && desktopStatus.dashboard.accessibility
        && desktopStatus.dashboard.accessibility.reducedMotion === true
    readonly property int motionDuration: reducedMotion ? 0 : 180
    readonly property int bottomSafeInset: compactLayout ? 60 : 24
    readonly property bool ultrawideLayout: width >= 2200
    readonly property int responsiveGutter: compactLayout ? 12 : 28
    readonly property int contentMaxWidth: ultrawideLayout ? 1400 : 1920
    readonly property int navigationWidth: compactLayout ? 72
        : width >= 1400 ? 264 : 228
    property alias responsiveShell: appShell
    property alias responsiveNavigation: navRepeater
    property alias responsiveDrawer: navigationDrawer
    property alias responsiveDrawerNavigation: drawerNavRepeater
    property alias responsiveTaskDrawer: taskDrawer
    property alias responsiveHeader: compactHeader
    property alias navigationMenuControl: navigationMenuButton
    property alias taskMenuControl: compactTaskButton
    property alias responsiveContent: contentStack
    property alias responsiveFooter: handheldFooter
    property alias overviewScrollControl: overviewScroll
    property alias profilesScrollControl: profilesScroll
    property alias syncScrollControl: syncScroll
    property alias systemScrollControl: systemScroll
    property alias syncProviderControl: providerStatusCard
    property alias syncUpdateControl: syncUpdateButton
    property alias profilePickerControl: profilePicker
    property alias profilePlanControl: planButton
    property alias emulationControl: emulationPage
    property alias steamGameplayControl: steamGameplayPage
    property alias diagnosticsPreviewControl: diagnosticsPreviewDialog
    property alias credentialDialogControl: credentialDialog
    property alias credentialScrollControl: credentialScroll
    property alias credentialProviderRepeaterControl: credentialProviderRepeater
    property alias credentialCloseControl: credentialCloseButton

    property var desktopStatus: ({
        "truthState": "unapplied",
        "desiredProfile": "handheld-desktop",
        "appliedProfile": null,
        "observedProfile": null,
        "effectiveProfile": null,
        "recommendedProfile": "handheld-desktop",
        "observation": {"checkedEffects": [], "unavailableEffects": [], "ambiguousCandidates": [], "errors": []},
        "statusReasons": [],
        "recoveryRequired": false,
        "independentRuntime": true,
        "context": {"deviceKind": "deck-lcd", "displays": [], "capabilities": [], "conflicts": []},
        "dashboard": {
            "components": [], "steam": [], "sync": {}, "doctor": {"checks": []},
            "uiContracts": {"schemaVersion": 1, "states": [], "actions": [], "byId": {}}
        }
    })
    property Item dialogInvoker: null
    property var fallbackComponents: [
        {
            "id": "dolphin", "name": "Dolphin", "description": "Emulador de Wii e GameCube",
            "iconName": "dolphin-emu", "systems": ["Wii", "GameCube"], "state": "missing",
            "statusLabel": "Não instalado", "versionLabel": "—", "targetVersion": "—",
            "detail": "O status será atualizado quando a bridge local responder.",
            "blockedReason": "", "action": {"kind": "detail", "label": "Bridge indisponível", "enabled": false,
                "reason": "A bridge local ainda não publicou uma ação operacional."}
        },
        {
            "id": "duckstation", "name": "DuckStation", "description": "Emulador de PlayStation",
            "iconName": "duckstation", "systems": ["PlayStation"], "state": "unsupported",
            "statusLabel": "Fonte descontinuada", "versionLabel": "—", "targetVersion": "—",
            "detail": "A origem validada está descontinuada.",
            "blockedReason": "", "action": {"kind": "detail", "label": "Indisponível", "enabled": false}
        },
        {
            "id": "retroarch", "name": "RetroArch", "description": "Plataforma multi-emulador",
            "iconName": "retroarch", "systems": ["Múltiplos"], "state": "missing",
            "statusLabel": "Não instalado", "versionLabel": "—", "targetVersion": "—",
            "detail": "O status será atualizado quando a bridge local responder.",
            "blockedReason": "", "action": {"kind": "detail", "label": "Bridge indisponível", "enabled": false,
                "reason": "A bridge local ainda não publicou uma ação operacional."}
        }
    ]
    property var fallbackSteam: [
        {
            "id": "steam-client", "name": "Cliente Steam", "description": "Cliente oficial e modo Big Picture",
            "iconName": "steam", "state": "missing", "statusLabel": "Verificando", "versionLabel": "—",
            "detail": "O estado do Steam será atualizado pela bridge local.",
            "action": {"kind": "detail", "label": "Bridge indisponível", "enabled": false,
                "reason": "A bridge local ainda não publicou uma ação operacional."}
        }
    ]
    property var fallbackSteamGameplay: ({
        "games": [],
        "environment": [
            {"id": "steam", "name": "Steam", "detail": "Contexto de jogo e runtime", "owner": "Steam", "required": true, "state": "missing", "statusLabel": "ausente"},
            {"id": "gamescope", "name": "Gamescope", "detail": "Composição e limite de quadros", "owner": "SteamZero", "required": true, "state": "missing", "statusLabel": "ausente"},
            {"id": "gamemode", "name": "Feral GameMode", "detail": "Prioridade de CPU e processos", "owner": "Steam", "required": true, "state": "missing", "statusLabel": "ausente"},
            {"id": "mangohud", "name": "MangoHud", "detail": "Métricas durante o jogo", "owner": "SteamZero", "required": false, "state": "missing", "statusLabel": "ausente, opcional"},
            {"id": "mangoapp", "name": "MangoApp", "detail": "Overlay compatível com Gamescope", "owner": "Sistema", "required": false, "state": "missing", "statusLabel": "ausente, opcional"},
            {"id": "vkbasalt", "name": "vkBasalt", "detail": "Pós-processamento Vulkan", "owner": "Sistema", "required": false, "state": "missing", "statusLabel": "ausente, opcional"},
            {"id": "lsfg", "name": "LSFG-VK", "detail": "Geração de quadros configurada por jogo", "owner": "Sistema", "required": false, "state": "missing", "statusLabel": "ausente, opcional"}
        ],
        "readiness": {"percent": 0, "title": "Ambiente Steam indisponível", "detail": "Abra Sistema para diagnosticar"},
        "hardware": {"deviceLabel": "Linux", "tdpMin": null, "tdpMax": null, "gpuMin": null, "gpuMax": null, "refreshHz": null, "memoryGb": null, "withinSafeLimits": false},
        "context": {"device": "Linux", "battery": null, "mode": "Modo Desktop"},
        "currentProfile": {"gameId": "", "scope": "global", "profile": "balanced", "fps": 40, "tdp": null, "gpuMode": "auto", "gpuClock": null, "gamescope": false, "gameMode": false, "mangoHud": "off", "upscaling": "native", "frameGeneration": "off", "controllerLayout": "steam-recommended"},
        "launcher": {"state": "unconfigured", "statusLabel": "Selecione um jogo", "launchOption": "", "recoveryRequired": false, "configuration": {"state": "unavailable", "statusLabel": "Configuração Steam indisponível", "managed": false, "lastOperationId": null}},
        "impact": {"battery": "—", "resolution": "1280×800", "fluidity": "40 FPS estáveis"},
        "lsfgInstaller": {"id": "lsfg-vk", "state": "missing", "statusLabel": "Não instalado", "detail": "Camada Vulkan LSFG-VK ainda não preparada.", "version": null, "source": "PancakeTAS/lsfg-vk", "archiveSha256": "", "losslessScalingInstalled": false, "supportedHardware": true, "installable": false, "lastOperationId": null}
    })
    readonly property var emulatorItems: desktopStatus.dashboard && desktopStatus.dashboard.components
        ? desktopStatus.dashboard.components : fallbackComponents
    readonly property var emulationData: desktopStatus.dashboard
        && desktopStatus.dashboard.emulation
        ? desktopStatus.dashboard.emulation : ({
            "schemaVersion": 1,
            "truthState": "degraded",
            "contextLabel": root.deviceSummary(),
            "platforms": [
                {
                    "id": "switch",
                    "name": qsTr("Nintendo Switch"),
                    "shortName": qsTr("Switch"),
                    "iconKey": "switch",
                    "state": "degraded",
                    "statusLabel": qsTr("Backend Switch ainda não conectado"),
                    "modeLabel": desktopStatus.context && desktopStatus.context.displays
                        && desktopStatus.context.displays.length > 1
                        ? qsTr("Dock detectado") : qsTr("Modo portátil ou desktop"),
                    "modeShortLabel": desktopStatus.context && desktopStatus.context.displays
                        && desktopStatus.context.displays.length > 1 ? qsTr("Dock") : qsTr("Portátil"),
                    "readiness": {
                        "percent": 0,
                        "title": qsTr("Conectando a plataforma Switch"),
                        "detail": qsTr("A apresentação está pronta; keys, firmware, emuladores e jogos ainda precisam ser publicados pela bridge local."),
                        "blockers": [
                            qsTr("Keys e firmware ainda não verificados"),
                            qsTr("Nenhum emulador Switch confirmado")
                        ]
                    },
                    "emulators": [],
                    "games": []
                },
                root.legacyPlatform(
                    "nintendo-classic",
                    qsTr("Nintendo Wii e GameCube"),
                    "input-gaming",
                    ["Wii", "GameCube"]
                ),
                root.legacyPlatform(
                    "playstation",
                    qsTr("PlayStation"),
                    "applications-games",
                    ["PlayStation"]
                ),
                root.legacyPlatform(
                    "multi",
                    qsTr("Multi-sistema"),
                    "folder-games",
                    ["Múltiplos"]
                )
            ]
        })
    readonly property var steamItems: desktopStatus.dashboard && desktopStatus.dashboard.steam
        ? desktopStatus.dashboard.steam : fallbackSteam
    readonly property var steamGameplayData: desktopStatus.dashboard
        && desktopStatus.dashboard.steamGameplay
        ? desktopStatus.dashboard.steamGameplay : fallbackSteamGameplay
    readonly property var lsfgSystemData: steamGameplayData && steamGameplayData.lsfgInstaller
        ? steamGameplayData.lsfgInstaller : fallbackSteamGameplay.lsfgInstaller
    property var liveTasks: null
    readonly property var taskItems: liveTasks !== null ? liveTasks
        : emulationData && emulationData.jobs ? emulationData.jobs : []
    readonly property var uiContracts: desktopStatus.dashboard
        && desktopStatus.dashboard.uiContracts
        ? desktopStatus.dashboard.uiContracts : ({"actions": [], "byId": {}})
    readonly property bool hasConflicts: desktopStatus.context
        && desktopStatus.context.conflicts && desktopStatus.context.conflicts.length > 0
    readonly property bool desktopTruthNeedsAttention: ["stale", "degraded", "unapplied"]
        .indexOf(desktopStatus.truthState) >= 0
    readonly property bool needsAttention: hasConflicts || desktopTruthNeedsAttention
        || desktopStatus.recoveryRequired

    property int sectionIndex: 1
    property int emulatorFilter: 0
    property int steamFilter: 0
    property string steamArea: "performance"
    property var selectedEmulator: null
    property var selectedSteam: null
    property string selectedProfile: "auto"
    property var currentPlan: null
    property var conflictPlan: null
    property var componentPlan: null
    property var emulationPlan: null
    property var lsfgPlan: null
    property string lsfgLastOperationId: ""
    property var diagnosticsPlan: null
    property var diagnosticsPreview: ({})
    property string diagnosticsKind: "state"
    property string apiUrl: ""
    property string apiToken: ""
    property string lastRequest: ""
    property bool lastRequestIsError: false
    property int pendingRequests: 0
    property bool recoveryPromptShown: false
    property bool keyboardVisible: false

    function sectionLabel(index) {
        return [
            qsTr("Visão geral"), qsTr("Emulação"), qsTr("Steam"),
            qsTr("Perfis"), qsTr("Saves e Sync"), qsTr("Sistema")
        ][index] || qsTr("Central")
    }

    function activeTaskCount() {
        return taskItems.filter(function(job) {
            return job.state === "queued" || job.state === "running"
        }).length
    }

    function taskStateLabel(state) {
        return ({
            "queued": qsTr("Na fila"), "running": qsTr("Em andamento"),
            "succeeded": qsTr("Concluída"), "failed": qsTr("Falhou"),
            "cancelled": qsTr("Cancelada")
        })[state] || qsTr("Estado desconhecido")
    }

    function taskLabel(type) {
        return ({
            "library.scan": qsTr("Varredura da biblioteca"),
            "rom.scan": qsTr("Descoberta de ROMs"),
            "media.search": qsTr("Busca de mídia"),
            "ui.action": qsTr("Ação da interface"),
            "content.import": qsTr("Importação de conteúdo"),
            "nsz.convert": qsTr("Conversão NSZ"),
            "steam.publish": qsTr("Publicação na Steam")
        })[type] || type
    }

    function taskProgress(job) {
        const progress = job && job.progress ? job.progress : {}
        const current = Number(progress.current || 0)
        const total = Number(progress.total || 0)
        return total > 0 ? Math.max(0, Math.min(1, current / total)) : 0
    }

    function taskResultSummary(job) {
        const result = job && job.result ? job.result : {}
        const progress = job && job.progress ? job.progress : {}
        if (job.state === "running" && Number(progress.total || 0) > 0)
            return qsTr("%1 de %2 %3").arg(progress.current || 0)
                .arg(progress.total).arg(progress.unit || qsTr("itens"))
        if (job.state === "queued")
            return qsTr("Aguardando recursos; pode ser cancelada com segurança.")
        if (job.type === "library.scan")
            return qsTr("%1 jogo(s); %2 sem identificação; %3 erro(s)")
                .arg(result.games || 0).arg(result.unidentified || 0)
                .arg(result.errors ? result.errors.length : 0)
        if (job.type === "media.search") {
            const providerErrors = result.provider_errors || {}
            const degraded = Object.keys(providerErrors).length
            return degraded > 0
                ? qsTr("%1 candidato(s); %2 provider(s) degradado(s)")
                    .arg(result.candidate_count || 0).arg(degraded)
                : qsTr("%1 candidato(s) encontrado(s)").arg(result.candidate_count || 0)
        }
        if (result.message)
            return String(result.message)
        if (job.errorCode)
            return qsTr("Código: %1. Abra os detalhes para tentar novamente.").arg(job.errorCode)
        return taskStateLabel(job.state)
    }

    function refreshTasks() {
        requestAction("jobs.list", {}, function(response) {
            liveTasks = response.jobs || []
        })
    }

    function ensureFocusedItemVisible(item) {
        if (!item)
            return
        let ancestor = item.parent
        while (ancestor && ancestor !== root.contentItem) {
            if (ancestor.contentY !== undefined && ancestor.contentItem
                    && ancestor.height !== undefined) {
                const point = item.mapToItem(ancestor.contentItem, 0, 0)
                const top = point.y - 12
                const bottom = point.y + item.height + 12
                if (top < ancestor.contentY)
                    ancestor.contentY = Math.max(0, top)
                else if (bottom > ancestor.contentY + ancestor.height)
                    ancestor.contentY = Math.min(
                        Math.max(0, ancestor.contentHeight - ancestor.height),
                        bottom - ancestor.height
                    )
            }
            ancestor = ancestor.parent
        }
    }

    function rememberDialogInvoker() {
        const active = root.activeFocusItem
        if (active)
            dialogInvoker = active
    }

    function restoreDialogFocus() {
        const invoker = dialogInvoker
        Qt.callLater(function() {
            if (invoker && invoker.visible && invoker.enabled)
                invoker.forceActiveFocus(Qt.TabFocusReason)
        })
    }

    Connections {
        target: root
        function onActiveFocusItemChanged() {
            const item = root.activeFocusItem
            if (item)
                Qt.callLater(function() {
                    root.ensureFocusedItemVisible(item)
                })
        }
    }

    signal planRequested(string profile)
    signal recoveryRequested()
    signal keyboardRequested(string language)

    function parseArguments() {
        const args = Qt.application.arguments
        const marker = args.indexOf("--steamzero-status")
        if (marker >= 0 && marker + 1 < args.length) {
            try {
                desktopStatus = JSON.parse(args[marker + 1])
            } catch (error) {
                notify(qsTr("Status inválido; modo observador mantido"), true)
            }
        }
        const apiMarker = args.indexOf("--steamzero-api")
        const tokenMarker = args.indexOf("--steamzero-token")
        const sectionMarker = args.indexOf("--steamzero-section")
        const steamAreaMarker = args.indexOf("--steamzero-steam-area")
        if (apiMarker >= 0 && apiMarker + 1 < args.length)
            apiUrl = args[apiMarker + 1]
        if (tokenMarker >= 0 && tokenMarker + 1 < args.length)
            apiToken = args[tokenMarker + 1]
        if (sectionMarker >= 0 && sectionMarker + 1 < args.length) {
            const sections = {"overview": 0, "emulators": 1, "steam": 2, "profiles": 3, "sync": 4, "system": 5}
            if (sections[args[sectionMarker + 1]] !== undefined)
                sectionIndex = sections[args[sectionMarker + 1]]
        }
        if (steamAreaMarker >= 0 && steamAreaMarker + 1 < args.length
                && ["performance", "controls", "library", "desktop"]
                    .indexOf(args[steamAreaMarker + 1]) >= 0)
            steamArea = args[steamAreaMarker + 1]
        ensureSelections()
        if (apiUrl !== "" && apiToken !== "")
            Qt.callLater(function() { refreshStatus("") })
        if (desktopStatus.recoveryRequired) {
            recoveryPromptShown = true
            Qt.callLater(recoveryDialog.open)
        }
    }

    function notify(message, isError) {
        lastRequest = message
        lastRequestIsError = isError === true
        feedbackTimer.restart()
    }

    function recordActionFailure(actionId, message) {
        const current = liveTasks !== null ? liveTasks.slice()
            : (emulationData && emulationData.jobs ? emulationData.jobs.slice() : [])
        const now = new Date().toISOString()
        current.unshift({
            "jobId": "ui-" + Date.now() + "-" + current.length,
            "type": "ui.action",
            "state": "failed",
            "rawState": "failed",
            "priority": "interactive",
            "progress": null,
            "errorCode": "E-UI-ACTION",
            "result": {"message": String(message), "actionId": actionId},
            "canCancel": false,
            "canRetry": false,
            "createdAt": now,
            "updatedAt": now
        })
        liveTasks = current.slice(0, 20)
    }

    function errorMessage(response, fallback) {
        if (!response || response.error === undefined)
            return fallback
        if (typeof response.error === "string")
            return response.error
        return response.error.title || response.error.detail || response.error.code || fallback
    }

    function request(method, path, payload, callback, errorCallback) {
        if (!apiUrl || !apiToken) {
            const message = qsTr("Bridge local indisponível; nenhuma mudança foi feita")
            if (errorCallback)
                errorCallback(message)
            notify(message, true)
            return
        }
        const xhr = new XMLHttpRequest()
        let completed = false
        pendingRequests += 1
        xhr.open(method, apiUrl + path)
        xhr.setRequestHeader("Content-Type", "application/json")
        xhr.setRequestHeader("X-SteamZero-Token", apiToken)
        xhr.timeout = path === "/component/apply" ? 1900000 : 60000

        function finish() {
            if (completed)
                return false
            completed = true
            root.pendingRequests = Math.max(0, root.pendingRequests - 1)
            return true
        }

        xhr.onreadystatechange = function() {
            if (xhr.readyState !== XMLHttpRequest.DONE || !finish())
                return
            try {
                const response = JSON.parse(xhr.responseText)
                if (xhr.status < 200 || xhr.status >= 300) {
                    const message = root.errorMessage(response, qsTr("Ação recusada"))
                    if (errorCallback)
                        errorCallback(message)
                    root.notify(message, true)
                    return
                }
                callback(response)
            } catch (error) {
                const message = qsTr("Resposta inválida; nenhuma mudança adicional foi feita")
                if (errorCallback)
                    errorCallback(message)
                root.notify(message, true)
            }
        }
        xhr.onerror = function() {
            if (finish()) {
                const message = qsTr("A central local não respondeu; o estado foi preservado")
                if (errorCallback)
                    errorCallback(message)
                root.notify(message, true)
            }
        }
        xhr.ontimeout = function() {
            if (finish()) {
                const message = qsTr("A operação excedeu o tempo esperado; verifique o estado antes de repetir")
                if (errorCallback)
                    errorCallback(message)
                root.notify(message, true)
            }
        }
        xhr.send(JSON.stringify(payload || {}))
    }

    function backendAction(actionId) {
        const actions = uiContracts && uiContracts.byId ? uiContracts.byId : {}
        return actions[actionId] || null
    }

    function requestAction(actionId, payload, callback, errorCallback) {
        const action = backendAction(actionId)
        if (!action || action.applicability !== "applicable" || action.enabled !== true
                || !action.endpoint || !action.method) {
            const message = action && action.reason
                ? action.reason
                : qsTr("A bridge não publicou o contrato %1; nenhuma mudança foi feita.").arg(actionId)
            recordActionFailure(actionId, message)
            if (errorCallback)
                errorCallback(message)
            notify(message, true)
            return
        }
        request(action.method, action.endpoint, payload, callback, function(message) {
            root.recordActionFailure(actionId, message)
            if (errorCallback)
                errorCallback(message)
        })
    }

    function localPath(url) {
        const value = String(url || "")
        if (!value.startsWith("file://"))
            return ""
        return decodeURIComponent(value.replace(/^file:\/\/(?:localhost)?/, ""))
    }

    function beginDiagnosticsExport(kind) {
        diagnosticsKind = kind
        diagnosticsExportDialog.open()
    }

    function refreshStatus(message) {
        // /status é o único bootstrap: ele entrega o próprio catálogo de contratos.
        request("GET", "/status", {}, function(response) {
            desktopStatus = response
            liveTasks = null
            currentPlan = null
            ensureSelections()
            if (desktopStatus.recoveryRequired && !recoveryPromptShown) {
                recoveryPromptShown = true
                recoveryDialog.open()
            }
            if (message)
                notify(message, false)
        })
    }

    function ensureSelections() {
        if (emulatorItems.length > 0) {
            const emulatorId = selectedEmulator ? selectedEmulator.id : ""
            selectedEmulator = emulatorItems.find(function(row) { return row.id === emulatorId })
                || emulatorItems[0]
        }
        if (steamItems.length > 0) {
            const steamId = selectedSteam ? selectedSteam.id : ""
            selectedSteam = steamItems.find(function(row) { return row.id === steamId })
                || steamItems[0]
        }
    }

    function filterRows(rows, filter) {
        if (filter === 1)
            return rows.filter(function(row) {
                return ["attention", "unsupported", "blocked", "missing"].indexOf(row.state) >= 0
            })
        if (filter === 2)
            return rows.filter(function(row) {
                return ["installed", "available", "running"].indexOf(row.state) >= 0
            })
        return rows
    }

    function legacyPlatform(id, name, iconKey, systems) {
        const rows = emulatorItems.filter(function(row) {
            const rowSystems = row.systems || []
            return systems.some(function(system) { return rowSystems.indexOf(system) >= 0 })
        })
        const ready = readyCount(rows)
        const total = rows.length
        const percent = total > 0 ? Math.round(ready * 100 / total) : 0
        return {
            "id": id,
            "name": name,
            "shortName": name,
            "iconKey": iconKey,
            "state": ready > 0 ? "ready" : total > 0 ? "degraded" : "empty",
            "statusLabel": ready > 0
                ? qsTr("%1 de %2 emulador(es) pronto(s)").arg(ready).arg(total)
                : total > 0 ? qsTr("Requer atenção") : qsTr("Nenhum emulador catalogado"),
            "readiness": {
                "percent": percent,
                "title": ready > 0 ? qsTr("Plataforma parcialmente pronta")
                    : qsTr("Emuladores ainda não preparados"),
                "detail": qsTr("A compatibilidade detalhada desta plataforma será incorporada de forma incremental."),
                "blockers": ready > 0 ? [] : [qsTr("Nenhum emulador instalado ou disponível")]
            },
            "emulators": rows,
            "games": []
        }
    }

    function attentionCount(rows) {
        return rows.filter(function(row) {
            return ["attention", "unsupported", "blocked", "missing"].indexOf(row.state) >= 0
        }).length
    }

    function readyCount(rows) {
        return rows.filter(function(row) {
            return ["installed", "available", "running"].indexOf(row.state) >= 0
        }).length
    }

    function stateColor(state) {
        if (["installed", "available", "running", "healthy"].indexOf(state) >= 0)
            return greenColor
        if (["attention", "unsupported", "blocked", "missing"].indexOf(state) >= 0)
            return amberColor
        if (state === "failed")
            return redColor
        return mutedColor
    }

    function stateIcon(state) {
        if (["installed", "available", "running", "healthy"].indexOf(state) >= 0)
            return "dialog-ok-apply"
        if (["attention", "unsupported", "blocked", "missing"].indexOf(state) >= 0)
            return "dialog-warning"
        if (state === "failed")
            return "dialog-error"
        return "dialog-information"
    }

    function truthStateLabel(state) {
        if (state === "ready" || state === "applied")
            return qsTr("pronto")
        if (state === "degraded")
            return qsTr("degradado")
        if (state === "stale")
            return qsTr("desatualizado")
        if (state === "unapplied")
            return qsTr("não aplicado")
        return qsTr("desconhecido")
    }

    function brandAsset(iconName) {
        const assets = {
            "dolphin-emu": "../assets/dolphin-emu.svg",
            "duckstation": "../assets/duckstation.svg",
            "retroarch": "../assets/retroarch.svg",
            "steam": "../assets/steam.svg"
        }
        return assets[iconName] || ""
    }

    function commandPreview(plan) {
        if (!plan || !plan.action || !plan.action.commands)
            return ""
        return plan.action.commands.map(function(command) { return command.join(" ") }).join("\n")
    }

    function deviceSummary() {
        const context = desktopStatus.context || {}
        const parts = []
        parts.push(context.deviceKind && context.deviceKind.indexOf("deck-") === 0 ? "Deck LCD" : "Linux")
        const displays = context.displays || []
        const external = displays.find(function(display) { return display.connected && !display.internal })
        if (external)
            parts.push(qsTr("Monitor %1 conectado").arg(external.name))
        parts.push(qsTr("Modo Desktop"))
        return parts.join("  •  ")
    }

    function performRowAction(row) {
        if (!row || !row.action || !row.action.enabled)
            return
        const kind = row.action.kind
        if (kind === "component-plan") {
            requestAction("component.plan", {"componentId": row.id}, function(response) {
                componentPlan = response.plan
                componentDialog.open()
            })
        } else if (kind === "component-launch") {
            requestAction("component.launch", {"componentId": row.id}, function(response) {
                notify(qsTr("%1 foi aberto").arg(row.name), false)
            })
        } else if (kind === "steam-open") {
            requestAction("steam.open", {"target": row.action.target}, function(response) {
                notify(qsTr("Steam aberto com segurança"), false)
                refreshStatus("")
            })
        } else if (kind === "keyboard") {
            openKeyboard()
        }
    }

    function performEmulationAction(action) {
        if (!action || action.enabled !== true) {
            notify(action && action.reason
                ? action.reason : qsTr("Esta ação de emulação ainda não está disponível."), true)
            return
        }
        if (action.id === "emulation.refresh" || action.id === "requirements.verify") {
            refreshStatus(qsTr("Ambiente de emulação verificado"))
            return
        }
        if (action.id === "open-credential-dialog") {
            credentialDialog.refresh()
            credentialDialog.open()
            return
        }
        if (action.id === "library.scan") {
            requestAction("library.scan", {}, function(response) {
                refreshStatus(qsTr("Biblioteca atualizada: %1 jogo(s)").arg(response.games))
            })
            return
        }
        if (action.id.indexOf("emulator.launch:") === 0) {
            const emulatorId = action.id.split(":")[1]
            requestAction("emulator.launch", {"emulatorId": emulatorId},
                    function(response) {
                notify(qsTr("Emulador aberto"), false)
            })
            return
        }
        if (action.id.indexOf("game.launch:") === 0) {
            const gameId = action.id.split(":")[1]
            requestAction("game.launch", {"gameId": gameId},
                    function(response) {
                notify(qsTr("Jogo iniciado com %1").arg(response.emulatorId), false)
            })
            return
        }
        if (action.id.indexOf("emulator.stop:") === 0) {
            const emulatorId = action.id.split(":")[1]
            requestAction("emulator.stop", {"emulatorId": emulatorId},
                    function() {
                refreshStatus(qsTr("Emulador encerrado"))
            })
            return
        }
        if (action.id.indexOf("emulator.install:") === 0
                || action.id.indexOf("emulator.update:") === 0
                || action.id.indexOf("emulator.uninstall:") === 0) {
            const parts = action.id.split(":")
            const lifecycleAction = parts[0].split(".")[1]
            requestAction("emulator.plan", {
                "emulatorId": parts[1], "action": lifecycleAction
            }, function(response) {
                emulationPlan = response.plan
                emulationDialog.open()
            })
            return
        }
        if (["library.root.add", "keys.import", "keys.repair", "firmware.import", "nsz.install", "nsz.convert",
                "content.update.import", "content.dlc.import", "content.save.import",
                "content.shader.import", "storage.recover", "game.emulator.set",
                "mod.import", "cheat.import",
                "game.steam.set", "steam.shortcuts.sync"]            .indexOf(action.id) >= 0
                || action.id.indexOf("content.state:") === 0
                || action.id.indexOf("mod.state:") === 0
                || action.id.indexOf("mod.remove:") === 0
                || action.id.indexOf("cheat.state:") === 0
                || action.id.indexOf("cheat.remove:") === 0
                || action.id.indexOf("game.delete:") === 0
                || action.id.indexOf("game.media.search:") === 0
                || action.id.indexOf("game.media.import:") === 0
                || action.id.indexOf("game.media.select:") === 0
                || action.id.indexOf("game.media.clear:") === 0
                || action.id.indexOf("game.media.publish-steam:") === 0
                || action.id.indexOf("game.media.unpublish-steam:") === 0
                || action.id.indexOf("media.") === 0
                || action.id.indexOf("library.root.") === 0
                || action.id.indexOf("game.save.") === 0
                || action.id.indexOf("game.shader.") === 0
                || action.id === "game.emulator.default"
                || action.id === "game.emulator.clear_default"
                || action.id === "emulation.global.set-auto-publish-steam"
                || action.id === "emulation.global.set-prefer-native-nca") {
            const payload = {
                "actionId": action.id,
                "path": action.path || "",
                "titleId": action.titleId || "",
                "emulatorId": action.emulatorId || "",
                "version": action.version || "",
                "gameId": action.gameId || (action.id.indexOf("game.delete:") === 0
                    ? action.id.split(":")[1] : ""),
                "selected": action.selected === true,
                "value": action.value === true,
                "overwrite": action.overwrite === true,
                "approvedPaths": action.approvedPaths || [],
                "steamUserId": action.steamUserId || "",
                "mediaKinds": action.mediaKinds || []
            }
            requestAction("emulation.action.plan", payload, function(response) {
                emulationPage.setActionMessage(action.id, "")
                emulationPlan = response.plan
                emulationDialog.open()
            }, function(message) {
                emulationPage.setActionMessage(action.id, message)
            })
            return
        }
        notify(action.reason || qsTr("Ação de emulação não reconhecida; nada foi alterado."), true)
    }

    function beginConflictResolution() {
        if (!desktopStatus.conflictActions || desktopStatus.conflictActions.length === 0) {
            notify(qsTr("Este conflito não possui correção automática allowlisted"), true)
            return
        }
        const action = desktopStatus.conflictActions[0]
        requestAction("desktop.conflict.plan", {"actionId": action.actionId}, function(response) {
            conflictPlan = response.plan
            conflictDialog.open()
        })
    }

    property var gamemodePlan: null

    function beginGamemodeReturn() {
        requestAction("session.select", {"target": "steam"}, function(response) {
            gamemodePlan = response
            gamemodeDialog.open()
        })
    }

    function beginQuickReset() {
        requestAction("desktop.profile.plan", {"profile": "safe"}, function(response) {
            currentPlan = response.plan
            resetDialog.open()
        })
    }

    function beginLsfgInstall() {
        requestAction("lsfg.plan", {}, function(response) {
            lsfgPlan = response.plan
            lsfgDialog.open()
        })
    }

    function openKeyboard(language) {
        keyboardRequested(language || "")
        requestAction("keyboard.toggle", {"action": "toggle", "language": language || ""}, function(response) {
            keyboardVisible = response.action === "show"
            notify(qsTr("Teclado %1 por %2").arg(
                keyboardVisible ? qsTr("aberto") : qsTr("fechado")
            ).arg(response.provider || "steamzero"), false)
        })
    }

    Component.onCompleted: parseArguments()

    Timer {
        id: feedbackTimer
        interval: root.lastRequestIsError ? 10000 : 5000
        onTriggered: root.lastRequest = ""
    }

    Dialog {
        id: conflictDialog
        onAboutToShow: root.rememberDialogInvoker()
        onClosed: root.restoreDialogFocus()
        title: qsTr("Resolver conflito de controle")
        modal: true
        width: Math.min(root.width - 48, 720)
        x: (root.width - width) / 2
        y: (root.height - height) / 2
        standardButtons: Dialog.NoButton

        background: Rectangle { color: root.raisedColor; radius: 12; border.color: root.amberColor }
        contentItem: ColumnLayout {
            spacing: 14
            Label {
                text: qsTr("O SteamZero continuará em modo observador até o watcher deixar de controlar display e entrada.")
                color: root.textColor
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Label {
                text: root.conflictPlan ? root.conflictPlan.action.unit : ""
                color: root.amberColor
                font.bold: true
                wrapMode: Text.WrapAnywhere
                Layout.fillWidth: true
                Accessible.name: qsTr("Serviço conflitante: %1").arg(text)
            }
            TextArea {
                text: root.commandPreview(root.conflictPlan)
                readOnly: true
                selectByMouse: true
                wrapMode: TextEdit.WrapAnywhere
                color: root.textColor
                background: Rectangle { color: root.backgroundColor; radius: 8; border.color: root.borderColor }
                Layout.fillWidth: true
                Layout.minimumHeight: 96
                Accessible.name: qsTr("Comandos exatos que serão executados")
            }
            Label {
                text: qsTr("Se uma etapa falhar, o estado anterior será restaurado.")
                color: root.mutedColor
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            RowLayout {
                Layout.fillWidth: true
                Button {
                    text: qsTr("Cancelar")
                    Layout.fillWidth: true
                    Layout.minimumHeight: 48
                    Accessible.name: text
                    onClicked: conflictDialog.close()
                }
                Button {
                    text: qsTr("Desativar e verificar novamente")
                    Layout.fillWidth: true
                    Layout.minimumHeight: 48
                    Accessible.name: text
                    onClicked: {
                        if (!root.conflictPlan)
                            return
                        root.requestAction("desktop.conflict.apply", {
                            "planId": root.conflictPlan.planId,
                            "confirmToken": root.conflictPlan.confirmToken
                        }, function(response) {
                            root.conflictPlan = null
                            conflictDialog.close()
                            root.refreshStatus(qsTr("Serviço conflitante desativado; Desktop liberado"))
                        })
                    }
                }
            }
        }
    }

    Dialog {
        id: componentDialog
        onAboutToShow: root.rememberDialogInvoker()
        onClosed: root.restoreDialogFocus()
        title: root.componentPlan
            ? (root.componentPlan.action === "install" ? qsTr("Revisar instalação") : qsTr("Revisar atualização"))
            : qsTr("Revisar componente")
        modal: true
        width: Math.min(root.width - 48, 720)
        x: (root.width - width) / 2
        y: (root.height - height) / 2
        standardButtons: Dialog.NoButton
        background: Rectangle { color: root.raisedColor; radius: 12; border.color: root.cyanDarkColor }
        contentItem: ColumnLayout {
            spacing: 14
            Label {
                text: qsTr("O plano usa Flatpak do usuário, commit pinado, verificação e rollback.")
                color: root.textColor
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            TextArea {
                text: root.componentPlan ? root.componentPlan.preview : ""
                readOnly: true
                selectByMouse: true
                wrapMode: TextEdit.WrapAnywhere
                color: root.textColor
                background: Rectangle { color: root.backgroundColor; radius: 8; border.color: root.borderColor }
                Layout.fillWidth: true
                Layout.minimumHeight: 132
                Accessible.name: qsTr("Prévia da operação")
            }
            RowLayout {
                Layout.fillWidth: true
                Button {
                    text: qsTr("Cancelar")
                    Layout.fillWidth: true
                    Layout.minimumHeight: 48
                    Accessible.name: text
                    onClicked: componentDialog.close()
                }
                Button {
                    text: root.componentPlan && root.componentPlan.action === "install"
                        ? qsTr("Instalar com rollback") : qsTr("Aplicar atualização")
                    Layout.fillWidth: true
                    Layout.minimumHeight: 48
                    Accessible.name: text
                    onClicked: {
                        if (!root.componentPlan)
                            return
                        root.requestAction("component.apply", {
                            "planId": root.componentPlan.planId,
                            "confirmToken": root.componentPlan.confirmToken
                        }, function(response) {
                            componentDialog.close()
                            root.componentPlan = null
                            root.refreshStatus(qsTr("Componente verificado e pronto"))
                        })
                    }
                }
            }
        }
    }

    Dialog {
        id: emulationDialog
        onAboutToShow: root.rememberDialogInvoker()
        onClosed: {
            auditSelections = []
            root.restoreDialogFocus()
        }
        property var auditSelections: []

        function auditItems() {
            if (!root.emulationPlan || !root.emulationPlan.auditPreview
                    || root.emulationPlan.quarantineId)
                return []
            const categories = root.emulationPlan.auditPreview.categories || {}
            const result = []
            const selectable = ["duplicate", "incompatible", "corrupted", "unknown"]
            for (let categoryIndex = 0; categoryIndex < selectable.length; categoryIndex++) {
                const category = selectable[categoryIndex]
                const items = categories[category] || []
                for (let itemIndex = 0; itemIndex < items.length; itemIndex++) {
                    result.push({
                        "relativePath": items[itemIndex].relativePath,
                        "category": category,
                        "sizeBytes": items[itemIndex].sizeBytes || 0
                    })
                }
            }
            return result
        }

        function setAuditSelected(relativePath, selected) {
            const next = auditSelections.filter(function(value) {
                return value !== relativePath
            })
            if (selected)
                next.push(relativePath)
            auditSelections = next
        }

        function prepareQuarantine() {
            if (!root.emulationPlan || auditSelections.length === 0)
                return
            root.requestAction("emulation.action.plan", {
                "actionId": root.emulationPlan.action,
                "approvedPaths": auditSelections
            }, function(response) {
                root.emulationPlan = response.plan
                root.notify(qsTr("Quarentena preparada; revise os movimentos antes de aplicar."),
                            false)
            })
        }

        title: qsTr("Revisar operação de emulação")
        modal: true
        width: Math.min(root.width - 48, 720)
        height: Math.min(root.height - 48, 720)
        x: (root.width - width) / 2
        y: (root.height - height) / 2
        standardButtons: Dialog.NoButton
        background: Rectangle { color: root.raisedColor; radius: 12; border.color: root.cyanDarkColor }
        contentItem: ColumnLayout {
            spacing: 14
            Label {
                text: qsTr("Confira a origem, os arquivos afetados e a garantia de rollback antes de aplicar.")
                color: root.textColor
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            ScrollView {
                id: emulationPreviewScroll
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumHeight: 150
                clip: true
                ScrollBar.horizontal.policy: ScrollBar.AsNeeded
                ScrollBar.vertical.policy: ScrollBar.AlwaysOn
                background: Rectangle {
                    color: root.backgroundColor
                    radius: 8
                    border.color: root.borderColor
                }
                Column {
                    width: emulationPreviewScroll.availableWidth
                    spacing: 8
                    TextArea {
                        width: parent.width
                        text: root.emulationPlan ? root.emulationPlan.preview : ""
                        readOnly: true
                        selectByMouse: true
                        wrapMode: TextEdit.WrapAnywhere
                        color: root.textColor
                        background: null
                        Accessible.name: qsTr("Prévia da operação de emulação")
                    }
                    Label {
                        width: parent.width
                        visible: emulationDialog.auditItems().length > 0
                        text: qsTr("Selecione apenas itens não jogáveis para mover à quarentena. Jogos base, updates e DLCs nunca são oferecidos aqui.")
                        color: root.amberColor
                        wrapMode: Text.WordWrap
                    }
                    Repeater {
                        model: emulationDialog.auditItems()
                        delegate: CheckBox {
                            required property var modelData
                            width: parent.width
                            implicitHeight: Math.max(48, contentItem.implicitHeight + 12)
                            text: qsTr("%1 · %2 · %3 bytes")
                                .arg(modelData.category)
                                .arg(modelData.relativePath)
                                .arg(modelData.sizeBytes)
                            onToggled: emulationDialog.setAuditSelected(
                                modelData.relativePath, checked)
                            Accessible.name: text
                        }
                    }
                }
            }
            RowLayout {
                Layout.fillWidth: true
                Button {
                    text: qsTr("Cancelar")
                    Layout.fillWidth: true
                    Layout.minimumHeight: 48
                    onClicked: {
                        emulationPage.cancelPendingEmulatorSelection()
                        root.emulationPlan = null
                        emulationDialog.close()
                    }
                }
                Button {
                    visible: root.emulationPlan
                        && root.emulationPlan.auditPreview
                        && !root.emulationPlan.quarantineId
                    text: qsTr("Preparar quarentena (%1)")
                        .arg(emulationDialog.auditSelections.length)
                    enabled: emulationDialog.auditSelections.length > 0
                    Layout.fillWidth: true
                    Layout.minimumHeight: 48
                    onClicked: emulationDialog.prepareQuarantine()
                }
                Button {
                    text: qsTr("Aplicar com rollback")
                    Layout.fillWidth: true
                    Layout.minimumHeight: 48
                    onClicked: {
                        if (!root.emulationPlan)
                            return
                        const emulatorLifecycle = String(root.emulationPlan.action)
                            .indexOf("emulator.") === 0
                        const actionId = emulatorLifecycle
                            ? "emulator.apply" : "emulation.action.apply"
                        root.requestAction(actionId, {
                            "planId": root.emulationPlan.planId,
                            "confirmToken": root.emulationPlan.confirmToken
                        }, function(response) {
                            emulationDialog.close()
                            root.emulationPlan = null
                            root.refreshStatus(qsTr("Operação aplicada e verificada"))
                        })
                    }
                }
            }
        }
    }

    Dialog {
        id: gamemodeDialog
        onAboutToShow: root.rememberDialogInvoker()
        onClosed: root.restoreDialogFocus()
        title: qsTr("Voltar ao Game Mode")
        modal: true
        width: Math.min(root.width - 48, 620)
        x: (root.width - width) / 2
        y: (root.height - height) / 2
        standardButtons: Dialog.NoButton
        background: Rectangle { color: root.raisedColor; radius: 12; border.color: root.amberColor }
        contentItem: ColumnLayout {
            spacing: 14
            Label {
                text: qsTr("A sessão desktop será encerrada e o dispositivo volta ao Game Mode. Salve o que estiver aberto antes de confirmar.")
                color: root.textColor
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            RowLayout {
                Layout.fillWidth: true
                Button {
                    text: qsTr("Cancelar")
                    Layout.fillWidth: true
                    Layout.minimumHeight: 48
                    Accessible.name: text
                    onClicked: gamemodeDialog.close()
                }
                Button {
                    text: qsTr("Encerrar e voltar ao Game Mode")
                    Layout.fillWidth: true
                    Layout.minimumHeight: 48
                    enabled: root.gamemodePlan !== null
                    Accessible.name: text
                    onClicked: {
                        root.requestAction("session.select", {
                            "target": root.gamemodePlan.target,
                            "planId": root.gamemodePlan.planId,
                            "confirmToken": root.gamemodePlan.confirmToken
                        }, function(response) {
                            gamemodeDialog.close()
                            root.notify(qsTr("Encerrando sessão desktop..."), false)
                        })
                    }
                }
            }
        }
    }

    Dialog {
        id: resetDialog
        onAboutToShow: root.rememberDialogInvoker()
        onClosed: root.restoreDialogFocus()
        title: qsTr("Quick Reset")
        modal: true
        width: Math.min(root.width - 48, 620)
        x: (root.width - width) / 2
        y: (root.height - height) / 2
        standardButtons: Dialog.NoButton
        background: Rectangle { color: root.raisedColor; radius: 12; border.color: root.amberColor }
        contentItem: ColumnLayout {
            spacing: 14
            Label {
                text: qsTr("Restaura somente o perfil Desktop seguro. Jogos, saves, BIOS e configurações dos emuladores não são apagados.")
                color: root.textColor
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Label {
                text: root.currentPlan ? root.currentPlan.changes.join("\n") : ""
                color: root.mutedColor
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            RowLayout {
                Layout.fillWidth: true
                Button {
                    text: qsTr("Cancelar")
                    Layout.fillWidth: true
                    Layout.minimumHeight: 48
                    Accessible.name: text
                    onClicked: resetDialog.close()
                }
                Button {
                    text: qsTr("Restaurar perfil seguro")
                    Layout.fillWidth: true
                    Layout.minimumHeight: 48
                    enabled: root.currentPlan !== null && root.currentPlan.blockers.length === 0
                    Accessible.name: text
                    onClicked: {
                        root.requestAction("desktop.profile.reset", {
                            "planId": root.currentPlan.planId,
                            "confirmToken": root.currentPlan.confirmToken
                        }, function(response) {
                            resetDialog.close()
                            root.refreshStatus(qsTr("Quick Reset concluído"))
                        })
                    }
                }
            }
        }
    }

    Dialog {
        id: lsfgDialog
        onAboutToShow: root.rememberDialogInvoker()
        onClosed: root.restoreDialogFocus()
        title: qsTr("Preparar LSFG-VK")
        modal: true
        width: Math.min(root.width - 48, 720)
        x: (root.width - width) / 2
        y: (root.height - height) / 2
        standardButtons: Dialog.NoButton
        background: Rectangle {
            color: root.raisedColor
            radius: 12
            border.color: root.cyanColor
            border.width: 2
        }
        contentItem: ColumnLayout {
            spacing: 14
            Label {
                text: qsTr("Instalação no usuário, sem sudo, usando somente o release oficial pinado.")
                color: root.textColor
                font.pixelSize: 17
                font.bold: true
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            RowLayout {
                Layout.fillWidth: true
                Label { text: qsTr("Versão"); color: root.mutedColor; Layout.preferredWidth: 100 }
                Label { text: root.lsfgPlan ? root.lsfgPlan.version : "—"; color: root.textColor; font.bold: true }
                Item { Layout.fillWidth: true }
                Label { text: "G-FULL"; color: root.greenColor; font.bold: true }
            }
            TextArea {
                text: root.lsfgPlan ? root.lsfgPlan.changes.join("\n") : ""
                readOnly: true
                selectByMouse: true
                wrapMode: TextEdit.WrapAnywhere
                color: root.textColor
                background: Rectangle {
                    color: root.backgroundColor
                    radius: 8
                    border.color: root.borderColor
                }
                Layout.fillWidth: true
                Layout.minimumHeight: 104
                Accessible.name: qsTr("Arquivos que serão instalados")
            }
            Label {
                text: root.lsfgPlan
                    ? qsTr("SHA-256 do arquivo: %1").arg(root.lsfgPlan.sha256)
                    : ""
                color: root.mutedColor
                font.family: "monospace"
                font.pixelSize: 11
                wrapMode: Text.WrapAnywhere
                Layout.fillWidth: true
            }
            Label {
                text: qsTr("Lossless Scaling continua sendo fornecido pela Steam e não é copiado pelo SteamZero.")
                color: root.amberColor
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            RowLayout {
                Layout.fillWidth: true
                Button {
                    text: qsTr("Cancelar")
                    Layout.fillWidth: true
                    Layout.minimumHeight: 48
                    Accessible.name: text
                    onClicked: lsfgDialog.close()
                }
                Button {
                    text: qsTr("Instalar e verificar")
                    Layout.fillWidth: true
                    Layout.minimumHeight: 48
                    Accessible.name: text
                    onClicked: {
                        if (!root.lsfgPlan)
                            return
                        root.requestAction("lsfg.apply", {
                            "planId": root.lsfgPlan.planId,
                            "confirmToken": root.lsfgPlan.confirmToken
                        }, function(response) {
                            root.lsfgLastOperationId = response.operationId || ""
                            root.lsfgPlan = null
                            lsfgDialog.close()
                            root.refreshStatus(response.message || qsTr("LSFG-VK preparado"))
                        })
                    }
                }
            }
        }
    }

    Dialog {
        id: credentialDialog
        onAboutToShow: root.rememberDialogInvoker()
        onClosed: root.restoreDialogFocus()
        title: qsTr("Credenciais de scraping")
        modal: true
        closePolicy: Popup.CloseOnEscape
        width: Math.min(root.width - 48, 500)
        height: Math.min(root.height - 32, 620)
        x: (root.width - width) / 2
        y: (root.height - height) / 2
        standardButtons: Dialog.NoButton
        focus: true
        background: Rectangle { color: root.raisedColor; radius: 12; border.color: root.borderColor; border.width: 1 }
        property var providers: []

        function moveFocus(forward) {
            const active = root.activeFocusItem
            const next = active ? active.nextItemInFocusChain(forward) : null
            if (next) {
                next.forceActiveFocus(Qt.TabFocusReason)
                Qt.callLater(function() { root.ensureFocusedItemVisible(next) })
            }
        }

        function closeFromBack() {
            close()
        }

        Keys.onUpPressed: function(event) {
            credentialDialog.moveFocus(false)
            event.accepted = true
        }
        Keys.onDownPressed: function(event) {
            credentialDialog.moveFocus(true)
            event.accepted = true
        }
        Keys.onEscapePressed: function(event) {
            credentialDialog.closeFromBack()
            event.accepted = true
        }
        Keys.onPressed: function(event) {
            if (event.key === Qt.Key_Back) {
                credentialDialog.closeFromBack()
                event.accepted = true
            }
        }

        function refresh() {
            root.requestAction("credential.status", {}, function(resp) {
                credentialDialog.providers = resp.providers || []
            })
        }

        contentItem: ScrollView {
            id: credentialScroll
            clip: true
            contentWidth: availableWidth
            ColumnLayout {
                width: credentialScroll.availableWidth
                spacing: 12
            Label {
                text: qsTr("Configure as chaves de API dos provedores de scraping para buscar capas e mídia automaticamente.")
                color: root.textColor
                font.pixelSize: 13
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Repeater {
                id: credentialProviderRepeater
                model: credentialDialog.providers.filter(function(provider) {
                    return provider.id !== "steam-web-api"
                        && (provider.enabled || provider.id === "steam-local")
                })
                delegate: CredentialProviderCard {
                    id: providerCard
                    required property var modelData
                    provider: modelData
                    Layout.fillWidth: true
                    surfaceColor: root.surfaceColor
                    raisedColor: root.raisedColor
                    borderColor: root.borderColor
                    textColor: root.textColor
                    mutedColor: root.mutedColor
                    cyanColor: root.cyanColor
                    greenColor: root.greenColor
                    amberColor: root.amberColor
                    redColor: root.redColor
                    onSaveRequested: function(providerId, credentials) {
                        root.requestAction("credential.save", {
                            "provider": providerId,
                            "credentials": credentials
                        }, function(resp) {
                            providerCard.saveSucceeded(resp)
                        }, function(errMsg) {
                            providerCard.saveFailed(errMsg)
                        })
                    }
                    onTestRequested: function(providerId) {
                        root.requestAction("credential.test", {
                            "provider": providerId
                        }, function(resp) {
                            providerCard.testSucceeded(resp)
                        }, function(errMsg) {
                            providerCard.actionFailed(errMsg)
                        })
                    }
                    onRevokeRequested: function(providerId) {
                        root.requestAction("credential.delete", {
                            "provider": providerId
                        }, function(resp) {
                            providerCard.revokeSucceeded(resp)
                        }, function(errMsg) {
                            providerCard.actionFailed(errMsg)
                        })
                    }
                    onLinkRequested: function(providerId, linkKey) {
                        root.requestAction("provider.link", {
                            "provider": providerId,
                            "link": linkKey
                        }, function(resp) {
                            if (resp.opened) {
                                providerCard.messageIsError = false
                                providerCard.message = qsTr("Link aberto no navegador.")
                            } else {
                                providerCard.actionFailed(
                                    qsTr("O navegador não confirmou a abertura."))
                            }
                        }, function(errMsg) {
                            providerCard.actionFailed(errMsg)
                        })
                    }
                    onKeyboardRequested: function(fieldId) {
                        root.openKeyboard()
                    }
                }
            }
            Label {
                text: qsTr("Opcional — Steam Web API")
                color: root.textColor
                font.bold: true
                font.pixelSize: 13
                Layout.fillWidth: true
            }
            Label {
                text: qsTr("Não é necessária para atalhos nem para artes locais da Steam.")
                color: root.mutedColor
                font.pixelSize: 11
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Repeater {
                model: credentialDialog.providers.filter(function(provider) {
                    return provider.id === "steam-web-api"
                })
                delegate: CredentialProviderCard {
                    required property var modelData
                    provider: modelData
                    Layout.fillWidth: true
                    surfaceColor: root.surfaceColor
                    raisedColor: root.raisedColor
                    borderColor: root.borderColor
                    textColor: root.textColor
                    mutedColor: root.mutedColor
                    cyanColor: root.cyanColor
                    greenColor: root.greenColor
                    amberColor: root.amberColor
                    redColor: root.redColor
                    onKeyboardRequested: function(fieldId) {
                        root.openKeyboard()
                    }
                }
            }
            Button {
                id: credentialCloseButton
                Layout.fillWidth: true
                Layout.minimumHeight: 48
                text: qsTr("Fechar")
                palette.button: root.raisedColor
                palette.buttonText: root.textColor
                onClicked: credentialDialog.close()
            }
            }
        }
    }

    Dialog {
        id: recoveryDialog
        onAboutToShow: root.rememberDialogInvoker()
        onClosed: root.restoreDialogFocus()
        title: qsTr("Alteração incompleta detectada")
        modal: true
        closePolicy: Popup.NoAutoClose
        width: Math.min(root.width - 48, 650)
        x: (root.width - width) / 2
        y: (root.height - height) / 2
        standardButtons: Dialog.NoButton
        background: Rectangle { color: root.raisedColor; radius: 12; border.color: root.amberColor; border.width: 2 }
        contentItem: ColumnLayout {
            spacing: 16
            Label {
                text: qsTr("Detectamos uma tentativa incompleta de alteração de perfil. Restaure o último estado seguro antes de continuar.")
                color: root.textColor
                font.pixelSize: 18
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Button {
                text: qsTr("Restaurar último estado seguro")
                Layout.fillWidth: true
                Layout.minimumHeight: 52
                Accessible.name: text
                onClicked: {
                    root.recoveryRequested()
                    root.requestAction("desktop.recover", {}, function(response) {
                        recoveryDialog.close()
                        root.refreshStatus(qsTr("Recuperação concluída com segurança"))
                    })
                }
            }
        }
    }

    FileDialog {
        id: diagnosticsExportDialog
        title: root.diagnosticsKind === "support"
            ? qsTr("Salvar pacote de suporte sanitizado")
            : qsTr("Salvar estado sanitizado")
        fileMode: FileDialog.SaveFile
        nameFilters: root.diagnosticsKind === "support"
            ? [qsTr("Pacote ZIP (*.zip)")]
            : [qsTr("Documento JSON (*.json)")]
        defaultSuffix: root.diagnosticsKind === "support" ? "zip" : "json"
        onAccepted: {
            const destination = root.localPath(selectedFile)
            const contract = root.diagnosticsKind === "support"
                ? "support.bundle" : "state.export"
            root.requestAction(contract, {
                "destination": destination,
                "kind": root.diagnosticsKind
            }, function(response) {
                root.diagnosticsPlan = response.plan
                root.diagnosticsPreview = response.contentPreview || ({})
                diagnosticsPreviewDialog.open()
            })
        }
    }

    Dialog {
        id: diagnosticsPreviewDialog
        onAboutToShow: root.rememberDialogInvoker()
        onClosed: root.restoreDialogFocus()
        title: qsTr("Revisar conteúdo antes de exportar")
        modal: true
        width: Math.min(root.width - 48, 760)
        height: Math.min(root.height - 48, 620)
        x: (root.width - width) / 2
        y: (root.height - height) / 2
        standardButtons: Dialog.NoButton
        background: Rectangle {
            color: root.raisedColor
            radius: 12
            border.color: root.cyanDarkColor
        }
        contentItem: ColumnLayout {
            spacing: 12
            Label {
                text: qsTr("Arquivos: %1").arg(
                    (root.diagnosticsPreview.files || []).join(", "))
                color: root.textColor
                font.bold: true
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                TextArea {
                    readOnly: true
                    text: JSON.stringify(root.diagnosticsPreview.content || {}, null, 2)
                    color: root.textColor
                    background: Rectangle { color: root.backgroundColor; radius: 6 }
                    wrapMode: TextEdit.WrapAnywhere
                    Accessible.name: qsTr("Preview integral da exportação sanitizada")
                }
            }
            RowLayout {
                Layout.fillWidth: true
                Button {
                    text: qsTr("Cancelar")
                    Layout.fillWidth: true
                    Layout.minimumHeight: 48
                    onClicked: diagnosticsPreviewDialog.close()
                }
                Button {
                    text: qsTr("Confirmar exportação")
                    Layout.fillWidth: true
                    Layout.minimumHeight: 48
                    enabled: root.diagnosticsPlan !== null
                    onClicked: root.requestAction("diagnostics.export.apply", {
                        "planId": root.diagnosticsPlan.planId,
                        "confirmToken": root.diagnosticsPlan.confirmToken
                    }, function(response) {
                        diagnosticsPreviewDialog.close()
                        root.diagnosticsPlan = null
                        root.notify(qsTr("Exportação sanitizada concluída"), false)
                        root.refreshStatus("")
                    })
                }
            }
        }
    }

    Drawer {
        id: navigationDrawer
        edge: Qt.LeftEdge
        modal: true
        interactive: root.compactLayout
        width: Math.min(336, root.width * 0.82)
        height: root.height
        dim: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        Accessible.name: qsTr("Navegação principal")
        onOpened: {
            const current = drawerNavRepeater.itemAt(root.sectionIndex)
            if (current)
                current.forceActiveFocus(Qt.PopupFocusReason)
        }
        onClosed: navigationMenuButton.forceActiveFocus(Qt.PopupFocusReason)

        enter: Transition {
            NumberAnimation { property: "position"; duration: root.motionDuration; easing.type: Easing.OutCubic }
        }
        exit: Transition {
            NumberAnimation { property: "position"; duration: root.motionDuration; easing.type: Easing.InCubic }
        }
        background: Rectangle {
            color: root.sidebarColor
            border.color: root.borderColor
        }
        contentItem: ColumnLayout {
            spacing: 8
            anchors.margins: 12

            RowLayout {
                Layout.fillWidth: true
                Layout.minimumHeight: 56
                Image {
                    source: "../assets/steamzero-mark.png"
                    sourceSize.width: 40
                    sourceSize.height: 40
                    Layout.preferredWidth: 40
                    Layout.preferredHeight: 40
                    fillMode: Image.PreserveAspectFit
                    Accessible.name: qsTr("Marca SteamZero")
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    Label { text: "STEAMZERO"; color: root.textColor; font.bold: true; font.pixelSize: 17 }
                    Label {
                        text: qsTr("%1 · %2").arg(root.sectionLabel(root.sectionIndex)).arg(root.deviceSummary())
                        color: root.mutedColor
                        font.pixelSize: 11
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                }
                Button {
                    text: qsTr("Fechar")
                    Layout.minimumWidth: 48
                    Layout.minimumHeight: 48
                    Accessible.name: qsTr("Fechar navegação")
                    onClicked: navigationDrawer.close()
                }
            }

            Rectangle { color: root.borderColor; Layout.fillWidth: true; Layout.preferredHeight: 1 }

            Repeater {
                id: drawerNavRepeater
                model: [
                    {"label": qsTr("Visão geral"), "icon": "view-dashboard"},
                    {"label": qsTr("Emulação"), "icon": "input-gaming"},
                    {"label": qsTr("Steam"), "icon": "steam"},
                    {"label": qsTr("Perfis"), "icon": "preferences-system"},
                    {"label": qsTr("Saves e Sync"), "icon": "folder-sync"},
                    {"label": qsTr("Sistema"), "icon": "configure"}
                ]
                delegate: Button {
                    required property int index
                    required property var modelData
                    text: modelData.label
                    icon.name: modelData.icon
                    icon.color: root.sectionIndex === index ? root.cyanColor : root.mutedColor
                    display: AbstractButton.TextBesideIcon
                    Layout.fillWidth: true
                    Layout.minimumHeight: 52
                    Accessible.name: text
                    Accessible.description: root.sectionIndex === index
                        ? qsTr("Seção atual") : qsTr("Abrir seção")
                    KeyNavigation.up: index > 0
                        ? drawerNavRepeater.itemAt(index - 1) : drawerNavRepeater.itemAt(drawerNavRepeater.count - 1)
                    KeyNavigation.down: index + 1 < drawerNavRepeater.count
                        ? drawerNavRepeater.itemAt(index + 1) : drawerNavRepeater.itemAt(0)
                    onClicked: {
                        root.sectionIndex = index
                        navigationDrawer.close()
                    }
                    background: Rectangle {
                        color: root.sectionIndex === parent.index ? "#183044" : root.surfaceColor
                        radius: 8
                        border.color: parent.activeFocus || root.sectionIndex === parent.index
                            ? root.cyanColor : root.borderColor
                        border.width: parent.activeFocus ? 2 : 1
                    }
                }
            }

            Item { Layout.fillHeight: true }

            Label {
                text: qsTr("O contexto da seção e os filtros atuais são preservados.")
                color: root.mutedColor
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
                font.pixelSize: 11
            }
        }
    }

    Drawer {
        id: taskDrawer
        edge: Qt.RightEdge
        modal: true
        interactive: true
        width: Math.min(460, root.width * 0.94)
        height: root.height
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        Accessible.name: qsTr("Central de tarefas")
        onOpened: {
            root.refreshTasks()
            Qt.callLater(function() { taskCloseButton.forceActiveFocus(Qt.PopupFocusReason) })
        }
        onClosed: {
            if (root.compactLayout)
                compactTaskButton.forceActiveFocus(Qt.PopupFocusReason)
            else
                desktopTaskButton.forceActiveFocus(Qt.PopupFocusReason)
        }

        enter: Transition {
            NumberAnimation { property: "position"; duration: root.motionDuration; easing.type: Easing.OutCubic }
        }
        exit: Transition {
            NumberAnimation { property: "position"; duration: root.motionDuration; easing.type: Easing.InCubic }
        }
        background: Rectangle { color: root.sidebarColor; border.color: root.borderColor }
        contentItem: ColumnLayout {
            spacing: 10

            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 12
                Layout.rightMargin: 12
                Layout.topMargin: 10
                Layout.minimumHeight: 54
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    Label { text: qsTr("Central de tarefas"); color: root.textColor; font.pixelSize: 19; font.bold: true }
                    Label {
                        text: root.activeTaskCount() > 0
                            ? qsTr("%1 ativa(s)").arg(root.activeTaskCount())
                            : qsTr("Nenhuma operação ativa")
                        color: root.activeTaskCount() > 0 ? root.cyanColor : root.mutedColor
                        font.pixelSize: 11
                    }
                }
                Button {
                    text: qsTr("Atualizar")
                    Layout.minimumHeight: 48
                    Accessible.name: text
                    onClicked: root.refreshTasks()
                }
                Button {
                    id: taskCloseButton
                    text: qsTr("Fechar")
                    Layout.minimumHeight: 48
                    Accessible.name: qsTr("Fechar central de tarefas")
                    onClicked: taskDrawer.close()
                }
            }

            Rectangle { color: root.borderColor; Layout.fillWidth: true; Layout.preferredHeight: 1 }

            ScrollView {
                id: taskScroll
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                contentWidth: availableWidth

                ColumnLayout {
                    width: taskScroll.availableWidth
                    spacing: 10

                    Rectangle {
                        visible: root.taskItems.length === 0
                        Layout.fillWidth: true
                        Layout.leftMargin: 12
                        Layout.rightMargin: 12
                        Layout.topMargin: 12
                        implicitHeight: 100
                        color: root.surfaceColor
                        border.color: root.borderColor
                        radius: 8
                        Column {
                            anchors.centerIn: parent
                            spacing: 5
                            Label { text: qsTr("Nenhuma tarefa registrada"); color: root.textColor; font.bold: true }
                            Label { text: qsTr("Varreduras e buscas aparecerão aqui."); color: root.mutedColor }
                        }
                    }

                    Repeater {
                        model: root.taskItems
                        delegate: Rectangle {
                            required property var modelData
                            Layout.fillWidth: true
                            Layout.leftMargin: 12
                            Layout.rightMargin: 12
                            Layout.topMargin: index === 0 ? 4 : 0
                            implicitHeight: taskContent.implicitHeight + 24
                            color: root.surfaceColor
                            border.color: modelData.state === "failed" ? root.redColor
                                : modelData.state === "running" ? root.cyanColor : root.borderColor
                            radius: 8

                            ColumnLayout {
                                id: taskContent
                                anchors.fill: parent
                                anchors.margins: 12
                                spacing: 7
                                RowLayout {
                                    Layout.fillWidth: true
                                    Label {
                                        text: root.taskLabel(modelData.type)
                                        color: root.textColor
                                        font.bold: true
                                        Layout.fillWidth: true
                                        elide: Text.ElideRight
                                    }
                                    Label {
                                        text: root.taskStateLabel(modelData.state)
                                        color: modelData.state === "failed" ? root.redColor
                                            : modelData.state === "succeeded" ? root.greenColor
                                            : modelData.state === "running" ? root.cyanColor : root.mutedColor
                                        font.bold: true
                                    }
                                }
                                ProgressBar {
                                    visible: modelData.state === "running" || modelData.state === "queued"
                                    from: 0
                                    to: 1
                                    value: root.taskProgress(modelData)
                                    indeterminate: modelData.state === "running" && value === 0
                                    Layout.fillWidth: true
                                    Accessible.name: qsTr("Progresso de %1").arg(root.taskLabel(modelData.type))
                                }
                                Label {
                                    text: root.taskResultSummary(modelData)
                                    color: root.mutedColor
                                    wrapMode: Text.WordWrap
                                    Layout.fillWidth: true
                                }
                                RowLayout {
                                    visible: modelData.canCancel || modelData.canRetry
                                    Layout.fillWidth: true
                                    Item { Layout.fillWidth: true }
                                    Button {
                                        visible: modelData.canCancel
                                        text: qsTr("Cancelar")
                                        Layout.minimumHeight: 48
                                        Accessible.name: qsTr("Cancelar %1").arg(root.taskLabel(modelData.type))
                                        onClicked: root.requestAction("job.cancel", {
                                            "jobId": modelData.jobId
                                        }, function() {
                                            root.refreshTasks()
                                            root.refreshStatus(qsTr("Cancelamento registrado"))
                                        })
                                    }
                                    Button {
                                        visible: modelData.canRetry
                                        text: qsTr("Tentar novamente")
                                        Layout.minimumHeight: 48
                                        Accessible.name: qsTr("Tentar novamente %1").arg(root.taskLabel(modelData.type))
                                        onClicked: root.requestAction("job.retry", {
                                            "jobId": modelData.jobId
                                        }, function() {
                                            root.refreshTasks()
                                            root.refreshStatus(qsTr("Nova tentativa concluída"))
                                        })
                                    }
                                }
                            }
                        }
                    }
                    Item { Layout.preferredHeight: 8 }
                }
            }
        }
    }

    Timer {
        id: taskRefreshTimer
        interval: 1500
        repeat: true
        running: taskDrawer.opened && root.activeTaskCount() > 0
        onTriggered: root.refreshTasks()
    }

    ColumnLayout {
        id: appShell
        anchors.fill: parent
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            Rectangle {
                id: sidebar
                visible: !root.compactLayout
                color: root.sidebarColor
                Layout.preferredWidth: visible ? root.navigationWidth : 0
                Layout.fillHeight: true
                border.color: root.borderColor
                border.width: 1

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: root.compactLayout ? 7 : 14
                    spacing: root.compactLayout ? 5 : 8

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.minimumHeight: root.compactLayout ? 54 : 72
                        Image {
                            source: "../assets/steamzero-mark.png"
                            sourceSize.width: root.compactLayout ? 40 : 48
                            sourceSize.height: root.compactLayout ? 40 : 48
                            fillMode: Image.PreserveAspectFit
                            Layout.preferredWidth: root.compactLayout ? 40 : 48
                            Layout.preferredHeight: root.compactLayout ? 40 : 48
                            Accessible.name: qsTr("Marca SteamZero")
                        }
                        ColumnLayout {
                            visible: !root.compactLayout
                            spacing: 0
                            Label {
                                text: "STEAMZERO"
                                color: root.textColor
                                font.pixelSize: root.width < 980 ? 16 : 19
                                font.bold: true
                            }
                            Label {
                                visible: root.width >= 980
                                text: qsTr("Central de jogos")
                                color: root.mutedColor
                                font.pixelSize: 13
                            }
                        }
                    }

                    Rectangle { color: root.borderColor; Layout.fillWidth: true; Layout.preferredHeight: 1 }

                    Repeater {
                        id: navRepeater
                        model: [
                            {"label": qsTr("Visão geral"), "icon": "view-dashboard"},
                            {"label": qsTr("Emulação"), "icon": "input-gaming"},
                            {"label": qsTr("Steam"), "icon": "steam"},
                            {"label": qsTr("Perfis"), "icon": "preferences-system"},
                            {"label": qsTr("Saves e Sync"), "icon": "folder-sync"},
                            {"label": qsTr("Sistema"), "icon": "configure"}
                        ]
                        delegate: Button {
                            required property int index
                            required property var modelData
                            text: modelData.label
                            icon.name: modelData.icon
                            icon.color: root.sectionIndex === index ? root.cyanColor : root.mutedColor
                            display: AbstractButton.TextBesideIcon
                            Layout.fillWidth: true
                            Layout.minimumHeight: root.compactLayout ? 48
                                : index === 2 && root.sectionIndex === 2 ? 70 : 48
                            leftPadding: root.compactLayout ? 5 : 14
                            rightPadding: root.compactLayout ? 5 : 12
                            spacing: root.compactLayout ? 0 : 12
                            Accessible.name: text
                            ToolTip.visible: root.compactLayout && hovered
                            ToolTip.text: modelData.label
                            KeyNavigation.up: index > 0 ? navRepeater.itemAt(index - 1) : quickResetButton
                            KeyNavigation.down: index + 1 < navRepeater.count
                                ? navRepeater.itemAt(index + 1) : attentionButton
                            onClicked: root.sectionIndex = index
                            background: Rectangle {
                                color: root.sectionIndex === parent.index ? "#183044" : "transparent"
                                radius: 7
                                border.color: parent.activeFocus ? root.cyanColor : "transparent"
                                border.width: parent.activeFocus ? 2 : 0
                                Rectangle {
                                    visible: root.sectionIndex === parent.parent.index
                                    width: 4
                                    anchors.left: parent.left
                                    anchors.top: parent.top
                                    anchors.bottom: parent.bottom
                                    color: root.cyanColor
                                    radius: 2
                                }
                            }
                            contentItem: RowLayout {
                                spacing: root.compactLayout ? 0 : 12
                                ToolButton {
                                    enabled: false
                                    icon.name: modelData.icon
                                    icon.color: root.sectionIndex === index ? root.cyanColor : root.mutedColor
                                    icon.width: 24
                                    icon.height: 24
                                    background: Item {}
                                    Layout.preferredWidth: 28
                                    Layout.alignment: Qt.AlignHCenter
                                }
                                ColumnLayout {
                                    visible: !root.compactLayout
                                    Layout.fillWidth: true
                                    spacing: 1
                                    Label {
                                        text: modelData.label
                                        color: root.sectionIndex === index ? root.cyanColor : root.textColor
                                        font.pixelSize: 15
                                        Layout.fillWidth: true
                                        elide: Text.ElideRight
                                    }
                                    Label {
                                        visible: index === 2 && root.sectionIndex === 2
                                        text: qsTr("Gameplay")
                                        color: root.cyanColor
                                        font.pixelSize: 12
                                    }
                                }
                            }
                        }
                    }

                    Button {
                        id: desktopTaskButton
                        text: root.activeTaskCount() > 0
                            ? qsTr("Tarefas · %1").arg(root.activeTaskCount()) : qsTr("Tarefas")
                        icon.name: "view-task"
                        Layout.fillWidth: true
                        Layout.minimumHeight: 48
                        Accessible.name: qsTr("Abrir central de tarefas")
                        onClicked: taskDrawer.open()
                    }

                    Button {
                        id: attentionButton
                        visible: root.needsAttention
                        text: root.hasConflicts ? qsTr("Conflito do Desktop")
                            : root.desktopStatus.recoveryRequired ? qsTr("Recuperação pendente")
                            : qsTr("Estado %1").arg(root.truthStateLabel(root.desktopStatus.truthState))
                        icon.name: "security-high"
                        Layout.fillWidth: true
                        Layout.minimumHeight: root.compactLayout ? 48 : 54
                        Accessible.name: text
                        KeyNavigation.up: navRepeater.itemAt(navRepeater.count - 1)
                        KeyNavigation.down: quickResetButton
                        onClicked: root.sectionIndex = 5
                        background: Rectangle { color: "#211a10"; radius: 7; border.color: "#59401f" }
                        contentItem: RowLayout {
                            ToolButton {
                                enabled: false
                                icon.name: "security-high"
                                icon.color: root.amberColor
                                background: Item {}
                            }
                            ColumnLayout {
                                visible: !root.compactLayout
                                spacing: 1
                                Label { text: attentionButton.text; color: root.amberColor; font.bold: true }
                                Label { text: qsTr("Requer sua atenção"); color: root.mutedColor; font.pixelSize: 12 }
                            }
                        }
                    }

                    Item { Layout.fillHeight: true }

                    Label {
                        visible: !root.compactLayout
                        text: qsTr("AÇÕES DO SISTEMA")
                        color: root.mutedColor
                        font.pixelSize: 11
                        font.capitalization: Font.AllUppercase
                    }
                    DarkButton {
                        id: quickResetButton
                        visible: !root.compactLayout
                        text: qsTr("Quick Reset")
                        icon.name: "edit-undo"
                        palette.buttonText: root.textColor
                        Layout.fillWidth: true
                        Layout.minimumHeight: 48
                        display: root.compactLayout ? AbstractButton.IconOnly
                            : AbstractButton.TextBesideIcon
                        ToolTip.visible: root.compactLayout && hovered
                        ToolTip.text: text
                        Accessible.name: text
                        background: Rectangle {
                            color: quickResetButton.activeFocus ? root.raisedColor : root.surfaceColor
                            radius: 6
                            border.color: quickResetButton.activeFocus ? root.cyanColor : root.borderColor
                            border.width: quickResetButton.activeFocus ? 2 : 1
                        }
                        KeyNavigation.up: attentionButton.visible ? attentionButton : navRepeater.itemAt(navRepeater.count - 1)
                        KeyNavigation.down: cloudSyncButton
                        onClicked: root.beginQuickReset()
                    }
                    DarkButton {
                        id: cloudSyncButton
                        visible: !root.compactLayout
                        text: qsTr("Cloud Sync")
                        icon.name: "folder-cloud"
                        palette.buttonText: root.textColor
                        Layout.fillWidth: true
                        Layout.minimumHeight: 48
                        display: root.compactLayout ? AbstractButton.IconOnly
                            : AbstractButton.TextBesideIcon
                        ToolTip.visible: root.compactLayout && hovered
                        ToolTip.text: text
                        Accessible.name: text
                        background: Rectangle {
                            color: cloudSyncButton.activeFocus ? root.raisedColor : root.surfaceColor
                            radius: 6
                            border.color: cloudSyncButton.activeFocus ? root.cyanColor : root.borderColor
                            border.width: cloudSyncButton.activeFocus ? 2 : 1
                        }
                        KeyNavigation.up: quickResetButton
                        KeyNavigation.down: doctorButton
                        onClicked: root.sectionIndex = 4
                    }
                    DarkButton {
                        id: doctorButton
                        visible: !root.compactLayout
                        text: qsTr("steamzero doctor")
                        icon.name: "tools-report-bug"
                        palette.buttonText: root.textColor
                        Layout.fillWidth: true
                        Layout.minimumHeight: 48
                        display: root.compactLayout ? AbstractButton.IconOnly
                            : AbstractButton.TextBesideIcon
                        ToolTip.visible: root.compactLayout && hovered
                        ToolTip.text: text
                        Accessible.name: text
                        background: Rectangle {
                            color: doctorButton.activeFocus ? root.raisedColor : root.surfaceColor
                            radius: 6
                            border.color: doctorButton.activeFocus ? root.cyanColor : root.borderColor
                            border.width: doctorButton.activeFocus ? 2 : 1
                        }
                        KeyNavigation.up: cloudSyncButton
                        KeyNavigation.down: navRepeater.itemAt(0)
                        onClicked: root.sectionIndex = 5
                    }
                    RowLayout {
                        visible: !root.compactLayout
                        Layout.fillWidth: true
                        Label {
                            text: root.desktopStatus.independentRuntime
                                ? qsTr("Runtime autônomo") : qsTr("Verificação necessária")
                            color: root.desktopStatus.independentRuntime ? root.greenColor : root.amberColor
                            font.pixelSize: 11
                            Layout.fillWidth: true
                        }
                        BusyIndicator { running: root.pendingRequests > 0; implicitWidth: 22; implicitHeight: 22 }
                    }
                }
            }

            Rectangle {
                color: root.backgroundColor
                Layout.fillWidth: true
                Layout.fillHeight: true

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 0

                    Rectangle {
                        id: compactHeader
                        visible: root.compactLayout
                        color: root.sidebarColor
                        border.color: root.borderColor
                        Layout.fillWidth: true
                        Layout.preferredHeight: 58

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 8
                            anchors.rightMargin: 8
                            spacing: 8
                            ToolButton {
                                id: navigationMenuButton
                                icon.name: "application-menu"
                                icon.color: root.textColor
                                Layout.minimumWidth: 48
                                Layout.minimumHeight: 48
                                Accessible.name: qsTr("Abrir navegação")
                                Accessible.description: qsTr("Seção atual: %1").arg(root.sectionLabel(root.sectionIndex))
                                onClicked: navigationDrawer.open()
                                background: Rectangle {
                                    color: navigationMenuButton.activeFocus ? root.raisedColor : "transparent"
                                    radius: 8
                                    border.color: navigationMenuButton.activeFocus
                                        ? root.cyanColor : "transparent"
                                    border.width: navigationMenuButton.activeFocus ? 2 : 0
                                }
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 0
                                Label {
                                    text: root.sectionLabel(root.sectionIndex)
                                    color: root.textColor
                                    font.pixelSize: 17
                                    font.bold: true
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                                Label {
                                    text: root.sectionIndex === 1 && root.emulationData.platforms
                                        && root.emulationData.platforms.length > 0
                                        ? root.emulationData.platforms[0].name
                                        : root.sectionIndex === 2 ? qsTr("%1 · %2").arg(root.steamArea).arg(root.deviceSummary())
                                        : root.deviceSummary()
                                    color: root.mutedColor
                                    font.pixelSize: 11
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                    Accessible.name: qsTr("Contexto: %1").arg(text)
                                }
                            }
                            BusyIndicator {
                                running: root.pendingRequests > 0
                                visible: running
                                Layout.preferredWidth: 32
                                Layout.preferredHeight: 32
                                Accessible.name: qsTr("Operação em andamento")
                            }
                            ToolButton {
                                id: compactTaskButton
                                icon.name: "view-task"
                                icon.color: root.activeTaskCount() > 0 ? root.cyanColor : root.mutedColor
                                Layout.minimumWidth: 48
                                Layout.minimumHeight: 48
                                Accessible.name: root.activeTaskCount() > 0
                                    ? qsTr("Abrir %1 tarefa(s) ativa(s)").arg(root.activeTaskCount())
                                    : qsTr("Abrir central de tarefas")
                                onClicked: taskDrawer.open()
                            }
                            ToolButton {
                                id: compactSystemButton
                                icon.name: root.needsAttention ? "security-high" : "configure"
                                icon.color: root.needsAttention ? root.amberColor : root.mutedColor
                                Layout.minimumWidth: 48
                                Layout.minimumHeight: 48
                                Accessible.name: root.needsAttention
                                    ? qsTr("Abrir pendência do sistema") : qsTr("Abrir sistema")
                                onClicked: root.sectionIndex = 5
                            }
                        }
                    }

                    Rectangle {
                        visible: root.hasConflicts || root.desktopTruthNeedsAttention
                        color: "#24180b"
                        border.color: root.amberColor
                        border.width: 1
                        radius: 8
                        Layout.fillWidth: true
                        Layout.maximumWidth: root.ultrawideLayout ? 1400 : -1
                        Layout.alignment: Qt.AlignHCenter
                        Layout.leftMargin: root.compactLayout ? 8 : 14
                        Layout.rightMargin: root.compactLayout ? 8 : 14
                        Layout.topMargin: root.compactLayout ? 7 : 12
                        Layout.preferredHeight: root.compactLayout ? 60 : 72

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: root.compactLayout ? 10 : 18
                            anchors.rightMargin: root.compactLayout ? 8 : 14
                            spacing: root.compactLayout ? 7 : 12
                            ToolButton {
                                enabled: false
                                icon.name: "dialog-warning"
                                icon.color: root.amberColor
                                icon.width: root.compactLayout ? 22 : 30
                                icon.height: root.compactLayout ? 22 : 30
                                background: Item {}
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 2
                                RowLayout {
                                    Label {
                                        text: root.hasConflicts
                                            ? qsTr("Outro serviço controla o Desktop")
                                            : root.desktopStatus.truthState === "stale"
                                                ? qsTr("Perfil do Desktop desatualizado")
                                                : root.desktopStatus.truthState === "unapplied"
                                                    ? qsTr("Nenhum perfil foi aplicado")
                                                    : qsTr("Observação do Desktop degradada")
                                        color: root.amberColor
                                        font.pixelSize: root.compactLayout ? 14 : 17
                                        font.bold: true
                                    }
                                    Label {
                                        visible: !root.compactLayout
                                        text: root.hasConflicts ? "E-DESKTOP-OWNER-CONFLICT"
                                            : root.truthStateLabel(root.desktopStatus.truthState).toUpperCase()
                                        color: "#d5b47d"
                                        font.pixelSize: 11
                                    }
                                }
                                Label {
                                    text: root.hasConflicts
                                        ? qsTr("Várias ações estão bloqueadas até o conflito ser resolvido.")
                                        : root.desktopStatus.statusReasons.length > 0
                                            ? root.desktopStatus.statusReasons[0]
                                            : qsTr("Revise o perfil desejado, aplicado e observado.")
                                    color: root.textColor
                                    font.pixelSize: root.compactLayout ? 11 : 13
                                    elide: Text.ElideRight
                                    maximumLineCount: 1
                                }
                            }
                            DarkButton {
                                id: resolveBannerButton
                                text: root.hasConflicts ? qsTr("Resolver agora")
                                    : root.desktopStatus.truthState === "degraded"
                                        ? qsTr("Ver diagnóstico") : qsTr("Revisar perfis")
                                palette.buttonText: root.textColor
                                icon.name: "go-next"
                                Layout.minimumHeight: 48
                                Accessible.name: text
                                background: Rectangle {
                                    color: resolveBannerButton.activeFocus ? "#3b2b18" : "#201a13"
                                    radius: 6
                                    border.color: resolveBannerButton.activeFocus ? root.cyanColor : "#705127"
                                    border.width: resolveBannerButton.activeFocus ? 2 : 1
                                }
                                onClicked: {
                                    if (root.hasConflicts)
                                        root.beginConflictResolution()
                                    else
                                        root.sectionIndex = root.desktopStatus.truthState === "degraded" ? 5 : 3
                                }
                            }
                        }
                    }

                    StackLayout {
                        id: contentStack
                        currentIndex: root.sectionIndex
                        Layout.fillWidth: true
                        Layout.fillHeight: true

                        // Visão geral
                        ScrollView {
                            id: overviewScroll
                            clip: true
                            contentWidth: availableWidth
                            bottomPadding: root.bottomSafeInset
                            ColumnLayout {
                                width: Math.min(parent.width, root.contentMaxWidth)
                                anchors.horizontalCenter: parent.horizontalCenter
                                spacing: root.compactLayout ? 12 : 18
                                anchors.margins: 28
                                Label {
                                    text: qsTr("Visão geral")
                                    color: root.textColor
                                    font.pixelSize: root.compactLayout ? 24 : 30
                                    font.bold: true
                                    Layout.topMargin: root.compactLayout ? 12 : 24
                                    Layout.leftMargin: root.responsiveGutter
                                }
                                Label {
                                    text: root.deviceSummary()
                                    color: root.mutedColor
                                    font.pixelSize: 15
                                    Layout.leftMargin: root.responsiveGutter
                                }
                                Rectangle {
                                    Layout.fillWidth: true
                                    Layout.leftMargin: root.responsiveGutter
                                    Layout.rightMargin: root.responsiveGutter
                                    Layout.minimumHeight: root.compactLayout ? 96 : 124
                                    color: root.surfaceColor
                                    radius: 10
                                    border.color: root.borderColor
                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.margins: root.compactLayout ? 12 : 20
                                        spacing: root.compactLayout ? 12 : 22
                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            Label {
                                                text: root.needsAttention ? qsTr("Ação necessária") : qsTr("Sistema pronto")
                                                color: root.needsAttention ? root.amberColor : root.greenColor
                                                font.pixelSize: root.compactLayout ? 18 : 22
                                                font.bold: true
                                            }
                                            Label {
                                                text: root.needsAttention
                                                    ? qsTr("Revise o estado real do Desktop antes de aplicar configurações.")
                                                    : qsTr("Perfil, display e providers foram verificados.")
                                                color: root.textColor
                                                wrapMode: Text.WordWrap
                                                Layout.fillWidth: true
                                            }
                                        }
                                        Button {
                                            text: root.hasConflicts ? qsTr("Resolver conflito")
                                                : root.desktopTruthNeedsAttention ? qsTr("Revisar perfis")
                                                : qsTr("Ver sistema")
                                            Layout.minimumHeight: 48
                                            Accessible.name: text
                                            onClicked: {
                                                if (root.hasConflicts)
                                                    root.beginConflictResolution()
                                                else
                                                    root.sectionIndex = root.desktopTruthNeedsAttention ? 3 : 5
                                            }
                                        }
                                    }
                                }
                                Label {
                                    text: qsTr("Áreas principais")
                                    color: root.textColor
                                    font.pixelSize: 20
                                    font.bold: true
                                    Layout.leftMargin: root.responsiveGutter
                                }
                                Repeater {
                                    model: [
                                        {"title": qsTr("Emuladores"), "detail": qsTr("%1 componentes · %2 precisam de atenção").arg(root.emulatorItems.length).arg(root.attentionCount(root.emulatorItems)), "target": 1, "icon": "input-gaming"},
                                        {"title": qsTr("Steam"), "detail": qsTr("Cliente, biblioteca, Steam Input e teclado"), "target": 2, "icon": "steam"},
                                        {"title": qsTr("Saves e Sync"), "detail": qsTr("Fila offline e conflitos preservados"), "target": 4, "icon": "folder-sync"}
                                    ]
                                    delegate: Button {
                                        required property var modelData
                                        text: modelData.title
                                        icon.name: modelData.icon
                                        Layout.fillWidth: true
                                        Layout.leftMargin: root.responsiveGutter
                                        Layout.rightMargin: root.responsiveGutter
                                        Layout.minimumHeight: root.compactLayout ? 58 : 66
                                        Accessible.name: qsTr("%1: %2").arg(modelData.title).arg(modelData.detail)
                                        onClicked: root.sectionIndex = modelData.target
                                        contentItem: RowLayout {
                                            ToolButton { enabled: false; icon.name: modelData.icon; icon.color: root.cyanColor; background: Item {} }
                                            ColumnLayout {
                                                Layout.fillWidth: true
                                                Label { text: modelData.title; color: root.textColor; font.bold: true }
                                                Label { text: modelData.detail; color: root.mutedColor; font.pixelSize: 13 }
                                            }
                                            ToolButton { enabled: false; icon.name: "go-next"; icon.color: root.mutedColor; background: Item {} }
                                        }
                                    }
                                }
                            }
                        }

                        // Emuladores
                        RowLayout {
                            spacing: 0
                            Emulation {
                                id: emulationPage
                                emulation: root.emulationData
                                reducedMotion: root.reducedMotion
                                backgroundColor: root.backgroundColor
                                sidebarColor: root.sidebarColor
                                surfaceColor: root.surfaceColor
                                raisedColor: root.raisedColor
                                borderColor: root.borderColor
                                textColor: root.textColor
                                mutedColor: root.mutedColor
                                cyanColor: root.cyanColor
                                cyanDarkColor: root.cyanDarkColor
                                greenColor: root.greenColor
                                amberColor: root.amberColor
                                redColor: root.redColor
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                onComponentActionRequested: function(component) {
                                    root.selectedEmulator = component
                                    root.performRowAction(component)
                                }
                                onActionRequested: function(action) {
                                    root.performEmulationAction(action)
                                }
                                onSystemRequested: root.sectionIndex = 5
                            }
                            ColumnLayout {
                                visible: false
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                spacing: 0
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    Layout.margins: 28
                                    spacing: 8
                                    RowLayout {
                                        Layout.fillWidth: true
                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 2
                                            Label { text: qsTr("Gerenciar emuladores"); color: root.textColor; font.pixelSize: 30; font.bold: true }
                                            Label { text: qsTr("Instale, atualize e restaure configurações com segurança."); color: root.mutedColor; font.pixelSize: 15 }
                                        }
                                        Button {
                                            visible: root.desktopStatus.recoveryRequired
                                            text: qsTr("Estado seguro disponível")
                                            icon.name: "security-medium"
                                            Layout.minimumHeight: 48
                                            Accessible.name: text
                                            onClicked: recoveryDialog.open()
                                        }
                                    }
                                    Label { text: root.deviceSummary(); color: root.mutedColor; font.pixelSize: 12 }
                                    RowLayout {
                                        spacing: 0
                                        DarkButton {
                                            id: emulatorAllFilter
                                            text: qsTr("Todos  %1").arg(root.emulatorItems.length)
                                            palette.buttonText: root.textColor
                                            checked: root.emulatorFilter === 0
                                            checkable: true
                                            Layout.minimumHeight: 48
                                            Accessible.name: text
                                            background: Rectangle {
                                                color: emulatorAllFilter.checked ? root.cyanDarkColor : root.surfaceColor
                                                border.color: emulatorAllFilter.checked || emulatorAllFilter.activeFocus ? root.cyanColor : root.borderColor
                                                border.width: emulatorAllFilter.checked || emulatorAllFilter.activeFocus ? 2 : 1
                                                radius: 6
                                            }
                                            onClicked: root.emulatorFilter = 0
                                        }
                                        DarkButton {
                                            id: emulatorAttentionFilter
                                            text: qsTr("Atenção  %1").arg(root.attentionCount(root.emulatorItems))
                                            palette.buttonText: root.textColor
                                            checked: root.emulatorFilter === 1
                                            checkable: true
                                            Layout.minimumHeight: 48
                                            Accessible.name: text
                                            background: Rectangle {
                                                color: emulatorAttentionFilter.checked ? root.cyanDarkColor : root.surfaceColor
                                                border.color: emulatorAttentionFilter.checked || emulatorAttentionFilter.activeFocus ? root.cyanColor : root.borderColor
                                                border.width: emulatorAttentionFilter.checked || emulatorAttentionFilter.activeFocus ? 2 : 1
                                                radius: 6
                                            }
                                            onClicked: root.emulatorFilter = 1
                                        }
                                        DarkButton {
                                            id: emulatorInstalledFilter
                                            text: qsTr("Instalados  %1").arg(root.readyCount(root.emulatorItems))
                                            palette.buttonText: root.textColor
                                            checked: root.emulatorFilter === 2
                                            checkable: true
                                            Layout.minimumHeight: 48
                                            Accessible.name: text
                                            background: Rectangle {
                                                color: emulatorInstalledFilter.checked ? root.cyanDarkColor : root.surfaceColor
                                                border.color: emulatorInstalledFilter.checked || emulatorInstalledFilter.activeFocus ? root.cyanColor : root.borderColor
                                                border.width: emulatorInstalledFilter.checked || emulatorInstalledFilter.activeFocus ? 2 : 1
                                                radius: 6
                                            }
                                            onClicked: root.emulatorFilter = 2
                                        }
                                    }
                                }
                                Rectangle { color: root.borderColor; Layout.fillWidth: true; Layout.preferredHeight: 1 }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Layout.leftMargin: 28
                                    Layout.rightMargin: 20
                                    Layout.preferredHeight: 34
                                    Label { text: qsTr("EMULADOR"); color: root.mutedColor; font.pixelSize: 11; Layout.fillWidth: true }
                                    Label { visible: root.width >= 1100; text: qsTr("ESTADO"); color: root.mutedColor; font.pixelSize: 11; Layout.preferredWidth: 180 }
                                    Label { text: qsTr("AÇÃO"); color: root.mutedColor; font.pixelSize: 11; Layout.preferredWidth: 132 }
                                }
                                ListView {
                                    id: emulatorList
                                    model: root.filterRows(root.emulatorItems, root.emulatorFilter)
                                    clip: true
                                    spacing: 2
                                    Layout.fillWidth: true
                                    Layout.fillHeight: true
                                    Layout.leftMargin: 8
                                    Layout.rightMargin: 8
                                    currentIndex: 0
                                    delegate: ItemDelegate {
                                        required property int index
                                        required property var modelData
                                        width: ListView.view.width
                                        height: 94
                                        highlighted: root.selectedEmulator && root.selectedEmulator.id === modelData.id
                                        Accessible.name: qsTr("%1, %2").arg(modelData.name).arg(modelData.statusLabel)
                                        KeyNavigation.up: index > 0 ? emulatorList.itemAtIndex(index - 1) : navRepeater.itemAt(1)
                                        KeyNavigation.down: index + 1 < emulatorList.count ? emulatorList.itemAtIndex(index + 1) : navRepeater.itemAt(1)
                                        onClicked: root.selectedEmulator = modelData
                                        background: Rectangle {
                                            color: parent.highlighted ? "#122534" : "transparent"
                                            radius: 8
                                            border.color: parent.highlighted || parent.activeFocus ? root.cyanColor : "transparent"
                                            border.width: parent.highlighted || parent.activeFocus ? 2 : 0
                                        }
                                        contentItem: RowLayout {
                                            spacing: 14
                                            Rectangle {
                                                color: root.raisedColor
                                                radius: 8
                                                border.color: root.borderColor
                                                Layout.preferredWidth: 66
                                                Layout.preferredHeight: 66
                                                Image {
                                                    visible: root.brandAsset(modelData.iconName) !== ""
                                                    anchors.centerIn: parent
                                                    source: root.brandAsset(modelData.iconName)
                                                    sourceSize.width: 48
                                                    sourceSize.height: 48
                                                    width: 48
                                                    height: 48
                                                    fillMode: Image.PreserveAspectFit
                                                    Accessible.name: qsTr("Logotipo %1").arg(modelData.name)
                                                }
                                                ToolButton {
                                                    visible: root.brandAsset(modelData.iconName) === ""
                                                    anchors.centerIn: parent
                                                    enabled: false
                                                    icon.name: modelData.iconName
                                                    icon.width: 36
                                                    icon.height: 36
                                                    icon.color: root.cyanColor
                                                    background: Item {}
                                                }
                                            }
                                            ColumnLayout {
                                                Layout.fillWidth: true
                                                spacing: 3
                                                Label { text: modelData.name; color: root.textColor; font.pixelSize: 17; font.bold: true }
                                                Label { text: modelData.description; color: root.mutedColor; font.pixelSize: 12 }
                                                RowLayout {
                                                    Repeater {
                                                        model: modelData.systems || []
                                                        delegate: Label {
                                                            required property string modelData
                                                            text: modelData
                                                            color: root.mutedColor
                                                            font.pixelSize: 11
                                                            leftPadding: 6
                                                            rightPadding: 6
                                                            background: Rectangle { color: root.surfaceColor; radius: 4; border.color: root.borderColor }
                                                        }
                                                    }
                                                }
                                            }
                                            RowLayout {
                                                visible: root.width >= 1100
                                                Layout.preferredWidth: 180
                                                ToolButton { enabled: false; icon.name: root.stateIcon(modelData.state); icon.color: root.stateColor(modelData.state); background: Item {} }
                                                ColumnLayout {
                                                    spacing: 0
                                                    Label { text: modelData.statusLabel; color: root.stateColor(modelData.state); font.pixelSize: 13 }
                                                    Label { text: modelData.versionLabel || "—"; color: root.mutedColor; font.pixelSize: 11 }
                                                }
                                            }
                                            DarkButton {
                                                id: componentRowAction
                                                text: modelData.action.label
                                                palette.buttonText: componentRowAction.enabled ? root.textColor : root.mutedColor
                                                enabled: modelData.action.enabled
                                                Layout.preferredWidth: 132
                                                Layout.minimumHeight: 48
                                                Accessible.name: qsTr("%1: %2").arg(text).arg(modelData.name)
                                                background: Rectangle {
                                                    color: componentRowAction.enabled ? root.raisedColor : root.surfaceColor
                                                    radius: 6
                                                    border.color: componentRowAction.activeFocus ? root.cyanColor : root.borderColor
                                                    border.width: componentRowAction.activeFocus ? 2 : 1
                                                }
                                                onClicked: {
                                                    root.selectedEmulator = modelData
                                                    root.performRowAction(modelData)
                                                }
                                            }
                                        }
                                    }
                                }
                            }

                            Rectangle {
                                visible: false
                                color: root.surfaceColor
                                border.color: root.borderColor
                                Layout.preferredWidth: 292
                                Layout.fillHeight: true
                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: 20
                                    spacing: 14
                                    Label {
                                        text: root.selectedEmulator ? root.selectedEmulator.name : qsTr("Emulador")
                                        color: root.textColor
                                        font.pixelSize: 20
                                        font.bold: true
                                        Layout.fillWidth: true
                                    }
                                    Label {
                                        text: root.selectedEmulator ? root.selectedEmulator.statusLabel : ""
                                        color: root.selectedEmulator ? root.stateColor(root.selectedEmulator.state) : root.mutedColor
                                        font.pixelSize: 14
                                    }
                                    Rectangle { color: root.borderColor; Layout.fillWidth: true; Layout.preferredHeight: 1 }
                                    Label { text: qsTr("Sobre"); color: root.textColor; font.bold: true }
                                    Label {
                                        text: root.selectedEmulator ? root.selectedEmulator.detail : ""
                                        color: root.mutedColor
                                        wrapMode: Text.WordWrap
                                        Layout.fillWidth: true
                                    }
                                    Label {
                                        visible: root.selectedEmulator && root.selectedEmulator.blockedReason
                                        text: root.selectedEmulator ? root.selectedEmulator.blockedReason : ""
                                        color: root.amberColor
                                        wrapMode: Text.WordWrap
                                        Layout.fillWidth: true
                                    }
                                    Item { Layout.fillHeight: true }
                                    DarkButton {
                                        id: componentDetailAction
                                        visible: root.selectedEmulator !== null
                                        text: root.selectedEmulator ? root.selectedEmulator.action.label : ""
                                        palette.buttonText: componentDetailAction.enabled ? root.textColor : root.mutedColor
                                        enabled: root.selectedEmulator && root.selectedEmulator.action.enabled
                                        Layout.fillWidth: true
                                        Layout.minimumHeight: 48
                                        Accessible.name: text
                                        background: Rectangle {
                                            color: componentDetailAction.enabled ? root.raisedColor : root.surfaceColor
                                            radius: 6
                                            border.color: componentDetailAction.activeFocus ? root.cyanColor : root.borderColor
                                            border.width: componentDetailAction.activeFocus ? 2 : 1
                                        }
                                        onClicked: root.performRowAction(root.selectedEmulator)
                                    }
                                }
                            }
                        }

                        // Steam
                        RowLayout {
                            spacing: 0
                            SteamGameplay {
                                id: steamGameplayPage
                                gameplay: root.steamGameplayData
                                desktopStatus: root.desktopStatus
                                reducedMotion: root.reducedMotion
                                initialArea: root.steamArea
                                backgroundColor: root.backgroundColor
                                surfaceColor: root.surfaceColor
                                raisedColor: root.raisedColor
                                borderColor: root.borderColor
                                textColor: root.textColor
                                mutedColor: root.mutedColor
                                cyanColor: root.cyanColor
                                cyanDarkColor: root.cyanDarkColor
                                greenColor: root.greenColor
                                amberColor: root.amberColor
                                redColor: root.redColor
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                onPlanRequested: function(payload) {
                                    root.requestAction("steam.gameplay.plan", payload, function(response) {
                                        steamGameplayPage.showPlan(response.plan)
                                    })
                                }
                                onApplyRequested: function(planId, confirmToken) {
                                    root.requestAction("steam.gameplay.apply", {
                                        "planId": planId,
                                        "confirmToken": confirmToken
                                    }, function(response) {
                                        root.refreshStatus(response.message || qsTr("Perfil Steam salvo"))
                                    })
                                }
                                onSystemRequested: root.sectionIndex = 5
                                onDesktopProfilePlanRequested: function(profile) {
                                    root.requestAction("desktop.profile.plan", {"profile": profile}, function(response) {
                                        steamGameplayPage.showDesktopPlan(response.plan)
                                    })
                                }
                                onDesktopProfileApplyRequested: function(planId, confirmToken) {
                                    root.requestAction("desktop.profile.apply", {
                                        "planId": planId,
                                        "confirmToken": confirmToken
                                    }, function() {
                                        root.refreshStatus(qsTr("Perfil do Modo Desktop aplicado"))
                                    })
                                }
                                onDesktopSafeResetRequested: root.beginQuickReset()
                                onDesktopConflictRequested: root.beginConflictResolution()
                                onDesktopRecoveryRequested: root.requestAction(
                                    "desktop.recover", {}, function() {
                                        root.refreshStatus(qsTr("Estado Desktop seguro restaurado"))
                                    }
                                )
                                onDesktopKeyboardRequested: function(language) { root.openKeyboard(language) }
                                onDesktopAshytermRequested: root.requestAction("terminal.open", {}, function(response) {
                                    root.notify(qsTr("Terminal Ashy aberto"), false)
                                })
                                onDesktopPanelAutoHideRequested: function(enable) {
                                    root.requestAction("panel.autohide", {"enable": enable}, function(response) {
                                        root.notify(qsTr("Painel auto-ocultar %1").arg(enable ? qsTr("ativado") : qsTr("desativado")), false)
                                    })
                                }
                                onDesktopKeyboardSoundRequested: function(enable) {
                                    root.requestAction("keyboard.settings", {"sound": enable}, function(response) {
                                        root.notify(qsTr("Som do teclado %1").arg(enable ? qsTr("ativado") : qsTr("desativado")), false)
                                    })
                                }
                                onDesktopKeyboardThemeRequested: function(dark) {
                                    root.requestAction("keyboard.settings", {"theme": dark ? "SuruDark" : "Ambiance"}, function(response) {
                                        root.notify(qsTr("Tema do teclado: %1").arg(dark ? qsTr("escuro") : qsTr("claro")), false)
                                    })
                                }
                                onDesktopGamemodeReturnRequested: root.beginGamemodeReturn()
                                onSteamInputRequested: function(gameId) {
                                    root.requestAction("steam.input.open", {
                                        "gameId": gameId
                                    }, function() {
                                        root.notify(qsTr("Configuração Steam Input aberta"), false)
                                    })
                                }
                                onLauncherRecoveryRequested: function(gameId) {
                                    root.requestAction("steam.gameplay.recover", {
                                        "gameId": gameId
                                    }, function() {
                                        root.refreshStatus(qsTr("Estado do lançamento restaurado"))
                                    })
                                }
                                onLaunchOptionsPlanRequested: function(gameId) {
                                    root.requestAction("steam.launch-options.plan", {
                                        "gameId": gameId
                                    }, function(response) {
                                        steamGameplayPage.showLaunchOptionsPlan(response.plan)
                                    })
                                }
                                onLaunchOptionsApplyRequested: function(planId, confirmToken, gameId) {
                                    root.requestAction("steam.launch-options.apply", {
                                        "planId": planId,
                                        "confirmToken": confirmToken,
                                        "gameId": gameId
                                    }, function(response) {
                                        root.refreshStatus(response.message || qsTr("Lançamento configurado"))
                                    })
                                }
                                onLaunchOptionsRollbackRequested: function(operationId) {
                                    root.requestAction("steam.launch-options.rollback", {
                                        "operationId": operationId
                                    }, function(response) {
                                        root.refreshStatus(response.message || qsTr("Configuração restaurada"))
                                    })
                                }
                                onMaintenancePlanRequested: function(gameId, categories) {
                                    root.requestAction("steam.maintenance.plan", {
                                        "gameId": gameId,
                                        "categories": categories
                                    }, function(response) {
                                        steamGameplayPage.showMaintenancePlan(response)
                                    })
                                }
                                onMaintenanceApplyRequested: function(planId, confirmToken, confirmPhrase) {
                                    root.requestAction("steam.maintenance.apply", {
                                        "planId": planId,
                                        "confirmToken": confirmToken,
                                        "confirmPhrase": confirmPhrase
                                    }, function(response) {
                                        root.refreshStatus(qsTr("%1 liberados com segurança").arg(
                                            steamGameplayPage.formatBytes(response.freedBytes)
                                        ))
                                    })
                                }
                                onMaintenanceRecoveryRequested: {
                                    root.requestAction("steam.maintenance.recover", {}, function() {
                                        root.refreshStatus(qsTr("Limpeza interrompida concluída"))
                                    })
                                }
                                onMediaPlanRequested: function(gameId, accountId, packagePath) {
                                    root.requestAction("steam.media.plan", {
                                        "gameId": gameId,
                                        "accountId": accountId,
                                        "packagePath": packagePath
                                    }, function(response) {
                                        steamGameplayPage.showMediaPlan(response)
                                    })
                                }
                                onMediaApplyRequested: function(planId, confirmToken) {
                                    root.requestAction("steam.media.apply", {
                                        "planId": planId,
                                        "confirmToken": confirmToken
                                    }, function(response) {
                                        steamGameplayPage.mediaLastOperationId = response.operationId || ""
                                        root.refreshStatus(response.message || qsTr("Pacote de mídia aplicado"))
                                    })
                                }
                                onMediaRollbackRequested: function(operationId) {
                                    root.requestAction("steam.media.rollback", {
                                        "operationId": operationId
                                    }, function() {
                                        steamGameplayPage.mediaLastOperationId = ""
                                        root.refreshStatus(qsTr("Mídia anterior restaurada"))
                                    })
                                }
                            }
                            ColumnLayout {
                                visible: false
                                Layout.preferredWidth: 0
                                Layout.fillWidth: false
                                Layout.fillHeight: true
                                spacing: 0
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    Layout.margins: 28
                                    spacing: 8
                                    Label { text: qsTr("Steam e integração"); color: root.textColor; font.pixelSize: 30; font.bold: true }
                                    Label { text: qsTr("Gerencie cliente, biblioteca, Steam Input e teclado em um só lugar."); color: root.mutedColor; font.pixelSize: 15 }
                                    Label { text: root.deviceSummary(); color: root.mutedColor; font.pixelSize: 12 }
                                    RowLayout {
                                        spacing: 0
                                        DarkButton {
                                            id: steamAllFilter
                                            text: qsTr("Todos  %1").arg(root.steamItems.length)
                                            palette.buttonText: root.textColor
                                            checked: root.steamFilter === 0
                                            checkable: true
                                            Layout.minimumHeight: 48
                                            Accessible.name: text
                                            background: Rectangle {
                                                color: steamAllFilter.checked ? root.cyanDarkColor : root.surfaceColor
                                                border.color: steamAllFilter.checked || steamAllFilter.activeFocus ? root.cyanColor : root.borderColor
                                                border.width: steamAllFilter.checked || steamAllFilter.activeFocus ? 2 : 1
                                                radius: 6
                                            }
                                            onClicked: root.steamFilter = 0
                                        }
                                        DarkButton {
                                            id: steamAttentionFilter
                                            text: qsTr("Atenção  %1").arg(root.attentionCount(root.steamItems))
                                            palette.buttonText: root.textColor
                                            checked: root.steamFilter === 1
                                            checkable: true
                                            Layout.minimumHeight: 48
                                            Accessible.name: text
                                            background: Rectangle {
                                                color: steamAttentionFilter.checked ? root.cyanDarkColor : root.surfaceColor
                                                border.color: steamAttentionFilter.checked || steamAttentionFilter.activeFocus ? root.cyanColor : root.borderColor
                                                border.width: steamAttentionFilter.checked || steamAttentionFilter.activeFocus ? 2 : 1
                                                radius: 6
                                            }
                                            onClicked: root.steamFilter = 1
                                        }
                                        DarkButton {
                                            id: steamReadyFilter
                                            text: qsTr("Prontos  %1").arg(root.readyCount(root.steamItems))
                                            palette.buttonText: root.textColor
                                            checked: root.steamFilter === 2
                                            checkable: true
                                            Layout.minimumHeight: 48
                                            Accessible.name: text
                                            background: Rectangle {
                                                color: steamReadyFilter.checked ? root.cyanDarkColor : root.surfaceColor
                                                border.color: steamReadyFilter.checked || steamReadyFilter.activeFocus ? root.cyanColor : root.borderColor
                                                border.width: steamReadyFilter.checked || steamReadyFilter.activeFocus ? 2 : 1
                                                radius: 6
                                            }
                                            onClicked: root.steamFilter = 2
                                        }
                                    }
                                }
                                Rectangle { color: root.borderColor; Layout.fillWidth: true; Layout.preferredHeight: 1 }
                                ListView {
                                    id: steamList
                                    model: root.filterRows(root.steamItems, root.steamFilter)
                                    clip: true
                                    spacing: 2
                                    Layout.fillWidth: true
                                    Layout.fillHeight: true
                                    Layout.leftMargin: 8
                                    Layout.rightMargin: 8
                                    delegate: ItemDelegate {
                                        required property int index
                                        required property var modelData
                                        width: ListView.view.width
                                        height: 94
                                        highlighted: root.selectedSteam && root.selectedSteam.id === modelData.id
                                        Accessible.name: qsTr("%1, %2").arg(modelData.name).arg(modelData.statusLabel)
                                        KeyNavigation.up: index > 0 ? steamList.itemAtIndex(index - 1) : navRepeater.itemAt(2)
                                        KeyNavigation.down: index + 1 < steamList.count ? steamList.itemAtIndex(index + 1) : navRepeater.itemAt(2)
                                        onClicked: root.selectedSteam = modelData
                                        background: Rectangle {
                                            color: parent.highlighted ? "#122534" : "transparent"
                                            radius: 8
                                            border.color: parent.highlighted || parent.activeFocus ? root.cyanColor : "transparent"
                                            border.width: parent.highlighted || parent.activeFocus ? 2 : 0
                                        }
                                        contentItem: RowLayout {
                                            spacing: 14
                                            Rectangle {
                                                color: root.raisedColor
                                                radius: 8
                                                border.color: root.borderColor
                                                Layout.preferredWidth: 66
                                                Layout.preferredHeight: 66
                                                Image {
                                                    visible: root.brandAsset(modelData.iconName) !== ""
                                                    anchors.centerIn: parent
                                                    source: root.brandAsset(modelData.iconName)
                                                    sourceSize.width: 48
                                                    sourceSize.height: 48
                                                    width: 48
                                                    height: 48
                                                    fillMode: Image.PreserveAspectFit
                                                    Accessible.name: qsTr("Logotipo %1").arg(modelData.name)
                                                }
                                                ToolButton {
                                                    visible: root.brandAsset(modelData.iconName) === ""
                                                    anchors.centerIn: parent
                                                    enabled: false
                                                    icon.name: modelData.iconName
                                                    icon.width: 36
                                                    icon.height: 36
                                                    icon.color: root.cyanColor
                                                    background: Item {}
                                                }
                                            }
                                            ColumnLayout {
                                                Layout.fillWidth: true
                                                spacing: 3
                                                Label { text: modelData.name; color: root.textColor; font.pixelSize: 17; font.bold: true }
                                                Label { text: modelData.description; color: root.mutedColor; font.pixelSize: 12 }
                                                Label { text: modelData.versionLabel || ""; color: root.mutedColor; font.pixelSize: 11 }
                                            }
                                            RowLayout {
                                                visible: root.width >= 1100
                                                Layout.preferredWidth: 180
                                                ToolButton { enabled: false; icon.name: root.stateIcon(modelData.state); icon.color: root.stateColor(modelData.state); background: Item {} }
                                                Label { text: modelData.statusLabel; color: root.stateColor(modelData.state); wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                            }
                                            DarkButton {
                                                id: steamRowAction
                                                text: modelData.action.label
                                                palette.buttonText: steamRowAction.enabled ? root.textColor : root.mutedColor
                                                enabled: modelData.action.enabled
                                                Layout.preferredWidth: 144
                                                Layout.minimumHeight: 48
                                                Accessible.name: qsTr("%1: %2").arg(text).arg(modelData.name)
                                                background: Rectangle {
                                                    color: steamRowAction.enabled ? root.raisedColor : root.surfaceColor
                                                    radius: 6
                                                    border.color: steamRowAction.activeFocus ? root.cyanColor : root.borderColor
                                                    border.width: steamRowAction.activeFocus ? 2 : 1
                                                }
                                                onClicked: {
                                                    root.selectedSteam = modelData
                                                    root.performRowAction(modelData)
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                            Rectangle {
                                visible: false
                                color: root.surfaceColor
                                border.color: root.borderColor
                                Layout.preferredWidth: 292
                                Layout.fillHeight: true
                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: 20
                                    spacing: 14
                                    Label {
                                        text: root.selectedSteam ? root.selectedSteam.name : "Steam"
                                        color: root.textColor
                                        font.pixelSize: 20
                                        font.bold: true
                                        Layout.fillWidth: true
                                    }
                                    Label {
                                        text: root.selectedSteam ? root.selectedSteam.statusLabel : ""
                                        color: root.selectedSteam ? root.stateColor(root.selectedSteam.state) : root.mutedColor
                                    }
                                    Rectangle { color: root.borderColor; Layout.fillWidth: true; Layout.preferredHeight: 1 }
                                    Label { text: qsTr("Integração"); color: root.textColor; font.bold: true }
                                    Label {
                                        text: root.selectedSteam ? root.selectedSteam.detail : ""
                                        color: root.mutedColor
                                        wrapMode: Text.WordWrap
                                        Layout.fillWidth: true
                                    }
                                    Label {
                                        text: qsTr("O Steam é opcional: a central e o perfil Desktop continuam funcionando sem ele.")
                                        color: root.mutedColor
                                        wrapMode: Text.WordWrap
                                        Layout.fillWidth: true
                                    }
                                    Item { Layout.fillHeight: true }
                                    DarkButton {
                                        id: steamDetailAction
                                        visible: root.selectedSteam !== null
                                        text: root.selectedSteam ? root.selectedSteam.action.label : ""
                                        palette.buttonText: steamDetailAction.enabled ? root.textColor : root.mutedColor
                                        enabled: root.selectedSteam && root.selectedSteam.action.enabled
                                        Layout.fillWidth: true
                                        Layout.minimumHeight: 48
                                        Accessible.name: text
                                        background: Rectangle {
                                            color: steamDetailAction.enabled ? root.raisedColor : root.surfaceColor
                                            radius: 6
                                            border.color: steamDetailAction.activeFocus ? root.cyanColor : root.borderColor
                                            border.width: steamDetailAction.activeFocus ? 2 : 1
                                        }
                                        onClicked: root.performRowAction(root.selectedSteam)
                                    }
                                }
                            }
                        }

                        // Perfis
                        ScrollView {
                            id: profilesScroll
                            clip: true
                            contentWidth: availableWidth
                            bottomPadding: root.bottomSafeInset
                            ColumnLayout {
                                width: parent.width
                                spacing: 16
                                Label {
                                    text: qsTr("Perfis do Desktop")
                                    color: root.textColor
                                    font.pixelSize: 30
                                    font.bold: true
                                    Layout.topMargin: 28
                                    Layout.leftMargin: 28
                                }
                                Label {
                                    text: qsTr("Aplicado: %1 · Observado: %2 · Desejado: %3").arg(root.desktopStatus.appliedProfile || qsTr("nenhum")).arg(root.desktopStatus.observedProfile || qsTr("incerto")).arg(root.desktopStatus.desiredProfile)
                                    color: root.mutedColor
                                    Layout.leftMargin: 28
                                }
                                Rectangle {
                                    color: root.surfaceColor
                                    radius: 10
                                    border.color: root.borderColor
                                    Layout.fillWidth: true
                                    Layout.leftMargin: 28
                                    Layout.rightMargin: 28
                                    Layout.minimumHeight: 180
                                    ColumnLayout {
                                        anchors.fill: parent
                                        anchors.margins: 20
                                        spacing: 12
                                        Label { text: qsTr("Escolha o comportamento"); color: root.textColor; font.pixelSize: 18; font.bold: true }
                                        SteamComboBox {
                                            id: profilePicker
                                            Layout.fillWidth: true
                                            Layout.minimumHeight: 48
                                            model: [qsTr("Automático"), qsTr("Portátil"), qsTr("Dock"), qsTr("Seguro")]
                                            Accessible.name: qsTr("Selecionar perfil")
                                            onActivated: root.selectedProfile = ["auto", "handheld", "dock", "safe"][currentIndex]
                                            KeyNavigation.down: planButton
                                        }
                                        Button {
                                            id: planButton
                                            text: qsTr("Revisar alterações")
                                            Layout.fillWidth: true
                                            Layout.minimumHeight: 48
                                            Accessible.name: text
                                            KeyNavigation.up: profilePicker
                                            KeyNavigation.down: applyButton
                                            onClicked: {
                                                root.planRequested(root.selectedProfile)
                                                root.requestAction("desktop.profile.plan", {"profile": root.selectedProfile}, function(response) {
                                                    root.currentPlan = response.plan
                                                    if (response.plan.blockers.length > 0)
                                                        root.notify(qsTr("Plano bloqueado: %1").arg(response.plan.blockers.join("; ")), true)
                                                    else
                                                        root.notify(qsTr("Plano pronto para revisão"), false)
                                                })
                                            }
                                        }
                                    }
                                }
                                Rectangle {
                                    visible: root.currentPlan !== null
                                    color: root.surfaceColor
                                    radius: 10
                                    border.color: root.currentPlan && root.currentPlan.blockers.length > 0 ? root.amberColor : root.cyanDarkColor
                                    Layout.fillWidth: true
                                    Layout.leftMargin: 28
                                    Layout.rightMargin: 28
                                    Layout.minimumHeight: 180
                                    ColumnLayout {
                                        anchors.fill: parent
                                        anchors.margins: 20
                                        spacing: 10
                                        Label { text: qsTr("Plano revisado"); color: root.textColor; font.pixelSize: 18; font.bold: true }
                                        Label {
                                            text: root.currentPlan ? root.currentPlan.changes.join("\n") : ""
                                            color: root.mutedColor
                                            wrapMode: Text.WordWrap
                                            Layout.fillWidth: true
                                        }
                                        Label {
                                            visible: root.currentPlan && root.currentPlan.blockers.length > 0
                                            text: root.currentPlan ? qsTr("Plano bloqueado: %1").arg(root.currentPlan.blockers.join("; ")) : ""
                                            color: root.amberColor
                                            wrapMode: Text.WordWrap
                                            Layout.fillWidth: true
                                        }
                                        Button {
                                            id: applyButton
                                            text: root.currentPlan && root.currentPlan.blockers.length > 0
                                                ? qsTr("Aplicação bloqueada — resolva o conflito") : qsTr("Aplicar plano revisado")
                                            enabled: root.currentPlan !== null && root.currentPlan.blockers.length === 0
                                            Layout.fillWidth: true
                                            Layout.minimumHeight: 48
                                            Accessible.name: text
                                            KeyNavigation.up: planButton
                                            KeyNavigation.down: profilePicker
                                            onClicked: {
                                                const actionId = root.currentPlan.target.id === "safe"
                                                    ? "desktop.profile.reset" : "desktop.profile.apply"
                                                root.requestAction(actionId, {
                                                    "planId": root.currentPlan.planId,
                                                    "confirmToken": root.currentPlan.confirmToken
                                                }, function(response) {
                                                    root.refreshStatus(qsTr("Perfil aplicado: %1").arg(response.profile.id))
                                                })
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        // Saves e Sync
                        ScrollView {
                            id: syncScroll
                            clip: true
                            contentWidth: availableWidth
                            bottomPadding: root.bottomSafeInset
                            ColumnLayout {
                                width: parent.width
                                spacing: 16
                                Label { text: qsTr("Estado da sincronização"); color: root.textColor; font.pixelSize: 30; font.bold: true; Layout.topMargin: 28; Layout.leftMargin: 28 }
                                Label { text: qsTr("Somente leitura: a bridge ainda não publicou provider nem mutações seguras."); color: root.amberColor; Layout.leftMargin: 28 }
                                Repeater {
                                    model: [
                                        {"label": qsTr("Pendentes"), "value": root.desktopStatus.dashboard && root.desktopStatus.dashboard.sync ? root.desktopStatus.dashboard.sync.pending || 0 : 0, "icon": "view-refresh"},
                                        {"label": qsTr("Conflitos preservados"), "value": root.desktopStatus.dashboard && root.desktopStatus.dashboard.sync ? root.desktopStatus.dashboard.sync.conflicted || 0 : 0, "icon": "dialog-warning"},
                                        {"label": qsTr("Concluídos"), "value": root.desktopStatus.dashboard && root.desktopStatus.dashboard.sync ? root.desktopStatus.dashboard.sync.done || 0 : 0, "icon": "dialog-ok-apply"}
                                    ]
                                    delegate: Rectangle {
                                        required property var modelData
                                        color: root.surfaceColor
                                        radius: 8
                                        border.color: root.borderColor
                                        Layout.fillWidth: true
                                        Layout.leftMargin: 28
                                        Layout.rightMargin: 28
                                        Layout.minimumHeight: 64
                                        RowLayout {
                                            anchors.fill: parent
                                            anchors.margins: 16
                                            ToolButton { enabled: false; icon.name: modelData.icon; icon.color: root.cyanColor; background: Item {} }
                                            Label { text: modelData.label; color: root.textColor; Layout.fillWidth: true }
                                            Label { text: String(modelData.value); color: root.textColor; font.pixelSize: 20; font.bold: true }
                                        }
                                    }
                                }
                                Rectangle {
                                    id: providerStatusCard
                                    color: root.surfaceColor
                                    radius: 8
                                    border.color: root.borderColor
                                    Layout.fillWidth: true
                                    Layout.leftMargin: 28
                                    Layout.rightMargin: 28
                                    Layout.minimumHeight: providerStatusColumn.implicitHeight + 24
                                    ColumnLayout {
                                        id: providerStatusColumn
                                        anchors.fill: parent
                                        anchors.margins: 12
                                        Label { text: qsTr("Provider"); color: root.textColor; font.bold: true }
                                        Label {
                                            text: root.desktopStatus.dashboard && root.desktopStatus.dashboard.sync
                                                && root.desktopStatus.dashboard.sync.provider
                                                ? root.desktopStatus.dashboard.sync.provider.detail
                                                : qsTr("Provider não configurado")
                                            color: root.mutedColor
                                            wrapMode: Text.WordWrap
                                            Layout.fillWidth: true
                                        }
                                    }
                                }
                                Repeater {
                                    model: root.desktopStatus.dashboard && root.desktopStatus.dashboard.sync
                                        ? root.desktopStatus.dashboard.sync.items || [] : []
                                    delegate: Rectangle {
                                        required property var modelData
                                        color: root.surfaceColor
                                        radius: 8
                                        border.color: modelData.state === "conflicted"
                                            ? root.amberColor : root.borderColor
                                        Layout.fillWidth: true
                                        Layout.leftMargin: 28
                                        Layout.rightMargin: 28
                                        Layout.minimumHeight: syncItemColumn.implicitHeight + 24
                                        ColumnLayout {
                                            id: syncItemColumn
                                            anchors.fill: parent
                                            anchors.margins: 12
                                            Label {
                                                text: qsTr("Item %1 • %2")
                                                    .arg(String(modelData.id || "").slice(0, 12))
                                                    .arg(modelData.state || qsTr("desconhecido"))
                                                color: root.textColor
                                                font.bold: true
                                            }
                                            Label {
                                                text: qsTr("%1 • jogo %2 • última tentativa não publicada")
                                                    .arg(modelData.direction || qsTr("direção desconhecida"))
                                                    .arg(modelData.gameId || qsTr("não associado"))
                                                color: root.mutedColor
                                                wrapMode: Text.WordWrap
                                                Layout.fillWidth: true
                                            }
                                            Label {
                                                visible: modelData.conflict !== null
                                                text: qsTr("Conflito preservado; resolução exige contrato com confirmação.")
                                                color: root.amberColor
                                                wrapMode: Text.WordWrap
                                                Layout.fillWidth: true
                                            }
                                        }
                                    }
                                }
                                Label {
                                    text: root.desktopStatus.dashboard && root.desktopStatus.dashboard.sync
                                        ? root.desktopStatus.dashboard.sync.dependency || ""
                                        : qsTr("Aguardando leitura da fila local.")
                                    color: root.mutedColor
                                    wrapMode: Text.WordWrap
                                    Layout.fillWidth: true
                                    Layout.leftMargin: 28
                                    Layout.rightMargin: 28
                                }
                                Button {
                                    id: syncUpdateButton
                                    text: qsTr("Atualizar status")
                                    icon.name: "view-refresh"
                                    Layout.leftMargin: 28
                                    Layout.minimumHeight: 48
                                    Accessible.name: text
                                    onClicked: root.refreshStatus(qsTr("Status de sincronização atualizado"))
                                }
                            }
                        }

                        // Sistema
                        ScrollView {
                            id: systemScroll
                            clip: true
                            contentWidth: availableWidth
                            bottomPadding: root.bottomSafeInset
                            ColumnLayout {
                                width: parent.width
                                spacing: 16
                                Label { text: qsTr("Sistema e recuperação"); color: root.textColor; font.pixelSize: 30; font.bold: true; Layout.topMargin: 28; Layout.leftMargin: 28 }
                                Label { text: root.deviceSummary(); color: root.mutedColor; Layout.leftMargin: 28 }
                                Rectangle {
                                    visible: root.hasConflicts
                                    color: "#24180b"
                                    radius: 8
                                    border.color: root.amberColor
                                    Layout.fillWidth: true
                                    Layout.leftMargin: 28
                                    Layout.rightMargin: 28
                                    Layout.minimumHeight: 100
                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.margins: 18
                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            Label { text: qsTr("Conflito de controle do sistema"); color: root.amberColor; font.pixelSize: 18; font.bold: true }
                                            Label { text: "E-DESKTOP-OWNER-CONFLICT"; color: root.mutedColor; font.pixelSize: 12 }
                                        }
                                        Button { text: qsTr("Resolver conflito"); Layout.minimumHeight: 48; Accessible.name: text; onClicked: root.beginConflictResolution() }
                                    }
                                }
                                Label {
                                    text: qsTr("Componentes de gameplay")
                                    color: root.textColor
                                    font.pixelSize: 20
                                    font.bold: true
                                    Layout.leftMargin: 28
                                }
                                Rectangle {
                                    color: root.surfaceColor
                                    radius: 8
                                    border.color: root.lsfgSystemData.state === "ready"
                                        ? root.greenColor
                                        : root.lsfgSystemData.state === "degraded"
                                        ? root.amberColor : root.borderColor
                                    Layout.fillWidth: true
                                    Layout.leftMargin: 28
                                    Layout.rightMargin: 28
                                    Layout.minimumHeight: 116
                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.margins: 18
                                        spacing: 16
                                        ToolButton {
                                            enabled: false
                                            icon.name: "view-media-visualization"
                                            icon.color: root.lsfgSystemData.state === "ready"
                                                ? root.greenColor : root.cyanColor
                                            icon.width: 30
                                            icon.height: 30
                                            background: Item {}
                                        }
                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 3
                                            RowLayout {
                                                Layout.fillWidth: true
                                                Label {
                                                    text: "LSFG-VK"
                                                    color: root.textColor
                                                    font.pixelSize: 18
                                                    font.bold: true
                                                }
                                                Label {
                                                    text: root.lsfgSystemData.statusLabel
                                                    color: root.lsfgSystemData.state === "ready"
                                                        ? root.greenColor : root.amberColor
                                                    font.bold: true
                                                }
                                            }
                                            Label {
                                                text: root.lsfgSystemData.detail
                                                color: root.mutedColor
                                                wrapMode: Text.WordWrap
                                                Layout.fillWidth: true
                                            }
                                            Label {
                                                text: root.lsfgSystemData.losslessScalingInstalled
                                                    ? qsTr("Lossless Scaling detectado na Steam")
                                                    : qsTr("Requer Lossless Scaling instalado pela Steam")
                                                color: root.lsfgSystemData.losslessScalingInstalled
                                                    ? root.greenColor : root.amberColor
                                                font.pixelSize: 11
                                            }
                                        }
                                        Button {
                                            visible: root.lsfgSystemData.state !== "ready"
                                                && !root.lsfgSystemData.losslessScalingInstalled
                                            text: qsTr("Abrir biblioteca")
                                            Layout.minimumHeight: 48
                                            Accessible.name: qsTr("Abrir biblioteca Steam para Lossless Scaling")
                                            onClicked: root.requestAction("steam.open", {
                                                "target": "library"
                                            }, function() {
                                                root.notify(qsTr("Biblioteca Steam aberta"), false)
                                            })
                                        }
                                        Button {
                                            visible: root.lsfgSystemData.state !== "ready"
                                                && root.lsfgSystemData.losslessScalingInstalled
                                            text: root.lsfgSystemData.state === "degraded"
                                                ? qsTr("Reparar LSFG-VK") : qsTr("Preparar LSFG-VK")
                                            enabled: root.lsfgSystemData.installable
                                            Layout.minimumHeight: 48
                                            Accessible.name: text
                                            onClicked: root.beginLsfgInstall()
                                        }
                                        Button {
                                            visible: root.lsfgSystemData.state === "ready"
                                            text: qsTr("Verificado · %1").arg(
                                                root.lsfgSystemData.version || "1.0.0"
                                            )
                                            enabled: false
                                            Layout.minimumHeight: 48
                                            Accessible.name: text
                                        }
                                        Button {
                                            visible: root.lsfgLastOperationId.length > 0
                                                || Boolean(root.lsfgSystemData.lastOperationId)
                                            text: qsTr("Desfazer")
                                            Layout.minimumHeight: 48
                                            Accessible.name: qsTr("Desfazer última instalação LSFG-VK")
                                            onClicked: root.requestAction("lsfg.rollback", {
                                                "operationId": root.lsfgLastOperationId.length > 0
                                                    ? root.lsfgLastOperationId
                                                    : String(root.lsfgSystemData.lastOperationId)
                                            }, function(response) {
                                                root.lsfgLastOperationId = ""
                                                root.refreshStatus(response.message || qsTr("LSFG-VK restaurado"))
                                            })
                                        }
                                    }
                                }
                                Label { text: qsTr("Diagnóstico"); color: root.textColor; font.pixelSize: 20; font.bold: true; Layout.leftMargin: 28 }
                                Repeater {
                                    model: root.desktopStatus.dashboard && root.desktopStatus.dashboard.doctor
                                        ? root.desktopStatus.dashboard.doctor.checks || [] : []
                                    delegate: Rectangle {
                                        required property var modelData
                                        color: root.surfaceColor
                                        radius: 7
                                        border.color: root.borderColor
                                        Layout.fillWidth: true
                                        Layout.leftMargin: 28
                                        Layout.rightMargin: 28
                                        Layout.minimumHeight: 58
                                        RowLayout {
                                            anchors.fill: parent
                                            anchors.margins: 14
                                            ToolButton {
                                                enabled: false
                                                icon.name: modelData.status === "pass" ? "dialog-ok-apply" : modelData.status === "warn" ? "dialog-warning" : "dialog-error"
                                                icon.color: modelData.status === "pass" ? root.greenColor : modelData.status === "warn" ? root.amberColor : root.redColor
                                                background: Item {}
                                            }
                                            ColumnLayout {
                                                Layout.fillWidth: true
                                                Label { text: modelData.name; color: root.textColor; font.bold: true }
                                                Label { text: modelData.message; color: root.mutedColor; font.pixelSize: 12; elide: Text.ElideMiddle; Layout.fillWidth: true }
                                            }
                                        }
                                    }
                                }
                                Label {
                                    text: qsTr("Operações recentes")
                                    color: root.textColor
                                    font.pixelSize: 20
                                    font.bold: true
                                    Layout.leftMargin: 28
                                }
                                Repeater {
                                    model: root.desktopStatus.dashboard
                                        && root.desktopStatus.dashboard.diagnostics
                                        && root.desktopStatus.dashboard.diagnostics.operations
                                        ? root.desktopStatus.dashboard.diagnostics.operations.items || [] : []
                                    delegate: Rectangle {
                                        required property var modelData
                                        color: root.surfaceColor
                                        radius: 7
                                        border.color: root.borderColor
                                        Layout.fillWidth: true
                                        Layout.leftMargin: 28
                                        Layout.rightMargin: 28
                                        Layout.minimumHeight: operationColumn.implicitHeight + 24
                                        ColumnLayout {
                                            id: operationColumn
                                            anchors.fill: parent
                                            anchors.margins: 12
                                            Label {
                                                text: qsTr("%1 • %2")
                                                    .arg(modelData.operation)
                                                    .arg(modelData.state)
                                                color: root.textColor
                                                font.bold: true
                                            }
                                            Label {
                                                text: qsTr("%1 • %2 • rollback %3")
                                                    .arg(modelData.timestamp || qsTr("sem horário"))
                                                    .arg(modelData.target || qsTr("alvo sanitizado"))
                                                    .arg(modelData.rollbackAvailable
                                                        ? qsTr("disponível") : qsTr("indisponível"))
                                                color: root.mutedColor
                                                wrapMode: Text.WordWrap
                                                Layout.fillWidth: true
                                            }
                                        }
                                    }
                                }
                                Rectangle {
                                    color: root.surfaceColor
                                    radius: 7
                                    border.color: root.borderColor
                                    Layout.fillWidth: true
                                    Layout.leftMargin: 28
                                    Layout.rightMargin: 28
                                    Layout.minimumHeight: sessionDiagnosticsColumn.implicitHeight + 24
                                    ColumnLayout {
                                        id: sessionDiagnosticsColumn
                                        anchors.fill: parent
                                        anchors.margins: 12
                                        Label { text: qsTr("Sessão e recovery"); color: root.textColor; font.bold: true }
                                        Label {
                                            text: root.desktopStatus.dashboard
                                                && root.desktopStatus.dashboard.diagnostics
                                                && root.desktopStatus.dashboard.diagnostics.sessionRecovery
                                                ? root.desktopStatus.dashboard.diagnostics.sessionRecovery.reason
                                                : qsTr("Contrato de recovery não publicado.")
                                            color: root.mutedColor
                                            wrapMode: Text.WordWrap
                                            Layout.fillWidth: true
                                        }
                                    }
                                }
                                RowLayout {
                                    Layout.leftMargin: 28
                                    Layout.rightMargin: 28
                                    Button {
                                        text: qsTr("Exportar estado")
                                        icon.name: "document-export"
                                        Layout.minimumHeight: 48
                                        onClicked: root.beginDiagnosticsExport("state")
                                    }
                                    Button {
                                        text: qsTr("Pacote de suporte")
                                        icon.name: "tools-report-bug"
                                        Layout.minimumHeight: 48
                                        onClicked: root.beginDiagnosticsExport("support")
                                    }
                                    Button {
                                        text: qsTr("Saúde administrativa")
                                        icon.name: "security-high"
                                        Layout.minimumHeight: 48
                                        onClicked: root.requestAction("admin.health", {}, function(response) {
                                            root.notify(response.detail || response.state, false)
                                        })
                                    }
                                }
                                RowLayout {
                                    Layout.leftMargin: 28
                                    Layout.rightMargin: 28
                                    Button {
                                        text: qsTr("Executar verificação")
                                        icon.name: "view-refresh"
                                        Layout.minimumHeight: 48
                                        Accessible.name: text
                                        onClicked: root.refreshStatus(qsTr("Diagnóstico atualizado"))
                                    }
                                    Button {
                                        text: qsTr("Abrir teclado virtual")
                                        icon.name: "input-keyboard-virtual"
                                        Layout.minimumHeight: 48
                                        Accessible.name: text
                                        onClicked: root.openKeyboard()
                                    }
                                    Button {
                                        visible: root.desktopStatus.recoveryRequired
                                        text: qsTr("Restaurar estado seguro")
                                        icon.name: "security-medium"
                                        Layout.minimumHeight: 48
                                        Accessible.name: text
                                        onClicked: recoveryDialog.open()
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        Rectangle {
            id: handheldFooter
            color: "#080d13"
            border.color: root.borderColor
            Layout.fillWidth: true
            Layout.preferredHeight: root.compactLayout ? 44 : 54
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: root.compactLayout ? 12 : 20
                anchors.rightMargin: root.compactLayout ? 12 : 20
                spacing: root.compactLayout ? 12 : 24
                Label { text: qsTr("STEAM  MENU"); color: root.mutedColor; font.bold: true }
                Item { Layout.fillWidth: true }
                Label { visible: !root.compactLayout; text: qsTr("D-PAD  NAVEGAR"); color: root.mutedColor }
                Label { text: qsTr("A  SELECIONAR"); color: root.textColor }
                Label { visible: !root.compactLayout; text: qsTr("X  AÇÃO DE CONTEXTO"); color: root.textColor }
                Label { text: qsTr("B  VOLTAR"); color: root.textColor }
            }
        }
    }

    Rectangle {
        visible: root.lastRequest.length > 0
        z: 1000
        width: Math.min(520, root.width - 40)
        height: feedbackLabel.implicitHeight + 28
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.rightMargin: 20
        anchors.bottomMargin: root.compactLayout ? 54 : 68
        color: root.lastRequestIsError ? "#35171b" : "#102b20"
        radius: 8
        border.color: root.lastRequestIsError ? root.redColor : root.greenColor
        Label {
            id: feedbackLabel
            anchors.fill: parent
            anchors.margins: 14
            text: root.lastRequest
            color: root.textColor
            wrapMode: Text.WordWrap
            Accessible.name: text
        }
    }
}
