// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick

Item {
    id: root
    property string glyph: "overview"
    property color iconColor: "#9eabba"
    property real strokeWidth: 2

    implicitWidth: 28
    implicitHeight: 28
    Accessible.ignored: true

    onGlyphChanged: iconCanvas.requestPaint()
    onIconColorChanged: iconCanvas.requestPaint()
    onStrokeWidthChanged: iconCanvas.requestPaint()

    Canvas {
        id: iconCanvas
        anchors.fill: parent
        antialiasing: true

        function line(context, x1, y1, x2, y2) {
            context.moveTo(x1, y1)
            context.lineTo(x2, y2)
        }

        onPaint: {
            const context = getContext("2d")
            const scaleX = width / 28
            const scaleY = height / 28
            context.setTransform(1, 0, 0, 1, 0, 0)
            context.clearRect(0, 0, width, height)
            context.setTransform(scaleX, 0, 0, scaleY, 0, 0)
            context.strokeStyle = root.iconColor
            context.fillStyle = root.iconColor
            context.lineWidth = root.strokeWidth
            context.lineCap = "round"
            context.lineJoin = "round"
            context.beginPath()

            if (root.glyph === "overview") {
                context.strokeRect(3.5, 3.5, 8, 8)
                context.strokeRect(16.5, 3.5, 8, 8)
                context.strokeRect(3.5, 16.5, 8, 8)
                context.strokeRect(16.5, 16.5, 8, 8)
            } else if (root.glyph === "emulators") {
                context.moveTo(8, 9)
                context.bezierCurveTo(5, 9, 3.5, 12, 3, 18)
                context.bezierCurveTo(2.6, 22, 5.5, 24, 8, 20.5)
                context.lineTo(10, 18)
                context.lineTo(18, 18)
                context.lineTo(20, 20.5)
                context.bezierCurveTo(22.5, 24, 25.4, 22, 25, 18)
                context.bezierCurveTo(24.5, 12, 23, 9, 20, 9)
                context.closePath()
                line(context, 8, 12, 8, 16)
                line(context, 6, 14, 10, 14)
                context.moveTo(19, 13)
                context.arc(19, 13, 1, 0, Math.PI * 2)
                context.moveTo(22, 16)
                context.arc(22, 16, 1, 0, Math.PI * 2)
            } else if (root.glyph === "steam") {
                context.arc(14, 14, 10.5, 0, Math.PI * 2)
                context.moveTo(7, 19)
                context.lineTo(11.5, 21)
                context.arc(14, 21, 2.8, 0, Math.PI * 2)
                context.moveTo(16.5, 19.5)
                context.lineTo(20, 12)
                context.arc(21, 9.5, 3.2, 0, Math.PI * 2)
            } else if (root.glyph === "profiles") {
                line(context, 4, 7, 24, 7)
                line(context, 4, 14, 24, 14)
                line(context, 4, 21, 24, 21)
                context.moveTo(10, 7)
                context.arc(10, 7, 2.3, 0, Math.PI * 2)
                context.moveTo(18, 14)
                context.arc(18, 14, 2.3, 0, Math.PI * 2)
                context.moveTo(12, 21)
                context.arc(12, 21, 2.3, 0, Math.PI * 2)
            } else if (root.glyph === "sync") {
                context.arc(14, 14, 8.5, Math.PI * 0.15, Math.PI * 1.05)
                context.moveTo(6, 17)
                context.lineTo(5, 10)
                context.lineTo(11.5, 11.5)
                context.moveTo(22, 11)
                context.arc(14, 14, 8.5, Math.PI * 1.15, Math.PI * 2.05)
                context.moveTo(22, 11)
                context.lineTo(23, 18)
                context.lineTo(16.5, 16.5)
            } else {
                context.arc(14, 14, 5, 0, Math.PI * 2)
                for (let index = 0; index < 8; index++) {
                    const angle = index * Math.PI / 4
                    line(context, 14 + Math.cos(angle) * 7,
                         14 + Math.sin(angle) * 7,
                         14 + Math.cos(angle) * 11,
                         14 + Math.sin(angle) * 11)
                }
                context.moveTo(14, 14)
                context.arc(14, 14, 1.5, 0, Math.PI * 2)
            }
            context.stroke()
        }
    }
}
