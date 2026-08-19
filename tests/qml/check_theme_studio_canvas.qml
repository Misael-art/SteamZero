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
            "budget": {
                "effectCost": 3, "recipeCost": 2, "declaredCost": 5,
                "highCostNodes": 1, "omitted": 0, "diagnostics": 0,
                "withinBudget": true, "measured": false
            },
            "nodes": [
                {"id": "scene", "kind": "scene", "label": "Cena", "parent": null,
                 "children": ["layout.previewTitles"], "properties": {"children": 1},
                 "depth": 0, "path": "Cena"},
                {"id": "layout.previewTitles", "kind": "layout", "label": "previewTitles",
                 "parent": "scene", "children": [],
                 "properties": {"kind": "grid", "columns": 4, "entries": 4},
                 "depth": 1, "path": "Cena / previewTitles"},
                {"id": "effect.focusedCover", "kind": "effect", "label": "focusedCover",
                 "parent": "scene", "children": ["effect.focusedCover.0"],
                 "properties": {"stack": "focusedCover", "nodes": 1, "omitted": 0},
                 "depth": 1, "path": "Cena / focusedCover"},
                {"id": "effect.focusedCover.0", "kind": "effect", "label": "glow",
                 "parent": "effect.focusedCover", "children": [],
                 "properties": {"type": "glow", "cost": "high",
                                "capability": "graphics.effect.glow"},
                 "depth": 2, "path": "Cena / focusedCover / glow",
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
                 "properties": {"state": "focused", "duration": 180, "easing": "cubicOut"}},
                {"id": "binding.layout.previewTitles.text", "kind": "binding",
                 "label": "previewTitles.text", "parent": "scene", "children": [],
                 "properties": {"path": "item.title", "field": "text", "source": "layout",
                                "fallback": "Sem título", "resolved": "Axiom Verge",
                                "usedFallback": false}}
            ]
        })
    }

    Timer {
        interval: 50
        running: true
        repeat: false
        onTriggered: {
            harness.check(canvas.nodeCount === 8, "canvas não recebeu a árvore")
            harness.check(canvas.select("layout.previewTitles") === true, "seleção falhou")
            harness.check(canvas.selectedKind === "layout", "inspector não acompanhou o nó")
            harness.check(canvas.select("effect.focusedCover.0") === true, "efeito não selecionou")
            harness.check(canvas.selectedKind === "effect", "inspector não acompanhou o efeito")
            harness.check(canvas.selectedPath === "Cena / focusedCover / glow",
                          "inspector precisa situar o nó na árvore, não só nomeá-lo")
            harness.check(canvas.selectedConstraintCode === "THEME-STUDIO-COST-001",
                          "constraint do efeito não chegou ao inspector")
            harness.check(canvas.select("timeline.previewFocus") === true, "timeline não selecionou")
            harness.check(canvas.selectedKind === "timeline", "inspector não acompanhou a timeline")
            harness.check(canvas.selectedTimelineDuration === 260,
                          "duração materializada não chegou à faixa da timeline")
            harness.check(canvas.declaredCost === 5, "profiler não somou o custo declarado")
            harness.check(canvas.withinBudget === true, "orçamento declarado precisa chegar ao inspector")
            harness.check(canvas.budgetMeasured === false,
                          "profiler offscreen não pode alegar medição física")
            harness.check(canvas.select("binding.layout.previewTitles.text") === true,
                          "binding assistido não selecionou")
            harness.check(canvas.selectedKind === "binding", "inspector não acompanhou o binding")
            harness.check(canvas.selectedBindingPath === "item.title",
                          "caminho allowlisted não chegou ao inspector")
            harness.check(canvas.select("evil.qml") === false, "id inexistente não pode selecionar")
            Qt.exit(harness.failures === 0 ? 0 : 1)
        }
    }
}
