// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    property string iconName: "dialog-information"
    property string title: ""
    property string description: ""
    property string primaryText: ""
    property string secondaryText: ""
    property color textColor: "#f2f6fb"
    property color mutedColor: "#9eabba"
    property color accentColor: "#13bdf2"
    property int minimumTarget: 48
    signal primaryTriggered()
    signal secondaryTriggered()

    implicitHeight: Math.max(240, content.implicitHeight + 48)
    Accessible.name: title
    Accessible.description: description

    ColumnLayout {
        id: content
        width: Math.min(parent.width - 32, 560)
        anchors.centerIn: parent
        spacing: 12

        ToolButton {
            enabled: false
            icon.name: root.iconName
            icon.color: root.accentColor
            icon.width: 42
            icon.height: 42
            background: Item {}
            Layout.alignment: Qt.AlignHCenter
        }
        Label {
            text: root.title
            color: root.textColor
            font.pixelSize: 20
            font.bold: true
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Label {
            text: root.description
            color: root.mutedColor
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        GridLayout {
            visible: root.primaryText.length > 0 || root.secondaryText.length > 0
            columns: root.width < 520 ? 1 : 2
            columnSpacing: 10
            rowSpacing: 10
            Layout.fillWidth: true
            Layout.topMargin: 8

            Button {
                visible: root.primaryText.length > 0
                text: root.primaryText
                Layout.fillWidth: true
                Layout.minimumHeight: root.minimumTarget
                Accessible.name: text
                onClicked: root.primaryTriggered()
            }
            Button {
                visible: root.secondaryText.length > 0
                text: root.secondaryText
                Layout.fillWidth: true
                Layout.minimumHeight: root.minimumTarget
                Accessible.name: text
                onClicked: root.secondaryTriggered()
            }
        }
    }
}
