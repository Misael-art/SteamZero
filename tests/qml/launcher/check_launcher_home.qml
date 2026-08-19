// SPDX-License-Identifier: GPL-3.0-or-later
//
// Contrato de navegação da home do Launcher. O foco anda pelo mapa resolvido
// no domínio: o QML não escolhe vizinho, não deduz coluna e não inventa
// destino quando a direção não existe.
import QtQuick
import "../../../src/steamzero/ui/qml/launcher"

Item {
    id: harness
    width: 1280
    height: 800

    property int failures: 0
    property int checkIndex: 0
    property int firstFail: -1
    function check(condition, message) {
        checkIndex += 1
        if (!condition) {
            failures += 1
            if (firstFail < 0)
                firstFail = checkIndex
            console.error("FAIL #" + checkIndex + ": " + message)
        }
    }

    readonly property var sections: [
        {"id": "continue", "title": "Continuar",
         "items": [{"id": "celeste", "title": "Celeste"}, {"id": "hades", "title": "Hades"}]},
        {"id": "library", "title": "Biblioteca",
         "items": [{"id": "tunic", "title": "Tunic"}, {"id": "axiom", "title": "Axiom Verge"}]}
    ]

    readonly property var focusMap: ({
        "initial": "continue:celeste",
        "rows": ["header:home", "continue:celeste", "library:tunic"],
        "diagnostics": [],
        "nodes": {
            "header:home": {"id": "header:home", "section": "header", "column": 0,
                            "up": null, "down": "continue:celeste", "left": null,
                            "right": null, "action": null},
            "continue:celeste": {"id": "continue:celeste", "section": "continue", "column": 0,
                                 "up": "header:home", "down": "library:tunic",
                                 "left": "continue:hades", "right": "continue:hades",
                                 "action": null},
            "continue:hades": {"id": "continue:hades", "section": "continue", "column": 1,
                               "up": "header:home", "down": "library:axiom",
                               "left": "continue:celeste", "right": "continue:celeste",
                               "action": null},
            "library:tunic": {"id": "library:tunic", "section": "library", "column": 0,
                              "up": "continue:celeste", "down": null,
                              "left": "library:axiom", "right": "library:axiom",
                              "action": null},
            "library:axiom": {"id": "library:axiom", "section": "library", "column": 1,
                              "up": "continue:hades", "down": null,
                              "left": "library:tunic", "right": "library:tunic",
                              "action": null}
        }
    })

    LauncherHome {
        id: home
        anchors.fill: parent
        focusMap: harness.focusMap
        sections: harness.sections
    }

    Timer {
        interval: 80
        running: true
        repeat: false
        onTriggered: {
            harness.check(home.currentFocus === "continue:celeste",
                          "a home precisa começar no foco inicial resolvido")
            home.move("right")
            harness.check(home.currentFocus === "continue:hades", "direita não seguiu o mapa")
            home.move("down")
            harness.check(home.currentFocus === "library:axiom",
                          "descer precisa preservar a coluna pelo mapa")
            // Direção sem destino não pode zerar o foco nem sair do mapa.
            home.move("down")
            harness.check(home.currentFocus === "library:axiom",
                          "direção sem destino precisa manter o foco onde está")
            home.move("up")
            home.move("up")
            harness.check(home.currentFocus === "header:home", "subir não chegou ao cabeçalho")

            // Varredura: nenhuma sequência de direcionais tira o foco do mapa.
            const dirs = ["up", "down", "left", "right"]
            for (let i = 0; i < 60; ++i) {
                home.move(dirs[i % 4])
                if (home.focusMap.nodes[home.currentFocus] === undefined) {
                    harness.check(false, "foco saiu do mapa após " + i + " movimentos")
                    break
                }
            }
            harness.check(home.focusedItemCount === 4,
                          "a home precisa instanciar um item focável por entrada")
            // O destaque tem de cair no item certo: contar itens não prova
            // que a chave do nó bate com a do mapa.
            harness.check(home.itemIndex.indexOf("continue:celeste") >= 0
                          && home.itemIndex.indexOf("library:axiom") >= 0,
                          "as chaves dos itens precisam ser as mesmas do mapa de foco")
            home.currentFocus = "library:tunic"
            harness.check(home.highlightedCount === 1,
                          "exatamente um item pode estar destacado por vez")
            harness.check(home.highlightedNode === "library:tunic",
                          "o destaque precisa cair no nó em foco")
            Qt.exit(harness.failures === 0 ? 0 : 1)
        }
    }
}
