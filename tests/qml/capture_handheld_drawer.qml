// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import "../../src/steamzero/ui/qml"

Main {
    id: window
    visible: true
    width: 949
    height: 593

    Timer {
        id: openTimer
        interval: 100
        running: true
        onTriggered: {
            window.responsiveDrawer.open()
            captureTimer.start()
        }
    }

    Timer {
        id: captureTimer
        interval: window.motionDuration + 400
        onTriggered: window.responsiveDrawer.contentItem.grabToImage(function(result) {
            Qt.exit(result.saveToFile("/tmp/steamzero-responsive-949x593-drawer.png") ? 0 : 1)
        })
    }
}
