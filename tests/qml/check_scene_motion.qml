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
            },
            "presence": {
                "chrome": {"layer": "chrome", "state": "idle", "opacity": 0.25, "fadeDuration": 0}
            }
        })
    }

    SceneMotionPreview {
        id: withoutPresence
        anchors.fill: parent
        stateName: "normal"
        motion: ({
            "states": {
                "normal": {"opacity": 1, "scale": 1, "translateX": 0, "translateY": 0}
            },
            "transitions": {},
            "presence": {}
        })
    }

    Timer {
        interval: 50
        running: true
        repeat: false
        onTriggered: {
            harness.check(focused.snapshotScale === 1.06, "snapshot focused não chegou ao QML")
            harness.check(focused.focusDuration === 0, "reduced motion precisa zerar a duração no plano")
            harness.check(focused.chromeOpacity === 0.25 && focused.interactionState === "idle",
                          "transparência por ociosidade precisa vir resolvida")
            harness.check(focused.chromeFadeDuration === 0,
                          "duração do fade não pode ser inventada no QML")
            const chrome = focused.children[1]
            harness.check(chrome.objectName === "chromeLayer" && chrome.opacity === 0.25,
                          "camada de chrome não aplicou a opacidade materializada")
            harness.check(withoutPresence.chromeOpacity === 1,
                          "sem presence a interface fica opaca, nunca invisível")
            Qt.exit(harness.failures === 0 ? 0 : 1)
        }
    }
}
