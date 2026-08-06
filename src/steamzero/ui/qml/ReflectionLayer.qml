// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Reflexo confiável: reutiliza a textura já decodificada pelo MediaEffectLayer.
// Não recebe path, shader ou código do tema.
import QtQuick
import QtQuick.Effects

Item {
    id: root

    required property Item sourceItem
    property real reflectionOpacity: 0
    property real reflectionScale: 0.35
    property real maskStart: 0.72
    property real maskEnd: 0

    visible: reflectionOpacity > 0 && reflectionScale > 0 && sourceItem !== null
    clip: true

    readonly property real boundedScale: Math.max(0.05, Math.min(1, reflectionScale))

    Item {
        id: reflectedArea
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: parent.height * root.boundedScale
        clip: true

        Item {
            id: alphaMask
            anchors.fill: parent
            // A ShaderEffectSource esconde o item na cena principal; deixá-lo
            // renderizável evita uma máscara transparente em alguns backends.
            visible: true
            Rectangle {
                anchors.fill: parent
                gradient: Gradient {
                    GradientStop {
                        position: 0
                        color: Qt.rgba(1, 1, 1, root.maskStart)
                    }
                    GradientStop {
                        position: 1
                        color: Qt.rgba(1, 1, 1, root.maskEnd)
                    }
                }
            }
        }

        MultiEffect {
            anchors.fill: parent
            source: root.sourceItem
            opacity: root.reflectionOpacity
            maskEnabled: true
            maskSource: ShaderEffectSource {
                sourceItem: alphaMask
                hideSource: true
            }
            transform: Scale {
                origin.x: width / 2
                origin.y: height / 2
                yScale: -1
            }
        }
    }
}
