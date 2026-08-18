// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Consumidor de slots já resolvidos. Não lê o catálogo de jogos, não abre
// saves e não interpreta o OSD: só desenha o contrato materializado.
import QtQuick

Item {
    id: surfacePreview

    required property var surfaces

    readonly property var gallery: surfaces && surfaces.slots && surfaces.slots.saveStates
        ? surfaces.slots.saveStates : ({"entries": []})
    readonly property var osd: surfaces && surfaces.slots && surfaces.slots.osd
        ? surfaces.slots.osd : ({"items": [], "progress": 0, "criticalVisible": false})
    readonly property int saveCount: gallery.entries ? gallery.entries.length : 0
    readonly property bool thumbnailFallback: saveCount > 1 && gallery.entries[1].thumbnailFallback === true
    readonly property bool criticalVisible: osd.criticalVisible === true
    readonly property real progress: osd.progress !== undefined ? Number(osd.progress) : 0

    Column {
        anchors.fill: parent
        anchors.margins: 4
        spacing: 6

        Repeater {
            model: surfacePreview.gallery.entries || []
            delegate: Rectangle {
                required property var modelData
                width: parent.width
                height: 18
                radius: 4
                color: modelData.thumbnailFallback ? "#334155" : "#0e7490"
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.left: parent.left
                    anchors.leftMargin: 6
                    text: modelData.title
                    color: "#f2f6fb"
                    font.pixelSize: 11
                }
            }
        }

        Rectangle {
            width: parent.width
            height: 8
            radius: 4
            color: "#1e293b"
            Rectangle {
                width: Math.max(0, parent.width * surfacePreview.progress)
                height: parent.height
                radius: 4
                color: surfacePreview.criticalVisible ? "#ff8a90" : "#22d3ee"
            }
        }
    }
}
