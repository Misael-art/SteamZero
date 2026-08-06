// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Resumo factual para áreas operacionais. A linguagem é deliberadamente menos
// dramática que descoberta de jogos, mas mantém foco, contraste e estados.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root

    required property string title
    required property string value
    property string iconName: "dialog-information"
    property string state: "unverified"
    property string detail: ""
    required property color surfaceColor
    required property color raisedColor
    required property color borderColor
    required property color textColor
    required property color mutedColor
    required property color cyanColor
    required property color greenColor
    required property color amberColor
    required property color redColor

    implicitHeight: 104
    Accessible.name: detail === "" ? title + ": " + value : title + ": " + value + ". " + detail

    function stateColor() {
        if (["ready", "healthy", "done", "completed"].indexOf(state) >= 0)
            return greenColor
        if (["attention", "pending", "conflicted", "blocked", "unavailable"].indexOf(state) >= 0)
            return amberColor
        if (["failed", "error"].indexOf(state) >= 0)
            return redColor
        return mutedColor
    }

    function stateLabel() {
        if (["ready", "healthy", "done", "completed"].indexOf(state) >= 0)
            return qsTr("Sem pendências")
        if (state === "conflicted")
            return qsTr("Conflito preservado")
        if (state === "pending")
            return qsTr("Aguardando sincronização")
        if (["failed", "error"].indexOf(state) >= 0)
            return qsTr("Requer revisão")
        return qsTr("Estado não publicado")
    }

    Rectangle {
        anchors.fill: parent
        color: root.surfaceColor
        radius: 14
        border.color: root.stateColor()
        border.width: 1
        RowLayout {
            anchors.fill: parent
            anchors.margins: 16
            spacing: 12
            Rectangle {
                color: root.raisedColor
                radius: 10
                border.color: root.borderColor
                Layout.preferredWidth: 46
                Layout.preferredHeight: 46
                ModernIcon {
                    anchors.centerIn: parent
                    width: 24
                    height: 24
                    iconName: root.iconName
                    iconColor: root.stateColor()
                }
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 1
                Label {
                    text: root.title
                    color: root.textColor
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
                Label {
                    text: root.stateLabel()
                    color: root.stateColor()
                    font.pixelSize: 12
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
            }
            Label {
                text: root.value
                color: root.textColor
                font.pixelSize: 28
                font.weight: Font.DemiBold
                horizontalAlignment: Text.AlignRight
            }
        }
    }
}
