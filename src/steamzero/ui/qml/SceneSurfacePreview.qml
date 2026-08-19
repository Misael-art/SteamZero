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

    // Barra de progresso do slot loading: estilo, faixas preenchidas, ângulo e
    // rótulo chegam prontos. O QML não conta segmentos nem formata contador.
    readonly property var loading: surfaces && surfaces.slots && surfaces.slots.loading
        ? surfaces.slots.loading : ({"kind": "loadingState"})
    readonly property bool loadingIsProgress: loading.kind === "progressBar"
    readonly property string loadingStyle: loading.style !== undefined ? String(loading.style) : "linear"
    readonly property int loadingSegments: loading.segments !== undefined ? Number(loading.segments) : 0
    readonly property int loadingFilled: loading.filledSegments !== undefined
        ? Number(loading.filledSegments) : 0
    readonly property real loadingSweep: loading.sweep !== undefined ? Number(loading.sweep) : 0
    readonly property string loadingLabel: loading.label !== undefined ? String(loading.label) : ""

    // Widgets allowlisted: relógio e estatística chegam formatados pelo domínio.
    readonly property var clockSlot: surfaces && surfaces.slots && surfaces.slots.quickMenu
        ? surfaces.slots.quickMenu : ({"kind": "emptyState"})
    readonly property var statsSlot: surfaces && surfaces.slots && surfaces.slots.collections
        ? surfaces.slots.collections : ({"kind": "emptyState"})
    readonly property string clockLabel: clockSlot.kind === "clock" && clockSlot.label !== undefined
        ? String(clockSlot.label) : ""
    readonly property string statsLabel: statsSlot.kind === "statistics" && statsSlot.label !== undefined
        ? String(statsSlot.label) : ""

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

        Row {
            id: segmentRow
            visible: surfacePreview.loadingIsProgress && surfacePreview.loadingSegments > 0
            spacing: 3
            Repeater {
                model: surfacePreview.loadingSegments
                delegate: Rectangle {
                    required property int index
                    width: 10
                    height: 8
                    radius: surfacePreview.loadingStyle === "dotted" ? 4 : 2
                    color: index < surfacePreview.loadingFilled ? "#22d3ee" : "#1e293b"
                }
            }
        }

        Text {
            id: counterLabel
            visible: surfacePreview.loadingIsProgress && text.length > 0
            text: surfacePreview.loadingLabel
            color: "#f2f6fb"
            font.pixelSize: 11
        }

        Row {
            spacing: 8
            Text {
                id: clockText
                visible: text.length > 0
                text: surfacePreview.clockLabel
                color: "#f2f6fb"
                font.pixelSize: 11
            }
            Text {
                id: statsText
                visible: text.length > 0
                text: surfacePreview.statsLabel
                color: "#94a3b8"
                font.pixelSize: 11
            }
        }
    }
}
