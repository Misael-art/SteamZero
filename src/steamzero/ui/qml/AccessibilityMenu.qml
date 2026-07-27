// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Popup {
    id: root
    property bool highContrast: false
    property bool reducedMotion: false
    property real textScale: 1.0
    property Item returnFocusItem: null
    property color surfaceColor: "#122131"
    property color borderColor: "#2a3a49"
    property color textColor: "#f2f6fb"
    property color mutedColor: "#9eabba"
    property color accentColor: "#13bdf2"
    property int minimumTarget: 48
    property real visualScale: 1.0

    signal highContrastRequested(bool enabled)
    signal reducedMotionRequested(bool enabled)
    signal textScaleRequested(real scale)

    modal: true
    focus: true
    closePolicy: Popup.CloseOnPressOutside
    padding: 18
    Accessible.name: qsTr("Preferências de acessibilidade")

    function scaleIndex() {
        if (textScale >= 1.5)
            return 2
        if (textScale >= 1.25)
            return 1
        return 0
    }

    onOpened: highContrastSwitch.forceActiveFocus(Qt.PopupFocusReason)
    onClosed: {
        const target = returnFocusItem
        returnFocusItem = null
        if (target)
            Qt.callLater(function() { target.forceActiveFocus(Qt.OtherFocusReason) })
    }

    background: Rectangle {
        color: root.surfaceColor
        radius: 12
        border.color: root.borderColor
    }

    contentItem: ColumnLayout {
        spacing: 12

        Label {
            text: qsTr("Acessibilidade visual")
            color: root.textColor
            font.pixelSize: Math.round(20 * root.visualScale)
            font.bold: true
            Layout.fillWidth: true
        }
        Label {
            text: qsTr("As alterações são imediatas e não modificam o estado operacional.")
            color: root.mutedColor
            font.pixelSize: Math.round(13 * root.visualScale)
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Switch {
            id: highContrastSwitch
            text: qsTr("Alto contraste")
            checked: root.highContrast
            font.pixelSize: Math.round(14 * root.visualScale)
            Layout.fillWidth: true
            Layout.minimumHeight: root.minimumTarget
            Accessible.name: text
            onToggled: root.highContrastRequested(checked)
        }
        Switch {
            id: reducedMotionSwitch
            text: qsTr("Reduzir movimento")
            checked: root.reducedMotion
            font.pixelSize: Math.round(14 * root.visualScale)
            Layout.fillWidth: true
            Layout.minimumHeight: root.minimumTarget
            Accessible.name: text
            onToggled: root.reducedMotionRequested(checked)
        }
        Label {
            text: qsTr("Escala da interface")
            color: root.textColor
            font.bold: true
            font.pixelSize: Math.round(14 * root.visualScale)
            Layout.fillWidth: true
        }
        ComboBox {
            id: scaleSelector
            model: [
                {"label": qsTr("100% — padrão"), "value": 1.0},
                {"label": qsTr("125% — ampliada"), "value": 1.25},
                {"label": qsTr("150% — máxima"), "value": 1.5}
            ]
            textRole: "label"
            currentIndex: root.scaleIndex()
            font.pixelSize: Math.round(14 * root.visualScale)
            Layout.fillWidth: true
            Layout.minimumHeight: root.minimumTarget
            Accessible.name: qsTr("Escala da interface: %1").arg(currentText)
            onActivated: function(index) { root.textScaleRequested(model[index].value) }
        }
        Button {
            text: qsTr("Concluir")
            font.pixelSize: Math.round(14 * root.visualScale)
            Layout.fillWidth: true
            Layout.minimumHeight: root.minimumTarget
            Accessible.name: qsTr("Fechar preferências de acessibilidade")
            onClicked: root.close()
        }
    }
}
