// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: root
    width: 1280
    height: 800
    minimumWidth: 720
    minimumHeight: 560
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
    palette.highlightedText: textColor
    palette.toolTipBase: raisedColor
    palette.toolTipText: textColor
    palette.disabled.buttonText: "#667481"
    palette.disabled.text: "#667481"

    readonly property var desktopContext: desktopStatus.context || ({})
    readonly property bool handheldDevice: desktopContext.deviceKind
        && String(desktopContext.deviceKind).indexOf("deck-") === 0
    readonly property var connectedDisplays: desktopContext.displays || []
    readonly property var primaryDisplay: connectedDisplays.find(function(display) {
        return display.connected && (display.internal || connectedDisplays.length === 1)
    }) || connectedDisplays.find(function(display) { return display.connected }) || ({})
    readonly property bool televisionMode: connectedDisplays.some(function(display) {
        return display.connected && !display.internal && (display.width || 0) >= 3840
    }) && !desktopContext.externalKeyboard && !desktopContext.externalMouse
    property bool reducedMotionPreference: false
    property bool highContrastPreference: false

    UiTokens {
        id: ui
        viewportWidth: root.width
        viewportHeight: root.height
        handheld: root.handheldDevice
        television: root.televisionMode
        highContrast: root.highContrastPreference
        reducedMotion: root.reducedMotionPreference
    }

    readonly property color backgroundColor: ui.background
    readonly property color sidebarColor: ui.sidebar
    readonly property color surfaceColor: ui.surface
    readonly property color raisedColor: ui.raised
    readonly property color borderColor: ui.border
    readonly property color textColor: ui.text
    readonly property color mutedColor: ui.muted
    readonly property color cyanColor: ui.cyan
    readonly property color cyanDarkColor: ui.cyanDark
    readonly property color amberColor: ui.amber
    readonly property color greenColor: ui.green
    readonly property color redColor: ui.red
    readonly property string compositionProfile: ui.composition
    readonly property bool compactLayout: ui.compact
    readonly property int sidebarLogicalWidth: ui.sidebarWidth
    readonly property int minimumInteractiveTarget: ui.targetSize
    readonly property bool motionReduced: ui.reducedMotion

    property var desktopStatus: ({
        "effectiveProfile": "handheld-desktop",
        "recommendedProfile": "handheld-desktop",
        "recoveryRequired": false,
        "independentRuntime": true,
        "context": {"deviceKind": "deck-lcd", "displays": [], "capabilities": [], "conflicts": []},
        "dashboard": {"components": [], "steam": [], "sync": {}, "doctor": {"checks": []}}
    })
    property var fallbackComponents: [
        {
            "id": "dolphin", "name": "Dolphin", "description": "Emulador de Wii e GameCube",
            "iconName": "dolphin-emu", "systems": ["Wii", "GameCube"], "state": "missing",
            "statusLabel": "Não instalado", "versionLabel": "—", "targetVersion": "—",
            "detail": "O status será atualizado quando a bridge local responder.",
            "blockedReason": "", "action": {"kind": "detail", "label": "Ver detalhes", "enabled": true}
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
            "blockedReason": "", "action": {"kind": "detail", "label": "Ver detalhes", "enabled": true}
        }
    ]
    property var fallbackSteam: [
        {
            "id": "steam-client", "name": "Cliente Steam", "description": "Cliente oficial e modo Big Picture",
            "iconName": "steam", "state": "missing", "statusLabel": "Verificando", "versionLabel": "—",
            "detail": "O estado do Steam será atualizado pela bridge local.",
            "action": {"kind": "detail", "label": "Ver detalhes", "enabled": true}
        }
    ]
    readonly property var emulatorItems: desktopStatus.dashboard && desktopStatus.dashboard.components
        ? desktopStatus.dashboard.components : fallbackComponents
    readonly property var steamItems: desktopStatus.dashboard && desktopStatus.dashboard.steam
        ? desktopStatus.dashboard.steam : fallbackSteam
    readonly property var filteredEmulatorItems: filterRows(emulatorItems, emulatorFilter)
    readonly property var filteredSteamItems: filterRows(steamItems, steamFilter)
    readonly property bool hasConflicts: desktopStatus.context
        && desktopStatus.context.conflicts && desktopStatus.context.conflicts.length > 0
    readonly property int syncPending: desktopStatus.dashboard && desktopStatus.dashboard.sync
        ? desktopStatus.dashboard.sync.pending || 0 : 0
    readonly property int syncConflicted: desktopStatus.dashboard && desktopStatus.dashboard.sync
        ? desktopStatus.dashboard.sync.conflicted || 0 : 0
    readonly property int syncDone: desktopStatus.dashboard && desktopStatus.dashboard.sync
        ? desktopStatus.dashboard.sync.done || 0 : 0
    readonly property int syncTotal: syncPending + syncConflicted + syncDone
    readonly property string doctorState: desktopStatus.dashboard && desktopStatus.dashboard.doctor
        ? desktopStatus.dashboard.doctor.state || "unverified" : "unverified"
    readonly property bool environmentReady: !hasConflicts && !desktopStatus.recoveryRequired
        && doctorState !== "failed"

    property int sectionIndex: 1
    property int emulatorFilter: 0
    property int steamFilter: 0
    property var selectedEmulator: null
    property var selectedSteam: null
    property string selectedProfile: "auto"
    property var currentPlan: null
    property var conflictPlan: null
    property var componentPlan: null
    property string apiUrl: ""
    property string apiToken: ""
    property string lastRequest: ""
    property bool lastRequestIsError: false
    property int pendingRequests: 0
    property bool recoveryPromptShown: false
    property bool loadingOverlayVisible: false
    property string loadingTitle: qsTr("Preparando tudo para você")
    property string loadingDetail: qsTr("Aguarde enquanto o SteamZero verifica o estado com segurança.")
    property bool alertExpanded: true
    property bool syncExplanationVisible: false
    property Item emulatorDrawerReturnItem: null
    property Item steamDrawerReturnItem: null
    property Item conflictDialogReturnItem: null
    property Item componentDialogReturnItem: null
    property Item resetDialogReturnItem: null
    property Item recoveryDialogReturnItem: null
    property var sectionHistory: []
    property var sectionFocusItems: ({})

    signal planRequested(string profile)
    signal recoveryRequested()
    signal keyboardRequested()

    onEmulatorFilterChanged: ensureEmulatorSelection()
    onSteamFilterChanged: ensureSteamSelection()
    onHasConflictsChanged: {
        if (hasConflicts)
            alertExpanded = true
    }
    onPendingRequestsChanged: {
        if (pendingRequests > 0) {
            loadingDelay.restart()
        } else {
            loadingDelay.stop()
            loadingOverlayVisible = false
        }
    }

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
        reducedMotionPreference = args.indexOf("--steamzero-reduced-motion") >= 0
        highContrastPreference = args.indexOf("--steamzero-high-contrast") >= 0
        if (apiMarker >= 0 && apiMarker + 1 < args.length)
            apiUrl = args[apiMarker + 1]
        if (tokenMarker >= 0 && tokenMarker + 1 < args.length)
            apiToken = args[tokenMarker + 1]
        if (sectionMarker >= 0 && sectionMarker + 1 < args.length) {
            const sections = {"overview": 0, "emulators": 1, "steam": 2, "profiles": 3, "sync": 4, "system": 5}
            if (sections[args[sectionMarker + 1]] !== undefined)
                sectionIndex = sections[args[sectionMarker + 1]]
        }
        selectedProfile = desktopStatus.manualOverride || "auto"
        ensureSelections()
        if (desktopStatus.recoveryRequired) {
            recoveryPromptShown = true
            Qt.callLater(recoveryDialog.open)
        }
    }

    function rememberSectionFocus() {
        if (!root.activeFocusItem)
            return
        const remembered = Object.assign({}, sectionFocusItems)
        remembered[sectionIndex] = root.activeFocusItem
        sectionFocusItems = remembered
    }

    function navigateToSection(index, rememberHistory) {
        const destination = Number(index)
        if (!Number.isInteger(destination) || destination < 0 || destination > 5)
            return
        if (destination === sectionIndex)
            return
        rememberSectionFocus()
        if (rememberHistory !== false) {
            const history = sectionHistory.slice()
            if (history.length === 0 || history[history.length - 1] !== sectionIndex)
                history.push(sectionIndex)
            sectionHistory = history.slice(-12)
        }
        sectionIndex = destination
        Qt.callLater(sectionNavigator.updateActiveSection)
    }

    function restoreFocus(item) {
        if (item)
            Qt.callLater(function() { item.forceActiveFocus(Qt.OtherFocusReason) })
    }

    function openRecoveryDialog() {
        recoveryDialogReturnItem = root.activeFocusItem
        recoveryDialog.open()
    }

    function openSectionMenu() {
        if (!sectionNavigator.visible)
            return
        sectionMenu.returnFocusItem = root.activeFocusItem
        sectionMenu.currentIndex = sectionNavigator.activeIndex
        sectionMenu.open()
    }

    function goBack() {
        if (sectionMenu.opened) {
            sectionMenu.close()
            return
        }
        if (emulatorInspectorDrawer.opened) {
            emulatorInspectorDrawer.close()
            return
        }
        if (steamInspectorDrawer.opened) {
            steamInspectorDrawer.close()
            return
        }
        if (conflictDialog.opened) {
            conflictDialog.close()
            return
        }
        if (componentDialog.opened) {
            componentDialog.close()
            return
        }
        if (resetDialog.opened) {
            resetDialog.close()
            return
        }
        if (recoveryDialog.opened)
            return
        if (sectionHistory.length === 0)
            return
        const history = sectionHistory.slice()
        const destination = history.pop()
        sectionHistory = history
        sectionIndex = destination
        const target = sectionFocusItems[destination]
        restoreFocus(target)
        Qt.callLater(sectionNavigator.updateActiveSection)
    }

    function notify(message, isError) {
        lastRequest = message
        lastRequestIsError = isError === true
        feedbackTimer.restart()
    }

    function errorMessage(response, fallback) {
        if (!response || response.error === undefined)
            return fallback
        if (typeof response.error === "string")
            return response.error
        return response.error.title || response.error.detail || response.error.code || fallback
    }

    function request(method, path, payload, callback) {
        if (!apiUrl || !apiToken) {
            notify(qsTr("Bridge local indisponível; nenhuma mudança foi feita"), true)
            return
        }
        const xhr = new XMLHttpRequest()
        let completed = false
        loadingTitle = requestTitle(path)
        loadingDetail = requestDetail(path)
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
                    root.notify(root.errorMessage(response, qsTr("Ação recusada")), true)
                    return
                }
                callback(response)
            } catch (error) {
                root.notify(qsTr("Resposta inválida; nenhuma mudança adicional foi feita"), true)
            }
        }
        xhr.onerror = function() {
            if (finish())
                root.notify(qsTr("A central local não respondeu; o estado foi preservado"), true)
        }
        xhr.ontimeout = function() {
            if (finish())
                root.notify(qsTr("A operação excedeu o tempo esperado; verifique o estado antes de repetir"), true)
        }
        xhr.send(JSON.stringify(payload || {}))
    }

    function refreshStatus(message) {
        request("GET", "/status", {}, function(response) {
            desktopStatus = response
            currentPlan = null
            selectedProfile = desktopStatus.manualOverride || "auto"
            ensureSelections()
            if (desktopStatus.recoveryRequired && !recoveryPromptShown) {
                recoveryPromptShown = true
                root.openRecoveryDialog()
            }
            if (message)
                notify(message, false)
        })
    }

    function ensureSelections() {
        ensureEmulatorSelection()
        ensureSteamSelection()
    }

    function ensureEmulatorSelection() {
        const emulatorId = selectedEmulator ? selectedEmulator.id : ""
        selectedEmulator = filteredEmulatorItems.find(function(row) { return row.id === emulatorId })
            || (filteredEmulatorItems.length > 0 ? filteredEmulatorItems[0] : null)
        if (!selectedEmulator && emulatorInspectorDrawer.opened)
            emulatorInspectorDrawer.close()
    }

    function ensureSteamSelection() {
        const steamId = selectedSteam ? selectedSteam.id : ""
        selectedSteam = filteredSteamItems.find(function(row) { return row.id === steamId })
            || (filteredSteamItems.length > 0 ? filteredSteamItems[0] : null)
        if (!selectedSteam && steamInspectorDrawer.opened)
            steamInspectorDrawer.close()
    }

    function openEmulatorInspector() {
        if (selectedEmulator)
            emulatorInspectorDrawer.open()
    }

    function openSteamInspector() {
        if (selectedSteam)
            steamInspectorDrawer.open()
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

    function firstInstallableEmulator() {
        return emulatorItems.find(function(row) {
            return row.action && row.action.enabled && row.action.kind === "component-plan"
        }) || null
    }

    function requestTitle(path) {
        if (path === "/component/apply")
            return qsTr("Instalando com segurança")
        if (path === "/apply" || path === "/reset")
            return qsTr("Aplicando o perfil revisado")
        if (path === "/recover")
            return qsTr("Restaurando o último estado seguro")
        if (path === "/steam/open")
            return qsTr("Abrindo a Steam")
        return qsTr("Atualizando o estado")
    }

    function requestDetail(path) {
        if (path === "/component/apply")
            return qsTr("O componente será verificado antes de ficar disponível.")
        if (path === "/recover" || path === "/reset")
            return qsTr("A recuperação preserva jogos, saves e configurações pessoais.")
        return qsTr("Isso pode levar alguns instantes. O contexto atual será preservado.")
    }

    function profileLabel(profileId) {
        const labels = {
            "auto": qsTr("Automático"),
            "handheld": qsTr("Portátil"),
            "handheld-desktop": qsTr("Portátil"),
            "dock": qsTr("Dock"),
            "docked-desktop": qsTr("Dock"),
            "safe": qsTr("Seguro")
        }
        return labels[profileId] || profileId || qsTr("Não verificado")
    }

    function observedProfileId() {
        const current = desktopStatus.current || {}
        return current.profile && current.profile.id ? current.profile.id : ""
    }

    function profileMatches(candidate, effective) {
        if (candidate === "handheld")
            return effective === "handheld" || effective === "handheld-desktop"
        if (candidate === "dock")
            return effective === "dock" || effective === "docked-desktop"
        return candidate === effective
    }

    function desiredProfileId() {
        return desktopStatus.manualOverride || "auto"
    }

    function displaySummary() {
        if (!primaryDisplay || !primaryDisplay.width || !primaryDisplay.height)
            return qsTr("Resolução não verificada")
        let displayWidth = primaryDisplay.width
        let displayHeight = primaryDisplay.height
        if (handheldDevice && primaryDisplay.internal && displayHeight > displayWidth) {
            const swap = displayWidth
            displayWidth = displayHeight
            displayHeight = swap
        }
        const scale = primaryDisplay.scale ? qsTr(" · escala %1%").arg(Math.round(primaryDisplay.scale * 100)) : ""
        return qsTr("%1×%2%3").arg(displayWidth).arg(displayHeight).arg(scale)
    }

    function pageTitle() {
        return [qsTr("Visão geral"), qsTr("Emuladores"), qsTr("Steam"),
            qsTr("Perfis do Desktop"), qsTr("Saves e Sync"), qsTr("Sistema e recuperação")][sectionIndex]
    }

    function currentScrollTarget() {
        if (sectionIndex === 0)
            return overviewScroll.contentItem
        if (sectionIndex === 3)
            return profilesScroll.contentItem
        if (sectionIndex === 4)
            return syncScroll.contentItem
        if (sectionIndex === 5)
            return systemScroll.contentItem
        return null
    }

    function currentSections() {
        if (sectionIndex === 0)
            return [
                {"label": qsTr("Contexto"), "item": overviewHeaderAnchor},
                {"label": qsTr("Prontidão"), "item": overviewReadinessAnchor},
                {"label": qsTr("Áreas principais"), "item": overviewAreasAnchor}
            ]
        if (sectionIndex === 3) {
            const sections = [
                {"label": qsTr("Estado dos perfis"), "item": profilesHeaderAnchor},
                {"label": qsTr("Escolher perfil"), "item": profilesChoicesAnchor}
            ]
            if (profilesPlanAnchor.visible)
                sections.push({"label": qsTr("Plano revisado"), "item": profilesPlanAnchor})
            return sections
        }
        if (sectionIndex === 4) {
            const sections = [
                {"label": qsTr("Estado da sincronização"), "item": syncHeaderAnchor},
                {"label": root.syncTotal === 0 ? qsTr("Fila vazia") : qsTr("Resumo da fila"),
                 "item": root.syncTotal === 0 ? syncEmptyAnchor : syncSummaryAnchor}
            ]
            if (syncExplanationAnchor.visible)
                sections.push({"label": qsTr("Como funciona"), "item": syncExplanationAnchor})
            return sections
        }
        if (sectionIndex === 5) {
            const sections = [{"label": qsTr("Contexto do sistema"), "item": systemHeaderAnchor}]
            if (systemAttentionAnchor.visible)
                sections.push({"label": qsTr("Ação necessária"), "item": systemAttentionAnchor})
            sections.push({"label": qsTr("Diagnóstico"), "item": systemDoctorAnchor})
            sections.push({"label": qsTr("Ações seguras"), "item": systemActionsAnchor})
            return sections
        }
        return []
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
            componentDialogReturnItem = root.activeFocusItem
            request("POST", "/component/plan", {"componentId": row.id}, function(response) {
                componentPlan = response.plan
                componentDialog.open()
            })
        } else if (kind === "component-launch") {
            request("POST", "/component/launch", {"componentId": row.id}, function(response) {
                notify(qsTr("%1 foi aberto").arg(row.name), false)
            })
        } else if (kind === "steam-open") {
            request("POST", "/steam/open", {"target": row.action.target}, function(response) {
                notify(qsTr("Steam aberto com segurança"), false)
                refreshStatus("")
            })
        } else if (kind === "keyboard") {
            openKeyboard()
        }
    }

    function beginConflictResolution() {
        if (!desktopStatus.conflictActions || desktopStatus.conflictActions.length === 0) {
            notify(qsTr("Este conflito não possui correção automática allowlisted"), true)
            return
        }
        conflictDialogReturnItem = root.activeFocusItem
        const action = desktopStatus.conflictActions[0]
        request("POST", "/conflict/plan", {"actionId": action.actionId}, function(response) {
            conflictPlan = response.plan
            conflictDialog.open()
        })
    }

    function beginQuickReset() {
        resetDialogReturnItem = root.activeFocusItem
        request("POST", "/plan", {"profile": "safe"}, function(response) {
            currentPlan = response.plan
            resetDialog.open()
        })
    }

    function openKeyboard() {
        keyboardRequested()
        request("POST", "/keyboard", {}, function(response) {
            notify(qsTr("Teclado aberto por %1").arg(response.provider), false)
        })
    }

    Component.onCompleted: parseArguments()

    Timer {
        id: feedbackTimer
        interval: root.lastRequestIsError ? 10000 : 5000
        onTriggered: root.lastRequest = ""
    }
    Timer {
        id: loadingDelay
        interval: 280
        repeat: false
        onTriggered: {
            if (root.pendingRequests > 0)
                root.loadingOverlayVisible = true
        }
    }
    Shortcut {
        sequence: "PgUp"
        enabled: sectionNavigator.visible
        onActivated: sectionNavigator.previousSection()
    }
    Shortcut {
        sequence: "PgDown"
        enabled: sectionNavigator.visible
        onActivated: sectionNavigator.nextSection()
    }
    Shortcut {
        sequence: "F6"
        enabled: sectionNavigator.visible
        onActivated: root.openSectionMenu()
    }
    Shortcut {
        sequence: "Escape"
        onActivated: root.goBack()
    }

    Dialog {
        id: conflictDialog
        title: qsTr("Resolver conflito de controle")
        modal: true
        closePolicy: Popup.NoAutoClose
        width: Math.min(root.width - 48, 720)
        x: (root.width - width) / 2
        y: (root.height - height) / 2
        standardButtons: Dialog.NoButton
        onClosed: {
            const target = root.conflictDialogReturnItem
            root.conflictDialogReturnItem = null
            root.restoreFocus(target)
        }

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
            GridLayout {
                columns: ui.compact ? 1 : 2
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
                        root.request("POST", "/conflict/apply", {
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
        title: root.componentPlan
            ? (root.componentPlan.action === "install" ? qsTr("Revisar instalação") : qsTr("Revisar atualização"))
            : qsTr("Revisar componente")
        modal: true
        closePolicy: Popup.NoAutoClose
        width: Math.min(root.width - 48, 720)
        x: (root.width - width) / 2
        y: (root.height - height) / 2
        standardButtons: Dialog.NoButton
        onClosed: {
            const target = root.componentDialogReturnItem
            root.componentDialogReturnItem = null
            root.restoreFocus(target)
        }
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
            GridLayout {
                columns: ui.compact ? 1 : 2
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
                        root.request("POST", "/component/apply", {
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
        id: resetDialog
        title: qsTr("Restauração rápida")
        modal: true
        closePolicy: Popup.NoAutoClose
        width: Math.min(root.width - 48, 620)
        x: (root.width - width) / 2
        y: (root.height - height) / 2
        standardButtons: Dialog.NoButton
        onClosed: {
            const target = root.resetDialogReturnItem
            root.resetDialogReturnItem = null
            root.restoreFocus(target)
        }
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
            GridLayout {
                columns: ui.compact ? 1 : 2
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
                        root.request("POST", "/reset", {
                            "planId": root.currentPlan.planId,
                            "confirmToken": root.currentPlan.confirmToken
                        }, function(response) {
                            resetDialog.close()
                            root.refreshStatus(qsTr("Restauração rápida concluída"))
                        })
                    }
                }
            }
        }
    }

    Dialog {
        id: recoveryDialog
        title: qsTr("Alteração incompleta detectada")
        modal: true
        closePolicy: Popup.NoAutoClose
        width: Math.min(root.width - 48, 650)
        x: (root.width - width) / 2
        y: (root.height - height) / 2
        standardButtons: Dialog.NoButton
        onClosed: {
            const target = root.recoveryDialogReturnItem
            root.recoveryDialogReturnItem = null
            root.restoreFocus(target)
        }
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
                    root.request("POST", "/recover", {}, function(response) {
                        recoveryDialog.close()
                        root.refreshStatus(qsTr("Recuperação concluída com segurança"))
                    })
                }
            }
        }
    }

    SectionMenu {
        id: sectionMenu
        width: Math.min(root.width - 32, 420)
        x: Math.round((root.width - width) / 2)
        y: Math.round((root.height - height) / 2)
        sections: root.currentSections()
        surfaceColor: root.raisedColor
        borderColor: root.borderColor
        textColor: root.textColor
        mutedColor: root.mutedColor
        accentColor: root.cyanColor
        onSectionChosen: function(index) { sectionNavigator.goTo(index) }
    }

    AdaptiveInspector {
        id: emulatorInspectorDrawer
        returnFocusItem: root.emulatorDrawerReturnItem
        panelColor: root.surfaceColor
        borderColor: root.borderColor

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: ui.pageMargin
            spacing: ui.gap

            RowLayout {
                Layout.fillWidth: true
                Label {
                    text: root.selectedEmulator ? root.selectedEmulator.name : qsTr("Emulador")
                    color: root.textColor
                    font.pixelSize: ui.sectionTitleSize
                    font.bold: true
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                ToolButton {
                    text: "×"
                    icon.name: "window-close"
                    font.pixelSize: 22
                    Layout.minimumWidth: ui.targetSize
                    Layout.minimumHeight: ui.targetSize
                    Accessible.name: qsTr("Fechar detalhes do emulador")
                    onClicked: emulatorInspectorDrawer.close()
                }
            }
            Label {
                text: root.selectedEmulator ? root.selectedEmulator.statusLabel : qsTr("Não verificado")
                color: root.selectedEmulator ? root.stateColor(root.selectedEmulator.state) : root.mutedColor
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
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
                text: root.selectedEmulator ? root.selectedEmulator.action.label : ""
                enabled: root.selectedEmulator && root.selectedEmulator.action.enabled
                icon.name: "go-next"
                Layout.fillWidth: true
                Layout.minimumHeight: ui.targetSize
                Accessible.name: text
                onClicked: root.performRowAction(root.selectedEmulator)
            }
        }
    }

    AdaptiveInspector {
        id: steamInspectorDrawer
        returnFocusItem: root.steamDrawerReturnItem
        panelColor: root.surfaceColor
        borderColor: root.borderColor

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: ui.pageMargin
            spacing: ui.gap

            RowLayout {
                Layout.fillWidth: true
                Label {
                    text: root.selectedSteam ? root.selectedSteam.name : "Steam"
                    color: root.textColor
                    font.pixelSize: ui.sectionTitleSize
                    font.bold: true
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                ToolButton {
                    text: "×"
                    icon.name: "window-close"
                    font.pixelSize: 22
                    Layout.minimumWidth: ui.targetSize
                    Layout.minimumHeight: ui.targetSize
                    Accessible.name: qsTr("Fechar detalhes da Steam")
                    onClicked: steamInspectorDrawer.close()
                }
            }
            Label {
                text: root.selectedSteam ? root.selectedSteam.statusLabel : qsTr("Não verificado")
                color: root.selectedSteam ? root.stateColor(root.selectedSteam.state) : root.mutedColor
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
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
                text: qsTr("A tarefa abre na Steam. Ao retornar, sua seção e seleção continuam aqui.")
                color: root.mutedColor
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Item { Layout.fillHeight: true }
            DarkButton {
                text: root.selectedSteam ? root.selectedSteam.action.label : ""
                enabled: root.selectedSteam && root.selectedSteam.action.enabled
                icon.name: "steam"
                Layout.fillWidth: true
                Layout.minimumHeight: ui.targetSize
                Accessible.name: text
                onClicked: root.performRowAction(root.selectedSteam)
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            Rectangle {
                id: sidebar
                color: root.sidebarColor
                Layout.preferredWidth: ui.sidebarWidth
                Layout.minimumWidth: ui.sidebarWidth
                Layout.maximumWidth: ui.sidebarWidth
                Layout.fillHeight: true
                border.color: root.borderColor
                border.width: 1

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: ui.compact ? 8 : 14
                    spacing: ui.compact ? 5 : 8

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.minimumHeight: ui.compact ? 56 : 72
                        Image {
                            source: "../assets/steamzero-mark.png"
                            sourceSize.width: 48
                            sourceSize.height: 48
                            fillMode: Image.PreserveAspectFit
                            Layout.preferredWidth: ui.compact ? 42 : 48
                            Layout.preferredHeight: ui.compact ? 42 : 48
                            Layout.alignment: Qt.AlignHCenter
                            Accessible.name: qsTr("Marca SteamZero")
                        }
                        ColumnLayout {
                            visible: !ui.compact
                            spacing: 0
                            Label {
                                text: "STEAMZERO"
                                color: root.textColor
                                font.pixelSize: 19
                                font.bold: true
                            }
                            Label {
                                visible: !ui.compact
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
                            {"label": qsTr("Emuladores"), "icon": "input-gaming"},
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
                            Layout.minimumHeight: 48
                            leftPadding: ui.compact ? 6 : 14
                            rightPadding: ui.compact ? 6 : 12
                            spacing: ui.compact ? 0 : 12
                            Accessible.name: text
                            ToolTip.visible: ui.compact && hovered
                            ToolTip.text: text
                            KeyNavigation.up: index > 0 ? navRepeater.itemAt(index - 1) : quickResetButton
                            KeyNavigation.down: index + 1 < navRepeater.count
                                ? navRepeater.itemAt(index + 1) : attentionButton
                            onClicked: root.navigateToSection(index)
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
                                spacing: 12
                                ToolButton {
                                    enabled: false
                                    icon.name: modelData.icon
                                    icon.color: root.sectionIndex === index ? root.cyanColor : root.mutedColor
                                    icon.width: 24
                                    icon.height: 24
                                    background: Item {}
                                    Layout.preferredWidth: 28
                                }
                                Label {
                                    visible: ui.compact
                                    text: modelData.label.charAt(0)
                                    color: root.sectionIndex === index ? root.cyanColor : root.textColor
                                    font.pixelSize: 18
                                    font.bold: true
                                    horizontalAlignment: Text.AlignHCenter
                                    Layout.fillWidth: true
                                }
                                Label {
                                    visible: !ui.compact
                                    text: modelData.label
                                    color: root.sectionIndex === index ? root.cyanColor : root.textColor
                                    font.pixelSize: 15
                                    Layout.fillWidth: true
                                    elide: Text.ElideRight
                                }
                            }
                        }
                    }

                    Button {
                        id: attentionButton
                        visible: root.hasConflicts || root.desktopStatus.recoveryRequired
                        text: root.hasConflicts
                            ? qsTr("%1 ação necessária").arg(root.desktopContext.conflicts.length)
                            : qsTr("Recuperação pendente")
                        icon.name: "security-high"
                        Layout.fillWidth: true
                        Layout.minimumHeight: 54
                        Accessible.name: text
                        ToolTip.visible: ui.compact && hovered
                        ToolTip.text: text
                        KeyNavigation.up: navRepeater.itemAt(navRepeater.count - 1)
                        KeyNavigation.down: quickResetButton
                        onClicked: root.navigateToSection(5)
                        background: Rectangle { color: "#211a10"; radius: 7; border.color: "#59401f" }
                        contentItem: RowLayout {
                            ToolButton {
                                enabled: false
                                icon.name: "security-high"
                                icon.color: root.amberColor
                                background: Item {}
                            }
                            Label {
                                visible: ui.compact
                                text: "!"
                                color: root.amberColor
                                font.pixelSize: 20
                                font.bold: true
                                horizontalAlignment: Text.AlignHCenter
                                Layout.fillWidth: true
                            }
                            ColumnLayout {
                                visible: !ui.compact
                                spacing: 1
                                Label { text: attentionButton.text; color: root.amberColor; font.bold: true }
                                Label { text: qsTr("Requer sua atenção"); color: root.mutedColor; font.pixelSize: 12 }
                            }
                        }
                    }

                    Item { Layout.fillHeight: true }

                    Label {
                        visible: !ui.compact
                        text: qsTr("AÇÕES DO SISTEMA")
                        color: root.mutedColor
                        font.pixelSize: 11
                        font.capitalization: Font.AllUppercase
                    }
                    DarkButton {
                        id: quickResetButton
                        text: ui.compact ? "↶" : qsTr("Restauração rápida")
                        icon.name: "edit-undo"
                        display: ui.compact ? AbstractButton.TextOnly : AbstractButton.TextBesideIcon
                        palette.buttonText: root.textColor
                        Layout.fillWidth: true
                        Layout.minimumHeight: 48
                        Accessible.name: qsTr("Restauração rápida")
                        ToolTip.visible: ui.compact && hovered
                        ToolTip.text: Accessible.name
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
                        visible: !ui.compact
                        text: qsTr("Sincronização em nuvem")
                        icon.name: "folder-cloud"
                        palette.buttonText: root.textColor
                        Layout.fillWidth: true
                        Layout.minimumHeight: 48
                        Accessible.name: text
                        background: Rectangle {
                            color: cloudSyncButton.activeFocus ? root.raisedColor : root.surfaceColor
                            radius: 6
                            border.color: cloudSyncButton.activeFocus ? root.cyanColor : root.borderColor
                            border.width: cloudSyncButton.activeFocus ? 2 : 1
                        }
                        KeyNavigation.up: quickResetButton
                        KeyNavigation.down: doctorButton
                        onClicked: root.navigateToSection(4)
                    }
                    DarkButton {
                        id: doctorButton
                        visible: !ui.compact
                        text: qsTr("Diagnóstico do sistema")
                        icon.name: "tools-report-bug"
                        palette.buttonText: root.textColor
                        Layout.fillWidth: true
                        Layout.minimumHeight: 48
                        Accessible.name: text
                        background: Rectangle {
                            color: doctorButton.activeFocus ? root.raisedColor : root.surfaceColor
                            radius: 6
                            border.color: doctorButton.activeFocus ? root.cyanColor : root.borderColor
                            border.width: doctorButton.activeFocus ? 2 : 1
                        }
                        KeyNavigation.up: cloudSyncButton
                        KeyNavigation.down: navRepeater.itemAt(0)
                        onClicked: root.navigateToSection(5)
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Label {
                            visible: !ui.compact
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

            Item {
                visible: ui.wide
                Layout.fillWidth: true
                Layout.fillHeight: true
            }

            Rectangle {
                color: root.backgroundColor
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.maximumWidth: ui.maximumContentWidth
                Layout.alignment: Qt.AlignHCenter

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 0

                    Rectangle {
                        visible: root.hasConflicts && root.sectionIndex !== 5
                        color: "#24180b"
                        border.color: root.amberColor
                        border.width: 1
                        radius: 8
                        Layout.fillWidth: true
                        Layout.leftMargin: ui.pageMargin
                        Layout.rightMargin: ui.pageMargin
                        Layout.topMargin: ui.compact ? 8 : 12
                        Layout.preferredHeight: root.alertExpanded ? 82 : 56

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 18
                            anchors.rightMargin: 14
                            spacing: 12
                            ToolButton {
                                enabled: false
                                icon.name: "dialog-warning"
                                icon.color: root.amberColor
                                icon.width: 30
                                icon.height: 30
                                background: Item {}
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 2
                                RowLayout {
                                    Label {
                                        text: root.alertExpanded
                                            ? qsTr("Outro serviço controla o Desktop")
                                            : qsTr("Desktop degradado · %1 problema").arg(root.desktopContext.conflicts.length)
                                        color: root.amberColor
                                        font.pixelSize: 17
                                        font.bold: true
                                    }
                                    Label {
                                        visible: root.alertExpanded && !ui.compact
                                        text: "E-DESKTOP-OWNER-CONFLICT"
                                        color: "#d5b47d"
                                        font.pixelSize: 11
                                    }
                                }
                                Label {
                                    visible: root.alertExpanded
                                    text: qsTr("Algumas ações estão bloqueadas até o conflito ser resolvido.")
                                    color: root.textColor
                                    font.pixelSize: 13
                                    wrapMode: Text.WordWrap
                                    Layout.fillWidth: true
                                }
                            }
                            ToolButton {
                                icon.name: root.alertExpanded ? "arrow-up" : "arrow-down"
                                icon.color: root.mutedColor
                                Layout.minimumWidth: 48
                                Layout.minimumHeight: 48
                                Accessible.name: root.alertExpanded ? qsTr("Recolher alerta") : qsTr("Expandir alerta")
                                onClicked: root.alertExpanded = !root.alertExpanded
                            }
                            DarkButton {
                                id: resolveBannerButton
                                text: root.alertExpanded ? qsTr("Resolver agora") : qsTr("Ver diagnóstico")
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
                                    if (root.alertExpanded)
                                        root.beginConflictResolution()
                                    else
                                        root.navigateToSection(5)
                                }
                            }
                        }
                    }

                    StackLayout {
                        currentIndex: root.sectionIndex
                        Layout.fillWidth: true
                        Layout.fillHeight: true

                        // Visão geral
                        ScrollView {
                            id: overviewScroll
                            clip: true
                            contentWidth: availableWidth
                            ColumnLayout {
                                id: overviewContent
                                width: parent.width - 72
                                spacing: ui.gap
                                Label {
                                    id: overviewHeaderAnchor
                                    text: qsTr("Visão geral")
                                    color: root.textColor
                                    font.pixelSize: ui.pageTitleSize
                                    font.bold: true
                                    Layout.topMargin: ui.pageMargin
                                    Layout.leftMargin: ui.pageMargin
                                }
                                Label {
                                    text: root.deviceSummary()
                                    color: root.mutedColor
                                    font.pixelSize: ui.bodySize
                                    wrapMode: Text.WordWrap
                                    Layout.fillWidth: true
                                    Layout.leftMargin: ui.pageMargin
                                    Layout.rightMargin: ui.pageMargin
                                }
                                Rectangle {
                                    id: overviewReadinessAnchor
                                    Layout.fillWidth: true
                                    Layout.leftMargin: ui.pageMargin
                                    Layout.rightMargin: ui.pageMargin
                                    implicitHeight: overviewStatusContent.implicitHeight + 40
                                    color: root.surfaceColor
                                    radius: 10
                                    border.color: root.borderColor
                                    RowLayout {
                                        id: overviewStatusContent
                                        anchors.fill: parent
                                        anchors.margins: 20
                                        spacing: 22
                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            Label {
                                                text: root.environmentReady
                                                    ? qsTr("Pronto para configurar") : qsTr("Ação necessária")
                                                color: root.environmentReady ? root.greenColor : root.amberColor
                                                font.pixelSize: ui.sectionTitleSize
                                                font.bold: true
                                            }
                                            Label {
                                                text: root.hasConflicts
                                                    ? qsTr("Libere o controle do Desktop para revisar e aplicar configurações.")
                                                    : root.desktopStatus.recoveryRequired
                                                        ? qsTr("Restaure o último estado seguro antes de continuar.")
                                                        : root.observedProfileId().length > 0
                                                            ? qsTr("O ambiente está disponível. Último perfil aplicado: %1.").arg(root.profileLabel(root.observedProfileId()))
                                                            : qsTr("O ambiente está disponível. Ainda não há um perfil aplicado verificado.")
                                                color: root.textColor
                                                wrapMode: Text.WordWrap
                                                Layout.fillWidth: true
                                            }
                                        }
                                        Button {
                                            text: root.hasConflicts ? qsTr("Resolver conflito")
                                                : root.desktopStatus.recoveryRequired ? qsTr("Restaurar estado") : qsTr("Ver sistema")
                                            Layout.minimumHeight: 48
                                            Accessible.name: text
                                            onClicked: root.hasConflicts ? root.beginConflictResolution()
                                                : root.desktopStatus.recoveryRequired ? root.openRecoveryDialog()
                                                : root.navigateToSection(5)
                                        }
                                    }
                                }
                                Label {
                                    id: overviewAreasAnchor
                                    text: qsTr("Áreas principais")
                                    color: root.textColor
                                    font.pixelSize: ui.sectionTitleSize
                                    font.bold: true
                                    Layout.leftMargin: ui.pageMargin
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
                                        Layout.leftMargin: ui.pageMargin
                                        Layout.rightMargin: ui.pageMargin
                                        implicitHeight: contentItem.implicitHeight + 16
                                        Accessible.name: qsTr("%1: %2").arg(modelData.title).arg(modelData.detail)
                                        onClicked: root.navigateToSection(modelData.target)
                                        contentItem: RowLayout {
                                            ToolButton { enabled: false; icon.name: modelData.icon; icon.color: root.cyanColor; background: Item {} }
                                            ColumnLayout {
                                                Layout.fillWidth: true
                                                Label { text: modelData.title; color: root.textColor; font.bold: true }
                                                Label { text: modelData.detail; color: root.mutedColor; font.pixelSize: ui.labelSize; wrapMode: Text.WordWrap; Layout.fillWidth: true }
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
                            ColumnLayout {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                spacing: 0
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    Layout.margins: ui.pageMargin
                                    spacing: 8
                                    RowLayout {
                                        Layout.fillWidth: true
                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 2
                                            Label { text: qsTr("Gerenciar emuladores"); color: root.textColor; font.pixelSize: ui.pageTitleSize; font.bold: true; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                            Label { text: qsTr("Instale, atualize e restaure configurações com segurança."); color: root.mutedColor; font.pixelSize: ui.bodySize; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                        }
                                        Button {
                                            visible: root.desktopStatus.recoveryRequired
                                            text: qsTr("Estado seguro disponível")
                                            icon.name: "security-medium"
                                            Layout.minimumHeight: 48
                                            Accessible.name: text
                                            onClicked: root.openRecoveryDialog()
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
                                    Layout.leftMargin: ui.pageMargin
                                    Layout.rightMargin: ui.pageMargin
                                    Layout.preferredHeight: 34
                                    Label { text: qsTr("EMULADOR"); color: root.mutedColor; font.pixelSize: 11; Layout.fillWidth: true }
                                    Label { visible: !ui.compact; text: qsTr("ESTADO"); color: root.mutedColor; font.pixelSize: 11; Layout.preferredWidth: 180 }
                                    Label { text: qsTr("AÇÃO"); color: root.mutedColor; font.pixelSize: 11; Layout.preferredWidth: 132 }
                                }
                                ListView {
                                    id: emulatorList
                                    model: root.filteredEmulatorItems
                                    clip: true
                                    spacing: 2
                                    Layout.fillWidth: true
                                    Layout.fillHeight: true
                                    Layout.leftMargin: 8
                                    Layout.rightMargin: 8
                                    currentIndex: root.selectedEmulator
                                        ? root.filteredEmulatorItems.findIndex(function(row) { return row.id === root.selectedEmulator.id }) : -1
                                    footer: EmptyState {
                                        width: emulatorList.width
                                        height: emulatorList.count === 0 ? emulatorList.height : 0
                                        visible: emulatorList.count === 0
                                        iconName: "edit-find"
                                        title: qsTr("Nenhum emulador neste filtro")
                                        description: root.emulatorFilter === 2
                                            ? qsTr("Ainda não há emuladores instalados. Você pode revisar uma instalação segura ou voltar a ver todos.")
                                            : qsTr("Os componentes continuam preservados; apenas o filtro atual não encontrou resultados.")
                                        primaryText: qsTr("Ver todos")
                                        secondaryText: root.firstInstallableEmulator() ? qsTr("Instalar primeiro emulador") : ""
                                        textColor: root.textColor
                                        mutedColor: root.mutedColor
                                        accentColor: root.cyanColor
                                        minimumTarget: ui.targetSize
                                        onPrimaryTriggered: root.emulatorFilter = 0
                                        onSecondaryTriggered: {
                                            const row = root.firstInstallableEmulator()
                                            if (row) {
                                                root.emulatorFilter = 0
                                                root.selectedEmulator = row
                                                root.performRowAction(row)
                                            }
                                        }
                                    }
                                    delegate: ItemDelegate {
                                        id: emulatorDelegate
                                        required property int index
                                        required property var modelData
                                        width: ListView.view.width
                                        height: Math.max(86, implicitContentHeight + 16)
                                        highlighted: root.selectedEmulator && root.selectedEmulator.id === modelData.id
                                        Accessible.name: qsTr("%1, %2").arg(modelData.name).arg(modelData.statusLabel)
                                        KeyNavigation.up: index > 0 ? emulatorList.itemAtIndex(index - 1) : navRepeater.itemAt(1)
                                        KeyNavigation.down: index + 1 < emulatorList.count ? emulatorList.itemAtIndex(index + 1) : navRepeater.itemAt(1)
                                        onClicked: {
                                            root.selectedEmulator = modelData
                                            if (ui.compact) {
                                                root.emulatorDrawerReturnItem = emulatorDelegate
                                                root.openEmulatorInspector()
                                            }
                                        }
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
                                                visible: !ui.compact
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
                                                Layout.preferredWidth: ui.compact ? 116 : 132
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
                                visible: !ui.compact && root.selectedEmulator !== null
                                color: root.surfaceColor
                                border.color: root.borderColor
                                Layout.preferredWidth: ui.inspectorWidth
                                Layout.minimumWidth: 320
                                Layout.maximumWidth: 420
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
                            ColumnLayout {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                spacing: 0
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    Layout.margins: ui.pageMargin
                                    spacing: 8
                                    Label { text: qsTr("Steam e integração"); color: root.textColor; font.pixelSize: ui.pageTitleSize; font.bold: true; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                    Label { text: qsTr("Gerencie cliente, biblioteca, Steam Input e teclado em um só lugar."); color: root.mutedColor; font.pixelSize: ui.bodySize; wrapMode: Text.WordWrap; Layout.fillWidth: true }
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
                                    model: root.filteredSteamItems
                                    clip: true
                                    spacing: 2
                                    Layout.fillWidth: true
                                    Layout.fillHeight: true
                                    Layout.leftMargin: 8
                                    Layout.rightMargin: 8
                                    currentIndex: root.selectedSteam
                                        ? root.filteredSteamItems.findIndex(function(row) { return row.id === root.selectedSteam.id }) : -1
                                    footer: EmptyState {
                                        width: steamList.width
                                        height: steamList.count === 0 ? steamList.height : 0
                                        visible: steamList.count === 0
                                        iconName: "steam"
                                        title: qsTr("Nenhuma integração neste filtro")
                                        description: qsTr("A Steam é opcional. Limpe o filtro ou atualize o estado para verificar novamente.")
                                        primaryText: qsTr("Ver todos")
                                        secondaryText: qsTr("Atualizar estado")
                                        textColor: root.textColor
                                        mutedColor: root.mutedColor
                                        accentColor: root.cyanColor
                                        minimumTarget: ui.targetSize
                                        onPrimaryTriggered: root.steamFilter = 0
                                        onSecondaryTriggered: root.refreshStatus(qsTr("Estado da Steam atualizado"))
                                    }
                                    delegate: ItemDelegate {
                                        id: steamDelegate
                                        required property int index
                                        required property var modelData
                                        width: ListView.view.width
                                        height: Math.max(86, implicitContentHeight + 16)
                                        highlighted: root.selectedSteam && root.selectedSteam.id === modelData.id
                                        Accessible.name: qsTr("%1, %2").arg(modelData.name).arg(modelData.statusLabel)
                                        KeyNavigation.up: index > 0 ? steamList.itemAtIndex(index - 1) : navRepeater.itemAt(2)
                                        KeyNavigation.down: index + 1 < steamList.count ? steamList.itemAtIndex(index + 1) : navRepeater.itemAt(2)
                                        onClicked: {
                                            root.selectedSteam = modelData
                                            if (ui.compact) {
                                                root.steamDrawerReturnItem = steamDelegate
                                                root.openSteamInspector()
                                            }
                                        }
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
                                                visible: !ui.compact
                                                Layout.preferredWidth: 180
                                                ToolButton { enabled: false; icon.name: root.stateIcon(modelData.state); icon.color: root.stateColor(modelData.state); background: Item {} }
                                                Label { text: modelData.statusLabel; color: root.stateColor(modelData.state); wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                            }
                                            DarkButton {
                                                id: steamRowAction
                                                text: modelData.action.label
                                                palette.buttonText: steamRowAction.enabled ? root.textColor : root.mutedColor
                                                enabled: modelData.action.enabled
                                                Layout.preferredWidth: ui.compact ? 124 : 144
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
                                visible: !ui.compact && root.selectedSteam !== null
                                color: root.surfaceColor
                                border.color: root.borderColor
                                Layout.preferredWidth: ui.inspectorWidth
                                Layout.minimumWidth: 320
                                Layout.maximumWidth: 420
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
                            ColumnLayout {
                                id: profilesContent
                                width: parent.width - 72
                                spacing: ui.gap
                                Label {
                                    id: profilesHeaderAnchor
                                    text: qsTr("Perfis do Desktop")
                                    color: root.textColor
                                    font.pixelSize: ui.pageTitleSize
                                    font.bold: true
                                    wrapMode: Text.WordWrap
                                    Layout.fillWidth: true
                                    Layout.topMargin: ui.pageMargin
                                    Layout.leftMargin: ui.pageMargin
                                    Layout.rightMargin: ui.pageMargin
                                }
                                Label {
                                    text: qsTr("Desejado: %1 · Recomendado: %2 · Último aplicado: %3")
                                        .arg(root.profileLabel(root.desiredProfileId()))
                                        .arg(root.profileLabel(root.desktopStatus.recommendedProfile))
                                        .arg(root.profileLabel(root.observedProfileId()))
                                    color: root.mutedColor
                                    wrapMode: Text.WordWrap
                                    Layout.fillWidth: true
                                    Layout.leftMargin: ui.pageMargin
                                    Layout.rightMargin: ui.pageMargin
                                }

                                GridLayout {
                                    id: profilesChoicesAnchor
                                    columns: ui.compact ? 1 : 2
                                    columnSpacing: ui.gap
                                    rowSpacing: ui.gap
                                    Layout.fillWidth: true
                                    Layout.leftMargin: ui.pageMargin
                                    Layout.rightMargin: ui.pageMargin

                                    Repeater {
                                        id: profileCards
                                        model: [
                                            {"id": "auto", "name": qsTr("Automático"), "icon": "system-run", "summary": qsTr("Acompanha o contexto de tela e dock com segurança.")},
                                            {"id": "handheld", "name": qsTr("Portátil"), "icon": "input-gaming", "summary": qsTr("Prioriza leitura, toque e controle no painel interno.")},
                                            {"id": "dock", "name": qsTr("Dock"), "icon": "video-display", "summary": qsTr("Equilibra densidade para monitor e periféricos externos.")},
                                            {"id": "safe", "name": qsTr("Seguro"), "icon": "security-medium", "summary": qsTr("Restaura uma composição mínima que não depende de providers.")}
                                        ]
                                        delegate: Button {
                                            id: profileCard
                                            required property int index
                                            required property var modelData
                                            property bool recommended: root.profileMatches(modelData.id, root.desktopStatus.recommendedProfile)
                                            property bool desired: root.selectedProfile === modelData.id
                                            property bool applied: root.profileMatches(modelData.id, root.observedProfileId())

                                            Layout.fillWidth: true
                                            Layout.minimumWidth: 260
                                            implicitHeight: profileCardContent.implicitHeight + 28
                                            text: modelData.name
                                            Accessible.name: qsTr("Perfil %1%2%3")
                                                .arg(modelData.name)
                                                .arg(recommended ? qsTr(", recomendado") : "")
                                                .arg(applied ? qsTr(", aplicado e verificado anteriormente") : "")
                                            KeyNavigation.left: index % 2 === 1 ? profileCards.itemAt(index - 1) : profileCard
                                            KeyNavigation.right: index % 2 === 0 && index + 1 < profileCards.count ? profileCards.itemAt(index + 1) : profileCard
                                            KeyNavigation.up: index > 1 ? profileCards.itemAt(index - 2) : navRepeater.itemAt(3)
                                            KeyNavigation.down: index + 2 < profileCards.count ? profileCards.itemAt(index + 2) : planButton
                                            onClicked: root.selectedProfile = modelData.id

                                            background: Rectangle {
                                                color: profileCard.desired ? "#153449" : root.surfaceColor
                                                radius: 10
                                                border.color: profileCard.activeFocus || profileCard.desired
                                                    ? root.cyanColor : root.borderColor
                                                border.width: profileCard.activeFocus || profileCard.desired ? 2 : 1
                                            }
                                            contentItem: ColumnLayout {
                                                id: profileCardContent
                                                spacing: 7
                                                RowLayout {
                                                    Layout.fillWidth: true
                                                    ToolButton { enabled: false; icon.name: modelData.icon; icon.color: root.cyanColor; background: Item {} }
                                                    Label { text: modelData.name; color: root.textColor; font.pixelSize: ui.cardTitleSize; font.bold: true; Layout.fillWidth: true }
                                                    Label { visible: profileCard.recommended; text: qsTr("Recomendado"); color: root.greenColor; font.bold: true }
                                                }
                                                Label { text: modelData.summary; color: root.mutedColor; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                                Label { visible: profileCard.desired; text: qsTr("Desejado para o próximo plano"); color: root.cyanColor; font.bold: true }
                                                Label { visible: profileCard.applied; text: qsTr("Aplicado · última verificação concluída"); color: root.greenColor }
                                                Label {
                                                    visible: !profileCard.applied && root.observedProfileId().length === 0
                                                    text: qsTr("Observado · não verificado")
                                                    color: root.mutedColor
                                                }
                                            }
                                        }
                                    }
                                }

                                SectionCard {
                                    title: qsTr("Revisar antes de aplicar")
                                    subtitle: qsTr("O SteamZero primeiro cria um plano. Nenhuma alteração é feita nesta etapa.")
                                    surfaceColor: root.surfaceColor
                                    borderColor: root.borderColor
                                    textColor: root.textColor
                                    mutedColor: root.mutedColor
                                    titleSize: ui.cardTitleSize
                                    padding: ui.gap
                                    Layout.fillWidth: true
                                    Layout.leftMargin: ui.pageMargin
                                    Layout.rightMargin: ui.pageMargin

                                    Button {
                                        id: planButton
                                        text: qsTr("Revisar alterações de %1").arg(root.profileLabel(root.selectedProfile))
                                        Layout.fillWidth: true
                                        Layout.minimumHeight: ui.targetSize
                                        Accessible.name: text
                                        KeyNavigation.up: profileCards.itemAt(profileCards.count - 1)
                                        KeyNavigation.down: applyButton
                                        onClicked: {
                                            root.planRequested(root.selectedProfile)
                                            root.request("POST", "/plan", {"profile": root.selectedProfile}, function(response) {
                                                root.currentPlan = response.plan
                                                if (response.plan.blockers.length > 0)
                                                    root.notify(qsTr("Plano bloqueado: %1").arg(response.plan.blockers.join("; ")), true)
                                                else
                                                    root.notify(qsTr("Plano pronto para revisão"), false)
                                            })
                                        }
                                    }
                                }

                                SectionCard {
                                    id: profilesPlanAnchor
                                    visible: root.currentPlan !== null
                                    title: qsTr("Plano revisado")
                                    surfaceColor: root.surfaceColor
                                    borderColor: root.currentPlan && root.currentPlan.blockers.length > 0
                                        ? root.amberColor : root.cyanDarkColor
                                    textColor: root.textColor
                                    mutedColor: root.mutedColor
                                    titleSize: ui.cardTitleSize
                                    padding: ui.gap
                                    Layout.fillWidth: true
                                    Layout.leftMargin: ui.pageMargin
                                    Layout.rightMargin: ui.pageMargin
                                    Layout.bottomMargin: ui.pageMargin

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
                                        Layout.minimumHeight: ui.targetSize
                                        Accessible.name: text
                                        KeyNavigation.up: planButton
                                        KeyNavigation.down: profileCards.itemAt(0)
                                        onClicked: {
                                            const path = root.currentPlan.target.id === "safe" ? "/reset" : "/apply"
                                            root.request("POST", path, {
                                                "planId": root.currentPlan.planId,
                                                "confirmToken": root.currentPlan.confirmToken
                                            }, function(response) {
                                                root.refreshStatus(qsTr("Perfil aplicado: %1").arg(root.profileLabel(response.profile.id)))
                                            })
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
                            ColumnLayout {
                                id: syncContent
                                width: parent.width - 72
                                spacing: ui.gap
                                Label {
                                    id: syncHeaderAnchor
                                    text: qsTr("Saves e Sync")
                                    color: root.textColor
                                    font.pixelSize: ui.pageTitleSize
                                    font.bold: true
                                    wrapMode: Text.WordWrap
                                    Layout.fillWidth: true
                                    Layout.topMargin: ui.pageMargin
                                    Layout.leftMargin: ui.pageMargin
                                    Layout.rightMargin: ui.pageMargin
                                }
                                Label {
                                    text: qsTr("Fila offline: nenhum save é sobrescrito quando há conflito.")
                                    color: root.mutedColor
                                    wrapMode: Text.WordWrap
                                    Layout.fillWidth: true
                                    Layout.leftMargin: ui.pageMargin
                                    Layout.rightMargin: ui.pageMargin
                                }

                                EmptyState {
                                    id: syncEmptyAnchor
                                    visible: root.syncTotal === 0
                                    iconName: "folder-sync"
                                    title: qsTr("Tudo tranquilo por aqui")
                                    description: qsTr("Não há transferências ou conflitos na fila local. Estado do provider: %1.")
                                        .arg(root.desktopStatus.dashboard && root.desktopStatus.dashboard.sync
                                            ? root.desktopStatus.dashboard.sync.state || qsTr("não verificado")
                                            : qsTr("não verificado"))
                                    primaryText: qsTr("Atualizar estado")
                                    secondaryText: qsTr("Como funciona")
                                    textColor: root.textColor
                                    mutedColor: root.mutedColor
                                    accentColor: root.greenColor
                                    minimumTarget: ui.targetSize
                                    Layout.fillWidth: true
                                    Layout.minimumHeight: 260
                                    Layout.leftMargin: ui.pageMargin
                                    Layout.rightMargin: ui.pageMargin
                                    onPrimaryTriggered: root.refreshStatus(qsTr("Status de sincronização atualizado"))
                                    onSecondaryTriggered: root.syncExplanationVisible = !root.syncExplanationVisible
                                }

                                GridLayout {
                                    id: syncSummaryAnchor
                                    visible: root.syncTotal > 0
                                    columns: ui.compact ? 1 : 3
                                    columnSpacing: ui.gap
                                    rowSpacing: ui.gap
                                    Layout.fillWidth: true
                                    Layout.leftMargin: ui.pageMargin
                                    Layout.rightMargin: ui.pageMargin

                                    Repeater {
                                        model: [
                                            {"label": qsTr("Pendentes"), "value": root.syncPending, "icon": "view-refresh", "color": root.cyanColor},
                                            {"label": qsTr("Conflitos preservados"), "value": root.syncConflicted, "icon": "dialog-warning", "color": root.amberColor},
                                            {"label": qsTr("Concluídos"), "value": root.syncDone, "icon": "dialog-ok-apply", "color": root.greenColor}
                                        ]
                                        delegate: SectionCard {
                                            required property var modelData
                                            title: modelData.label
                                            surfaceColor: root.surfaceColor
                                            borderColor: root.borderColor
                                            textColor: root.textColor
                                            mutedColor: root.mutedColor
                                            padding: ui.gap
                                            titleSize: ui.cardTitleSize
                                            Layout.fillWidth: true

                                            RowLayout {
                                                Layout.fillWidth: true
                                                ToolButton { enabled: false; icon.name: modelData.icon; icon.color: modelData.color; background: Item {} }
                                                Label { text: String(modelData.value); color: root.textColor; font.pixelSize: 26; font.bold: true; Layout.fillWidth: true; horizontalAlignment: Text.AlignRight }
                                            }
                                        }
                                    }
                                }

                                SectionCard {
                                    id: syncExplanationAnchor
                                    visible: root.syncExplanationVisible || root.syncTotal > 0
                                    title: qsTr("Sincronização em nuvem")
                                    subtitle: qsTr("O provider é opcional. Se a rede cair, os itens permanecem na fila local; conflitos preservam as duas versões.")
                                    surfaceColor: root.surfaceColor
                                    borderColor: root.borderColor
                                    textColor: root.textColor
                                    mutedColor: root.mutedColor
                                    padding: ui.gap
                                    titleSize: ui.cardTitleSize
                                    Layout.fillWidth: true
                                    Layout.leftMargin: ui.pageMargin
                                    Layout.rightMargin: ui.pageMargin
                                    Layout.bottomMargin: ui.pageMargin

                                    Button {
                                        text: qsTr("Atualizar estado")
                                        icon.name: "view-refresh"
                                        Layout.fillWidth: true
                                        Layout.minimumHeight: ui.targetSize
                                        Accessible.name: text
                                        onClicked: root.refreshStatus(qsTr("Status de sincronização atualizado"))
                                    }
                                }
                            }
                        }

                        // Sistema
                        ScrollView {
                            id: systemScroll
                            clip: true
                            contentWidth: availableWidth
                            ColumnLayout {
                                id: systemContent
                                width: parent.width - 72
                                spacing: ui.gap
                                Label {
                                    id: systemHeaderAnchor
                                    text: qsTr("Sistema e recuperação")
                                    color: root.textColor
                                    font.pixelSize: ui.pageTitleSize
                                    font.bold: true
                                    wrapMode: Text.WordWrap
                                    Layout.fillWidth: true
                                    Layout.topMargin: ui.pageMargin
                                    Layout.leftMargin: ui.pageMargin
                                    Layout.rightMargin: ui.pageMargin
                                }
                                Label {
                                    text: qsTr("%1 · %2").arg(root.deviceSummary()).arg(root.displaySummary())
                                    color: root.mutedColor
                                    wrapMode: Text.WordWrap
                                    Layout.fillWidth: true
                                    Layout.leftMargin: ui.pageMargin
                                    Layout.rightMargin: ui.pageMargin
                                }
                                Rectangle {
                                    id: systemAttentionAnchor
                                    visible: root.hasConflicts
                                    color: "#24180b"
                                    radius: 8
                                    border.color: root.amberColor
                                    Layout.fillWidth: true
                                    Layout.leftMargin: ui.pageMargin
                                    Layout.rightMargin: ui.pageMargin
                                    implicitHeight: systemConflictContent.implicitHeight + 28
                                    RowLayout {
                                        id: systemConflictContent
                                        anchors.fill: parent
                                        anchors.margins: 14
                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            Label { text: qsTr("Conflito de controle do sistema"); color: root.amberColor; font.pixelSize: ui.cardTitleSize; font.bold: true; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                            Label { text: "E-DESKTOP-OWNER-CONFLICT"; color: root.mutedColor; font.pixelSize: 12 }
                                        }
                                        Button { text: qsTr("Resolver conflito"); Layout.minimumHeight: ui.targetSize; Accessible.name: text; onClicked: root.beginConflictResolution() }
                                    }
                                }
                                Label { id: systemDoctorAnchor; text: qsTr("Diagnóstico do sistema"); color: root.textColor; font.pixelSize: ui.sectionTitleSize; font.bold: true; Layout.leftMargin: ui.pageMargin }
                                EmptyState {
                                    visible: !(root.desktopStatus.dashboard && root.desktopStatus.dashboard.doctor
                                        && root.desktopStatus.dashboard.doctor.checks
                                        && root.desktopStatus.dashboard.doctor.checks.length > 0)
                                    iconName: "tools-report-bug"
                                    title: qsTr("Diagnóstico ainda não disponível")
                                    description: qsTr("Execute uma verificação para consultar os checks reais do sistema.")
                                    primaryText: qsTr("Executar verificação")
                                    textColor: root.textColor
                                    mutedColor: root.mutedColor
                                    accentColor: root.cyanColor
                                    minimumTarget: ui.targetSize
                                    Layout.fillWidth: true
                                    Layout.leftMargin: ui.pageMargin
                                    Layout.rightMargin: ui.pageMargin
                                    onPrimaryTriggered: root.refreshStatus(qsTr("Diagnóstico atualizado"))
                                }
                                Repeater {
                                    model: root.desktopStatus.dashboard && root.desktopStatus.dashboard.doctor
                                        ? root.desktopStatus.dashboard.doctor.checks || [] : []
                                    delegate: Rectangle {
                                        id: doctorCard
                                        required property var modelData
                                        color: root.surfaceColor
                                        radius: 7
                                        border.color: root.borderColor
                                        Layout.fillWidth: true
                                        Layout.leftMargin: ui.pageMargin
                                        Layout.rightMargin: ui.pageMargin
                                        implicitHeight: doctorContent.implicitHeight + 24
                                        RowLayout {
                                            id: doctorContent
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
                                                Label { text: modelData.name; color: root.textColor; font.bold: true; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                                Label { text: modelData.message; color: root.mutedColor; font.pixelSize: ui.metadataSize; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                            }
                                        }
                                    }
                                }
                                GridLayout {
                                    id: systemActionsAnchor
                                    columns: ui.compact ? 1 : 3
                                    columnSpacing: ui.gap
                                    rowSpacing: ui.gap
                                    Layout.fillWidth: true
                                    Layout.leftMargin: ui.pageMargin
                                    Layout.rightMargin: ui.pageMargin
                                    Layout.bottomMargin: ui.pageMargin
                                    Button {
                                        text: qsTr("Executar verificação")
                                        icon.name: "view-refresh"
                                        Layout.fillWidth: true
                                        Layout.minimumHeight: ui.targetSize
                                        Accessible.name: text
                                        onClicked: root.refreshStatus(qsTr("Diagnóstico atualizado"))
                                    }
                                    Button {
                                        text: qsTr("Abrir teclado virtual")
                                        icon.name: "input-keyboard-virtual"
                                        Layout.fillWidth: true
                                        Layout.minimumHeight: ui.targetSize
                                        Accessible.name: text
                                        onClicked: root.openKeyboard()
                                    }
                                    Button {
                                        visible: root.desktopStatus.recoveryRequired
                                        text: qsTr("Restaurar último estado seguro")
                                        icon.name: "security-medium"
                                        Layout.fillWidth: true
                                        Layout.minimumHeight: ui.targetSize
                                        Accessible.name: text
                                        onClicked: root.openRecoveryDialog()
                                    }
                                }
                            }
                        }
                    }
                }

                Rectangle {
                    id: stickyContextHeader
                    visible: root.currentScrollTarget() !== null
                        && root.currentScrollTarget().contentY > 72
                    z: 30
                    height: ui.compact ? 48 : 54
                    anchors.top: parent.top
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.topMargin: root.hasConflicts ? (root.alertExpanded ? 94 : 68) : 0
                    color: "#f20d1924"
                    border.color: root.borderColor

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: ui.pageMargin
                        anchors.rightMargin: ui.pageMargin + 72
                        spacing: ui.gap
                        Label {
                            text: root.pageTitle()
                            color: root.textColor
                            font.pixelSize: ui.cardTitleSize
                            font.bold: true
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                        Label {
                            visible: !ui.compact
                            text: root.profileLabel(root.desktopStatus.effectiveProfile)
                            color: root.mutedColor
                        }
                        ToolButton {
                            visible: root.pendingRequests > 0
                            enabled: false
                            icon.name: "view-refresh"
                            icon.color: root.cyanColor
                            background: Item {}
                            Accessible.name: qsTr("Operação em andamento")
                        }
                    }
                }

                SectionNavigator {
                    id: sectionNavigator
                    z: 40
                    flickable: root.currentScrollTarget()
                    sections: root.currentSections()
                    reducedMotion: root.reducedMotionPreference
                    surfaceColor: root.raisedColor
                    borderColor: root.borderColor
                    textColor: root.textColor
                    mutedColor: root.mutedColor
                    accentColor: root.cyanColor
                    anchors.right: parent.right
                    anchors.rightMargin: 8
                    anchors.verticalCenter: parent.verticalCenter
                    onMenuRequested: root.openSectionMenu()
                }
            }

            Item {
                visible: ui.wide
                Layout.fillWidth: true
                Layout.fillHeight: true
            }
        }

        ResponsiveFooter {
            compact: ui.compact
            backgroundColor: "#080d13"
            borderColor: root.borderColor
            textColor: root.textColor
            mutedColor: root.mutedColor
            targetHeight: ui.footerHeight
            showContextAction: root.sectionIndex === 1 || root.sectionIndex === 2
            sectionNavigationAvailable: sectionNavigator.visible
            sectionListAvailable: sectionNavigator.visible
            Layout.fillWidth: true
        }
    }

    FeedbackNotice {
        message: root.lastRequest
        error: root.lastRequestIsError
        z: 1000
        width: Math.min(520, root.width - 40)
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.rightMargin: 20
        anchors.bottomMargin: ui.footerHeight + 14
        surfaceColor: root.lastRequestIsError ? "#35171b" : "#102b20"
        textColor: root.textColor
        mutedColor: root.mutedColor
        successColor: root.greenColor
        errorColor: root.redColor
        minimumTarget: ui.targetSize
        onContextActionRequested: {
            root.lastRequest = ""
            root.navigateToSection(5)
        }
        onDismissRequested: root.lastRequest = ""
    }

    LoadingOverlay {
        anchors.fill: parent
        active: root.loadingOverlayVisible
        reducedMotion: root.reducedMotionPreference
        title: root.loadingTitle
        detail: root.loadingDetail
        surfaceColor: root.raisedColor
        borderColor: root.borderColor
        textColor: root.textColor
        mutedColor: root.mutedColor
        accentColor: root.cyanColor
    }
}
