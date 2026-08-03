// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// VS-03 — cenário de captura de IMAGEM pertencente ao projeto.
//
// Contraparte de `CaptureHarness.qml` para `SceneImage.qml`. Mesma postura:
// o runner decide aprovação em Python olhando artefatos; este arquivo é um
// cenário controlado.
//
// `mediaFiles` é o test-double do mapeamento do shell: chave `assets/...` do
// modelo -> caminho real do arquivo no disco do runner. O QML não resolve
// asset sozinho — o shell mapeia, e aqui o runner faz o papel do shell.
import QtQuick
import QtQuick.Window
import "../../src/steamzero/ui/qml"

Window {
    id: stage

    property var config: parseConfig()
    readonly property var model: config.model !== undefined ? config.model : ({})
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

    // A resolução de asset é do shell (aqui, do runner). O componente da
    // cena continua burro: recebe um modelo já apontando para o arquivo.
    function resolvedModel() {
        var source = model.source
        var resolved = mediaFiles[source]
        if (resolved === undefined || resolved === "") {
            fail("QML-VISUAL-CAPTURE-005",
                 "runner não mapeou o asset '" + source + "' em mediaFiles")
            return model
        }
        var copy = {}
        for (var key in model)
            copy[key] = model[key]
        copy.source = resolved
        return copy
    }

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

    SceneImage {
        id: subject
        model: stage.resolvedModel()
    }

    function fail(code, detail) {
        console.error("HARNESS-FAIL " + code + " " + detail)
        Qt.exit(2)
    }

    // Relatório geométrico. `paintedWidth`/`paintedHeight` são o que a imagem
    // REALMENTE ocupa após o scale do fillMode — é o que prova que o crop
    // aconteceu, em números, sem depender de olhar a imagem.
    function geometryReport() {
        return {
            "id": subject.objectName,
            "x": subject.x,
            "y": subject.y,
            "width": subject.width,
            "height": subject.height,
            "implicitWidth": subject.implicitWidth,
            "implicitHeight": subject.implicitHeight,
            "paintedWidth": subject.paintedWidth,
            "paintedHeight": subject.paintedHeight,
            "sourceSizeWidth": subject.sourceSize.width,
            "sourceSizeHeight": subject.sourceSize.height,
            "visible": subject.visible,
            "opacity": subject.opacity,
            "fillMode": subject.fillMode,
            "source": subject.source,
            "status": subject.status,
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

        if (subject.status !== Image.Ready) {
            fail("QML-VISUAL-CAPTURE-005",
                 "imagem não carregou (status " + subject.status + "); "
                 + "arquivo ausente ou ilegível: " + subject.source)
            return
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
