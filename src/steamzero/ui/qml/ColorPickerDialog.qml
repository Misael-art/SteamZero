// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Controls as QQC
import QtQuick.Layouts

QQC.Dialog {
    id: dialog

    property color initialColor: "#13bdf2"
    property color backgroundColor: "#071019"
    property color surfaceColor: "#0d1924"
    property color raisedColor: "#122131"
    property color borderColor: "#2a3a49"
    property color textColor: "#f2f6fb"
    property color mutedColor: "#9eabba"
    property color cyanColor: "#13bdf2"
    property color cyanDarkColor: "#0a5f85"

    property var presets: [
        "#071019", "#0d1924", "#122131", "#2a3a49",
        "#f2f6fb", "#9eabba", "#667481", "#13bdf2",
        "#0a5f85", "#59d35d", "#1b6b1e", "#ff9f1a",
        "#b36e00", "#ff6b73", "#b33d45", "#ffffff",
    ]

    signal colorPicked(color selectedColor)

    onInitialColorChanged: hexField.text = String(initialColor)
    Component.onCompleted: hexField.text = String(initialColor)

    title: qsTr("Selecionar cor")
    modal: true
    width: Math.min(parent ? parent.width : 440, 440)
    x: parent ? (parent.width - width) / 2 : 0
    y: parent ? Math.max((parent.height - height) / 2, 40) : 40
    standardButtons: QQC.Dialog.NoButton
    onAboutToShow: {}
    onClosed: {}

    background: Rectangle {
        color: dialog.raisedColor
        radius: 12
        border.color: dialog.cyanDarkColor
        border.width: 1
    }

    contentItem: ColumnLayout {
        spacing: 16
        Layout.margins: 20

        RowLayout {
            spacing: 14
            Rectangle {
                id: swatch
                implicitWidth: 48
                implicitHeight: 48
                radius: 8
                border.color: dialog.borderColor
                border.width: 1
                color: {
                    var c = hexField.text.trim()
                    return /^#[0-9a-fA-F]{6}$/.test(c) ? c : dialog.initialColor
                }
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4
                QQC.Label {
                    text: qsTr("Hexadecimal")
                    color: dialog.mutedColor
                    font.pixelSize: 12
                }
                QQC.TextField {
                    id: hexField
                    text: String(dialog.initialColor)
                    placeholderText: "#RRGGBB"
                    maximumLength: 7
                    Layout.fillWidth: true
                    Layout.minimumHeight: 40
                    color: dialog.textColor
                    background: Rectangle {
                        color: dialog.backgroundColor
                        radius: 6
                        border.color: dialog.borderColor
                        border.width: 1
                    }
                    onTextChanged: {
                        if (/^#[0-9a-fA-F]{6}$/.test(text))
                            swatch.color = text
                    }
                }
            }
        }

        QQC.Label {
            text: qsTr("Predefinidas")
            color: dialog.mutedColor
            font.pixelSize: 12
        }

        Flow {
            Layout.fillWidth: true
            spacing: 8
            Repeater {
                model: dialog.presets
                delegate: Rectangle {
                    required property var modelData
                    implicitWidth: 36
                    implicitHeight: 36
                    radius: 6
                    color: modelData
                    border.color: hexField.text.trim().toUpperCase() === String(modelData).toUpperCase()
                        ? dialog.textColor : dialog.borderColor
                    border.width: hexField.text.trim().toUpperCase() === String(modelData).toUpperCase()
                        ? 2 : 1
                    Accessible.name: qsTr("Cor %1").arg(modelData)
                    Accessible.role: Accessible.Button
                    TapHandler {
                        onTapped: hexField.text = String(modelData)
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 12
            Item { Layout.fillWidth: true }
            QQC.Button {
                text: qsTr("Cancelar")
                Layout.minimumHeight: 44
                Layout.preferredWidth: 120
                onClicked: dialog.close()
                background: Rectangle {
                    color: dialog.surfaceColor
                    radius: 8
                    border.color: dialog.borderColor
                    border.width: 1
                }
                contentItem: QQC.Label {
                    text: parent.text
                    color: dialog.textColor
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }
            QQC.Button {
                text: qsTr("Aplicar")
                Layout.minimumHeight: 44
                Layout.preferredWidth: 120
                onClicked: {
                    var c = hexField.text.trim()
                    if (/^#[0-9a-fA-F]{6}$/.test(c)) {
                        dialog.colorPicked(c)
                        dialog.close()
                    }
                }
                background: Rectangle {
                    color: dialog.cyanColor
                    radius: 8
                    border.color: parent.activeFocus ? dialog.textColor : "transparent"
                    border.width: parent.activeFocus ? 2 : 0
                }
                contentItem: QQC.Label {
                    text: parent.text
                    color: "#071019"
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    font.weight: Font.Medium
                }
            }
        }
    }
}
