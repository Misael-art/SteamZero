// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Controls as QQC

// Texto e ícone seguem palette.buttonText do pai (tema claro/escuro).
// Não hardcodar cor clara: no tema mineral o fundo da sidebar é claro.
// primary: texto escuro sobre preenchimento ciano (quando o pai não sobrescreve).
QQC.Button {
    id: control
    property bool primary: false
    // Pais (Main.qml) definem palette.buttonText = root.textColor / muted.
    // labelColor pode ser sobrescrito pelo pai; o default respeita a paleta.
    property color labelColor: {
        if (control.primary)
            return control.enabled ? "#0b1a22" : "#7a878b"
        if (!control.enabled) {
            if (control.palette.disabled.buttonText.a > 0)
                return control.palette.disabled.buttonText
            return "#7a878b"
        }
        if (control.palette.buttonText.a > 0)
            return control.palette.buttonText
        return "#16212a"
    }

    contentItem: QQC.Label {
        text: control.text
        color: control.labelColor
        font: control.font
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
}
