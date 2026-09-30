// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Captura de tela do diálogo "Importar cena RetroFE" nos dois viewports que a
// auditoria UX-05/UX-07 mediu (949x593 compacto e 1280x800 largo), para a pasta
// de evidência do lote RC-01.
//
// A prova de comportamento (teclas reais, foco alcançado, retângulo inteiro na
// banda) está em tests/qml/check_retrofe_import_dialog_compact_viewport.qml,
// executada por tests/integration/test_retrofe_import_dialog_compact.py. Este
// arquivo só produz imagem: nenhuma asserção de contrato vive aqui, e a cena é
// montada com dados locais — nada é publicado no host.
//
// Roda com o binário `qml` (a raiz é uma Window) e aceita --output-dir= e
// --label=, o que permite capturar o mesmo cenário antes e depois da correção
// sem duplicar nada. As imagens são renderizadas offscreen: provam geometria,
// não a release instalada no host.
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
        "2-compacto-foco-rola-destino",
        "3-compacto-relatorio-extenso",
        "4-largo-relatorio-extenso"
    ]

    property int captureIndex: 0
    property int phase: 10
    property int ticks: 0
    property bool reportLongo: false
    property var publishedPayload: null

    readonly property string longReport:
        "O layout relata referências que precisam de revisão antes da publicação. "

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
        if (actionId === "theme.import.retrofe.inspect") {
            callback({"layouts": [
                {"id": "main", "name": "Main",
                 "report": {"elements": 8, "degraded": 1},
                 "assets": {"available": ["assets/logo.png"], "missing": [],
                            "refused": [], "ready": true}}
            ]})
            return
        }
        if (actionId === "theme.import.retrofe.apply") {
            harness.publishedPayload = payload
            if (harness.reportLongo) {
                // Mesmo relatório extenso do harness de contrato: 24 frases.
                errorCallback(new Array(25).join(harness.longReport))
            } else {
                callback({"sceneId": payload.sceneId || "", "activated": false})
            }
        }
    }

    ThemeEditorPanel {
        id: panel
        anchors.fill: parent
        request: harness.request
        requestAction: harness.requestAction
        activeThemeId: "org.steamzero.default"
    }

    /// Popup não expõe `children`: o corpo está em `contentItem` e as ações em
    /// `footer`. Varer as duas pontas é o que encontra um controle do corpo ou
    /// do rodapé.
    function findInDialog(name) {
        const dialog = panel.retrofeImportDialogControl
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
    /// reentra na mesma fase enquanto a imagem ainda não saiu e o `captureIndex`
    /// passa do fim da lista (medido sob carga: "capturas=5 de 4" com um arquivo
    /// `undefined-gate.png` e rc=1, intercalado com execuções 4 de 4 — é corrida).
    /// 500 é a fase "grab em andamento", que nenhum ramo trata.
    ///
    /// `rectOf`/`rectOfPopup` publicam os retângulos reais da cena junto de cada
    /// PNG. Um arquivo com o tamanho certo não prova nada sozinho: é a geografia
    /// da captura que diz ONDE o gate deve achar tinta, e por que caminho o
    /// conteúdo saiu da banda.
    function rectOf(item) {
        if (!item)
            return "ausente"
        const topLeft = item.mapToItem(harness.contentItem, 0, 0)
        const bottomRight = item.mapToItem(harness.contentItem, item.width, item.height)
        return Math.round(topLeft.x) + "," + Math.round(topLeft.y) + ","
            + Math.round(bottomRight.x - topLeft.x) + ","
            + Math.round(bottomRight.y - topLeft.y)
    }

    function rectOfPopup(popup) {
        if (!popup)
            return "ausente"
        return Math.round(popup.x) + "," + Math.round(popup.y) + ","
            + Math.round(popup.width) + "," + Math.round(popup.height)
    }

    function geometryLine(name) {
        return "GEOMETRIA|" + name
            + "|janela=" + Math.round(harness.width) + "x" + Math.round(harness.height)
            + "|dialogo=" + harness.rectOfPopup(panel.retrofeImportDialogControl)
            + "|corpo=" + harness.rectOf(panel.retrofeImportDialogControl.contentItem)
            + "|rodape=" + harness.rectOf(panel.retrofeImportDialogControl.footer)
            + "|acao=" + harness.rectOf(panel.retrofeImportApplyControl)
    }

    function capture(nextPhase) {
        harness.phase = 500
        harness.contentItem.grabToImage(function(result) {
            const nome = harness.captureNames[harness.captureIndex]
            const path = harness.outputDirectory + "/" + nome + "-" + harness.label + ".png"
            console.log((result.saveToFile(path) ? "CAPTURADO " : "FALHA ") + path)
            console.log(harness.geometryLine(nome))
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
                panel.retrofeImportSource = "/tmp/retrofe"
                panel.inspectRetrofeImport()
                harness.phase = 20
                return
            }
            if (harness.phase === 20) {
                if (!harness.until(function() {
                        return panel.retrofeImportLayouts.length === 1
                    }))
                    return
                panel.retrofeImportDialogControl.open()
                harness.phase = 30
                return
            }
            if (harness.phase === 30) {
                if (!harness.until(function() {
                        return panel.retrofeImportDialogControl.visible === true
                    }))
                    return
                panel.retrofeImportSceneId = "org.exemplo.retrofe"
                panel.retrofeImportName = "Cena RetroFE"
                panel.retrofeImportAuthor = "Autor RetroFE"
                panel.retrofeImportLicense = "CC0-1.0"
                harness.phase = 40
                return
            }
            if (harness.phase === 40) {
                if (harness.until(function() {
                        return panel.retrofeImportApplyControl.enabled === true
                    }))
                    harness.capture(50)
                return
            }
            if (harness.phase === 50) {
                const license = harness.findInDialog("themeImportRetrofeLicense")
                if (license && license.activeFocus !== true)
                    license.forceActiveFocus(Qt.TabFocusReason)
                if (harness.until(function() {
                        return license && license.activeFocus === true
                    }))
                    harness.capture(60)
                return
            }
            if (harness.phase === 60) {
                harness.reportLongo = true
                panel.applyRetrofeImport()
                if (harness.until(function() {
                        const notice = harness.findInDialog("themeImportRetrofeNotice")
                        return notice && notice.implicitHeight > 200
                    }))
                    harness.capture(70)
                return
            }
            if (harness.phase === 70) {
                harness.width = 1280
                harness.height = 800
                if (harness.until(function() {
                        return Math.round(panel.width) === 1280
                            && Math.round(panel.retrofeImportDialogControl.height) === 650
                    }))
                    harness.capture(80)
                return
            }
            if (harness.phase === 80) {
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
