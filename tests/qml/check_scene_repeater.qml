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
        id: covers
        layout: ({
            "id": "previewCoverFlow",
            "kind": "coverFlow",
            "columns": 1,
            "entries": [{
                "kind": "text", "id": "cover-0", "text": "Axiom Verge",
                "x": 124, "y": 28, "width": 80, "height": 24,
                "visible": true, "opacity": 0.85, "scale": 0.9, "z": 31,
                "rotationY": -28, "color": "#f2f6fb", "fontFamily": "",
                "fontPixelSize": 14, "fontWeight": 400, "fontItalic": false,
                "horizontalAlignment": "AlignLeft", "verticalAlignment": "AlignTop"
            }, {
                "kind": "text", "id": "cover-1", "text": "Celeste",
                "x": 160, "y": 28, "width": 80, "height": 24,
                "visible": true, "opacity": 1, "scale": 1, "z": 32,
                "rotationY": 0, "color": "#f2f6fb", "fontFamily": "",
                "fontPixelSize": 14, "fontWeight": 400, "fontItalic": false,
                "horizontalAlignment": "AlignLeft", "verticalAlignment": "AlignTop"
            }]
        })
    }

    SceneRepeater {
        id: wheel
        layout: ({
            "id": "previewWheel",
            "kind": "wheel",
            "columns": 1,
            "entries": [{
                "kind": "text", "id": "wheel-0", "text": "Axiom Verge",
                "x": 70, "y": 24, "width": 80, "height": 24,
                "visible": true, "opacity": 0.82, "scale": 0.92, "z": 31,
                "color": "#f2f6fb", "fontFamily": "", "fontPixelSize": 14,
                "fontWeight": 400, "fontItalic": false,
                "horizontalAlignment": "AlignLeft", "verticalAlignment": "AlignTop"
            }, {
                "kind": "text", "id": "wheel-1", "text": "Celeste",
                "x": 160, "y": 24, "width": 80, "height": 24,
                "visible": true, "opacity": 1, "scale": 1, "z": 32,
                "color": "#f2f6fb", "fontFamily": "", "fontPixelSize": 14,
                "fontWeight": 400, "fontItalic": false,
                "horizontalAlignment": "AlignLeft", "verticalAlignment": "AlignTop"
            }]
        })
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
            harness.check(covers.entryCount === 2, "cover flow não recebeu duas entradas")
            const cover = covers.entryAt(1)
            const neighbor = covers.entryAt(0)
            harness.check(cover !== null && neighbor !== null, "nós do cover flow não instanciaram")
            if (cover !== null) {
                harness.check(cover.text === "Celeste", "capa selecionada não chegou ao QML")
                harness.check(cover.z === 32 && cover.scale === 1,
                              "offset converter do cover flow não pode ser recalculado no QML")
            }
            if (neighbor !== null) {
                harness.check(neighbor.x === 124 && neighbor.scale === 0.9,
                              "vizinho do cover flow precisa usar overlap materializado")
            }
            harness.check(wheel.entryCount === 2, "wheel não recebeu duas entradas")
            const focused = wheel.entryAt(1)
            const side = wheel.entryAt(0)
            harness.check(focused !== null && side !== null, "nós do wheel não instanciaram")
            if (focused !== null) {
                harness.check(focused.text === "Celeste", "item selecionado não chegou ao QML")
                harness.check(focused.scale === 1 && focused.z === 32,
                              "offset converter não pode ser recalculado no QML")
            }
            if (side !== null) {
                harness.check(side.x === 70 && side.scale === 0.92,
                              "vizinho do wheel precisa usar escala materializada")
            }
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
