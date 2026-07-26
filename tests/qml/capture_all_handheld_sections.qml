// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import "../../src/steamzero/ui/qml"

Main {
    id: window
    visible: true
    width: 949
    height: 593
    property int captureIndex: 0
    readonly property var sections: [
        "overview", "emulation", "steam", "profiles", "saves-sync",
        "transmission", "system"
    ]
    readonly property var captures: [
        {"width": 949, "height": 593, "section": 0},
        {"width": 949, "height": 593, "section": 1},
        {"width": 949, "height": 593, "section": 2},
        {"width": 949, "height": 593, "section": 3},
        {"width": 949, "height": 593, "section": 4},
        {"width": 949, "height": 593, "section": 5},
        {"width": 949, "height": 593, "section": 6},
        {"width": 1280, "height": 800, "section": 0},
        {"width": 1280, "height": 800, "section": 1},
        {"width": 1280, "height": 800, "section": 2},
        {"width": 1280, "height": 800, "section": 3},
        {"width": 1280, "height": 800, "section": 4},
        {"width": 1280, "height": 800, "section": 5},
        {"width": 1280, "height": 800, "section": 6}
    ]

    function prepareCapture() {
        if (captureIndex >= captures.length) {
            Qt.exit(0)
            return
        }
        const capture = captures[captureIndex]
        width = capture.width
        height = capture.height
        sectionIndex = capture.section
        captureTimer.restart()
    }

    Timer {
        id: captureTimer
        interval: 450
        onTriggered: window.responsiveShell.grabToImage(function(result) {
            const capture = window.captures[window.captureIndex]
            const name = "/tmp/steamzero-" + capture.width + "x" + capture.height
                + "-" + window.sections[capture.section] + ".png"
            if (!result.saveToFile(name)) {
                Qt.exit(1)
                return
            }
            window.captureIndex += 1
            window.prepareCapture()
        })
    }

    Component.onCompleted: prepareCapture()
}
