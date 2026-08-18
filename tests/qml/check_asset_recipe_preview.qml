// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Window
import "../../src/steamzero/ui/qml"

Window {
    id: harness
    visible: true
    width: 360
    height: 220
    color: "transparent"

    property int failures: 0
    property int captureIndex: 0
    property real thinScale: 0
    property real thickScale: 0
    readonly property var captureNames: [
        "original", "colored", "grayscale", "black", "white",
        "outlineThin", "outlineThick", "outlinedGlow", "outlinedShadow"
    ]
    readonly property string outputDirectory: {
        const prefix = "--output-dir="
        for (let i = 0; i < Qt.application.arguments.length; ++i) {
            if (Qt.application.arguments[i].startsWith(prefix))
                return Qt.application.arguments[i].slice(prefix.length)
        }
        return ""
    }

    readonly property var recipes: ({
        "original": {"source": "logo", "nodes": [], "fallback": "source"},
        "colored": {"source": "logo", "fallback": "source", "nodes": [{
            "type": "recolor", "parameters": {"color": "#22d3ee", "opacity": 1},
            "capability": "graphics.asset.recolor", "cost": "low", "fallback": "source"
        }]},
        "grayscale": {"source": "logo", "fallback": "source", "nodes": [{
            "type": "grayscale", "parameters": {"amount": 1},
            "capability": "graphics.asset.grayscale", "cost": "low", "fallback": "source"
        }]},
        "black": {"source": "logo", "fallback": "source", "nodes": [{
            "type": "silhouette", "parameters": {"color": "#000000", "opacity": 1},
            "capability": "graphics.asset.silhouette", "cost": "low", "fallback": "source"
        }]},
        "white": {"source": "logo", "fallback": "source", "nodes": [{
            "type": "silhouette", "parameters": {"color": "#ffffff", "opacity": 1},
            "capability": "graphics.asset.silhouette", "cost": "low", "fallback": "source"
        }]},
        "outlineThin": {"source": "logo", "fallback": "source", "nodes": [{
            "type": "outline", "parameters": {
                "width": 2, "color": "#ffffff", "opacity": 1,
                "position": "outer", "mask": "alpha"
            },
            "capability": "graphics.asset.outline.outer", "cost": "medium",
            "fallback": "outer"
        }]},
        "outlineThick": {"source": "logo", "fallback": "source", "nodes": [{
            "type": "outline", "parameters": {
                "width": 8, "color": "#000000", "opacity": 1,
                "position": "outer", "mask": "alpha"
            },
            "capability": "graphics.asset.outline.outer", "cost": "medium",
            "fallback": "outer"
        }]},
        "outlinedGlow": {"source": "logo", "fallback": "source", "nodes": [{
            "type": "recolor", "parameters": {"color": "#22d3ee", "opacity": 1},
            "capability": "graphics.asset.recolor", "cost": "low", "fallback": "source"
        }, {
            "type": "outline", "parameters": {
                "width": 3, "color": "#ffffff", "opacity": 0.9,
                "position": "outer", "mask": "alpha"
            },
            "capability": "graphics.asset.outline.outer", "cost": "medium",
            "fallback": "outer"
        }, {
            "type": "glow", "parameters": {"color": "#22d3ee", "strength": 0.55, "blur": 18},
            "capability": "graphics.effect.glow", "cost": "high", "fallback": "source"
        }]},
        "outlinedShadow": {"source": "logo", "fallback": "source", "nodes": [{
            "type": "outline", "parameters": {
                "width": 3, "color": "#ffffff", "opacity": 1,
                "position": "outer", "mask": "alpha"
            },
            "capability": "graphics.asset.outline.outer", "cost": "medium",
            "fallback": "outer"
        }, {
            "type": "shadow", "parameters": {
                "color": "#000000", "opacity": 0.7, "blur": 10,
                "offsetX": 4, "offsetY": 6
            },
            "capability": "graphics.effect.shadow", "cost": "medium", "fallback": "source"
        }]}
    })

    function check(condition, message) {
        if (!condition) {
            failures += 1
            console.error("FAIL: " + message)
        }
    }

    function finish() {
        check(preview.sourceDecodeCount === 1,
              "trocar receita não pode decodificar a fonte novamente")
        check(thickScale > thinScale,
              "contorno grosso precisa ter escala visual maior que o fino")
        Qt.exit(failures === 0 ? 0 : 1)
    }

    function nextCapture() {
        if (captureIndex >= captureNames.length) {
            finish()
            return
        }
        const name = captureNames[captureIndex]
        preview.recipe = recipes[name]
        if (name === "outlineThin")
            thinScale = preview.outlineScale
        if (name === "outlineThick")
            thickScale = preview.outlineScale
        captureTimer.restart()
    }

    AssetRecipePreview {
        id: preview
        anchors.centerIn: parent
        width: 320
        height: 180
        source: Qt.resolvedUrl(
            "../../src/steamzero/themes/org.steamzero.asset-recipes-demo/assets/source.svg")
        recipe: harness.recipes.original
    }

    Timer {
        id: readyTimer
        interval: 180
        running: true
        repeat: false
        onTriggered: {
            check(preview.sourceStatus === Image.Ready, "asset-fonte transparente precisa carregar")
            nextCapture()
        }
    }

    Timer {
        id: captureTimer
        interval: 60
        repeat: false
        onTriggered: {
            const name = harness.captureNames[harness.captureIndex]
            if (name === "colored")
                harness.check(preview.recolorNode !== null,
                              "receita colored precisa chegar ao renderer")
            if (name === "colored")
                harness.check(preview.appliedColorization === 1,
                              "recolor precisa ativar colorization")
            if (name === "grayscale")
                harness.check(preview.grayscaleNode !== null,
                              "receita grayscale precisa chegar ao renderer")
            if (name === "grayscale")
                harness.check(preview.appliedSaturation === -1,
                              "grayscale precisa remover saturação")
            if (name === "black" || name === "white")
                harness.check(preview.silhouetteNode !== null,
                              "receita silhouette precisa chegar ao renderer")
            if (name === "outlineThin" || name === "outlineThick")
                harness.check(preview.outlineNode !== null,
                              "receita outline precisa chegar ao renderer")
            if (name === "outlineThin" || name === "outlineThick")
                harness.check(preview.outlineActive,
                              "outline precisa ativar a camada alpha")
            if (harness.outputDirectory === "") {
                harness.captureIndex += 1
                harness.nextCapture()
                return
            }
            preview.grabToImage(function(result) {
                const saved = result.saveToFile(harness.outputDirectory + "/" + name + ".png")
                harness.check(saved, "captura precisa ser gravada para " + name)
                harness.captureIndex += 1
                harness.nextCapture()
            })
        }
    }
}
