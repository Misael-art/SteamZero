// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: card

    property var errorObject: ({})
    property bool critical: false
    property bool detailed: false
    property string areaColor: "#d5b47d"
    property string areaIcon: "dialog-warning"
    property string codeLabel: ""
    property string titleLabel: ""
    property string whatLabel: ""
    property string impactLabel: ""
    property string autoActionLabel: ""
    property string manualActionLabel: ""
    property string probableCauseLabel: ""
    property string operationIdLabel: ""

    signal dismiss()
    signal showDiagnostics()

    function resolve(error) {
        if (!error || typeof error !== "object") {
            card.visible = false
            return
        }
        card.visible = true
        var code = String(error.code || "")
        codeLabel = code
        titleLabel = String(error.title || "")
        whatLabel = String(error.what || "")
        impactLabel = String(error.impact || "")
        autoActionLabel = String(error.autoAction || "")
        manualActionLabel = String(error.manualAction || "")
        probableCauseLabel = String(error.probableCause || "")
        operationIdLabel = String(error.operationId || "")

        var area = code.startsWith("E-") ? code.split("-")[1] : ""
        if (area === "TX" || area === "SESSION" || area === "DESKTOP" || area === "SAVES") {
            critical = true
            areaColor = "#d45454"
            areaIcon = "dialog-error"
        } else if (area === "STORAGE" || area === "CONTENT" || area === "SUPPLY") {
            critical = false
            areaColor = "#ff9f1a"
            areaIcon = "dialog-warning"
        } else {
            critical = false
            areaColor = "#d5b47d"
            areaIcon = "dialog-information"
        }
        var criticalCodes = [
            "E-TX-ROLLBACK-FAILED", "E-SESSION-INTERRUPTED",
            "E-DESKTOP-OWNER-CONFLICT", "E-DESKTOP-RECOVERY", "E-SAVES-FLUSH-TIMEOUT"
        ]
        if (criticalCodes.indexOf(code) >= 0)
            critical = true
    }

    color: "#24180b"
    border.color: areaColor
    border.width: 1
    radius: 8
    Layout.fillWidth: true
    Layout.maximumWidth: 1400
    Layout.alignment: Qt.AlignHCenter
    Layout.leftMargin: 14
    Layout.rightMargin: 14
    Layout.topMargin: 7
    Layout.preferredHeight: detailColumn.implicitHeight + 28

    ColumnLayout {
        id: detailColumn
        anchors.fill: parent
        anchors.margins: 14
        spacing: 6

        RowLayout {
            Layout.fillWidth: true
            spacing: 10
            ToolButton {
                enabled: false
                icon.name: areaIcon
                icon.color: areaColor
                icon.width: 26
                icon.height: 26
                background: Item {}
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2
                RowLayout {
                    Layout.fillWidth: true
                    Label {
                        text: titleLabel
                        color: areaColor
                        font.pixelSize: 15
                        font.bold: true
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                    }
                    Label {
                        text: codeLabel
                        color: areaColor
                        font.pixelSize: 10
                        opacity: 0.7
                    }
                }
                Label {
                    visible: whatLabel.length > 0
                    text: whatLabel
                    color: "#f2f6fb"
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                Label {
                    visible: impactLabel.length > 0
                    text: qsTr("Impacto: ") + impactLabel
                    color: "#d5b47d"
                    font.pixelSize: 11
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }
        }

        Label {
            visible: autoActionLabel.length > 0
            text: qsTr("Ação automática: ") + autoActionLabel
            color: "#59d35d"
            font.pixelSize: 11
            font.italic: true
            Layout.fillWidth: true
            Layout.leftMargin: 36
        }

        Label {
            visible: manualActionLabel.length > 0
            text: qsTr("Orientação: ") + manualActionLabel
            color: "#f2f6fb"
            font.pixelSize: 11
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
            Layout.leftMargin: 36
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 36
            spacing: 8
            Button {
                id: detailButton
                text: detailed ? qsTr("Ocultar detalhes") : qsTr("Ver detalhes")
                palette.buttonText: "#9eabba"
                Layout.minimumHeight: 36
                Accessible.name: text
                onClicked: detailed = !detailed
                background: Rectangle {
                    color: detailButton.activeFocus ? "#1a2530" : "#0d1924"
                    radius: 6
                    border.color: detailButton.activeFocus ? "#13bdf2" : "#2a3a49"
                    border.width: detailButton.activeFocus ? 2 : 1
                }
            }
            Button {
                text: qsTr("Exportar diagnóstico")
                palette.buttonText: "#9eabba"
                Layout.minimumHeight: 36
                Accessible.name: text
                onClicked: card.showDiagnostics()
                background: Rectangle {
                    color: "#0d1924"
                    radius: 6
                    border.color: "#2a3a49"
                    border.width: 1
                }
            }
            Item { Layout.fillWidth: true }
            Button {
                visible: !critical
                text: qsTr("Descartar")
                palette.buttonText: "#71808d"
                Layout.minimumHeight: 36
                Accessible.name: text
                onClicked: card.dismiss()
                background: Rectangle {
                    color: "#09131d"
                    radius: 6
                    border.color: "#2a3a49"
                    border.width: 1
                }
            }
        }

        ColumnLayout {
            visible: detailed
            Layout.fillWidth: true
            Layout.leftMargin: 36
            spacing: 4
            Label {
                visible: probableCauseLabel.length > 0
                text: qsTr("Causa provável: ") + probableCauseLabel
                color: "#9eabba"
                font.pixelSize: 11
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Label {
                visible: operationIdLabel.length > 0
                text: qsTr("ID da operação: ") + operationIdLabel
                color: "#71808d"
                font.pixelSize: 10
                Layout.fillWidth: true
            }
        }
    }
}
