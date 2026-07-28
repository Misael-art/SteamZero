// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// VS-03 — cenário de captura pertencente ao projeto.
//
// Diferença para os dez harnesses legados: eles são o teste. Este não é. Ele é
// um cenário controlado que o `qml_capture_runner.py` executa, e quem decide
// aprovação é o runner, em Python, olhando artefatos.
//
// A distinção importa porque um harness que faz suas próprias asserções e chama
// `Qt.exit(0)` produz verde sem que ninguém tenha olhado um pixel — e um `skip`
// quando o Qt falta produz verde sem que nada tenha rodado. Foi assim que a
// regressão de ícones da a37 atravessou os gates.
//
// O modelo entra por arquivo JSON, já resolvido pelo adapter. Este arquivo não
// conhece TokenRegistry, ReadModel, ThemeSettingRegistry, TranslationCatalog
// nem AssetRegistry, e não tem como conhecer: ele lê um dicionário de escalares.
import QtQuick
import QtQuick.Window
import "../../src/steamzero/ui/qml"

Window {
    id: stage

    // Tudo parametrizado pelo runner. Nenhum default implícito aqui: canvas,
    // cor de fundo e caminhos vêm de fora, para que a mesma cena seja
    // reproduzível byte a byte em outra máquina.
    //
    // A configuração entra pelo argv, como JSON. Não por arquivo: XHR síncrono
    // em `file://` TRAVA o runtime — verificado, não suposto —, e o assíncrono
    // traria uma espera a mais para o capture depender. Argv também mantém o
    // harness sem nenhuma leitura de disco, que é a postura que o resto do
    // motor de temas segue.
    property var config: parseConfig()
    readonly property var model: config.model !== undefined ? config.model : ({})

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

    width: config.canvasWidth !== undefined ? config.canvasWidth : 1920
    height: config.canvasHeight !== undefined ? config.canvasHeight : 1080
    color: config.background !== undefined ? config.background : "#000000"
    visible: true

    // Animação desligada no cenário canônico: um frame capturado no meio de uma
    // transição não é reproduzível, e a diferença apareceria como ruído no
    // golden sem nenhuma mudança real de código.
    property int frameCount: 0
    property bool captured: false

    // Fundo explícito, e não a cor da Window: `grabToImage` no `contentItem`
    // captura os itens, não o `color` da janela — verificado, a primeira captura
    // saiu com fundo transparente. Sem isto o golden congelaria um fundo que não
    // é o configurado, e a checagem de "imagem vazia" não teria referência.
    Rectangle {
        id: canvas
        anchors.fill: parent
        color: stage.color
    }

    SceneText {
        id: subject
        model: stage.model
    }

    // Caractere garantidamente ausente da Liberation Sans. Serve de referência
    // para descobrir a largura da caixa `.notdef` deste ambiente.
    Text {
        id: probe
        visible: false
        font.family: subject.font.family
        font.pixelSize: subject.font.pixelSize
        text: "漢"
    }

    Text {
        id: measure
        visible: false
        font.family: subject.font.family
        font.pixelSize: subject.font.pixelSize
    }

    function glyphWidths() {
        // Mede cada caractere distinto do texto renderizado. O runner cruza
        // com `notdefWidth` para provar que nenhum glifo foi substituído por
        // caixa — algo que a imagem sozinha não denuncia.
        var seen = {}
        var text = subject.text
        for (var i = 0; i < text.length; i++) {
            var glyph = text.charAt(i)
            if (glyph === "\n" || seen[glyph] !== undefined)
                continue
            measure.text = glyph
            seen[glyph] = measure.contentWidth
        }
        return seen
    }

    // Relatório geométrico. Existe para que os gates de layout não dependam de
    // comparação visual: `width` errado é um número errado, e um número errado
    // deve reprovar sem ninguém precisar olhar duas imagens lado a lado.
    function geometryReport() {
        return {
            "id": subject.objectName,
            "x": subject.x,
            "y": subject.y,
            "width": subject.width,
            "height": subject.height,
            "contentWidth": subject.contentWidth,
            "contentHeight": subject.contentHeight,
            "implicitWidth": subject.implicitWidth,
            "implicitHeight": subject.implicitHeight,
            "boundingRect": {
                "x": subject.x,
                "y": subject.y,
                "width": subject.width,
                "height": subject.height
            },
            "visible": subject.visible,
            "opacity": subject.opacity,
            "color": subject.color.toString(),
            "horizontalAlignment": subject.horizontalAlignment,
            "verticalAlignment": subject.verticalAlignment,
            "fontFamilyRequested": stage.model.fontFamily !== undefined ? stage.model.fontFamily : "",
            "fontFamilyResolved": subject.font.family,
            "fontPixelSize": subject.font.pixelSize,
            "fontWeight": subject.font.weight,
            "fontItalic": subject.font.italic,
            "availableFontFamilyCount": Qt.fontFamilies().length,
            "testFontAvailable": stage.model.fontFamily === undefined
                                 || stage.model.fontFamily === ""
                                 || Qt.fontFamilies().indexOf(stage.model.fontFamily) >= 0,
            // O Qt não expõe a família efetivamente adotada. O que dá para
            // afirmar é se a solicitada EXISTE — e é por isso que o harness
            // reprova quando não existe, em vez de registrar um fallback que
            // não teria como comprovar.
            "fallbackDetected": false,
            // Face efetivamente pedida ao Qt. Derivada de peso e itálico porque
            // o Qt não expõe o arquivo escolhido — mas com o fontconfig isolado
            // só existem as quatro empacotadas, então a derivação é exata.
            "resolvedFace": (subject.font.weight >= 700
                             ? (subject.font.italic ? "BoldItalic" : "Bold")
                             : (subject.font.italic ? "Italic" : "Regular")),
            // Detector de glifo ausente. `notdefWidth` é a largura da caixa que
            // o Qt desenha para um caractere que a fonte não tem — medida aqui,
            // não suposta. Um acentuado com essa largura exata é um glifo que
            // sumiu, e a imagem sairia com caixinhas parecendo texto.
            "notdefWidth": probe.contentWidth,
            "glyphWidths": stage.glyphWidths(),
            "canvasWidth": stage.width,
            "canvasHeight": stage.height,
            "devicePixelRatio": Screen.devicePixelRatio
        }
    }

    function fail(code, detail) {
        console.error("HARNESS-FAIL " + code + " " + detail)
        Qt.exit(2)
    }

    function capture() {
        if (captured)
            return
        captured = true

        if (stage.width <= 0 || stage.height <= 0) {
            fail("QML-VISUAL-CAPTURE-005", "janela sem tamanho válido")
            return
        }

        // Conferir `font.family` contra o solicitado NÃO funciona: a
        // propriedade ecoa o que foi atribuído, exista a fonte ou não.
        // Verificado — uma família inexistente e uma real produziram o mesmo
        // `font.family` E o mesmo `contentWidth`, porque as duas renderizaram
        // com o fallback. A checagem parecia rigorosa e não verificava nada.
        //
        // `Qt.fontFamilies()` é a lista do que o Qt REALMENTE tem. Ausência ali
        // significa que o texto sairá com métrica de outra fonte, e um golden
        // congelado assim esconde o problema atrás de uma imagem aprovada.
        var requested = stage.model.fontFamily
        if (requested !== undefined && requested !== "") {
            if (Qt.fontFamilies().indexOf(requested) < 0) {
                fail("QML-VISUAL-FONT-004",
                     "fonte '" + requested + "' não está disponível para o Qt; "
                     + "o texto sairia com a métrica de outra família")
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

    // Espera determinística, não `sleep`. `afterRendering` só dispara quando o
    // scene graph terminou um frame de verdade; contar dois garante que o
    // primeiro, que às vezes sai antes do polish do texto, não seja o capturado.
    //
    // Um timer fixo aqui seria pior de duas formas: curto demais captura tela
    // incompleta e o golden vira flaky; longo demais esconde o problema e ainda
    // desperdiça o tempo em toda execução.
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
