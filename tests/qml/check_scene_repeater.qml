// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import "../../src/steamzero/ui/qml"

Item {
    id: harness
    width: 480
    height: 120

    property int failures: 0
    function check(condition, message) {
        if (!condition) {
            failures += 1
            console.error("FAIL: " + message)
        }
    }

    SceneRepeater {
        id: cards
        layout: ({
            "id": "previewTitles",
            "kind": "grid",
            "columns": 2,
            "entries": [{
                "kind": "text", "id": "title-0", "text": "Axiom Verge",
                "x": 0, "y": 0, "width": 180, "height": 32,
                "visible": true, "opacity": 1, "color": "#f2f6fb",
                "fontFamily": "", "fontPixelSize": 16, "fontWeight": 400,
                "fontItalic": false, "horizontalAlignment": "AlignLeft",
                "verticalAlignment": "AlignTop"
            }, {
                "kind": "text", "id": "title-1", "text": "Celeste",
                "x": 192, "y": 0, "width": 180, "height": 32,
                "visible": true, "opacity": 1, "color": "#22d3ee",
                "fontFamily": "", "fontPixelSize": 16, "fontWeight": 600,
                "fontItalic": false, "horizontalAlignment": "AlignLeft",
                "verticalAlignment": "AlignTop"
            }]
        })
    }

    Timer {
        interval: 50
        running: true
        repeat: false
        onTriggered: {
            harness.check(cards.entryCount === 2, "repetidor não recebeu duas entradas")
            const first = cards.entryAt(0)
            const second = cards.entryAt(1)
            harness.check(first !== null && second !== null, "nós finais não instanciaram")
            if (first !== null) {
                harness.check(first.text === "Axiom Verge", "texto final não chegou ao QML")
                harness.check(first.x === 0 && first.y === 0, "geometria não pode ser recalculada no QML")
            }
            if (second !== null) {
                harness.check(second.text === "Celeste", "segundo binding materializado não chegou")
                harness.check(second.x === 192 && second.color.toString().toLowerCase().indexOf("22d3ee") !== -1,
                              "estilo materializado não chegou")
            }
            Qt.exit(harness.failures === 0 ? 0 : 1)
        }
    }
}
