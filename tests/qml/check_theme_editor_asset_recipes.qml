// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Window
import "../../src/steamzero/ui/qml"

Window {
    id: harness
    visible: true
    width: 1100
    height: 720
    color: "#071019"
    property int failures: 0

    function check(condition, message) {
        if (!condition) {
            failures += 1
            console.error("FAIL: " + message)
        }
    }

    ThemeEditorPanel {
        id: panel
        anchors.fill: parent
        compactLayout: false
        request: function(_method, _path, _payload, callback, _errorCallback) {
            callback({"themes": []})
        }
    }

    Component.onCompleted: {
        const manifest = {
            "id": "org.steamzero.asset-recipes-demo",
            "name": "Theme Engine — asset único",
            "version": "1.0.0",
            "author": "SteamZero contributors",
            "license": "CC0-1.0"
        }
        const recipe = function(nodes) {
            return {
                "source": "logo", "nodes": nodes, "tier": "cinematic",
                "fallback": "source", "reducedMotionSafe": true
            }
        }
        const preview = {
            "schemaVersion": 1,
            "themeId": manifest.id,
            "themeVersion": manifest.version,
            "highContrast": false,
            "reducedMotion": true,
            "resolved": {
                "color": {
                    "background": "#0b1020", "surface": "#141a2e",
                    "surfaceRaised": "#1c2440", "border": "#262f4d",
                    "text": "#e8ecf7", "textMuted": "#8b93a8",
                    "accent": "#22d3ee", "success": "#59d35d",
                    "warning": "#ff9f1a", "danger": "#ff6b73"
                }
            },
            "assetRecipes": {
                "original": recipe([]),
                "colored": recipe([{
                    "type": "recolor", "parameters": {"color": "#22d3ee", "opacity": 1},
                    "capability": "graphics.asset.recolor", "cost": "low",
                    "fallback": "source"
                }]),
                "outlineThin": recipe([{
                    "type": "outline", "parameters": {
                        "width": 2, "color": "#ffffff", "opacity": 1,
                        "position": "outer", "mask": "alpha"
                    },
                    "capability": "graphics.asset.outline.outer", "cost": "medium",
                    "fallback": "outer"
                }]),
                "outlineThick": recipe([{
                    "type": "outline", "parameters": {
                        "width": 8, "color": "#000000", "opacity": 1,
                        "position": "outer", "mask": "alpha"
                    },
                    "capability": "graphics.asset.outline.outer", "cost": "medium",
                    "fallback": "outer"
                }])
            },
            "assetRecipeDiagnostics": [],
            "sceneLayoutPreview": {
                "layouts": {
                    "previewTitles": {
                        "id": "previewTitles", "kind": "grid", "columns": 2,
                        "entries": [{
                            "kind": "text", "id": "preview-title-0", "text": "Axiom Verge",
                            "x": 0, "y": 0, "width": 138, "height": 32,
                            "visible": true, "opacity": 1, "color": "#f2f6fb",
                            "fontFamily": "", "fontPixelSize": 14, "fontWeight": 400,
                            "fontItalic": false, "horizontalAlignment": "AlignLeft",
                            "verticalAlignment": "AlignTop"
                        }, {
                            "kind": "text", "id": "preview-title-1", "text": "Celeste",
                            "x": 146, "y": 0, "width": 138, "height": 32,
                            "visible": true, "opacity": 1, "color": "#f2f6fb",
                            "fontFamily": "", "fontPixelSize": 14, "fontWeight": 400,
                            "fontItalic": false, "horizontalAlignment": "AlignLeft",
                            "verticalAlignment": "AlignTop"
                        }]
                    }
                }, "diagnostics": []
            },
            "dynamicPalette": {
                "swatches": {
                    "dominant": "#132833", "vibrant": "#22d3ee", "lightVibrant": "#7dd3fc",
                    "darkVibrant": "#0e7490", "muted": "#64748b", "lightMuted": "#94a3b8",
                    "darkMuted": "#334155", "complementary": "#ee3d22", "accent": "#22d3ee",
                    "background": "#071019", "contrastText": "#f2f6fb"
                },
                "cacheKey": "preview", "algorithm": "medianCut", "diagnostics": []
            },
            "glassPreview": {
                "panels": {
                    "previewCard": {
                        "id": "previewCard", "tint": "#22d3ee", "blur": 24,
                        "tintOpacity": 0.42, "borderColor": "#ffffff", "borderOpacity": 0.28,
                        "highlightOpacity": 0.16, "shadowOpacity": 0.32, "sampleScale": 0.5,
                        "blurEnabled": true, "fallback": "none"
                    }
                }, "diagnostics": []
            },
            "sceneMotionPreview": {
                "states": {
                    "normal": {"opacity": 1, "scale": 1, "translateX": 0, "translateY": 0},
                    "focused": {"opacity": 1, "scale": 1.06, "translateX": 0, "translateY": 0}
                },
                "transitions": {
                    "focusIn": {
                        "id": "focusIn", "from": "normal", "to": "focused",
                        "duration": 180, "easing": "cubicOut", "essential": false
                    }
                },
                "timelines": {
                    "previewFocus": {
                        "id": "previewFocus", "kind": "sequence", "repeat": 0,
                        "totalDuration": 260,
                        "steps": [
                            {"state": "normal", "duration": 0, "easing": "linear"},
                            {"state": "focused", "duration": 180, "easing": "cubicOut"},
                            {"state": "focused", "duration": 80, "easing": "linear"}
                        ]
                    }
                },
                "diagnostics": []
            },
            "sceneSurfacePreview": {
                "slots": {
                    "saveStates": {
                        "slot": "saveStates", "kind": "saveGallery",
                        "entries": [
                            {"title": "Auto", "timestamp": "2026-08-17T12:00:00Z",
                             "playtime": "1h 12m", "compatible": true, "thumbnailFallback": false},
                            {"title": "Slot 2", "timestamp": "", "playtime": "",
                             "compatible": false, "thumbnailFallback": true}
                        ],
                        "items": [], "progress": 0, "criticalVisible": false, "success": false
                    },
                    "osd": {
                        "slot": "osd", "kind": "osd", "entries": [],
                        "items": ["volume", "mute", "pause", "saveState"],
                        "progress": 0.4, "criticalVisible": false, "success": false
                    }
                },
                "diagnostics": []
            },
            "studioGraph": {
                "selectedId": "scene",
                "budget": {
                    "effectCost": 3, "recipeCost": 2, "declaredCost": 5,
                    "highCostNodes": 1, "omitted": 0, "diagnostics": 0,
                    "withinBudget": true, "measured": false
                },
                "nodes": [
                    {"id": "scene", "kind": "scene", "label": "Cena", "parent": null,
                     "children": ["layout.previewTitles", "surface.saveStates",
                                  "motion.focusIn", "timeline.previewFocus",
                                  "effect.focusedCover"],
                     "properties": {"children": 5}},
                    {"id": "layout.previewTitles", "kind": "layout", "label": "previewTitles",
                     "parent": "scene", "children": [],
                     "properties": {"kind": "grid", "columns": 4, "entries": 2}},
                    {"id": "surface.saveStates", "kind": "surface", "label": "saveStates",
                     "parent": "scene", "children": [],
                     "properties": {"kind": "saveGallery", "entries": 2, "criticalVisible": false}},
                    {"id": "motion.focusIn", "kind": "motion", "label": "focusIn",
                     "parent": "scene", "children": [],
                     "properties": {"from": "normal", "to": "focused", "duration": 180, "easing": "cubicOut"}},
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
                     "parent": "scene", "children": ["timeline.previewFocus.0"],
                     "properties": {"kind": "sequence", "repeat": 0,
                                    "totalDuration": 260, "steps": 1}},
                    {"id": "timeline.previewFocus.0", "kind": "timeline", "label": "focused",
                     "parent": "timeline.previewFocus", "children": [],
                     "properties": {"state": "focused", "duration": 180, "easing": "cubicOut"}}
                ]
            }
        }
        panel._openEditor("edit-asset-recipes", manifest, preview)
    }

    Timer {
        interval: 250
        running: true
        repeat: false
        onTriggered: {
            check(panel.assetRecipeDemoActive,
                  "preview de receitas precisa ser consumido pelo editor real")
            check(panel.assetRecipePreviewReady,
                  "fixture empacotada precisa chegar a Image.Ready no editor")
            check(panel.assetRecipePreviewDecodeCount === 1,
                  "preview integrado precisa decodificar a fonte uma vez")
            check(panel._previewBridge.assetRecipes.outlineThin.nodes[0].parameters.mask === "alpha",
                  "receita alpha precisa atravessar ThemeBridge")
            check(panel.sceneLayoutPreviewActive,
                  "preview de layout materializado precisa chegar ao editor real")
            check(panel.sceneLayoutPreviewEntryCount === 2,
                  "repetidor integrado precisa consumir os nós finais")
            check(panel.sceneLayoutPreviewEntryAt(1).text === "Celeste",
                  "binding materializado não chegou ao consumidor real")
            check(panel.dynamicPalettePreviewActive,
                  "paleta extraída precisa chegar ao editor real")
            check(panel.dynamicPalettePreview.accent.toString().toLowerCase().indexOf("22d3ee") !== -1,
                  "swatch extraído não chegou ao consumidor")
            check(panel.glassPreviewActive && panel.glassPreview.tint.toString().toLowerCase().indexOf("22d3ee") !== -1,
                  "vidro materializado não chegou ao consumidor real")
            check(panel.sceneMotionPreviewActive,
                  "plano de estados precisa chegar ao editor real")
            check(panel.sceneMotionFocusDuration === 180,
                  "transição materializada não chegou ao consumidor")
            check(panel.sceneMotionPreview.states.focused.scale === 1.06,
                  "snapshot focused não foi aplicado")
            check(panel.sceneSurfacePreviewActive,
                  "contratos de save/OSD precisam chegar ao editor real")
            check(panel.sceneSurfaceSaveCount === 2,
                  "galeria materializada não chegou ao consumidor")
            check(panel.sceneSurfaceThumbnailFallback,
                  "slot sem captura precisa degradar com placeholder")
            check(panel.sceneSurfaceCriticalVisible === false,
                  "OSD não pode inventar erro crítico")
            check(panel.studioGraphActive,
                  "grafo do Studio precisa chegar ao editor real")
            check(panel.studioGraphNodeCount >= 4,
                  "árvore do Studio precisa listar a cena e os nós da engine")
            check(panel.studioGraphSelect("layout.previewTitles") === true,
                  "seleção da árvore precisa apontar para o layout materializado")
            check(panel.studioGraphSelectedId === "layout.previewTitles",
                  "inspector precisa acompanhar o nó selecionado")
            check(panel.studioGraphSelect("effect.focusedCover.0") === true,
                  "grafo de efeitos precisa ser selecionável no editor real")
            check(panel.studioGraphSelectedKind === "effect",
                  "inspector precisa identificar o node de efeito")
            check(panel.studioGraphConstraintCode === "THEME-STUDIO-COST-001",
                  "constraint do efeito precisa chegar ao inspector")
            check(panel.studioGraphSelect("timeline.previewFocus") === true,
                  "timeline materializada precisa ser selecionável no editor real")
            check(panel.studioGraphSelectedKind === "timeline",
                  "inspector precisa identificar o node de timeline")
            check(panel.studioGraphTimelineDuration === 260,
                  "duração da timeline precisa chegar ao inspector")
            check(panel.studioGraphDeclaredCost === 5,
                  "profiler declarado precisa chegar ao editor real")
            check(panel.studioGraphWithinBudget === true,
                  "orçamento declarado precisa chegar ao inspector")
            check(panel.studioGraphBudgetMeasured === false,
                  "profiler offscreen não pode alegar medição física")
            Qt.exit(failures === 0 ? 0 : 1)
        }
    }
}
