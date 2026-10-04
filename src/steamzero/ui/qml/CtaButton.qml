// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Controls as QQC

// Botão de ação principal compartilhado (V1 / AC-134-03, AC-134-05).
// Preenchimento e texto formam um par fixo ≥7:1 (branco sobre #045a80 = 7,56:1),
// independente da paleta do tema; desabilitado usa a superfície do pai com texto
// `mutedColor` e o motivo vai em Accessible.description, não só em cor.
QQC.Button {
    id: control
    property color fillColor: "#045a80"
    property color labelColor: "#ffffff"
    property color disabledFill: "#2b3a45"
    property color disabledLabel: "#c6d0db"
    property color focusColor: "#ffffff"
    property color outlineColor: "#55d8ff"
    property int labelSize: 16
    implicitHeight: Math.max(48, contentItem.implicitHeight + 24)
    Accessible.name: text

    background: Rectangle {
        color: control.enabled ? control.fillColor : control.disabledFill
        border.color: control.activeFocus ? control.focusColor : control.outlineColor
        border.width: control.activeFocus ? 3 : 1
        radius: 7
    }
    contentItem: QQC.Label {
        text: control.text
        color: control.enabled ? control.labelColor : control.disabledLabel
        font.pixelSize: control.labelSize
        font.bold: true
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
}
