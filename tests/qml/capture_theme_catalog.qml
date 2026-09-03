// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Captura o painel do catálogo de temas nos três estados que importam para a
// evidência da AGENTS §9: o catálogo carregado, o resultado de uma instalação e
// a recuperação de espaço depois de remover.
//
// Os dados vêm de um duplo local: a captura é da TELA, e ligar isto à rede
// tornaria a evidência dependente de um download e do estado do host, que é
// justamente o que a evidência de host separada já cobre.
import QtQuick
import QtQuick.Window
import "../../src/steamzero/ui/qml"

Window {
    id: harness
    visible: true
    width: 1000
    height: 760
    color: "#071019"

    readonly property string outputDirectory: {
        const prefix = "--output-dir="
        for (let i = 0; i < Qt.application.arguments.length; ++i) {
            if (Qt.application.arguments[i].startsWith(prefix))
                return Qt.application.arguments[i].slice(prefix.length)
        }
        return "/tmp"
    }

    property int captureIndex: 0
    // Os nomes descrevem o que a imagem MOSTRA. A terceira captura chamava-se
    // "espaco-recuperado" exibindo o espaço ainda por recuperar — o nome
    // afirmava um estado que a tela não estava mostrando, que é o mesmo defeito
    // de um erro que anuncia a causa errada.
    readonly property var captureNames: [
        "01-catalogo", "02-instalado", "03-remocao-preserva", "04-espaco-recuperado"
    ]

    property var entriesBase: [
        {"id": "org.esde.iconic", "name": "Iconic", "license": "CC0-1.0",
         "credits": ["Siddy212"], "installed": false, "installedVersion": "", "upToDate": false},
        {"id": "org.esde.playstation-x", "name": "PlayStation-X",
         "license": "CC-BY-NC-SA-4.0",
         "credits": ["RobZombie9043", "pajarorrojo (tema original)"],
         "installed": false, "installedVersion": "", "upToDate": false},
        {"id": "org.esde.xmb-menu", "name": "XMB Menu", "license": "CC-BY-NC-SA-2.0",
         "credits": ["anthonycaccese", "InitialDin (XML original)"],
         "installed": false, "installedVersion": "", "upToDate": false},
        {"id": "org.esde.nso-menu", "name": "NSO Menu Interpreted",
         "license": "CC-BY-NC-SA-2.0", "credits": ["anthonycaccese", "rogs123"],
         "installed": false, "installedVersion": "", "upToDate": false},
        {"id": "org.esde.modern", "name": "Modern", "license": "CC-BY-NC-SA-4.0",
         "credits": ["ES-DE"], "installed": false, "installedVersion": "", "upToDate": false}
    ]
    property var excludedBase: [
        {"repo": "RobZombie9043/shinretro-revisited-es-de", "reason": "não declara licença"},
        {"repo": "Weestuarty-es-de/slick-es-de", "reason": "não declara licença"},
        {"repo": "VictorUnlocked/iisu-interpreted-es-de", "reason": "não declara licença"},
        {"repo": "anthonycaccese/retrofix-revisited-es-de", "reason": "não declara licença"}
    ]

    // Estado do duplo, alterado entre as capturas.
    property bool xmbInstalled: false
    property var usage: ({"blobs": 0, "bytes": 0})

    function currentEntries() {
        const out = []
        for (let i = 0; i < entriesBase.length; ++i) {
            const entry = {}
            for (const key in entriesBase[i])
                entry[key] = entriesBase[i][key]
            if (entry.id === "org.esde.xmb-menu" && harness.xmbInstalled) {
                entry.installed = true
                entry.installedVersion = "afe3b7b61cb2"
                entry.upToDate = true
            }
            out.push(entry)
        }
        return out
    }

    ThemeCatalogPanel {
        id: panel
        anchors.fill: parent
        requestAction: function(actionId, payload, callback, _errorCallback) {
            if (actionId === "theme.catalog.list") {
                callback({"entries": harness.currentEntries(),
                          "excluded": harness.excludedBase,
                          "storeUsage": harness.usage})
            } else if (actionId === "theme.store.gc") {
                callback({"dryRun": payload.apply !== true, "orphans": 474,
                          "reclaimedBytes": 69324695})
            } else {
                callback({"operationId": "01OPERACAO"})
            }
        }
    }

    Timer {
        id: settle
        interval: 600
        onTriggered: {
            panel.grabToImage(function(result) {
                result.saveToFile(harness.outputDirectory + "/"
                                  + harness.captureNames[harness.captureIndex] + ".png")
                harness.captureIndex += 1
                harness.advance()
            })
        }
    }

    function advance() {
        if (captureIndex >= captureNames.length) {
            Qt.exit(0)
            return
        }
        if (captureIndex === 1) {
            harness.xmbInstalled = true
            harness.usage = {"blobs": 474, "bytes": 69324695}
            panel.refresh()
        } else if (captureIndex === 2) {
            // Removido, mas os 474 arquivos CONTINUAM no disco: é a propriedade
            // central do desenho, e é isto que a captura precisa mostrar.
            harness.xmbInstalled = false
            harness.usage = {"blobs": 474, "bytes": 69324695}
            panel.refresh()
            panel.gcPreview = {"dryRun": true, "orphans": 474, "reclaimedBytes": 69324695}
            // Rola até o fim: a seção de espaço e a lista de excluídos ficam
            // abaixo da dobra, e uma captura que não mostra o que o nome promete
            // é pior que nenhuma.
            harness.scrollToBottom()
        } else if (captureIndex === 3) {
            // Só agora o espaço volta, e volta porque foi PEDIDO. A captura
            // chama a função REAL do painel em vez de montar o estado final à
            // mão: escrever gcPreview daqui produziria uma tela que o código
            // nunca gera — evidência de um estado impossível.
            harness.usage = {"blobs": 0, "bytes": 0}
            panel.applyGarbage()
            harness.scrollToBottom()
        }
        settle.restart()
    }

    // Encontra o Flickable do ScrollView interno do painel e o leva ao fim.
    function scrollToBottom() {
        const flick = harness.findFlickable(panel)
        if (flick)
            flick.contentY = Math.max(0, flick.contentHeight - flick.height)
    }

    function findFlickable(node) {
        if (node === null || node === undefined)
            return null
        if (node.contentHeight !== undefined && node.contentY !== undefined)
            return node
        for (let i = 0; i < node.children.length; ++i) {
            const found = harness.findFlickable(node.children[i])
            if (found)
                return found
        }
        return null
    }

    Component.onCompleted: harness.advance()
}
