// SPDX-License-Identifier: GPL-3.0-or-later
//
// Contrato do node de cor builtin, exercitado nos DOIS runtimes:
// onde o módulo de efeitos existe (host de desenvolvimento) o efeito é
// instanciado; onde não existe (imagem canônica do gate visual) o node precisa
// se declarar indisponível. O mesmo arquivo prova os dois caminhos, e a
// asserção que interessa vale sempre: nunca `available` e `unsupported` ambos
// falsos com um efeito pedido — isso seria sumiço silencioso.
import QtQuick
import "../../src/steamzero/ui/qml"

Item {
    id: harness
    width: 120
    height: 120

    property int failures: 0
    function check(condition, message) {
        if (!condition) {
            failures += 1
            console.error("FAIL: " + message)
        }
    }

    Image { id: fonte; anchors.fill: parent; source: "" }

    AssetColorTransform {
        id: semPedido
        anchors.fill: parent
        source: fonte
        mode: ""
    }

    AssetColorTransform {
        id: invertido
        anchors.fill: parent
        source: fonte
        mode: "invert"
    }

    AssetColorTransform {
        id: matiz
        anchors.fill: parent
        source: fonte
        mode: "hueRotate"
        hue: 0.33
    }

    Timer {
        interval: 60
        running: true
        repeat: false
        onTriggered: {
            harness.check(semPedido.requested === false,
                          "sem mode declarado o node não pode pedir efeito")
            harness.check(semPedido.unsupported === false,
                          "node sem pedido não pode alegar indisponibilidade")

            const nodes = [invertido, matiz]
            for (let i = 0; i < nodes.length; ++i) {
                const node = nodes[i]
                harness.check(node.requested === true,
                              "mode allowlisted precisa registrar o pedido")
                harness.check(node.available || node.unsupported,
                              "efeito pedido precisa aplicar ou declarar indisponibilidade")
                harness.check(!(node.available && node.unsupported),
                              "aplicar e declarar indisponível ao mesmo tempo é contraditório")
            }
            Qt.exit(harness.failures === 0 ? 0 : 1)
        }
    }
}
