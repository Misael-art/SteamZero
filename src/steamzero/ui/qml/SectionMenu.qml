// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Popup {
    id: root
    property var sections: []
    property int currentIndex: 0
    property Item returnFocusItem: null
    property color surfaceColor: "#122131"
    property color borderColor: "#2a3a49"
    property color textColor: "#f2f6fb"
    property color mutedColor: "#9eabba"
    property color accentColor: "#13bdf2"

    signal sectionChosen(int index)

    modal: true
    focus: true
    // Escape é tratado pelo histórico global para evitar fechamento duplo e perda de contexto.
    closePolicy: Popup.CloseOnPressOutside
    padding: 16
    Accessible.name: qsTr("Lista de seções")

    function restoreFocus() {
        const target = returnFocusItem
        returnFocusItem = null
        if (target)
            Qt.callLater(function() { target.forceActiveFocus(Qt.OtherFocusReason) })
    }

    onOpened: {
        const target = sectionRepeater.itemAt(Math.max(0,
            Math.min(currentIndex, sectionRepeater.count - 1)))
        if (target)
            target.forceActiveFocus(Qt.PopupFocusReason)
    }
    onClosed: restoreFocus()

    background: Rectangle {
        color: root.surfaceColor
        radius: 12
        border.color: root.borderColor
        border.width: 1
    }

    contentItem: ColumnLayout {
        spacing: 8

        Label {
            text: qsTr("Ir para uma seção")
            color: root.textColor
            font.pixelSize: 20
            font.bold: true
            Layout.fillWidth: true
        }
        Label {
            text: qsTr("Escolha um bloco desta página.")
            color: root.mutedColor
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Rectangle {
            color: root.borderColor
            Layout.fillWidth: true
            Layout.preferredHeight: 1
        }
        Repeater {
            id: sectionRepeater
            model: root.sections
            delegate: Button {
                required property int index
                required property var modelData
                text: qsTr("%1. %2").arg(index + 1).arg(modelData.label)
                icon.name: index === root.currentIndex ? "go-next" : ""
                icon.color: root.accentColor
                Layout.fillWidth: true
                Layout.minimumHeight: 48
                Accessible.name: qsTr("%1, seção %2 de %3")
                    .arg(modelData.label).arg(index + 1).arg(root.sections.length)
                onClicked: {
                    root.sectionChosen(index)
                    root.close()
                }
                background: Rectangle {
                    color: parent.activeFocus || parent.index === root.currentIndex
                        ? "#183044" : "transparent"
                    radius: 7
                    border.color: parent.activeFocus ? root.accentColor : "transparent"
                    border.width: parent.activeFocus ? 2 : 0
                }
                contentItem: Label {
                    text: parent.text
                    color: parent.index === root.currentIndex ? root.accentColor : root.textColor
                    verticalAlignment: Text.AlignVCenter
                    wrapMode: Text.WordWrap
                    leftPadding: 12
                    rightPadding: 12
                }
            }
        }
    }
}
