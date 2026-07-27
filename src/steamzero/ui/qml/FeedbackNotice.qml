// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    property string message: ""
    property bool error: false
    property color surfaceColor: "#122131"
    property color textColor: "#f2f6fb"
    property color mutedColor: "#9eabba"
    property color successColor: "#59d35d"
    property color errorColor: "#ff6b73"
    property int minimumTarget: 48

    readonly property string displayTitle: error
        ? qsTr("Não foi possível concluir") : qsTr("Ação concluída")
    readonly property string impactText: error
        ? qsTr("O estado anterior foi preservado. Revise o diagnóstico antes de tentar novamente.")
        : ""
    readonly property bool hasContextAction: error

    signal contextActionRequested()
    signal dismissRequested()

    visible: message.length > 0
    color: surfaceColor
    radius: 8
    border.color: error ? errorColor : successColor
    implicitHeight: noticeContent.implicitHeight + 24
    Accessible.name: error
        ? qsTr("Erro. %1. Impacto: %2").arg(message).arg(impactText)
        : qsTr("Sucesso. %1").arg(message)

    RowLayout {
        id: noticeContent
        anchors.fill: parent
        anchors.margins: 12
        spacing: 10

        ToolButton {
            enabled: false
            icon.name: root.error ? "dialog-error" : "dialog-ok-apply"
            icon.color: root.error ? root.errorColor : root.successColor
            background: Item {}
            Layout.minimumWidth: root.minimumTarget
            Layout.minimumHeight: root.minimumTarget
        }
        ColumnLayout {
            spacing: 2
            Layout.fillWidth: true
            Label {
                text: root.displayTitle
                color: root.error ? root.errorColor : root.successColor
                font.bold: true
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Label {
                text: root.message
                color: root.textColor
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Label {
                visible: root.error
                text: root.impactText
                color: root.mutedColor
                font.pixelSize: 12
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }
        Button {
            visible: root.hasContextAction
            text: qsTr("Ver diagnóstico")
            Layout.minimumHeight: root.minimumTarget
            Accessible.name: qsTr("Ver diagnóstico do sistema para este erro")
            onClicked: root.contextActionRequested()
        }
        ToolButton {
            icon.name: "window-close"
            text: "×"
            Layout.minimumWidth: root.minimumTarget
            Layout.minimumHeight: root.minimumTarget
            Accessible.name: qsTr("Dispensar mensagem")
            onClicked: root.dismissRequested()
        }
    }
}
