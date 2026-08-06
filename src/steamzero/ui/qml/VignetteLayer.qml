// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Vinheta procedural em quatro gradientes. A cor e a intensidade vêm da pilha
// allowlisted resolvida; não há textura adicional nem shader fornecido por tema.
import QtQuick

Item {
    id: root

    property color tint: "#000000"
    property real strength: 0

    visible: strength > 0
    readonly property real boundedStrength: Math.max(0, Math.min(1, strength))
    readonly property color transparentTint: Qt.rgba(tint.r, tint.g, tint.b, 0)

    Rectangle {
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: parent.width * 0.30
        opacity: root.boundedStrength
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: root.tint }
            GradientStop { position: 1; color: root.transparentTint }
        }
    }
    Rectangle {
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: parent.width * 0.30
        opacity: root.boundedStrength
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: root.transparentTint }
            GradientStop { position: 1; color: root.tint }
        }
    }
    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: parent.height * 0.30
        opacity: root.boundedStrength
        gradient: Gradient {
            GradientStop { position: 0; color: root.tint }
            GradientStop { position: 1; color: root.transparentTint }
        }
    }
    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: parent.height * 0.30
        opacity: root.boundedStrength
        gradient: Gradient {
            GradientStop { position: 0; color: root.transparentTint }
            GradientStop { position: 1; color: root.tint }
        }
    }
}
