// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import "../../src/steamzero/ui/qml"

Main {
    id: window
    visible: true
    width: 1280
    height: 800
    property int captureIndex: 0
    readonly property var captures: [
        {"width": 949, "height": 593,
         "path": "/tmp/steamzero-responsive-949x593-shell.png"},
        {"width": 1280, "height": 800,
         "path": "/tmp/steamzero-responsive-1280x800-shell.png"},
        {"width": 1920, "height": 1080,
         "path": "/tmp/steamzero-responsive-1920x1080-shell.png"},
        {"width": 2560, "height": 1080,
         "path": "/tmp/steamzero-responsive-2560x1080-shell.png"}
    ]

    function prepareCapture() {
        if (captureIndex >= captures.length) {
            Qt.exit(0)
            return
        }
        width = captures[captureIndex].width
        height = captures[captureIndex].height
        captureTimer.restart()
    }

    Timer {
        id: captureTimer
        interval: 700
        onTriggered: window.responsiveShell.grabToImage(function(result) {
            if (!result.saveToFile(window.captures[window.captureIndex].path)) {
                Qt.exit(1)
                return
            }
            window.captureIndex += 1
            window.prepareCapture()
        })
    }

    Component.onCompleted: prepareCapture()
}
