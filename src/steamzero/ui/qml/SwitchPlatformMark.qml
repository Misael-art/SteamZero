// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick

Item {
    id: mark

    property color leftColor: "#16bff3"
    property color rightColor: "#ff5d68"
    property color cutoutColor: "#0d1924"
    property bool compact: false

    implicitWidth: compact ? 38 : 58
    implicitHeight: compact ? 38 : 58
    Accessible.name: qsTr("Símbolo da plataforma Nintendo Switch")
    Accessible.role: Accessible.Graphic

    Row {
        anchors.centerIn: parent
        spacing: Math.max(3, mark.width * 0.07)

        Rectangle {
            width: mark.width * 0.39
            height: mark.height * 0.82
            radius: width * 0.45
            color: mark.leftColor

            Rectangle {
                anchors.centerIn: parent
                anchors.verticalCenterOffset: -parent.height * 0.18
                width: parent.width * 0.38
                height: width
                radius: width / 2
                color: mark.cutoutColor
            }
        }

        Rectangle {
            width: mark.width * 0.39
            height: mark.height * 0.82
            radius: width * 0.45
            color: mark.rightColor

            Rectangle {
                anchors.centerIn: parent
                anchors.verticalCenterOffset: parent.height * 0.18
                width: parent.width * 0.38
                height: width
                radius: width / 2
                color: mark.cutoutColor
            }
        }
    }
}
