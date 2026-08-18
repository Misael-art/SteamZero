// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Consumidor QML de um painel de vidro já negociado. O tema não fornece
// shader, backbuffer nem região de captura; o fallback sem blur permanece
// visível com tint, borda e highlight estáticos.
import QtQuick
import QtQuick.Effects

Item {
    id: glassPanel

    required property var panel
    property Item backdrop: null

    readonly property bool blurEnabled: !!(panel && panel.blurEnabled)
    readonly property string tint: panel && panel.tint ? panel.tint : "#132833"
    readonly property real tintOpacity: panel && panel.tintOpacity !== undefined ? panel.tintOpacity : 0.4
    readonly property color borderColor: panel && panel.borderColor ? panel.borderColor : "#ffffff"
    readonly property real borderOpacity: panel && panel.borderOpacity !== undefined ? panel.borderOpacity : 0.28
    readonly property real highlightOpacity: panel && panel.highlightOpacity !== undefined ? panel.highlightOpacity : 0.16
    readonly property string fallback: panel && panel.fallback ? panel.fallback : "flat"

    ShaderEffectSource {
        id: capturedBackdrop
        anchors.fill: parent
        sourceItem: glassPanel.backdrop
        visible: false
        live: true
        hideSource: false
    }

    MultiEffect {
        anchors.fill: parent
        source: capturedBackdrop
        visible: glassPanel.blurEnabled && glassPanel.backdrop !== null
        blurEnabled: visible
        blur: glassPanel.panel && glassPanel.panel.blur ? glassPanel.panel.blur / 64.0 : 0
    }

    Rectangle {
        anchors.fill: parent
        radius: 12
        color: glassPanel.tint
        opacity: glassPanel.tintOpacity
        border.width: 1
        border.color: glassPanel.borderColor
    }

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: Math.max(8, parent.height * 0.28)
        radius: 12
        color: Qt.rgba(1, 1, 1, glassPanel.highlightOpacity)
    }
}
