// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Controls as QQC

QQC.Button {
    id: control
    palette.buttonText: control.enabled ? "#f2f6fb" : "#71808d"
    contentItem: QQC.Label {
        text: control.text
        color: control.enabled ? "#f2f6fb" : "#71808d"
        font: control.font
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
}
