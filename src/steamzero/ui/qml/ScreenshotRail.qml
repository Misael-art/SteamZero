// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Faixa de capturas publicada pelo read model. Não faz descoberta de arquivos,
// não simula vídeo e mantém a árvore limitada mesmo para uma galeria extensa.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root

    property var sources: []
    property bool highContrast: false
    property bool compact: false
    required property color surfaceColor
    required property color raisedColor
    required property color borderColor
    required property color textColor
    required property color mutedColor
    required property color cyanColor

    readonly property var publishedSources: {
        const rows = []
        const values = sources || []
        for (let i = 0; i < values.length && rows.length < 24; ++i) {
            const source = String(values[i] || "")
            if (source !== "" && rows.indexOf(source) < 0)
                rows.push(source)
        }
        return rows
    }
    readonly property bool hasPublishedMedia: publishedSources.length > 0
    readonly property int itemWidth: compact ? 156 : 232
    readonly property int itemHeight: compact ? 88 : 130
    implicitHeight: railContent.implicitHeight

    ColumnLayout {
        id: railContent
        anchors.left: parent.left
        anchors.right: parent.right
        spacing: 10
        RowLayout {
            Layout.fillWidth: true
            Label {
                text: qsTr("Capturas")
                color: root.textColor
                font.pixelSize: 20
                font.weight: Font.DemiBold
                Layout.fillWidth: true
            }
            Label {
                visible: root.hasPublishedMedia
                text: qsTr("%1 publicada(s)").arg(root.publishedSources.length)
                color: root.mutedColor
                font.pixelSize: 12
            }
        }
        ListView {
            visible: root.hasPublishedMedia && !root.highContrast
            clip: true
            orientation: ListView.Horizontal
            Layout.fillWidth: true
            Layout.preferredHeight: root.itemHeight
            model: root.publishedSources
            spacing: 10
            cacheBuffer: root.itemWidth * 2
            reuseItems: true
            delegate: Rectangle {
                required property string modelData
                width: root.itemWidth
                height: root.itemHeight
                color: root.raisedColor
                radius: 10
                border.color: root.borderColor
                clip: true
                Accessible.name: qsTr("Captura publicada")
                Image {
                    anchors.fill: parent
                    source: modelData
                    asynchronous: true
                    fillMode: Image.PreserveAspectCrop
                }
            }
        }
        Rectangle {
            visible: !root.hasPublishedMedia || root.highContrast
            color: root.surfaceColor
            radius: 10
            border.color: root.borderColor
            Layout.fillWidth: true
            Layout.preferredHeight: 72
            Label {
                anchors.fill: parent
                anchors.margins: 14
                text: root.highContrast && root.hasPublishedMedia
                    ? qsTr("Capturas publicadas ocultas para priorizar contraste")
                    : qsTr("Nenhuma captura foi publicada para este jogo.")
                color: root.mutedColor
                wrapMode: Text.WordWrap
                verticalAlignment: Text.AlignVCenter
            }
        }
    }
}
