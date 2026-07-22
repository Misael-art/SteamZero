// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Controls

ComboBox {
    id: control
    property color surfaceColor: "#0d1924"
    property color raisedColor: "#122131"
    property color borderColor: "#2a3a49"
    property color textColor: "#f2f6fb"
    property color mutedColor: "#9eabba"
    property color accentColor: "#13bdf2"

    implicitHeight: 48
    leftPadding: 14
    rightPadding: 44
    Accessible.name: displayText

    contentItem: Text {
        leftPadding: 0
        rightPadding: 0
        text: control.displayText
        color: control.enabled ? control.textColor : control.mutedColor
        font: control.font
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    indicator: ToolButton {
        x: control.width - width - 4
        y: (control.height - height) / 2
        width: 40
        height: 40
        enabled: false
        icon.name: control.popup.visible ? "go-up" : "go-down"
        icon.color: control.enabled ? control.textColor : control.mutedColor
        background: Item {}
    }
    background: Rectangle {
        color: control.activeFocus ? control.raisedColor : control.surfaceColor
        radius: 8
        border.color: control.activeFocus ? control.accentColor : control.borderColor
        border.width: control.activeFocus ? 2 : 1
    }
    popup: Popup {
        y: control.height + 4
        width: control.width
        implicitHeight: Math.min(contentItem.implicitHeight, 280)
        padding: 4
        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: control.popup.visible ? control.delegateModel : null
            currentIndex: control.highlightedIndex
            ScrollIndicator.vertical: ScrollIndicator {}
        }
        background: Rectangle {
            color: control.raisedColor
            radius: 8
            border.color: control.accentColor
        }
    }
    delegate: ItemDelegate {
        width: control.width - 8
        height: 48
        text: control.textRole
            ? (Array.isArray(control.model) ? model[control.textRole] : modelData[control.textRole])
            : modelData
        highlighted: control.highlightedIndex === index
        palette.text: control.textColor
        palette.highlightedText: control.textColor
        background: Rectangle {
            color: parent.highlighted ? "#183044" : "transparent"
            radius: 6
        }
    }
}
