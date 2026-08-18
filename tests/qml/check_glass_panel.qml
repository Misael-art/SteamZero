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

    GlassPanel {
        id: glass
        anchors.fill: parent
        panel: ({
            "id": "previewCard",
            "tint": "#22d3ee",
            "blur": 24,
            "tintOpacity": 0.42,
            "borderColor": "#ffffff",
            "borderOpacity": 0.28,
            "highlightOpacity": 0.16,
            "shadowOpacity": 0.32,
            "sampleScale": 0.5,
            "blurEnabled": false,
            "fallback": "flat"
        })
    }

    Timer {
        interval: 50
        running: true
        repeat: false
        onTriggered: {
            harness.check(glass.blurEnabled === false, "fallback sem blur precisa permanecer visível")
            harness.check(glass.tint.toLowerCase().indexOf("22d3ee") !== -1, "tint extraído não chegou")
            harness.check(glass.fallback === "flat", "fallback flat precisa ser explícito")
            Qt.exit(harness.failures === 0 ? 0 : 1)
        }
    }
}
