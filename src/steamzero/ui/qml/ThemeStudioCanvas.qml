// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Canvas, árvore e inspector do Theme Studio. Consome somente o grafo já
// materializado pela Theme Engine; não executa QML do pacote.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: studio

    required property var graph
    property string selectedId: graph && graph.selectedId ? graph.selectedId : "scene"

    readonly property var nodes: graph && graph.nodes ? graph.nodes : []
    readonly property var selectedNode: {
        for (let i = 0; i < nodes.length; ++i) {
            if (nodes[i].id === studio.selectedId)
                return nodes[i]
        }
        return nodes.length ? nodes[0] : null
    }
    readonly property string selectedKind: selectedNode ? selectedNode.kind : ""
    readonly property string selectedLabel: selectedNode ? selectedNode.label : ""
    readonly property int nodeCount: nodes.length

    function select(nodeId) {
        for (let i = 0; i < nodes.length; ++i) {
            if (nodes[i].id === nodeId) {
                studio.selectedId = nodeId
                return true
            }
        }
        return false
    }

    RowLayout {
        anchors.fill: parent
        spacing: 8

        ListView {
            id: tree
            objectName: "studioTree"
            Layout.preferredWidth: 160
            Layout.fillHeight: true
            clip: true
            model: studio.nodes
            delegate: ItemDelegate {
                required property var modelData
                width: tree.width
                text: modelData.label
                highlighted: modelData.id === studio.selectedId
                onClicked: studio.select(modelData.id)
            }
        }

        Rectangle {
            id: canvas
            objectName: "studioCanvas"
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: "#0b1020"
            radius: 8
            border.color: "#262f4d"
            Text {
                anchors.centerIn: parent
                color: "#e8ecf7"
                text: studio.selectedLabel
                font.pixelSize: 16
            }
        }

        Column {
            id: inspector
            objectName: "studioInspector"
            Layout.preferredWidth: 180
            Layout.fillHeight: true
            spacing: 4
            Text {
                text: studio.selectedKind
                color: "#8b93a8"
                font.pixelSize: 11
            }
            Repeater {
                model: studio.selectedNode && studio.selectedNode.properties
                    ? Object.keys(studio.selectedNode.properties) : []
                delegate: Text {
                    required property string modelData
                    width: inspector.width
                    wrapMode: Text.Wrap
                    color: "#e8ecf7"
                    font.pixelSize: 12
                    text: modelData + ": " + studio.selectedNode.properties[modelData]
                }
            }
        }
    }
}
