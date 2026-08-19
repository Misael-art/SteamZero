// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Consumidor de contêineres já resolvidos. Geometria, scrim e z-index chegam
// prontos: este componente não calcula âncora, não decide o que bloqueia
// entrada e não escolhe onde o erro crítico entra na pilha.
import QtQuick

Item {
    id: containerPreview

    required property var containers

    readonly property var declared: containers && containers.containers
        ? containers.containers : ({})
    readonly property int criticalErrorZ: containers && containers.criticalErrorZ !== undefined
        ? Number(containers.criticalErrorZ) : 0

    function containerAt(name) {
        return declared[name] !== undefined ? declared[name] : null
    }

    readonly property var modal: containerAt("previewModal")
    readonly property real scrimOpacity: modal ? Number(modal.scrim) : 0
    readonly property bool modalBlocksInput: modal ? modal.blocksInput === true : false
    // O modal nunca pode cobrir o erro crítico: a comparação é sobre valores
    // materializados, não sobre uma regra reimplementada aqui.
    readonly property bool criticalStaysOnTop: modal
        ? Number(modal.z) < criticalErrorZ : true

    Repeater {
        model: Object.keys(containerPreview.declared)

        delegate: Item {
            required property string modelData
            readonly property var box: containerPreview.declared[modelData]

            x: box.x
            y: box.y
            width: box.width
            height: box.height
            z: box.z

            Rectangle {
                id: scrim
                objectName: modelData + "Scrim"
                visible: box.scrim > 0
                parent: containerPreview
                anchors.fill: parent
                color: "#000000"
                opacity: box.scrim
                z: box.scrimZ
            }

            Rectangle {
                objectName: modelData
                anchors.fill: parent
                radius: box.radius
                color: "#132833"
                border.width: box.elevation
                border.color: "#22d3ee"
            }
        }
    }
}
