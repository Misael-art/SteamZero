// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Controls

Drawer {
    id: root
    default property alias contentData: contentHost.data
    property Item returnFocusItem: null
    property color panelColor: "#0d1924"
    property color borderColor: "#2a3a49"

    edge: Qt.RightEdge
    modal: true
    dim: true
    width: Math.min(420, parent ? parent.width - 32 : 420)
    height: parent ? parent.height : implicitHeight
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    Accessible.name: qsTr("Painel de detalhes")

    background: Rectangle {
        color: root.panelColor
        border.color: root.borderColor
        border.width: 1
    }
    contentItem: Item {
        id: contentHost
    }
    onClosed: {
        if (returnFocusItem)
            returnFocusItem.forceActiveFocus()
    }
}
