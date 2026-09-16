// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Superfície visual do OSD de sessão. O componente não executa operações nem
// interpreta capabilities: só desenha o read model allowlisted e encaminha a
// ação semântica escolhida para a ponte.

import QtQuick

Item {
    id: overlay

    property var overlayModel: null
    property var accessibility: ({"highContrast": false, "visualScale": 1.0,
        "reducedMotion": false})
    property string gameTitle: ""
    property string bridgeError: ""
    property string localError: ""
    property bool overlayOpen: false
    property bool saveGalleryOpen: false
    property bool peripheralOpen: false
    property bool requestPending: false
    property int selectedIndex: _initialIndex()
    readonly property var actions: overlayModel && Array.isArray(overlayModel.actions)
        ? overlayModel.actions : []
    readonly property var saveStates: overlayModel && overlayModel.saveStates
        ? overlayModel.saveStates : null
    readonly property var peripherals: overlayModel && overlayModel.peripherals
        ? overlayModel.peripherals : null
    readonly property var criticalError: overlayModel
        ? overlayModel.criticalError : null
    readonly property bool highContrast: !!(accessibility && accessibility.highContrast)
    readonly property bool reducedMotion: !!(accessibility && accessibility.reducedMotion)
    readonly property real visualScale: accessibility && Number(accessibility.visualScale) > 0
        ? Number(accessibility.visualScale) : 1.0
    readonly property string currentActionId: selectedIndex >= 0 && selectedIndex < actions.length
        ? String(actions[selectedIndex].id || "") : ""

    signal actionRequested(string actionId)
    signal saveStateRequested(string actionId, int slot)
    signal discRequested(string discId)
    signal closeRequested()

    function _initialIndex() {
        if (!overlayModel || !Array.isArray(overlayModel.actions))
            return 0
        const requested = String(overlayModel.focusedAction || "")
        for (let i = 0; i < overlayModel.actions.length; ++i)
            if (String(overlayModel.actions[i].id || "") === requested)
                return i
        return 0
    }

    function setModel(value) {
        overlay.overlayModel = value
        overlay.selectedIndex = _initialIndex()
        if (overlay.saveGalleryOpen)
            saveGallery.setModel(overlay.saveStates)
        if (overlay.peripheralOpen)
            peripheralSurface.setModel(overlay.peripherals)
        overlay.localError = ""
    }

    function openOverlay(value) {
        if (value !== undefined)
            setModel(value)
        overlay.overlayOpen = true
        overlay.saveGalleryOpen = false
        overlay.peripheralOpen = false
        saveGallery.visible = false
        peripheralSurface.visible = false
        overlay.forceActiveFocus()
    }

    function closeOverlay() {
        if (!overlay.overlayOpen)
            return false
        overlay.overlayOpen = false
        overlay.saveGalleryOpen = false
        overlay.peripheralOpen = false
        saveGallery.visible = false
        peripheralSurface.visible = false
        overlay.localError = ""
        overlay.closeRequested()
        return true
    }

    function focusAction(actionId) {
        for (let i = 0; i < actions.length; ++i) {
            if (String(actions[i].id || "") !== String(actionId))
                continue
            overlay.selectedIndex = i
            return true
        }
        return false
    }

    function move(direction) {
        if (actions.length === 0)
            return false
        let step = (direction === "left" || direction === "up") ? -1 : 1
        let next = overlay.selectedIndex
        for (let count = 0; count < actions.length; ++count) {
            next = (next + step + actions.length) % actions.length
            if (actions[next] !== undefined) {
                overlay.selectedIndex = next
                return true
            }
        }
        return false
    }

    function activateFocused() {
        if (requestPending || selectedIndex < 0 || selectedIndex >= actions.length)
            return false
        const action = actions[selectedIndex]
        if (!action || action.enabled !== true) {
            overlay.localError = action && action.reason
                ? String(action.reason)
                : qsTr("Esta ação está indisponível nesta sessão.")
            return false
        }
        if ((String(action.id) === "saveState" || String(action.id) === "loadState")
                && overlay.saveStates
                && (overlay.saveStates.saveAvailable === true
                    || overlay.saveStates.loadAvailable === true)) {
            overlay.saveGalleryOpen = true
            saveGallery.setModel(overlay.saveStates)
            saveGallery.openGallery(String(action.id))
            return true
        }
        if (String(action.id) === "disc" && overlay.peripherals
                && overlay.peripherals.available === true) {
            overlay.peripheralOpen = true
            peripheralSurface.setModel(overlay.peripherals)
            peripheralSurface.openSurface()
            return true
        }
        overlay.localError = ""
        overlay.actionRequested(String(action.id))
        return true
    }

    function closeSaveGallery() {
        if (!overlay.saveGalleryOpen)
            return false
        overlay.saveGalleryOpen = false
        saveGallery.visible = false
        overlay.forceActiveFocus()
        return true
    }

    function closePeripheralSurface() {
        if (!overlay.peripheralOpen)
            return false
        overlay.peripheralOpen = false
        peripheralSurface.visible = false
        overlay.forceActiveFocus()
        return true
    }

    function _text(value, fallback) {
        return typeof value === "string" && value.length > 0 ? value : fallback
    }

    visible: overlay.overlayOpen
    focus: overlay.overlayOpen
    z: 30

    Rectangle {
        objectName: "sessionOverlayBackdrop"
        anchors.fill: parent
        color: overlay.highContrast ? "#000000" : "#071019e8"
        opacity: overlay.overlayOpen ? 1 : 0
        visible: overlay.overlayOpen && !overlay.saveGalleryOpen && !overlay.peripheralOpen
        Behavior on opacity {
            NumberAnimation { duration: overlay.reducedMotion ? 0 : 160 }
        }
    }

    Rectangle {
        id: panel
        objectName: "sessionOverlayPanel"
        anchors.centerIn: parent
        width: Math.min(parent.width - 64, 900)
        height: Math.min(parent.height - 64, 650)
        radius: 18
        color: overlay.highContrast ? "#000000" : "#101c2bfa"
        border.width: overlay.highContrast ? 3 : 1
        border.color: overlay.highContrast ? "#ffffff" : "#2b4963"
        visible: overlay.overlayOpen && !overlay.saveGalleryOpen && !overlay.peripheralOpen

        Column {
            anchors.fill: parent
            anchors.margins: 28
            spacing: 18

            Row {
                width: parent.width
                spacing: 18

                Column {
                    width: parent.width - closeButton.width - 18
                    spacing: 4
                    Text {
                        text: qsTr("CONTROLE DA SESSÃO")
                        color: overlay.highContrast ? "#ffffff" : "#7dd3fc"
                        font.pixelSize: 13 * overlay.visualScale
                        font.bold: true
                    }
                    Text {
                        text: overlay.gameTitle !== "" ? overlay.gameTitle
                            : _text(overlay.overlayModel ? overlay.overlayModel.gameId : "",
                                    qsTr("Jogo em execução"))
                        color: "#f8fafc"
                        font.pixelSize: 26 * overlay.visualScale
                        font.bold: true
                        elide: Text.ElideRight
                        width: parent.width
                    }
                }

                Rectangle {
                    id: closeButton
                    width: 116
                    height: 44
                    radius: 8
                    color: overlay.highContrast ? "#000000" : "#17283a"
                    border.width: activeFocus ? 3 : 1
                    border.color: activeFocus ? "#7dd3fc" : "#68839b"
                    Accessible.name: qsTr("Fechar controle da sessão")
                    Accessible.role: Accessible.Button
                    Text {
                        anchors.centerIn: parent
                        text: qsTr("Fechar")
                        color: "#f8fafc"
                        font.pixelSize: 14 * overlay.visualScale
                    }
                    TapHandler { onTapped: overlay.closeOverlay() }
                }
            }

            Row {
                spacing: 12
                Text {
                    text: qsTr("Estado: %1").arg(_text(overlay.overlayModel
                        ? overlay.overlayModel.state : "", qsTr("indisponível")))
                    color: "#cbd5e1"
                    font.pixelSize: 14 * overlay.visualScale
                }
                Text {
                    visible: overlay.requestPending
                    text: qsTr("Atualizando…")
                    color: "#fbbf24"
                    font.pixelSize: 14 * overlay.visualScale
                }
            }

            Grid {
                id: actionGrid
                width: parent.width
                columns: 4
                rowSpacing: 10
                columnSpacing: 10

                Repeater {
                    model: overlay.actions
                    delegate: Rectangle {
                        required property var modelData
                        required property int index
                        width: (actionGrid.width - actionGrid.columnSpacing * 3) / 4
                        height: 58
                        radius: 8
                        color: modelData.enabled === true
                            ? (index === overlay.selectedIndex ? "#164e63" : "#17283a")
                            : (index === overlay.selectedIndex ? "#3b2f20" : "#111b27")
                        opacity: modelData.enabled === true ? 1 : 0.62
                        border.width: index === overlay.selectedIndex ? 3 : 1
                        border.color: index === overlay.selectedIndex
                            ? (modelData.enabled === true ? "#67e8f9" : "#fbbf24")
                            : "#2b4963"
                        Accessible.name: String(modelData.label || modelData.id || "")
                        Accessible.role: Accessible.Button
                        Accessible.description: modelData.enabled === true
                            ? qsTr("Ação disponível")
                            : String(modelData.reason || qsTr("Ação indisponível"))
                        Text {
                            anchors.fill: parent
                            anchors.margins: 8
                            text: String(modelData.label || modelData.id || "")
                            color: modelData.enabled === true ? "#f8fafc" : "#b7c1ce"
                            font.pixelSize: 13 * overlay.visualScale
                            font.bold: index === overlay.selectedIndex
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                            wrapMode: Text.Wrap
                        }
                        TapHandler {
                            onTapped: {
                                overlay.selectedIndex = index
                                overlay.activateFocused()
                            }
                        }
                    }
                }
            }

            Rectangle {
                width: parent.width
                height: Math.max(72, errorText.implicitHeight + 24)
                radius: 8
                visible: overlay.bridgeError !== "" || overlay.localError !== ""
                    || (overlay.overlayModel && overlay.overlayModel.diagnostic)
                    || overlay.criticalError !== null
                color: overlay.highContrast ? "#000000" : "#241a1e"
                border.width: 1
                border.color: "#fb7185"
                Text {
                    id: errorText
                    anchors.fill: parent
                    anchors.margins: 12
                    text: overlay.bridgeError !== "" ? overlay.bridgeError
                        : overlay.localError !== "" ? overlay.localError
                        : overlay.criticalError !== null
                        ? [_text(overlay.criticalError.code, "AURA-OSD-ERROR-004"),
                           _text(overlay.criticalError.message
                                 || overlay.criticalError.detail,
                                 qsTr("A sessão registrou um erro crítico.")),
                           _text(overlay.criticalError.impact, ""),
                           _text(overlay.criticalError.nextAction,
                                 qsTr("Verifique a sessão e tente novamente."))]
                            .filter(function(value) { return value !== "" }).join("\n")
                        : _text(overlay.overlayModel ? overlay.overlayModel.diagnostic : "",
                                qsTr("A sessão ainda não está disponível para controle."))
                    color: "#fecdd3"
                    font.pixelSize: 14 * overlay.visualScale
                    wrapMode: Text.Wrap
                    maximumLineCount: 5
                    elide: Text.ElideRight
                }
            }

            Item { width: 1; height: 1 }

            Text {
                width: parent.width
                text: qsTr("← ↑ ↓ → Navegar   Enter Selecionar   Esc Fechar")
                color: overlay.highContrast ? "#ffffff" : "#a8b8ca"
                font.pixelSize: 13 * overlay.visualScale
                horizontalAlignment: Text.AlignHCenter
            }
        }
    }

    LauncherSaveStateGallery {
        id: saveGallery
        anchors.fill: parent
        model: overlay.saveStates
        accessibility: overlay.accessibility
        onSlotRequested: function(actionId, slot) {
            overlay.saveStateRequested(actionId, slot)
        }
        onCloseRequested: overlay.closeSaveGallery()
    }

    LauncherSessionPeripherals {
        id: peripheralSurface
        anchors.fill: parent
        model: overlay.peripherals
        accessibility: overlay.accessibility
        onDiscRequested: function(discId) {
            overlay.discRequested(discId)
        }
        onCloseRequested: overlay.closePeripheralSurface()
    }

    Keys.onEscapePressed: overlay.saveGalleryOpen ? overlay.closeSaveGallery()
        : overlay.peripheralOpen ? overlay.closePeripheralSurface() : overlay.closeOverlay()
    Keys.onPressed: function(event) {
        if (event.key === Qt.Key_F1 || event.key === Qt.Key_Menu) {
            if (overlay.saveGalleryOpen)
                overlay.closeSaveGallery()
            else if (overlay.peripheralOpen)
                overlay.closePeripheralSurface()
            else
                overlay.closeOverlay()
            event.accepted = true
        }
    }
    Keys.onLeftPressed: overlay.saveGalleryOpen ? saveGallery.move("left")
        : overlay.peripheralOpen ? peripheralSurface.move("left") : overlay.move("left")
    Keys.onRightPressed: overlay.saveGalleryOpen ? saveGallery.move("right")
        : overlay.peripheralOpen ? peripheralSurface.move("right") : overlay.move("right")
    Keys.onUpPressed: overlay.saveGalleryOpen ? saveGallery.move("left")
        : overlay.peripheralOpen ? peripheralSurface.move("left") : overlay.move("up")
    Keys.onDownPressed: overlay.saveGalleryOpen ? saveGallery.move("right")
        : overlay.peripheralOpen ? peripheralSurface.move("right") : overlay.move("down")
    Keys.onReturnPressed: overlay.saveGalleryOpen ? saveGallery.activateFocused()
        : overlay.peripheralOpen ? peripheralSurface.activateFocused() : overlay.activateFocused()
    Keys.onEnterPressed: overlay.saveGalleryOpen ? saveGallery.activateFocused()
        : overlay.peripheralOpen ? peripheralSurface.activateFocused() : overlay.activateFocused()
    Keys.onSpacePressed: overlay.saveGalleryOpen ? saveGallery.activateFocused()
        : overlay.peripheralOpen ? peripheralSurface.activateFocused() : overlay.activateFocused()
}
