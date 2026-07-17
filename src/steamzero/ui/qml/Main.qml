// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: root
    width: 1600
    height: 1000
    minimumWidth: 1100
    minimumHeight: 720
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
    property var fallbackSteamGameplay: ({
        "games": [],
        "environment": [
            {"id": "steam", "name": "Steam", "detail": "Contexto de jogo e runtime", "owner": "Steam", "required": true, "state": "missing", "statusLabel": "ausente"},
            {"id": "gamescope", "name": "Gamescope", "detail": "Composição e limite de quadros", "owner": "SteamZero", "required": true, "state": "missing", "statusLabel": "ausente"},
            {"id": "gamemode", "name": "Feral GameMode", "detail": "Prioridade de CPU e processos", "owner": "Steam", "required": true, "state": "missing", "statusLabel": "ausente"},
            {"id": "mangohud", "name": "MangoHud", "detail": "Métricas durante o jogo", "owner": "SteamZero", "required": false, "state": "missing", "statusLabel": "ausente, opcional"},
            {"id": "vkbasalt", "name": "vkBasalt", "detail": "Pós-processamento Vulkan", "owner": "Sistema", "required": false, "state": "missing", "statusLabel": "ausente, opcional"},
            {"id": "lsfg", "name": "LSFG-VK", "detail": "Geração de quadros configurada por jogo", "owner": "Sistema", "required": false, "state": "missing", "statusLabel": "ausente, opcional"}
        ],
        "readiness": {"percent": 0, "title": "Ambiente Steam indisponível", "detail": "Abra Sistema para diagnosticar"},
        "hardware": {"deviceLabel": "Linux", "tdpMin": null, "tdpMax": null, "gpuMin": null, "gpuMax": null, "refreshHz": null, "memoryGb": null, "withinSafeLimits": false},
        "context": {"device": "Linux", "battery": null, "mode": "Modo Desktop"},
        "currentProfile": {"gameId": "", "scope": "global", "profile": "balanced", "fps": 40, "tdp": null, "gpuMode": "auto", "gpuClock": null, "gamescope": false, "gameMode": false, "mangoHud": "off", "upscaling": "native", "frameGeneration": "off", "controllerLayout": "steam-recommended"},
        "impact": {"battery": "—", "resolution": "1280×800", "fluidity": "40 FPS estáveis"}
    })
    readonly property var emulatorItems: desktopStatus.dashboard && desktopStatus.dashboard.components
        ? desktopStatus.dashboard.components : fallbackComponents
    readonly property var steamItems: desktopStatus.dashboard && desktopStatus.dashboard.steam
        ? desktopStatus.dashboard.steam : fallbackSteam
    readonly property var steamGameplayData: desktopStatus.dashboard
        && desktopStatus.dashboard.steamGameplay
        ? desktopStatus.dashboard.steamGameplay : fallbackSteamGameplay
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
    property string apiUrl: ""
    property string apiToken: ""
    property string lastRequest: ""
    property bool lastRequestIsError: false
    property int pendingRequests: 0
    property bool recoveryPromptShown: false

    signal planRequested(string profile)
    signal recoveryRequested()
    signal keyboardRequested()

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
                && ["performance", "controls"].indexOf(args[steamAreaMarker + 1]) >= 0)
            steamArea = args[steamAreaMarker + 1]
        ensureSelections()
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
        const action = desktopStatus.conflictActions[0]
        request("POST", "/conflict/plan", {"actionId": action.actionId}, function(response) {
            conflictPlan = response.plan
            conflictDialog.open()
        })
    }

    function beginQuickReset() {
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

    Dialog {
        id: conflictDialog
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
                        root.request("POST", "/reset", {
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
        id: recoveryDialog
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
                    root.request("POST", "/recover", {}, function(response) {
                        recoveryDialog.close()
                        root.refreshStatus(qsTr("Recuperação concluída com segurança"))
                    })
                }
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
                Layout.preferredWidth: root.width < 980 ? 184 : root.width >= 1400 ? 264 : 228
                Layout.fillHeight: true
                border.color: root.borderColor
                border.width: 1

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 8

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.minimumHeight: 72
                        Image {
                            source: "../assets/steamzero-mark.png"
                            sourceSize.width: 48
                            sourceSize.height: 48
                            fillMode: Image.PreserveAspectFit
                            Layout.preferredWidth: 48
                            Layout.preferredHeight: 48
                            Accessible.name: qsTr("Marca SteamZero")
                        }
                        ColumnLayout {
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
                            Layout.minimumHeight: index === 2 && root.sectionIndex === 2 ? 70 : 48
                            leftPadding: 14
                            rightPadding: 12
                            spacing: 12
                            Accessible.name: text
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
                                ColumnLayout {
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
                        id: attentionButton
                        visible: root.needsAttention
                        text: root.hasConflicts ? qsTr("Conflito do Desktop")
                            : root.desktopStatus.recoveryRequired ? qsTr("Recuperação pendente")
                            : qsTr("Estado %1").arg(root.desktopStatus.truthState)
                        icon.name: "security-high"
                        Layout.fillWidth: true
                        Layout.minimumHeight: 54
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
                                spacing: 1
                                Label { text: attentionButton.text; color: root.amberColor; font.bold: true }
                                Label { text: qsTr("Requer sua atenção"); color: root.mutedColor; font.pixelSize: 12 }
                            }
                        }
                    }

                    Item { Layout.fillHeight: true }

                    Label {
                        text: qsTr("AÇÕES DO SISTEMA")
                        color: root.mutedColor
                        font.pixelSize: 11
                        font.capitalization: Font.AllUppercase
                    }
                    DarkButton {
                        id: quickResetButton
                        text: qsTr("Quick Reset")
                        icon.name: "edit-undo"
                        palette.buttonText: root.textColor
                        Layout.fillWidth: true
                        Layout.minimumHeight: 48
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
                        text: qsTr("Cloud Sync")
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
                        onClicked: root.sectionIndex = 4
                    }
                    DarkButton {
                        id: doctorButton
                        text: qsTr("steamzero doctor")
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
                        onClicked: root.sectionIndex = 5
                    }
                    RowLayout {
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
                        visible: root.hasConflicts || root.desktopTruthNeedsAttention
                        color: "#24180b"
                        border.color: root.amberColor
                        border.width: 1
                        radius: 8
                        Layout.fillWidth: true
                        Layout.leftMargin: 14
                        Layout.rightMargin: 14
                        Layout.topMargin: 12
                        Layout.preferredHeight: 72

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
                                        text: root.hasConflicts
                                            ? qsTr("Outro serviço controla o Desktop")
                                            : root.desktopStatus.truthState === "stale"
                                                ? qsTr("Perfil do Desktop desatualizado")
                                                : root.desktopStatus.truthState === "unapplied"
                                                    ? qsTr("Nenhum perfil foi aplicado")
                                                    : qsTr("Observação do Desktop degradada")
                                        color: root.amberColor
                                        font.pixelSize: 17
                                        font.bold: true
                                    }
                                    Label {
                                        text: root.hasConflicts ? "E-DESKTOP-OWNER-CONFLICT"
                                            : root.desktopStatus.truthState.toUpperCase()
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
                                    font.pixelSize: 13
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
                        currentIndex: root.sectionIndex
                        Layout.fillWidth: true
                        Layout.fillHeight: true

                        // Visão geral
                        ScrollView {
                            clip: true
                            contentWidth: availableWidth
                            ColumnLayout {
                                width: parent.width
                                spacing: 18
                                anchors.margins: 28
                                Label {
                                    text: qsTr("Visão geral")
                                    color: root.textColor
                                    font.pixelSize: 30
                                    font.bold: true
                                    Layout.topMargin: 24
                                    Layout.leftMargin: 28
                                }
                                Label {
                                    text: root.deviceSummary()
                                    color: root.mutedColor
                                    font.pixelSize: 15
                                    Layout.leftMargin: 28
                                }
                                Rectangle {
                                    Layout.fillWidth: true
                                    Layout.leftMargin: 28
                                    Layout.rightMargin: 28
                                    Layout.minimumHeight: 124
                                    color: root.surfaceColor
                                    radius: 10
                                    border.color: root.borderColor
                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.margins: 20
                                        spacing: 22
                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            Label {
                                                text: root.needsAttention ? qsTr("Ação necessária") : qsTr("Sistema pronto")
                                                color: root.needsAttention ? root.amberColor : root.greenColor
                                                font.pixelSize: 22
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
                                    Layout.leftMargin: 28
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
                                        Layout.leftMargin: 28
                                        Layout.rightMargin: 28
                                        Layout.minimumHeight: 66
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
                            ColumnLayout {
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
                                visible: root.width >= 1040
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
                                    root.request("POST", "/steam/gameplay/plan", payload, function(response) {
                                        steamGameplayPage.showPlan(response.plan)
                                    })
                                }
                                onApplyRequested: function(planId, confirmToken) {
                                    root.request("POST", "/steam/gameplay/apply", {
                                        "planId": planId,
                                        "confirmToken": confirmToken
                                    }, function(response) {
                                        root.refreshStatus(response.message || qsTr("Perfil Steam salvo"))
                                    })
                                }
                                onSystemRequested: root.sectionIndex = 5
                                onSteamInputRequested: function(gameId) {
                                    root.request("POST", "/steam/input/open", {
                                        "gameId": gameId
                                    }, function() {
                                        root.notify(qsTr("Configuração Steam Input aberta"), false)
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
                            clip: true
                            contentWidth: availableWidth
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
                                        ComboBox {
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
                                                const path = root.currentPlan.target.id === "safe" ? "/reset" : "/apply"
                                                root.request("POST", path, {
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
                            clip: true
                            contentWidth: availableWidth
                            ColumnLayout {
                                width: parent.width
                                spacing: 16
                                Label { text: qsTr("Saves e Sync"); color: root.textColor; font.pixelSize: 30; font.bold: true; Layout.topMargin: 28; Layout.leftMargin: 28 }
                                Label { text: qsTr("Fila offline: nenhum save é sobrescrito quando há conflito."); color: root.mutedColor; Layout.leftMargin: 28 }
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
                                Label {
                                    text: qsTr("Cloud Sync permanece opcional. Se a rede ou o provedor cair, os itens continuam na fila local.")
                                    color: root.mutedColor
                                    wrapMode: Text.WordWrap
                                    Layout.fillWidth: true
                                    Layout.leftMargin: 28
                                    Layout.rightMargin: 28
                                }
                                Button {
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
                            clip: true
                            contentWidth: availableWidth
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
            color: "#080d13"
            border.color: root.borderColor
            Layout.fillWidth: true
            Layout.preferredHeight: 54
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 20
                anchors.rightMargin: 20
                spacing: 24
                Label { text: qsTr("STEAM  MENU"); color: root.mutedColor; font.bold: true }
                Item { Layout.fillWidth: true }
                Label { text: qsTr("D-PAD  NAVEGAR"); color: root.mutedColor }
                Label { text: qsTr("A  SELECIONAR"); color: root.textColor }
                Label { text: qsTr("X  AÇÃO DE CONTEXTO"); color: root.textColor }
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
        anchors.bottomMargin: 68
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
