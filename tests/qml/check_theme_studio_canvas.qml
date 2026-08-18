// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import "../../src/steamzero/ui/qml"

Item {
    id: harness
    width: 520
    height: 180
    property int failures: 0
    function check(condition, message) {
        if (!condition) {
            failures += 1
            console.error("FAIL: " + message)
        }
    }

    ThemeStudioCanvas {
        id: canvas
        anchors.fill: parent
        graph: ({
            "selectedId": "scene",
            "nodes": [
                {"id": "scene", "kind": "scene", "label": "Cena", "parent": null,
                 "children": ["layout.previewTitles"], "properties": {"children": 1}},
                {"id": "layout.previewTitles", "kind": "layout", "label": "previewTitles",
                 "parent": "scene", "children": [],
                 "properties": {"kind": "grid", "columns": 4, "entries": 4}}
            ]
        })
    }

    Timer {
        interval: 50
        running: true
        repeat: false
        onTriggered: {
            harness.check(canvas.nodeCount === 2, "canvas não recebeu a árvore")
            harness.check(canvas.select("layout.previewTitles") === true, "seleção falhou")
            harness.check(canvas.selectedKind === "layout", "inspector não acompanhou o nó")
            harness.check(canvas.select("evil.qml") === false, "id inexistente não pode selecionar")
            Qt.exit(harness.failures === 0 ? 0 : 1)
        }
    }
}
