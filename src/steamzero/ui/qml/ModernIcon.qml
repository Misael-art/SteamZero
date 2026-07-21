// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick

Canvas {
    id: icon

    property string iconName: "dialog-information"
    property color iconColor: "#9eabba"
    property real strokeWidth: Math.max(1.6, width / 12)

    implicitWidth: 22
    implicitHeight: 22
    Accessible.role: Accessible.Graphic
    Accessible.name: iconName

    onIconNameChanged: requestPaint()
    onIconColorChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()

    function roundedRect(context, x, y, width, height, radius) {
        context.beginPath()
        context.moveTo(x + radius, y)
        context.lineTo(x + width - radius, y)
        context.quadraticCurveTo(x + width, y, x + width, y + radius)
        context.lineTo(x + width, y + height - radius)
        context.quadraticCurveTo(x + width, y + height, x + width - radius, y + height)
        context.lineTo(x + radius, y + height)
        context.quadraticCurveTo(x, y + height, x, y + height - radius)
        context.lineTo(x, y + radius)
        context.quadraticCurveTo(x, y, x + radius, y)
        context.stroke()
    }

    onPaint: {
        const context = getContext("2d")
        const w = width
        const h = height
        const cx = w / 2
        const cy = h / 2
        context.reset()
        context.clearRect(0, 0, w, h)
        context.strokeStyle = iconColor
        context.fillStyle = iconColor
        context.lineWidth = strokeWidth
        context.lineCap = "round"
        context.lineJoin = "round"

        if (iconName === "view-dashboard") {
            context.strokeRect(w * 0.12, h * 0.14, w * 0.29, h * 0.29)
            context.strokeRect(w * 0.58, h * 0.14, w * 0.29, h * 0.29)
            context.strokeRect(w * 0.12, h * 0.57, w * 0.29, h * 0.29)
            context.strokeRect(w * 0.58, h * 0.57, w * 0.29, h * 0.29)
        } else if (iconName === "document-encrypt") {
            roundedRect(context, w * 0.2, h * 0.43, w * 0.6, h * 0.43, w * 0.08)
            context.beginPath()
            context.arc(cx, h * 0.42, w * 0.22, Math.PI, 0)
            context.stroke()
            context.beginPath()
            context.arc(cx, h * 0.63, w * 0.04, 0, Math.PI * 2)
            context.fill()
            context.fillRect(cx - w * 0.025, h * 0.64, w * 0.05, h * 0.12)
        } else if (iconName === "download" || iconName === "system-software-update") {
            context.beginPath()
            context.moveTo(cx, h * 0.12)
            context.lineTo(cx, h * 0.62)
            context.moveTo(w * 0.3, h * 0.45)
            context.lineTo(cx, h * 0.67)
            context.lineTo(w * 0.7, h * 0.45)
            context.moveTo(w * 0.18, h * 0.84)
            context.lineTo(w * 0.82, h * 0.84)
            context.stroke()
        } else if (iconName === "video-display") {
            roundedRect(context, w * 0.1, h * 0.15, w * 0.8, h * 0.57, w * 0.06)
            context.beginPath()
            context.moveTo(cx, h * 0.72)
            context.lineTo(cx, h * 0.86)
            context.moveTo(w * 0.3, h * 0.87)
            context.lineTo(w * 0.7, h * 0.87)
            context.stroke()
        } else if (iconName === "input-gaming" || iconName === "applications-games"
                   || iconName === "preferences-desktop-peripherals") {
            context.beginPath()
            context.moveTo(w * 0.28, h * 0.37)
            context.quadraticCurveTo(w * 0.12, h * 0.38, w * 0.09, h * 0.72)
            context.quadraticCurveTo(w * 0.08, h * 0.9, w * 0.25, h * 0.78)
            context.lineTo(w * 0.39, h * 0.65)
            context.lineTo(w * 0.61, h * 0.65)
            context.lineTo(w * 0.75, h * 0.78)
            context.quadraticCurveTo(w * 0.92, h * 0.9, w * 0.91, h * 0.72)
            context.quadraticCurveTo(w * 0.88, h * 0.38, w * 0.72, h * 0.37)
            context.closePath()
            context.stroke()
            context.beginPath()
            context.moveTo(w * 0.25, h * 0.55)
            context.lineTo(w * 0.39, h * 0.55)
            context.moveTo(w * 0.32, h * 0.48)
            context.lineTo(w * 0.32, h * 0.62)
            context.stroke()
            context.beginPath()
            context.arc(w * 0.7, h * 0.51, w * 0.035, 0, Math.PI * 2)
            context.arc(w * 0.79, h * 0.59, w * 0.035, 0, Math.PI * 2)
            context.fill()
        } else if (iconName === "document-save") {
            roundedRect(context, w * 0.16, h * 0.1, w * 0.68, h * 0.8, w * 0.05)
            context.strokeRect(w * 0.28, h * 0.12, w * 0.37, h * 0.26)
            context.strokeRect(w * 0.28, h * 0.58, w * 0.44, h * 0.3)
        } else if (iconName === "applications-graphics" || iconName === "speedometer") {
            context.beginPath()
            context.arc(cx, cy, w * 0.34, Math.PI * 0.85, Math.PI * 2.15)
            context.stroke()
            context.beginPath()
            context.moveTo(cx, cy)
            context.lineTo(w * 0.72, h * 0.3)
            context.stroke()
            context.beginPath()
            context.arc(cx, cy, w * 0.06, 0, Math.PI * 2)
            context.fill()
        } else if (iconName === "image-x-generic") {
            roundedRect(context, w * 0.1, h * 0.13, w * 0.8, h * 0.72, w * 0.06)
            context.beginPath()
            context.arc(w * 0.67, h * 0.34, w * 0.08, 0, Math.PI * 2)
            context.stroke()
            context.beginPath()
            context.moveTo(w * 0.18, h * 0.72)
            context.lineTo(w * 0.39, h * 0.49)
            context.lineTo(w * 0.53, h * 0.63)
            context.lineTo(w * 0.63, h * 0.53)
            context.lineTo(w * 0.82, h * 0.73)
            context.stroke()
        } else if (iconName === "drive-harddisk") {
            context.beginPath()
            context.ellipse(cx, h * 0.24, w * 0.34, h * 0.13)
            context.stroke()
            context.beginPath()
            context.moveTo(w * 0.16, h * 0.24)
            context.lineTo(w * 0.16, h * 0.72)
            context.moveTo(w * 0.84, h * 0.24)
            context.lineTo(w * 0.84, h * 0.72)
            context.stroke()
            context.beginPath()
            context.ellipse(cx, h * 0.72, w * 0.34, h * 0.13)
            context.stroke()
        } else if (iconName === "configure") {
            const rows = [0.25, 0.5, 0.75]
            const knobs = [0.36, 0.68, 0.45]
            for (let i = 0; i < rows.length; i++) {
                context.beginPath()
                context.moveTo(w * 0.12, h * rows[i])
                context.lineTo(w * 0.88, h * rows[i])
                context.stroke()
                context.beginPath()
                context.arc(w * knobs[i], h * rows[i], w * 0.08, 0, Math.PI * 2)
                context.fill()
            }
        } else if (iconName === "globe") {
            context.beginPath()
            context.arc(cx, cy, w * 0.37, 0, Math.PI * 2)
            context.moveTo(w * 0.13, cy)
            context.lineTo(w * 0.87, cy)
            context.moveTo(cx, h * 0.13)
            context.bezierCurveTo(w * 0.32, h * 0.32, w * 0.32, h * 0.68, cx, h * 0.87)
            context.moveTo(cx, h * 0.13)
            context.bezierCurveTo(w * 0.68, h * 0.32, w * 0.68, h * 0.68, cx, h * 0.87)
            context.stroke()
        } else if (iconName === "media-playback-start") {
            context.beginPath()
            context.moveTo(w * 0.28, h * 0.16)
            context.lineTo(w * 0.82, cy)
            context.lineTo(w * 0.28, h * 0.84)
            context.closePath()
            context.stroke()
        } else if (iconName === "computer-laptop") {
            roundedRect(context, w * 0.18, h * 0.14, w * 0.64, h * 0.5, w * 0.04)
            context.beginPath()
            context.moveTo(w * 0.08, h * 0.78)
            context.lineTo(w * 0.92, h * 0.78)
            context.lineTo(w * 0.8, h * 0.88)
            context.lineTo(w * 0.2, h * 0.88)
            context.closePath()
            context.stroke()
        } else if (iconName === "dialog-ok-apply") {
            context.beginPath()
            context.arc(cx, cy, w * 0.38, 0, Math.PI * 2)
            context.moveTo(w * 0.29, h * 0.51)
            context.lineTo(w * 0.44, h * 0.66)
            context.lineTo(w * 0.73, h * 0.34)
            context.stroke()
        } else if (iconName === "dialog-warning") {
            context.beginPath()
            context.moveTo(cx, h * 0.1)
            context.lineTo(w * 0.91, h * 0.84)
            context.lineTo(w * 0.09, h * 0.84)
            context.closePath()
            context.stroke()
            context.beginPath()
            context.moveTo(cx, h * 0.35)
            context.lineTo(cx, h * 0.59)
            context.stroke()
            context.beginPath()
            context.arc(cx, h * 0.71, w * 0.035, 0, Math.PI * 2)
            context.fill()
        } else {
            context.beginPath()
            context.arc(cx, cy, w * 0.37, 0, Math.PI * 2)
            context.stroke()
            context.beginPath()
            context.arc(cx, h * 0.31, w * 0.035, 0, Math.PI * 2)
            context.fill()
            context.beginPath()
            context.moveTo(cx, h * 0.45)
            context.lineTo(cx, h * 0.72)
            context.stroke()
        }
    }
}
