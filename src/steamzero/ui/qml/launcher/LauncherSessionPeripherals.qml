// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Superfície declarativa para periféricos confirmados pelo adapter da sessão.
// Sem discos ou bezel compatível, a ausência continua legível e acionável.

import QtQuick

Item {
    id: surface

    property var model: null
    property var accessibility: ({"highContrast": false, "visualScale": 1.0,
        "reducedMotion": false})
    property int selectedIndex: 0
    readonly property var discs: model && Array.isArray(model.discs) ? model.discs : []
    readonly property var bezels: model && Array.isArray(model.bezels) ? model.bezels : []
    readonly property var fade: model && model.fade ? model.fade : ({"phase": "idle",
        "progress": 0.0, "durationMs": 180, "reducedMotion": false})
    readonly property bool highContrast: !!(accessibility && accessibility.highContrast)
    readonly property bool reducedMotion: !!(accessibility && accessibility.reducedMotion)
    readonly property real visualScale: accessibility && Number(accessibility.visualScale) > 0
        ? Number(accessibility.visualScale) : 1.0
    readonly property var selectedDisc: selectedIndex >= 0 && selectedIndex < discs.length
        ? discs[selectedIndex] : null

    signal discRequested(string discId)
    signal closeRequested()

    function setModel(value) {
        surface.model = value
        surface.selectedIndex = 0
    }

    function openSurface() {
        surface.visible = true
        surface.selectedIndex = 0
        surface.forceActiveFocus()
    }

    function closeSurface() {
        if (!surface.visible)
            return false
        surface.visible = false
        surface.closeRequested()
        return true
    }

    function move(direction) {
        if (discs.length === 0)
            return false
        const step = direction === "left" || direction === "up" ? -1 : 1
        surface.selectedIndex = (surface.selectedIndex + step + discs.length) % discs.length
        return true
    }

    function activateFocused() {
        if (selectedDisc === null || selectedDisc.available !== true
                || selectedDisc.compatible !== true)
            return false
        surface.discRequested(String(selectedDisc.id || ""))
        return true
    }

    function _text(value, fallback) {
        return typeof value === "string" && value.length > 0 ? value : fallback
    }

    visible: false
    focus: visible
    z: 55

    Rectangle {
        anchors.fill: parent
        color: surface.highContrast ? "#000000" : "#071019f5"
    }

    Rectangle {
        anchors.centerIn: parent
        width: Math.min(parent.width - 64, 1080)
        height: Math.min(parent.height - 64, 580)
        radius: 18
        color: surface.highContrast ? "#000000" : "#101c2bfa"
        border.width: surface.highContrast ? 3 : 1
        border.color: surface.highContrast ? "#ffffff" : "#2b4963"

        Column {
            anchors.fill: parent
            anchors.margins: 28
            spacing: 16

            Row {
                width: parent.width
                spacing: 16
                Text {
                    width: parent.width - closeButton.width - 16
                    text: qsTr("MÍDIA DA SESSÃO · TROCAR DISCO")
                    color: surface.highContrast ? "#ffffff" : "#7dd3fc"
                    font.pixelSize: 18 * surface.visualScale
                    font.bold: true
                    elide: Text.ElideRight
                }
                Rectangle {
                    id: closeButton
                    width: 116
                    height: 44
                    radius: 8
                    color: surface.highContrast ? "#000000" : "#17283a"
                    border.width: activeFocus ? 3 : 1
                    border.color: activeFocus ? "#7dd3fc" : "#68839b"
                    Text {
                        anchors.centerIn: parent
                        text: qsTr("Fechar")
                        color: "#f8fafc"
                        font.pixelSize: 14 * surface.visualScale
                    }
                    TapHandler { onTapped: surface.closeSurface() }
                }
            }

            Text {
                width: parent.width
                text: discs.length > 1
                    ? qsTr("%1 discos declarados · o disco inserido está destacado").arg(discs.length)
                    : _text(surface.model ? surface.model.reason : "",
                            qsTr("Este jogo não declara um conjunto multi-disc."))
                color: discs.length > 1 ? "#cbd5e1" : "#fbbf24"
                font.pixelSize: 14 * surface.visualScale
                wrapMode: Text.Wrap
            }

            ListView {
                id: discList
                width: parent.width
                height: 300
                orientation: ListView.Horizontal
                spacing: 14
                clip: true
                model: surface.discs
                delegate: Rectangle {
                    required property var modelData
                    required property int index
                    width: 220
                    height: 270
                    radius: 12
                    color: modelData.available === true && modelData.compatible === true
                        ? (index === surface.selectedIndex ? "#164e63" : "#17283a")
                        : "#111b27"
                    opacity: modelData.available === true && modelData.compatible === true ? 1 : 0.62
                    border.width: index === surface.selectedIndex ? 3 : 1
                    border.color: index === surface.selectedIndex ? "#67e8f9" : "#2b4963"
                    Accessible.name: String(modelData.label || qsTr("Disco %1").arg(index + 1))
                    Accessible.role: Accessible.Button
                    Accessible.description: modelData.inserted === true
                        ? qsTr("Disco inserido") : String(modelData.reason || qsTr("Disco disponível"))
                    Column {
                        anchors.fill: parent
                        anchors.margins: 18
                        spacing: 12
                        Text {
                            text: modelData.inserted === true ? qsTr("INSERIDO") : qsTr("DISCO %1").arg(index + 1)
                            color: modelData.inserted === true ? "#67e8f9" : "#a8b8ca"
                            font.pixelSize: 12 * surface.visualScale
                            font.bold: true
                        }
                        Text {
                            width: parent.width
                            text: String(modelData.label || qsTr("Mídia sem nome"))
                            color: "#f8fafc"
                            font.pixelSize: 17 * surface.visualScale
                            font.bold: true
                            wrapMode: Text.Wrap
                            elide: Text.ElideRight
                        }
                        Item { width: 1; height: 34 }
                        Text {
                            width: parent.width
                            text: modelData.available === true && modelData.compatible === true
                                ? qsTr("Enter para inserir")
                                : String(modelData.reason || qsTr("Indisponível"))
                            color: modelData.available === true && modelData.compatible === true
                                ? "#cbd5e1" : "#fbbf24"
                            font.pixelSize: 13 * surface.visualScale
                            wrapMode: Text.Wrap
                        }
                    }
                    TapHandler {
                        onTapped: {
                            surface.selectedIndex = index
                            surface.activateFocused()
                        }
                    }
                }
            }

            Text {
                width: parent.width
                text: bezels.length > 0
                    ? qsTr("Molduras declaradas: %1 · aplicadas somente quando o adapter confirmar compatibilidade.").arg(bezels.length)
                    : qsTr("Moldura: fallback proporcional sem asset confirmado")
                color: "#a8b8ca"
                font.pixelSize: 12 * surface.visualScale
                wrapMode: Text.Wrap
            }
            Text {
                width: parent.width
                text: qsTr("← → Navegar   Enter Inserir   Esc Fechar")
                color: surface.highContrast ? "#ffffff" : "#a8b8ca"
                font.pixelSize: 13 * surface.visualScale
                horizontalAlignment: Text.AlignHCenter
            }
        }
    }

    // O fade é derivado de um evento do read model; reducedMotion elimina a
    // animação sem esconder o estado do usuário.
    Rectangle {
        anchors.fill: parent
        z: 2
        color: "#000000"
        visible: String(surface.fade.phase || "idle") !== "idle"
        opacity: surface.reducedMotion || surface.fade.reducedMotion === true
            ? (String(surface.fade.phase || "") === "out" ? 1 : 0)
            : Number(surface.fade.progress || 0)
        Behavior on opacity {
            NumberAnimation {
                duration: surface.reducedMotion ? 0 : Math.min(1000, Number(surface.fade.durationMs || 180))
            }
        }
    }

    Keys.onEscapePressed: surface.closeSurface()
    Keys.onLeftPressed: surface.move("left")
    Keys.onRightPressed: surface.move("right")
    Keys.onUpPressed: surface.move("left")
    Keys.onDownPressed: surface.move("right")
    Keys.onReturnPressed: surface.activateFocused()
    Keys.onEnterPressed: surface.activateFocused()
    Keys.onSpacePressed: surface.activateFocused()
}
