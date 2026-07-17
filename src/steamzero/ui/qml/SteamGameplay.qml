// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: page

    required property var gameplay
    required property color backgroundColor
    required property color surfaceColor
    required property color raisedColor
    required property color borderColor
    required property color textColor
    required property color mutedColor
    required property color cyanColor
    required property color cyanDarkColor
    required property color greenColor
    required property color amberColor
    required property color redColor

    signal planRequested(var payload)
    signal applyRequested(string planId, string confirmToken)
    signal systemRequested()
    signal steamInputRequested(string gameId)

    property int gameIndex: 0
    property int scopeIndex: 1
    property int profileIndex: 1
    property int fpsIndex: 1
    property int tdpValue: 10
    property int gpuModeIndex: 0
    property int mangoIndex: 0
    property int upscalingIndex: 1
    property int frameGenerationIndex: 0
    property int controllerLayoutIndex: 0
    property int workspaceIndex: 0
    property string initialArea: "performance"
    property bool gamescopeEnabled: true
    property bool gameModeEnabled: true
    property bool initialized: false
    property var reviewedPlan: null

    readonly property var games: gameplay && gameplay.games ? gameplay.games : []
    readonly property var environment: gameplay && gameplay.environment ? gameplay.environment : []
    readonly property var hardware: gameplay && gameplay.hardware ? gameplay.hardware : ({})
    readonly property var impact: gameplay && gameplay.impact ? gameplay.impact : ({})
    readonly property var currentProfile: gameplay && gameplay.currentProfile
        ? gameplay.currentProfile : ({})
    readonly property var selectedGame: games.length > 0 && gameIndex < games.length
        ? games[gameIndex] : ({"id": "", "name": qsTr("Nenhum jogo instalado"), "coverUrl": ""})

    function valueIndex(values, value, fallback) {
        const index = values.indexOf(value)
        return index >= 0 ? index : fallback
    }

    function loadProfile() {
        const profile = currentProfile || {}
        const gameId = String(profile.gameId || "")
        const foundGame = games.findIndex(function(game) { return String(game.id) === gameId })
        gameIndex = foundGame >= 0 ? foundGame : 0
        scopeIndex = valueIndex(["global", "game", "portable", "dock"], profile.scope, 1)
        profileIndex = 1
        fpsIndex = 1
        tdpValue = hardware.tdpMax ? 10 : 0
        gpuModeIndex = profile.gpuMode === "manual" ? 1 : 0
        gamescopeEnabled = profile.gamescope !== false
        gameModeEnabled = profile.gameMode !== false
        mangoIndex = environmentById("mangohud").state === "ready" ? 1 : 0
        upscalingIndex = valueIndex(
            ["native", "fsr2-quality", "fsr2-balanced", "gamescope-fsr"],
            profile.upscaling, 1
        )
        frameGenerationIndex = valueIndex(
            ["off", "lsfg-2x", "lsfg-3x", "lsfg-4x"],
            profile.frameGeneration, 0
        )
        controllerLayoutIndex = valueIndex(
            [
                "steam-recommended", "official", "community",
                "steamzero-gamepad", "steamzero-kbm", "custom"
            ],
            profile.controllerLayout, 0
        )
        initialized = true
    }

    function environmentById(id) {
        return environment.find(function(row) { return row.id === id }) || ({"state": "missing"})
    }

    function payload() {
        return {
            "gameId": String(selectedGame.id || ""),
            "scope": ["global", "game", "portable", "dock"][scopeIndex],
            "profile": ["economy", "balanced", "performance"][profileIndex],
            "fps": [30, 40, 60][fpsIndex],
            "tdp": hardware.tdpMax ? Math.round(tdpValue) : null,
            "gpuMode": gpuModeIndex === 0 ? "auto" : "manual",
            "gpuClock": gpuModeIndex === 0 ? null : 800,
            "gamescope": gamescopeEnabled,
            "gameMode": gameModeEnabled,
            "mangoHud": ["off", "basic", "detailed"][mangoIndex],
            "upscaling": ["native", "fsr2-quality", "fsr2-balanced", "gamescope-fsr"][upscalingIndex],
            "frameGeneration": ["off", "lsfg-2x", "lsfg-3x", "lsfg-4x"][frameGenerationIndex],
            "controllerLayout": [
                "steam-recommended", "official", "community",
                "steamzero-gamepad", "steamzero-kbm", "custom"
            ][controllerLayoutIndex]
        }
    }

    function safePayload() {
        const result = payload()
        result.profile = "economy"
        result.fps = 30
        result.tdp = hardware.tdpMax ? 7 : null
        result.gpuMode = "auto"
        result.gpuClock = null
        result.gamescope = environmentById("gamescope").state === "ready"
        result.gameMode = false
        result.mangoHud = "off"
        result.upscaling = "native"
        result.frameGeneration = "off"
        result.controllerLayout = "steam-recommended"
        return result
    }

    function showPlan(plan) {
        reviewedPlan = plan
        reviewDialog.open()
    }

    function choosePerformance(index) {
        profileIndex = index
        fpsIndex = index
        tdpValue = [7, 10, 15][index]
    }

    function estimatedBattery() {
        if (!hardware.tdpMax)
            return impact.battery || "—"
        const minutes = Math.max(60, 255 - Math.round(tdpValue) * 10)
        const remainder = minutes % 60
        return "%1 h %2 min".arg(Math.floor(minutes / 60)).arg(remainder < 10 ? "0" + remainder : remainder)
    }

    function frameGenerationSummary() {
        if (frameGenerationIndex === 0)
            return qsTr("Nativa")
        return qsTr("%1 FPS percebidos · base %2 FPS").arg(
            [1, 2, 3, 4][frameGenerationIndex] * [30, 40, 60][fpsIndex]
        ).arg([30, 40, 60][fpsIndex])
    }

    onGameplayChanged: loadProfile()
    onInitialAreaChanged: workspaceIndex = initialArea === "controls" ? 1 : 0
    Component.onCompleted: {
        workspaceIndex = initialArea === "controls" ? 1 : 0
        loadProfile()
    }

    Dialog {
        id: reviewDialog
        modal: true
        title: qsTr("Revisar perfil de gameplay")
        width: Math.min(page.width - 48, 720)
        x: (page.width - width) / 2
        y: (page.height - height) / 2
        standardButtons: Dialog.NoButton
        background: Rectangle {
            color: page.raisedColor
            radius: 10
            border.color: page.reviewedPlan && page.reviewedPlan.blockers.length > 0
                ? page.amberColor : page.cyanColor
            border.width: 2
        }
        contentItem: ColumnLayout {
            spacing: 14
            Label {
                text: page.reviewedPlan && page.reviewedPlan.blockers.length > 0
                    ? qsTr("O perfil não pode ser aplicado ainda")
                    : qsTr("O SteamZero salvará esta política para o lançamento gerenciado.")
                color: page.reviewedPlan && page.reviewedPlan.blockers.length > 0
                    ? page.amberColor : page.textColor
                font.pixelSize: 18
                font.bold: true
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Label {
                text: page.reviewedPlan ? page.reviewedPlan.changes.join("\n") : ""
                color: page.mutedColor
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Rectangle {
                visible: page.reviewedPlan && page.reviewedPlan.blockers.length > 0
                color: "#24180b"
                border.color: page.amberColor
                radius: 7
                Layout.fillWidth: true
                Layout.minimumHeight: blockerText.implicitHeight + 28
                Label {
                    id: blockerText
                    anchors.fill: parent
                    anchors.margins: 14
                    text: page.reviewedPlan ? page.reviewedPlan.blockers.join("\n") : ""
                    color: page.amberColor
                    wrapMode: Text.WordWrap
                }
            }
            Label {
                text: page.reviewedPlan ? qsTr("Rollback: %1").arg(page.reviewedPlan.rollbackGuarantee) : ""
                color: page.mutedColor
                font.pixelSize: 12
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
                    onClicked: reviewDialog.close()
                }
                Button {
                    text: page.reviewedPlan && page.reviewedPlan.blockers.length > 0
                        ? qsTr("Abrir Sistema") : qsTr("Confirmar perfil")
                    Layout.fillWidth: true
                    Layout.minimumHeight: 48
                    Accessible.name: text
                    onClicked: {
                        if (!page.reviewedPlan)
                            return
                        if (page.reviewedPlan.blockers.length > 0) {
                            reviewDialog.close()
                            page.systemRequested()
                        } else {
                            page.applyRequested(
                                page.reviewedPlan.planId,
                                page.reviewedPlan.confirmToken
                            )
                            reviewDialog.close()
                        }
                    }
                }
            }
        }
    }

    Dialog {
        id: environmentDialog
        modal: true
        title: qsTr("Ambiente e capacidade")
        width: Math.min(page.width - 48, 620)
        x: (page.width - width) / 2
        y: (page.height - height) / 2
        standardButtons: Dialog.Close
        background: Rectangle {
            color: page.raisedColor
            radius: 10
            border.color: page.cyanColor
            border.width: 2
        }
        contentItem: ColumnLayout {
            spacing: 10
            Repeater {
                model: page.environment
                delegate: RowLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.minimumHeight: 44
                    ToolButton {
                        enabled: false
                        icon.name: modelData.id === "steam" ? "steam"
                            : modelData.id === "gamescope" ? "video-display"
                            : modelData.id === "gamemode" ? "speedometer"
                            : modelData.id === "lsfg" ? "view-media-visualization"
                            : "applications-system"
                        icon.color: modelData.state === "ready"
                            ? page.greenColor : page.amberColor
                        background: Item {}
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 1
                        Label {
                            text: "%1 — %2".arg(modelData.name).arg(modelData.statusLabel)
                            color: modelData.state === "ready"
                                ? page.greenColor : page.amberColor
                            font.bold: true
                        }
                        Label { text: modelData.detail; color: page.mutedColor }
                    }
                    Label {
                        text: modelData.owner
                        color: modelData.owner === "Sistema"
                            ? page.amberColor : page.cyanColor
                        font.pixelSize: 11
                    }
                }
            }
            Rectangle { color: page.borderColor; Layout.fillWidth: true; Layout.preferredHeight: 1 }
            Label {
                text: qsTr("%1 · TDP %2 · GPU %3 · %4 Hz").arg(
                    page.hardware.deviceLabel || "Linux"
                ).arg(
                    page.hardware.tdpMax ? "%1–%2 W".arg(page.hardware.tdpMin).arg(page.hardware.tdpMax) : qsTr("não observado")
                ).arg(
                    page.hardware.gpuMax ? "%1–%2 MHz".arg(page.hardware.gpuMin).arg(page.hardware.gpuMax) : qsTr("não observado")
                ).arg(page.hardware.refreshHz || "—")
                color: page.mutedColor
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }
    }

    ScrollView {
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: fixedActions.top
        clip: true
        contentWidth: availableWidth

        ColumnLayout {
            width: parent.width
            spacing: 14

            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 20
                Layout.rightMargin: 20
                Layout.topMargin: 18
                spacing: 18
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2
                    Label {
                        text: qsTr("Prontidão do jogo")
                        color: page.textColor
                        font.pixelSize: 28
                        font.bold: true
                    }
                    Label {
                        text: {
                            const context = page.gameplay && page.gameplay.context
                                ? page.gameplay.context : {}
                            const battery = context.battery === null || context.battery === undefined
                                ? qsTr("Bateria —") : qsTr("Bateria %1%").arg(context.battery)
                            return "%1  •  %2  •  %3".arg(context.device || "Linux").arg(battery).arg(context.mode || qsTr("Modo Desktop"))
                        }
                        color: page.mutedColor
                        font.pixelSize: 13
                    }
                }
                Label { text: qsTr("Jogo"); color: page.mutedColor }
                ComboBox {
                    id: gamePicker
                    model: page.games
                    textRole: "name"
                    currentIndex: page.gameIndex
                    enabled: page.games.length > 0
                    Layout.preferredWidth: Math.min(360, page.width * 0.3)
                    Layout.minimumHeight: 48
                    Accessible.name: qsTr("Selecionar jogo")
                    onActivated: page.gameIndex = currentIndex
                    contentItem: RowLayout {
                        spacing: 10
                        Image {
                            source: page.selectedGame.coverUrl || "../assets/steam.svg"
                            sourceSize.width: 54
                            sourceSize.height: 38
                            fillMode: Image.PreserveAspectCrop
                            Layout.preferredWidth: 54
                            Layout.preferredHeight: 38
                            Accessible.name: qsTr("Capa de %1").arg(page.selectedGame.name)
                        }
                        Label {
                            text: page.selectedGame.name
                            color: page.textColor
                            font.pixelSize: 15
                            font.bold: true
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 20
                Layout.rightMargin: 20
                spacing: 0
                Label {
                    text: qsTr("Escopo")
                    color: page.mutedColor
                    Layout.rightMargin: 12
                }
                Repeater {
                    model: [qsTr("Global"), qsTr("Por jogo"), qsTr("Portátil"), qsTr("Dock")]
                    delegate: Button {
                        required property int index
                        required property string modelData
                        text: modelData
                        checkable: true
                        checked: page.scopeIndex === index
                        Layout.preferredWidth: 116
                        Layout.minimumHeight: 44
                        Accessible.name: text
                        onClicked: page.scopeIndex = index
                        background: Rectangle {
                            color: parent.checked ? page.cyanDarkColor : page.surfaceColor
                            border.color: parent.checked || parent.activeFocus ? page.cyanColor : page.borderColor
                            border.width: parent.checked || parent.activeFocus ? 2 : 1
                            radius: 4
                        }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 20
                Layout.rightMargin: 20
                spacing: 0
                Label {
                    text: qsTr("Área")
                    color: page.mutedColor
                    Layout.rightMargin: 12
                }
                Repeater {
                    model: [qsTr("Desempenho e LSFG"), qsTr("Controles")]
                    delegate: Button {
                        required property int index
                        required property string modelData
                        text: modelData
                        checkable: true
                        checked: page.workspaceIndex === index
                        Layout.preferredWidth: index === 0 ? 174 : 126
                        Layout.minimumHeight: 44
                        Accessible.name: qsTr("Abrir área %1").arg(text)
                        onClicked: page.workspaceIndex = index
                        background: Rectangle {
                            color: parent.checked ? page.cyanDarkColor : page.surfaceColor
                            border.color: parent.checked || parent.activeFocus
                                ? page.cyanColor : page.borderColor
                            border.width: parent.checked || parent.activeFocus ? 2 : 1
                            radius: 4
                        }
                    }
                }
                Item { Layout.fillWidth: true }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.leftMargin: 20
                Layout.rightMargin: 20
                Layout.minimumHeight: 82
                color: "#0c2a21"
                border.color: page.gameplay && page.gameplay.readiness && page.gameplay.readiness.percent >= 80
                    ? page.greenColor : page.amberColor
                radius: 8
                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 16
                    Label {
                        text: page.gameplay && page.gameplay.readiness
                            ? page.gameplay.readiness.percent + "%" : "—"
                        color: page.greenColor
                        font.pixelSize: 25
                        font.bold: true
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2
                        Label {
                            text: page.gameplay && page.gameplay.readiness
                                ? page.gameplay.readiness.title : qsTr("Verificando ambiente")
                            color: page.greenColor
                            font.pixelSize: 18
                            font.bold: true
                        }
                        Label {
                            text: page.gameplay && page.gameplay.readiness
                                ? page.gameplay.readiness.detail : ""
                            color: page.mutedColor
                        }
                    }
                    ProgressBar {
                        value: page.gameplay && page.gameplay.readiness
                            ? page.gameplay.readiness.percent / 100 : 0
                        Layout.preferredWidth: page.width < 1240 ? 140 : 260
                        Accessible.name: qsTr("Prontidão do ambiente")
                        Accessible.description: qsTr("%1 por cento").arg(Math.round(value * 100))
                    }
                    Button {
                        visible: page.width < 1240
                        text: qsTr("Ambiente")
                        icon.name: "applications-system"
                        Layout.minimumHeight: 44
                        Accessible.name: qsTr("Ver ambiente e capacidade")
                        onClicked: environmentDialog.open()
                    }
                }
            }

            RowLayout {
                visible: page.workspaceIndex === 0
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.leftMargin: 20
                Layout.rightMargin: 20
                spacing: 12

                ColumnLayout {
                    id: environmentColumn
                    visible: page.width >= 1240
                    Layout.preferredWidth: 290
                    Layout.alignment: Qt.AlignTop
                    spacing: 10
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.minimumHeight: 350
                        color: page.surfaceColor
                        border.color: page.borderColor
                        radius: 8
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 12
                            spacing: 0
                            Label { text: qsTr("Ambiente"); color: page.textColor; font.pixelSize: 17; font.bold: true; Layout.bottomMargin: 8 }
                            Repeater {
                                model: page.environment
                                delegate: Item {
                                    required property var modelData
                                    Layout.fillWidth: true
                                    Layout.minimumHeight: 50
                                    RowLayout {
                                        anchors.fill: parent
                                        spacing: 8
                                        ToolButton {
                                            enabled: false
                                            icon.name: modelData.id === "steam" ? "steam"
                                                : modelData.id === "gamescope" ? "video-display"
                                                : modelData.id === "gamemode" ? "speedometer"
                                                : modelData.id === "mangohud" ? "office-chart-line"
                                                : "applications-system"
                                            icon.color: modelData.state === "ready" ? page.greenColor : page.amberColor
                                            background: Item {}
                                            Layout.preferredWidth: 32
                                        }
                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 0
                                            Label {
                                                text: "%1 — %2".arg(modelData.name).arg(modelData.statusLabel)
                                                color: modelData.state === "ready" ? page.greenColor : page.amberColor
                                                font.pixelSize: 13
                                                font.bold: true
                                                elide: Text.ElideRight
                                                Layout.fillWidth: true
                                            }
                                            Label { text: modelData.detail; color: page.mutedColor; font.pixelSize: 10; elide: Text.ElideRight; Layout.fillWidth: true }
                                        }
                                        Label {
                                            text: modelData.owner
                                            color: modelData.owner === "Sistema" ? page.amberColor : page.cyanColor
                                            font.pixelSize: 10
                                        }
                                    }
                                }
                            }
                            Button {
                                visible: page.environment.some(function(row) { return row.state !== "ready" })
                                text: qsTr("Abrir Sistema")
                                Layout.fillWidth: true
                                Layout.minimumHeight: 44
                                Accessible.name: text
                                onClicked: page.systemRequested()
                            }
                        }
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.minimumHeight: 154
                        color: page.surfaceColor
                        border.color: page.borderColor
                        radius: 8
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 12
                            spacing: 3
                            Label { text: qsTr("Capacidade do %1").arg(page.hardware.deviceLabel || "hardware"); color: page.textColor; font.bold: true }
                            Label { text: qsTr("TDP"); color: page.mutedColor; Layout.fillWidth: true; Label { anchors.right: parent.right; text: page.hardware.tdpMax ? "%1–%2 W".arg(page.hardware.tdpMin).arg(page.hardware.tdpMax) : qsTr("não observado"); color: page.textColor } }
                            Label { text: qsTr("GPU"); color: page.mutedColor; Layout.fillWidth: true; Label { anchors.right: parent.right; text: page.hardware.gpuMax ? "%1–%2 MHz".arg(page.hardware.gpuMin).arg(page.hardware.gpuMax) : qsTr("não observado"); color: page.textColor } }
                            Label { text: qsTr("Tela"); color: page.mutedColor; Layout.fillWidth: true; Label { anchors.right: parent.right; text: page.hardware.refreshHz ? page.hardware.refreshHz + " Hz" : "—"; color: page.textColor } }
                            Label { text: qsTr("Memória disponível"); color: page.mutedColor; Layout.fillWidth: true; Label { anchors.right: parent.right; text: page.hardware.memoryGb ? page.hardware.memoryGb + " GB" : "—"; color: page.textColor } }
                            Label { text: page.hardware.withinSafeLimits ? qsTr("Dentro dos limites seguros") : qsTr("Limites não confirmados"); color: page.hardware.withinSafeLimits ? page.greenColor : page.amberColor; font.pixelSize: 11 }
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 500
                    Layout.minimumHeight: 464
                    Layout.alignment: Qt.AlignTop
                    color: page.surfaceColor
                    border.color: page.borderColor
                    radius: 8
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 14
                        spacing: 7
                        Label { text: qsTr("Ajustes essenciais"); color: page.textColor; font.pixelSize: 17; font.bold: true }
                        RowLayout {
                            Layout.fillWidth: true
                            Label { text: qsTr("Perfil de desempenho"); color: page.mutedColor; Layout.preferredWidth: 112; wrapMode: Text.WordWrap }
                            Repeater {
                                model: [qsTr("Economia\n30 FPS"), qsTr("Equilibrado\n40 FPS\nRecomendado"), qsTr("Desempenho\n60 FPS")]
                                delegate: Button {
                                    required property int index
                                    required property string modelData
                                    text: modelData
                                    checkable: true
                                    checked: page.profileIndex === index
                                    Layout.fillWidth: true
                                    Layout.minimumHeight: 68
                                    Accessible.name: text.replace("\n", " ")
                                    onClicked: page.choosePerformance(index)
                                    background: Rectangle { color: parent.checked ? page.cyanDarkColor : page.raisedColor; border.color: parent.checked || parent.activeFocus ? page.cyanColor : page.borderColor; border.width: parent.checked || parent.activeFocus ? 2 : 1; radius: 6 }
                                }
                            }
                        }
                        Rectangle { color: page.borderColor; Layout.fillWidth: true; Layout.preferredHeight: 1 }
                        RowLayout {
                            Layout.fillWidth: true
                            Label { text: qsTr("Limite de FPS"); color: page.mutedColor; Layout.preferredWidth: 112 }
                            Repeater {
                                model: ["30", "40", "60"]
                                delegate: Button {
                                    required property int index
                                    required property string modelData
                                    text: modelData
                                    checkable: true
                                    checked: page.fpsIndex === index
                                    Layout.fillWidth: true
                                    Layout.minimumHeight: 42
                                    Accessible.name: qsTr("%1 FPS").arg(text)
                                    onClicked: page.fpsIndex = index
                                    background: Rectangle { color: parent.checked ? page.cyanDarkColor : page.raisedColor; border.color: parent.checked || parent.activeFocus ? page.cyanColor : page.borderColor; border.width: parent.checked || parent.activeFocus ? 2 : 1; radius: 5 }
                                }
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            enabled: page.hardware.tdpMax !== null && page.hardware.tdpMax !== undefined
                            Label { text: qsTr("TDP"); color: page.mutedColor; Layout.preferredWidth: 112 }
                            Label { text: page.hardware.tdpMin ? page.hardware.tdpMin + " W" : "—"; color: page.mutedColor }
                            Slider {
                                from: page.hardware.tdpMin || 3
                                to: page.hardware.tdpMax || 15
                                stepSize: 1
                                value: page.tdpValue
                                Layout.fillWidth: true
                                Accessible.name: qsTr("TDP")
                                Accessible.description: qsTr("%1 watts, limite %2 watts").arg(Math.round(value)).arg(to)
                                onMoved: page.tdpValue = Math.round(value)
                            }
                            Label { text: page.hardware.tdpMax ? page.tdpValue + " W / " + page.hardware.tdpMax + " W" : qsTr("não observado"); color: page.textColor; Layout.preferredWidth: 94 }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Label { text: qsTr("Clock da GPU"); color: page.mutedColor; Layout.preferredWidth: 112 }
                            Repeater {
                                model: [qsTr("Automático"), qsTr("Manual")]
                                delegate: Button {
                                    required property int index
                                    required property string modelData
                                    text: modelData
                                    checked: page.gpuModeIndex === index
                                    checkable: true
                                    Layout.fillWidth: true
                                    Layout.minimumHeight: 42
                                    Accessible.name: text
                                    enabled: index === 0 || page.hardware.gpuMax
                                    onClicked: page.gpuModeIndex = index
                                    background: Rectangle { color: parent.checked ? page.cyanDarkColor : page.raisedColor; border.color: parent.checked || parent.activeFocus ? page.cyanColor : page.borderColor; border.width: parent.checked || parent.activeFocus ? 2 : 1; radius: 5 }
                                }
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Label { text: qsTr("Gamescope"); color: page.textColor; Layout.preferredWidth: 112; font.bold: true }
                            Label { text: qsTr("Composição e limite de quadros"); color: page.mutedColor; Layout.fillWidth: true }
                            Label { text: "SteamZero"; color: page.cyanColor; font.pixelSize: 10 }
                            Switch { checked: page.gamescopeEnabled; enabled: page.environmentById("gamescope").state === "ready"; Accessible.name: qsTr("Ativar Gamescope"); onToggled: page.gamescopeEnabled = checked }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Label { text: qsTr("Feral GameMode"); color: page.textColor; Layout.preferredWidth: 112; font.bold: true }
                            Label { text: qsTr("Prioridade de CPU e processos"); color: page.mutedColor; Layout.fillWidth: true }
                            Label { text: "Steam"; color: page.cyanColor; font.pixelSize: 10 }
                            Switch { checked: page.gameModeEnabled; enabled: page.environmentById("gamemode").state === "ready"; Accessible.name: qsTr("Ativar Feral GameMode"); onToggled: page.gameModeEnabled = checked }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Label { text: "MangoHud"; color: page.mutedColor; Layout.preferredWidth: 112 }
                            Repeater {
                                model: [qsTr("Desligado"), qsTr("Básico"), qsTr("Detalhado")]
                                delegate: Button {
                                    required property int index
                                    required property string modelData
                                    text: modelData
                                    checked: page.mangoIndex === index
                                    checkable: true
                                    enabled: index === 0 || page.environmentById("mangohud").state === "ready"
                                    Layout.fillWidth: true
                                    Layout.minimumHeight: 42
                                    Accessible.name: text
                                    onClicked: page.mangoIndex = index
                                    background: Rectangle { color: parent.checked ? page.cyanDarkColor : page.raisedColor; border.color: parent.checked || parent.activeFocus ? page.cyanColor : page.borderColor; border.width: parent.checked || parent.activeFocus ? 2 : 1; radius: 5 }
                                }
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Label { text: qsTr("Upscaling"); color: page.mutedColor; Layout.preferredWidth: 112 }
                            ComboBox {
                                model: [qsTr("Nativo"), qsTr("FSR 2 · Qualidade"), qsTr("FSR 2 · Balanceado"), qsTr("Gamescope FSR")]
                                currentIndex: page.upscalingIndex
                                Layout.fillWidth: true
                                Layout.minimumHeight: 44
                                Accessible.name: qsTr("Selecionar upscaling")
                                onActivated: page.upscalingIndex = currentIndex
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Label {
                                text: qsTr("Frame generation")
                                color: page.mutedColor
                                Layout.preferredWidth: 112
                                wrapMode: Text.WordWrap
                            }
                            ComboBox {
                                id: frameGenerationPicker
                                model: [qsTr("Desligado"), "LSFG 2×", "LSFG 3×", "LSFG 4×"]
                                currentIndex: page.frameGenerationIndex
                                Layout.fillWidth: true
                                Layout.minimumHeight: 44
                                Accessible.name: qsTr("Geração de quadros LSFG por jogo")
                                Accessible.description: page.environmentById("lsfg").state === "ready"
                                    ? qsTr("LSFG-VK pronto")
                                    : qsTr("Componente ausente; a revisão encaminhará para Sistema")
                                onActivated: page.frameGenerationIndex = currentIndex
                            }
                            Label {
                                text: page.environmentById("lsfg").state === "ready"
                                    ? qsTr("Pronto") : qsTr("Abrir Sistema")
                                color: page.environmentById("lsfg").state === "ready"
                                    ? page.greenColor : page.amberColor
                                font.pixelSize: 11
                                font.bold: true
                            }
                        }
                        Button {
                            text: qsTr("Configurações avançadas")
                            icon.name: "go-down"
                            flat: true
                            Layout.fillWidth: true
                            Layout.minimumHeight: 42
                            Accessible.name: text
                        }
                    }
                }

                Rectangle {
                    Layout.preferredWidth: page.width < 1240 ? 232 : 250
                    Layout.minimumHeight: 464
                    Layout.alignment: Qt.AlignTop
                    color: page.surfaceColor
                    border.color: page.borderColor
                    radius: 8
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 16
                        spacing: 10
                        Label { text: qsTr("Impacto esperado"); color: page.textColor; font.pixelSize: 17; font.bold: true }
                        Repeater {
                            model: [
                                {"label": qsTr("Bateria"), "value": page.estimatedBattery(), "icon": "battery-080"},
                                {"label": qsTr("Resolução"), "value": page.impact.resolution || "—", "icon": "video-display"},
                                {"label": qsTr("Fluidez"), "value": [30, 40, 60][page.fpsIndex] + " FPS estáveis", "icon": "speedometer"},
                                {"label": qsTr("Quadros gerados"), "value": page.frameGenerationSummary(), "icon": "view-media-visualization"}
                            ]
                            delegate: RowLayout {
                                required property var modelData
                                Layout.fillWidth: true
                                Layout.minimumHeight: 64
                                ToolButton { enabled: false; icon.name: modelData.icon; icon.color: page.greenColor; background: Item {} }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 1
                                    Label { text: modelData.label; color: page.mutedColor; font.pixelSize: 12 }
                                    Label { text: modelData.value; color: page.greenColor; font.pixelSize: 18; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true }
                                }
                            }
                        }
                        Rectangle { color: page.borderColor; Layout.fillWidth: true; Layout.preferredHeight: 1 }
                        Label {
                            text: qsTr("Perfil salvo (desejado): %1 · %2 FPS").arg(
                                [qsTr("Economia"), qsTr("Equilibrado"), qsTr("Desempenho")][page.valueIndex(["economy", "balanced", "performance"], page.currentProfile.profile, 1)]
                            ).arg(page.currentProfile.fps || 40)
                            color: page.cyanColor
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                        Label { text: qsTr("SteamZero"); color: page.greenColor; font.bold: true }
                        Label { text: qsTr("Perfis e orquestração"); color: page.mutedColor; font.pixelSize: 11 }
                        Label { text: qsTr("Steam"); color: page.cyanColor; font.bold: true }
                        Label { text: qsTr("Contexto de jogo e runtime"); color: page.mutedColor; font.pixelSize: 11 }
                        Label { text: qsTr("Sistema"); color: page.amberColor; font.bold: true }
                        Label { text: qsTr("Drivers e componentes do host"); color: page.mutedColor; font.pixelSize: 11; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                    }
                }
            }

            Rectangle {
                visible: page.workspaceIndex === 1
                Layout.fillWidth: true
                Layout.leftMargin: 20
                Layout.rightMargin: 20
                Layout.minimumHeight: 142
                color: page.surfaceColor
                border.color: page.borderColor
                radius: 8
                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 18
                    ToolButton {
                        enabled: false
                        icon.name: "input-gaming"
                        icon.color: page.cyanColor
                        icon.width: 34
                        icon.height: 34
                        background: Item {}
                        Layout.preferredWidth: 48
                    }
                    ColumnLayout {
                        Layout.preferredWidth: 280
                        spacing: 3
                        Label {
                            text: qsTr("Controles por jogo")
                            color: page.textColor
                            font.pixelSize: 18
                            font.bold: true
                        }
                        Label {
                            text: qsTr("Steam Input mantém a posse do controle no gameplay. O SteamZero guarda a política desejada sem editar arquivos internos da Steam.")
                            color: page.mutedColor
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                        Label {
                            text: page.environmentById("steam").state === "ready"
                                ? qsTr("Steam Input disponível") : qsTr("Steam indisponível")
                            color: page.environmentById("steam").state === "ready"
                                ? page.greenColor : page.amberColor
                            font.pixelSize: 11
                            font.bold: true
                        }
                    }
                    Rectangle {
                        color: page.borderColor
                        Layout.preferredWidth: 1
                        Layout.fillHeight: true
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 6
                        Label { text: qsTr("Layout para %1").arg(page.selectedGame.name); color: page.mutedColor }
                        ComboBox {
                            id: controllerLayoutPicker
                            model: [
                                qsTr("Recomendado pela Steam"), qsTr("Layout oficial"),
                                qsTr("Layout da comunidade"), qsTr("SteamZero · Gamepad"),
                                qsTr("SteamZero · Teclado e mouse"), qsTr("Personalizado")
                            ]
                            currentIndex: page.controllerLayoutIndex
                            enabled: page.games.length > 0
                            Layout.fillWidth: true
                            Layout.minimumHeight: 48
                            Accessible.name: qsTr("Escolher layout de controles para o jogo")
                            onActivated: page.controllerLayoutIndex = currentIndex
                        }
                        Label {
                            text: qsTr("A escolha entra no mesmo plano revisável do perfil de gameplay.")
                            color: page.cyanColor
                            font.pixelSize: 11
                        }
                    }
                    Button {
                        id: editSteamInputButton
                        text: qsTr("Editar no Steam")
                        icon.name: "steam"
                        enabled: page.games.length > 0
                            && page.environmentById("steam").state === "ready"
                        Layout.preferredWidth: 180
                        Layout.minimumHeight: 48
                        Accessible.name: qsTr("Abrir configuração Steam Input de %1").arg(page.selectedGame.name)
                        onClicked: page.steamInputRequested(String(page.selectedGame.id || ""))
                        KeyNavigation.tab: frameGenerationPicker
                    }
                }
            }

        }
    }

    Rectangle {
        id: fixedActions
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 78
        color: page.backgroundColor
        border.color: page.borderColor
        z: 3
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 20
            anchors.rightMargin: 20
            anchors.topMargin: 10
            anchors.bottomMargin: 14
            spacing: 12
            Button {
                text: qsTr("Restaurar perfil seguro")
                Layout.fillWidth: true
                Layout.minimumHeight: 54
                Accessible.name: text
                onClicked: page.planRequested(page.safePayload())
            }
            Button {
                text: qsTr("Revisar e aplicar perfil")
                enabled: page.games.length > 0
                Layout.fillWidth: true
                Layout.minimumHeight: 54
                Accessible.name: text
                onClicked: page.planRequested(page.payload())
                background: Rectangle {
                    color: parent.enabled ? "#069bd7" : page.raisedColor
                    border.color: parent.activeFocus ? page.textColor : page.cyanColor
                    border.width: parent.activeFocus ? 2 : 1
                    radius: 7
                }
                contentItem: Label {
                    text: parent.text
                    color: parent.enabled ? "white" : page.mutedColor
                    font.pixelSize: 16
                    font.bold: true
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }
        }
    }
}
