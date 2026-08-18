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
                 "properties": {"kind": "grid", "columns": 4, "entries": 4}},
                {"id": "effect.focusedCover", "kind": "effect", "label": "focusedCover",
                 "parent": "scene", "children": ["effect.focusedCover.0"],
                 "properties": {"stack": "focusedCover", "nodes": 1, "omitted": 0}},
                {"id": "effect.focusedCover.0", "kind": "effect", "label": "glow",
                 "parent": "effect.focusedCover", "children": [],
                 "properties": {"type": "glow", "cost": "high",
                                "capability": "graphics.effect.glow"},
                 "constraints": [
                     {"code": "THEME-STUDIO-COST-001",
                      "reason": "efeito de custo alto; o inspector só observa, não executa",
                      "severity": "info"}
                 ]},
                {"id": "timeline.previewFocus", "kind": "timeline", "label": "previewFocus",
                 "parent": "scene", "children": ["timeline.previewFocus.0",
                                                "timeline.previewFocus.1"],
                 "properties": {"kind": "sequence", "repeat": 0,
                                "totalDuration": 260, "steps": 2}},
                {"id": "timeline.previewFocus.0", "kind": "timeline", "label": "normal",
                 "parent": "timeline.previewFocus", "children": [],
                 "properties": {"state": "normal", "duration": 80, "easing": "linear"}},
                {"id": "timeline.previewFocus.1", "kind": "timeline", "label": "focused",
                 "parent": "timeline.previewFocus", "children": [],
                 "properties": {"state": "focused", "duration": 180, "easing": "cubicOut"}}
            ]
        })
    }

    Timer {
        interval: 50
        running: true
        repeat: false
        onTriggered: {
            harness.check(canvas.nodeCount === 7, "canvas não recebeu a árvore")
            harness.check(canvas.select("layout.previewTitles") === true, "seleção falhou")
            harness.check(canvas.selectedKind === "layout", "inspector não acompanhou o nó")
            harness.check(canvas.select("effect.focusedCover.0") === true, "efeito não selecionou")
            harness.check(canvas.selectedKind === "effect", "inspector não acompanhou o efeito")
            harness.check(canvas.selectedConstraintCode === "THEME-STUDIO-COST-001",
                          "constraint do efeito não chegou ao inspector")
            harness.check(canvas.select("timeline.previewFocus") === true, "timeline não selecionou")
            harness.check(canvas.selectedKind === "timeline", "inspector não acompanhou a timeline")
            harness.check(canvas.selectedTimelineDuration === 260,
                          "duração materializada não chegou à faixa da timeline")
            harness.check(canvas.select("evil.qml") === false, "id inexistente não pode selecionar")
            Qt.exit(harness.failures === 0 ? 0 : 1)
        }
    }
}
