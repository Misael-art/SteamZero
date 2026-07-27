// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

FocusScope {
    id: root
    property bool active: false
    property bool reducedMotion: false
    property string title: qsTr("Preparando tudo para você")
    property string detail: qsTr("Aguarde enquanto o SteamZero verifica o estado com segurança.")
    property color surfaceColor: "#122131"
    property color borderColor: "#2a3a49"
    property color textColor: "#f2f6fb"
    property color mutedColor: "#9eabba"
    property color accentColor: "#13bdf2"

    visible: opacity > 0
    opacity: active ? 1 : 0
    focus: active
    z: 2000
    Accessible.name: title
    Accessible.description: detail

    Behavior on opacity {
        enabled: !root.reducedMotion
        NumberAnimation { duration: 160; easing.type: Easing.OutCubic }
    }

    Rectangle {
        anchors.fill: parent
        color: "#d9071019"
    }
    MouseArea {
        anchors.fill: parent
        enabled: root.active
        acceptedButtons: Qt.AllButtons
    }
    Rectangle {
        width: Math.min(parent.width - 32, 520)
        implicitHeight: loadingContent.implicitHeight + 48
        height: implicitHeight
        anchors.centerIn: parent
        color: root.surfaceColor
        radius: 16
        border.color: root.borderColor
        border.width: 1

        ColumnLayout {
            id: loadingContent
            anchors.fill: parent
            anchors.margins: 24
            spacing: 14

            Image {
                source: "../assets/steamzero-mark.png"
                sourceSize.width: 64
                sourceSize.height: 64
                fillMode: Image.PreserveAspectFit
                Layout.preferredWidth: 64
                Layout.preferredHeight: 64
                Layout.alignment: Qt.AlignHCenter
                Accessible.name: qsTr("SteamZero")
            }
            BusyIndicator {
                running: root.active
                palette.highlight: root.accentColor
                Layout.preferredWidth: 48
                Layout.preferredHeight: 48
                Layout.alignment: Qt.AlignHCenter
                Accessible.name: qsTr("Operação em andamento")
            }
            Label {
                text: root.title
                color: root.textColor
                font.pixelSize: 21
                font.bold: true
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Label {
                text: root.detail
                color: root.mutedColor
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Label {
                text: qsTr("O progresso é indeterminado; nenhuma porcentagem será estimada.")
                color: root.mutedColor
                font.pixelSize: 12
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }
    }
}
