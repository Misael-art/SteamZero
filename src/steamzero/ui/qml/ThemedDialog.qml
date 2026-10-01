// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Diálogo modal que pertence ao tema (V1 / AC-134-04, AC-134-05).
// O Dialog nativo herda a paleta do estilo, não a do tema da central: aparecia
// cinza sobre uma superfície escura e com botões de contraste insuficiente. A
// correção mora aqui, na base, em vez de cores fixas por página: fundo, título,
// rodapé (alvos ≥48 px) e palette dos botões padrão derivam dos mesmos tokens.
Dialog {
    id: dialog
    property color surfaceColor: "#0d1924"
    property color raisedColor: "#122131"
    property color borderColor: "#2a3a49"
    property color textColor: "#f2f6fb"
    property color mutedColor: "#9eabba"
    property color accentColor: "#13bdf2"
    property real visualScale: 1.0
    readonly property int minimumTarget: 48

    palette.window: dialog.surfaceColor
    palette.windowText: dialog.textColor
    palette.text: dialog.textColor
    palette.base: dialog.raisedColor
    palette.button: dialog.raisedColor
    palette.buttonText: dialog.textColor
    palette.highlight: dialog.accentColor
    palette.highlightedText: "#04141c"
    palette.placeholderText: dialog.mutedColor
    palette.disabled.buttonText: dialog.mutedColor

    background: Rectangle {
        color: dialog.surfaceColor
        radius: 10
        border.color: dialog.accentColor
        border.width: 1
    }
    header: Label {
        visible: dialog.title.length > 0
        text: dialog.title
        color: dialog.textColor
        font.pixelSize: Math.round(18 * dialog.visualScale)
        font.bold: true
        elide: Label.ElideRight
        leftPadding: 20
        rightPadding: 20
        topPadding: 16
        bottomPadding: 8
        Accessible.role: Accessible.Heading
        Accessible.name: text
    }
    footer: DialogButtonBox {
        visible: count > 0
        standardButtons: dialog.standardButtons
        alignment: Qt.AlignRight
        spacing: 12
        padding: 12
        background: Rectangle { color: "transparent" }
        delegate: Button {
            id: footerButton
            implicitHeight: dialog.minimumTarget
            implicitWidth: Math.max(112, implicitContentWidth + 32)
            Accessible.name: text
            background: Rectangle {
                color: footerButton.down ? dialog.borderColor : dialog.raisedColor
                border.color: footerButton.activeFocus ? dialog.textColor : dialog.accentColor
                border.width: footerButton.activeFocus ? 3 : 1
                radius: 7
            }
            contentItem: Label {
                text: footerButton.text
                color: footerButton.enabled ? dialog.textColor : dialog.mutedColor
                font.pixelSize: Math.round(15 * dialog.visualScale)
                font.bold: true
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
        }
    }
}
