// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Controls as QQC
import QtQuick.Layouts

QQC.Button {
    id: control
    palette.buttonText: control.enabled ? "#f2f6fb" : "#71808d"
    contentItem: RowLayout {
        spacing: control.spacing

        QQC.ToolButton {
            visible: control.display !== QQC.AbstractButton.TextOnly && control.icon.name.length > 0
            enabled: false
            icon.name: control.icon.name
            icon.source: control.icon.source
            icon.color: control.icon.color.a > 0 ? control.icon.color
                : control.enabled ? "#f2f6fb" : "#71808d"
            icon.width: control.icon.width > 0 ? control.icon.width : 22
            icon.height: control.icon.height > 0 ? control.icon.height : 22
            background: Item {}
            Layout.preferredWidth: control.icon.width > 0 ? control.icon.width : 22
            Layout.preferredHeight: control.icon.height > 0 ? control.icon.height : 22
            Layout.alignment: Qt.AlignVCenter
        }
        QQC.Label {
            visible: control.display !== QQC.AbstractButton.IconOnly
            text: control.text
            color: control.enabled ? "#f2f6fb" : "#71808d"
            font: control.font
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            wrapMode: Text.WordWrap
            maximumLineCount: 2
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignVCenter
        }
    }
}
