// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    property bool compact: false
    property bool showContextAction: false
    property bool sectionNavigationAvailable: false
    property bool sectionListAvailable: false
    property color backgroundColor: "#080d13"
    property color borderColor: "#2a3a49"
    property color textColor: "#f2f6fb"
    property color mutedColor: "#9eabba"
    property int targetHeight: 52
    property int compactTextSize: 12
    property int textSize: 13
    property var commands: {
        const result = compact
            ? [qsTr("D-PAD  Navegar"), qsTr("A  Selecionar"), qsTr("Esc  Voltar")]
            : [qsTr("D-PAD  Navegar"), qsTr("A  Selecionar"), qsTr("Esc  Voltar")]
        if (sectionNavigationAvailable)
            result.unshift(qsTr("PgUp/PgDn  Seções"))
        if (sectionListAvailable && !compact)
            result.unshift(qsTr("F6  Lista de seções"))
        return result
    }

    color: backgroundColor
    border.color: borderColor
    implicitHeight: targetHeight
    Accessible.name: qsTr("Comandos disponíveis")

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: root.compact ? 12 : 20
        anchors.rightMargin: root.compact ? 12 : 20
        spacing: root.compact ? 10 : 20

        Repeater {
            model: root.commands
            delegate: Label {
                required property int index
                required property string modelData
                text: modelData
                color: index === 0 ? root.mutedColor : root.textColor
                font.pixelSize: root.compact ? root.compactTextSize : root.textSize
                font.bold: index === 0
                elide: Text.ElideRight
                Layout.fillWidth: true
                horizontalAlignment: index === 0 ? Text.AlignLeft : Text.AlignHCenter
            }
        }
        Label {
            visible: root.showContextAction && !root.compact
            text: qsTr("X  Ação de contexto")
            color: root.textColor
        }
    }
}
