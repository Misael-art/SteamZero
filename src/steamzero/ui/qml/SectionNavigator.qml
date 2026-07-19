// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    property Flickable flickable: null
    property var sections: []
    property bool reducedMotion: false
    property color surfaceColor: "#122131"
    property color borderColor: "#2a3a49"
    property color textColor: "#f2f6fb"
    property color mutedColor: "#9eabba"
    property color accentColor: "#13bdf2"
    property int activeIndex: 0

    signal menuRequested()

    implicitWidth: 64
    implicitHeight: navigatorColumn.implicitHeight
    visible: flickable !== null && sections.length > 1
        && flickable.contentHeight > flickable.height + 8

    function sectionLabel(index) {
        if (index < 0 || index >= sections.length)
            return ""
        return qsTr("%1 · %2 de %3").arg(sections[index].label).arg(index + 1).arg(sections.length)
    }

    function sectionY(index) {
        if (!flickable || index < 0 || index >= sections.length || !sections[index].item)
            return 0
        return Math.max(0, Math.min(sections[index].item.y - 12,
            flickable.contentHeight - flickable.height))
    }

    function goTo(index) {
        if (!flickable || sections.length === 0)
            return
        const destination = Math.max(0, Math.min(index, sections.length - 1))
        activeIndex = destination
        const targetY = sectionY(destination)
        if (reducedMotion) {
            flickable.contentY = targetY
        } else {
            scrollAnimation.stop()
            scrollAnimation.from = flickable.contentY
            scrollAnimation.to = targetY
            scrollAnimation.start()
        }
    }

    function previousSection() { goTo(activeIndex - 1) }
    function nextSection() { goTo(activeIndex + 1) }

    function updateActiveSection() {
        if (!flickable || sections.length === 0)
            return
        const marker = flickable.contentY + 36
        let next = 0
        for (let index = 0; index < sections.length; index++) {
            if (sectionY(index) <= marker)
                next = index
        }
        activeIndex = next
    }

    NumberAnimation {
        id: scrollAnimation
        target: root.flickable
        property: "contentY"
        duration: 180
        easing.type: Easing.OutCubic
    }
    Connections {
        target: root.flickable
        ignoreUnknownSignals: true
        function onContentYChanged() { root.updateActiveSection() }
        function onContentHeightChanged() { root.updateActiveSection() }
    }

    Rectangle {
        anchors.fill: parent
        color: root.surfaceColor
        radius: 12
        border.color: root.borderColor
        opacity: 0.96
    }
    ColumnLayout {
        id: navigatorColumn
        anchors.fill: parent
        anchors.margins: 8
        spacing: 4

        ToolButton {
            id: menuButton
            text: "≡"
            font.pixelSize: 20
            Layout.minimumWidth: 48
            Layout.minimumHeight: 48
            Accessible.name: qsTr("Abrir lista de seções")
            ToolTip.visible: activeFocus || hovered
            ToolTip.text: Accessible.name
            onClicked: root.menuRequested()
        }

        ToolButton {
            id: previousButton
            icon.name: "go-up"
            enabled: root.activeIndex > 0
            Layout.minimumWidth: 48
            Layout.minimumHeight: 48
            Accessible.name: qsTr("Seção anterior")
            ToolTip.visible: activeFocus || hovered
            ToolTip.text: Accessible.name
            onClicked: root.previousSection()
        }
        Repeater {
            model: root.sections
            delegate: ToolButton {
                required property int index
                required property var modelData
                text: "●"
                font.pixelSize: root.activeIndex === index ? 16 : 11
                palette.buttonText: root.activeIndex === index ? root.accentColor : root.mutedColor
                Layout.minimumWidth: 48
                Layout.minimumHeight: 32
                Accessible.name: root.sectionLabel(index)
                ToolTip.visible: activeFocus || hovered
                ToolTip.text: Accessible.name
                onClicked: root.goTo(index)
            }
        }
        ToolButton {
            id: nextButton
            icon.name: "go-down"
            enabled: root.activeIndex + 1 < root.sections.length
            Layout.minimumWidth: 48
            Layout.minimumHeight: 48
            Accessible.name: qsTr("Próxima seção")
            ToolTip.visible: activeFocus || hovered
            ToolTip.text: Accessible.name
            onClicked: root.nextSection()
        }
        Label {
            visible: menuButton.activeFocus || previousButton.activeFocus || nextButton.activeFocus
            text: root.sectionLabel(root.activeIndex)
            color: root.textColor
            font.pixelSize: 11
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            Layout.preferredWidth: 48
        }
    }
}
