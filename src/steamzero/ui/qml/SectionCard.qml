// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    default property alias contentData: contentColumn.data
    property string title: ""
    property string subtitle: ""
    property color surfaceColor: "#0d1924"
    property color borderColor: "#2a3a49"
    property color textColor: "#f2f6fb"
    property color mutedColor: "#9eabba"
    property int padding: 20
    property int contentSpacing: 12
    property int titleSize: 18

    color: surfaceColor
    radius: 10
    border.color: borderColor
    implicitHeight: contentColumn.implicitHeight + padding * 2
    Layout.minimumWidth: 240
    Layout.preferredWidth: 420
    Layout.maximumWidth: 920

    ColumnLayout {
        id: contentColumn
        anchors.fill: parent
        anchors.margins: root.padding
        spacing: root.contentSpacing

        Label {
            visible: root.title.length > 0
            text: root.title
            color: root.textColor
            font.pixelSize: root.titleSize
            font.bold: true
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Label {
            visible: root.subtitle.length > 0
            text: root.subtitle
            color: root.mutedColor
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }
}
