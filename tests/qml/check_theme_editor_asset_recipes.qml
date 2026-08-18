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
            Qt.exit(failures === 0 ? 0 : 1)
        }
    }
}
