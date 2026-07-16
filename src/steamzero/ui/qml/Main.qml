// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: root
    width: 949
    height: 593
    minimumWidth: 640
    minimumHeight: 480
    visible: true
    title: qsTr("SteamZero — Desktop portátil")
    color: "#111318"

    property var desktopStatus: ({
        "effectiveProfile": "handheld-desktop",
        "recommendedProfile": "handheld-desktop",
        "recoveryRequired": false,
        "independentRuntime": true,
        "context": {"capabilities": [], "conflicts": []}
    })
    property string selectedProfile: "auto"
    property string lastRequest: ""
    property bool lastRequestIsError: false
    property string apiUrl: ""
    property string apiToken: ""
    property var currentPlan: null
    property var conflictPlan: null
    readonly property bool hasConflicts: desktopStatus.context
        && desktopStatus.context.conflicts
        && desktopStatus.context.conflicts.length > 0

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
                lastRequest = qsTr("Status inválido; modo observador mantido")
            }
        }
        const apiMarker = args.indexOf("--steamzero-api")
        const tokenMarker = args.indexOf("--steamzero-token")
        if (apiMarker >= 0 && apiMarker + 1 < args.length)
            apiUrl = args[apiMarker + 1]
        if (tokenMarker >= 0 && tokenMarker + 1 < args.length)
            apiToken = args[tokenMarker + 1]
    }

    function request(method, path, payload, callback) {
        if (!apiUrl || !apiToken) {
            lastRequest = qsTr("Bridge local indisponível; nenhuma mudança foi feita")
            return
        }
        const xhr = new XMLHttpRequest()
        xhr.open(method, apiUrl + path)
        xhr.setRequestHeader("Content-Type", "application/json")
        xhr.setRequestHeader("X-SteamZero-Token", apiToken)
        xhr.onreadystatechange = function() {
            if (xhr.readyState !== XMLHttpRequest.DONE)
                return
            try {
                const response = JSON.parse(xhr.responseText)
                if (xhr.status < 200 || xhr.status >= 300) {
                    const error = response.error || {}
                    lastRequest = error.title || error.detail || qsTr("Ação recusada")
                    lastRequestIsError = true
                    return
                }
                lastRequestIsError = false
                callback(response)
            } catch (error) {
                lastRequest = qsTr("Resposta inválida; nenhuma mudança adicional foi feita")
                lastRequestIsError = true
            }
        }
        xhr.send(JSON.stringify(payload || {}))
    }

    function refreshStatus() {
        request("GET", "/status", {}, function(response) {
            desktopStatus = response
            currentPlan = null
        })
    }

    function commandPreview(plan) {
        if (!plan || !plan.action || !plan.action.commands)
            return ""
        return plan.action.commands.map(function(command) { return command.join(" ") }).join("\n")
    }

    Component.onCompleted: parseArguments()

    Dialog {
        id: conflictDialog
        title: qsTr("Desativar serviço conflitante?")
        modal: true
        width: Math.min(root.width - 40, 680)
        x: Math.max(20, (root.width - width) / 2)
        y: Math.max(20, (root.height - height) / 2)
        standardButtons: Dialog.NoButton

        ColumnLayout {
            width: parent.width
            spacing: 12
            Label {
                text: qsTr("O SteamZero continuará bloqueado até o watcher deixar de controlar display e entrada.")
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Label {
                text: root.conflictPlan ? root.conflictPlan.action.unit : ""
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
                Layout.fillWidth: true
                Layout.minimumHeight: 84
                Accessible.name: qsTr("Comandos exatos que serão executados")
            }
            Label {
                text: qsTr("Se a segunda etapa falhar, o estado anterior será restaurado.")
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
                    text: qsTr("Desativar e liberar SteamZero")
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
                            root.lastRequest = qsTr("Serviço desativado. Gere um novo plano para aplicar o perfil.")
                            root.conflictPlan = null
                            conflictDialog.close()
                            root.refreshStatus()
                        })
                    }
                }
            }
        }
    }

    header: ToolBar {
        height: 56
        background: Rectangle { color: "#191c23" }
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 20
            anchors.rightMargin: 20
            Label {
                text: qsTr("SteamZero")
                color: "#f4f7ff"
                font.pixelSize: 22
                font.bold: true
                Layout.fillWidth: true
            }
            Label {
                text: desktopStatus.independentRuntime ? qsTr("Runtime autônomo") : qsTr("Verificação necessária")
                color: desktopStatus.independentRuntime ? "#83e6aa" : "#ffc66d"
                Accessible.name: text
            }
        }
    }

    ScrollView {
        anchors.fill: parent
        contentWidth: availableWidth
        clip: true

        ColumnLayout {
            width: parent.width
            spacing: 16
            anchors.margins: 20

            Label {
                text: qsTr("Experiência Desktop")
                color: "#f4f7ff"
                font.pixelSize: 28
                font.bold: true
                Layout.topMargin: 20
                Layout.leftMargin: 20
            }
            Label {
                text: qsTr("Perfil atual: %1").arg(desktopStatus.effectiveProfile)
                color: "#c7cfdd"
                font.pixelSize: 17
                Layout.leftMargin: 20
            }

            Frame {
                visible: root.hasConflicts
                Layout.fillWidth: true
                Layout.leftMargin: 20
                Layout.rightMargin: 20
                padding: 16
                background: Rectangle {
                    color: "#35251a"
                    radius: 14
                    border.color: "#ffb86b"
                    border.width: 2
                }
                ColumnLayout {
                    width: parent.width
                    spacing: 10
                    Label {
                        text: qsTr("Outro serviço está controlando display ou entrada")
                        color: "#ffd29b"
                        font.pixelSize: 19
                        font.bold: true
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                        Accessible.name: text
                    }
                    Label {
                        text: qsTr("Nenhuma configuração foi aplicada. Desative o serviço conflitante ou mantenha o SteamZero em modo observador.")
                        color: "#f4d9bd"
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    Repeater {
                        model: root.hasConflicts ? root.desktopStatus.context.conflicts : []
                        Label {
                            required property string modelData
                            text: modelData
                            color: "#f4d9bd"
                            wrapMode: Text.WrapAnywhere
                            Layout.fillWidth: true
                            Accessible.name: text
                        }
                    }
                    Label {
                        visible: !root.desktopStatus.conflictActions
                            || root.desktopStatus.conflictActions.length === 0
                        text: qsTr("Este conflito não possui desativação automática allowlisted.")
                        color: "#f4d9bd"
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    Button {
                        id: releaseConflictButton
                        visible: root.desktopStatus.conflictActions
                            && root.desktopStatus.conflictActions.length > 0
                        text: qsTr("Revisar desativação do watcher antigo")
                        Layout.fillWidth: true
                        Layout.minimumHeight: 48
                        Accessible.name: text
                        onClicked: {
                            const action = root.desktopStatus.conflictActions[0]
                            root.request("POST", "/conflict/plan", {"actionId": action.actionId}, function(response) {
                                root.conflictPlan = response.plan
                                conflictDialog.open()
                            })
                        }
                        KeyNavigation.down: profilePicker
                    }
                }
            }

            GridLayout {
                id: cards
                columns: width >= 820 ? 2 : 1
                columnSpacing: 16
                rowSpacing: 16
                Layout.fillWidth: true
                Layout.leftMargin: 20
                Layout.rightMargin: 20

                GroupBox {
                    title: qsTr("Modo")
                    Accessible.name: title
                    Layout.fillWidth: true
                    Layout.minimumHeight: 190
                    background: Rectangle { color: "#1b1f27"; radius: 14; border.color: "#343b49" }
                    label: Label { text: parent.title; color: "#f4f7ff"; font.pixelSize: 19; font.bold: true }
                    ColumnLayout {
                        anchors.fill: parent
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
                            text: qsTr("Gerar plano")
                            Layout.fillWidth: true
                            Layout.minimumHeight: 48
                            Accessible.name: text
                            onClicked: {
                                root.planRequested(root.selectedProfile)
                                root.request("POST", "/plan", {"profile": root.selectedProfile}, function(response) {
                                    root.currentPlan = response.plan
                                    if (response.plan.blockers.length > 0) {
                                        root.lastRequest = qsTr("Plano bloqueado: %1").arg(response.plan.blockers.join("; "))
                                        root.lastRequestIsError = true
                                    } else {
                                        root.lastRequest = qsTr("Plano pronto: %1 mudança(s). Revise e aplique.").arg(response.plan.changes.length)
                                        root.lastRequestIsError = false
                                    }
                                })
                            }
                            KeyNavigation.up: profilePicker
                            KeyNavigation.down: applyButton
                        }
                        Button {
                            id: applyButton
                            text: root.currentPlan !== null && root.currentPlan.blockers.length > 0
                                ? qsTr("Aplicação bloqueada — resolva o conflito")
                                : qsTr("Aplicar plano revisado")
                            enabled: root.currentPlan !== null && root.currentPlan.blockers.length === 0
                            Layout.fillWidth: true
                            Layout.minimumHeight: 48
                            Accessible.name: text
                            onClicked: {
                                const path = root.currentPlan.target.id === "safe" ? "/reset" : "/apply"
                                root.request("POST", path, {
                                    "planId": root.currentPlan.planId,
                                    "confirmToken": root.currentPlan.confirmToken
                                }, function(response) {
                                    root.lastRequest = qsTr("Perfil aplicado: %1").arg(response.profile.id)
                                    root.currentPlan = null
                                    root.refreshStatus()
                                })
                            }
                            KeyNavigation.up: planButton
                            KeyNavigation.down: keyboardButton
                        }
                    }
                }

                GroupBox {
                    title: qsTr("Controles e teclado")
                    Accessible.name: title
                    Layout.fillWidth: true
                    Layout.minimumHeight: 190
                    background: Rectangle { color: "#1b1f27"; radius: 14; border.color: "#343b49" }
                    label: Label { text: parent.title; color: "#f4f7ff"; font.pixelSize: 19; font.bold: true }
                    ColumnLayout {
                        anchors.fill: parent
                        Label {
                            text: qsTr("Um único owner de entrada; providers são opcionais")
                            color: "#c7cfdd"
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                        Button {
                            id: keyboardButton
                            text: qsTr("Abrir teclado virtual")
                            Layout.fillWidth: true
                            Layout.minimumHeight: 48
                            Accessible.name: text
                            onClicked: {
                                root.keyboardRequested()
                                root.request("POST", "/keyboard", {}, function(response) {
                                    root.lastRequest = qsTr("Teclado aberto por %1").arg(response.provider)
                                })
                            }
                            KeyNavigation.up: applyButton
                            KeyNavigation.down: recoveryButton
                        }
                    }
                }

                GroupBox {
                    title: qsTr("Display e janelas")
                    Accessible.name: title
                    Layout.fillWidth: true
                    Layout.minimumHeight: 150
                    background: Rectangle { color: "#1b1f27"; radius: 14; border.color: "#343b49" }
                    label: Label { text: parent.title; color: "#f4f7ff"; font.pixelSize: 19; font.bold: true }
                    Label {
                        anchors.fill: parent
                        text: qsTr("Escala portátil 135% · Overview e Application Dashboard do Plasma")
                        color: "#c7cfdd"
                        wrapMode: Text.WordWrap
                    }
                }

                GroupBox {
                    title: qsTr("Diagnóstico e recuperação")
                    Accessible.name: title
                    Layout.fillWidth: true
                    Layout.minimumHeight: 150
                    background: Rectangle {
                        color: desktopStatus.recoveryRequired ? "#322319" : "#1b1f27"
                        radius: 14
                        border.color: desktopStatus.recoveryRequired ? "#ffb86b" : "#343b49"
                    }
                    label: Label { text: parent.title; color: "#f4f7ff"; font.pixelSize: 19; font.bold: true }
                    Button {
                        id: recoveryButton
                        anchors.left: parent.left
                        anchors.right: parent.right
                        height: 48
                        text: desktopStatus.recoveryRequired ? qsTr("Restaurar snapshot") : qsTr("Nenhuma recuperação pendente")
                        enabled: desktopStatus.recoveryRequired
                        Accessible.name: text
                        onClicked: {
                            root.recoveryRequested()
                            root.request("POST", "/recover", {}, function(response) {
                                root.lastRequest = qsTr("Recuperação concluída: %1").arg(response.status)
                                root.refreshStatus()
                            })
                        }
                        KeyNavigation.up: keyboardButton
                        KeyNavigation.down: profilePicker
                    }
                }
            }

            Label {
                text: root.lastRequest
                visible: text.length > 0
                color: root.lastRequestIsError ? "#ff9b9b" : "#83e6aa"
                font.pixelSize: 16
                Accessible.name: text
                Layout.leftMargin: 20
                Layout.bottomMargin: 20
            }
        }
    }
}
