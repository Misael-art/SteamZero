// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// VS-03 — cenário de captura de SHELL pertencente ao projeto.
//
// Contraparte de `CaptureSceneHarness.qml` para a cena + estado de foco: cada
// nó em `config.nodes` é um modelo renderizado por SceneText.qml,
// SceneImage.qml ou SceneFocusRing.qml conforme `kind` ("text"/"image"/"focus").
// O relatório geométrico é uma LISTA, um item por nó — o anel de foco entra
// como um nó a mais, para que o teste possa provar onde ele está.
//
// `mediaFiles` faz o mesmo papel dos demais harnesses: o test-double do
// mapeamento de assets do shell, chave `assets/...` -> arquivo real.
import QtQuick
import QtQuick.Window
import "../../src/steamzero/ui/qml"

Window {
    id: stage

    property var config: parseConfig()
    readonly property var nodes: config.nodes !== undefined ? config.nodes : []
    readonly property var mediaFiles: config.mediaFiles !== undefined ? config.mediaFiles : ({})

    function parseConfig() {
        var args = Qt.application.arguments
        for (var i = 0; i < args.length - 1; i++) {
            if (args[i] === "--config-json")
                return JSON.parse(args[i + 1])
        }
        console.error("HARNESS-FAIL QML-VISUAL-CAPTURE-005 runner não passou --config-json")
        Qt.exit(2)
        return {}
    }

    function fail(code, detail) {
        console.error("HARNESS-FAIL " + code + " " + detail)
        Qt.exit(2)
    }

    // Resolve o source de nó de imagem no arquivo real (papel do shell, aqui
    // do runner) e devolve um modelo pronto para a cena.
    function resolveModel(node) {
        var copy = {}
        for (var key in node)
            copy[key] = node[key]
        if (node.kind === "image") {
            var resolved = mediaFiles[node.source]
            if (resolved === undefined || resolved === "") {
                fail("QML-VISUAL-CAPTURE-005",
                     "runner não mapeou o asset '" + node.source + "' em mediaFiles")
                return copy
            }
            copy.source = resolved
        }
        return copy
    }

    // Componentes do PRODUTO, resolvidos pelo caminho relativo — o mesmo da
    // diretiva `import`. `setSource` com propriedades iniciais é a única forma
    // de satisfazer a `required property var model` na criação (um Loader não
    // expõe `setSourceComponent` no Qt 6.11).
    readonly property string textSource: Qt.resolvedUrl("../../src/steamzero/ui/qml/SceneText.qml")
    readonly property string imageSource: Qt.resolvedUrl("../../src/steamzero/ui/qml/SceneImage.qml")
    readonly property string focusSource: Qt.resolvedUrl("../../src/steamzero/ui/qml/SceneFocusRing.qml")

    width: config.canvasWidth !== undefined ? config.canvasWidth : 1920
    height: config.canvasHeight !== undefined ? config.canvasHeight : 1080
    color: config.background !== undefined ? config.background : "#000000"
    visible: true

    property int frameCount: 0
    property bool captured: false

    Rectangle {
        id: canvas
        anchors.fill: parent
        color: stage.color
    }

    Repeater {
        id: nodesRepeater
        model: stage.nodes

        delegate: Loader {
            id: nodeLoader
            property var nodeData: modelData

            onNodeDataChanged: loadNode()
            Component.onCompleted: loadNode()

            function loadNode() {
                if (nodeData === undefined)
                    return
                var url = stage.kindSource(nodeData.kind)
                setSource(url, { "model": stage.resolveModel(nodeData) })
            }
        }
    }

    function kindSource(kind) {
        switch (kind) {
        case "image": return imageSource
        case "focus": return focusSource
        default: return textSource
        }
    }

    // Nomes canônicos do adapter (`_FILL_MODE`), não os números do enum do Qt.
    function fillModeName(mode) {
        switch (mode) {
        case Image.Stretch: return "Stretch"
        case Image.PreserveAspectFit: return "PreserveAspectFit"
        case Image.PreserveAspectCrop: return "PreserveAspectCrop"
        case Image.Original: return "Original"
        }
        return "unknown"
    }

    function nodeReport(item) {
        var report = {
            "id": item.objectName,
            "x": item.x,
            "y": item.y,
            "width": item.width,
            "height": item.height,
            "implicitWidth": item.implicitWidth,
            "implicitHeight": item.implicitHeight,
            "visible": item.visible,
            "opacity": item.opacity
        }
        if (item.border !== undefined) {
            report.kind = "focus"
            report.color = item.border.color.toString()
            report.borderWidth = item.border.width
        } else if (item.text !== undefined) {
            report.kind = "text"
            report.text = item.text
            report.contentWidth = item.contentWidth
            report.contentHeight = item.contentHeight
            report.color = item.color.toString()
        } else {
            report.kind = "image"
            report.source = item.source
            report.paintedWidth = item.paintedWidth
            report.paintedHeight = item.paintedHeight
            report.sourceSizeWidth = item.sourceSize.width
            report.sourceSizeHeight = item.sourceSize.height
            report.fillMode = stage.fillModeName(item.fillMode)
        }
        return report
    }

    function geometryReport() {
        var reports = []
        for (var i = 0; i < nodesRepeater.count; i++) {
            var item = nodesRepeater.itemAt(i).item
            if (item !== null)
                reports.push(nodeReport(item))
        }
        return {
            "nodes": reports,
            "count": reports.length,
            "canvasWidth": stage.width,
            "canvasHeight": stage.height,
            "devicePixelRatio": Screen.devicePixelRatio
        }
    }

    function capture() {
        if (captured)
            return
        captured = true

        if (stage.width <= 0 || stage.height <= 0) {
            fail("QML-VISUAL-CAPTURE-005", "janela sem tamanho válido")
            return
        }

        if (nodesRepeater.count !== stage.nodes.length) {
            fail("QML-VISUAL-CAPTURE-005", "nem todo nó instanciou")
            return
        }

        for (var i = 0; i < nodesRepeater.count; i++) {
            var item = nodesRepeater.itemAt(i).item
            if (item === null || item === undefined) {
                fail("QML-VISUAL-CAPTURE-005", "nó " + i + " não instanciou")
                return
            }
            if (item.status !== undefined && item.status !== Image.Ready) {
                fail("QML-VISUAL-CAPTURE-005",
                     "imagem do nó '" + item.objectName + "' não carregou (status "
                     + item.status + "); arquivo ausente ou ilegível: " + item.source)
                return
            }
            if (item.text !== undefined && item.horizontalAlignment === undefined) {
                fail("QML-VISUAL-CAPTURE-005", "texto do nó '" + item.objectName + "' não resolveu")
                return
            }
        }

        var grabbed = stage.contentItem.grabToImage(function(result) {
            if (result === null || result.image.width === 0 || result.image.height === 0) {
                fail("QML-VISUAL-EMPTY-IMAGE-006", "grabToImage devolveu imagem vazia")
                return
            }
            if (!result.saveToFile(config.imagePath)) {
                fail("QML-VISUAL-CAPTURE-005", "saveToFile falhou em " + config.imagePath)
                return
            }
            console.info("HARNESS-GEOMETRY " + JSON.stringify(stage.geometryReport()))
            console.info("HARNESS-CAPTURED " + config.imagePath)
            Qt.exit(0)
        })

        if (!grabbed)
            fail("QML-VISUAL-CAPTURE-005", "grabToImage recusou o pedido")
    }

    Connections {
        target: stage
        function onAfterRendering() {
            stage.frameCount += 1
            if (stage.frameCount >= 2)
                Qt.callLater(stage.capture)
        }
    }

    Component.onCompleted: {
        if (config.imagePath === undefined)
            fail("QML-VISUAL-CAPTURE-005", "runner não informou imagePath")
    }
}