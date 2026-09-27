// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Captura de tela do diálogo "Importar tema ES-DE" nos viewports que a auditoria
// UX-05/UX-07 mediu (949x593 compacto e 1280x800 largo), para a pasta de
// evidência da terceira fatia de RC-01.
//
// A prova de comportamento (teclas reais, foco alcançado, retângulo inteiro na
// banda) está em tests/qml/check_esde_import_dialog_compact_viewport.qml,
// executada por tests/integration/test_esde_import_dialog_compact.py. Este
// arquivo só produz imagem: nenhuma asserção de contrato vive aqui, e a cena é
// montada com dados locais — nada é publicado no host.
//
// As cinco fases foram escolhidas para rodarem na MESMA cena antes e depois da
// correção: cada espera é uma condição que existe nas duas árvores (campo de
// origem, botão habilitado, foco pedido por forceActiveFocus, altura implícita
// do aviso, largura do painel). Por isso `--label=antes` e `--label=depois`
// produzem pares comparáveis sem duplicar nada. As imagens são renderizadas
// offscreen: provam geometria, não a release instalada no host.
import QtQuick
import QtQuick.Controls
import QtQuick.Window
import "../../src/steamzero/ui/qml"

Window {
    id: harness
    visible: true
    width: 949
    height: 593
    color: "#071019"

    readonly property string outputDirectory: harness.argument("--output-dir=", "/tmp")
    readonly property string label: harness.argument("--label=", "atual")
    readonly property var captureNames: [
        "1-compacto-acoes-e-corpo",
        "2-compacto-listagem-24-esquemas",
        "3-compacto-rodape-fixo-com-campo-de-nome-focado",
        "4-compacto-relatorio-extenso",
        "5-largo-relatorio-extenso"
    ]

    property int captureIndex: 0
    property int phase: 10
    property int ticks: 0
    property bool reportLongo: false
    property bool extensiveSchemes: false
    property var publishedPayload: null

    readonly property string longReport:
        "Falha ao converter o tema ES-DE: esquemas com paleta fora do espaço de cor, "
        + "arquivos de referência ausentes, tema-monocromático sem derivação possível "
        + "e um caminho recusado por estar fora da raiz permitida. "

    function argument(prefix, fallback) {
        const args = Qt.application.arguments
        for (let i = 0; i < args.length; i++) {
            if (args[i].startsWith(prefix))
                return args[i].slice(prefix.length)
        }
        return fallback
    }

    function request(method, path, _payload, callback) {
        if (method === "GET" && path === "/theme/list")
            callback({"themes": []})
    }

    function requestAction(actionId, payload, callback, errorCallback) {
        if (actionId === "theme.import.esde.inspect") {
            if (harness.extensiveSchemes) {
                const schemes = []
                for (let i = 0; i < 24; i++)
                    schemes.push({"scheme": "esquema-" + i, "isMonochrome": i % 3 === 0})
                callback({"schemes": schemes})
            } else {
                callback({"schemes": [{"scheme": "principal", "isMonochrome": false}]})
            }
            return
        }
        if (actionId === "theme.import.esde.apply") {
            harness.publishedPayload = payload
            if (harness.reportLongo)
                errorCallback(harness.longReport.repeat(24), {})
            else
                callback({"themeId": payload.name, "activated": false})
        }
    }

    ThemeEditorPanel {
        id: panel
        anchors.fill: parent
        request: harness.request
        requestAction: harness.requestAction
        activeThemeId: "org.steamzero.default"
    }

    /// Popup não expõe `children`: o corpo está em `contentItem` e, na forma
    /// corrigida, as ações vivem em `footer`. Varer as duas pontas é o que
    /// encontra o controle nas duas árvores (antes: tudo no corpo; depois:
    /// corpo rolável + rodapé).
    function findInDialog(name) {
        const dialog = panel.esdeImportDialogControl
        const roots = []
        if (dialog) {
            roots.push(dialog.contentItem)
            roots.push(dialog.footer)
        }
        const stack = roots.slice()
        while (stack.length) {
            const item = stack.pop()
            if (!item)
                continue
            if (item.objectName === name)
                return item
            const kids = item.children !== undefined ? item.children : []
            for (let i = 0; i < kids.length; i++)
                stack.push(kids[i])
        }
        return null
    }

    /// Window não é Item: quem tem grabToImage é o contentItem da janela, que
    /// inclui o overlay onde o Popup é renderizado.
    /// `grabToImage` é assíncrono: sem tomar a fase antes do grab, o Timer de 20 ms
    /// reentra na mesma fase enquanto a imagem ainda não saiu (medido — mais
    /// capturas que nomes, com `undefined-<rotulo>.png` e rc=1; é corrida, por isso
    /// o total varia de execução), e o `captureIndex` passa do fim da lista.
    /// 500 é a fase "grab em andamento", que nenhum ramo trata.
    function capture(nextPhase) {
        harness.phase = 500
        harness.contentItem.grabToImage(function(result) {
            const path = harness.outputDirectory + "/"
                + harness.captureNames[harness.captureIndex] + "-" + harness.label + ".png"
            console.log((result.saveToFile(path) ? "CAPTURADO " : "FALHA ") + path)
            harness.captureIndex += 1
            harness.phase = nextPhase
        }, Qt.size(harness.width, harness.height))
    }

    /// Espera uma condição observável com limite de tempo: estourar o limite é
    /// falha explícita, não captura silenciosa pela metade.
    function until(condition) {
        if (condition()) {
            harness.ticks = 0
            return true
        }
        harness.ticks += 1
        if (harness.ticks > 250) {
            console.log("TIMEOUT na fase " + harness.phase)
            Qt.exit(1)
        }
        return false
    }

    Timer {
        interval: 20
        running: true
        repeat: true
        onTriggered: {
            if (harness.phase === 10) {
                panel.esdeImportSource = "/tmp/esde-tema"
                panel.inspectEsdeImport()
                harness.phase = 20
                return
            }
            if (harness.phase === 20) {
                if (!harness.until(function() {
                        return panel.esdeImportSchemes.length === 1
                    }))
                    return
                panel.esdeImportDialogControl.open()
                harness.phase = 30
                return
            }
            if (harness.phase === 30) {
                if (!harness.until(function() {
                        return panel.esdeImportDialogControl.visible === true
                    }))
                    return
                panel.esdeImportName = "Tema ES-DE de exemplo"
                harness.phase = 40
                return
            }
            if (harness.phase === 40) {
                if (harness.until(function() {
                        return panel.esdeImportApplyControl.enabled === true
                    }))
                    harness.capture(50)
                return
            }
            if (harness.phase === 50) {
                // Conteúdo extenso de verdade: 24 esquemas publicados pelo examine.
                harness.extensiveSchemes = true
                panel.inspectEsdeImport()
                if (harness.until(function() {
                        return panel.esdeImportSchemes.length === 24
                    }))
                    harness.capture(60)
                return
            }
            if (harness.phase === 60) {
                // Foco PROGRAMÁTICO de propósito: ele mostra o rodapé fixo com o
                // corpo ainda acima da dobra, e é exatamente por isso que a imagem
                // não prova rolagem — revelar o destino focado é caminho do D-pad
                // real, medido no harness de contrato (test_03/test_07), não aqui.
                const name = harness.findInDialog("themeImportEsdeName")
                if (name && name.activeFocus !== true)
                    name.forceActiveFocus(Qt.TabFocusReason)
                if (harness.until(function() {
                        return name && name.activeFocus === true
                    }))
                    harness.capture(70)
                return
            }
            if (harness.phase === 70) {
                harness.reportLongo = true
                panel.applyEsdeImport()
                if (harness.until(function() {
                        const notice = harness.findInDialog("themeImportEsdeNotice")
                        return notice && notice.implicitHeight > 200
                    }))
                    harness.capture(80)
                return
            }
            if (harness.phase === 80) {
                harness.width = 1280
                harness.height = 800
                if (harness.until(function() {
                        return Math.round(panel.width) === 1280
                            && Math.round(panel.esdeImportDialogControl.height) === 560
                    }))
                    harness.capture(90)
                return
            }
            if (harness.phase === 90) {
                console.log("capturas=" + harness.captureIndex + " de "
                            + harness.captureNames.length)
                Qt.exit(harness.captureIndex === harness.captureNames.length ? 0 : 1)
            }
        }
    }

    Timer {
        interval: 60000
        running: true
        onTriggered: {
            console.log("TIMEOUT geral na fase " + harness.phase)
            Qt.exit(1)
        }
    }
}
