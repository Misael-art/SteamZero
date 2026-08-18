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
                },
                "loading": {
                    "kind": "progressBar",
                    "style": "segmented",
                    "progress": 0.375,
                    "segments": 8,
                    "filledSegments": 3,
                    "sweep": 0,
                    "label": "3/8"
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
            harness.check(surfaces.loadingIsProgress === true, "slot loading não virou progressBar")
            harness.check(surfaces.loadingSegments === 8 && surfaces.loadingFilled === 3,
                          "segmentos preenchidos precisam vir materializados")
            harness.check(surfaces.loadingLabel === "3/8",
                          "contador {current}/{total} não pode ser formatado no QML")
            Qt.exit(harness.failures === 0 ? 0 : 1)
        }
    }
}
