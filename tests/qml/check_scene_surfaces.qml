// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import "../../src/steamzero/ui/qml"

Item {
    id: harness
    width: 240
    height: 80
    property int failures: 0
    function check(condition, message) {
        if (!condition) {
            failures += 1
            console.error("FAIL: " + message)
        }
    }

    SceneSurfacePreview {
        id: surfaces
        anchors.fill: parent
        surfaces: ({
            "slots": {
                "saveStates": {
                    "kind": "saveGallery",
                    "entries": [
                        {"title": "Auto", "thumbnailFallback": false},
                        {"title": "Slot 2", "thumbnailFallback": true}
                    ]
                },
                "osd": {
                    "kind": "osd",
                    "items": ["volume", "pause"],
                    "progress": 0.4,
                    "criticalVisible": false
                }
            }
        })
    }

    Timer {
        interval: 50
        running: true
        repeat: false
        onTriggered: {
            harness.check(surfaces.saveCount === 2, "galeria não recebeu dois slots")
            harness.check(surfaces.thumbnailFallback === true, "placeholder de captura ausente")
            harness.check(surfaces.progress === 0.4, "progresso do OSD não chegou")
            harness.check(surfaces.criticalVisible === false, "erro crítico não pode ser inventado")
            Qt.exit(harness.failures === 0 ? 0 : 1)
        }
    }
}
