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
    readonly property string selectedPath: selectedNode && selectedNode.path !== undefined
        ? String(selectedNode.path) : selectedLabel
    readonly property int nodeCount: nodes.length
    readonly property int selectedConstraintCount:
        selectedNode && selectedNode.constraints ? selectedNode.constraints.length : 0
    readonly property string selectedConstraintCode:
        selectedConstraintCount ? String(selectedNode.constraints[0].code) : ""
    readonly property var selectedSteps: {
        if (!selectedNode || selectedKind !== "timeline" || !selectedNode.children)
            return []
        const ids = selectedNode.children
        const steps = []
        for (let i = 0; i < ids.length; ++i) {
            for (let j = 0; j < nodes.length; ++j) {
                if (nodes[j].id === ids[i])
                    steps.push(nodes[j])
            }
        }
        return steps
    }
    readonly property int selectedTimelineDuration: {
        if (selectedKind !== "timeline" || !selectedNode || !selectedNode.properties)
            return 0
        const value = Number(selectedNode.properties.totalDuration)
        return value === value ? value : 0
    }
    readonly property var budget: graph && graph.budget ? graph.budget : ({})
    readonly property int declaredCost: Number(budget.declaredCost) || 0
    readonly property bool withinBudget: budget.withinBudget !== false
    readonly property bool budgetMeasured: budget.measured === true
    readonly property string selectedBindingPath: {
        if (selectedKind !== "binding" || !selectedNode || !selectedNode.properties)
            return ""
        return String(selectedNode.properties.path || "")
    }

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
            // A indentação vem de `depth`, resolvido no domínio. O QML não
            // percorre `parent`/`children` nem deduz hierarquia: se desenhasse
            // a própria árvore, ela poderia divergir da que a engine validou.
            delegate: ItemDelegate {
                required property var modelData
                readonly property int depth: modelData.depth !== undefined
                    ? Number(modelData.depth) : 0
                width: tree.width
                leftPadding: 8 + depth * 14
                text: modelData.label
                highlighted: modelData.id === studio.selectedId
                // Rótulos repetidos entre irmãos só se distinguem pelo caminho.
                ToolTip.visible: hovered && modelData.path !== undefined
                ToolTip.text: modelData.path !== undefined ? modelData.path : modelData.label
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
            Row {
                id: timelineStrip
                objectName: "studioTimeline"
                visible: studio.selectedKind === "timeline" && studio.selectedSteps.length > 0
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.margins: 12
                spacing: 4
                Repeater {
                    model: studio.selectedSteps
                    delegate: Rectangle {
                        required property var modelData
                        width: Math.max(28, Number(modelData.properties.duration) * 0.4)
                        height: 22
                        radius: 4
                        color: "#1c2440"
                        border.color: "#262f4d"
                        Text {
                            anchors.centerIn: parent
                            color: "#e8ecf7"
                            font.pixelSize: 10
                            text: String(modelData.properties.state)
                        }
                    }
                }
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
            // Onde o nó está na cena. Sem isto, dois irmãos de mesmo rótulo
            // ficam indistinguíveis depois de selecionados.
            Text {
                objectName: "studioSelectedPath"
                width: inspector.width
                wrapMode: Text.Wrap
                text: studio.selectedPath
                color: "#5f6b85"
                font.pixelSize: 10
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
            Repeater {
                model: studio.selectedNode && studio.selectedNode.constraints
                    ? studio.selectedNode.constraints : []
                delegate: Text {
                    required property var modelData
                    objectName: "studioConstraint"
                    width: inspector.width
                    wrapMode: Text.Wrap
                    color: "#ffc400"
                    font.pixelSize: 12
                    text: modelData.code + ": " + modelData.reason
                }
            }
            Column {
                id: profiler
                objectName: "studioProfiler"
                width: inspector.width
                spacing: 2
                Text {
                    color: "#8b93a8"
                    font.pixelSize: 11
                    text: qsTr("Profiler declarado")
                }
                Text {
                    color: "#e8ecf7"
                    font.pixelSize: 12
                    text: qsTr("custo %1").arg(studio.declaredCost)
                }
                Text {
                    color: studio.withinBudget ? "#59d35d" : "#ffc400"
                    font.pixelSize: 12
                    text: studio.withinBudget ? qsTr("dentro do orçamento") : qsTr("orçamento excedido")
                }
                Text {
                    visible: !studio.budgetMeasured
                    color: "#8b93a8"
                    font.pixelSize: 11
                    text: qsTr("sem medição física")
                }
            }
        }
    }
}
