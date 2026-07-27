// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import QtQuick.Window

Item {
    id: page

    required property var gameplay
    property var desktopStatus: ({})
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
    signal profileRollbackRequested(string operationId)
    signal systemRequested()
    signal steamInputRequested(string gameId)
    signal launcherRecoveryRequested(string gameId)
    signal launchOptionsPlanRequested(string gameId)
    signal launchOptionsApplyRequested(string planId, string confirmToken, string gameId)
    signal launchOptionsRollbackRequested(string operationId)
    signal maintenancePlanRequested(string gameId, var categories)
    signal maintenanceApplyRequested(string planId, string confirmToken, string confirmPhrase)
    signal maintenanceRecoveryRequested()
    signal mediaPlanRequested(string gameId, string accountId, string packagePath)
    signal mediaApplyRequested(string planId, string confirmToken)
    signal mediaRollbackRequested(string operationId)
    signal desktopProfilePlanRequested(string profile)
    signal desktopProfileApplyRequested(string planId, string confirmToken)
    signal desktopSafeResetRequested()
    signal desktopConflictRequested()
    signal desktopRecoveryRequested()
    signal desktopKeyboardRequested(string language)
    signal desktopAshytermRequested()
    signal desktopPanelAutoHideRequested(bool enable)
    signal desktopKeyboardSoundRequested(bool enable)
    signal desktopKeyboardThemeRequested(bool dark)
    signal desktopGamemodeReturnRequested()

    property int gameIndex: 0
    property int scopeIndex: 1
    property int profileIndex: 1
    property int fpsIndex: 1
    property int tdpValue: 10
    property int gpuModeIndex: 0
    property int mangoIndex: 0
    property int vkBasaltIndex: 0
    property int upscalingIndex: 1
    property int frameGenerationIndex: 0
    property int controllerLayoutIndex: 0
    property int workspaceIndex: 0
    property string initialArea: "performance"
    property bool gamescopeEnabled: true
    property bool gameModeEnabled: true
    property bool initialized: false
    property var reviewedPlan: null
    property string profileLastOperationId: ""
    property var launchOptionsPlan: null
    property var maintenancePlan: null
    property var selectedMaintenanceCategories: ["shader-cache"]
    property var mediaPlan: null
    property string mediaPackagePath: ""
    property string mediaLastOperationId: ""
    property bool reducedMotion: false
    property Item dialogInvoker: null
    readonly property bool compactLayout: width <= 1296 || height <= 720
    readonly property bool ultrawideLayout: width >= 1900
    readonly property int responsiveGutter: compactLayout ? 12 : 20
    readonly property int minimumTouchTarget: 48
    readonly property int bottomSafeInset: minimumTouchTarget + responsiveGutter
    readonly property int motionDuration: reducedMotion ? 0 : 180
    readonly property int contentMaxWidth: ultrawideLayout ? 1400 : 1800
    readonly property bool showSupplementaryPanels: !compactLayout && width >= 1240
    property alias reviewApplyControl: reviewApplyButton
    property alias gameplayScrollControl: gameplayScroll
    property alias scopeControlRepeater: gameplayScopeRepeater
    property alias areaControlRepeater: gameplayAreaRepeater
    property alias gamePickerControl: gamePicker
    property alias fixedActionsControl: fixedActions
    property alias desktopModeControl: desktopModePanel
    property alias fpsControlRepeater: gameplayFpsRepeater
    property alias vkBasaltControl: vkBasaltPicker
    property alias maintenanceReviewControl: maintenanceReviewButton

    readonly property var games: gameplay && gameplay.games ? gameplay.games : []
    readonly property var environment: gameplay && gameplay.environment ? gameplay.environment : []
    readonly property var hardware: gameplay && gameplay.hardware ? gameplay.hardware : ({})
    readonly property var impact: gameplay && gameplay.impact ? gameplay.impact : ({})
    readonly property var vkBasalt: gameplay && gameplay.vkBasalt
        ? gameplay.vkBasalt : ({"presets": []})
    readonly property var currentProfile: gameplay && gameplay.currentProfile
        ? gameplay.currentProfile : ({})
    readonly property var launcher: gameplay && gameplay.launcher ? gameplay.launcher : ({})
    readonly property var launchConfiguration: launcher && launcher.configuration
        ? launcher.configuration : ({})
    readonly property var maintenance: gameplay && gameplay.maintenance
        ? gameplay.maintenance : ({"totalBytes": 0, "categories": [], "excluded": []})
    readonly property var media: gameplay && gameplay.media
        ? gameplay.media : ({"accounts": []})
    readonly property var sessionManager: gameplay && gameplay.sessionManager
        ? gameplay.sessionManager : ({"state": "degraded", "directBoot": {"state": "gated"}})
    readonly property var selectedGame: games.length > 0 && gameIndex < games.length
        ? games[gameIndex] : ({"id": "", "name": qsTr("Nenhum jogo instalado"), "coverUrl": ""})
    readonly property bool touchMode: desktopStatus.current && desktopStatus.current.profile
        ? desktopStatus.current.profile.touchMode : false

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
        vkBasaltIndex = valueIndex(
            ["off", "cas", "fxaa", "smaa"], profile.vkBasalt, 0
        )
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
            "vkBasalt": ["off", "cas", "fxaa", "smaa"][vkBasaltIndex],
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
        result.vkBasalt = "off"
        result.upscaling = "native"
        result.frameGeneration = "off"
        result.controllerLayout = "steam-recommended"
        return result
    }

    function currentFocusItem() {
        const hostWindow = page.Window.window
        return hostWindow ? hostWindow.activeFocusItem : null
    }

    function rememberDialogInvoker() {
        const active = currentFocusItem()
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

    function showPlan(plan) {
        rememberDialogInvoker()
        reviewedPlan = plan
        reviewDialog.open()
    }

    function showLaunchOptionsPlan(plan) {
        rememberDialogInvoker()
        launchOptionsPlan = plan
        launchOptionsDialog.open()
    }

    function showMaintenancePlan(plan) {
        rememberDialogInvoker()
        maintenancePlan = plan
        cleanupPhrase.text = ""
        maintenanceDialog.open()
    }

    function showMediaPlan(plan) {
        rememberDialogInvoker()
        mediaPlan = plan
        mediaDialog.open()
    }

    function showDesktopPlan(plan) {
        desktopModePanel.showPlan(plan)
    }

    function formatBytes(value) {
        const bytes = Number(value || 0)
        if (bytes < 1024)
            return bytes + " B"
        if (bytes < 1024 * 1024)
            return (bytes / 1024).toFixed(1) + " KiB"
        if (bytes < 1024 * 1024 * 1024)
            return (bytes / (1024 * 1024)).toFixed(1) + " MiB"
        return (bytes / (1024 * 1024 * 1024)).toFixed(2) + " GiB"
    }

    function selectedMaintenanceBytes() {
        var total = 0
        var categories = page.maintenance.categories || []
        for (var index = 0; index < categories.length; index++) {
            var category = categories[index]
            if (page.selectedMaintenanceCategories.indexOf(category.id) >= 0)
                total += Number(category.sizeBytes) || 0
        }
        return total
    }

    function choosePerformance(index) {
        profileIndex = index
        fpsIndex = index
        tdpValue = [7, 10, 15][index]
    }

    function moveVerticalFocus(forward) {
        const hostWindow = page.Window.window
        const active = hostWindow ? hostWindow.activeFocusItem : null
        const next = active ? active.nextItemInFocusChain(forward) : null
        if (next) {
            next.forceActiveFocus(Qt.TabFocusReason)
            Qt.callLater(function() { page.revealFocusedItem(next) })
        }
    }

    function revealFocusedItem(item) {
        if (!gameplayScroll.contentItem || !item)
            return
        const flickable = gameplayScroll.contentItem
        const point = item.mapToItem(flickable.contentItem, 0, 0)
        const top = point.y - 12
        const bottom = point.y + item.height + 12
        if (top < flickable.contentY)
            flickable.contentY = Math.max(0, top)
        else if (bottom > flickable.contentY + flickable.height)
            flickable.contentY = Math.min(
                Math.max(0, flickable.contentHeight - flickable.height),
                bottom - flickable.height
            )
    }

    Keys.onUpPressed: function(event) {
        page.moveVerticalFocus(false)
        event.accepted = true
    }
    Keys.onDownPressed: function(event) {
        page.moveVerticalFocus(true)
        event.accepted = true
    }

    Connections {
        target: page.Window.window
        enabled: target !== null
        ignoreUnknownSignals: true
        function onActiveFocusItemChanged() {
            const item = target ? target.activeFocusItem : null
            if (item)
                Qt.callLater(function() { page.revealFocusedItem(item) })
        }
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
    function areaIndex(area) {
        if (area === "controls")
            return 1
        if (area === "library")
            return 2
        if (area === "desktop")
            return 3
        return 0
    }

    onInitialAreaChanged: workspaceIndex = areaIndex(initialArea)
    Component.onCompleted: {
        workspaceIndex = areaIndex(initialArea)
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
        onClosed: page.restoreDialogFocus()
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
        onClosed: page.restoreDialogFocus()
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
                    Layout.minimumHeight: 48
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

    Dialog {
        id: launchOptionsDialog
        modal: true
        title: qsTr("Configurar lançamento automaticamente")
        width: Math.min(page.width - 48, 680)
        x: (page.width - width) / 2
        y: (page.height - height) / 2
        standardButtons: Dialog.NoButton
        onClosed: page.restoreDialogFocus()
        background: Rectangle {
            color: page.raisedColor
            radius: 10
            border.color: page.cyanColor
            border.width: 2
        }
        contentItem: ColumnLayout {
            spacing: 14
            Label {
                text: page.launchOptionsPlan && page.launchOptionsPlan.replacesExisting
                    ? qsTr("Este jogo já possui Launch Options. O valor será substituído, mas poderá ser restaurado byte a byte.")
                    : qsTr("O wrapper SteamZero será adicionado somente ao jogo selecionado.")
                color: page.launchOptionsPlan && page.launchOptionsPlan.replacesExisting
                    ? page.amberColor : page.textColor
                font.bold: true
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Label {
                text: page.launchOptionsPlan
                    ? page.launchOptionsPlan.changes.join("\n") : ""
                color: page.mutedColor
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Label {
                text: qsTr("A Steam precisa permanecer fechada durante a aplicação. Rollback: G-FULL.")
                color: page.greenColor
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
                    onClicked: launchOptionsDialog.close()
                }
                Button {
                    text: qsTr("Configurar e verificar")
                    Layout.fillWidth: true
                    Layout.minimumHeight: 48
                    Accessible.name: text
                    onClicked: {
                        if (!page.launchOptionsPlan)
                            return
                        page.launchOptionsApplyRequested(
                            page.launchOptionsPlan.planId,
                            page.launchOptionsPlan.confirmToken,
                            String(page.launchOptionsPlan.gameId)
                        )
                        launchOptionsDialog.close()
                    }
                }
            }
        }
    }

    Dialog {
        id: maintenanceDialog
        modal: true
        title: qsTr("Revisar limpeza segura")
        width: Math.min(page.width - 48, 660)
        x: (page.width - width) / 2
        y: (page.height - height) / 2
        standardButtons: Dialog.NoButton
        onClosed: page.restoreDialogFocus()
        background: Rectangle { color: page.raisedColor; radius: 10; border.color: page.amberColor; border.width: 2 }
        contentItem: ColumnLayout {
            spacing: 14
            Label {
                text: page.maintenancePlan
                    ? qsTr("%1 serão liberados de caches regeneráveis.").arg(page.formatBytes(page.maintenancePlan.totalBytes))
                    : ""
                color: page.textColor
                font.pixelSize: 18
                font.bold: true
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Label {
                text: qsTr("Compatdata, saves, jogos, Workshop e downloads nunca entram nesta operação. A Steam deve estar fechada.")
                color: page.mutedColor
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Label {
                text: qsTr("Esta remoção não possui rollback porque o espaço é liberado de fato. Digite LIBERAR ESPACO para confirmar.")
                color: page.amberColor
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            TextField {
                id: cleanupPhrase
                placeholderText: "LIBERAR ESPACO"
                inputMethodHints: Qt.ImhNone
                onActiveFocusChanged: { if (activeFocus && page.touchMode) Qt.inputMethod.show() }
                EnterKey.type: Qt.EnterKeyDone
                Layout.fillWidth: true
                Layout.minimumHeight: 48
                Accessible.name: qsTr("Frase de confirmação destrutiva")
            }
            RowLayout {
                Layout.fillWidth: true
                Button { text: qsTr("Cancelar"); Layout.fillWidth: true; Layout.minimumHeight: 48; onClicked: maintenanceDialog.close() }
                Button {
                    text: qsTr("Liberar espaço")
                    enabled: cleanupPhrase.text === "LIBERAR ESPACO"
                    Layout.fillWidth: true
                    Layout.minimumHeight: 48
                    Accessible.name: text
                    onClicked: {
                        page.maintenanceApplyRequested(
                            page.maintenancePlan.planId,
                            page.maintenancePlan.confirmToken,
                            cleanupPhrase.text
                        )
                        maintenanceDialog.close()
                    }
                }
            }
        }
    }

    Dialog {
        id: mediaDialog
        modal: true
        title: qsTr("Aplicar pacote de mídia")
        width: Math.min(page.width - 48, 660)
        x: (page.width - width) / 2
        y: (page.height - height) / 2
        standardButtons: Dialog.NoButton
        onClosed: page.restoreDialogFocus()
        background: Rectangle { color: page.raisedColor; radius: 10; border.color: page.cyanColor; border.width: 2 }
        contentItem: ColumnLayout {
            spacing: 14
            Label {
                text: page.mediaPlan
                    ? qsTr("Itens: %1 · variantes substituídas: %2").arg(page.mediaPlan.assets.join(", ")).arg(page.mediaPlan.replacedVariants)
                    : ""
                color: page.textColor
                font.pixelSize: 17
                font.bold: true
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Label {
                text: qsTr("A arte atual será preservada byte a byte e poderá ser restaurada. Nenhuma mídia é baixada pelo SteamZero.")
                color: page.greenColor
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            RowLayout {
                Layout.fillWidth: true
                Button { text: qsTr("Cancelar"); Layout.fillWidth: true; Layout.minimumHeight: 48; onClicked: mediaDialog.close() }
                Button {
                    text: qsTr("Aplicar com rollback")
                    Layout.fillWidth: true
                    Layout.minimumHeight: 48
                    Accessible.name: text
                    onClicked: {
                        page.mediaApplyRequested(page.mediaPlan.planId, page.mediaPlan.confirmToken)
                        mediaDialog.close()
                    }
                }
            }
        }
    }

    FolderDialog {
        id: mediaFolderDialog
        title: qsTr("Selecionar pacote local de mídia")
        onAccepted: {
            const encoded = selectedFolder.toString().replace(/^file:\/\//, "")
            page.mediaPackagePath = decodeURIComponent(encoded)
        }
    }

    ScrollView {
        id: gameplayScroll
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: fixedActions.top
        clip: true
        contentWidth: availableWidth
        bottomPadding: page.bottomSafeInset

        ColumnLayout {
            width: Math.min(gameplayScroll.availableWidth, page.contentMaxWidth)
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: page.compactLayout ? 9 : 14

            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: page.responsiveGutter
                Layout.rightMargin: page.responsiveGutter
                Layout.topMargin: page.compactLayout ? 10 : 18
                spacing: page.compactLayout ? 10 : 18
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2
                    Label {
                        text: page.workspaceIndex === 3
                            ? qsTr("Experiência no Modo Desktop") : qsTr("Prontidão do jogo")
                        color: page.textColor
                        font.pixelSize: page.compactLayout ? 23 : 28
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
                Label { visible: page.workspaceIndex !== 3; text: qsTr("Jogo"); color: page.mutedColor }
                SteamComboBox {
                    id: gamePicker
                    model: page.games
                    textRole: "name"
                    currentIndex: page.gameIndex
                    enabled: page.games.length > 0
                    visible: page.workspaceIndex !== 3
                    Layout.preferredWidth: page.compactLayout ? 280
                        : Math.min(360, page.width * 0.3)
                    Layout.minimumHeight: page.minimumTouchTarget
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
                visible: page.workspaceIndex !== 3
                Layout.fillWidth: true
                Layout.leftMargin: page.responsiveGutter
                Layout.rightMargin: page.responsiveGutter
                spacing: 0
                Label {
                    text: qsTr("Escopo")
                    color: page.mutedColor
                    Layout.rightMargin: 12
                }
                Repeater {
                    id: gameplayScopeRepeater
                    model: [qsTr("Global"), qsTr("Por jogo"), qsTr("Portátil"), qsTr("Dock")]
                    delegate: Button {
                        required property int index
                        required property string modelData
                        text: modelData
                        checkable: true
                        checked: page.scopeIndex === index
                        Layout.fillWidth: page.compactLayout
                        Layout.preferredWidth: page.compactLayout ? -1 : 116
                        Layout.minimumHeight: page.minimumTouchTarget
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
                Layout.leftMargin: page.responsiveGutter
                Layout.rightMargin: page.responsiveGutter
                spacing: 0
                Label {
                    text: qsTr("Área")
                    color: page.mutedColor
                    Layout.rightMargin: 12
                }
                Repeater {
                    id: gameplayAreaRepeater
                    model: [
                        qsTr("Desempenho e LSFG"), qsTr("Controles"),
                        qsTr("Biblioteca"), qsTr("Modo Desktop")
                    ]
                    delegate: Button {
                        required property int index
                        required property string modelData
                        text: modelData
                        checkable: true
                        checked: page.workspaceIndex === index
                        Layout.fillWidth: page.compactLayout
                        Layout.preferredWidth: page.compactLayout ? -1
                            : index === 0 ? 174 : index === 3 ? 142 : 126
                        Layout.minimumHeight: page.minimumTouchTarget
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
                visible: page.workspaceIndex !== 3
                Layout.fillWidth: true
                Layout.leftMargin: page.responsiveGutter
                Layout.rightMargin: page.responsiveGutter
                Layout.minimumHeight: launcherColumn.implicitHeight
                    + (page.compactLayout ? 16 : 24)
                color: page.launcher.state === "observed" ? "#0c2a21"
                    : page.launcher.state === "stale" || page.launcher.state === "degraded"
                    ? "#24180b" : page.surfaceColor
                border.color: page.launcher.state === "observed" ? page.greenColor
                    : page.launcher.state === "stale" || page.launcher.state === "degraded"
                    ? page.amberColor : page.borderColor
                radius: 8
                ColumnLayout {
                    id: launcherColumn
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.margins: page.compactLayout ? 8 : 12
                    spacing: page.compactLayout ? 4 : 7
                    RowLayout {
                        Layout.fillWidth: true
                        Label {
                            text: qsTr("Lançamento gerenciado")
                            color: page.textColor
                            font.bold: true
                        }
                        Label {
                            text: page.launcher.statusLabel || qsTr("Perfil recomendado")
                            color: page.launcher.state === "observed"
                                ? page.greenColor : page.amberColor
                            font.bold: true
                        }
                        Item { Layout.fillWidth: true }
                        Button {
                            visible: Boolean(page.launcher.recoveryRequired)
                            text: qsTr("Restaurar estado")
                            Layout.minimumHeight: 48
                            Accessible.name: text
                            onClicked: page.launcherRecoveryRequested(
                                String(page.selectedGame.id || "")
                            )
                        }
                    }
                    TextField {
                        visible: Boolean(page.launcher.launchOption)
                        text: page.launcher.launchOption || ""
                        readOnly: true
                        selectByMouse: true
                        inputMethodHints: Qt.ImhNone
                        onActiveFocusChanged: { if (activeFocus && page.touchMode) Qt.inputMethod.show() }
                        color: page.textColor
                        font.family: "monospace"
                        Layout.fillWidth: true
                        Accessible.name: qsTr("Opção de inicialização Steam para o jogo")
                        background: Rectangle {
                            color: page.backgroundColor
                            border.color: page.borderColor
                            radius: 5
                        }
                    }
                    Label {
                        visible: Boolean(page.launcher.launchOption)
                        text: qsTr("Use esta linha nas opções de inicialização do jogo; o perfil só vira observado durante a execução real.")
                        color: page.mutedColor
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    RowLayout {
                        visible: Boolean(page.selectedGame.id)
                        Layout.fillWidth: true
                        Label {
                            text: page.launchConfiguration.statusLabel
                                || qsTr("Configuração Steam indisponível")
                            color: page.launchConfiguration.managed
                                ? page.greenColor : page.amberColor
                            wrapMode: Text.WordWrap
                        }
                        Button {
                            visible: ["missing", "foreign", "steam-running"].indexOf(
                                page.launchConfiguration.state
                            ) >= 0
                            text: page.launchConfiguration.state === "steam-running"
                                ? qsTr("Feche a Steam")
                                : page.width < 1000
                                    ? qsTr("Configurar")
                                    : qsTr("Configurar na Steam")
                            enabled: page.launchConfiguration.state !== "steam-running"
                            Layout.minimumHeight: 48
                            Accessible.name: page.launchConfiguration.state === "steam-running"
                                ? text : qsTr("Configurar Launch Options automaticamente na Steam")
                            onClicked: page.launchOptionsPlanRequested(
                                String(page.selectedGame.id)
                            )
                        }
                        Button {
                            visible: Boolean(page.launchConfiguration.lastOperationId)
                            text: qsTr("Desfazer configuração")
                            Layout.minimumHeight: 48
                            Accessible.name: text
                            onClicked: page.launchOptionsRollbackRequested(
                                String(page.launchConfiguration.lastOperationId)
                            )
                        }
                        Item { Layout.fillWidth: true }
                    }
                }
            }

            Rectangle {
                visible: page.workspaceIndex !== 3
                Layout.fillWidth: true
                Layout.leftMargin: page.responsiveGutter
                Layout.rightMargin: page.responsiveGutter
                Layout.minimumHeight: page.compactLayout ? 64 : 82
                color: "#0c2a21"
                border.color: page.gameplay && page.gameplay.readiness && page.gameplay.readiness.percent >= 80
                    ? page.greenColor : page.amberColor
                radius: 8
                RowLayout {
                    anchors.fill: parent
                    anchors.margins: page.compactLayout ? 10 : 16
                    Label {
                        text: page.gameplay && page.gameplay.readiness
                            ? page.gameplay.readiness.percent + "%" : "—"
                        color: page.greenColor
                        font.pixelSize: page.compactLayout ? 21 : 25
                        font.bold: true
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2
                        Label {
                            text: page.gameplay && page.gameplay.readiness
                                ? page.gameplay.readiness.title : qsTr("Verificando ambiente")
                            color: page.greenColor
                            font.pixelSize: page.compactLayout ? 15 : 18
                            font.bold: true
                        }
                        Label {
                            text: page.gameplay && page.gameplay.readiness
                                ? String(page.gameplay.readiness.detail || "") : ""
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
                        Layout.minimumHeight: 48
                        Accessible.name: qsTr("Ver ambiente e capacidade")
                        onClicked: {
                            page.rememberDialogInvoker()
                            environmentDialog.open()
                        }
                    }
                }
            }

            RowLayout {
                visible: page.workspaceIndex === 0
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.leftMargin: page.responsiveGutter
                Layout.rightMargin: page.responsiveGutter
                spacing: page.compactLayout ? 8 : 12

                ColumnLayout {
                    id: environmentColumn
                    visible: page.showSupplementaryPanels
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
                                Layout.minimumHeight: 48
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
                    Layout.minimumWidth: page.compactLayout ? 0 : 500
                    Layout.minimumHeight: page.compactLayout ? 430 : 464
                    Layout.alignment: Qt.AlignTop
                    color: page.surfaceColor
                    border.color: page.borderColor
                    radius: 8
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: page.compactLayout ? 10 : 14
                        spacing: page.compactLayout ? 5 : 7
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
                                    Layout.minimumHeight: page.compactLayout ? 56 : 68
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
                                id: gameplayFpsRepeater
                                model: ["30", "40", "60"]
                                delegate: Button {
                                    required property int index
                                    required property string modelData
                                    text: modelData
                                    checkable: true
                                    checked: page.fpsIndex === index
                                    Layout.fillWidth: true
                                    Layout.minimumHeight: 48
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
                                Layout.minimumHeight: page.minimumTouchTarget
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
                                    Layout.minimumHeight: 48
                                    Accessible.name: text
                                    enabled: index === 0 || Boolean(page.hardware.gpuMax)
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
                            Switch {
                                checked: page.gamescopeEnabled
                                enabled: page.environmentById("gamescope").state === "ready"
                                Layout.minimumWidth: page.minimumTouchTarget
                                Layout.minimumHeight: page.minimumTouchTarget
                                Accessible.name: qsTr("Ativar Gamescope")
                                onToggled: page.gamescopeEnabled = checked
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Label { text: qsTr("Feral GameMode"); color: page.textColor; Layout.preferredWidth: 112; font.bold: true }
                            Label { text: qsTr("Prioridade de CPU e processos"); color: page.mutedColor; Layout.fillWidth: true }
                            Label { text: "Steam"; color: page.cyanColor; font.pixelSize: 10 }
                            Switch {
                                checked: page.gameModeEnabled
                                enabled: page.environmentById("gamemode").state === "ready"
                                Layout.minimumWidth: page.minimumTouchTarget
                                Layout.minimumHeight: page.minimumTouchTarget
                                Accessible.name: qsTr("Ativar Feral GameMode")
                                onToggled: page.gameModeEnabled = checked
                            }
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
                                    Layout.minimumHeight: 48
                                    Accessible.name: text
                                    onClicked: page.mangoIndex = index
                                    background: Rectangle { color: parent.checked ? page.cyanDarkColor : page.raisedColor; border.color: parent.checked || parent.activeFocus ? page.cyanColor : page.borderColor; border.width: parent.checked || parent.activeFocus ? 2 : 1; radius: 5 }
                                }
                            }
                        }
                        Label {
                            visible: Boolean(gameplay && gameplay.hud && gameplay.hud.evidence)
                            text: qsTr("HUD 1280×800 · encaixe automatizado · revisão visual pendente")
                            color: page.amberColor
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                            Accessible.name: text
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Label {
                                text: "vkBasalt"
                                color: page.mutedColor
                                Layout.preferredWidth: 112
                            }
                            SteamComboBox {
                                id: vkBasaltPicker
                                model: [
                                    qsTr("Desligado"), qsTr("Nitidez CAS"),
                                    qsTr("Antisserrilhado FXAA"), qsTr("Antisserrilhado SMAA")
                                ]
                                currentIndex: page.vkBasaltIndex
                                enabled: (page.scopeIndex === 1
                                    && page.environmentById("vkbasalt").state === "ready")
                                    || page.vkBasaltIndex !== 0
                                Layout.fillWidth: true
                                Layout.minimumHeight: 48
                                Accessible.name: qsTr("Pós-processamento vkBasalt por jogo")
                                Accessible.description: page.scopeIndex !== 1
                                    ? qsTr("Disponível exclusivamente no escopo por jogo")
                                    : page.environmentById("vkbasalt").state === "ready"
                                        ? qsTr("Camada Vulkan disponível")
                                        : qsTr("Componente ausente; o modo desligado permanece completo")
                                onActivated: {
                                    if (currentIndex === 0
                                            || (page.scopeIndex === 1
                                                && page.environmentById("vkbasalt").state === "ready"))
                                        page.vkBasaltIndex = currentIndex
                                }
                            }
                            Label {
                                text: page.vkBasalt.presets
                                    && page.vkBasalt.presets.length > page.vkBasaltIndex
                                    ? page.vkBasalt.presets[page.vkBasaltIndex].costLabel : ""
                                color: page.vkBasaltIndex === 0
                                    ? page.greenColor : page.amberColor
                                font.pixelSize: 11
                                wrapMode: Text.WordWrap
                                Layout.preferredWidth: 120
                            }
                        }
                        Button {
                            visible: profileLastOperationId.length > 0
                            text: qsTr("Desfazer último perfil")
                            Layout.minimumHeight: minimumTouchTarget
                            Layout.alignment: Qt.AlignRight
                            Accessible.name: text
                            onClicked: profileRollbackRequested(profileLastOperationId)
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Label { text: qsTr("Upscaling"); color: page.mutedColor; Layout.preferredWidth: 112 }
                            SteamComboBox {
                                model: [qsTr("Nativo"), qsTr("FSR 2 · Qualidade"), qsTr("FSR 2 · Balanceado"), qsTr("Gamescope FSR")]
                                currentIndex: page.upscalingIndex
                                Layout.fillWidth: true
                                Layout.minimumHeight: 48
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
                            SteamComboBox {
                                id: frameGenerationPicker
                                model: [qsTr("Desligado"), "LSFG 2×", "LSFG 3×", "LSFG 4×"]
                                currentIndex: page.frameGenerationIndex
                                Layout.fillWidth: true
                                Layout.minimumHeight: 48
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
                            Layout.minimumHeight: 48
                            Accessible.name: text
                        }
                    }
                }

                Rectangle {
                    visible: !page.compactLayout
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
                        SteamComboBox {
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

            Rectangle {
                visible: page.workspaceIndex === 2
                Layout.fillWidth: true
                Layout.leftMargin: 20
                Layout.rightMargin: 20
                Layout.minimumHeight: 78
                color: page.sessionManager.state === "ready" ? "#0c2a21" : "#24180b"
                border.color: page.sessionManager.state === "ready" ? page.greenColor : page.amberColor
                radius: 8
                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 14
                    ToolButton { enabled: false; icon.name: "system-switch-user"; icon.color: page.greenColor; background: Item {} }
                    ColumnLayout {
                        Layout.fillWidth: true
                        Label { text: qsTr("SteamZero Game Mode"); color: page.textColor; font.pixelSize: 17; font.bold: true }
                        Label {
                            text: page.sessionManager.state === "ready"
                                ? qsTr("Sessão independente pronta no SDDM, com fallback automático para o Desktop.")
                                : qsTr("Steam, Gamescope ou fallback Plasma ainda não está disponível.")
                            color: page.mutedColor
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                    }
                    Label {
                        text: page.sessionManager.statusLabel || qsTr("Verificando")
                        color: page.sessionManager.state === "ready" ? page.greenColor : page.amberColor
                        font.bold: true
                    }
                    Label {
                        text: page.sessionManager.directBoot
                            && page.sessionManager.directBoot.configured
                            ? qsTr("Boot direto: ativo") : qsTr("Boot direto: disponível")
                        color: page.sessionManager.directBoot
                            && page.sessionManager.directBoot.configured
                            ? page.greenColor : page.amberColor
                        font.bold: true
                    }
                }
            }

            RowLayout {
                visible: page.workspaceIndex === 2
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.leftMargin: 20
                Layout.rightMargin: 20
                Layout.bottomMargin: 20
                spacing: 14

                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumHeight: 360
                    color: page.surfaceColor
                    border.color: page.borderColor
                    radius: 9
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 18
                        spacing: 12
                        RowLayout {
                            Layout.fillWidth: true
                            ToolButton { enabled: false; icon.name: "edit-clear-all"; icon.color: page.cyanColor; background: Item {} }
                            ColumnLayout {
                                Layout.fillWidth: true
                                Label { text: qsTr("Limpeza e manutenção"); color: page.textColor; font.pixelSize: 19; font.bold: true }
                                Label { text: qsTr("Somente caches regeneráveis do jogo selecionado"); color: page.mutedColor }
                            }
                            Label {
                                text: page.formatBytes(page.maintenance.totalBytes)
                                color: page.maintenance.totalBytes > 0 ? page.cyanColor : page.greenColor
                                font.pixelSize: 20
                                font.bold: true
                            }
                        }
                        Rectangle { color: page.borderColor; Layout.fillWidth: true; Layout.preferredHeight: 1 }
                        Repeater {
                            model: page.maintenance.categories || []
                            delegate: RowLayout {
                                required property var modelData
                                Layout.fillWidth: true
                                Layout.minimumHeight: 48
                                CheckBox {
                                    checked: page.selectedMaintenanceCategories.indexOf(modelData.id) >= 0
                                    enabled: modelData.sizeBytes > 0
                                    Accessible.name: modelData.id
                                    onToggled: {
                                        var selected = page.selectedMaintenanceCategories.slice()
                                        var index = selected.indexOf(modelData.id)
                                        if (checked && index < 0)
                                            selected.push(modelData.id)
                                        else if (!checked && index >= 0)
                                            selected.splice(index, 1)
                                        page.selectedMaintenanceCategories = selected
                                    }
                                }
                                Label {
                                    text: modelData.id === "shader-cache" ? qsTr("Shader cache") : qsTr("Crash dumps")
                                    color: page.textColor
                                    Layout.fillWidth: true
                                }
                                Label { text: page.formatBytes(modelData.sizeBytes); color: page.mutedColor }
                            }
                        }
                        Label {
                            text: qsTr("Protegidos: compatdata, saves, conteúdo dos jogos, Workshop e downloads.")
                            color: page.greenColor
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                        Item { Layout.fillHeight: true }
                        Button {
                            visible: Boolean(page.maintenance.recoveryRequired)
                            text: qsTr("Concluir limpeza interrompida")
                            icon.name: "view-refresh"
                            Layout.fillWidth: true
                            Layout.minimumHeight: 48
                            Accessible.name: text
                            onClicked: page.maintenanceRecoveryRequested()
                        }
                        Button {
                            id: maintenanceReviewButton
                            text: page.maintenance.steamRunning ? qsTr("Feche a Steam") : qsTr("Revisar limpeza")
                            enabled: !page.maintenance.steamRunning
                                && page.selectedMaintenanceBytes() > 0
                                && Boolean(page.selectedGame.id)
                            Layout.fillWidth: true
                            Layout.minimumHeight: 50
                            Accessible.name: text
                            onClicked: page.maintenancePlanRequested(
                                String(page.selectedGame.id), page.selectedMaintenanceCategories
                            )
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumHeight: 360
                    color: page.surfaceColor
                    border.color: page.borderColor
                    radius: 9
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 18
                        spacing: 12
                        RowLayout {
                            Layout.fillWidth: true
                            ToolButton { enabled: false; icon.name: "image-x-generic"; icon.color: page.cyanColor; background: Item {} }
                            ColumnLayout {
                                Layout.fillWidth: true
                                Label { text: qsTr("Pacote de mídia"); color: page.textColor; font.pixelSize: 19; font.bold: true }
                                Label { text: qsTr("Grade, retrato, hero e logo locais"); color: page.mutedColor }
                            }
                            Label { text: "G-FULL"; color: page.greenColor; font.bold: true }
                        }
                        Rectangle { color: page.borderColor; Layout.fillWidth: true; Layout.preferredHeight: 1 }
                        Label { text: qsTr("Conta Steam"); color: page.mutedColor }
                        SteamComboBox {
                            id: mediaAccountPicker
                            model: page.media.accounts || []
                            textRole: "label"
                            enabled: count > 0
                            Layout.fillWidth: true
                            Layout.minimumHeight: 48
                            Accessible.name: qsTr("Selecionar conta Steam para a mídia")
                        }
                        Label { text: qsTr("Pasta do pacote"); color: page.mutedColor }
                        RowLayout {
                            Layout.fillWidth: true
                            TextField {
                                text: page.mediaPackagePath || qsTr("Nenhuma pasta selecionada")
                                readOnly: true
                                inputMethodHints: Qt.ImhNone
                                onActiveFocusChanged: { if (activeFocus && page.touchMode) Qt.inputMethod.show() }
                                color: page.mediaPackagePath ? page.textColor : page.mutedColor
                                Layout.fillWidth: true
                                Layout.minimumHeight: 48
                                Accessible.name: qsTr("Caminho do pacote local")
                            }
                            Button {
                                text: qsTr("Escolher")
                                icon.name: "folder-open"
                                Layout.minimumHeight: 48
                                Accessible.name: qsTr("Escolher pasta do pacote de mídia")
                                onClicked: mediaFolderDialog.open()
                            }
                        }
                        Label {
                            text: qsTr("Arquivos aceitos: grid, portrait, hero e logo em PNG, JPG ou WebP. Fonte somente local.")
                            color: page.mutedColor
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                        Item { Layout.fillHeight: true }
                        Button {
                            visible: Boolean(page.mediaLastOperationId)
                            text: qsTr("Restaurar mídia anterior")
                            Layout.fillWidth: true
                            Layout.minimumHeight: 48
                            Accessible.name: text
                            onClicked: page.mediaRollbackRequested(page.mediaLastOperationId)
                        }
                        Button {
                            text: page.media.steamRunning ? qsTr("Feche a Steam") : qsTr("Revisar pacote")
                            enabled: !page.media.steamRunning
                                && page.mediaPackagePath.length > 0
                                && mediaAccountPicker.count > 0
                                && Boolean(page.selectedGame.id)
                            Layout.fillWidth: true
                            Layout.minimumHeight: 50
                            Accessible.name: text
                            onClicked: page.mediaPlanRequested(
                                String(page.selectedGame.id),
                                String(page.media.accounts[mediaAccountPicker.currentIndex].id),
                                page.mediaPackagePath
                            )
                        }
                    }
                }
            }

            SteamDesktop {
                id: desktopModePanel
                visible: page.workspaceIndex === 3
                desktopStatus: page.desktopStatus
                sessionManager: page.sessionManager
                hostPreparation: page.gameplay && page.gameplay.hostPreparation
                    ? page.gameplay.hostPreparation
                    : ({"state": "attention", "hardwareLab": {"reason": ""}})
                backgroundColor: page.backgroundColor
                surfaceColor: page.surfaceColor
                raisedColor: page.raisedColor
                borderColor: page.borderColor
                textColor: page.textColor
                mutedColor: page.mutedColor
                cyanColor: page.cyanColor
                cyanDarkColor: page.cyanDarkColor
                greenColor: page.greenColor
                amberColor: page.amberColor
                redColor: page.redColor
                Layout.fillWidth: true
                Layout.fillHeight: true
                onProfilePlanRequested: function(profile) {
                    page.desktopProfilePlanRequested(profile)
                }
                onProfileApplyRequested: function(planId, confirmToken) {
                    page.desktopProfileApplyRequested(planId, confirmToken)
                }
                onSafeResetRequested: page.desktopSafeResetRequested()
                onConflictRequested: page.desktopConflictRequested()
                onRecoveryRequested: page.desktopRecoveryRequested()
                onKeyboardRequested: function(language) { page.desktopKeyboardRequested(language) }
                onSystemRequested: page.systemRequested()
                onAshytermRequested: page.desktopAshytermRequested()
                onPanelAutoHideRequested: function(enable) { page.desktopPanelAutoHideRequested(enable) }
                onKeyboardSoundRequested: function(enable) { page.desktopKeyboardSoundRequested(enable) }
                onKeyboardThemeRequested: function(dark) { page.desktopKeyboardThemeRequested(dark) }
                onGamemodeReturnRequested: page.desktopGamemodeReturnRequested()
            }

        }
    }

    Rectangle {
        id: fixedActions
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        visible: page.workspaceIndex < 2
        height: visible ? (page.compactLayout ? 62 : 78) : 0
        color: page.backgroundColor
        border.color: page.borderColor
        z: 3
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: page.responsiveGutter
            anchors.rightMargin: page.responsiveGutter
            anchors.topMargin: page.compactLayout ? 7 : 10
            anchors.bottomMargin: page.compactLayout ? 7 : 14
            spacing: page.compactLayout ? 8 : 12
            Button {
                text: qsTr("Restaurar perfil seguro")
                Layout.fillWidth: true
                Layout.minimumHeight: page.compactLayout ? page.minimumTouchTarget : 54
                Accessible.name: text
                onClicked: page.planRequested(page.safePayload())
            }
            Button {
                id: reviewApplyButton
                text: qsTr("Revisar e aplicar perfil")
                enabled: page.games.length > 0
                Layout.fillWidth: true
                Layout.minimumHeight: page.compactLayout ? page.minimumTouchTarget : 54
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
