// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import "../../src/steamzero/ui/qml"

Item {
    id: harness
    width: 200
    height: 80
    property int failures: 0
    function check(condition, message) {
        if (!condition) {
            failures += 1
            console.error("FAIL: " + message)
        }
    }

    SceneMotionPreview {
        id: focused
        anchors.fill: parent
        stateName: "focused"
        motion: ({
            "states": {
                "normal": {"opacity": 1, "scale": 1, "translateX": 0, "translateY": 0},
                "focused": {"opacity": 1, "scale": 1.06, "translateX": 0, "translateY": 0}
            },
            "transitions": {
                "focusIn": {"id": "focusIn", "duration": 0, "easing": "cubicOut"}
            }
        })
    }

    Timer {
        interval: 50
        running: true
        repeat: false
        onTriggered: {
            harness.check(focused.snapshotScale === 1.06, "snapshot focused não chegou ao QML")
            harness.check(focused.focusDuration === 0, "reduced motion precisa zerar a duração no plano")
            Qt.exit(harness.failures === 0 ? 0 : 1)
        }
    }
}
